"""
Step plumbing, the safety classification, and the actions that touch real rows.

The registry assertion is the one to watch: it's what stops a newly added action
from defaulting to "runs without asking".
"""
from datetime import datetime

import pytest

from app import models, voice_actions
from app.task_models import Task, TaskStatus
from app.voice_actions import ActionContext, VoiceActionError, resolve_step_config


def _ctx(db, company, user, **config):
    return ActionContext(
        db=db, company_id=company.id, user_id=user.id,
        config=config, tz_name="Asia/Karachi",
    )


# ---- $prev references ----------------------------------------------------

def test_prev_reference_resolves_from_an_earlier_step():
    config = resolve_step_config(
        {"quotation_number": "$prev.quotation_number", "customer_name": "Acme"},
        {"quotation_number": "QUO-000007", "total": 125000},
    )
    assert config["quotation_number"] == "QUO-000007"
    assert config["customer_name"] == "Acme"


def test_prev_reference_is_case_insensitive_and_nested():
    config = resolve_step_config(
        {"outer": {"inner": ["$prev.Invoice_Number"]}}, {"invoice_number": "INV-000001"})
    assert config["outer"]["inner"][0] == "INV-000001"


def test_unresolvable_reference_fails_loudly_rather_than_sending_nothing():
    with pytest.raises(VoiceActionError) as exc:
        resolve_step_config({"quotation_number": "$prev.quotation_number"}, {})
    assert "quotation_number" in str(exc.value)


# ---- safety classification ----------------------------------------------

def test_customer_facing_and_money_actions_require_confirmation():
    for intent in ("send_email", "email_quotation", "send_invoice",
                   "send_payment_reminder", "record_payment", "set_recurring_invoice"):
        assert voice_actions.requires_confirmation(intent), intent


def test_internal_and_read_actions_do_not():
    for intent in ("create_task", "add_customer_note", "draft_quotation",
                   "create_invoice", "sales_report", "my_tasks"):
        assert not voice_actions.requires_confirmation(intent), intent


def test_an_unknown_action_defaults_to_requiring_confirmation():
    assert voice_actions.requires_confirmation("something_new_and_unclassified")


def test_reads_are_a_subset_of_auto_execute():
    assert voice_actions.READ_ONLY_INTENTS <= voice_actions.AUTO_EXECUTE


def test_safety_sets_do_not_overlap():
    assert not (voice_actions.AUTO_EXECUTE & voice_actions.CONFIRM_REQUIRED)


def test_registry_validation_catches_an_unclassified_action(monkeypatch):
    monkeypatch.setitem(voice_actions.VOICE_ACTION_REGISTRY, "rogue_action", lambda ctx: {})
    with pytest.raises(AssertionError) as exc:
        voice_actions._validate_registry()
    assert "rogue_action" in str(exc.value)


# ---- actions against real rows ------------------------------------------

def test_create_task_stores_utc_but_shows_local(db, company, user):
    result = voice_actions.action_create_task(
        _ctx(db, company, user, title="Call Acme", due_at="2026-09-18T15:00"))

    task = db.get(Task, result["task_id"])
    assert task.due_date == datetime(2026, 9, 18, 10, 0)   # 15:00 PKT -> 10:00 UTC
    assert "15:00" in result["due"]                        # shown back as spoken


def test_ambiguous_customer_name_refuses_rather_than_guessing(db, company, user):
    db.add_all([
        models.Customer(company_id=company.id, name="Acme Corp"),
        models.Customer(company_id=company.id, name="Acme Industries"),
    ])
    db.commit()

    with pytest.raises(VoiceActionError) as exc:
        voice_actions.action_add_customer_note(
            _ctx(db, company, user, customer_name="Acme", content="note"))
    assert "more than one" in str(exc.value).lower()


def test_exact_match_wins_over_ambiguity(db, company, user):
    exact = models.Customer(company_id=company.id, name="Acme")
    db.add_all([exact, models.Customer(company_id=company.id, name="Acme Industries")])
    db.commit()

    result = voice_actions.action_add_customer_note(
        _ctx(db, company, user, customer_name="Acme", content="note"))
    assert result["customer_id"] == exact.id


def test_errors_come_back_in_the_language_that_was_spoken(db, company, user):
    ctx = ActionContext(db=db, company_id=company.id, user_id=user.id,
                        config={"content": "note"}, locale="ur")
    with pytest.raises(VoiceActionError) as exc:
        voice_actions.action_add_customer_note(ctx)
    assert str(exc.value) == ctx.t("no_customer_named")


def test_pipeline_change_logs_to_the_activity_timeline(db, company, user, customer):
    voice_actions.action_change_pipeline_stage(
        _ctx(db, company, user, customer_name="Acme Corp", stage="negotiation"))

    db.refresh(customer)
    assert customer.pipeline_stage == models.PipelineStage.NEGOTIATION
    note = (
        db.query(models.CustomerNote)
        .filter(models.CustomerNote.customer_id == customer.id)
        .first()
    )
    assert note is not None and note.note_type == models.NoteType.STATUS_CHANGE


def test_an_invented_pipeline_stage_is_refused_with_the_valid_list(db, company, user, customer):
    with pytest.raises(VoiceActionError) as exc:
        voice_actions.action_change_pipeline_stage(
            _ctx(db, company, user, customer_name="Acme Corp", stage="nearly sold"))
    assert "negotiation" in str(exc.value)


def test_recording_a_payment_marks_the_invoice_paid(db, company, user, customer):
    invoice = models.Invoice(
        company_id=company.id, number="INV-000001", customer_id=customer.id,
        subtotal=1000, total=1000, currency="PKR",
    )
    db.add(invoice)
    db.commit()

    result = voice_actions.action_record_payment(
        _ctx(db, company, user, invoice_number="INV-000001"))

    assert result["status"] == models.InvoiceStatus.PAID.value
    db.refresh(invoice)
    assert invoice.amount_paid == 1000


def test_overpaying_is_refused(db, company, user, customer):
    db.add(models.Invoice(
        company_id=company.id, number="INV-000002", customer_id=customer.id,
        subtotal=500, total=500, currency="PKR"))
    db.commit()

    with pytest.raises(VoiceActionError) as exc:
        voice_actions.action_record_payment(
            _ctx(db, company, user, invoice_number="INV-000002", amount=900))
    assert "outstanding" in str(exc.value)


def test_completing_a_task_by_name(db, company, user):
    created = voice_actions.action_create_task(_ctx(db, company, user, title="Call the supplier"))
    voice_actions.action_complete_task(_ctx(db, company, user, title="supplier"))

    task = db.get(Task, created["task_id"])
    assert task.status == TaskStatus.DONE and task.completed_at is not None
