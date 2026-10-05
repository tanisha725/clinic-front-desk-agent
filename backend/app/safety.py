"""Deterministic safety screen. Runs on every caller turn before anything else.

Plain keyword patterns, on purpose: the one hard rule of this product must not
depend on a model being in a good mood. The LLM can ADD a flag, it can never
remove one raised here.
"""

import re

# Something that needs a clinician now.
EMERGENCY = [
    # chest and heart
    r"(seene|sine|chhati|chaati|chest)\b.{0,25}\b(dard|pain|jalan|bhaari|dabav|tight)",
    r"(dard|pain)\b.{0,30}\b(seene|sine|chhati|chaati|chest)",
    r"\bchest pain\b|\bheart attack\b|dil ka daura",
    # breathing
    r"saans\b.{0,30}\b(phool|nahi|nahin|ruk|takleef|dikkat|ukhad|mushkil|problem|pareshani)",
    r"saa?n?s lene (mein|me|main)\b.{0,20}\b(problem|dikkat|takleef|pareshani|mushkil)",
    r"can'?t breathe|cannot breathe|not breathing|breathless|short(ness)? of breath"
    r"|(difficulty|trouble|hard to|problem) breath",
    # consciousness
    r"behosh|unconscious|faint|passed out|hosh nahi|collapsed|unresponsive|not responding"
    r"|jawab nahi de rah",
    # bleeding
    r"khoon\b.{0,25}\b(beh|nikal|ruk nahi|ulti|aa raha)|bleeding|vomiting blood",
    r"(ulti|khansi|cough)\b.{0,20}\b(khoon|blood)|coughing (up )?blood|(bahut|zyada) khoon",
    # stroke signs: numbness, face, speech, sudden weakness or loss of sight
    r"\bstroke\b|lakwa|paralysis|(muh|chehra) (tedha|latak)|face (is )?droop|slurred",
    r"(haath|hath|pair|chehra|sharir|arm|leg|face|hand|body)\b.{0,20}\b(sunn|numb)",
    r"\bnumb(ness)?\b.{0,20}\b(arm|leg|face|hand|side)",
    r"bol nahi pa|awaaz nahi nikal|can'?t speak|unable to speak|zubaan ladkhada",
    r"(achanak|sudden(ly)?)\b.{0,30}\b(kamzori|weakness|sir ?dard|headache|andhera|dikhna band"
    r"|blind|sunn|numb)",
    r"aankhon ke (aage|saamne) andhera",
    # seizures
    r"\bdaura\b|\bdaure\b|seizure|\bfits\b|mirgi",
    # poisoning and self-harm
    r"zeher|zehar|poison|overdose|nigal liya|swallowed|phenyl|tezaab",
    r"suicide|khudkushi|aatmahatya|kill myself|jaan dena|marna chaht|mar jana chaht",
    # severe allergic reaction
    r"anaphyla|(gala|hont|chehra|zubaan) (sooj|band)|(throat|lips?|face|tongue) (is |are )?(closing|swell)",
    # a child who is not breathing or not waking
    r"(bachcha|bachchi|baby|beta|beti|child)\b.{0,30}\b(saans nahi|uth nahi rah|hil nahi"
    r"|not (breathing|waking|moving))",
    r"neela pad|turning blue",
    # bleeding or waters breaking in pregnancy
    r"(pregnan|garbh|hamal)\w*\b.{0,40}\b(khoon|bleeding|paani)",
    # injury, and pain the caller says they cannot bear
    r"\bemergency\b|\bambulance\b|accident|head injury|sar (par|pe|mein) chot|jal gay",
    r"(bardasht|sehan) nahi|unbearable|worst (pain|headache)",
    r"सीने में दर्द|सांस|बेहोश",
]

# A request for clinical judgement: a medicine word plus a "should I" phrase,
# or one of a few standalone questions.
MEDICINE = r"(goli|dawai|dawa|tablet|medicine|dose|crocin|paracetamol|antibiotic|syrup|capsule)"
ASKING = (r"(le lu|le loo|lena chahiye|leni chahiye|kha lu|kha loo|khana chahiye|de du|de doo"
          r"|dena chahiye|band kar|badha du|kitni|kitna|kaun si|should i|can i|is it safe|safe hai)")
MEDICAL_ADVICE = [
    MEDICINE + r".{0,40}" + ASKING,
    ASKING + r".{0,40}" + MEDICINE,
    r"kitni der mein|kitne din mein|utar jana chahiye|theek ho jayega|serious hai"
    r"|is it serious|what should i do|kya karna chahiye|side effect",
]

# Instructions hidden in the caller's turn, and bulk actions no tool supports.
INJECTION = [
    r"(ignore|disregard|forget).{0,30}(instruction|rules|prompt)",
    r"(administrator|admin|developer|debug|god) mode|system prompt|jailbreak|you are now",
    r"authori[sz]ed.{0,20}test|internal test",
    r"(instruction|niyam).{0,15}bhool",
    r"(book|cancel|reschedule)_appointment|lookup_patient|search_slots|escalate_to_human",
    r"i am (the )?(clinic )?(admin|administrator|owner|developer)",
    r"\b(every|all|saare|saari|sabhi|sabke)\s+(the\s+)?(appointments?|bookings?)",
]

# Real requests that the front desk agent has no tool for.
OUT_OF_SCOPE = [
    r"\b(bill|billing|refund|payment|insurance|invoice|receipt|fees|fee|charges)\b",
    r"\b(report|lab|test result|x-?ray|certificate|prescription)\b",
    r"\b(complaint|shikayat|home visit|ghar par|naya patient|new patient|register)\b",
]


def _hit(patterns, text):
    return any(re.search(p, text) for p in patterns)


def screen(text):
    """Returns 'emergency', 'medical_advice', 'injection', 'out_of_scope' or None."""
    text = text.lower()
    if _hit(EMERGENCY, text):
        return "emergency"
    if _hit(MEDICAL_ADVICE, text):
        return "medical_advice"
    if _hit(INJECTION, text):
        return "injection"
    if _hit(OUT_OF_SCOPE, text):
        return "out_of_scope"
    return None
