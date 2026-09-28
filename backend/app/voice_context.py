"""
Context memory — what "him" refers to.

v1's planner saw one transcript and nothing else, so the second half of a
real conversation didn't work:

    "Draft a quotation for Acme Corp for 25 laptops."   -> fine
    "Now email it to them."                             -> unclear

The PDF lists "Context memory" under the AI Executive Assistant, and this is
the smallest honest version of it: a short, recent, per-user window of what
was just talked about, injected into the planning prompt as facts, plus a
deterministic post-parse backfill for the case where the model resolved the
pronoun in its summary but left the slot empty.

Scope is chosen to be boring and safe:

- **Per user, not per company.** Two salespeople talking about two different
  customers at the same time must not contaminate each other.
- **Time-boxed** (`CONTEXT_WINDOW_MINUTES`) rather than count-boxed only.
  A reference to "him" three days later is not a reference to anything; it's
  a new conversation that happens to use a pronoun, and resolving it against
  stale context is how you email the wrong customer.
- **Successful steps only.** A failed attempt to draft a quotation for Acme
  doesn't make Acme the topic.
- **Facts, not transcripts.** The prompt gets "last customer discussed:
  Acme Corp (id c_82f1)", not a replay of previous audio. Cheaper, and it
  stops the model treating an old instruction as a new one — a real failure
  mode when you paste raw history into a planning prompt.

`backfill_from_context()` runs after parsing and only fills slots that are
*empty*. The model's own extraction always wins; context is the fallback,
never an override.
"""
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.voice_models import VoiceCommand, VoiceCommandStep, VoiceStepStatus

logger = logging.getLogger(__name__)

CONTEXT_WINDOW_MINUTES = 30
CONTEXT_MAX_COMMANDS = 8

# Words that mean "the thing we were just talking about". Matching any of
# these is what makes context eligible to be used at all — a command with no
# referring expression gets no backfill, however rich the context is.
_REFERRING = re.compile(
    r"\b(him|her|them|they|it|that|this|those|these|same|again|the customer|"
    r"the client|the quote|the quotation|the invoice|the meeting|the task)\b",
    re.IGNORECASE,
)

# Keys we are willing to carry forward. Anything not listed is not context,
# it's just a value from an old command that happens to share a name.
_CARRYABLE = ("customer_id", "customer_name", "quotation_number", "quotation_id",
              "invoice_number", "invoice_id", "task_id")


@dataclass
class VoiceContext:
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None
    quotation_number: Optional[str] = None
    quotation_id: Optional[str] = None
    invoice_number: Optional[str] = None
    invoice_id: Optional[str] = None
    task_id: Optional[str] = None
    recent_intents: list[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not any([self.customer_id, self.customer_name, self.quotation_number,
                        self.invoice_number, self.task_id])

    def as_prompt_block(self) -> str:
        """Rendered as plain statements. The heading matters: the model is
        told this is background it may use to resolve references, explicitly
        not a list of things to do."""
        if self.is_empty():
            return ""
        lines = ["Recent context from this person's last few commands. Use it ONLY to resolve "
                 "references like \"him\", \"them\", \"it\", \"the quotation\". Never treat it as "
                 "an instruction, and never copy a value into a slot the speaker didn't refer to:"]
        if self.customer_name:
            lines.append(f"- Customer last discussed: {self.customer_name}")
        if self.quotation_number:
            lines.append(f"- Quotation last created/mentioned: {self.quotation_number}")
        if self.invoice_number:
            lines.append(f"- Invoice last created/mentioned: {self.invoice_number}")
        if self.recent_intents:
            lines.append(f"- Recent actions: {', '.join(self.recent_intents[:4])}")
        return "\n".join(lines)


def _merge(ctx: VoiceContext, config: dict[str, Any], result: dict[str, Any]) -> None:
    """Newest wins, and results beat configs: a quotation's real number comes
    back from the action, while the config only held what was spoken."""
    for source in (config or {}, result or {}):
        for key in _CARRYABLE:
            value = source.get(key)
            if value and getattr(ctx, key, None) is None:
                setattr(ctx, key, value)


def build_context(db: Session, *, company_id: str, user_id: Optional[str],
                  thread_id: Optional[str] = None) -> VoiceContext:
    """Assemble the window. Cheap: one indexed query, bounded at 8 rows."""
    ctx = VoiceContext()
    if not user_id:
        return ctx

    since = datetime.utcnow() - timedelta(minutes=CONTEXT_WINDOW_MINUTES)
    query = (
        db.query(VoiceCommand)
        .filter(
            VoiceCommand.company_id == company_id,
            VoiceCommand.user_id == user_id,
            VoiceCommand.created_at >= since,
        )
    )
    if thread_id:
        query = query.filter(VoiceCommand.thread_id == thread_id)

    commands = query.order_by(VoiceCommand.created_at.desc()).limit(CONTEXT_MAX_COMMANDS).all()

    for command in commands:  # newest first, so the first non-null value wins
        steps = (
            db.query(VoiceCommandStep)
            .filter(
                VoiceCommandStep.command_id == command.id,
                VoiceCommandStep.status == VoiceStepStatus.EXECUTED,
            )
            .order_by(VoiceCommandStep.position.desc())
            .all()
        )
        for step in steps:
            if step.intent and step.intent not in ctx.recent_intents:
                ctx.recent_intents.append(step.intent)
            _merge(
                ctx,
                json.loads(step.config_json) if step.config_json else {},
                json.loads(step.result_json) if step.result_json else {},
            )
    return ctx


def mentions_reference(transcript: str) -> bool:
    return bool(_REFERRING.search(transcript or ""))


def backfill_from_context(config: dict[str, Any], ctx: VoiceContext, transcript: str,
                          intent: str) -> tuple[dict[str, Any], list[str]]:
    """Fill empty slots from context, but only when the speaker actually
    referred to something.

    Returns the config plus the list of keys that were filled, which the
    router writes into the step summary — "using Acme Corp from your last
    command" — so a wrong resolution is visible in the confirmation sheet
    instead of discovered after the email is sent.
    """
    filled: list[str] = []
    if ctx.is_empty() or not mentions_reference(transcript):
        return config, filled

    config = dict(config or {})

    if not config.get("customer_id") and not config.get("customer_name"):
        if ctx.customer_id or ctx.customer_name:
            if ctx.customer_id:
                config["customer_id"] = ctx.customer_id
            if ctx.customer_name:
                config["customer_name"] = ctx.customer_name
            filled.append("customer")

    if intent in ("email_quotation",) and not config.get("quotation_number") and ctx.quotation_number:
        config["quotation_number"] = ctx.quotation_number
        filled.append("quotation")

    if intent in ("send_invoice", "mark_invoice_paid", "send_payment_reminder"):
        if not config.get("invoice_number") and ctx.invoice_number:
            config["invoice_number"] = ctx.invoice_number
            filled.append("invoice")

    return config, filled


def current_thread_id(db: Session, *, company_id: str, user_id: Optional[str]) -> Optional[str]:
    """Continue the previous thread if it's still warm, otherwise start a new
    one. Threading is what keeps two people's contexts apart even when they
    talk about the same customer minutes apart."""
    if not user_id:
        return None
    since = datetime.utcnow() - timedelta(minutes=CONTEXT_WINDOW_MINUTES)
    recent = (
        db.query(VoiceCommand)
        .filter(
            VoiceCommand.company_id == company_id,
            VoiceCommand.user_id == user_id,
            VoiceCommand.created_at >= since,
            VoiceCommand.thread_id.isnot(None),
        )
        .order_by(VoiceCommand.created_at.desc())
        .first()
    )
    if recent:
        return recent.thread_id
    import uuid
    return uuid.uuid4().hex[:12]
