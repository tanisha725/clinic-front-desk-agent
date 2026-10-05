"""The conversation policy. Plain Python decides everything; the model only reads.

How one conversation runs:
  1. understand() turns every caller turn into a small validated dict.
  2. We walk the turns in order. Each turn is screened for safety FIRST.
  3. While the caller talks we only READ (lookup_patient, search_slots).
  4. The one WRITE (book / reschedule / cancel) happens in finish(), after the
     caller has said everything. So a correction or an emergency in the last
     turn can never arrive after we have already changed the schedule.
  5. Every reply is a template filled with values a tool returned.
"""

import time as clock
from dataclasses import dataclass, field
from datetime import date

from . import safety
from .tools import ClinicStore
from .understand import understand

EMERGENCY_REPLY = ("Yeh emergency ho sakti hai. Main baaki sab rok kar aapko abhi clinic staff se "
                   "connect kar rahi hoon. Agar takleef badh rahi hai to turant nazdeeki "
                   "emergency mein jaiye.")
ADVICE_REPLY = ("Dawai ya ilaaj ke baare mein main salah nahi de sakti. Main aapki baat clinic "
                "staff tak pahuncha rahi hoon, woh aapse sampark karenge.")
REFUSAL_REPLY = ("Main yeh request nahi kar sakti. Main sirf ek patient ka appointment book, "
                 "reschedule ya cancel kar sakti hoon, uski pehchaan ke baad.")


@dataclass
class State:
    """Everything the caller has told us so far."""
    intent: str = None            # book | reschedule | cancel
    doctor_id: str = None
    dates: list = field(default_factory=list)
    time: str = None              # HH:MM
    part_of_day: str = None       # morning | afternoon | evening
    caller_name: str = None
    phone: str = None
    subject_name: str = None      # the person the call is about, if not the caller
    on_behalf: bool = False
    caller_matches: list = None   # lookup_patient results; None = not looked up yet
    subject_matches: list = None
    saw_injection: bool = False
    out_of_scope: bool = False
    withdrawn: bool = False


@dataclass
class Outcome:
    terminal_state: str
    reply: str
    escalation_reason: str = None
    patient_id: str = None
    appointment_id: str = None
    detail: str = ""              # what the human picking up the handoff should read


class Run:
    """One conversation in progress: the store, the tool log and the transcript."""

    def __init__(self, today):
        self.store = ClinicStore(today)
        self.tool_calls = []      # exactly what schema.md asks for
        self.transcript = []      # caller / tool / agent events, in order, for the UI
        self.searches = {}        # (doctor_id, date) -> result, so we never search twice

    def say(self, role, text):
        self.transcript.append({"role": role, "text": text})

    def tool(self, tool_name, /, **arguments):
        arguments = {k: v for k, v in arguments.items() if v is not None}
        result = self.store.call(tool_name, arguments)
        self.tool_calls.append({"name": tool_name, "arguments": arguments})
        self.transcript.append({"role": "tool", "name": tool_name, "arguments": arguments, "result": result})
        return result

    def search(self, doctor_id, day):
        if (doctor_id, day) not in self.searches:
            self.searches[(doctor_id, day)] = self.tool("search_slots", doctor_id=doctor_id, date=day)
        return self.searches[(doctor_id, day)]


# ---------- wording helpers ----------

def nice_date(iso):
    day = date.fromisoformat(iso)
    return f"{day.day} {day:%B} ({day:%A})"


def abandoned(reply):
    return Outcome("abandoned", reply)


def escalated(reason, detail, reply):
    return Outcome("escalated", reply, escalation_reason=reason, detail=detail)


def only(matches):
    return matches[0] if matches and len(matches) == 1 else None


# ---------- the main loop ----------

def run_conversation(conversation_id, today, turns):
    started = clock.monotonic()
    run = Run(today)
    readings, tokens, source = understand(turns, today, run.store.doctors)
    state = State()
    outcome = None

    for index, (text, reading) in enumerate(zip(turns, readings)):
        run.say("caller", text)
        flag = safety.screen(text) or reading["flag"]

        # The hard rule. Checked on every turn, even after another handoff.
        if flag == "emergency":
            run.tool("escalate_to_human", reason="clinical_urgent", detail=text)
            run.say("agent", EMERGENCY_REPLY)
            patient = only(state.subject_matches if state.subject_name else state.caller_matches)
            outcome = Outcome("escalated", EMERGENCY_REPLY, "clinical_urgent",
                              patient_id=patient["id"] if patient else None, detail=text)
            break
        if outcome:
            continue  # already handed off; keep listening only for an emergency
        if flag == "medical_advice":
            run.tool("escalate_to_human", reason="medical_advice", detail=text)
            run.say("agent", ADVICE_REPLY)
            outcome = escalated("medical_advice", text, ADVICE_REPLY)
            continue
        if flag == "injection":
            state.saw_injection = True  # the turn is data, not instructions: skip it
            run.say("agent", REFUSAL_REPLY)
            continue

        state.out_of_scope = state.out_of_scope or flag == "out_of_scope"
        state.withdrawn = flag == "withdraw"
        merge(state, reading)
        look_up_people(run, state)
        progress = describe_progress(run, state)
        if index < len(turns) - 1:
            run.say("agent", progress)

    if outcome is None:
        outcome = finish(run, state)

    return {
        "conversation_id": conversation_id,
        "tool_calls": run.tool_calls,
        "terminal_state": outcome.terminal_state,
        "escalation_reason": outcome.escalation_reason,
        "patient_id": outcome.patient_id,
        "appointment_id": outcome.appointment_id,
        "reply": outcome.reply,
        "metrics": {"turns": len(turns), "tokens": tokens,
                    "latency_ms": int((clock.monotonic() - started) * 1000)},
    }, {"transcript": run.transcript, "detail": outcome.detail, "reader": source}


def merge(state, reading):
    """Fold one turn's reading into what we already know. Newer values win."""
    # "book" is the weakest signal (any mention of an appointment), so it never
    # overwrites a reschedule or cancel that was already stated.
    # And a "reschedule" heard in the middle of a new booking ("accha, toh 9:30 kar
    # dijiye") is the caller changing the slot they want, not moving an old appointment.
    intent = reading["intent"]
    changing_requested_slot = state.intent == "book" and intent == "reschedule"
    if intent and not (intent == "book" and state.intent) and not changing_requested_slot:
        state.intent = intent
    if reading["doctor_id"]:
        state.doctor_id = reading["doctor_id"]
    if reading["dates"]:
        state.dates = reading["dates"]
    if reading["time"]:
        state.time, state.part_of_day = reading["time"], reading["part_of_day"]
    elif reading["part_of_day"]:
        state.time, state.part_of_day = None, reading["part_of_day"]
    if reading["caller_name"] or reading["phone"]:
        state.caller_name = reading["caller_name"] or state.caller_name
        state.phone = reading["phone"] or state.phone
        state.caller_matches = None  # new information: look the caller up again
    if reading["patient_name"] and reading["patient_name"] != state.subject_name:
        state.subject_name, state.subject_matches = reading["patient_name"], None
    state.on_behalf = state.on_behalf or reading["on_behalf"]
    if not state.intent and state.doctor_id:
        state.intent = "book"  # "8 tareekh 9 baje Dr. Rao ke saath" is a booking request


def look_up_people(run, state):
    if state.caller_matches is None and (state.caller_name or state.phone):
        result = run.tool("lookup_patient", name=state.caller_name, phone=state.phone)
        state.caller_matches = result.get("candidates", [])
    if state.subject_matches is None and state.subject_name:
        result = run.tool("lookup_patient", name=state.subject_name)
        state.subject_matches = result.get("candidates", [])


# ---------- slots ----------

def part_of(start):
    return "morning" if start < "12:00" else "afternoon" if start < "16:00" else "evening"


def find_slot(run, doctor_id, dates, time, part_of_day):
    """Try each date in the order the caller gave them.

    Returns (date, start, note). start is None when nothing fits, and note then
    explains why using only what search_slots returned.
    """
    doctor = run.store.doctors[doctor_id]["name"]
    notes = []
    for day in dates:
        result = run.search(doctor_id, day)
        slots = result.get("slots", [])
        if not slots:
            reason = (result.get("reason") or "not available").replace("_", " ")
            notes.append(f"{nice_date(day)} ko {doctor} ka koi slot nahi hai ({reason}).")
            continue
        if time:
            fitting = [s for s in slots if s == time]
        elif part_of_day:
            fitting = [s for s in slots if part_of(s) == part_of_day]
        else:
            fitting = slots
        if fitting:
            return day, fitting[0], ""
        wanted = time or part_of_day
        nearby = [s for s in slots if part_of(s) == (part_of(time) if time else part_of_day)] or slots
        notes.append(f"{nice_date(day)} ko {doctor} ke paas {wanted} ka slot khali nahi hai. "
                     f"Khali slots: {', '.join(nearby[:6])}.")
    return None, None, " ".join(notes)


def describe_progress(run, state):
    """What the agent says between turns. Also fires search_slots as soon as it can."""
    parts = []
    if state.intent == "book" and state.doctor_id and state.dates:
        day, start, note = find_slot(run, state.doctor_id, state.dates, state.time, state.part_of_day)
        doctor = run.store.doctors[state.doctor_id]["name"]
        parts.append(f"{nice_date(day)} ko {start} baje {doctor} ke saath slot khali hai." if start else note)
    if state.caller_matches is None:
        parts.append("Kripya apna poora naam aur phone number batayein.")
    elif len(state.caller_matches) > 1:
        parts.append(f"Is jaankari se {len(state.caller_matches)} patient record mil rahe hain. "
                     "Kripya poora naam aur phone number batayein.")
    elif not state.caller_matches:
        parts.append("Is naam ya number se koi patient record nahi mila.")
    elif not state.intent:
        parts.append("Bataiye, appointment book, reschedule ya cancel karna hai?")
    return " ".join(parts) or "Ji, bataiye main aapki kya madad kar sakti hoon?"


# ---------- the end of the call: decide once, act once ----------

def finish(run, state):
    outcome = decide(run, state)
    # Someone tried to instruct the agent and the call did not end in a normal,
    # verified action: decline. There is nothing for a human to pick up.
    if state.saw_injection and outcome.terminal_state in ("escalated", "abandoned"):
        outcome = Outcome("refused", REFUSAL_REPLY)
    if outcome.terminal_state == "escalated":
        run.tool("escalate_to_human", reason=outcome.escalation_reason, detail=outcome.detail)
    run.say("agent", outcome.reply)
    return outcome


def decide(run, state):
    if state.withdrawn:
        return abandoned("Theek hai, koi baat nahi. Jab chahein dobara call kar lijiye.")
    if not state.intent:
        if state.out_of_scope:
            return escalated("out_of_scope", "Request the front desk agent has no tool for.",
                             "Is kaam ke liye main aapko clinic staff se connect kar rahi hoon.")
        return abandoned("Mujhe aapki request samajh nahi aayi. Appointment ke liye kripya dobara call karein.")

    patient, problem = who_is_the_patient(run, state)
    if problem:
        return problem
    if state.intent == "book":
        return book(run, state, patient)

    # reschedule or cancel: find the one appointment the caller means
    appointments = patient["appointments"]
    if not appointments:
        return abandoned(f"{patient['name']} ke naam par koi booked appointment nahi mila.")
    on_named_dates = [a for a in appointments if a["date"] in state.dates]
    if state.intent == "cancel" and state.dates and not on_named_dates:
        return abandoned(f"{patient['name']} ka appointment {nice_date(appointments[0]['date'])} ko hai, "
                         "aapne jo din bataya us din nahi. Kuch cancel nahi kiya gaya.")
    chosen = on_named_dates or appointments
    if len(chosen) > 1:
        return abandoned(f"{patient['name']} ke {len(chosen)} appointments hain. Kripya batayein kaun sa.")
    if state.intent == "cancel":
        return cancel(run, patient, chosen[0])
    return reschedule(run, state, patient, chosen[0])


def who_is_the_patient(run, state):
    """Returns (patient, None) or (None, Outcome explaining why we cannot act)."""
    caller = only(state.caller_matches)
    ask_identity = abandoned("Appointment ke liye mujhe patient ka poora naam aur phone number chahiye. "
                             "Kripya dobara call karein.")
    no_record = escalated("out_of_scope", "No patient record matches what the caller gave.",
                          "Is naam ya number se koi patient record nahi mila. "
                          "Main aapko clinic staff se connect kar rahi hoon.")

    def ambiguous(matches):
        names = ", ".join(m["name"] for m in matches)
        return escalated("ambiguous_patient", f"{len(matches)} patients match: {names}",
                         f"Is jaankari se {len(matches)} patient record mil rahe hain, isliye main "
                         "andaza nahi lagaungi. Main aapko clinic staff se connect kar rahi hoon.")

    # 1. The caller is the patient.
    if not (state.subject_name or state.on_behalf):
        if state.caller_matches is None:
            return None, ask_identity
        if not state.caller_matches:
            return None, no_record
        if len(state.caller_matches) > 1:
            return None, ambiguous(state.caller_matches)
        return caller, None

    # 2. The caller is acting for someone else.
    if state.subject_name:
        matches = state.subject_matches
    elif caller:  # "mere bete ke liye", no name given: the caller's listed dependants
        matches = [run.tool("lookup_patient", patient_id=ward)["candidates"][0]
                   for ward in caller["guardian_of"]]
    else:
        return None, ask_identity

    if caller:
        allowed = [m for m in matches if m["id"] == caller["id"] or m["id"] in caller["guardian_of"]]
        if len(allowed) == 1:
            return allowed[0], None
        if len(allowed) > 1:
            return None, ambiguous(allowed)
    elif len(matches) > 1:
        return None, ambiguous(matches)
    elif state.caller_matches and len(state.caller_matches) > 1:
        return None, ambiguous(state.caller_matches)
    if state.subject_name and not matches:
        return None, no_record
    who = caller["name"] if caller else "An unidentified caller"
    target = matches[0]["name"] if matches else "another person"
    return None, escalated("not_authorised", f"{who} asked to {state.intent} for {target}",
                           "Aap is patient ke record par listed guardian nahi hain, isliye main yeh "
                           "nahi kar sakti. Main aapko clinic staff se connect kar rahi hoon.")


def book(run, state, patient):
    if not state.doctor_id:
        doctors = " ya ".join(d["name"] for d in run.store.doctors.values())
        return abandoned(f"Aapne doctor nahi bataya ({doctors}). Koi appointment book nahi hua.")
    if not state.dates:
        return abandoned("Aapne din nahi bataya. Koi appointment book nahi hua.")
    day, start, note = find_slot(run, state.doctor_id, state.dates, state.time, state.part_of_day)
    if not start:
        return abandoned(f"{note} Koi appointment book nahi hua.")
    result = run.tool("book_appointment", patient_id=patient["id"], doctor_id=state.doctor_id,
                      date=day, start=start)
    if not result["ok"]:
        return abandoned(f"Booking nahi ho payi: {result['error']['message']}")
    booked = result["appointment"]
    doctor = run.store.doctors[booked["doctor_id"]]["name"]
    return Outcome("booked", f"Ji, {patient['name']} ka appointment {nice_date(booked['date'])} ko "
                             f"{booked['start']} baje {doctor} ke saath book ho gaya hai.",
                   patient_id=patient["id"], appointment_id=booked["id"])


def cancel(run, patient, appointment):
    result = run.tool("cancel_appointment", appointment_id=appointment["id"], patient_id=patient["id"])
    if not result["ok"]:
        return abandoned(f"Cancel nahi ho paya: {result['error']['message']}")
    return Outcome("cancelled", f"Ji, {patient['name']} ka {nice_date(appointment['date'])} "
                                f"{appointment['start']} baje ka appointment cancel ho gaya hai.",
                   patient_id=patient["id"], appointment_id=appointment["id"])


def reschedule(run, state, patient, appointment):
    # Any date the caller named that is not the current one is where they want to move to.
    targets = [d for d in state.dates if d != appointment["date"]]
    if not targets and not (state.time or state.part_of_day):
        return abandoned("Aapne naya din ya time nahi bataya. Appointment waise hi hai.")
    day, start, note = find_slot(run, appointment["doctor_id"], targets or [appointment["date"]],
                                 state.time, state.part_of_day)
    if not start:
        return abandoned(f"{note} Appointment waise hi hai.")
    result = run.tool("reschedule_appointment", appointment_id=appointment["id"],
                      patient_id=patient["id"], date=day, start=start)
    if not result["ok"]:
        return abandoned(f"Reschedule nahi ho paya: {result['error']['message']}")
    moved = result["appointment"]
    doctor = run.store.doctors[moved["doctor_id"]]["name"]
    return Outcome("rescheduled", f"Ji, {patient['name']} ka appointment ab {nice_date(moved['date'])} ko "
                                  f"{moved['start']} baje {doctor} ke saath hai.",
                   patient_id=patient["id"], appointment_id=moved["id"])


def failed_safely(conversation_id, today, turns):
    """Used by the API if run_conversation itself crashes: hand the call to a human."""
    run = Run(today)
    for text in turns:
        run.say("caller", text)
    reply = "Maaf kijiye, system mein dikkat aa gayi hai. Main aapko clinic staff se connect kar rahi hoon."
    run.tool("escalate_to_human", reason="out_of_scope", detail="Agent error; nothing was changed.")
    run.say("agent", reply)
    return {
        "conversation_id": conversation_id, "tool_calls": run.tool_calls,
        "terminal_state": "escalated", "escalation_reason": "out_of_scope",
        "patient_id": None, "appointment_id": None, "reply": reply,
        "metrics": {"turns": len(turns), "tokens": 0, "latency_ms": 0},
    }, {"transcript": run.transcript, "detail": "Agent error; nothing was changed.", "reader": "none"}
