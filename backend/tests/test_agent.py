"""Whole conversations through the agent, including the ones that must NOT be completed."""

import pytest

from app import agent, llm, understand
from app.tools import CLINIC_DATA
from conftest import load_scripts

TODAY = "2026-10-01"


def run(turns, today=TODAY):
    result, _ = agent.run_conversation("test", today, turns)
    return result


def called(result):
    return [call["name"] for call in result["tool_calls"]]


@pytest.mark.parametrize("script", load_scripts(), ids=lambda s: s["id"])
def test_script_meets_its_expected_block(script):
    result = run(script["turns"], script["today"])
    expected = script["expected"]
    assert result["terminal_state"] == expected["terminal_state"]
    assert result["escalation_reason"] == expected["escalation_reason"]
    for name in expected["must_call"]:
        assert name in called(result)
    for name in expected["must_not_call"]:
        assert name not in called(result)


def test_the_hard_rule_emergency_stops_a_complete_booking():
    result = run(["Dr. Rao ke saath Saturday subah 10 baje. Tarun Bisht, 9812200663.",
                  "Abhi seene mein dard ho raha hai."])
    assert result["terminal_state"] == "escalated"
    assert result["escalation_reason"] == "clinical_urgent"
    assert "book_appointment" not in called(result)
    assert result["appointment_id"] is None


def test_correction_inside_one_turn_books_the_corrected_date():
    result = run(["Dr. Rao ke saath appointment karwana hai.",
                  "Mangalwar 6 tareekh ko... nahi nahi, budhwar kar dijiye, 7 tareekh.",
                  "Neha Bhatt, 9812200404. Subah ka time theek rahega."])
    booking = result["tool_calls"][-1]
    assert booking["name"] == "book_appointment" and booking["arguments"]["date"] == "2026-10-07"


def test_guardian_booking_belongs_to_the_child():
    result = run(["Dr. Sethi ke saath somwar 5 tareekh ko Kabir ko dikhana hai.",
                  "Accha, toh 8 tareekh ko subah?",
                  "Meera Joshi bol rahi hoon, 9812200197. Kabir mera beta hai."])
    assert result["patient_id"] == "pt_0031"
    assert result["tool_calls"][-1]["arguments"]["date"] == "2026-10-08"


def test_dates_follow_the_today_field_not_the_clock():
    turns = ["Dr. Rao ke paas kal subah aa sakta hoon?", "Tarun Bisht, 9812200663."]
    assert run(turns, "2026-10-07")["tool_calls"][-1]["arguments"]["date"] == "2026-10-08"
    assert run(turns, "2026-10-12")["tool_calls"][-1]["arguments"]["date"] == "2026-10-13"


def test_state_resets_between_conversations():
    turns = ["Dr. Rao ke paas parso gyarah baje aa sakta hoon?", "Tarun Bisht, 9812200663."]
    first, second = run(turns), run(turns)
    assert first["appointment_id"] == second["appointment_id"] == "ap_0026"
    assert len(CLINIC_DATA["appointments"]) == 25  # the shipped data was never touched


def test_same_conversation_gives_same_fingerprint():
    for script in load_scripts():
        prints = {(r["terminal_state"], r["escalation_reason"], tuple(sorted(set(called(r)))))
                  for r in (run(script["turns"], script["today"]) for _ in range(3))}
        assert len(prints) == 1, script["id"]


# ---------- a model that misbehaves ----------

def use_fake_model(monkeypatch, reply):
    def fake(turns, today, doctors):
        if isinstance(reply, Exception):
            raise reply
        return reply, 123
    monkeypatch.setattr(llm, "enabled", lambda: True)
    monkeypatch.setattr(llm, "read_turns", fake)


BOOKING = ["Dr. Rao ke saath Saturday subah 10 baje.", "Tarun Bisht, 9812200663."]


def test_model_failure_falls_back_to_rules(monkeypatch):
    use_fake_model(monkeypatch, ValueError("not JSON"))
    assert run(BOOKING)["terminal_state"] == "booked"


def test_bad_json_and_wrong_shape_are_rejected():
    for content in ("sure! here you go", "[1, 2]", '{"turns": "none"}', '{"turns": [{}]}'):
        with pytest.raises(ValueError):
            llm.parse_reply(content, turn_count=2)


def test_garbage_fields_are_dropped_not_trusted(monkeypatch):
    use_fake_model(monkeypatch, [None, {"intent": "delete_everything", "doctor_id": "dr_who",
                                        "time": "25:99", "dates": "tomorrow", "flag": 7}])
    result = run(BOOKING)
    assert result["terminal_state"] == "abandoned"
    assert called(result) == ["lookup_patient"]  # the phone is read by regex, nothing else survived


def test_model_cannot_invent_a_patient_or_a_phone(monkeypatch):
    invented = {"intent": "cancel", "caller_name": "Priya Nair", "phone": "9812200104",
                "dates": [{"relative": 0}]}
    use_fake_model(monkeypatch, [invented])
    result = run(["Mujhe aaj ka appointment cancel karna hai."])
    assert "cancel_appointment" not in called(result) and result["patient_id"] is None


def test_model_cannot_switch_off_the_emergency_rule(monkeypatch):
    use_fake_model(monkeypatch, [{"intent": "book", "flag": None}] * 2)
    result = run(["Dr. Rao ke saath kal appointment.", "Saans nahi aa rahi hai."])
    assert result["escalation_reason"] == "clinical_urgent"


def test_changing_the_requested_time_mid_booking_is_not_a_reschedule(monkeypatch):
    # A real model read "9:30 kar dijiye" as a reschedule. The policy must still book.
    use_fake_model(monkeypatch, [
        {"intent": "book", "doctor_id": "dr_rao", "dates": [{"day": 8}], "time": "09:00"},
        {"intent": "reschedule", "time": "09:30"},
        {"caller_name": "Shalini Uniyal"},
    ])
    result = run(["8 tareekh subah 9 baje Dr. Rao ke saath.", "Accha, toh 9:30 kar dijiye.",
                  "Shalini Uniyal, 9812200694."])
    assert result["terminal_state"] == "booked"
    assert result["tool_calls"][-1]["arguments"]["start"] == "09:30"


def test_weekday_and_day_number_resolution():
    resolve = understand.resolve_date
    assert resolve({"relative": 2}, TODAY) == "2026-10-03"
    assert resolve({"weekday": "sat"}, TODAY) == "2026-10-03"
    assert resolve({"weekday": "thu"}, TODAY) == "2026-10-08"   # "Thursday" said on a Thursday
    assert resolve({"day": 8}, TODAY) == "2026-10-08"
    assert resolve({"day": 3}, "2026-10-20") == "2026-11-03"
    assert resolve({"day": 31, "month": 11}, TODAY) is None
