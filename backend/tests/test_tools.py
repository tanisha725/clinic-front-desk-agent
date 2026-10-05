"""The tool layer on its own: slots, double booking, lookup, argument errors."""

import threading

from app.tools import ClinicStore

TODAY = "2026-10-01"


def store():
    return ClinicStore(TODAY)


def test_search_excludes_booked_slots():
    slots = store().call("search_slots", {"doctor_id": "dr_rao", "date": "2026-10-08"})["slots"]
    assert "09:00" not in slots and "16:00" not in slots and "16:15" not in slots
    assert "09:15" in slots


def test_closed_days_have_no_slots_and_say_why():
    s = store()
    assert s.call("search_slots", {"doctor_id": "dr_rao", "date": "2026-10-02"})["reason"] == "clinic_holiday"
    assert s.call("search_slots", {"doctor_id": "dr_rao", "date": "2026-10-04"})["reason"] == "doctor_not_working"
    assert s.call("search_slots", {"doctor_id": "dr_sethi", "date": "2026-10-05"})["reason"] == "doctor_on_leave"
    assert s.call("search_slots", {"doctor_id": "dr_rao", "date": "2026-09-30"})["reason"] == "date_in_past"


def test_overlapping_monday_windows_do_not_duplicate_slots():
    slots = store().call("search_slots", {"doctor_id": "dr_rao", "date": "2026-10-12"})["slots"]
    assert len(slots) == len(set(slots))
    assert slots[0] == "09:00" and slots[-1] == "14:45"  # 15:00 is the end, not a slot


def test_booking_a_taken_slot_is_refused():
    s = store()
    args = {"patient_id": "pt_0027", "doctor_id": "dr_rao", "date": "2026-10-08", "start": "09:00"}
    assert s.call("book_appointment", args)["error"]["code"] == "slot_not_available"
    args["start"] = "09:30"
    assert s.call("book_appointment", args)["appointment"]["id"] == "ap_0026"
    assert s.call("book_appointment", args)["error"]["code"] == "slot_not_available"


def test_racing_callers_cannot_both_get_the_slot():
    s = store()
    results = []

    def book(patient_id):
        results.append(s.call("book_appointment", {
            "patient_id": patient_id, "doctor_id": "dr_rao", "date": "2026-10-03", "start": "11:00"}))

    threads = [threading.Thread(target=book, args=(f"pt_{n:04d}",)) for n in range(1, 31)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sum(r["ok"] for r in results) == 1


def test_failed_reschedule_changes_nothing():
    s = store()
    result = s.call("reschedule_appointment", {
        "appointment_id": "ap_0017", "patient_id": "pt_0003", "date": "2026-10-08", "start": "16:00"})
    assert result["error"]["code"] == "slot_not_available"
    kept = next(a for a in s.appointments if a["id"] == "ap_0017")
    assert (kept["date"], kept["start"], kept["end"]) == ("2026-10-08", "16:15", "16:30")


def test_reschedule_frees_the_old_slot_and_keeps_the_id():
    s = store()
    moved = s.call("reschedule_appointment", {
        "appointment_id": "ap_0001", "patient_id": "pt_0001", "date": "2026-10-03", "start": "10:00"})
    assert moved["appointment"]["id"] == "ap_0001" and moved["appointment"]["end"] == "10:15"
    assert "09:30" in s.call("search_slots", {"doctor_id": "dr_rao", "date": "2026-10-01"})["slots"]


def test_cancel_only_by_the_owner_and_only_once():
    s = store()
    wrong = s.call("cancel_appointment", {"appointment_id": "ap_0003", "patient_id": "pt_0020"})
    assert wrong["error"]["code"] == "not_your_appointment"
    assert s.call("cancel_appointment", {"appointment_id": "ap_0003", "patient_id": "pt_0012"})["ok"]
    again = s.call("cancel_appointment", {"appointment_id": "ap_0003", "patient_id": "pt_0012"})
    assert again["error"]["code"] == "not_booked"


def test_lookup_returns_every_candidate():
    s = store()
    assert s.call("lookup_patient", {"name": "Sharma"})["count"] == 3
    assert s.call("lookup_patient", {"name": "Priya"})["count"] == 2
    assert s.call("lookup_patient", {"phone": "9812200166"})["count"] == 3
    assert s.call("lookup_patient", {"name": "Imran Qureshi"})["count"] == 2  # spelling variants
    one = s.call("lookup_patient", {"name": "Rajesh Kumar Sharma", "phone": "9812200011"})
    assert [c["id"] for c in one["candidates"]] == ["pt_0001"]
    assert s.call("lookup_patient", {"name": "Priya Nair", "phone": "9812200135"})["count"] == 0


def test_malformed_arguments_get_specific_errors():
    s = store()
    cases = [
        ("search_slots", {"doctor_id": "dr_rao"}, "missing_argument"),
        ("search_slots", {"doctor_id": "dr_who", "date": "2026-10-03"}, "unknown_doctor"),
        ("search_slots", {"doctor_id": "dr_rao", "date": "3 October"}, "invalid_date"),
        ("search_slots", {"doctor_id": "dr_rao", "date": "2026-10-03", "window": "am"}, "unknown_argument"),
        ("search_slots", {"doctor_id": "dr_rao", "date": 20261003}, "invalid_type"),
        ("book_appointment", {"patient_id": "pt_0001", "doctor_id": "dr_rao",
                              "date": "2026-10-03", "start": "9am"}, "invalid_time"),
        ("book_appointment", {"patient_id": "pt_9999", "doctor_id": "dr_rao",
                              "date": "2026-10-03", "start": "10:00"}, "unknown_patient"),
        ("cancel_appointment", {"appointment_id": "ap_9999", "patient_id": "pt_0001"}, "unknown_appointment"),
        ("lookup_patient", {}, "missing_argument"),
        ("lookup_patient", {"phone": "12345"}, "invalid_phone"),
        ("escalate_to_human", {"reason": "bored", "detail": "x"}, "invalid_reason"),
        ("cancel_all", {}, "unknown_tool"),
        ("search_slots", "dr_rao", "invalid_arguments"),
    ]
    for name, arguments, code in cases:
        result = s.call(name, arguments)
        assert result["ok"] is False and result["error"]["code"] == code, (name, arguments, result)
        assert result["error"]["message"]
