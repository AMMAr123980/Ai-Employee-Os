"""
Turns a transcript into an ordered PLAN.

The rule is not "pick one intent" — it's "return one step per action, in the
order they should happen". That single change is what makes the product
description's flagship example work end to end:

    "Draft a quotation for Acme for 25 laptops, email it to them, and remind
     me if they don't reply within three days."

    -> [draft_quotation, email_quotation, schedule_followup]

Four decisions hold this together:

1. **A plan is a list, and order is semantic.** Steps run top to bottom and a
   later step may reference an earlier one's output with the literal token
   `"$prev.quotation_number"`. That's why "send a quotation" expands to
   draft-then-email rather than one fused action: the draft is reversible and
   internal, the email reaches a customer, and they need different gates.
   Fusing them would either put a confirmation tap in front of harmless work or
   — worse — let the email out without one.

2. **The catalog is the single source of truth**, the same role EMPLOYEE_CATALOG
   plays for the AI employees. It carries `reads_only` and `expands_to` so
   safety classification and shorthand expansion are declared next to the intent
   rather than rediscovered in the prompt.

3. **The catalog handed to the model is scoped to the speaker's permissions.**
   A member never sees `send_email` as an option. The executor re-checks
   regardless.

4. **Dates resolve against the speaker's local clock** (voice_time), recent
   context is injected as facts (voice_context), and the summary comes back in
   the language spoken (voice_i18n). All three are prompt inputs, so they cost
   no extra calls.

One model call per command, JSON mode, no new dependencies.
"""
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from app import voice_i18n, voice_llm, voice_time

logger = logging.getLogger(__name__)

MAX_STEPS = 6  # a spoken sentence with more than six actions in it is a mis-transcription

REFERENCE_TOKEN = "$prev."

# --------------------------------------------------------------------------
# Intent catalog
# --------------------------------------------------------------------------
# reads_only  -> writes nothing; safe to auto-run and cheap to re-run
# expands_to  -> shorthand the planner may emit; rewritten by expand_plan()

INTENT_CATALOG: dict[str, dict[str, Any]] = {
    # ---- tasks, reminders, follow-ups ----
    "create_task": {
        "label": "Create a task or reminder",
        "example": "Remind me to call the supplier tomorrow morning.",
        "slots": ["title", "due_at", "priority (low|normal|high)", "customer_name (optional)"],
    },
    "schedule_meeting": {
        "label": "Block out a meeting",
        "example": "Schedule a meeting with Acme on Friday at 3 PM.",
        "slots": ["title", "customer_name (optional)", "starts_at"],
        "expands_to": ["create_task"],
    },
    "schedule_followup": {
        "label": "Chase this only if something doesn't happen",
        "example": "Remind me if they haven't replied in three days.",
        "slots": ["customer_name", "condition (no_reply|no_payment|always)",
                  "wait_days", "reminder_title (optional)"],
    },
    "complete_task": {
        "label": "Mark a task done",
        "example": "Mark the supplier call as done.",
        "slots": ["title"],
    },
    # ---- CRM ----
    "add_customer_note": {
        "label": "Log a note on a customer",
        "example": "Note on Acme: they want delivery before the 20th.",
        "slots": ["customer_name", "content", "note_type (note|call|meeting)"],
    },
    "change_pipeline_stage": {
        "label": "Move a customer's pipeline stage",
        "example": "Move Acme Corp to negotiation.",
        "slots": ["customer_name", "stage (new|contacted|qualified|proposal|negotiation|won|lost)"],
    },
    "create_customer": {
        "label": "Add a new customer",
        "example": "Add Zenith Traders, contact is Bilal, email bilal@zenith.pk.",
        "slots": ["name", "company (optional)", "email (optional)", "phone (optional)",
                  "lead_source (optional)"],
    },
    # ---- quotations ----
    "draft_quotation": {
        "label": "Draft a quotation (internal, not sent)",
        "example": "Draft a quotation for Acme for 25 laptops at 600 each.",
        "slots": ["customer_name", "items_description", "discount_percent (optional)",
                  "notes (optional)"],
    },
    "email_quotation": {
        "label": "Email an existing quotation to the customer",
        "example": "Email that quotation to Acme.",
        "slots": ["quotation_number (optional)", "customer_name", "body (optional)"],
    },
    # ---- invoices ----
    "create_invoice": {
        "label": "Create an invoice (internal, not sent)",
        "example": "Invoice Acme for the 25 laptops, due in 15 days.",
        "slots": ["customer_name", "items_description", "due_in_days (optional)",
                  "quotation_number (optional)"],
    },
    "send_invoice": {
        "label": "Email an invoice to the customer",
        "example": "Send Acme their invoice.",
        "slots": ["invoice_number (optional)", "customer_name", "body (optional)"],
    },
    "send_payment_reminder": {
        "label": "Email a payment reminder for an unpaid invoice",
        "example": "Chase Acme about the overdue invoice.",
        "slots": ["invoice_number (optional)", "customer_name"],
    },
    "record_payment": {
        "label": "Record a payment against an invoice",
        "example": "Acme paid invoice INV-000042 in full today.",
        "slots": ["invoice_number", "amount (optional — omit to mean paid in full)"],
    },
    "set_recurring_invoice": {
        "label": "Make an invoice repeat",
        "example": "Bill Acme for the support retainer every month.",
        "slots": ["invoice_number (optional)", "customer_name",
                  "interval (weekly|monthly|quarterly|yearly)"],
    },
    # ---- email ----
    "send_email": {
        "label": "Write and send an email to a customer",
        "example": "Email Sarah and ask if Friday still works.",
        "slots": ["customer_name", "subject", "body", "follow_up_in_days (optional)"],
    },
    # ---- reads: nothing is written, the answer comes straight back ----
    "sales_report": {
        "label": "Ask about sales figures",
        "example": "What did we invoice last month?",
        "slots": ["period (this_month|last_month|this_quarter|this_year|last_7_days)"],
        "reads_only": True,
    },
    "outstanding_invoices": {
        "label": "Ask what's unpaid",
        "example": "Who owes us money right now?",
        "slots": ["customer_name (optional)", "overdue_only (optional)"],
        "reads_only": True,
    },
    "customer_summary": {
        "label": "Ask about one customer",
        "example": "Catch me up on Acme Corp.",
        "slots": ["customer_name"],
        "reads_only": True,
    },
    "my_tasks": {
        "label": "Ask what's on your plate",
        "example": "What's due this week?",
        "slots": ["period (optional)"],
        "reads_only": True,
    },
    "email_activity_summary": {
        "label": "Summarise recent email activity and what needs chasing",
        "example": "What's outstanding on email this week?",
        "slots": ["period (optional)", "customer_name (optional)"],
        "reads_only": True,
    },
    "ask_documents": {
        "label": "Ask a question against uploaded company documents",
        "example": "What does our refund policy say about late returns?",
        "slots": ["question", "document_title (optional)"],
        "reads_only": True,
    },
    # ---- delegation ----
    "ask_ai_employee": {
        "label": "Hand the job to a specialist AI employee (HR, legal, stock, procurement...)",
        "example": "Ask the stock controller what's running low.",
        "slots": ["employee_key (optional)", "brief"],
    },
    "unclear": {
        "label": "Couldn't confidently match a supported action",
        "example": None,
        "slots": [],
    },
}


_SYSTEM_PROMPT = """You turn a spoken business instruction into a PLAN. Output ONLY a JSON object.

{now}

{context}

Supported actions and their slots:
{catalog}

Rules:
- A single instruction often contains SEVERAL actions ("draft a quote, book Friday, and \
chase them Monday"). Return one step per action, in the order they should happen.
- Return the FEWEST steps that do what was asked. Never invent a step that wasn't asked for.
- "Send a quotation to X" means two steps: draft_quotation, then email_quotation. \
"Draft/prepare a quotation" is draft_quotation alone. The same split applies to invoices: \
create_invoice, then send_invoice only if sending was actually asked for.
- A later step may use a value produced by an earlier one by putting the literal string \
"{ref}<field>" in a slot — for example {{"quotation_number": "{ref}quotation_number"}}. \
Use this instead of guessing a number that doesn't exist yet.
- Fill every slot you can infer. Leave a slot out of "config" entirely if it wasn't stated \
or clearly implied. Never invent names, dates, quantities or amounts.
- Resolve relative dates and times ("Friday at 3", "in three days", "end of the month") \
against the current local date and time given above. Output them as LOCAL ISO 8601 with NO \
timezone offset, e.g. "2026-09-18T15:00". Do not convert to UTC yourself. Omit a date that \
is genuinely ambiguous rather than guessing.
- "confidence" per step is your own 0.0-1.0 estimate that both the action and its slots are right.
- Each step's "summary" is one accurate sentence naming every value that will be written \
(names, amounts, dates) — a human reads it to approve the action.
- "missing_info" per step lists required slot names the instruction didn't supply.
- If the whole instruction matches nothing here, return a single step with intent "unclear".{language}

Respond with exactly this shape:
{{"steps": [{{"intent": "<action>", "config": {{...}}, "summary": "<one sentence>", \
"confidence": <0.0-1.0>, "missing_info": [...]}}], "summary": "<one sentence for the whole plan>"}}
"""


@dataclass
class PlannedStep:
    intent: str
    config: dict[str, Any] = field(default_factory=dict)
    summary: str = ""
    confidence: float = 0.0
    missing_info: list[str] = field(default_factory=list)


@dataclass
class VoicePlan:
    steps: list[PlannedStep] = field(default_factory=list)
    summary: str = ""
    locale: str = voice_i18n.DEFAULT_LOCALE
    timezone: str = voice_time.DEFAULT_TIMEZONE

    @property
    def confidence(self) -> float:
        """A plan is only as trustworthy as its weakest step — a confident
        quotation followed by a shaky date is a shaky plan."""
        return min((s.confidence for s in self.steps), default=0.0)

    @property
    def is_actionable(self) -> bool:
        return bool(self.steps) and any(s.intent != "unclear" for s in self.steps)

    @property
    def missing_info(self) -> list[str]:
        seen: list[str] = []
        for step in self.steps:
            for item in step.missing_info:
                if item not in seen:
                    seen.append(item)
        return seen


class IntentParsingError(Exception):
    pass


def _catalog_for_prompt(intents: list[str]) -> str:
    lines = []
    for key in intents:
        info = INTENT_CATALOG.get(key)
        if not info or key == "unclear":
            continue
        suffix = " [read-only, answers a question]" if info.get("reads_only") else ""
        lines.append(f'- {key}: slots = {info["slots"]}. Example: "{info["example"]}"{suffix}')
    return "\n".join(lines)


def expand_plan(steps: list[PlannedStep]) -> list[PlannedStep]:
    """Apply `expands_to` when the model emits shorthand.

    `schedule_meeting` is the live case: people say it constantly, but this app
    has no calendar integration, so it becomes a dated task. Doing the rewrite
    here means there's exactly one place where "what the user said" turns into
    "what the system does" — and when a real calendar lands, one line changes.
    """
    out: list[PlannedStep] = []
    for step in steps:
        expansion = INTENT_CATALOG.get(step.intent, {}).get("expands_to")
        if not expansion:
            out.append(step)
            continue
        for target in expansion:
            config = dict(step.config)
            if target == "create_task":
                # A meeting is a task with a start time and a recognisable title.
                config.setdefault("due_at", config.get("starts_at"))
                title = config.get("title") or "Meeting"
                if not str(title).lower().startswith("meeting"):
                    title = f"Meeting: {title}"
                config["title"] = title
                config.setdefault("priority", "high")
            out.append(PlannedStep(
                intent=target,
                config=config,
                summary=step.summary,
                confidence=step.confidence,
                missing_info=list(step.missing_info),
            ))
    return out[:MAX_STEPS]


def parse_voice_command(
    transcript: str,
    *,
    allowed_intents: Optional[list[str]] = None,
    context_block: str = "",
    tz_name: str = voice_time.DEFAULT_TIMEZONE,
    locale: str = voice_i18n.DEFAULT_LOCALE,
) -> VoicePlan:
    """One model call, strict JSON out, a plan back.

    Keyword-only past the transcript so the call site reads as a list of what
    shapes the plan: who may do what, what was just discussed, what time it is
    where they are, what language they used.
    """
    intents = allowed_intents or [k for k in INTENT_CATALOG if k != "unclear"]

    system_prompt = _SYSTEM_PROMPT.format(
        now=voice_time.prompt_now(tz_name),
        context=context_block or "(no recent context)",
        catalog=_catalog_for_prompt(intents),
        ref=REFERENCE_TOKEN,
        language=voice_i18n.language_instruction(locale),
    )

    try:
        parsed = voice_llm.plan_json(system_prompt, transcript, max_tokens=1500)
    except voice_llm.LLMError as exc:
        raise IntentParsingError(str(exc)) from exc

    raw_steps = parsed.get("steps")
    if isinstance(raw_steps, dict):          # tolerated: one step returned unwrapped
        raw_steps = [raw_steps]
    if not isinstance(raw_steps, list) or not raw_steps:
        raw_steps = [{"intent": "unclear", "summary": parsed.get("summary", "")}]

    steps: list[PlannedStep] = []
    for raw in raw_steps[:MAX_STEPS]:
        if not isinstance(raw, dict):
            continue
        intent = raw.get("intent", "unclear")
        if intent not in INTENT_CATALOG or intent not in intents:
            # Either hallucinated, or an action this person may not run. Both
            # become "unclear" rather than being dropped, so the user is told
            # something wasn't understood instead of a step quietly vanishing
            # from a plan they were about to approve.
            logger.info("Discarding unsupported or forbidden intent %r", intent)
            intent = "unclear"
        steps.append(PlannedStep(
            intent=intent,
            config=raw.get("config") or {},
            summary=raw.get("summary", "") or "",
            confidence=float(raw.get("confidence", 0.0) or 0.0),
            missing_info=list(raw.get("missing_info") or []),
        ))

    steps = expand_plan(steps)
    actionable = [s for s in steps if s.intent != "unclear"]
    if actionable:
        steps = actionable  # drop stray "unclear" steps from an otherwise good plan

    return VoicePlan(
        steps=steps,
        summary=parsed.get("summary", "") or (steps[0].summary if steps else ""),
        locale=voice_i18n.normalize_locale(locale),
        timezone=tz_name,
    )
