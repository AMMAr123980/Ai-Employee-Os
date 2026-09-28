# Phase 8 — Specialized AI Employees

Seven colleagues for the departments the sales modules don't cover: **HR
Officer, Legal Assistant, Marketing Executive, Procurement Officer, Inventory
Controller, Bookkeeper, Support Agent.**

No new dependencies, no new API key, no new scheduler. It reuses the OpenAI
client, the JWT auth, the SQLAlchemy session and the Tailwind design language
already in the app.

## The shape of it

An employee is **not** a feature area. It's a declarative catalog entry —
persona, the actions it owns, example prompts — plus one shared pipeline:

```
brief → plan → ownership check → safety gate → execute or hold → log
```

Adding an eighth department is one entry in `ai_employee_registry.py` and N
action functions in `ai_employee_actions.py`. No new router, no new schema
file, no new confirmation UI. That's the whole reason it's built this way
instead of as six more CRUD modules.

| File | Job |
| --- | --- |
| `ai_employee_registry.py` | `EMPLOYEE_CATALOG`, `INTENT_SLOTS`, `DUTIES`. Read by the UI, the planner, and the router — so they can't drift apart. |
| `ai_employee_brain.py` | `plan()` (JSON mode, classification + slots), `write()` (long-form drafts), `review_json()` (structured findings). |
| `ai_employee_actions.py` | 41 action functions, `(db, company_id, user_id, config) -> dict`, plus the safety gate. |
| `ai_employee_models.py` | The run log, per-company config, and the department records. |
| `routers/ai_employees.py` | One router for all seven. |

## Using it

`/ai-employees` is the roster. Click into one and type what you need. The
result is either done, or a card asking you to approve it first.

```bash
POST /api/ai-employees/inventory_controller/brief
{"brief": "Add 'Logitech MX Master 3' as a stock item, we hold 25, reorder at 10"}
→ executed

POST /api/ai-employees/procurement_officer/brief
{"brief": "Raise a PO to Zenith for 50 keyboards at 2,400 each"}
→ executed (a DRAFT purchase order — nothing sent)

POST /api/ai-employees/procurement_officer/brief
{"brief": "Send PO-000001 to Zenith"}
→ awaiting_confirmation, with a summary to approve
```

| Endpoint | Purpose |
| --- | --- |
| `GET /api/ai-employees` | Roster + this company's overrides |
| `POST /api/ai-employees/{key}/brief` | The main flow. `{"dry_run": true}` plans without executing |
| `POST /api/ai-employees/runs/{id}/confirm` | Approve. `{"overrides": {...}}` patches a slot first |
| `POST /api/ai-employees/runs/{id}/cancel` | Decline |
| `GET /api/ai-employees/runs` | Audit trail |
| `GET /api/ai-employees/{key}/records` | That department's rows, for the Records tab |
| `PATCH /api/ai-employees/{key}/config` | Enable/disable, rename, approval level, company context |
| `GET /api/ai-employees/duties` · `POST .../{key}/run-duty/{duty}` | Recurring sweeps |

The run schema (`AIEmployeeRunOut`) deliberately mirrors the voice-command
schema from that module, so the same confirmation UI serves both if voice is
added later.

## The safety model

All of it is three sets at the bottom of `ai_employee_actions.py`, not a flag
on forty functions — "can this happen without a human approving it" should be
answerable by reading one screen.

- **`AUTO_EXECUTE`** — reads, reports, reversible internal writes. Runs immediately.
- **`CONFIRM_REQUIRED`** — awkward to undo, or produces something a human will act on. Held.
- **`ALWAYS_CONFIRM`** — reaches an outside party or moves money: `send_campaign`,
  `send_purchase_order`, `approve_purchase_order`, `record_payment`,
  `decide_leave_request`, `update_employee`. Held regardless of settings.

`autonomy_level` accepts `"standard"` or `"cautious"` (hold everything). There
is deliberately **no** third value that loosens the gate, and
`requires_confirmation()` checks `ALWAYS_CONFIRM` before anything else. A
company can make this more careful than default, never less.

Five guards that will look like over-engineering until the day they fire:

1. **An import-time assertion** fails the app if any registered action is in
   neither set. An unclassified action would otherwise default to running.
2. **`employee_owns_intent()`** is checked in the router, not just the prompt.
   Asking Marketing to raise a purchase order returns `no_action` even if the
   model plays along.
3. **A confidence floor** (`MIN_AUTO_CONFIDENCE = 0.45`). A shaky match gets a
   human look regardless of which set its intent is in.
4. **Whitelisted fields** on `update_employee` / `update_supplier`.
   `salary_amount` isn't on the HR whitelist, and `_redact()` strips salary-
   and credential-shaped keys from every prompt — the HR employee can tell you
   who's on probation without knowing what anyone earns.
5. **Drafting and sending are always separate intents.** Everything
   `write()` produces lands in a DRAFT row. Nothing generated can reach an
   outside party in the same step that generated it.

## Running without an OpenAI key

`plan()` falls back to keyword matching against the employee's own intent
list, scoring ≤0.3 confidence — which puts it under the floor above, so it
always lands in the approval card with the slots blank for you to fill. Every
non-AI action works fully: stock movements, purchase orders, leave, expenses,
supplier comparison, and all six reports. Only the text-generating four
(`draft_job_description`, `draft_contract`, `write_campaign_copy`,
`draft_support_reply`) genuinely need the key, and they say so plainly.

## Recurring duties

Four read-only sweeps in `ai_employee_registry.DUTIES` — low stock, expiring
contracts, overdue invoices, monthly headcount. They cost no tokens: the
intent is known, so no planning call happens. Run them from the roster page,
or hang them off the existing APScheduler job in `followup_scheduler.py`:

```python
from app.ai_employee_registry import DUTIES
# in the scheduler tick, for each company:
#   POST-equivalent call into the same code path as run_duty()
```

## What changed in the existing app

Everything else is untouched. The integration is:

- `main.py` — one router include, one model import (registers the new tables).
- `Nav.tsx` — one link.
- `lib/api.ts` — new types and methods, appended.
- Nothing in `models.py`, `auth.py`, `config.py`, or any existing router.

Three places where the module was adapted to fit this codebase rather than the
reverse, worth knowing about:

- **Escalations write to the customer activity timeline** (there's no tasks
  table here), so they appear on the customer detail page the team already
  watches.
- **Campaign sending is email-only.** WhatsApp and social raise a clear error
  *before* the campaign status moves, rather than marking something sent that
  never went anywhere.
- **Audience "no contact since N days"** is computed from the email log and
  notes, not from a customer `updated_at` column — a record edited last week
  hasn't necessarily been *spoken to*.

## Deliberately not here

- **Payroll.** Salary is stored and never prompted on, but running payroll
  means tax tables, statutory deductions and per-country filing. Getting that
  95% right is worse than not having it.
- **E-signature.** Contracts are drafted and tracked; signing needs a DocuSign
  or Adobe integration and an audit trail this app doesn't have.
- **Double-entry accounting.** The Bookkeeper does expenses, payment matching
  and a cash position. It is not a general ledger and shouldn't be presented
  as one.
- **A recruitment pipeline.** `draft_job_description` exists; CV parsing,
  candidate stages and interview scheduling would be an eighth employee with
  its own tables. It's the obvious next one to build.
