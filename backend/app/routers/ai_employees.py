"""
One router for every AI employee — see ai_employee_models.py's docstring for
why there isn't one per department.

The request flow is the same shape as routers/voice_commands.py, and
intentionally so: plan -> classify -> gate -> execute or hold -> log. If you
know that file, the only genuinely new step here is the ownership check in
`submit_brief` (`employee_owns_intent`), which is what keeps departments
from bleeding into each other.
"""
import json
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import get_current_user
from app import models
from app import ai_employee_schemas as schemas
from app import ai_employee_brain as brain
from app.ai_employee_actions import (
    EMPLOYEE_ACTION_REGISTRY, EmployeeActionError, requires_confirmation,
)
from app.ai_employee_models import (
    AIEmployeeConfig, AIEmployeeRun, AIEmployeeRunStatus, AIEmployeeRunTrigger,
)
from app.ai_employee_registry import (
    DUTIES, EMPLOYEE_CATALOG, employee_owns_intent, get_employee,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai-employees", tags=["ai-employees"])

# Below this, a plan is held for a human even if its intent is in
# AUTO_EXECUTE. The model's own confidence is a weak signal, so this is set
# low deliberately — it's a floor against obvious guesses, not a quality bar.
MIN_AUTO_CONFIDENCE = 0.45


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _out(run: AIEmployeeRun) -> schemas.AIEmployeeRunOut:
    return schemas.AIEmployeeRunOut(
        id=run.id,
        employee_key=run.employee_key,
        trigger=run.trigger,
        brief=run.brief,
        intent=run.intent,
        confidence=run.confidence,
        action=json.loads(run.action_json) if run.action_json else None,
        summary=run.summary,
        missing_info=json.loads(run.missing_info_json) if run.missing_info_json else [],
        status=run.status,
        result=json.loads(run.result_json) if run.result_json else None,
        error=run.error,
        created_at=run.created_at,
        executed_at=run.executed_at,
    )


def _config(db: Session, company_id: str, employee_key: str) -> AIEmployeeConfig | None:
    return (
        db.query(AIEmployeeConfig)
        .filter(AIEmployeeConfig.company_id == company_id,
                AIEmployeeConfig.employee_key == employee_key)
        .first()
    )


def _check_employee(db: Session, company_id: str, employee_key: str) -> dict:
    try:
        employee = get_employee(employee_key)
    except KeyError:
        raise HTTPException(404, f"No such AI employee: {employee_key}")
    config = _config(db, company_id, employee_key)
    if config and not config.enabled:
        raise HTTPException(403, f"{employee['label']} is switched off for this company")
    return employee


def _planning_context(db: Session, company_id: str, employee_key: str) -> dict:
    """Existing record names, so the planner matches "Zenith" to the supplier
    that exists rather than inventing a new one. Scoped per employee — the HR
    planner has no business seeing the supplier list, and a smaller context
    is a more accurate one.

    Capped at 100 names each: past that the prompt gets long enough to hurt
    extraction accuracy, and a company with 500 suppliers needs a search box,
    not a bigger prompt.
    """
    from app.ai_employee_models import Campaign, Employee, InventoryItem, PurchaseOrder, Supplier

    def names(model, field="name", limit=100, **filters):
        query = db.query(model).filter(model.company_id == company_id)
        for key, value in filters.items():
            query = query.filter(getattr(model, key) == value)
        return [getattr(row, field) for row in query.limit(limit).all()]

    if employee_key == "hr_officer":
        return {"employees": names(Employee, "full_name")}
    if employee_key == "procurement_officer":
        return {
            "suppliers": names(Supplier),
            "open_purchase_orders": names(PurchaseOrder, "number", limit=30),
            "stock_items": names(InventoryItem, limit=50),
        }
    if employee_key == "inventory_controller":
        return {"stock_items": names(InventoryItem), "suppliers": names(Supplier, limit=30)}
    if employee_key == "marketing_executive":
        return {"campaigns": names(Campaign, limit=30)}
    if employee_key == "legal_assistant":
        from app.ai_employee_models import Contract
        return {"contracts": names(Contract, "title", limit=50)}
    if employee_key in ("bookkeeper", "support_agent"):
        return {"customers": names(models.Customer, limit=100)}
    return {}


def _execute(db: Session, run: AIEmployeeRun, user: models.User, config: dict) -> None:
    handler = EMPLOYEE_ACTION_REGISTRY.get(run.intent)
    if handler is None:
        run.status = AIEmployeeRunStatus.FAILED
        run.error = f"No handler registered for: {run.intent}"
        db.commit()
        return
    try:
        result = handler(db, user.company_id, user.id, config)
        run.status = AIEmployeeRunStatus.EXECUTED
        run.result_json = json.dumps(result, default=str)
        run.executed_at = datetime.utcnow()
    except EmployeeActionError as exc:
        run.status = AIEmployeeRunStatus.FAILED
        run.error = str(exc)
    except brain.EmployeeBrainError as exc:
        run.status = AIEmployeeRunStatus.FAILED
        run.error = str(exc)
    except Exception:
        # A broken action must never surface as a 500 — the run row is the
        # user-visible record of what happened, so the failure belongs in it.
        logger.exception("AI employee run %s failed during execution", run.id)
        db.rollback()
        run.status = AIEmployeeRunStatus.FAILED
        run.error = "Something went wrong running that. Try again, or do it manually."
    db.commit()


def _owned_run(db: Session, user: models.User, run_id: str) -> AIEmployeeRun:
    run = (
        db.query(AIEmployeeRun)
        .filter(AIEmployeeRun.id == run_id, AIEmployeeRun.company_id == user.company_id)
        .first()
    )
    if not run:
        raise HTTPException(404, "Run not found")
    return run


# --------------------------------------------------------------------------
# roster
# --------------------------------------------------------------------------

@router.get("", response_model=list[schemas.EmployeeOut])
def list_employees(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """The roster screen. Catalog + this company's overrides merged here
    rather than seeded into the DB at signup — the catalog stays the single
    source of truth for defaults."""
    overrides = {
        c.employee_key: c
        for c in db.query(AIEmployeeConfig)
        .filter(AIEmployeeConfig.company_id == current_user.company_id).all()
    }
    roster = []
    for key, info in EMPLOYEE_CATALOG.items():
        config = overrides.get(key)
        roster.append(schemas.EmployeeOut(
            key=key,
            label=info["label"],
            department=info["department"],
            description=info["description"],
            intents=info["intents"],
            examples=info.get("examples", []),
            enabled=config.enabled if config else True,
            display_name=config.display_name if config else None,
            autonomy_level=config.autonomy_level if config else "standard",
            instructions=config.instructions if config else None,
        ))
    return roster


@router.get("/duties")
def list_duties(current_user: models.User = Depends(get_current_user)):
    """Recurring work the scheduler can trigger. See the integration doc for
    wiring these into the existing followups scheduler."""
    return {"duties": DUTIES}


@router.patch("/{employee_key}/config", response_model=schemas.EmployeeOut)
def update_employee_config(
    employee_key: str,
    payload: schemas.EmployeeConfigUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if employee_key not in EMPLOYEE_CATALOG:
        raise HTTPException(404, f"No such AI employee: {employee_key}")
    if payload.autonomy_level is not None and payload.autonomy_level not in ("standard", "cautious"):
        # There is deliberately no looser level — see ALWAYS_CONFIRM.
        raise HTTPException(400, 'autonomy_level must be "standard" or "cautious"')

    config = _config(db, current_user.company_id, employee_key)
    if not config:
        config = AIEmployeeConfig(company_id=current_user.company_id, employee_key=employee_key)
        db.add(config)

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(config, field, value)
    db.commit()
    db.refresh(config)

    info = EMPLOYEE_CATALOG[employee_key]
    return schemas.EmployeeOut(
        key=employee_key, label=info["label"], department=info["department"],
        description=info["description"], intents=info["intents"], examples=info.get("examples", []),
        enabled=config.enabled, display_name=config.display_name,
        autonomy_level=config.autonomy_level, instructions=config.instructions,
    )


# --------------------------------------------------------------------------
# the main flow
# --------------------------------------------------------------------------

@router.post("/{employee_key}/brief", response_model=schemas.AIEmployeeRunOut)
def submit_brief(
    employee_key: str,
    payload: schemas.BriefRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Hand one instruction to one employee.

    Returns either an EXECUTED run with a result, or an
    AWAITING_CONFIRMATION run with a summary to show before anything
    happens. Which one you get is decided by ai_employee_actions.
    requires_confirmation() — one function, one place to audit.
    """
    employee = _check_employee(db, current_user.company_id, employee_key)
    config_row = _config(db, current_user.company_id, employee_key)

    run = AIEmployeeRun(
        company_id=current_user.company_id,
        user_id=current_user.id,
        employee_key=employee_key,
        trigger=payload.trigger,
        brief=payload.brief,
        status=AIEmployeeRunStatus.PLANNED,
    )
    db.add(run)
    db.flush()

    try:
        plan = brain.plan(
            employee_key,
            payload.brief,
            context=_planning_context(db, current_user.company_id, employee_key),
            extra_instructions=config_row.instructions if config_row else None,
        )
    except brain.EmployeeBrainError as exc:
        run.status = AIEmployeeRunStatus.FAILED
        run.error = str(exc)
        db.commit()
        return _out(run)

    run.intent = plan.intent
    run.confidence = plan.confidence
    run.action_json = json.dumps({"type": plan.intent, "config": plan.config})
    run.summary = plan.summary
    run.missing_info_json = json.dumps(plan.missing_info)

    # Departmental boundary. `plan()` already rejects out-of-catalog intents;
    # this is the check that doesn't depend on the model behaving.
    if plan.intent == "unclear" or not employee_owns_intent(employee_key, plan.intent):
        run.status = AIEmployeeRunStatus.NO_ACTION
        run.summary = run.summary or (
            f"{employee['label']} doesn't handle that. Try one of: "
            f"{', '.join(employee['intents'][:4])}."
        )
        db.commit()
        return _out(run)

    if plan.intent not in EMPLOYEE_ACTION_REGISTRY:
        run.status = AIEmployeeRunStatus.FAILED
        run.error = f"{plan.intent} isn't implemented yet."
        db.commit()
        return _out(run)

    if payload.dry_run:
        run.status = AIEmployeeRunStatus.AWAITING_CONFIRMATION
        db.commit()
        return _out(run)

    # Gaps can't be auto-filled — hold for the user to supply them via
    # /confirm's overrides rather than writing a half-formed row.
    if plan.missing_info:
        run.status = AIEmployeeRunStatus.AWAITING_CONFIRMATION
        db.commit()
        return _out(run)

    # A shaky match gets a human look regardless of which set the intent is
    # in. This is also what catches the no-API-key keyword fallback in
    # ai_employee_brain._keyword_fallback, which never scores above 0.3.
    if (plan.confidence or 0) < MIN_AUTO_CONFIDENCE:
        run.status = AIEmployeeRunStatus.AWAITING_CONFIRMATION
        db.commit()
        return _out(run)

    autonomy = config_row.autonomy_level if config_row else "standard"
    if requires_confirmation(plan.intent, autonomy):
        run.status = AIEmployeeRunStatus.AWAITING_CONFIRMATION
        db.commit()
        return _out(run)

    _execute(db, run, current_user, plan.config)
    return _out(run)


@router.post("/runs/{run_id}/confirm", response_model=schemas.AIEmployeeRunOut)
def confirm_run(
    run_id: str,
    payload: schemas.ConfirmRunRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    run = _owned_run(db, current_user, run_id)
    if run.status != AIEmployeeRunStatus.AWAITING_CONFIRMATION:
        raise HTTPException(400, f"Run is '{run.status.value}', not awaiting confirmation")

    config = json.loads(run.action_json)["config"] if run.action_json else {}
    config = {**config, **payload.overrides}
    _execute(db, run, current_user, config)
    return _out(run)


@router.post("/runs/{run_id}/cancel", response_model=schemas.AIEmployeeRunOut)
def cancel_run(
    run_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    run = _owned_run(db, current_user, run_id)
    if run.status != AIEmployeeRunStatus.AWAITING_CONFIRMATION:
        raise HTTPException(400, f"Run is '{run.status.value}', not awaiting confirmation")
    run.status = AIEmployeeRunStatus.CANCELLED
    db.commit()
    return _out(run)


@router.get("/runs", response_model=list[schemas.AIEmployeeRunOut])
def list_runs(
    employee_key: str | None = Query(None),
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    query = db.query(AIEmployeeRun).filter(AIEmployeeRun.company_id == current_user.company_id)
    if employee_key:
        query = query.filter(AIEmployeeRun.employee_key == employee_key)
    runs = query.order_by(AIEmployeeRun.created_at.desc()).limit(limit).all()
    return [_out(r) for r in runs]


@router.get("/{employee_key}/records")
def list_records(
    employee_key: str,
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Whatever this employee's department has on file.

    One generic endpoint rather than seven CRUD routers, and it returns plain
    dicts rather than per-table Pydantic schemas. The reason is honest: these
    rows exist so the work an employee did is *visible*, not so they can be
    edited in a grid. The day a department needs real editing it gets its own
    router — until then, seven schema files would be seven files to keep in
    sync for a read-only table.

    Each department returns `{"columns": [...], "rows": [...]}` so the
    frontend renders all seven with one component.
    """
    from app.ai_employee_models import (
        Campaign, ContentPiece, Contract, Employee, Expense, InventoryItem,
        LeaveRequest, OnboardingTask, PurchaseOrder, StockMovement, Supplier,
    )

    _check_employee(db, current_user.company_id, employee_key)

    def rows(model, columns: list[str], order=None, **extra):
        query = db.query(model).filter(model.company_id == current_user.company_id)
        query = query.order_by(order if order is not None else model.created_at.desc())
        out = []
        for row in query.limit(limit).all():
            record = {}
            for column in columns:
                value = getattr(row, column, None)
                record[column] = value.value if hasattr(value, "value") else value
            for label, fn in extra.items():
                record[label] = fn(row)
            out.append(record)
        return {"columns": columns + list(extra), "rows": out}

    if employee_key == "hr_officer":
        return {
            "Employees": rows(Employee, ["full_name", "job_title", "department",
                                         "employment_status", "joined_on"]),
            "Leave requests": rows(LeaveRequest, ["leave_type", "starts_on", "ends_on", "days", "status"],
                                   employee=lambda r: r.employee.full_name if r.employee else None),
            "Onboarding": rows(OnboardingTask, ["title", "owner", "due_on", "completed"],
                               employee=lambda r: r.employee.full_name if r.employee else None),
        }
    if employee_key == "legal_assistant":
        return {"Contracts": rows(Contract, ["title", "contract_type", "counterparty_name",
                                             "status", "starts_on", "ends_on", "auto_renews"])}
    if employee_key == "marketing_executive":
        return {
            "Campaigns": rows(Campaign, ["name", "channel", "status", "audience_size",
                                         "subject", "sent_count"]),
            "Content calendar": rows(ContentPiece, ["title", "channel", "publish_on", "published"],
                                     order=ContentPiece.publish_on.asc()),
        }
    if employee_key == "procurement_officer":
        return {
            "Suppliers": rows(Supplier, ["name", "contact_person", "email", "phone",
                                         "payment_terms", "lead_time_days", "on_time_rate"]),
            "Purchase orders": rows(PurchaseOrder, ["number", "status", "total", "currency",
                                                    "expected_on", "received_on"],
                                    supplier=lambda r: r.supplier.name if r.supplier else None),
        }
    if employee_key == "inventory_controller":
        return {
            "Stock": rows(InventoryItem, ["name", "sku", "unit", "quantity_on_hand",
                                          "reorder_point"],
                          available=lambda r: r.quantity_available,
                          low=lambda r: r.needs_reorder),
            "Movements": rows(StockMovement, ["movement_type", "quantity", "balance_after",
                                              "reason", "created_at"],
                              item=lambda r: r.item.name if r.item else None),
        }
    if employee_key == "bookkeeper":
        return {"Expenses": rows(Expense, ["description", "category", "amount", "currency",
                                           "incurred_on", "status"])}
    # support_agent keeps nothing of its own — its output lands on the
    # customer's activity timeline, which the customer page already renders.
    return {}


@router.post("/{employee_key}/run-duty/{duty_key}", response_model=schemas.AIEmployeeRunOut)
def run_duty(
    employee_key: str,
    duty_key: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Runs a scheduled duty directly — no model call, since the intent is
    already known. That's the point: a daily sweep shouldn't cost a token,
    and its behaviour shouldn't vary run to run.

    Every duty maps to a read-only intent in AUTO_EXECUTE, so this endpoint
    can't be used to slip past the confirmation gate.
    """
    duty = DUTIES.get(duty_key)
    if not duty or duty["employee"] != employee_key:
        raise HTTPException(404, f"No duty '{duty_key}' for {employee_key}")
    _check_employee(db, current_user.company_id, employee_key)

    intent = duty["intent"]
    if requires_confirmation(intent):
        raise HTTPException(400, f"Duty '{duty_key}' maps to an intent that needs confirmation")

    run = AIEmployeeRun(
        company_id=current_user.company_id, user_id=current_user.id,
        employee_key=employee_key, trigger=AIEmployeeRunTrigger.SCHEDULE,
        brief=f"[scheduled duty] {duty['description']}",
        intent=intent, confidence=1.0,
        action_json=json.dumps({"type": intent, "config": {}}),
        summary=duty["description"],
        status=AIEmployeeRunStatus.PLANNED,
    )
    db.add(run)
    db.flush()
    _execute(db, run, current_user, {})
    return _out(run)
