"""In-memory log of finished conversations and the handoff queue, for the UI.

This is display data only. The clinic itself (slots, patients, appointments)
lives in tools.ClinicStore and is rebuilt for every conversation.
"""

import threading
from datetime import datetime
from zoneinfo import ZoneInfo

CLINIC_TIME = ZoneInfo("Asia/Kolkata")

_lock = threading.Lock()
conversations = {}  # conversation_id -> record of the latest run
handoffs = {}       # conversation_id -> handoff (one per escalated conversation)


def fingerprint(result):
    """Same string the runner compares across repeated runs."""
    names = sorted({call["name"] for call in result["tool_calls"]})
    return f"{result['terminal_state']}/{result['escalation_reason']}/{','.join(names)}"


def save(conversation_id, today, turns, result, extra):
    # Wall-clock time is used only to label the log entry, never for scheduling.
    now = datetime.now(CLINIC_TIME)
    with _lock:
        earlier = conversations.get(conversation_id, {}).get("fingerprints", [])
        conversations[conversation_id] = {
            "conversation_id": conversation_id,
            "today": today,
            "turns": turns,
            "result": result,
            "transcript": extra["transcript"],
            "reader": extra["reader"],
            "logged_at": now.strftime("%d %b %Y, %H:%M"),
            "fingerprints": earlier + [fingerprint(result)],
        }
        if result["terminal_state"] == "escalated":
            previous = handoffs.get(conversation_id, {})
            handoffs[conversation_id] = {
                "conversation_id": conversation_id,
                "caller_said": extra["detail"],
                "reason": result["escalation_reason"],
                "time": now.strftime("%H:%M"),
                "status": previous.get("status", "open"),  # a re-run does not reopen it
            }
        else:
            handoffs.pop(conversation_id, None)


def resolve(conversation_id):
    with _lock:
        if conversation_id not in handoffs:
            return False
        handoffs[conversation_id]["status"] = "resolved"
        return True


def queue():
    """Counters and open handoffs for the Handoff Queue screen."""
    with _lock:
        total = len(conversations)
        escalated = len(handoffs)
        still_open = [h for h in handoffs.values() if h["status"] == "open"]
        still_open.sort(key=lambda h: (h["reason"] != "clinical_urgent", h["conversation_id"]))
        return {
            "conversations": total,
            "completed_by_agent": total - escalated,
            "escalated": escalated,
            "open": len(still_open),
            "urgent_unresolved": sum(h["reason"] == "clinical_urgent" for h in still_open),
            "handoffs": still_open,
        }


def summaries():
    with _lock:
        return [{"conversation_id": c["conversation_id"],
                 "terminal_state": c["result"]["terminal_state"],
                 "escalation_reason": c["result"]["escalation_reason"]}
                for c in sorted(conversations.values(), key=lambda c: c["conversation_id"])]


def get(conversation_id):
    with _lock:
        return conversations.get(conversation_id)
