"""The tool layer: six tools over clinic.json.

This file is the ground truth. It never calls an LLM and never guesses.
Every tool validates its arguments and raises ToolError with a specific
message when something is wrong.

One ClinicStore = one private copy of the clinic. Every /agent/run builds a
fresh one, which is how state resets between conversations.
"""

import copy
import json
import re
import threading
from datetime import date
from pathlib import Path

CLINIC_FILE = Path(__file__).resolve().parent.parent / "clinic.json"
CLINIC_DATA = json.loads(CLINIC_FILE.read_text(encoding="utf-8"))

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
ESCALATION_REASONS = (
    "clinical_urgent", "medical_advice", "not_authorised",
    "ambiguous_patient", "out_of_scope",
)

# tool name -> (required arguments, optional arguments)
TOOLS = {
    "search_slots": (("doctor_id", "date"), ()),
    "book_appointment": (("patient_id", "doctor_id", "date", "start"), ()),
    "reschedule_appointment": (("appointment_id", "patient_id", "date", "start"), ()),
    "cancel_appointment": (("appointment_id", "patient_id"), ()),
    "lookup_patient": ((), ("name", "phone", "patient_id")),
    "escalate_to_human": (("reason", "detail"), ()),
}


class ToolError(Exception):
    """A tool refused to run. `code` is machine readable, `message` says how to fix it."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


# ---------- small helpers ----------

def to_minutes(hhmm):
    return int(hhmm[:2]) * 60 + int(hhmm[3:])


def to_hhmm(minutes):
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def name_key(word):
    """Fold common spelling variants of Hindi names: Imraan = Imran, Quraishi = Qureshi."""
    word = re.sub(r"[^a-z]", "", word.lower())
    for old, new in (("ee", "i"), ("oo", "u"), ("ai", "e"), ("au", "o")):
        word = word.replace(old, new)
    return re.sub(r"(.)\1+", r"\1", word)  # collapse doubled letters


def name_matches(query, full_name):
    """True if every word the caller said matches a word of the patient's name.

    An initial matches a full word ("R." matches "Rajesh"), so "Rajesh Sharma"
    matches "R. K. Sharma" too. That is deliberate: we return every possible
    candidate and let the caller's phone number narrow it down.
    """
    said = [name_key(w) for w in query.split() if name_key(w)]
    have = [name_key(w) for w in full_name.split() if name_key(w)]

    def same(a, b):
        if len(a) == 1 or len(b) == 1:
            return a[0] == b[0]
        return a == b

    return bool(said) and all(any(same(s, h) for h in have) for s in said)


def clean_phone(phone):
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    if len(digits) != 10:
        raise ToolError("invalid_phone", f"phone must have 10 digits, got {phone!r}")
    return digits


# ---------- the store ----------

class ClinicStore:
    def __init__(self, today):
        data = copy.deepcopy(CLINIC_DATA)
        self.today = date.fromisoformat(today)
        self.slot_minutes = data["clinic"]["slot_minutes"]
        self.doctors = {d["id"]: d for d in data["doctors"]}
        self.patients = {p["id"]: p for p in data["patients"]}
        self.holidays = set(data["holidays"])
        self.appointments = data["appointments"]
        self.handoffs = []
        # One lock around every read and write. A booking checks the slot and
        # takes it inside the same lock, so two racing callers cannot both win.
        self.lock = threading.Lock()

    # ----- entry point used by the agent and by POST /tools/{name} -----

    def call(self, name, arguments):
        """Validate the arguments, run the tool, never raise."""
        try:
            if name not in TOOLS:
                raise ToolError("unknown_tool", f"no tool named {name!r}; tools are {sorted(TOOLS)}")
            if not isinstance(arguments, dict):
                raise ToolError("invalid_arguments", "arguments must be a JSON object")
            required, optional = TOOLS[name]
            missing = [a for a in required if arguments.get(a) is None]
            if missing:
                raise ToolError("missing_argument", f"{name} needs: {', '.join(missing)}")
            unknown = [a for a in arguments if a not in required + optional]
            if unknown:
                raise ToolError("unknown_argument",
                                f"{name} does not take: {', '.join(unknown)}; "
                                f"it takes {', '.join(required + optional)}")
            wrong = [a for a, v in arguments.items() if v is not None and not isinstance(v, str)]
            if wrong:
                raise ToolError("invalid_type", f"these must be strings: {', '.join(wrong)}")
            with self.lock:
                return {"ok": True, **getattr(self, name)(**arguments)}
        except ToolError as error:
            return {"ok": False, "error": {"code": error.code, "message": error.message}}

    # ----- argument checks -----

    def _doctor(self, doctor_id):
        if doctor_id not in self.doctors:
            raise ToolError("unknown_doctor",
                            f"no doctor {doctor_id!r}; doctors are {sorted(self.doctors)}")
        return self.doctors[doctor_id]

    def _patient(self, patient_id):
        if patient_id not in self.patients:
            raise ToolError("unknown_patient",
                            f"no patient {patient_id!r}; find the id with lookup_patient first")
        return self.patients[patient_id]

    def _date(self, value):
        try:
            return date.fromisoformat(value)
        except ValueError:
            raise ToolError("invalid_date", f"date must be YYYY-MM-DD, got {value!r}")

    def _time(self, value):
        if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", value):
            raise ToolError("invalid_time", f"start must be HH:MM (24 hour), got {value!r}")
        return value

    def _booked(self, appointment_id, patient_id):
        """The booked appointment with this id, checked to belong to this patient."""
        self._patient(patient_id)
        for appointment in self.appointments:
            if appointment["id"] == appointment_id:
                if appointment["status"] != "booked":
                    raise ToolError("not_booked", f"{appointment_id} is already {appointment['status']}")
                if appointment["patient_id"] != patient_id:
                    raise ToolError("not_your_appointment",
                                    f"{appointment_id} does not belong to {patient_id}")
                return appointment
        raise ToolError("unknown_appointment", f"no appointment {appointment_id!r}")

    # ----- slots -----

    def _free_slots(self, doctor, day):
        """Returns (free start times, reason). reason says why the list is empty."""
        if day < self.today:
            return [], "date_in_past"
        if day.isoformat() in self.holidays:
            return [], "clinic_holiday"
        if day.isoformat() in doctor["leave_dates"]:
            return [], "doctor_on_leave"
        windows = [w for w in doctor["windows"] if w["day"] == WEEKDAYS[day.weekday()]]
        if not windows:
            return [], "doctor_not_working"
        # A set, so overlapping windows (Dr. Rao's Monday) do not produce a slot twice.
        starts = set()
        for window in windows:
            minute = to_minutes(window["start"])
            while minute + self.slot_minutes <= to_minutes(window["end"]):
                starts.add(to_hhmm(minute))
                minute += self.slot_minutes
        taken = {a["start"] for a in self.appointments
                 if a["status"] == "booked" and a["doctor_id"] == doctor["id"]
                 and a["date"] == day.isoformat()}
        free = sorted(starts - taken)
        return free, (None if free else "fully_booked")

    def _require_free(self, doctor, day, start):
        free, reason = self._free_slots(doctor, day)
        if start not in free:
            raise ToolError("slot_not_available",
                            f"{start} on {day} is not a free slot for {doctor['id']}"
                            f" ({reason or 'already booked or outside working hours'});"
                            " call search_slots to see what is free")

    # ----- the six tools -----

    def search_slots(self, doctor_id, date):
        doctor, day = self._doctor(doctor_id), self._date(date)
        free, reason = self._free_slots(doctor, day)
        return {"doctor_id": doctor_id, "date": date, "slots": free, "reason": reason}

    def book_appointment(self, patient_id, doctor_id, date, start):
        self._patient(patient_id)
        doctor, day, start = self._doctor(doctor_id), self._date(date), self._time(start)
        self._require_free(doctor, day, start)
        number = max(int(a["id"][3:]) for a in self.appointments) + 1
        appointment = {
            "id": f"ap_{number:04d}", "patient_id": patient_id, "doctor_id": doctor_id,
            "date": date, "start": start,
            "end": to_hhmm(to_minutes(start) + self.slot_minutes), "status": "booked",
        }
        self.appointments.append(appointment)
        return {"appointment": dict(appointment)}

    def reschedule_appointment(self, appointment_id, patient_id, date, start):
        appointment = self._booked(appointment_id, patient_id)
        day, start = self._date(date), self._time(start)
        # Validate everything first, change afterwards: a failed reschedule
        # leaves the old appointment exactly as it was.
        self._require_free(self.doctors[appointment["doctor_id"]], day, start)
        appointment.update(date=date, start=start,
                           end=to_hhmm(to_minutes(start) + self.slot_minutes))
        return {"appointment": dict(appointment)}

    def cancel_appointment(self, appointment_id, patient_id):
        appointment = self._booked(appointment_id, patient_id)
        appointment["status"] = "cancelled"
        return {"appointment": dict(appointment)}

    def lookup_patient(self, name=None, phone=None, patient_id=None):
        """Returns every patient that fits. Never picks one."""
        if not (name or phone or patient_id):
            raise ToolError("missing_argument", "lookup_patient needs a name, a phone or a patient_id")
        if phone:
            phone = clean_phone(phone)
        found = []
        for patient in self.patients.values():
            if patient_id and patient["id"] != patient_id:
                continue
            if phone and patient["phone"] != phone:
                continue
            if name and not name_matches(name, patient["name"]):
                continue
            found.append({
                **patient,
                "appointments": [dict(a) for a in self.appointments
                                 if a["patient_id"] == patient["id"] and a["status"] == "booked"],
            })
        return {"candidates": found, "count": len(found)}

    def escalate_to_human(self, reason, detail):
        if reason not in ESCALATION_REASONS:
            raise ToolError("invalid_reason", f"reason must be one of {list(ESCALATION_REASONS)}")
        self.handoffs.append({"reason": reason, "detail": detail})
        return {"status": "handed_off", "reason": reason}
