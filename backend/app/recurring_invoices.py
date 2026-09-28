"""
Recurring Invoice Scheduler — generalizes the same APScheduler pattern used by
the Follow-up Scheduler. Unlike follow-up nudges (which are AI-drafted and could
be wrong, so they wait for human review), a recurring invoice is a deterministic
copy of numbers that already exist — so it's created directly as a real, ready
to send invoice rather than sitting in a review queue. It's logged to the
customer's activity timeline either way, so it's never a silent surprise.
"""
import logging
from datetime import datetime, timedelta
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler

from app.database import SessionLocal
from app import models
from app.config import settings

logger = logging.getLogger(__name__)

_scheduler: Optional[BackgroundScheduler] = None

DEFAULT_NET_TERMS_DAYS = 14  # due date offset for auto-generated occurrences


def _next_invoice_number(db, company_id: str) -> str:
    count = db.query(models.Invoice).filter(models.Invoice.company_id == company_id).count() + 1
    return f"INV-{count:06d}"


def _template_owner(db, template) -> str:
    """CustomerNote requires a user_id. Attribute auto-generated notes to the
    company's first user (typically the owner) since there's no "system" user
    concept yet."""
    first_user = (
        db.query(models.User)
        .filter(models.User.company_id == template.company_id)
        .order_by(models.User.created_at.asc())
        .first()
    )
    return first_user.id if first_user else ""


def generate_due_recurring_invoices(company_id: Optional[str] = None) -> int:
    """Finds recurring invoice templates whose next occurrence is due and
    generates it as a new, real invoice (copying items, discount, tax, currency).
    If company_id is given, only that company is processed (manual "check now"
    trigger); otherwise all companies are processed (periodic background job).
    Returns the number of invoices generated."""
    db = SessionLocal()
    created = 0
    try:
        query = db.query(models.Invoice).filter(
            models.Invoice.is_recurring == True,  # noqa: E712
            models.Invoice.next_recurrence_at.isnot(None),
            models.Invoice.next_recurrence_at <= datetime.utcnow(),
        )
        if company_id:
            query = query.filter(models.Invoice.company_id == company_id)

        due_templates = query.all()
        for template in due_templates:
            try:
                new_invoice = models.Invoice(
                    company_id=template.company_id,
                    number=_next_invoice_number(db, template.company_id),
                    customer_id=template.customer_id,
                    recurrence_parent_id=template.id,
                    subtotal=template.subtotal,
                    discount_percent=template.discount_percent,
                    tax_percent=template.tax_percent,
                    total=template.total,
                    currency=template.currency,
                    notes=template.notes,
                    due_date=datetime.utcnow() + timedelta(days=DEFAULT_NET_TERMS_DAYS),
                    is_recurring=False,  # each generated occurrence is a one-off invoice
                )
                db.add(new_invoice)
                db.flush()

                for item in template.items:
                    db.add(models.InvoiceItem(
                        invoice_id=new_invoice.id,
                        description=item.description,
                        quantity=item.quantity,
                        unit_price=item.unit_price,
                        line_total=item.line_total,
                    ))

                db.add(models.CustomerNote(
                    company_id=template.company_id,
                    customer_id=template.customer_id,
                    user_id=_template_owner(db, template),
                    note_type=models.NoteType.NOTE,
                    content=(
                        f"Recurring invoice {new_invoice.number} auto-generated "
                        f"(from {template.number}), {new_invoice.currency} {new_invoice.total:,.2f} due "
                        f"{new_invoice.due_date.strftime('%d %b %Y')}."
                    ),
                ))

                # Advance the template to its next occurrence
                template.next_recurrence_at = datetime.utcnow() + timedelta(
                    days=template.recurrence_interval_days
                )
                created += 1
            except Exception:
                logger.exception("Failed to generate recurring invoice from template %s", template.id)
                # Push the template's next check forward a day so a persistent
                # failure doesn't retry every tick forever.
                template.next_recurrence_at = datetime.utcnow() + timedelta(days=1)

        db.commit()
    finally:
        db.close()

    if created:
        logger.info("Recurring invoice scheduler generated %d invoice(s)", created)
    return created


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return  # already running — avoid double-starting under --reload
    _scheduler = BackgroundScheduler(daemon=True)
    _scheduler.add_job(
        generate_due_recurring_invoices,
        "interval",
        minutes=settings.recurring_invoice_check_interval_minutes,
        id="recurring_invoice_check",
        next_run_time=datetime.utcnow(),  # run once immediately, then on interval
    )
    _scheduler.start()
    logger.info(
        "Recurring invoice scheduler started (checking every %s minute(s))",
        settings.recurring_invoice_check_interval_minutes,
    )


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
