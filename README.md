# Clinic Front Desk Agent

A front desk agent for Sunrise Clinic: a Python REST API with six tools over the clinic's
schedule, and a React UI with a Handoff Queue and a Conversation Detail screen.

The idea in one line: **the model only reads what the caller said; plain Python decides
what to do, and every reply is built from what a tool returned.** The reasoning behind
each choice is in [DECISIONS.md](DECISIONS.md).

- **Live app:** <https://clinic-front-desk-agent-rhw3.onrender.com> (free hosting: the first
  load can take up to a minute, and the sample calls fill in over the next few minutes)
- **Video, breaking my own agent:** <https://www.loom.com/share/6951a5a1bfe34f119194bfc5bf4fd92b>
  (5 min 48 s. That is over the three minutes asked for; I have tried to keep it as short
  and informative as I can.)

## Run it

```bash
./run.sh
```

Needs Python 3.10+ and Node 20+ (tested on Python 3.13 and Node 24). The script creates a virtualenv, installs the backend,
builds the frontend once, and serves both on <http://localhost:8000>.

```bash
python3 runner.py --repeat 3          # replay the 15 examples, check determinism
python3 check.py                      # compare results/ with each script's `expected`
python3 runner.py --dir adversarial && python3 check.py adversarial
cd backend && .venv/bin/python -m pytest      # 69 tests
```

To use the model, put a key for any OpenAI-compatible endpoint in a `.env` file in the
project root (it is git-ignored; `run.sh` loads it):

```bash
LLM_API_KEY=...                                   # enables the model
LLM_BASE_URL=https://api.groq.com/openai/v1       # default
LLM_MODEL=qwen/qwen3.8-27b                        # default
```

With no key the agent uses its rule-based reader, so everything above also works offline.

Docker: `docker build -t frontdesk . && docker run -p 8000:8000 frontdesk`.
Frontend development with hot reload: `cd frontend && npm run dev` (proxies to :8000).

## Layout

```
backend/app/tools.py        the six tools and the store (ground truth, no LLM)
backend/app/safety.py       keyword screen: emergency, medical advice, injection, out of scope
backend/app/understand.py   validates what the reader produced; computes dates from `today`
backend/app/llm.py          the only file that calls a model
backend/app/rules.py        regex reader used without a key or when the model fails
backend/app/agent.py        the conversation policy: when to read, when to write, when to stop
backend/app/records.py      in-memory log + handoff queue for the UI
backend/app/main.py         FastAPI routes
backend/tests/              tools, whole conversations, misbehaving model, HTTP
frontend/src/               Sidebar, HandoffQueue, ConversationDetail
adversarial/                my eight cases
conversations/, runner.py, schema.md    from the starter pack, unchanged
check.py                    compares runner results with `expected`
```

## How one conversation is handled

1. A fresh `ClinicStore` is built from `clinic.json` (this is the state reset).
2. The reader (model or rules) turns each caller turn into a small form: intent, doctor,
   dates, time, names, phone, flag. `understand.clean()` drops anything invalid, keeps a
   name only if it literally appears in the turn, always reads the phone by regex, and
   computes dates in Python from the request's `today`.
3. The policy walks the turns in order. Each turn goes through `safety.screen()` first.
   An emergency calls `escalate_to_human` and stops the conversation there.
4. While the caller is talking the agent only **reads** (`lookup_patient`, `search_slots`).
5. The single **write** (`book` / `reschedule` / `cancel`) happens after the last turn,
   so a correction or an emergency in a later turn can never arrive after the schedule
   has already changed.
6. The reply is a template filled with values the tools returned.

## API contract

### `POST /agent/run` (the graded endpoint)

Request: `{"conversation_id": "cv_0001", "today": "2026-10-01", "turns": ["...", "..."]}`

Response: exactly the fields in `schema.md`: `conversation_id`, `tool_calls`,
`terminal_state`, `escalation_reason`, `patient_id`, `appointment_id`, `reply`,
`metrics` (`turns`, `tokens`, `latency_ms`).

A malformed request (missing field, `today` not `YYYY-MM-DD`) returns `422` naming the
field. If the agent itself crashes, the response is still valid: `escalated` /
`out_of_scope` with one `escalate_to_human` call, and nothing changed.

### The six tools

All arguments are strings. Every tool returns `{"ok": true, ...}` or
`{"ok": false, "error": {"code": "...", "message": "..."}}`.

| Tool | Arguments | Returns |
|---|---|---|
| `search_slots` | `doctor_id`, `date` | `slots` (free `HH:MM` starts) and `reason` when empty: `clinic_holiday`, `doctor_on_leave`, `doctor_not_working`, `date_in_past`, `fully_booked` |
| `book_appointment` | `patient_id`, `doctor_id`, `date`, `start` | `appointment` |
| `reschedule_appointment` | `appointment_id`, `patient_id`, `date`, `start` | `appointment` (same id, same doctor) |
| `cancel_appointment` | `appointment_id`, `patient_id` | `appointment` with `status: cancelled` |
| `lookup_patient` | any of `name`, `phone`, `patient_id` | `candidates` (each with their booked `appointments`) and `count`. Never picks one. |
| `escalate_to_human` | `reason`, `detail` | `status: handed_off` |

Error codes: `unknown_tool`, `invalid_arguments`, `missing_argument`, `unknown_argument`,
`invalid_type`, `unknown_doctor`, `unknown_patient`, `unknown_appointment`, `invalid_date`,
`invalid_time`, `invalid_phone`, `invalid_reason`, `slot_not_available`, `not_booked`,
`not_your_appointment`. There is no bulk tool of any kind.

`POST /tools/{name}` with `{"arguments": {...}}` calls one tool against a fresh copy of the
data and returns `422` with the tool's error when it refuses. It exists to try the tools by
hand; nothing it does is kept.

### UI routes

| Route | Purpose |
|---|---|
| `GET /api/handoffs` | counters and open handoffs |
| `POST /api/handoffs/{conversation_id}/resolve` | mark a handoff resolved |
| `GET /api/conversations`, `GET /api/conversations/{id}` | logged runs; the detail has the transcript with tool calls in the order they fired |
| `GET /api/samples` | the example and adversarial scripts, for the "Replay sample calls" button |
| `GET /api/health` | which reader is active |

## How the functions keep data consistent on update

- **One lock, check and write together.** `ClinicStore.call()` runs every tool inside one
  `threading.Lock`. `book_appointment` computes the free slots and appends the appointment
  inside that same lock, so two callers racing for one slot cannot both pass the check.
  `test_racing_callers_cannot_both_get_the_slot` fires 30 threads at one slot and exactly
  one wins.
- **Free slots are derived, never stored.** A slot is free if it is inside a working window
  and no `booked` appointment has it. There is no second "availability" table that could
  drift out of step with the appointments.
- **Validate everything, then change.** `reschedule_appointment` checks the appointment,
  its owner, the date, the time and the new slot before touching anything, so a failed
  reschedule leaves the old appointment exactly as it was. It updates the same record in
  place, which frees the old slot and takes the new one in one step.
- **Writes check ownership.** Cancel and reschedule take `patient_id` and refuse if the
  appointment belongs to someone else, even if the policy above made a mistake.
- **One write per conversation, at the end.** The policy never has to undo anything.
- **State per conversation.** Each run deep-copies the shipped data, so no run can see
  another's bookings and `clinic.json` is never written to.

## Model, tokens and latency

Model: **`qwen/qwen3.8-27b` on Groq** (free tier), temperature 0, one call per conversation.

Measured with `python3 runner.py --repeat 3` on the 15 examples and the 8 adversarial
cases (23 conversations, 69 runs). All 23 match their `expected` block and are
deterministic across 3 runs. `check.py` prints the averages, and every response carries
its own `metrics`.

| | Tokens per conversation | Latency per conversation |
|---|---|---|
| First run, model reader | 928 average (846 to 994) | about 1 s when not rate limited (fastest 0.8 s); 12.4 s average when all 23 run back to back |
| Repeat run of the same conversation | 0 (the first reading is remembered) | under 5 ms |
| Rule reader (no key, or model unavailable) | 0 | under 5 ms |

About the 12.4 s: the free tier allows 8,000 tokens per minute, which is roughly nine
conversations. When the limit is hit, the agent waits for the time the provider asks and
retries (up to two retries, 40 s each). On a paid tier the wait disappears. If it still
cannot reach the model, the rule reader takes that conversation and keeps it for every
repeat, so the three runs of one conversation never use different readers.

I also ran the same 23 conversations on `openai/gpt-oss-120b`: all pass, at 1,315 tokens
average. I kept the smaller model because it reads these calls equally well for fewer tokens.

## Hosting

Live: <https://clinic-front-desk-agent-rhw3.onrender.com> (Render free plan: the first
visit after a quiet spell takes up to a minute to wake). The hosted copy sets
`PRELOAD_SAMPLES=1`, which runs the example and adversarial scripts in the background at
startup so the queue is not empty; on the free model tier that takes a few minutes to
finish. It is off by default, so a local or graded run starts clean.


The Dockerfile builds the UI and serves it from the API, so one container is the whole
app. On Render: New Web Service, pick this repository, runtime Docker, and optionally set
`LLM_API_KEY`. If the frontend is hosted separately, build it with `VITE_API_URL` set to
the API's address.
