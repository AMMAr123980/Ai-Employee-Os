"""
Conditional follow-ups.

"Remind me if they don't reply in three days" must not remind you when they did.
Both directions are tested, plus the deliberate choice that an unreadable
condition fires rather than going silent.
"""
from datetime import datetime, timedelta

from app import models, voice_followups
from app.task_models import Task
from app.voice_models import FollowupStatus, VoiceFollowup


def _followup(db, company, user, customer, **kwargs):
    row = VoiceFollowup(
        company_id=company.id,
        user_id=user.id,
        customer_id=customer.id,
        condition_type=kwargs.pop("condition_type", "no_reply"),
        reminder_title="Chase Acme",
        due_at=datetime.utcnow() - timedelta(minutes=1),
        created_at=datetime.utcnow() - timedelta(days=3),
        status=FollowupStatus.WAITING,
        **kwargs,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_silence_fires_a_reminder_task(db, company, user, customer):
    row = _followup(db, company, user, customer)
    result = voice_followups.sweep_followups(db)

    assert result["fired"] == 1
    db.refresh(row)
    assert row.status == FollowupStatus.FIRED
    assert db.get(Task, row.fired_task_id).title == "Chase Acme"


def test_logged_contact_resolves_it_without_nagging(db, company, user, customer):
    row = _followup(db, company, user, customer)
    db.add(models.CustomerNote(
        company_id=company.id, customer_id=customer.id, user_id=user.id,
        note_type=models.NoteType.CALL, content="Spoke to them, all good"))
    db.commit()

    result = voice_followups.sweep_followups(db)
    assert result["resolved"] == 1 and result["fired"] == 0
    db.refresh(row)
    assert row.status == FollowupStatus.RESOLVED and row.resolved_reason


def test_a_paid_invoice_resolves_a_payment_chase(db, company, user, customer):
    db.add(models.Invoice(
        company_id=company.id, number="INV-000009", customer_id=customer.id,
        subtotal=100, total=100, amount_paid=100, status=models.InvoiceStatus.PAID))
    db.commit()

    row = _followup(db, company, user, customer, condition_type="no_payment")
    voice_followups.sweep_followups(db)
    db.refresh(row)
    assert row.status == FollowupStatus.RESOLVED


def test_one_that_is_not_due_yet_is_left_alone(db, company, user, customer):
    row = _followup(db, company, user, customer)
    row.due_at = datetime.utcnow() + timedelta(days=1)
    db.commit()

    assert voice_followups.sweep_followups(db)["checked"] == 0
    db.refresh(row)
    assert row.status == FollowupStatus.WAITING


def test_a_broken_checker_fires_rather_than_going_silent(db, company, user, customer, monkeypatch):
    row = _followup(db, company, user, customer)

    def _explode(db_, followup):
        raise RuntimeError("checker is broken")

    monkeypatch.setitem(voice_followups.CONDITION_CHECKERS, "no_reply", _explode)
    result = voice_followups.sweep_followups(db)

    assert result["errors"] == 1 and result["fired"] == 1
    db.refresh(row)
    assert row.status == FollowupStatus.FIRED


def test_cancelling_a_command_cancels_its_pending_followups(db, company, user, customer):
    from app.voice_models import VoiceCommand, VoiceCommandSource, VoiceCommandStatus

    command = VoiceCommand(company_id=company.id, user_id=user.id,
                           source=VoiceCommandSource.TEXT, transcript="x",
                           status=VoiceCommandStatus.AWAITING_CONFIRMATION)
    db.add(command)
    db.commit()

    row = _followup(db, company, user, customer, voice_command_id=command.id)
    assert voice_followups.cancel_followups_for_command(db, command.id) == 1
    db.refresh(row)
    assert row.status == FollowupStatus.CANCELLED
