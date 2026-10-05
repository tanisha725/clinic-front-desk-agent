"""The HTTP surface: the graded contract, bad requests, and the UI routes."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
FIELDS = {"conversation_id", "tool_calls", "terminal_state", "escalation_reason",
          "patient_id", "appointment_id", "reply", "metrics"}


def post(conversation_id, turns):
    return client.post("/agent/run", json={"conversation_id": conversation_id,
                                           "today": "2026-10-01", "turns": turns})


def test_response_has_exactly_the_contract_fields():
    body = post("cv_x", ["Dr. Rao ke paas parso gyarah baje aa sakta hoon?", "Tarun Bisht, 9812200663."]).json()
    assert set(body) == FIELDS
    assert body["conversation_id"] == "cv_x" and body["terminal_state"] == "booked"
    assert set(body["metrics"]) == {"turns", "tokens", "latency_ms"}


def test_bad_requests_get_a_422_that_names_the_field():
    bad_date = client.post("/agent/run", json={"conversation_id": "x", "today": "tomorrow", "turns": []})
    assert bad_date.status_code == 422 and "today" in str(bad_date.json())
    no_turns = client.post("/agent/run", json={"conversation_id": "x", "today": "2026-10-01"})
    assert no_turns.status_code == 422 and "turns" in str(no_turns.json())


def test_empty_conversation_is_abandoned():
    assert post("empty", []).json()["terminal_state"] == "abandoned"


def test_tool_endpoint_returns_422_with_the_tool_error():
    response = client.post("/tools/book_appointment", json={"arguments": {
        "patient_id": "pt_0027", "doctor_id": "dr_rao", "date": "2026-10-08", "start": "09:00"}})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "slot_not_available"


def test_escalation_appears_in_the_queue_until_resolved():
    post("cv_chest", ["Seene mein dard ho raha hai."])
    queue = client.get("/api/handoffs").json()
    mine = [h for h in queue["handoffs"] if h["conversation_id"] == "cv_chest"]
    assert mine and mine[0]["reason"] == "clinical_urgent" and queue["urgent_unresolved"] >= 1

    detail = client.get("/api/conversations/cv_chest").json()
    assert [e["role"] for e in detail["transcript"]] == ["caller", "tool", "agent"]

    after = client.post("/api/handoffs/cv_chest/resolve").json()
    assert all(h["conversation_id"] != "cv_chest" for h in after["handoffs"])
    assert client.post("/api/handoffs/nope/resolve").status_code == 404
