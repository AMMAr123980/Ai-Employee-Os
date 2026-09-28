"""
Follow-up Scheduler — the "AI reminders" / "remind me if he doesn't reply within
three days" feature from the product spec.

Runs as an in-process background job (APScheduler) inside the same FastAPI process
— no separate worker or terminal needed. Every `FOLLOWUP_CHECK_INTERVAL_MINUTES`,
it looks for sent emails whose `follow_up_at` has passed and that haven't been
processed yet, and creates a new DRAFT EmailMessage (an AI-written nudge) linked
back to the original via `parent_email_id`. It never sends automatically — a human
reviews and sends from the Follow-ups page.
"""
import logging
from datetime import datetime
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler

from app.database import SessionLocal
from app import models, email_assistant
from app.config import settings

logger = logging.getLogger(__name__)

_scheduler: Optional[BackgroundScheduler] = None


def check_and_create_followups(company_id: Optional[str] = None) -> int:
    """Finds overdue pending follow-ups and drafts a nudge for each. If company_id
    is given, only that company's emails are processed (used by the manual
    "check now" endpoint); otherwise all companies are processed (used by the
    periodic background job). Returns the number of drafts created."""
    db = SessionLocal()
    created = 0
    try:
        query = db.query(models.EmailMessage).filter(
            models.EmailMessage.follow_up_status == models.FollowUpStatus.PENDING,
            models.EmailMessage.follow_up_at <= datetime.utcnow(),
        )
        if company_id:
            query = query.filter(models.EmailMessage.company_id == company_id)

        due = query.all()
        for original in due:
            try:
                customer = db.get(models.Customer, original.customer_id)
                if not customer:
                    original.follow_up_status = models.FollowUpStatus.DONE
                    continue

                company = db.get(models.Company, original.company_id)
                days_since = max((datetime.utcnow() - original.sent_at).days, 1) if original.sent_at else 1

                draft = email_assistant.draft_followup_email(
                    customer_name=customer.name,
                    company_name=company.name if company else settings.company_name,
                    original_subject=original.subject,
                    original_body=original.body,
                    days_since=days_since,
                )

                db.add(models.EmailMessage(
                    company_id=original.company_id,
                    user_id=original.user_id,
                    customer_id=original.customer_id,
                    quotation_id=original.quotation_id,
                    invoice_id=original.invoice_id,
                    parent_email_id=original.id,
                    to_email=original.to_email,
                    subject=draft["subject"],
                    body=draft["body"],
                    status=models.EmailStatus.DRAFT,
                    auto_generated=True,
                ))
                original.follow_up_status = models.FollowUpStatus.DONE
                created += 1
            except Exception:
                logger.exception("Failed to draft follow-up for email %s", original.id)
                # Mark it done anyway so a persistently-failing row doesn't get
                # retried forever on every tick; the original email is still
                # visible in the customer's activity timeline either way.
                original.follow_up_status = models.FollowUpStatus.DONE

        db.commit()
    finally:
        db.close()

    if created:
        logger.info("Follow-up scheduler created %d draft(s)", created)
    return created


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return  # already running — avoid double-starting under --reload
    _scheduler = BackgroundScheduler(daemon=True)
    _scheduler.add_job(
        check_and_create_followups,
        "interval",
        minutes=settings.followup_check_interval_minutes,
        id="followup_check",
        next_run_time=datetime.utcnow(),  # run once immediately, then on interval
    )
    _scheduler.start()
    logger.info(
        "Follow-up scheduler started (checking every %d minute(s))",
        settings.followup_check_interval_minutes,
    )


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
