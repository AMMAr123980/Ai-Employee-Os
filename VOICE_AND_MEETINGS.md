# Voice commands, Meeting Assistant & Tasks

Three features and the plumbing they share: multi-step voice commands, meeting
transcription with action items, and a task manager that gives both of them
somewhere to put their output.

No new services. Speech-to-text and planning both go through the OpenAI key the
app already uses, the sweeps run on APScheduler alongside the existing ones, and
`httpx` is the only new Python dependency (used solely for the optional
diarization call).

---

## 1. What a voice command actually does

```
hold to talk
  → upload returns immediately (status: queued)
  → background: transcribe → plan → execute
  → internal steps have already run when you get the result
  → anything customer-facing waits for a tap
```

The planner returns a **plan**, not a single action, which is what makes the
flagship example work:

> "Draft a quotation for Acme for 25 laptops, email it to them, and remind me if
> they don't reply within three days."

becomes three ordered steps — `draft_quotation` → `email_quotation` →
`schedule_followup` — where step 2 pulls the quotation number step 1 produced
via the literal token `"$prev.quotation_number"`.

The draft/send split is deliberate and load-bearing: drafting is reversible and
internal, so it runs immediately; emailing reaches a customer, so it's held.
Fusing them would either put a confirmation tap in front of harmless work or let
the email out without one.

### Supported intents

| Group | Intents |
| --- | --- |
| Tasks | `create_task`, `complete_task`, `schedule_meeting` (→ dated task), `schedule_followup` |
| CRM | `create_customer`, `add_customer_note`, `change_pipeline_stage` |
| Quotations | `draft_quotation`, `email_quotation` |
| Invoices | `create_invoice`, `send_invoice`, `send_payment_reminder`, `record_payment`, `set_recurring_invoice` |
| Email | `send_email` |
| Questions (read-only) | `sales_report`, `outstanding_invoices`, `customer_summary`, `my_tasks`, `email_activity_summary` |
| Delegation | `ask_ai_employee` |

Adding one is four edits, and the app refuses to boot if you miss any of the
last three: a function + `VOICE_ACTION_REGISTRY` entry in `voice_actions.py`, a
`voice_intent.INTENT_CATALOG` entry, a `voice_permissions.INTENT_PERMISSIONS`
entry, and a place in `AUTO_EXECUTE` or `CONFIRM_REQUIRED`.

### The safety model

Three sets at the bottom of `voice_actions.py`:

- **`AUTO_EXECUTE`** — reads and reversible internal writes. Nothing leaves the
  company, so nothing waits.
- **`CONFIRM_REQUIRED`** — reaches a customer, moves money, or delegates. Held at
  `awaiting_confirmation` until someone taps.
- **`READ_ONLY_INTENTS`** — a subset of auto-execute that skips the confirmation
  sheet entirely. Being asked to confirm "what did we invoice last month" is the
  kind of friction that stops people using a feature.

`requires_confirmation()` defaults to `True` for anything unrecognised, and a
step with unfilled required slots is held even when its intent is normally
automatic — running a half-filled action is worse than asking.

Partial approval is supported: a plan with three held steps can be confirmed as
"these two, not that one" (`only_steps` on the confirm endpoint).

### Things that are enforced in code, not in the prompt

- **Permissions.** `owner`/`admin` get everything; `member` can do the work but
  can't email customers or touch the books. Per-company overrides live in
  `voice_role_permissions`, and an empty table is a working system. The prompt is
  scoped to what you're allowed to do *and* the executor checks again, because a
  prompt is a suggestion and an `if` is a guarantee.
- **Quotas.** `usage_metering.py` counts AI requests, transcription seconds and
  stored bytes against the plan on the company row, reserving *before* the paid
  call and releasing if it fails. Over the cap returns HTTP 402 with the numbers,
  so the UI can say "500 of 500 used" instead of "request failed". An
  unrecognised plan gets the *most* generous limits — a billing bug should page
  you, not lock a paying customer out of their own data.
- **Timezones.** The browser sends its IANA zone with the recording; the planner
  is told the current local date and time and returns local ISO with no offset;
  Python converts once. "Friday at 3 PM" in Asia/Karachi stores as 10:00 UTC and
  displays back as 15:00. Unparseable dates become "missing info", never a
  plausible-looking wrong time.
- **Language.** Whisper auto-detects, and the detected language drives both the
  confirmation sentence and the fixed error strings (`voice_i18n.py`, currently
  English, Urdu and Arabic, falling back to English for anything else).

### Context memory

A short per-user window (30 minutes, 8 commands) of what was just discussed is
injected into the planning prompt as facts, so "now email it to them" resolves.
Two guards worth knowing: context is only applied when the transcript actually
contains a referring expression ("it", "them", "the quotation"), and anything
filled from context is named in the step summary — "using the customer from your
last command" — so a wrong resolution is visible *before* it runs.

### Audio retention

Recordings are kept for `VOICE_AUDIO_RETENTION_DAYS` and streamed back through
an authenticated endpoint. This is what makes the command log an audit trail: if
someone disputes "you told it to move Acme to lost", a transcript the same AI
produced is not evidence — the recording is. Set `VOICE_AUDIO_BACKEND=none` if
your data policy says otherwise; everything downstream already handles a null
audio key.

---

## 2. Conditional follow-ups

`schedule_followup` stores a **condition plus a deadline**, not just a date:

```
"remind me if they don't reply in three days"
  → VoiceFollowup(condition_type="no_reply", due_at=+3d)
  → sweep runs at the deadline
      customer got in touch? → resolved, nobody is nagged
      still silent?          → a high-priority task appears
```

Conditions are a closed set (`no_reply`, `no_payment`, `always`) because a
free-text condition would have to be evaluated by a model at fire time, and a
model that misreads "has he paid?" produces a dunning reminder about someone who
paid last week.

Checkers answer "did the thing happen?", not "should we fire?". That framing
means a checker that throws is safely treated as *not resolved* — the worst case
is a reminder you didn't need, instead of a chase that silently never happens.

The sweep never emails a customer. Firing a message at a customer days later from
an unattended job, with nobody looking, is exactly what the confirmation gate
exists to prevent, so it creates a task and a human sends.

---

## 3. Meeting Assistant

```
POST /api/meetings  (audio file)
  → queued → transcribing → summarizing → completed
```

Long recordings are chunked past Whisper's 25 MB limit, with a small backwards
overlap at each seam and word-level de-duplication where the chunks meet. It's
approximate at the margins — a word may repeat rather than a sentence vanishing.
If you add ffmpeg later, replace `_chunks()` with a real time-based split and
delete `_drop_overlap`; nothing else changes.

**Speaker identification, honestly.** Whisper returns no diarization, so
`speaker_method` records where the labels came from:

- `provided` — a person named them in the UI. Accurate.
- `diarized` — an external service (`DIARIZATION_URL`). Any endpoint taking an
  audio file and returning `{"segments": [{start, end, speaker}]}` works.
- `heuristic` — the default: turns inferred from pauses. It detects that the
  floor changed hands, not who took it, so the same person speaking twice with
  someone in between gets two labels. The UI says "estimated from pauses" rather
  than implying voice recognition.

Action items become real `Task` rows, assigned when a spoken owner matches
exactly one colleague by name. Matching is conservative on purpose: an
unassigned task is visible, a misassigned one isn't.

---

## 4. What's new in the codebase

**Backend (`backend/app/`)**

| File | What it does |
| --- | --- |
| `task_models.py` | The `tasks` table — new, and needed by voice, follow-ups and meetings |
| `voice_models.py` | Commands, plan steps, conditional follow-ups, meetings, usage counters, permission overrides |
| `voice_llm.py` | The OpenAI wrapper — `plan_json()` for structure, `write_text()` for prose |
| `voice_transcription.py` | Whisper, segments, long-audio chunking |
| `voice_intent.py` | The multi-step planner and the intent catalog |
| `voice_actions.py` | The action registry and the safety sets |
| `voice_context.py` | Conversation memory for pronoun resolution |
| `voice_permissions.py` | intent → permission → role |
| `usage_metering.py` | Plan quotas, reserve-before-spend |
| `voice_time.py` | Spoken time → naive UTC, and back for display |
| `voice_i18n.py` | Localised fixed strings and the prompt's language instruction |
| `voice_storage.py` | Audio retention: none / local / S3-compatible |
| `voice_followups.py` | Condition checkers and the sweep |
| `voice_meetings.py` | The meeting pipeline |
| `voice_summarizer.py` | Email digest and meeting write-up prompts |
| `voice_scheduler.py` | The two background jobs |
| `voice_schemas.py` | Wire shapes |
| `routers/voice_commands.py`, `routers/voice_meetings.py`, `routers/tasks.py` | The APIs |

**Changed:** `models.py` (adds `Company.plan` and `Company.timezone`),
`config.py` (voice settings), `main.py` (routers, table registration, scheduler),
`requirements.txt` (`httpx`), `.env.example`.

**Frontend**

- `components/voice/` — `useVoiceRecorder`, `MicButton`, `VoicePlanSheet`, `VoiceHistory`
- `app/(app)/voice/`, `app/(app)/meetings/`, `app/(app)/tasks/`
- `lib/api.ts` — voice/meeting/task types and methods, `QuotaError`, multipart upload,
  authenticated audio fetch, and `pollVoiceCommand` with backoff
- `components/Nav.tsx` — three new links

---

## 5. Running it

Nothing beyond the existing setup:

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env          # set OPENAI_API_KEY
uvicorn app.main:app --reload

cd ../frontend
npm install
npm run dev
```

Tables are still created by `Base.metadata.create_all` on startup, same as
before — the new ones appear automatically.

**One caveat for existing installs:** `Company.plan` and `Company.timezone` are
new columns on an existing table, and `create_all` does not add columns to a
table that already exists. On a fresh database nothing needs doing. On a database
you've already been using, add them once:

```sql
ALTER TABLE companies ADD COLUMN plan VARCHAR DEFAULT 'pro' NOT NULL;
ALTER TABLE companies ADD COLUMN timezone VARCHAR;
```

This is the point where the README's "swap for Alembic once the schema
stabilizes" stops being optional — two new nullable-ish columns is the easy
version of this problem, and the next schema change won't be.

### Tests

```bash
cd backend
pip install pytest
pytest tests
```

They run against the real `app` package with SQLite in a temp directory, and
every model call is patched, so the suite needs no API key and no network.

---

## 6. Deliberately not here

- **WhatsApp voice notes.** The data model keeps `whatsapp_team` and
  `whatsapp_customer` as command sources, and the routing rule that matters is
  settled (a team member's number may issue commands; anyone else is transcribed
  only, never acted on). But this app has no WhatsApp integration to hang it off,
  and shipping a webhook handler for an API you haven't connected is code that
  can only rot.
- **Calendar events.** `schedule_meeting` creates a dated task and says so.
  A real Google/Microsoft event needs an OAuth flow and stored tokens, which is a
  feature of its own, not a line in this module.
- ~~**Document Q&A by voice.**~~ **Built.** See `document_models.py` /
  `document_store.py` / `routers/documents.py` (the Company Knowledge Base)
  and the `ask_documents` entries in `voice_intent.py`, `voice_permissions.py`
  and `voice_actions.py`.
- **Inbound email.** `email_activity_summary` summarises what you *sent* and what
  has gone quiet, and the prompt says so explicitly, because this app logs
  outbound mail only. A model handed a list of sent emails will otherwise write
  as though it read the replies.
