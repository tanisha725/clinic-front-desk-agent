"""Rule-based reader: regular expressions for Hinglish front desk calls.

Used when no LLM key is configured, or when the model fails. It returns the
same raw shape as llm.py, and understand.clean() validates both the same way.
It is deliberately simple; DECISIONS.md lists what it cannot read.
"""

import re

RELATIVE_DAYS = {"aaj": 0, "today": 0, "kal": 1, "tomorrow": 1, "parso": 2, "parson": 2}
WEEKDAYS = {
    "mon": r"somwar|somvar|somvaar|monday",
    "tue": r"mangalwar|mangalvar|mangalvaar|tuesday",
    "wed": r"budhwar|budhvar|budhvaar|wednesday",
    "thu": r"guruwar|guruvar|guruvaar|veervar|brihaspativar|thursday",
    "fri": r"shukrawar|shukravar|shukravaar|friday",
    "sat": r"shaniwar|shanivar|shanivaar|saturday",
    "sun": r"raviwar|ravivar|ravivaar|itwar|sunday",
}
MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
NUMBER_WORDS = {
    "ek": 1, "do": 2, "teen": 3, "char": 4, "chaar": 4, "paanch": 5, "panch": 5,
    "chhe": 6, "cheh": 6, "chhah": 6, "saat": 7, "aath": 8, "nau": 9, "das": 10,
    "gyarah": 11, "gyaarah": 11, "barah": 12, "baarah": 12,
}
PART_OF_DAY = {
    "morning": r"subah|savere|morning",
    "afternoon": r"dopahar|dopeher|afternoon",
    "evening": r"shaam|sham|evening|raat|night",
}
# "6 tareekh... nahi nahi, 7 tareekh": only what follows the correction counts.
CORRECTION = r"nahi nahi|nahin nahin|no no|actually|sorry|i mean|wait"
WITHDRAW = r"baad mein (call|phone|baat)|call back|call you back|rehne d|chhod d|never mind|phir kabhi"
RELATION = (r"bete|beti|beta|bachche|bachchi|bachcha|son|daughter|child|wife|husband|patni|pati"
            r"|pitaji|papa|father|mother|mummy|maa|bhai|behen|dost|friend")
# Capitalised words that are not names.
NOT_A_NAME = set("""
main mai mera mere meri mujhe hum hamara bas kal parso aaj subah shaam dopahar accha achha
theek haan ji nahi namaste hello hi number koi waise do ek arre toh aur kya yes no ok okay
please sir madam doctor dr the i my is this you ignore cancel book appointment clinic
sunrise crocin paracetamol october oct unka unki uska waise abhi phir kripya thank thanks
monday tuesday wednesday thursday friday saturday sunday somwar mangalwar budhwar guruwar
shukrawar shanivaar shaniwar ravivar itwar can could will would it he she we they what when
""".split())


def _after_correction(text):
    """The part after the last 'nahi nahi', if that part has anything in it."""
    parts = re.split(CORRECTION, text)
    return parts[-1] if len(parts) > 1 else text


def find_dates(text):
    """Every date mentioned, in the order spoken, as refs for understand.resolve_date."""
    found = []  # (position, ref)
    for word, days in RELATIVE_DAYS.items():
        for m in re.finditer(rf"\b{word}\b", text):
            found.append((m.start(), {"relative": days}))
    for m in re.finditer(r"\bday after tomorrow\b", text):
        found = [f for f in found if not m.start() <= f[0] < m.end()]
        found.append((m.start(), {"relative": 2}))
    for key, pattern in WEEKDAYS.items():
        for m in re.finditer(rf"\b({pattern})\b", text):
            found.append((m.start(), {"weekday": key}))
    months = "|".join(MONTHS)
    numbered = []
    for m in re.finditer(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(tareekh|tarikh|taareekh|(?:{months})[a-z]*)\b"
                         r"|\b(\d{1,2})(?:st|nd|rd|th)\b", text):
        ref = {"day": int(m.group(1) or m.group(3))}
        if m.group(2) and m.group(2)[:3] in MONTHS:
            ref["month"] = MONTHS.index(m.group(2)[:3]) + 1
        numbered.append((m.start(), ref))
    if numbered:
        # "Shanivaar, 3 tareekh" is one date said two ways: the day number wins.
        found = [f for f in found if "weekday" not in f[1]]
    found += numbered
    return [ref for _, ref in sorted(found, key=lambda f: f[0])]


def find_part_of_day(text):
    for part, pattern in PART_OF_DAY.items():
        if re.search(rf"\b({pattern})\b", text):
            return part
    return None


def find_time(text):
    """'9:30', '10 baje', 'gyarah baje', 'saadhe paanch baje', '5 pm' -> 'HH:MM' or None."""
    numbers = "|".join(NUMBER_WORDS)
    clock = re.search(r"\b(\d{1,2})[:.](\d{2})\b", text)
    spoken = re.search(rf"\b(?:(saadhe|sadhe|sava|sawa|paune)\s+)?(\d{{1,2}}|{numbers})\s*"
                       r"(baje|bje|o'?clock|am|pm)\b", text)
    if clock:
        hour, minute, marker = int(clock.group(1)), int(clock.group(2)), ""
        marker_match = re.match(r"\s*(am|pm)\b", text[clock.end():])
        marker = marker_match.group(1) if marker_match else ""
    elif spoken:
        half, number, marker = spoken.groups()
        hour = int(number) if number.isdigit() else NUMBER_WORDS[number]
        minute = 0
        if half in ("saadhe", "sadhe"):
            minute = 30
        elif half in ("sava", "sawa"):
            minute = 15
        elif half == "paune":
            hour, minute = hour - 1, 45
    else:
        return None
    part = find_part_of_day(text)
    if marker == "pm" or part == "evening" or (part == "afternoon" and hour < 11):
        hour += 12 if hour < 12 else 0
    elif marker != "am" and part is None and hour < 9:
        hour += 12  # the clinic opens at 9, so a bare "5 baje" means 17:00
    return f"{hour:02d}:{minute:02d}" if 0 <= hour <= 23 and minute <= 59 else None


def find_intent(text):
    if re.search(r"\b(cancel|radd)", text):
        return "cancel"
    if re.search(r"reschedule|postpone|prepone|shift|badal|aage badha|ki jagah"
                 r"|appointment (hai|tha|booked)", text):
        return "reschedule"
    if re.search(r"appointment|milna|dikhana|dikha |book|aa sakt|slot|checkup|time chahiye", text):
        return "book"
    return None


def find_doctor(text, doctors):
    """Match on the doctor's first name or surname, e.g. 'rao' or 'sethi'."""
    for doctor_id, doctor in doctors.items():
        names = [w.lower() for w in doctor["name"].split() if w != "Dr."]
        if any(re.search(rf"\b{n}\b", text) for n in names):
            return doctor_id
    return None


def find_names(text):
    """Returns (caller_name, patient_name) from capitalised words that are not ordinary words.

    A name followed by "ke liye / ka / ko / mera", or right after "bete / beti",
    is the person the call is ABOUT. Any other name is the caller's own.
    """
    text = re.sub(r"\b(Dr\.?|Doctor)\s+[A-Z][a-z]+", " ", text)
    has_phone = bool(re.search(r"\d{10}", text))
    runs, current = [], None  # each run: [start, end, words]
    for m in re.finditer(r"[A-Z][a-z]+|[A-Z]\.", text):
        if m.group().strip(".").lower() in NOT_A_NAME:
            current = None
        elif current and not text[current[1]:m.start()].strip():
            current[1] = m.end()
            current[2].append(m.group())
        else:
            current = [m.start(), m.end(), [m.group()]]
            runs.append(current)

    caller = patient = None
    for start, end, words in runs:
        before, after = text[:start].lower(), text[end:].lower()
        about_them = (re.match(r"\s*(ji\s+)?(ke liye|ka\b|ki\b|ko\b|mera\b|meri\b|is my\b)", after)
                      or re.search(rf"\b({RELATION}|for)\s+$", before))
        own_name_cue = (len(words) > 1 or has_phone
                        or re.search(r"\b(main|mai|naam|name is|this is|i am|bas)\s+$", before)
                        or re.match(r"\s*(bol rah|speaking|hoon|hun)\b", after))
        if about_them:
            patient = patient or " ".join(words)
        elif own_name_cue:
            caller = caller or " ".join(words)
    return caller, patient


def read_turn(text, doctors):
    lower = text.lower()
    latest = _after_correction(lower)
    caller, patient = find_names(text)
    on_behalf = bool(patient) or bool(
        re.search(rf"\b(mere|meri|mera|apne|apni|my)\s+({RELATION})\b", lower)
        or re.search(r"\b(unka|unki|unke|uska|uski)\b", lower))
    return {
        "intent": find_intent(lower),
        "doctor_id": find_doctor(latest, doctors) or find_doctor(lower, doctors),
        "dates": find_dates(latest) or find_dates(lower),
        "time": find_time(latest) or find_time(lower),
        "part_of_day": find_part_of_day(latest) or find_part_of_day(lower),
        "caller_name": caller,
        "patient_name": patient,
        "phone": None,  # understand.clean() always reads the phone itself
        "on_behalf": on_behalf,
        "flag": "withdraw" if re.search(WITHDRAW, lower) else None,
    }
