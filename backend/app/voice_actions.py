"""
What actually happens once a plan has been produced.

Same open/closed shape as `ai_employee_actions.ACTION_REGISTRY`: every action is
a plain function `(ctx) -> dict`, keyed by string in VOICE_ACTION_REGISTRY. A new
voice-actionable intent is one function + one registry entry + one
`voice_intent.INTENT_CATALOG` entry + one `voice_permissions.INTENT_PERMISSIONS`
entry, and the import-time assertion at the bottom fails the app at boot if you
forget any of the last three.

Two things are shaped by multi-step plans:

1. **Actions take an `ActionContext`, not five positional arguments.** A step
   needs the timezone it was spoken in, the locale to write errors in, and the
   results of earlier steps. One dataclass beats threading four more parameters
   through twenty functions.

2. **`resolve_step_config()` substitutes `$prev.<field>` references** before an
   action runs. "Draft a quotation and email it" is two steps, and the second's
   `quotation_number` doesn't exist until the first has run. An unresolvable
   reference raises rather than passing an empty slot through — emailing
   "quotation None" to a customer is worse than failing.

Everything writes through the same models, helpers and side effects the REST
routers use: quotations get numbers from the same `PREFIX-000001` scheme, emails
are logged as `EmailMessage` rows so they appear in the customer activity
timeline, pipeline changes log a `CustomerNote`, and payments flow through the
same status transitions as the invoices router. A voice command should be
indistinguishable, afterwards, from the same work done by hand.

The safety classification:

- **AUTO_EXECUTE** — reads, and reversible internal writes. Nothing leaves the
  company, so nothing waits for a tap.
- **CONFIRM_REQUIRED** — anything that reaches a customer or moves money. Held
  at AWAITING_CONFIRMATION until a human approves it.

`READ_ONLY_INTENTS` is a subset of AUTO_EXECUTE that the UI uses to skip the
confirmation sheet entirely — being asked to confirm "what did we invoice last
month" is the kind of friction that stops people using a feature.
"""
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Optional

from sqlalchemy.orm import Session

from app import ai_assistant, models, voice_i18n, voice_time
from app.config import settings
from app.email_sender import EmailSendError, send_email as smtp_send
from app.pdf_generator import generate_invoice_pdf, generate_quotation_pdf
from app.task_models import Task, TaskPriority, TaskSource, TaskStatus

logger = logging.getLogger(__name__)

REFERENCE_TOKEN = "$prev."

_INTERVAL_DAYS = {"weekly": 7, "monthly": 30, "quarterly": 91, "yearly": 365}


class VoiceActionError(Exception):
    """Raised for anything the user can fix by re-issuing the command: customer
    not found, ambiguous name, missing slot. The message is shown as-is and is
    already localised, so keep it short."""


@dataclass
class ActionContext:
    db: Session
    company_id: str
    user_id: Optional[str]
    config: dict[str, Any] = field(default_factory=dict)
    tz_name: str = voice_time.DEFAULT_TIMEZONE
    locale: str = voice_i18n.DEFAULT_LOCALE
    command_id: Optional[str] = None
    step_id: Optional[str] = None

    def t(self, key: str, **kwargs: Any) -> str:
        return voice_i18n.t(key, self.locale, **kwargs)

    def get(self, key: str, default: Any = None) -> Any:
        value = self.config.get(key)
        return default if value in (None, "") else value


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def resolve_step_config(config: dict[str, Any], previous_results: dict[str, Any]) -> dict[str, Any]:
    """Substitute "$prev.<field>" tokens from earlier steps' results.

    Walks nested dicts and lists so a reference inside a list still resolves.
    Case-insensitive on the field name, because the planner isn't perfectly
    consistent about `quotation_number` vs `quotationNumber`.
    """
    def resolve(value: Any) -> Any:
        if isinstance(value, str) and value.startswith(REFERENCE_TOKEN):
            wanted = value[len(REFERENCE_TOKEN):].strip()
            for key, candidate in previous_results.items():
                if key.lower() == wanted.lower() and candidate not in (None, ""):
                    return candidate
            raise VoiceActionError(
                f'This step needed "{wanted}" from the previous step, which didn\'t produce it.'
            )
        if isinstance(value, dict):
            return {k: resolve(v) for k, v in value.items()}
        if isinstance(value, list):
            return [resolve(v) for v in value]
        return value

    return resolve(dict(config or {}))


def _resolve_customer(ctx: ActionContext, required: bool = True):
    """Name -> Customer row, refusing to guess when it's ambiguous.

    Matching is company-scoped and searches both the contact name and the
    company name, because people say "email Acme" when the customer row is
    "Bilal Ahmed" at company "Acme Traders".
    """
    customer_id = ctx.get("customer_id")
    if customer_id:
        customer = ctx.db.get(models.Customer, customer_id)
        if customer and customer.company_id == ctx.company_id:
            return customer

    name = str(ctx.get("customer_name") or ctx.get("name") or "").strip()
    if not name:
        if required:
            raise VoiceActionError(ctx.t("no_customer_named"))
        return None

    like = f"%{name}%"
    matches = (
        ctx.db.query(models.Customer)
        .filter(
            models.Customer.company_id == ctx.company_id,
            (models.Customer.name.ilike(like)) | (models.Customer.company.ilike(like)),
        )
        .limit(6)
        .all()
    )
    if not matches:
        if required:
            raise VoiceActionError(ctx.t("customer_not_found", name=name))
        return None
    if len(matches) > 1:
        exact = [
            m for m in matches
            if (m.name or "").strip().lower() == name.lower()
            or (m.company or "").strip().lower() == name.lower()
        ]
        if len(exact) == 1:
            return exact[0]
        raise VoiceActionError(
            ctx.t("customer_ambiguous", name=name, names=", ".join(m.name for m in matches))
        )
    return matches[0]


def _spoken_datetime(ctx: ActionContext, *keys: str) -> Optional[datetime]:
    for key in keys:
        value = ctx.get(key)
        if value:
            resolved = voice_time.resolve_spoken_datetime(value, ctx.tz_name)
            if resolved:
                return resolved
    days = ctx.get("due_in_days")
    if days is not None:
        try:
            return datetime.utcnow() + timedelta(days=float(days))
        except (TypeError, ValueError):
            return None
    return None


def _period_bounds(period: Optional[str]) -> tuple[datetime, datetime]:
    """Spoken periods -> (start, end) in naive UTC. Unknown or missing means this
    month, which is what people mean when they say "how are we doing"."""
    now = datetime.utcnow()
    period = (period or "this_month").lower().replace(" ", "_").replace("-", "_")
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    if period == "last_month":
        end = month_start
        start = (month_start - timedelta(days=1)).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0)
        return start, end
    if period in ("last_7_days", "this_week", "last_week"):
        return now - timedelta(days=7), now
    if period == "this_quarter":
        return month_start.replace(month=3 * ((now.month - 1) // 3) + 1), now
    if period in ("this_year", "ytd"):
        return month_start.replace(month=1), now
    if period == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0), now
    return month_start, now


def _money(amount: Any) -> float:
    try:
        return round(float(amount or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def _next_number(ctx: ActionContext, model, prefix: str) -> str:
    """Same scheme as routers/quotations._next_number, so numbers issued by voice
    sit in the same sequence as numbers issued by hand."""
    count = ctx.db.query(model).filter(model.company_id == ctx.company_id).count() + 1
    return f"{prefix}-{count:06d}"


def _totals(items: list[dict], discount_percent: float, tax_percent: float) -> tuple[float, float]:
    subtotal = sum(_money(i["quantity"]) * _money(i["unit_price"]) for i in items)
    taxable = subtotal - subtotal * (discount_percent / 100)
    return subtotal, taxable + taxable * (tax_percent / 100)


def _line_items_from(ctx: ActionContext) -> list[dict[str, Any]]:
    """Spoken description -> line items, through the same
    `ai_assistant.draft_items_from_prompt()` the quotation screen's AI Draft
    button uses. Reused rather than reimplemented so a spoken description goes
    through extraction that's already tuned for this."""
    description = ctx.get("items_description") or ctx.get("content") or ""
    if not description:
        raise VoiceActionError("Didn't catch what to put on it — say the product and quantity.")

    draft = ai_assistant.draft_items_from_prompt(str(description))
    items = [dict(i) for i in (draft.get("items") or [])]
    if not items:
        raise VoiceActionError("Couldn't turn that into line items — try naming the product and quantity.")
    return items


def _send_and_log_email(
    ctx: ActionContext, *, customer, subject: str, body: str,
    quotation=None, invoice=None, attach_pdf: bool = False,
    follow_up_in_days: Optional[float] = None,
) -> dict:
    """Send, and log the same `EmailMessage` row the email router logs.

    Going through this rather than calling the SMTP helper directly is what
    keeps a voice-sent email visible in the customer's activity timeline, in the
    follow-up scheduler's queue, and in the email history — identical to one
    sent from the Email Assistant screen.

    An SMTP failure is recorded on the row and returned, not raised: "SMTP isn't
    configured" is a setup problem the user should read, not a failed step they
    should retry by speaking again.
    """
    if not getattr(customer, "email", None):
        raise VoiceActionError(ctx.t("no_email_on_file", name=customer.name))

    follow_up_at = (
        datetime.utcnow() + timedelta(days=float(follow_up_in_days))
        if follow_up_in_days else None
    )

    row = models.EmailMessage(
        company_id=ctx.company_id,
        user_id=ctx.user_id,
        customer_id=customer.id,
        quotation_id=quotation.id if quotation is not None else None,
        invoice_id=invoice.id if invoice is not None else None,
        to_email=customer.email,
        subject=subject,
        body=body,
        status=models.EmailStatus.DRAFT,
        follow_up_at=follow_up_at,
    )
    ctx.db.add(row)
    ctx.db.flush()

    attachment_bytes = attachment_filename = None
    if attach_pdf and quotation is not None:
        attachment_bytes = generate_quotation_pdf(quotation, customer)
        attachment_filename = f"{quotation.number}.pdf"
    elif attach_pdf and invoice is not None:
        attachment_bytes = generate_invoice_pdf(invoice, customer)
        attachment_filename = f"{invoice.number}.pdf"

    error = None
    try:
        smtp_send(
            to_email=customer.email,
            subject=subject,
            body=body,
            attachment_bytes=attachment_bytes,
            attachment_filename=attachment_filename,
        )
        row.status = models.EmailStatus.SENT
        row.sent_at = datetime.utcnow()
        if follow_up_at:
            row.follow_up_status = models.FollowUpStatus.PENDING
        if quotation is not None and quotation.status == models.QuotationStatus.DRAFT:
            quotation.status = models.QuotationStatus.SENT
    except EmailSendError as exc:
        row.status = models.EmailStatus.FAILED
        row.error_message = str(exc)
        row.follow_up_at = None
        error = str(exc)

    ctx.db.commit()
    return {
        "email_id": row.id,
        "to": customer.email,
        "subject": subject,
        "sent": row.status == models.EmailStatus.SENT,
        "error": error,
        "customer_id": customer.id,
        "customer_name": customer.name,
    }


# --------------------------------------------------------------------------
# Tasks & reminders
# --------------------------------------------------------------------------

def action_create_task(ctx: ActionContext) -> dict:
    customer = _resolve_customer(ctx, required=False)
    due_date = _spoken_datetime(ctx, "due_at", "due_date", "starts_at")

    priority_raw = str(ctx.get("priority", "normal")).lower()
    priority = TaskPriority(priority_raw) if priority_raw in TaskPriority._value2member_map_ \
        else TaskPriority.NORMAL

    task = Task(
        company_id=ctx.company_id,
        created_by_user_id=ctx.user_id,
        assigned_to_user_id=ctx.user_id,
        customer_id=customer.id if customer else None,
        title=str(ctx.get("title", "Follow up")),
        description=ctx.get("description"),
        priority=priority,
        due_date=due_date,
        source=TaskSource.VOICE,
        source_ref=ctx.command_id,
    )
    ctx.db.add(task)
    ctx.db.commit()
    ctx.db.refresh(task)

    google_url = None
    outlook_url = None
    try:
        from app.calendar_service import create_calendar_event, generate_google_calendar_url, generate_outlook_calendar_url
        cal_event = create_calendar_event(
            db=ctx.db,
            company_id=ctx.company_id,
            user_id=ctx.user_id,
            data={
                "title": task.title,
                "description": task.description or f"Created via Voice/Meeting assistant",
                "starts_at": due_date or (datetime.utcnow() + timedelta(days=1)),
                "customer_id": customer.id if customer else None,
            }
        )
        google_url = generate_google_calendar_url(cal_event)
        outlook_url = generate_outlook_calendar_url(cal_event)
    except Exception as exc:
        logger.error(f"Failed to create calendar event for task: {exc}")

    return {
        "task_id": task.id,
        "title": task.title,
        "due": voice_time.format_for_user(due_date, ctx.tz_name),
        "customer_id": customer.id if customer else None,
        "customer_name": customer.name if customer else None,
        "google_calendar_url": google_url,
        "outlook_calendar_url": outlook_url,
    }



def action_complete_task(ctx: ActionContext) -> dict:
    title = str(ctx.get("title") or "").strip()
    if not title:
        raise VoiceActionError("Say which task to close.")

    matches = (
        ctx.db.query(Task)
        .filter(
            Task.company_id == ctx.company_id,
            Task.status.in_([TaskStatus.OPEN, TaskStatus.IN_PROGRESS]),
            Task.title.ilike(f"%{title}%"),
        )
        .order_by(Task.created_at.desc())
        .limit(5)
        .all()
    )
    if not matches:
        raise VoiceActionError(f'No open task matching "{title}".')
    if len(matches) > 1:
        raise VoiceActionError(
            f'"{title}" matches several open tasks ({", ".join(t.title for t in matches)}) — be more specific.'
        )

    task = matches[0]
    task.status = TaskStatus.DONE
    task.completed_at = datetime.utcnow()
    ctx.db.commit()
    return {"task_id": task.id, "title": task.title, "status": "done"}


def action_schedule_followup(ctx: ActionContext) -> dict:
    """"...and remind me if they don't reply within three days."

    Stores a condition, not just a deadline. voice_followups.sweep_followups()
    evaluates it when the deadline arrives, so a customer who replies on day two
    never generates a chase.
    """
    from app import voice_followups
    from app.voice_models import VoiceFollowup

    customer = _resolve_customer(ctx, required=False)
    condition = str(ctx.get("condition", "no_reply")).lower().replace(" ", "_")
    if condition not in voice_followups.CONDITION_CHECKERS:
        valid = ", ".join(voice_followups.CONDITION_CHECKERS)
        raise VoiceActionError(f'"{condition}" isn\'t a follow-up condition. Use one of: {valid}.')
    if condition != "always" and customer is None:
        raise VoiceActionError(ctx.t("no_customer_named"))

    due_at = _spoken_datetime(ctx, "due_at", "remind_at")
    if due_at is None:
        try:
            wait_days = float(ctx.get("wait_days", 3) or 3)
        except (TypeError, ValueError):
            wait_days = 3
        due_at = datetime.utcnow() + timedelta(days=wait_days)

    title = ctx.get("reminder_title") or (
        f"Follow up with {customer.name}" if customer else "Follow up")

    followup = VoiceFollowup(
        company_id=ctx.company_id,
        user_id=ctx.user_id,
        customer_id=customer.id if customer else None,
        voice_command_id=ctx.command_id,
        step_id=ctx.step_id,
        condition_type=condition,
        condition_config_json=json.dumps({
            k: v for k, v in ctx.config.items()
            if k in ("invoice_number", "quotation_number")
        }),
        reminder_title=str(title),
        due_at=due_at,
    )
    ctx.db.add(followup)
    ctx.db.commit()
    ctx.db.refresh(followup)
    return {
        "followup_id": followup.id,
        "condition": condition,
        "due": voice_time.format_for_user(due_at, ctx.tz_name),
        "customer_id": customer.id if customer else None,
    }


# --------------------------------------------------------------------------
# CRM
# --------------------------------------------------------------------------

def action_create_customer(ctx: ActionContext) -> dict:
    name = str(ctx.get("name") or ctx.get("customer_name") or "").strip()
    if not name:
        raise VoiceActionError("Didn't catch the customer's name.")

    existing = (
        ctx.db.query(models.Customer)
        .filter(models.Customer.company_id == ctx.company_id, models.Customer.name.ilike(name))
        .first()
    )
    if existing:
        raise VoiceActionError(f'"{name}" is already in the customer list.')

    customer = models.Customer(
        company_id=ctx.company_id,
        name=name,
        company=ctx.get("company"),
        email=ctx.get("email"),
        phone=ctx.get("phone"),
        address=ctx.get("address"),
        lead_source=ctx.get("lead_source"),
        notes=ctx.get("notes"),
    )
    ctx.db.add(customer)
    ctx.db.commit()
    ctx.db.refresh(customer)
    return {"customer_id": customer.id, "customer_name": customer.name}


def action_add_customer_note(ctx: ActionContext) -> dict:
    customer = _resolve_customer(ctx)
    content = str(ctx.get("content") or "").strip()
    if not content:
        raise VoiceActionError("Didn't catch what the note should say.")

    raw_type = str(ctx.get("note_type", "note")).lower()
    note_type = models.NoteType(raw_type) if raw_type in models.NoteType._value2member_map_ \
        else models.NoteType.NOTE

    note = models.CustomerNote(
        company_id=ctx.company_id,
        customer_id=customer.id,
        user_id=ctx.user_id,
        note_type=note_type,
        content=content,
    )
    ctx.db.add(note)
    ctx.db.commit()
    ctx.db.refresh(note)
    return {"note_id": note.id, "customer_id": customer.id, "customer_name": customer.name}


def action_change_pipeline_stage(ctx: ActionContext) -> dict:
    customer = _resolve_customer(ctx)
    raw = str(ctx.get("stage") or "").strip().lower().replace(" ", "_")
    try:
        new_stage = models.PipelineStage(raw)
    except ValueError:
        valid = ", ".join(s.value for s in models.PipelineStage)
        raise VoiceActionError(f'"{ctx.get("stage")}" isn\'t a pipeline stage. Valid stages: {valid}.')

    old_stage = customer.pipeline_stage
    if old_stage == new_stage:
        return {"customer_id": customer.id, "customer_name": customer.name,
                "new_stage": new_stage.value, "unchanged": True}

    customer.pipeline_stage = new_stage
    # The customers router logs stage changes to the activity timeline; voice
    # does the same, or the timeline would have a hole exactly where someone
    # later asks "who moved this to lost?".
    ctx.db.add(models.CustomerNote(
        company_id=ctx.company_id,
        customer_id=customer.id,
        user_id=ctx.user_id,
        note_type=models.NoteType.STATUS_CHANGE,
        content=f"Stage changed from {old_stage.value} to {new_stage.value} by voice command.",
    ))
    ctx.db.commit()
    return {
        "customer_id": customer.id,
        "customer_name": customer.name,
        "old_stage": old_stage.value if old_stage else None,
        "new_stage": new_stage.value,
    }


# --------------------------------------------------------------------------
# Quotations
# --------------------------------------------------------------------------

def action_draft_quotation(ctx: ActionContext) -> dict:
    """Internal draft only — nothing reaches the customer."""
    customer = _resolve_customer(ctx)
    items = _line_items_from(ctx)

    discount = _money(ctx.get("discount_percent", 0))
    tax = settings.default_tax_rate
    subtotal, total = _totals(items, discount, tax)

    quotation = models.Quotation(
        company_id=ctx.company_id,
        number=_next_number(ctx, models.Quotation, "QUO"),
        customer_id=customer.id,
        status=models.QuotationStatus.DRAFT,
        subtotal=subtotal,
        discount_percent=discount,
        tax_percent=tax,
        total=total,
        currency=settings.default_currency,
        notes=ctx.get("notes", "Drafted from a voice command — review before sending."),
        valid_until=datetime.utcnow() + timedelta(days=30),
    )
    ctx.db.add(quotation)
    ctx.db.flush()

    for item in items:
        line_total = _money(item["quantity"]) * _money(item["unit_price"])
        ctx.db.add(models.QuotationItem(
            quotation_id=quotation.id,
            description=str(item["description"]),
            quantity=_money(item["quantity"]),
            unit_price=_money(item["unit_price"]),
            line_total=line_total,
        ))
    ctx.db.commit()
    ctx.db.refresh(quotation)

    zero_priced = [i["description"] for i in items if _money(i["unit_price"]) == 0]
    return {
        "quotation_id": quotation.id,
        "quotation_number": quotation.number,
        "customer_id": customer.id,
        "customer_name": customer.name,
        "total": quotation.total,
        "currency": quotation.currency,
        # Surfaced because a spoken description often omits prices, and a
        # quotation that says 0.00 should be caught before it's emailed.
        "needs_pricing": zero_priced,
    }


def _find_quotation(ctx: ActionContext):
    number = ctx.get("quotation_number")
    if number:
        quotation = (
            ctx.db.query(models.Quotation)
            .filter(models.Quotation.company_id == ctx.company_id,
                    models.Quotation.number == str(number))
            .first()
        )
        if quotation:
            return quotation
    customer = _resolve_customer(ctx, required=False)
    if customer:
        return (
            ctx.db.query(models.Quotation)
            .filter(models.Quotation.company_id == ctx.company_id,
                    models.Quotation.customer_id == customer.id)
            .order_by(models.Quotation.created_at.desc())
            .first()
        )
    return None


def action_email_quotation(ctx: ActionContext) -> dict:
    quotation = _find_quotation(ctx)
    if not quotation:
        raise VoiceActionError("Couldn't work out which quotation to send — say the customer or the number.")

    customer = ctx.db.get(models.Customer, quotation.customer_id)
    body = ctx.get("body") or (
        f"Hi {customer.name},\n\nPlease find quotation {quotation.number} attached, "
        f"totalling {quotation.currency} {quotation.total:,.2f}.\n\n"
        f"Let me know if you'd like anything adjusted.\n\n{settings.company_name}"
    )
    result = _send_and_log_email(
        ctx, customer=customer,
        subject=f"Quotation {quotation.number}",
        body=body, quotation=quotation, attach_pdf=True,
        follow_up_in_days=ctx.get("follow_up_in_days"),
    )
    return {**result, "quotation_number": quotation.number, "quotation_id": quotation.id}


# --------------------------------------------------------------------------
# Invoices
# --------------------------------------------------------------------------

def action_create_invoice(ctx: ActionContext) -> dict:
    """Internal draft, same posture as draft_quotation: creating the invoice is
    reversible, sending it isn't.

    Building from a quotation is both the common case and the one where spoken
    line items are most likely to be misheard, so it's preferred when a
    quotation number is given.
    """
    customer = _resolve_customer(ctx)

    source_quotation = _find_quotation(ctx) if ctx.get("quotation_number") else None
    if source_quotation is not None:
        items = [
            {"description": i.description, "quantity": i.quantity, "unit_price": i.unit_price}
            for i in source_quotation.items
        ]
        subtotal, total = source_quotation.subtotal, source_quotation.total
        discount, tax = source_quotation.discount_percent, source_quotation.tax_percent
    else:
        items = _line_items_from(ctx)
        discount = _money(ctx.get("discount_percent", 0))
        tax = settings.default_tax_rate
        subtotal, total = _totals(items, discount, tax)

    due_date = _spoken_datetime(ctx, "due_at", "due_date") or (
        datetime.utcnow() + timedelta(days=int(_money(ctx.get("due_in_days", 15)) or 15)))

    invoice = models.Invoice(
        company_id=ctx.company_id,
        number=_next_number(ctx, models.Invoice, "INV"),
        customer_id=customer.id,
        quotation_id=source_quotation.id if source_quotation is not None else None,
        status=models.InvoiceStatus.UNPAID,
        subtotal=subtotal,
        discount_percent=discount,
        tax_percent=tax,
        total=total,
        currency=settings.default_currency,
        due_date=due_date,
        notes=ctx.get("notes", "Created from a voice command — review before sending."),
    )
    ctx.db.add(invoice)
    ctx.db.flush()

    for item in items:
        line_total = _money(item["quantity"]) * _money(item["unit_price"])
        ctx.db.add(models.InvoiceItem(
            invoice_id=invoice.id,
            description=str(item["description"]),
            quantity=_money(item["quantity"]),
            unit_price=_money(item["unit_price"]),
            line_total=line_total,
        ))

    if source_quotation is not None:
        source_quotation.status = models.QuotationStatus.CONVERTED

    ctx.db.commit()
    ctx.db.refresh(invoice)
    return {
        "invoice_id": invoice.id,
        "invoice_number": invoice.number,
        "customer_id": customer.id,
        "customer_name": customer.name,
        "total": invoice.total,
        "currency": invoice.currency,
        "due": voice_time.format_for_user(due_date, ctx.tz_name),
    }


def _find_invoice(ctx: ActionContext, *, unpaid_only: bool = False):
    number = ctx.get("invoice_number")
    if number:
        invoice = (
            ctx.db.query(models.Invoice)
            .filter(models.Invoice.company_id == ctx.company_id,
                    models.Invoice.number == str(number))
            .first()
        )
        if invoice:
            return invoice

    customer = _resolve_customer(ctx, required=False)
    if not customer:
        return None
    query = ctx.db.query(models.Invoice).filter(
        models.Invoice.company_id == ctx.company_id,
        models.Invoice.customer_id == customer.id,
    )
    if unpaid_only:
        query = query.filter(models.Invoice.status != models.InvoiceStatus.PAID)
    return query.order_by(models.Invoice.created_at.desc()).first()


def action_send_invoice(ctx: ActionContext) -> dict:
    invoice = _find_invoice(ctx)
    if not invoice:
        raise VoiceActionError("Couldn't work out which invoice to send — say the customer or the number.")

    customer = ctx.db.get(models.Customer, invoice.customer_id)
    due = f" It's due {voice_time.format_for_user(invoice.due_date, ctx.tz_name)}." if invoice.due_date else ""
    body = ctx.get("body") or (
        f"Hi {customer.name},\n\nPlease find invoice {invoice.number} attached, "
        f"for {invoice.currency} {invoice.total:,.2f}.{due}\n\n"
        f"Thank you,\n{settings.company_name}"
    )
    result = _send_and_log_email(
        ctx, customer=customer,
        subject=f"Invoice {invoice.number}",
        body=body, invoice=invoice, attach_pdf=True,
        follow_up_in_days=ctx.get("follow_up_in_days"),
    )
    return {**result, "invoice_number": invoice.number, "invoice_id": invoice.id}


def action_send_payment_reminder(ctx: ActionContext) -> dict:
    invoice = _find_invoice(ctx, unpaid_only=True) or _find_invoice(ctx)
    if not invoice:
        raise VoiceActionError("Couldn't find an invoice to chase — say the customer or the number.")
    if invoice.status == models.InvoiceStatus.PAID:
        raise VoiceActionError(f"Invoice {invoice.number} is already paid — nothing to chase.")

    customer = ctx.db.get(models.Customer, invoice.customer_id)
    balance = _money(invoice.total - (invoice.amount_paid or 0))
    when = (
        f"was due {voice_time.format_for_user(invoice.due_date, ctx.tz_name)}"
        if invoice.due_date else "is outstanding"
    )
    body = ctx.get("body") or (
        f"Hi {customer.name},\n\nA gentle reminder that invoice {invoice.number} for "
        f"{invoice.currency} {balance:,.2f} {when}.\n\n"
        f"If it's already on its way, please ignore this note.\n\nThank you,\n{settings.company_name}"
    )
    result = _send_and_log_email(
        ctx, customer=customer,
        subject=f"Reminder: invoice {invoice.number}",
        body=body, invoice=invoice, attach_pdf=True,
        follow_up_in_days=ctx.get("follow_up_in_days", 7),
    )
    return {**result, "invoice_number": invoice.number, "balance_due": balance}


def action_record_payment(ctx: ActionContext) -> dict:
    """Recording money is a write to the books, so it's held for a tap even
    though nothing leaves the building. A misheard payment on the wrong invoice
    is quietly corrosive in a way a wrong task isn't."""
    invoice = _find_invoice(ctx)
    if not invoice:
        raise VoiceActionError("Couldn't find that invoice — say the invoice number.")

    balance = _money(invoice.total - (invoice.amount_paid or 0))
    amount = _money(ctx.get("amount") or balance)
    if amount <= 0:
        raise VoiceActionError("Say how much was paid.")
    if amount > balance + 0.01:
        raise VoiceActionError(
            f"That's more than the {invoice.currency} {balance:,.2f} outstanding on {invoice.number}."
        )

    invoice.amount_paid = _money((invoice.amount_paid or 0) + amount)
    invoice.status = (
        models.InvoiceStatus.PAID if invoice.amount_paid >= invoice.total - 0.01
        else models.InvoiceStatus.PARTIALLY_PAID
    )
    ctx.db.commit()
    return {
        "invoice_id": invoice.id,
        "invoice_number": invoice.number,
        "amount": amount,
        "amount_paid": invoice.amount_paid,
        "status": invoice.status.value,
        "currency": invoice.currency,
    }


def action_set_recurring_invoice(ctx: ActionContext) -> dict:
    """Flips an existing invoice into the recurring schedule the recurring
    scheduler already walks, rather than inventing a second mechanism."""
    invoice = _find_invoice(ctx)
    if not invoice:
        raise VoiceActionError("Couldn't find which invoice to repeat — say the customer or the number.")

    interval = str(ctx.get("interval", "monthly")).lower()
    if interval not in _INTERVAL_DAYS:
        raise VoiceActionError("Say how often: weekly, monthly, quarterly or yearly.")

    days = _INTERVAL_DAYS[interval]
    invoice.is_recurring = True
    invoice.recurrence_interval_days = days
    invoice.next_recurrence_at = _spoken_datetime(ctx, "starts_on", "starts_at") or (
        datetime.utcnow() + timedelta(days=days))
    ctx.db.commit()
    return {
        "invoice_id": invoice.id,
        "invoice_number": invoice.number,
        "interval": interval,
        "every_days": days,
        "next_run": voice_time.format_for_user(invoice.next_recurrence_at, ctx.tz_name),
    }


# --------------------------------------------------------------------------
# Email
# --------------------------------------------------------------------------

def action_send_email(ctx: ActionContext) -> dict:
    customer = _resolve_customer(ctx)
    subject = str(ctx.get("subject") or f"A note from {settings.company_name}")
    body = str(ctx.get("body") or "")
    if not body.strip():
        raise VoiceActionError("Didn't catch what the email should say.")
    return _send_and_log_email(
        ctx, customer=customer, subject=subject, body=body,
        follow_up_in_days=ctx.get("follow_up_in_days"),
    )


# --------------------------------------------------------------------------
# Reads — answer a question, write nothing
# --------------------------------------------------------------------------

def action_sales_report(ctx: ActionContext) -> dict:
    """Assembled from rows rather than sent to a model: every number is exact,
    and "how did we do last month" asked five times in a day would otherwise be
    five billed calls for data that hasn't changed."""
    start, end = _period_bounds(ctx.get("period"))

    quotations = (
        ctx.db.query(models.Quotation)
        .filter(models.Quotation.company_id == ctx.company_id,
                models.Quotation.created_at >= start, models.Quotation.created_at < end)
        .all()
    )
    invoices = (
        ctx.db.query(models.Invoice)
        .filter(models.Invoice.company_id == ctx.company_id,
                models.Invoice.created_at >= start, models.Invoice.created_at < end)
        .all()
    )
    won = (
        ctx.db.query(models.Customer)
        .filter(models.Customer.company_id == ctx.company_id,
                models.Customer.pipeline_stage == models.PipelineStage.WON)
        .count()
    )

    return {
        "period": ctx.get("period", "this_month"),
        "from": start.date().isoformat(),
        "to": end.date().isoformat(),
        "currency": settings.default_currency,
        "quotations_count": len(quotations),
        "quotations_value": round(sum(_money(q.total) for q in quotations), 2),
        "invoices_count": len(invoices),
        "invoiced_value": round(sum(_money(i.total) for i in invoices), 2),
        "collected_value": round(sum(_money(i.amount_paid) for i in invoices), 2),
        "customers_won_total": won,
    }


def action_outstanding_invoices(ctx: ActionContext) -> dict:
    query = ctx.db.query(models.Invoice).filter(
        models.Invoice.company_id == ctx.company_id,
        models.Invoice.status != models.InvoiceStatus.PAID,
    )
    customer = _resolve_customer(ctx, required=False)
    if customer:
        query = query.filter(models.Invoice.customer_id == customer.id)
    if ctx.get("overdue_only"):
        query = query.filter(models.Invoice.due_date < datetime.utcnow())

    rows = query.order_by(models.Invoice.due_date.asc()).limit(50).all()
    items = []
    for invoice in rows[:20]:
        owner = ctx.db.get(models.Customer, invoice.customer_id)
        items.append({
            "invoice_number": invoice.number,
            "customer": owner.name if owner else None,
            "balance": round(_money(invoice.total) - _money(invoice.amount_paid), 2),
            "due": voice_time.format_for_user(invoice.due_date, ctx.tz_name),
            "overdue": bool(invoice.due_date and invoice.due_date < datetime.utcnow()),
        })
    return {
        "count": len(rows),
        "total_outstanding": round(
            sum(_money(i.total) - _money(i.amount_paid) for i in rows), 2),
        "currency": settings.default_currency,
        "invoices": items,
    }


def action_customer_summary(ctx: ActionContext) -> dict:
    customer = _resolve_customer(ctx)

    notes = (
        ctx.db.query(models.CustomerNote)
        .filter(models.CustomerNote.customer_id == customer.id)
        .order_by(models.CustomerNote.created_at.desc()).limit(5).all()
    )
    quotations = (
        ctx.db.query(models.Quotation)
        .filter(models.Quotation.customer_id == customer.id)
        .order_by(models.Quotation.created_at.desc()).limit(5).all()
    )
    invoices = (
        ctx.db.query(models.Invoice)
        .filter(models.Invoice.customer_id == customer.id)
        .order_by(models.Invoice.created_at.desc()).limit(10).all()
    )
    open_tasks = (
        ctx.db.query(Task)
        .filter(Task.customer_id == customer.id,
                Task.status.in_([TaskStatus.OPEN, TaskStatus.IN_PROGRESS]))
        .limit(5).all()
    )
    unpaid = [i for i in invoices if i.status != models.InvoiceStatus.PAID]

    return {
        "customer_id": customer.id,
        "customer_name": customer.name,
        "company": customer.company,
        "pipeline_stage": customer.pipeline_stage.value if customer.pipeline_stage else None,
        "email": customer.email,
        "phone": customer.phone,
        "recent_notes": [
            {"content": n.content, "type": n.note_type.value if n.note_type else None,
             "at": n.created_at.isoformat()} for n in notes
        ],
        "recent_quotations": [
            {"number": q.number, "total": _money(q.total), "status": q.status.value}
            for q in quotations
        ],
        "outstanding_count": len(unpaid),
        "outstanding_total": round(
            sum(_money(i.total) - _money(i.amount_paid) for i in unpaid), 2),
        "open_tasks": [
            {"title": t.title, "due": voice_time.format_for_user(t.due_date, ctx.tz_name)}
            for t in open_tasks
        ],
        "currency": settings.default_currency,
    }


def action_my_tasks(ctx: ActionContext) -> dict:
    horizon = datetime.utcnow() + timedelta(days=7)
    tasks = (
        ctx.db.query(Task)
        .filter(Task.company_id == ctx.company_id,
                Task.assigned_to_user_id == ctx.user_id,
                Task.status.in_([TaskStatus.OPEN, TaskStatus.IN_PROGRESS]))
        .order_by(Task.due_date.asc())
        .limit(100).all()
    )
    overdue = [t for t in tasks if t.due_date and t.due_date < datetime.utcnow()]
    soon = [t for t in tasks if t.due_date and t.due_date <= horizon]

    return {
        "open_count": len(tasks),
        "overdue_count": len(overdue),
        "tasks": [
            {
                "title": t.title,
                "due": voice_time.format_for_user(t.due_date, ctx.tz_name),
                "priority": t.priority.value,
                "overdue": bool(t.due_date and t.due_date < datetime.utcnow()),
            }
            for t in (soon or tasks)[:15]
        ],
    }


def action_email_activity_summary(ctx: ActionContext) -> dict:
    """The AI Email Assistant, asked by voice: what went out, what's silent,
    what's waiting on a nudge.

    Costs one model call, metered by the caller. Note what it summarises —
    this app logs outbound mail, so the honest framing is "what you've sent and
    what hasn't come back", not "your inbox".
    """
    from app.voice_summarizer import summarize_email_activity

    start, _ = _period_bounds(ctx.get("period", "last_7_days"))
    query = ctx.db.query(models.EmailMessage).filter(
        models.EmailMessage.company_id == ctx.company_id,
        models.EmailMessage.created_at >= start,
    )
    customer = _resolve_customer(ctx, required=False)
    if customer:
        query = query.filter(models.EmailMessage.customer_id == customer.id)

    messages = query.order_by(models.EmailMessage.created_at.desc()).limit(40).all()
    if not messages:
        return {"count": 0, "summary": "No email activity in that window."}

    digest = []
    for message in messages:
        owner = ctx.db.get(models.Customer, message.customer_id)
        digest.append({
            "customer": owner.name if owner else message.to_email,
            "subject": (message.subject or "")[:140],
            "status": message.status.value if message.status else None,
            "sent_at": message.sent_at.isoformat() if message.sent_at else None,
            "awaiting_followup": bool(
                message.follow_up_status == models.FollowUpStatus.PENDING),
            "snippet": (message.body or "")[:300],
        })

    summary = summarize_email_activity(digest, locale=ctx.locale)
    return {"count": len(messages), **summary}


def action_ask_documents(ctx: ActionContext) -> dict:
    """The `ask_documents` intent the product spec calls for: search the
    Company Knowledge Base (document_store.py) and answer from what's there,
    never from the model's general knowledge. A company with nothing
    uploaded gets told that plainly rather than a hallucinated policy."""
    from app import document_store

    question = str(ctx.get("question") or "").strip()
    if not question:
        raise VoiceActionError("Didn't catch what to ask the documents.")

    document_id = None
    title = str(ctx.get("document_title") or "").strip()
    if title:
        from app.document_models import Document
        match = (
            ctx.db.query(Document)
            .filter(Document.company_id == ctx.company_id, Document.title.ilike(f"%{title}%"))
            .first()
        )
        document_id = match.id if match else None

    result = document_store.answer_question(ctx.db, ctx.company_id, question, document_id=document_id)
    return {
        "question": question,
        "answer": result.get("answer"),
        "mode": result.get("mode"),
        "sources": [
            {"document_title": s["document_title"], "excerpt": s["content"][:300]}
            for s in result.get("sources", [])
        ],
    }


# --------------------------------------------------------------------------
# Delegation
# --------------------------------------------------------------------------

def action_ask_ai_employee(ctx: ActionContext) -> dict:
    """Hands the brief to the specialist employees module, so "ask the stock
    controller what's running low" works from the mic without this module
    knowing anything about inventory.

    Held behind a confirmation because transcription adds one more place a word
    can be misheard before it reaches an action that may well be ALWAYS_CONFIRM
    on the employee side. The employee's own gate still applies after this.
    """
    from app.ai_employee_registry import EMPLOYEE_CATALOG

    brief = ctx.get("brief") or ctx.get("content")
    if not brief:
        raise VoiceActionError("Didn't catch what to ask.")

    employee_key = ctx.get("employee_key")
    if not employee_key:
        spoken = str(ctx.get("employee") or brief).lower()
        for key, info in EMPLOYEE_CATALOG.items():
            if key.replace("_", " ") in spoken or info["label"].lower() in spoken:
                employee_key = key
                break
    if not employee_key or employee_key not in EMPLOYEE_CATALOG:
        raise VoiceActionError(
            "Say which colleague — " + ", ".join(
                info["label"] for info in list(EMPLOYEE_CATALOG.values())[:5]) + "."
        )

    return {
        "employee_key": employee_key,
        "employee_label": EMPLOYEE_CATALOG[employee_key]["label"],
        "brief": str(brief),
        "delegated": True,
        # The employee run is created by the router, which already owns the
        # plan/confirm/execute cycle for employees; duplicating it here would
        # mean two code paths that have to stay in sync.
        "next": "open_ai_employee",
    }


# --------------------------------------------------------------------------
# Registry and safety classification
# --------------------------------------------------------------------------

VOICE_ACTION_REGISTRY: dict[str, Callable[[ActionContext], dict]] = {
    "create_task": action_create_task,
    "complete_task": action_complete_task,
    "schedule_followup": action_schedule_followup,
    "create_customer": action_create_customer,
    "add_customer_note": action_add_customer_note,
    "change_pipeline_stage": action_change_pipeline_stage,
    "draft_quotation": action_draft_quotation,
    "email_quotation": action_email_quotation,
    "create_invoice": action_create_invoice,
    "send_invoice": action_send_invoice,
    "send_payment_reminder": action_send_payment_reminder,
    "record_payment": action_record_payment,
    "set_recurring_invoice": action_set_recurring_invoice,
    "send_email": action_send_email,
    "sales_report": action_sales_report,
    "outstanding_invoices": action_outstanding_invoices,
    "customer_summary": action_customer_summary,
    "my_tasks": action_my_tasks,
    "email_activity_summary": action_email_activity_summary,
    "ask_documents": action_ask_documents,
    "ask_ai_employee": action_ask_ai_employee,
}

# Questions. Nothing is written, so a confirmation tap would be pure friction.
READ_ONLY_INTENTS: set[str] = {
    "sales_report", "outstanding_invoices", "customer_summary", "my_tasks",
    "email_activity_summary", "ask_documents",
}

# Internal, reversible, nothing leaves the company -> runs on parse.
AUTO_EXECUTE: set[str] = READ_ONLY_INTENTS | {
    "create_task", "complete_task", "schedule_followup", "create_customer",
    "add_customer_note", "change_pipeline_stage", "draft_quotation", "create_invoice",
}

# Reaches a customer, moves money, or delegates -> held for a human tap.
CONFIRM_REQUIRED: set[str] = {
    "email_quotation", "send_invoice", "send_payment_reminder", "send_email",
    "record_payment", "set_recurring_invoice", "ask_ai_employee",
}


def requires_confirmation(intent: str) -> bool:
    """One place to read, one place to audit. Anything unknown defaults to True —
    an unclassified action must never slip through as auto."""
    if intent in CONFIRM_REQUIRED:
        return True
    return intent not in AUTO_EXECUTE


def _validate_registry() -> None:
    """Import-time guard, same idea as the AI employees module: a registered
    action that's unclassified, or missing from the catalog or the permission
    map, fails the app at boot rather than misbehaving in production."""
    from app.voice_intent import INTENT_CATALOG
    from app.voice_permissions import INTENT_PERMISSIONS

    problems = []
    for intent in VOICE_ACTION_REGISTRY:
        if intent not in AUTO_EXECUTE and intent not in CONFIRM_REQUIRED:
            problems.append(f"{intent}: not classified AUTO_EXECUTE or CONFIRM_REQUIRED")
        if intent not in INTENT_CATALOG:
            problems.append(f"{intent}: missing from voice_intent.INTENT_CATALOG")
        if intent not in INTENT_PERMISSIONS:
            problems.append(f"{intent}: missing from voice_permissions.INTENT_PERMISSIONS")
    overlap = AUTO_EXECUTE & CONFIRM_REQUIRED
    if overlap:
        problems.append(f"in both safety sets: {sorted(overlap)}")
    if problems:
        raise AssertionError("voice_actions registry is inconsistent:\n  " + "\n  ".join(problems))


_validate_registry()
