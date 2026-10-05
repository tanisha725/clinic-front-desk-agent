"""Turn the caller's words into a small, validated dict per turn.

Two readers produce the same raw shape:
  llm.py    the model (used when LLM_API_KEY is set)
  rules.py  regular expressions (used when there is no key, or the model fails)

Whatever they return goes through clean(), which trusts nothing: unknown values
are dropped, names must literally appear in what the caller said, the phone
number is always read by regex, and dates are computed here in Python from
`today`, never by the model and never from the system clock.
"""

import re
from datetime import date, timedelta

from . import llm, rules

INTENTS = ("book", "reschedule", "cancel")
PARTS_OF_DAY = ("morning", "afternoon", "evening")
FLAGS = ("emergency", "medical_advice", "injection", "out_of_scope", "withdraw")
WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def understand(turns, today, doctors):
    """Returns (one clean dict per turn, tokens used, 'llm' or 'rules')."""
    raw, tokens, source = None, 0, "rules"
    if llm.enabled():
        try:
            raw, tokens = llm.read_turns(turns, today, doctors)
            source = "llm"
        except Exception as error:  # network error, bad JSON, wrong shape: fall back
            print(f"LLM failed, using rules instead: {error}")
    if raw is None:
        raw = [rules.read_turn(text, doctors) for text in turns]
    return [clean(r, text, today, doctors) for r, text in zip(raw, turns)], tokens, source


def resolve_date(ref, today):
    """{'relative': 1} / {'day': 8, 'month': 10} / {'weekday': 'sat'} -> 'YYYY-MM-DD' or None."""
    if not isinstance(ref, dict):
        return None
    start = date.fromisoformat(today)
    relative, day, month, weekday = (ref.get(k) for k in ("relative", "day", "month", "weekday"))
    try:
        if isinstance(relative, int) and 0 <= relative <= 30:
            return (start + timedelta(days=relative)).isoformat()
        if isinstance(day, int):  # an explicit day number wins over a weekday name
            if isinstance(month, int):
                found = date(start.year, month, day)
                if found < start:
                    found = date(start.year + 1, month, day)
            else:
                found = start.replace(day=day)
                if found < start:  # "3 tareekh" said on the 20th means next month
                    year, next_month = (start.year + 1, 1) if start.month == 12 else (start.year, start.month + 1)
                    found = date(year, next_month, day)
            return found.isoformat()
        if weekday in WEEKDAYS:  # the next such day, strictly after today
            ahead = (WEEKDAYS.index(weekday) - start.weekday() - 1) % 7 + 1
            return (start + timedelta(days=ahead)).isoformat()
    except (ValueError, TypeError):
        pass  # e.g. 31 November
    return None


def _grounded_name(value, text):
    """Keep a name only if every word of it appears in the caller's turn."""
    if not isinstance(value, str):
        return None
    words = re.findall(r"[A-Za-z]+", value)
    if words and all(w.lower() in text.lower() for w in words):
        return " ".join(words)
    return None


def clean(raw, text, today, doctors):
    """Validate one raw turn reading. Anything unexpected becomes None/empty."""
    if not isinstance(raw, dict):
        raw = {}
    dates = []
    for ref in raw.get("dates") if isinstance(raw.get("dates"), list) else []:
        resolved = resolve_date(ref, today)
        if resolved and resolved not in dates:
            dates.append(resolved)
    time = raw.get("time")
    if not (isinstance(time, str) and re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", time)):
        time = None
    phone = re.search(r"(?<!\d)\d{10}(?!\d)", re.sub(r"(?<=\d)[ -](?=\d)", "", text))
    return {
        "intent": raw.get("intent") if raw.get("intent") in INTENTS else None,
        "doctor_id": raw.get("doctor_id") if raw.get("doctor_id") in doctors else None,
        "dates": dates,
        "time": time,
        "part_of_day": raw.get("part_of_day") if raw.get("part_of_day") in PARTS_OF_DAY else None,
        "caller_name": _grounded_name(raw.get("caller_name"), text),
        "patient_name": _grounded_name(raw.get("patient_name"), text),
        "phone": phone.group() if phone else None,
        "on_behalf": raw.get("on_behalf") is True,
        "flag": raw.get("flag") if raw.get("flag") in FLAGS else None,
    }
