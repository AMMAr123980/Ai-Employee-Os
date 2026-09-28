"""
"...and remind me if they don't reply within three days."

This is the half of the flagship example a dated reminder can't express. A task
fires on its due date whether or not the customer replied; a follow-up fires
only if the thing you were waiting for still hasn't happened.

    VoiceFollowup(condition_type="no_reply", due_at=<+3 days>)
        -> sweep runs
        -> customer got in touch?  -> RESOLVED, nobody is nagged
        -> still silent?           -> FIRED, a Task appears in your queue

`CONDITION_CHECKERS` is a closed dict on purpose. A free-text condition would
have to be evaluated by a model at fire time, and a model that misreads "has he
paid?" produces a dunning reminder about a customer who paid last week. An
unknown condition is rejected when the follow-up is created
(voice_actions.action_schedule_followup), never defaulted to "fire".

Each checker answers "did the thing we were waiting for happen?", not "should we
fire?". Framed that way, an exception inside a checker can safely be treated as
"not resolved": the worst case is a reminder you didn't need, instead of a chase
that silently never happens. That asymmetry is the whole reason for the framing.

Note what this is *not*: it never emails the customer. Firing a message at a
customer from an unattended sweep, days after a spoken command, with nobody
looking, is exactly what the confirmation gate exists to prevent. It creates a
task; a human sends.

No new scheduler — `sweep_followups()` hangs off the APScheduler tick that
already runs the email follow-up job (followup_scheduler.py).
"""
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Callable, Optional

from sqlalchemy.orm import Session

from app import models
from app.task_models import Task, TaskPriority, TaskSource
from app.voice_models import FollowupStatus, VoiceFollowup

logger = logging.getLogger(__name__)


def _config(followup: VoiceFollowup) -> dict[str, Any]:
    if not followup.condition_config_json:
        return {}
    try:
        return json.loads(followup.condition_config_json)
    except json.JSONDecodeError:
        return {}


def _check_no_reply(db: Session, followup: VoiceFollowup) -> tuple[bool, Optional[str]]:
    """Resolved if there's been contact with this customer since the follow-up
    was set.

    This app logs outbound email rather than inbound, so a literal "did they
    reply" isn't available. What is available is just as good in practice: a
    logged note, a call or meeting recorded on the timeline. If someone wrote
    "spoke to him, all good", chasing is noise.
    """
    if not followup.customer_id:
        return False, None
    since = followup.created_at or (datetime.utcnow() - timedelta(days=30))

    note = (
        db.query(models.CustomerNote)
        .filter(models.CustomerNote.customer_id == followup.customer_id,
                models.CustomerNote.created_at >= since,
                models.CustomerNote.note_type.in_([
                    models.NoteType.NOTE, models.NoteType.CALL, models.NoteType.MEETING,
                ]))
        .first()
    )
    if note:
        return True, "Contact was logged on the account since."

    # A quotation being approved, or an invoice being raised, is also a reply in
    # every sense that matters.
    approved = (
        db.query(models.Quotation)
        .filter(models.Quotation.customer_id == followup.customer_id,
                models.Quotation.updated_at >= since,
                models.Quotation.status.in_([
                    models.QuotationStatus.APPROVED, models.QuotationStatus.CONVERTED,
                ]))
        .first()
    )
    if approved:
        return True, f"Quotation {approved.number} was {approved.status.value}."
    return False, None


def _check_no_payment(db: Session, followup: VoiceFollowup) -> tuple[bool, Optional[str]]:
    number = _config(followup).get("invoice_number")
    query = db.query(models.Invoice).filter(models.Invoice.company_id == followup.company_id)
    if number:
        query = query.filter(models.Invoice.number == str(number))
    elif followup.customer_id:
        query = query.filter(models.Invoice.customer_id == followup.customer_id)
    else:
        return False, None

    invoices = query.order_by(models.Invoice.created_at.desc()).limit(5).all()
    if invoices and all(i.status == models.InvoiceStatus.PAID for i in invoices):
        return True, "Invoice was paid."
    return False, None


def _check_always(db: Session, followup: VoiceFollowup) -> tuple[bool, Optional[str]]:
    """An unconditional reminder, kept so the planner has something to emit for
    "remind me on Friday regardless"."""
    return False, None


CONDITION_CHECKERS: dict[str, Callable[[Session, VoiceFollowup], tuple[bool, Optional[str]]]] = {
    "no_reply": _check_no_reply,
    "no_payment": _check_no_payment,
    "always": _check_always,
}


def _fire(db: Session, followup: VoiceFollowup) -> Optional[str]:
    task = Task(
        company_id=followup.company_id,
        created_by_user_id=followup.user_id,
        assigned_to_user_id=followup.user_id,
        customer_id=followup.customer_id,
        title=followup.reminder_title,
        description=(
            "Created by a conditional voice follow-up: the thing you were waiting for "
            "hasn't happened yet."
        ),
        priority=TaskPriority.HIGH,
        due_date=datetime.utcnow(),
        source=TaskSource.FOLLOWUP,
        source_ref=followup.id,
    )
    db.add(task)
    db.flush()
    return task.id


def sweep_followups(db: Session, *, company_id: Optional[str] = None,
                    limit: int = 200, now: Optional[datetime] = None) -> dict:
    """Evaluate every follow-up whose deadline has arrived.

    Commits once at the end rather than per row: a sweep that dies halfway
    should have done everything or nothing, so a retry can't create duplicate
    reminders.
    """
    now = now or datetime.utcnow()
    query = db.query(VoiceFollowup).filter(
        VoiceFollowup.status == FollowupStatus.WAITING,
        VoiceFollowup.due_at <= now,
    )
    if company_id:
        query = query.filter(VoiceFollowup.company_id == company_id)
    due = query.order_by(VoiceFollowup.due_at.asc()).limit(limit).all()

    fired = resolved = errors = 0
    for followup in due:
        checker = CONDITION_CHECKERS.get(followup.condition_type)
        try:
            is_resolved, reason = checker(db, followup) if checker else (False, None)
        except Exception:
            # Deliberate: an unreadable condition means "not resolved", so a
            # human gets told. See the module docstring.
            logger.exception("Follow-up %s condition check failed", followup.id)
            is_resolved, reason, = False, None
            errors += 1

        followup.checked_at = now
        if is_resolved:
            followup.status = FollowupStatus.RESOLVED
            followup.resolved_reason = reason
            resolved += 1
        else:
            followup.fired_task_id = _fire(db, followup)
            followup.status = FollowupStatus.FIRED
            fired += 1

    db.commit()
    if due:
        logger.info("Voice follow-up sweep: %d fired, %d resolved, %d check errors",
                    fired, resolved, errors)
    return {"checked": len(due), "fired": fired, "resolved": resolved, "errors": errors}


def cancel_followups_for_command(db: Session, command_id: str) -> int:
    """If a command is discarded before its steps run, its pending follow-ups go
    with it — otherwise a cancelled plan still nags you in three days."""
    rows = (
        db.query(VoiceFollowup)
        .filter(VoiceFollowup.voice_command_id == command_id,
                VoiceFollowup.status == FollowupStatus.WAITING)
        .all()
    )
    for row in rows:
        row.status = FollowupStatus.CANCELLED
    db.commit()
    return len(rows)
