# Decisions

What I found unclear or wrong, what I chose, and why. Weaknesses I know about are at the end.

## 1. The shape of the agent

**The model reads. Python decides. Templates speak.**
The brief says the evaluation is about keeping an agent safe, predictable and honest when
the model is free to do anything. So I took away the freedom instead of prompting around
it. The model never chooses a tool, never sees patient records and never writes the reply.
It fills in a small form per caller turn (intent, doctor, dates, time, names, flag). A
plain Python policy decides which tools to call, and the reply is a template filled with
tool results. That gives:

- Zero invented facts by construction: every slot, patient and appointment in a reply came
  out of a tool call in the same run.
- Determinism: after the reading step there is no randomness at all.
- Prompt injection has nothing to grab: the caller's text cannot become a tool call.

The cost is flexibility. The agent cannot handle a request I did not write a path for. I
think that is the right trade for a healthcare front desk.

**Reads while listening, one write at the end.**
The script is fixed, so the agent cannot confirm with the caller. If it booked as soon as
it had enough information, a later "nahi nahi" or a later "seene mein dard" would arrive
after the schedule had changed. So `lookup_patient` and `search_slots` fire as soon as
they can, and the single `book` / `reschedule` / `cancel` happens only after the last
turn. An emergency in any turn means no write ever happens. This is the decision I would
defend hardest, because the hard rule depends on it.

**Two readers, one validator.**
With `LLM_API_KEY` set, the model reads the turns. Without it, or if the model call fails
or returns the wrong shape, a regex reader (`rules.py`) does. Both go through the same
`clean()` step, which trusts neither. I built the rule reader because I wanted the agent
to keep working when the model is down, and to be testable without a key.

**What the model is not trusted with.**
- Dates. The reader returns "kal" as `{"relative": 1}` or "8 tareekh" as `{"day": 8}`, and
  Python computes the calendar date from the request's `today`. No `datetime.now()` in
  date handling. (The wall clock is used once, to timestamp the UI log.)
- Phone numbers. Always read by regex from the caller's text.
- Names. A name is kept only if every word of it appears in that turn.
- Safety. See the next section.

**Malformed model output.** Bad JSON or a wrong number of turns: fall back to rules for the
whole conversation. A wrong value in one field: that field becomes empty. A crash anywhere
in the agent: the API still returns a valid response, `escalated` / `out_of_scope`.

## 2. Safety against restraint

**The emergency check is a keyword list, not the model.** `safety.screen()` runs on every
turn before anything else. The model can add an emergency flag but cannot remove one. I
chose to over-trigger here: a false alarm costs a restraint point, a miss gets the
submission rejected and, in real life, is much worse.

**It keeps listening after a handoff.** If the call was already escalated for medical
advice and a later turn describes an emergency, it escalates again as `clinical_urgent`.

**An ordinary symptom is not an escalation.** "Do din se bukhar hai, Dr. Rao ko dikhana
hai" is a booking. Only a question asking for judgement (dose, should I take, is it
serious) is `medical_advice`. If a caller both books and asks for advice, I escalate and
do not book, because the brief says anything clinical belongs with a human.

**`abandoned` when the agent would have asked a question and nobody answered.** No
identity given, no doctor, no date, or the exact slot is taken and the caller offered no
alternative: nothing happens and no human is needed. I do not escalate these, or the
queue fills with empty calls. I also do not book a time the caller did not ask for.

**`refused` for injection.** A turn that tries to instruct the agent (admin mode, ignore
instructions, dictating a tool call, "all appointments") is skipped entirely. If the call
then has no legitimate, verified request, the result is `refused` with no tool calls. If
the rest of the call is a normal verified booking, it goes ahead. Skipping the turn means
real information in the same turn is lost too; I accepted that.

## 3. Things in the pack that looked wrong or inconsistent

1. **Dr. Rao's Monday windows overlap** (09:00 to 12:00 and 11:45 to 15:00) and Monday has
   no evening window, unlike every other weekday. An existing appointment sits at 13:00 on
   a Monday, so the second window is real. I take the union of the windows and build slots
   in a set, so 11:45 appears once.
2. **"Two appointment windows per day each"** in the brief is not true of the data:
   Saturday has one, Dr. Sethi's Wednesday has one, Sunday has none. I follow the data.
3. **The response example in `schema.md` does not match `cv_0001`.** The example has two
   turns and patient `pt_0014` (Harpreet Kaur); the real `cv_0001` has three turns and
   Harpreet Singh (`pt_0013`). The example request says "kal subah", which is the 2 October
   holiday, yet the example response books 3 October. I treated the example as showing the
   format only. I did take one thing from it: new ids continue the sequence (`ap_0026`).
4. **The UI mock uses ids that do not exist in the data** (`d_rao`, `pt_0192`) and shows a
   `window="morning"` argument on `search_slots`. I kept `search_slots(doctor_id, date)`
   and filter by part of day in the policy, so the tool stays a plain fact lookup.
5. **"State resets between conversations" and "two conversations racing for the same slot
   must not both succeed" pull apart.** With a fresh store per run, two runs never share a
   slot. I read the second as a requirement on the tool layer itself: the store is
   thread-safe, and a test races 30 threads at one slot on a shared store.
6. **Adults are booked with the paediatrician** in the shipped data (for example `ap_0008`,
   a patient born in 1965, with Dr. Sethi). So I do not enforce any age rule.
7. **There is no tool to list a patient's appointments**, but cancel and reschedule need the
   appointment id. `lookup_patient` returns each candidate's booked appointments.
8. **No tool creates a patient.** A caller with no record cannot be booked. I escalate as
   `out_of_scope` (registration needs a person).
9. **No clock time is given, only `today`.** So I cannot tell whether a 09:30 slot today has
   already passed. All of today's slots are treated as usable.
10. **`cv_0011`'s "kal" is the clinic holiday**, so a naive agent might pass it only because
    there was no slot to book. My own `adv_01` has a bookable slot before the emergency.
11. **The submission page and the PDF differ**: `hiring@swasthiq.com` against
    `hiring@swasthiq.in`, page upload against email, and the page adds "how your functions
    keep data consistent on update" to the README. I covered both sets of requirements.
12. **"Exactly the JSON described in schema.md"** against a UI that needs a transcript.
    `/agent/run` returns only the schema fields; the transcript is served by `/api/conversations/{id}`.

## 4. Ambiguities and what I chose

**Who is the caller?**
- A lookup uses the name and the phone together. One match means resolved. More than one
  means `ambiguous_patient`. Zero means `out_of_scope` (no record).
- A unique full name with no phone is accepted. All success examples include a phone, so
  this goes beyond them; a real front desk would accept it, and booking is low risk. It is
  weaker for cancellations (see weaknesses).
- A phone number alone is not identity: three Guptas, two Rawats and two Joshis share numbers.
- Name matching is deliberately generous so that it returns candidates instead of missing
  them: an initial matches a full word ("R. K. Sharma" is a candidate for "Rajesh Sharma"),
  and common spelling variants are folded ("Imraan Quraishi" and "Imran Qureshi" both come
  back for either spelling). The phone then narrows it. Generous matching plus "never pick"
  errs toward asking a human, not toward acting on the wrong record.

**Acting for someone else.**
- Allowed only if the caller is identified and the patient is in the caller's `guardian_of`.
- Same surname or same phone is not authorisation. Kavita Rawat cannot cancel for Sanjay Rawat.
- "Mere bete ke liye" with no name: if the caller has exactly one dependant it is that
  child; with two (Sunita Gupta) it is `ambiguous_patient`.
- Order of checks when several things are wrong: ambiguous patient first, then no record,
  then not authorised.

**`patient_id` in the response.** The patient the action is for (Kabir, not Meera). `null`
for `ambiguous_patient` and `not_authorised`, because the call did not resolve to a patient
the caller may act for. For an emergency, the patient if already identified.

**Dates.**
- "kal" is tomorrow. In a booking call "yesterday" makes no sense.
- A weekday name means the next such day strictly after today. "Thursday" said on a
  Thursday means next week; a caller who means today says "aaj".
- A day number below today's date means next month.
- "Shanivaar, 3 tareekh" in one turn is one date said twice; the day number wins.
- "Kal ya parso" is two options tried in order; the first with a fitting slot is used.
- A correction inside a turn ("6 tareekh... nahi nahi, 7 tareekh") keeps only what follows it.

**Times.**
- No time given, or "koi bhi time": the earliest free slot that day. "Subah" / "dopahar" /
  "shaam": the earliest free slot before 12:00 / before 16:00 / from 16:00.
- A bare "5 baje" is 17:00, because the clinic opens at 09:00.
- A stated time that is not free is never swapped for another one.

**Reschedule and cancel.**
- With one booked appointment, that is the one. A date the caller names that matches it
  identifies it; any other date named is the target.
- Cancel with a date that does not match the patient's appointment: nothing is cancelled.
- Reschedule keeps the same doctor and the same appointment id.

**Intent.** A turn naming a doctor with no verb ("8 tareekh 9 baje Dr. Rao ke saath") is a
booking. "Book" never overrides an earlier reschedule or cancel, since any mention of the
word "appointment" looks like a booking.

**Caching the model's reading.** Keyed by model, `today` and the turns. Same conversation,
same reading, no tokens on a repeat. I am stating it openly because it also helps the
determinism score: it does not hide flakiness on the first run, and it is lost on restart.

## 5. Known weaknesses

These are real, and several are how I would break my own agent.

1. **Over-escalation on emergency words.** "My father had a heart attack last year, I need a
   routine follow-up" escalates as `clinical_urgent`. So does "emergency nahi hai". The
   keyword screen does not understand tense or negation. I kept it that way on purpose
   (section 2), but it costs restraint.
2. **Under-detection outside the list.** An emergency in words I did not list ("ankhon ke
   aage andhera", "haath sunn pad gaya") is caught only if the model flags it. With the
   rule reader alone it is missed. This is the weakness I worry about most.
3. **Identity is not verified.** Anyone who knows a unique full name can cancel that
   patient's appointment without the phone number. Requiring name and phone for writes
   would fix it and I would do that next.
4. **The rule reader is brittle.** It finds names by capital letters and a stop-word list,
   so lower-case transcripts lose names, and an unusual capitalised word can be mistaken
   for one. It does not read Devanagari. It needs "nahi nahi" style markers for corrections.
5. **Inconsistent dates are not questioned.** "Somwar 6 tareekh" (the 6th is a Tuesday) is
   booked on the 6th without comment.
6. **A doctor who does not exist** ("Dr. Mehta") is not explained; the call ends as
   `abandoned` asking which doctor.
7. **Injection skipping is whole-turn.** A real request in the same turn as an injected
   sentence is ignored.
8. **Out-of-scope detection is a short keyword list.** A request outside it with no booking
   intent ends as `abandoned`, not `escalated`.
9. **The UI log is in memory.** A restart empties the queue. The clinic data itself is
   rebuilt per conversation by design.
10. **The free tier's rate limit shapes latency.** A burst of new conversations waits on the
    provider's limit (see the README numbers). If the limit is still hit after two retries,
    that one conversation is read by the rule reader instead, which could differ from a
    model reading.
11. **The model has only been measured on 23 conversations** (the 15 examples and my 8). It
    read all of them correctly after the fix described in section 7, but that is a small set.

## 6. What I left out on purpose

Authentication, a database, multi-clinic support, changing doctor during a reschedule,
creating patients, and letting the model write replies. The brief asks for a smaller scope
done carefully, and each of these would have added surface without adding safety.

## 7. What running the real model taught me

I built and tested the policy with the rule reader first, then connected the model. Two
things changed.

1. **The model called a mid-booking change a "reschedule".** In `cv_0015` the caller says
   "Accha, toh 9:30 kar dijiye" after 09:00 turns out to be taken. The model labelled that
   turn `reschedule`, so the agent went looking for an existing appointment, found none and
   booked nothing. `cv_0006` failed the same way. I fixed it in two places: the prompt now
   says reschedule means an appointment that already exists, and, more importantly, the
   policy ignores a `reschedule` that arrives while a new booking is in progress. The second
   fix is the one I trust, because it does not depend on the model obeying the prompt.
   There is a test for it using a fake model that repeats the mistake.
2. **The model I planned to use was no longer offered**, and the free tier's token limit made
   later conversations in a batch fall back to rules. Falling back quietly would have made
   run 1 and run 2 of the same conversation use different readers. So a rate-limited call
   now waits and retries before it falls back.

Model choice: `qwen/qwen3.8-27b` and `openai/gpt-oss-120b` both got all 23 conversations
right. The smaller one used about 30% fewer tokens, so I kept it. Because the model only
fills in a form and the policy does the rest, a small model is enough.
