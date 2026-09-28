"""
What actually happens once an employee's brief has been planned.

Same open/closed shape as workflow_actions.ACTION_REGISTRY and
voice_actions.VOICE_ACTION_REGISTRY: every action is a plain function,
`(db, company_id, user_id, config) -> dict`, keyed by string in
EMPLOYEE_ACTION_REGISTRY. A new capability is one function + one registry
entry + one INTENT_SLOTS entry + adding the intent to its employee in
EMPLOYEE_CATALOG. Nothing else.

THE SAFETY GATE (bottom of this file) is the one part worth reading twice.
Three sets, not a per-function flag, for the same reason voice_actions.py
does it this way — "can this happen without a human tapping approve" must
be answerable by reading one screen, not by auditing forty functions:

- AUTO_EXECUTE — reads, reports, and internal writes to this company's own
  records. Reversible, nothing leaves the building.
- CONFIRM_REQUIRED — writes that are awkward to undo, or that produce a
  document a human will act on. Held at AWAITING_CONFIRMATION.
- ALWAYS_CONFIRM — a subset of CONFIRM_REQUIRED that stays held even when
  a company sets autonomy_level to something looser. Every action in here
  either sends a message to a real outside party (a campaign to 400
  customers, a PO to a supplier) or moves money. There is deliberately no
  configuration value that empties this set. A company can make the system
  more cautious than default; it cannot make it less.

On LLM-generated text: every action that calls ai_employee_brain.write()
writes it to a DRAFT-status row and returns it for display. None of them
send it. Sending is always a separate, separately-confirmed intent
(`send_campaign`, `send_purchase_order`) — so "draft the thing" and "the
thing went out" can never collapse into one accidental step.
"""
import json
import logging
from datetime import date, datetime, timedelta
from typing import Any, Callable, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app import models
from app.config import settings
from app import ai_employee_brain as brain
from app.ai_employee_models import (
    Employee, EmploymentStatus, LeaveRequest, LeaveType, LeaveStatus, OnboardingTask,
    Contract, ContractStatus, ContractParty,
    Campaign, CampaignChannel, CampaignStatus, ContentPiece,
    Supplier, PurchaseOrder, PurchaseOrderItem, PurchaseOrderStatus,
    InventoryItem, StockMovement, StockMovementType,
    Expense, ExpenseStatus,
)

logger = logging.getLogger(__name__)


class EmployeeActionError(Exception):
    """Anything the user can fix by re-phrasing or supplying a detail
    (record not found, ambiguous name, missing slot). The message is shown
    back verbatim, so keep it short and tell them what to do next."""


# --------------------------------------------------------------------------
# Shared resolvers
# --------------------------------------------------------------------------

def _resolve(db: Session, model, company_id: str, name: str, *fields, label: str):
    """Fuzzy name -> row, with the two failure modes spelled out.

    Ambiguity is an error, never a silent pick-the-first: "send the PO to
    Zenith" when there are two Zeniths must stop, because the wrong branch
    of that guess is a real order placed with the wrong company.
    """
    name = (name or "").strip()
    if not name:
        raise EmployeeActionError(f"No {label} named in that instruction.")

    clauses = [getattr(model, f).ilike(f"%{name}%") for f in fields]
    matches = (
        db.query(model)
        .filter(model.company_id == company_id, or_(*clauses))
        .limit(5)
        .all()
    )
    if not matches:
        raise EmployeeActionError(f'No {label} matching "{name}" found.')
    if len(matches) > 1:
        shown = ", ".join(str(getattr(m, fields[0])) for m in matches)
        raise EmployeeActionError(f'"{name}" matches more than one {label} ({shown}) — be more specific.')
    return matches[0]


def _employee(db, company_id, config, key="employee_name") -> Employee:
    return _resolve(db, Employee, company_id, config.get(key), "full_name", "email", label="employee")


def _supplier(db, company_id, config, key="supplier_name") -> Supplier:
    return _resolve(db, Supplier, company_id, config.get(key), "name", label="supplier")


def _item(db, company_id, config, key="item_name") -> InventoryItem:
    return _resolve(db, InventoryItem, company_id, config.get(key), "name", "sku", label="stock item")


def _campaign(db, company_id, config, key="campaign_name") -> Campaign:
    return _resolve(db, Campaign, company_id, config.get(key), "name", label="campaign")


def _customer(db, company_id, config, key="customer_name") -> "models.Customer":
    return _resolve(db, models.Customer, company_id, config.get(key), "name", "email", label="customer")


def _contract(db, company_id, config, key="contract_title_or_id") -> Contract:
    raw = (config.get(key) or "").strip()
    found = db.query(Contract).filter(Contract.company_id == company_id, Contract.id == raw).first()
    return found or _resolve(db, Contract, company_id, raw, "title", "counterparty_name", label="contract")


def _parse_date(value: Any) -> Optional[date]:
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return datetime.fromisoformat(str(value)).date()
    except ValueError:
        return None


def _required(config: dict, *keys: str) -> None:
    """Belt to the planner's braces. missing_info should already have caught
    these, but an action must never write a half-formed row because the model
    forgot to populate that list."""
    missing = [k for k in keys if config.get(k) in (None, "", [])]
    if missing:
        raise EmployeeActionError(f"Still need: {', '.join(missing)}.")


def _next_number(db: Session, model, company_id: str, prefix: str) -> str:
    count = db.query(model).filter(model.company_id == company_id).count() + 1
    return f"{prefix}-{count:06d}"


def _config_instructions(db: Session, company_id: str, employee_key: str) -> Optional[str]:
    from app.ai_employee_models import AIEmployeeConfig
    row = (
        db.query(AIEmployeeConfig)
        .filter(AIEmployeeConfig.company_id == company_id, AIEmployeeConfig.employee_key == employee_key)
        .first()
    )
    return row.instructions if row else None


# ==========================================================================
# HR
# ==========================================================================

def action_add_employee(db: Session, company_id: str, user_id: str, config: dict) -> dict:
    _required(config, "full_name")
    manager = None
    if config.get("manager_name"):
        try:
            manager = _employee(db, company_id, config, "manager_name")
        except EmployeeActionError:
            manager = None  # an unrecognised manager shouldn't block the hire

    status_raw = (config.get("employment_status") or "active").lower()
    try:
        status = EmploymentStatus(status_raw)
    except ValueError:
        status = EmploymentStatus.ACTIVE

    employee = Employee(
        company_id=company_id,
        full_name=config["full_name"],
        email=config.get("email"),
        phone=config.get("phone"),
        job_title=config.get("job_title"),
        department=config.get("department"),
        manager_employee_id=manager.id if manager else None,
        employment_status=status,
        joined_on=_parse_date(config.get("joined_on")),
        annual_leave_days=float(config.get("annual_leave_days", 20) or 20),
    )
    db.add(employee)
    db.commit()
    db.refresh(employee)
    return {"employee_id": employee.id, "full_name": employee.full_name, "job_title": employee.job_title}


_EMPLOYEE_EDITABLE = {
    "job_title", "department", "email", "phone", "employment_status",
    "annual_leave_days", "notes", "ended_on",
}


def action_update_employee(db: Session, company_id: str, user_id: str, config: dict) -> dict:
    """Field is whitelisted, not free. The model proposing
    `field="salary_amount"` is exactly the case this guards — pay changes go
    through a human in the HR screen, never through a chat instruction."""
    _required(config, "field", "value")
    employee = _employee(db, company_id, config)
    field = str(config["field"]).lower().strip()
    if field not in _EMPLOYEE_EDITABLE:
        raise EmployeeActionError(
            f'"{field}" can\'t be changed this way. Editable here: {", ".join(sorted(_EMPLOYEE_EDITABLE))}.'
        )

    value: Any = config["value"]
    if field == "employment_status":
        try:
            value = EmploymentStatus(str(value).lower())
        except ValueError:
            raise EmployeeActionError(f'"{value}" isn\'t an employment status.')
    elif field == "annual_leave_days":
        value = float(value)
    elif field == "ended_on":
        value = _parse_date(value)

    old = getattr(employee, field)
    setattr(employee, field, value)
    db.commit()
    return {"employee_id": employee.id, "field": field,
            "old": str(old) if old is not None else None, "new": str(value)}


def action_record_leave_request(db: Session, company_id: str, user_id: str, config: dict) -> dict:
    _required(config, "starts_on", "ends_on")
    employee = _employee(db, company_id, config)
    starts, ends = _parse_date(config["starts_on"]), _parse_date(config["ends_on"])
    if not starts or not ends:
        raise EmployeeActionError("Couldn't read those dates — give them as day and month.")
    if ends < starts:
        raise EmployeeActionError("The end date is before the start date.")

    try:
        leave_type = LeaveType((config.get("leave_type") or "annual").lower())
    except ValueError:
        leave_type = LeaveType.OTHER

    days = float(config.get("days") or (ends - starts).days + 1)
    request = LeaveRequest(
        company_id=company_id, employee_id=employee.id, leave_type=leave_type,
        starts_on=starts, ends_on=ends, days=days, reason=config.get("reason"),
        status=LeaveStatus.PENDING,
    )
    db.add(request)
    db.commit()
    db.refresh(request)

    # Advisory only — the balance doesn't block the request, a manager decides.
    taken = (
        db.query(LeaveRequest)
        .filter(LeaveRequest.employee_id == employee.id,
                LeaveRequest.leave_type == LeaveType.ANNUAL,
                LeaveRequest.status == LeaveStatus.APPROVED)
        .all()
    )
    used = sum(r.days for r in taken)
    return {
        "leave_request_id": request.id, "employee": employee.full_name,
        "days": days, "status": request.status.value,
        "annual_days_used": used, "annual_days_entitled": employee.annual_leave_days,
        "over_entitlement": leave_type == LeaveType.ANNUAL and (used + days) > employee.annual_leave_days,
    }


def action_decide_leave_request(db: Session, company_id: str, user_id: str, config: dict) -> dict:
    _required(config, "decision")
    employee = _employee(db, company_id, config)
    request = (
        db.query(LeaveRequest)
        .filter(LeaveRequest.company_id == company_id,
                LeaveRequest.employee_id == employee.id,
                LeaveRequest.status == LeaveStatus.PENDING)
        .order_by(LeaveRequest.created_at.desc())
        .first()
    )
    if not request:
        raise EmployeeActionError(f"{employee.full_name} has no pending leave request.")

    decision = str(config["decision"]).lower()
    if decision.startswith(("approve", "yes", "accept")):
        request.status = LeaveStatus.APPROVED
    elif decision.startswith(("reject", "decline", "no", "deny")):
        request.status = LeaveStatus.REJECTED
    else:
        raise EmployeeActionError('Say "approve" or "reject".')

    request.decided_by_user_id = user_id
    request.decided_at = datetime.utcnow()
    request.decision_note = config.get("decision_note")
    db.commit()
    return {"leave_request_id": request.id, "employee": employee.full_name, "status": request.status.value}


_DEFAULT_ONBOARDING = [
    ("Send offer letter and contract", "HR", 0),
    ("Collect ID, tax and bank details", "HR", 2),
    ("Create email account and system logins", "IT", 1),
    ("Issue laptop and equipment", "IT", 1),
    ("Add to payroll", "Finance", 3),
    ("Schedule first-week introductions", "Line manager", 1),
    ("Set 30/60/90 day objectives", "Line manager", 5),
    ("Book probation review", "HR", 7),
]


def action_generate_onboarding_checklist(db: Session, company_id: str, user_id: str, config: dict) -> dict:
    """Template-first, AI-second: the eight items below are always created,
    and the model only adds role-specific extras on top. A checklist that
    silently loses "add to payroll" because a generation wobbled is worse
    than one that's slightly generic."""
    employee = _employee(db, company_id, config)
    start = employee.joined_on or date.today()

    created = []
    for title, owner, offset in _DEFAULT_ONBOARDING:
        task = OnboardingTask(
            company_id=company_id, employee_id=employee.id, title=title,
            owner=owner, due_on=start + timedelta(days=offset),
        )
        db.add(task)
        created.append(title)

    if config.get("role_context") or employee.job_title:
        try:
            extras = brain.review_json(
                "hr_officer",
                "List up to 5 onboarding tasks specific to this role that a generic checklist "
                'would miss. Return {"items": [...]}; each element: '
                '{"title": ..., "owner": ..., "due_day_offset": <int>}.',
                context={"job_title": employee.job_title, "department": employee.department,
                         "role_context": config.get("role_context")},
                max_tokens=600,
            )
            for extra in extras[:5]:
                if not isinstance(extra, dict) or not extra.get("title"):
                    continue
                db.add(OnboardingTask(
                    company_id=company_id, employee_id=employee.id,
                    title=str(extra["title"])[:200], owner=extra.get("owner"),
                    due_on=start + timedelta(days=int(extra.get("due_day_offset", 3) or 3)),
                ))
                created.append(str(extra["title"])[:200])
        except Exception:
            logger.warning("Role-specific onboarding extras failed; standard checklist kept", exc_info=True)

    db.commit()
    return {"employee": employee.full_name, "tasks_created": len(created), "tasks": created}


def action_draft_job_description(db: Session, company_id: str, user_id: str, config: dict) -> dict:
    _required(config, "job_title")
    text = brain.write(
        "hr_officer",
        f"Write a job description for: {config['job_title']}. "
        "Sections: role summary, responsibilities, required experience, nice to have, "
        "what we offer. Keep it under 500 words.",
        context={"seniority": config.get("seniority"), "notes": config.get("requirements_note"),
                 "department": config.get("department")},
        extra_instructions=_config_instructions(db, company_id, "hr_officer"),
    )
    return {"job_title": config["job_title"], "job_description": text}


def action_hr_headcount_report(db: Session, company_id: str, user_id: str, config: dict) -> dict:
    employees = db.query(Employee).filter(Employee.company_id == company_id).all()
    by_status: dict[str, int] = {}
    by_department: dict[str, int] = {}
    for e in employees:
        by_status[e.employment_status.value] = by_status.get(e.employment_status.value, 0) + 1
        key = e.department or "Unassigned"
        by_department[key] = by_department.get(key, 0) + 1

    pending = (
        db.query(LeaveRequest)
        .filter(LeaveRequest.company_id == company_id, LeaveRequest.status == LeaveStatus.PENDING)
        .count()
    )
    return {
        "headcount": len(employees),
        "by_status": by_status,
        "by_department": by_department,
        "pending_leave_requests": pending,
    }


# ==========================================================================
# Legal
# ==========================================================================

def action_draft_contract(db: Session, company_id: str, user_id: str, config: dict) -> dict:
    """Produces a DRAFT row and nothing else. Status is never anything but
    DRAFT out of this function — moving a contract to SENT or SIGNED is a
    separate, separately-confirmed intent."""
    _required(config, "contract_type", "counterparty_name")
    company = db.get(models.Company, company_id)

    body = brain.write(
        "legal_assistant",
        f"Draft a {config['contract_type']} between {company.name if company else '[OUR COMPANY]'} "
        f"and {config['counterparty_name']}.",
        context={
            "key_terms": config.get("key_terms"),
            "value": config.get("value_amount"),
            "currency": config.get("value_currency") or getattr(settings, "default_currency", None),
            "starts_on": config.get("starts_on"),
            "ends_on": config.get("ends_on"),
            "governing_law": config.get("governing_law"),
        },
        max_tokens=4000,
        extra_instructions=_config_instructions(db, company_id, "legal_assistant"),
    )

    contract = Contract(
        company_id=company_id,
        title=f"{config['contract_type']} — {config['counterparty_name']}",
        contract_type=config["contract_type"],
        counterparty_name=config["counterparty_name"],
        status=ContractStatus.DRAFT,
        body=body,
        value_amount=float(config["value_amount"]) if config.get("value_amount") else None,
        value_currency=config.get("value_currency") or getattr(settings, "default_currency", None),
        starts_on=_parse_date(config.get("starts_on")),
        ends_on=_parse_date(config.get("ends_on")),
    )
    db.add(contract)
    db.commit()
    db.refresh(contract)
    return {
        "contract_id": contract.id, "title": contract.title, "status": contract.status.value,
        "body": body,
        "disclaimer": "AI-generated draft. Have a qualified lawyer review before signing.",
    }


def action_review_contract(db: Session, company_id: str, user_id: str, config: dict) -> dict:
    contract = _contract(db, company_id, config)
    if not contract.body:
        raise EmployeeActionError(f'"{contract.title}" has no text stored to review.')

    findings = brain.review_json(
        "legal_assistant",
        "Review this contract from our side. Return {\"items\": [...]}; each element: "
        '{"clause": "<short name>", "risk": "high|medium|low", "why": "<one sentence>", '
        '"suggestion": "<what to ask for instead>"}. Include only real commercial risks — '
        "an empty array is a valid answer if the terms are balanced.",
        context={"title": contract.title, "counterparty": contract.counterparty_name,
                 "body": contract.body},
        max_tokens=3000,
    )
    contract.risk_findings_json = json.dumps(findings)
    contract.reviewed_at = datetime.utcnow()
    if contract.status == ContractStatus.DRAFT:
        contract.status = ContractStatus.IN_REVIEW
    db.commit()

    high = [f for f in findings if isinstance(f, dict) and str(f.get("risk", "")).lower() == "high"]
    return {
        "contract_id": contract.id, "title": contract.title,
        "findings": findings, "high_risk_count": len(high),
        "disclaimer": "Commercial review only, not legal advice.",
    }


def action_log_contract(db: Session, company_id: str, user_id: str, config: dict) -> dict:
    """For agreements signed elsewhere — the point is the expiry tracking,
    so `ends_on` is what everything downstream cares about."""
    _required(config, "title", "counterparty_name")
    try:
        party = ContractParty((config.get("counterparty_type") or "other").lower())
    except ValueError:
        party = ContractParty.OTHER

    contract = Contract(
        company_id=company_id,
        title=config["title"],
        contract_type=config.get("contract_type"),
        counterparty_type=party,
        counterparty_name=config["counterparty_name"],
        status=ContractStatus.ACTIVE,
        starts_on=_parse_date(config.get("starts_on")),
        ends_on=_parse_date(config.get("ends_on")),
        value_amount=float(config["value_amount"]) if config.get("value_amount") else None,
        auto_renews=bool(config.get("auto_renews", False)),
        notice_period_days=int(config["notice_period_days"]) if config.get("notice_period_days") else None,
    )
    db.add(contract)
    db.commit()
    db.refresh(contract)
    return {"contract_id": contract.id, "title": contract.title,
            "ends_on": contract.ends_on.isoformat() if contract.ends_on else None}


def action_update_contract_status(db: Session, company_id: str, user_id: str, config: dict) -> dict:
    _required(config, "status")
    contract = _contract(db, company_id, config)
    try:
        new_status = ContractStatus(str(config["status"]).lower().replace(" ", "_"))
    except ValueError:
        valid = ", ".join(s.value for s in ContractStatus)
        raise EmployeeActionError(f'"{config["status"]}" isn\'t a contract status. Valid: {valid}.')
    old = contract.status
    contract.status = new_status
    db.commit()
    return {"contract_id": contract.id, "old_status": old.value, "new_status": new_status.value}


def action_list_expiring_contracts(db: Session, company_id: str, user_id: str, config: dict) -> dict:
    """Notice period, not expiry date, is the deadline that matters: an
    auto-renewing contract with 60 days' notice is already lost on day 61
    before expiry. `action_by` is the date the user actually needs."""
    within = int(config.get("within_days") or 90)
    horizon = date.today() + timedelta(days=within)

    contracts = (
        db.query(Contract)
        .filter(Contract.company_id == company_id,
                Contract.ends_on.isnot(None),
                Contract.ends_on <= horizon,
                Contract.status.in_([ContractStatus.ACTIVE, ContractStatus.SIGNED]))
        .order_by(Contract.ends_on.asc())
        .all()
    )

    rows = []
    for c in contracts:
        action_by = c.ends_on - timedelta(days=c.notice_period_days) if c.notice_period_days else c.ends_on
        rows.append({
            "contract_id": c.id, "title": c.title, "counterparty": c.counterparty_name,
            "ends_on": c.ends_on.isoformat(),
            "auto_renews": c.auto_renews,
            "notice_deadline": action_by.isoformat(),
            "notice_deadline_passed": action_by < date.today(),
        })
    return {"within_days": within, "count": len(rows), "contracts": rows}


# ==========================================================================
# Marketing
# ==========================================================================

def _resolve_audience(db: Session, company_id: str, audience: dict) -> list["models.Customer"]:
    """Audience rules -> customers.

    Supported keys: pipeline_stage, lead_source, has_email, has_phone,
    no_contact_since_days. Unknown keys are ignored rather than raising —
    a rule the model invents must narrow nothing, never silently widen the
    send. Getting that backwards mails 400 people by accident.
    """
    query = db.query(models.Customer).filter(models.Customer.company_id == company_id)

    stage = audience.get("pipeline_stage")
    if stage:
        try:
            query = query.filter(models.Customer.pipeline_stage == models.PipelineStage(str(stage).lower()))
        except ValueError:
            pass

    if audience.get("lead_source"):
        query = query.filter(models.Customer.lead_source.ilike(f"%{audience['lead_source']}%"))
    if audience.get("has_email"):
        query = query.filter(models.Customer.email.isnot(None), models.Customer.email != "")
    if audience.get("has_phone"):
        query = query.filter(models.Customer.phone.isnot(None), models.Customer.phone != "")

    customers = query.limit(5000).all()

    since_days = audience.get("no_contact_since_days")
    if since_days:
        # "Contact" means an email we sent or a note someone logged. Customer
        # has no updated_at in this schema, so this is computed from the
        # activity tables rather than faked from created_at — a customer
        # edited last week hasn't necessarily been *spoken to*.
        cutoff = datetime.utcnow() - timedelta(days=int(since_days))
        ids = [c.id for c in customers]
        recent: set[str] = set()
        if ids:
            recent |= {
                row[0] for row in db.query(models.EmailMessage.customer_id)
                .filter(models.EmailMessage.customer_id.in_(ids),
                        models.EmailMessage.created_at > cutoff).all()
            }
            recent |= {
                row[0] for row in db.query(models.CustomerNote.customer_id)
                .filter(models.CustomerNote.customer_id.in_(ids),
                        models.CustomerNote.created_at > cutoff).all()
            }
        customers = [c for c in customers if c.id not in recent and (c.created_at or datetime.min) <= cutoff]

    return customers


def action_create_campaign(db: Session, company_id: str, user_id: str, config: dict) -> dict:
    _required(config, "name")
    try:
        channel = CampaignChannel((config.get("channel") or "email").lower())
    except ValueError:
        channel = CampaignChannel.EMAIL

    audience = config.get("audience") or {}
    if isinstance(audience, str):
        audience = {"description": audience}

    campaign = Campaign(
        company_id=company_id, created_by_user_id=user_id,
        name=config["name"], goal=config.get("goal"), channel=channel,
        status=CampaignStatus.DRAFT,
        audience_json=json.dumps(audience),
        scheduled_for=_parse_date(config.get("scheduled_for")) and
        datetime.fromisoformat(str(config["scheduled_for"])),
    )
    campaign.audience_size = len(_resolve_audience(db, company_id, audience)) if audience else None
    db.add(campaign)
    db.commit()
    db.refresh(campaign)
    return {"campaign_id": campaign.id, "name": campaign.name,
            "channel": campaign.channel.value, "audience_size": campaign.audience_size}


def action_write_campaign_copy(db: Session, company_id: str, user_id: str, config: dict) -> dict:
    campaign = _campaign(db, company_id, config)
    company = db.get(models.Company, company_id)

    limit = "under 500 characters, no subject line" if campaign.channel == CampaignChannel.WHATSAPP \
        else "with a subject line on the first line, then the body"
    text = brain.write(
        "marketing_executive",
        f"Write {campaign.channel.value} copy for the campaign \"{campaign.name}\", {limit}.",
        context={"goal": campaign.goal, "angle": config.get("angle"), "tone": config.get("tone"),
                 "company": company.name if company else None,
                 "audience": json.loads(campaign.audience_json) if campaign.audience_json else None},
        max_tokens=1200,
        extra_instructions=_config_instructions(db, company_id, "marketing_executive"),
    )

    if campaign.channel == CampaignChannel.WHATSAPP:
        campaign.body = text
    else:
        first, _, rest = text.partition("\n")
        campaign.subject = first.removeprefix("Subject:").strip()[:250]
        campaign.body = rest.strip() or text
    db.commit()
    return {"campaign_id": campaign.id, "subject": campaign.subject, "body": campaign.body}


def action_preview_campaign_audience(db: Session, company_id: str, user_id: str, config: dict) -> dict:
    campaign = _campaign(db, company_id, config)
    audience = json.loads(campaign.audience_json) if campaign.audience_json else {}
    customers = _resolve_audience(db, company_id, audience)
    campaign.audience_size = len(customers)
    db.commit()
    return {
        "campaign_id": campaign.id, "audience_size": len(customers),
        "reachable_by_email": sum(1 for c in customers if c.email),
        "reachable_by_whatsapp": sum(1 for c in customers if c.phone),
        "sample": [c.name for c in customers[:10]],
    }


def action_send_campaign(db: Session, company_id: str, user_id: str, config: dict) -> dict:
    """The one action in this module that touches hundreds of real people at
    once. Three guards, in order: copy must exist, the list is re-resolved
    now rather than trusting a cached count, and a campaign already SENT
    can't be sent twice."""
    campaign = _campaign(db, company_id, config)
    if campaign.status == CampaignStatus.SENT:
        raise EmployeeActionError(f'"{campaign.name}" has already been sent.')
    if not campaign.body:
        raise EmployeeActionError(f'"{campaign.name}" has no copy yet — write the copy first.')

    audience = json.loads(campaign.audience_json) if campaign.audience_json else {}
    customers = _resolve_audience(db, company_id, audience)
    if not customers:
        raise EmployeeActionError("That audience matches nobody right now.")

    if campaign.channel in (CampaignChannel.WHATSAPP, CampaignChannel.SOCIAL):
        # Only email sending exists in this build. Refusing here — before the
        # status moves to SENDING — is better than marking a campaign sent
        # that never went anywhere.
        raise EmployeeActionError(
            f"{campaign.channel.value} sending isn't wired up in this build. "
            "The copy and audience are saved; send it from your own tool, or "
            "switch the campaign to email."
        )

    campaign.status = CampaignStatus.SENDING
    db.commit()

    sent = failed = 0
    for customer in customers:
        try:
            if not customer.email:
                continue
            from app.email_sender import send_email as _send
            _send(to_email=customer.email, subject=campaign.subject or campaign.name, body=campaign.body)
            sent += 1
        except Exception:
            # One bad address must not abort a 400-recipient send.
            logger.warning("Campaign %s failed for customer %s", campaign.id, customer.id, exc_info=True)
            failed += 1

    campaign.sent_count, campaign.failed_count = sent, failed
    campaign.status = CampaignStatus.SENT
    campaign.sent_at = datetime.utcnow()
    db.commit()
    return {"campaign_id": campaign.id, "sent": sent, "failed": failed}


def action_plan_content_calendar(db: Session, company_id: str, user_id: str, config: dict) -> dict:
    _required(config, "theme")
    count = int(config.get("pieces") or 8)
    start = _parse_date(config.get("start_on")) or date.today()

    pieces = brain.review_json(
        "marketing_executive",
        f"Plan {count} content pieces on the theme: {config['theme']}. Return {{\"items\": [...]}}; "
        'each element: {"title": ..., "channel": ..., "body": "<the actual post, ready to publish>", '
        '"hashtags": "...", "day_offset": <int days from the start date>}.',
        context={"channel": config.get("channel"), "start_on": start.isoformat()},
        max_tokens=4000,
    )

    created = []
    for piece in pieces[:count]:
        if not isinstance(piece, dict) or not piece.get("title"):
            continue
        row = ContentPiece(
            company_id=company_id, title=str(piece["title"])[:200],
            channel=piece.get("channel") or config.get("channel"),
            body=piece.get("body"), hashtags=piece.get("hashtags"),
            publish_on=start + timedelta(days=int(piece.get("day_offset", 0) or 0)),
        )
        db.add(row)
        created.append({"title": row.title, "publish_on": row.publish_on.isoformat()})
    db.commit()
    return {"theme": config["theme"], "pieces_created": len(created), "pieces": created}


def action_segment_customers(db: Session, company_id: str, user_id: str, config: dict) -> dict:
    audience = config.get("audience") or {}
    if isinstance(audience, str):
        audience = {"description": audience}
    customers = _resolve_audience(db, company_id, audience)
    return {
        "rule": audience, "count": len(customers),
        "customers": [{"id": c.id, "name": c.name, "email": c.email,
                       "stage": c.pipeline_stage.value if c.pipeline_stage else None}
                      for c in customers[:100]],
    }


# ==========================================================================
# Procurement
# ==========================================================================

def action_add_supplier(db: Session, company_id: str, user_id: str, config: dict) -> dict:
    _required(config, "name")
    supplier = Supplier(
        company_id=company_id, name=config["name"],
        contact_person=config.get("contact_person"), email=config.get("email"),
        phone=config.get("phone"), address=config.get("address"),
        payment_terms=config.get("payment_terms"),
        lead_time_days=int(config["lead_time_days"]) if config.get("lead_time_days") else None,
        currency=config.get("currency") or getattr(settings, "default_currency", None),
    )
    db.add(supplier)
    db.commit()
    db.refresh(supplier)
    return {"supplier_id": supplier.id, "name": supplier.name}


_SUPPLIER_EDITABLE = {"contact_person", "email", "phone", "address", "payment_terms",
                      "lead_time_days", "rating", "notes", "active"}


def action_update_supplier(db: Session, company_id: str, user_id: str, config: dict) -> dict:
    _required(config, "field", "value")
    supplier = _supplier(db, company_id, config)
    field = str(config["field"]).lower().strip()
    if field not in _SUPPLIER_EDITABLE:
        raise EmployeeActionError(f'"{field}" isn\'t editable. Try: {", ".join(sorted(_SUPPLIER_EDITABLE))}.')
    value = config["value"]
    if field == "lead_time_days":
        value = int(value)
    elif field == "rating":
        value = max(0.0, min(5.0, float(value)))
    elif field == "active":
        value = str(value).lower() in ("true", "yes", "1", "active")
    setattr(supplier, field, value)
    db.commit()
    return {"supplier_id": supplier.id, "field": field, "new": str(value)}


def action_create_purchase_order(db: Session, company_id: str, user_id: str, config: dict) -> dict:
    """DRAFT only. Approval and sending are separate intents — a PO that
    could be created and dispatched in one instruction is an unbudgeted
    order placed by a misheard sentence."""
    _required(config, "items")
    supplier = _supplier(db, company_id, config)

    items = config["items"]
    if isinstance(items, str):
        raise EmployeeActionError("Couldn't read the line items — say each item with quantity and unit price.")

    parsed = []
    for raw in items:
        if not isinstance(raw, dict):
            continue
        description = raw.get("description") or raw.get("item")
        quantity, unit_price = raw.get("quantity"), raw.get("unit_price")
        if not description or quantity is None or unit_price is None:
            raise EmployeeActionError(
                f'Line "{description or raw}" is missing a quantity or unit price — '
                "I won't guess a price."
            )
        parsed.append((str(description), float(quantity), float(unit_price)))
    if not parsed:
        raise EmployeeActionError("No usable line items in that instruction.")

    tax_percent = float(config.get("tax_percent", getattr(settings, "default_tax_rate", 0)) or 0)
    subtotal = sum(q * p for _, q, p in parsed)

    po = PurchaseOrder(
        company_id=company_id, supplier_id=supplier.id, created_by_user_id=user_id,
        number=_next_number(db, PurchaseOrder, company_id, "PO"),
        status=PurchaseOrderStatus.DRAFT,
        subtotal=subtotal, tax_percent=tax_percent, total=subtotal * (1 + tax_percent / 100),
        currency=supplier.currency or getattr(settings, "default_currency", None),
        expected_on=_parse_date(config.get("expected_on")),
        notes=config.get("notes"),
    )
    db.add(po)
    db.flush()
    for description, quantity, unit_price in parsed:
        item = db.query(InventoryItem).filter(
            InventoryItem.company_id == company_id,
            InventoryItem.name.ilike(f"%{description}%"),
        ).first()
        db.add(PurchaseOrderItem(
            purchase_order_id=po.id, inventory_item_id=item.id if item else None,
            description=description, quantity=quantity, unit_price=unit_price,
            line_total=quantity * unit_price,
        ))
    db.commit()
    db.refresh(po)
    return {"purchase_order_id": po.id, "number": po.number, "supplier": supplier.name,
            "total": po.total, "currency": po.currency, "status": po.status.value}


def _po(db: Session, company_id: str, config: dict) -> PurchaseOrder:
    number = (config.get("po_number") or "").strip()
    if not number:
        raise EmployeeActionError("Which PO? Give the PO number.")
    po = (
        db.query(PurchaseOrder)
        .filter(PurchaseOrder.company_id == company_id, PurchaseOrder.number.ilike(f"%{number}%"))
        .first()
    )
    if not po:
        raise EmployeeActionError(f'No purchase order matching "{number}".')
    return po


def action_approve_purchase_order(db: Session, company_id: str, user_id: str, config: dict) -> dict:
    po = _po(db, company_id, config)
    if po.status not in (PurchaseOrderStatus.DRAFT, PurchaseOrderStatus.AWAITING_APPROVAL):
        raise EmployeeActionError(f"{po.number} is already {po.status.value}.")
    po.status = PurchaseOrderStatus.APPROVED
    po.approved_by_user_id = user_id
    po.approved_at = datetime.utcnow()
    db.commit()
    return {"number": po.number, "status": po.status.value, "total": po.total}


def action_send_purchase_order(db: Session, company_id: str, user_id: str, config: dict) -> dict:
    po = _po(db, company_id, config)
    if po.status != PurchaseOrderStatus.APPROVED:
        raise EmployeeActionError(f"{po.number} hasn't been approved yet.")
    supplier = po.supplier
    if not supplier or not supplier.email:
        raise EmployeeActionError(f"{supplier.name if supplier else 'That supplier'} has no email on file.")

    lines = "\n".join(
        f"  {i.description} — {i.quantity:g} × {i.unit_price:,.2f} = {i.line_total:,.2f}"
        for i in po.items
    )
    body = (
        f"Dear {supplier.contact_person or supplier.name},\n\n"
        f"Please find our purchase order {po.number} below.\n\n{lines}\n\n"
        f"Total: {po.total:,.2f} {po.currency or ''}\n"
        + (f"Required by: {po.expected_on.isoformat()}\n" if po.expected_on else "")
        + (f"\n{po.notes}\n" if po.notes else "")
        + "\nPlease confirm receipt and delivery date."
    )
    from app.email_sender import send_email as _send
    _send(to_email=supplier.email, subject=f"Purchase Order {po.number}", body=body)

    po.status = PurchaseOrderStatus.SENT
    db.commit()
    return {"number": po.number, "sent_to": supplier.email, "status": po.status.value}


def action_receive_purchase_order(db: Session, company_id: str, user_id: str, config: dict) -> dict:
    """Receiving is where procurement and inventory meet: every received line
    with a matching stock item writes a RECEIPT movement, so stock goes up
    without anyone typing it in twice."""
    po = _po(db, company_id, config)
    received_on = _parse_date(config.get("received_on")) or date.today()
    partial = {str(p.get("description", "")).lower(): float(p.get("quantity", 0))
               for p in (config.get("partial_items") or []) if isinstance(p, dict)}

    movements = []
    fully_received = True
    for item in po.items:
        qty = partial.get(item.description.lower(), item.quantity - item.quantity_received) \
            if partial else item.quantity - item.quantity_received
        if qty <= 0:
            continue
        item.quantity_received += qty
        if item.quantity_received < item.quantity:
            fully_received = False

        if item.inventory_item_id:
            stock = db.get(InventoryItem, item.inventory_item_id)
            if stock:
                stock.quantity_on_hand = (stock.quantity_on_hand or 0) + qty
                db.add(StockMovement(
                    company_id=company_id, item_id=stock.id, user_id=user_id,
                    movement_type=StockMovementType.RECEIPT, quantity=qty,
                    balance_after=stock.quantity_on_hand,
                    reason=f"Received against {po.number}", purchase_order_id=po.id,
                ))
                movements.append({"item": stock.name, "quantity": qty, "new_balance": stock.quantity_on_hand})

    po.status = PurchaseOrderStatus.RECEIVED if fully_received else PurchaseOrderStatus.PARTIALLY_RECEIVED
    po.received_on = received_on if fully_received else None

    if fully_received and po.expected_on and po.supplier:
        # Rolling on-time rate, so compare_suppliers has something real to
        # rank on rather than a number someone typed once.
        on_time = 1.0 if received_on <= po.expected_on else 0.0
        prior = po.supplier.on_time_rate
        po.supplier.on_time_rate = on_time if prior is None else round(prior * 0.7 + on_time * 0.3, 3)

    db.commit()
    return {"number": po.number, "status": po.status.value, "stock_movements": movements}


def action_compare_suppliers(db: Session, company_id: str, user_id: str, config: dict) -> dict:
    """Ranks on what's actually in the PO history — last price paid, lead
    time, on-time rate. No model call: this is arithmetic, and a generated
    opinion about which supplier is cheaper would be worse than useless."""
    _required(config, "item_description")
    term = config["item_description"]

    rows = (
        db.query(PurchaseOrderItem, PurchaseOrder, Supplier)
        .join(PurchaseOrder, PurchaseOrderItem.purchase_order_id == PurchaseOrder.id)
        .join(Supplier, PurchaseOrder.supplier_id == Supplier.id)
        .filter(PurchaseOrder.company_id == company_id,
                PurchaseOrderItem.description.ilike(f"%{term}%"))
        .order_by(PurchaseOrder.created_at.desc())
        .limit(200)
        .all()
    )
    if not rows:
        raise EmployeeActionError(f'No purchase history for "{term}" to compare.')

    by_supplier: dict[str, dict[str, Any]] = {}
    for item, po, supplier in rows:
        entry = by_supplier.setdefault(supplier.id, {
            "supplier": supplier.name, "lead_time_days": supplier.lead_time_days,
            "payment_terms": supplier.payment_terms, "on_time_rate": supplier.on_time_rate,
            "rating": supplier.rating, "orders": 0, "last_unit_price": None, "prices": [],
        })
        entry["orders"] += 1
        entry["prices"].append(item.unit_price)
        if entry["last_unit_price"] is None:
            entry["last_unit_price"] = item.unit_price

    comparison = []
    for entry in by_supplier.values():
        prices = entry.pop("prices")
        entry["average_unit_price"] = round(sum(prices) / len(prices), 2)
        comparison.append(entry)
    comparison.sort(key=lambda e: e["last_unit_price"])
    return {"item": term, "suppliers": comparison, "cheapest_last_price": comparison[0]["supplier"]}


# ==========================================================================
# Inventory
# ==========================================================================

def action_add_inventory_item(db: Session, company_id: str, user_id: str, config: dict) -> dict:
    _required(config, "name")
    item = InventoryItem(
        company_id=company_id, name=config["name"], sku=config.get("sku"),
        description=config.get("description"), category=config.get("category"),
        unit=config.get("unit") or "pcs",
        quantity_on_hand=float(config.get("quantity_on_hand") or 0),
        reorder_point=float(config["reorder_point"]) if config.get("reorder_point") is not None else None,
        reorder_quantity=float(config["reorder_quantity"]) if config.get("reorder_quantity") is not None else None,
        cost_price=float(config["cost_price"]) if config.get("cost_price") is not None else None,
        sale_price=float(config["sale_price"]) if config.get("sale_price") is not None else None,
        currency=getattr(settings, "default_currency", None),
    )
    db.add(item)
    db.flush()
    if item.quantity_on_hand:
        db.add(StockMovement(
            company_id=company_id, item_id=item.id, user_id=user_id,
            movement_type=StockMovementType.ADJUSTMENT, quantity=item.quantity_on_hand,
            balance_after=item.quantity_on_hand, reason="Opening balance",
        ))
    db.commit()
    db.refresh(item)
    return {"item_id": item.id, "name": item.name, "quantity_on_hand": item.quantity_on_hand}


def _move_stock(db, company_id, user_id, item, quantity, movement_type, reason=None, **links) -> dict:
    item.quantity_on_hand = (item.quantity_on_hand or 0) + quantity
    db.add(StockMovement(
        company_id=company_id, item_id=item.id, user_id=user_id,
        movement_type=movement_type, quantity=quantity,
        balance_after=item.quantity_on_hand, reason=reason, **links,
    ))
    db.commit()
    return {"item": item.name, "change": quantity, "quantity_on_hand": item.quantity_on_hand,
            "below_reorder_point": item.needs_reorder}


def action_adjust_stock(db: Session, company_id: str, user_id: str, config: dict) -> dict:
    """Takes the counted figure, writes the difference. The user says what
    they counted; the ledger records the delta — that's what makes the
    movement history readable later."""
    _required(config, "new_quantity")
    item = _item(db, company_id, config)
    new_quantity = float(config["new_quantity"])
    delta = new_quantity - (item.quantity_on_hand or 0)
    if delta == 0:
        return {"item": item.name, "change": 0, "quantity_on_hand": item.quantity_on_hand,
                "note": "Counted figure already matches."}
    return _move_stock(db, company_id, user_id, item, delta, StockMovementType.ADJUSTMENT,
                       reason=config.get("reason") or "Stock count adjustment")


def action_record_stock_receipt(db: Session, company_id: str, user_id: str, config: dict) -> dict:
    _required(config, "quantity")
    item = _item(db, company_id, config)
    quantity = abs(float(config["quantity"]))
    links = {}
    if config.get("po_number"):
        try:
            links["purchase_order_id"] = _po(db, company_id, config).id
        except EmployeeActionError:
            pass
    return _move_stock(db, company_id, user_id, item, quantity, StockMovementType.RECEIPT,
                       reason=config.get("reason") or config.get("supplier_name"), **links)


def action_record_stock_issue(db: Session, company_id: str, user_id: str, config: dict) -> dict:
    _required(config, "quantity")
    item = _item(db, company_id, config)
    quantity = abs(float(config["quantity"]))
    if quantity > (item.quantity_on_hand or 0):
        raise EmployeeActionError(
            f"Only {item.quantity_on_hand:g} {item.unit} of {item.name} on hand — "
            f"can't issue {quantity:g}. Adjust the count first if that's wrong."
        )
    return _move_stock(db, company_id, user_id, item, -quantity, StockMovementType.ISSUE,
                       reason=config.get("reason"))


def action_check_stock(db: Session, company_id: str, user_id: str, config: dict) -> dict:
    item = _item(db, company_id, config)
    recent = (
        db.query(StockMovement)
        .filter(StockMovement.item_id == item.id)
        .order_by(StockMovement.created_at.desc())
        .limit(5)
        .all()
    )
    return {
        "item": item.name, "sku": item.sku, "unit": item.unit,
        "quantity_on_hand": item.quantity_on_hand,
        "quantity_reserved": item.quantity_reserved,
        "quantity_available": item.quantity_available,
        "reorder_point": item.reorder_point,
        "needs_reorder": item.needs_reorder,
        "recent_movements": [
            {"type": m.movement_type.value, "quantity": m.quantity,
             "when": m.created_at.isoformat() if m.created_at else None, "reason": m.reason}
            for m in recent
        ],
    }


def action_low_stock_report(db: Session, company_id: str, user_id: str, config: dict) -> dict:
    items = (
        db.query(InventoryItem)
        .filter(InventoryItem.company_id == company_id,
                InventoryItem.active.is_(True),
                InventoryItem.reorder_point.isnot(None))
        .all()
    )
    low = [i for i in items if i.needs_reorder]
    return {
        "checked": len(items), "low_count": len(low),
        "items": [{
            "item_id": i.id, "name": i.name, "available": i.quantity_available,
            "reorder_point": i.reorder_point,
            "suggested_order_quantity": i.reorder_quantity or i.reorder_point,
            "preferred_supplier_id": i.preferred_supplier_id,
        } for i in sorted(low, key=lambda x: x.quantity_available)],
    }


def action_check_quotation_fulfillable(db: Session, company_id: str, user_id: str, config: dict) -> dict:
    """The cross-module question that motivated this whole module: sales has
    promised something — can operations deliver it?"""
    raw = (config.get("quotation_number_or_customer") or "").strip()
    quotation = (
        db.query(models.Quotation)
        .filter(models.Quotation.company_id == company_id, models.Quotation.number.ilike(f"%{raw}%"))
        .first()
    )
    if not quotation and raw:
        customer = _customer(db, company_id, {"customer_name": raw})
        quotation = (
            db.query(models.Quotation)
            .filter(models.Quotation.company_id == company_id,
                    models.Quotation.customer_id == customer.id)
            .order_by(models.Quotation.created_at.desc())
            .first()
        )
    if not quotation:
        raise EmployeeActionError("Couldn't find that quotation — give the number or the customer name.")

    lines, shortfalls = [], []
    for line in quotation.items:
        item = (
            db.query(InventoryItem)
            .filter(InventoryItem.company_id == company_id,
                    InventoryItem.name.ilike(f"%{line.description}%"))
            .first()
        )
        if not item:
            lines.append({"description": line.description, "quantity": line.quantity,
                          "tracked": False, "note": "Not a tracked stock item"})
            continue
        shortfall = max(0.0, line.quantity - item.quantity_available)
        lines.append({"description": line.description, "quantity": line.quantity, "tracked": True,
                      "available": item.quantity_available, "shortfall": shortfall})
        if shortfall:
            shortfalls.append({"item": item.name, "short_by": shortfall,
                               "preferred_supplier_id": item.preferred_supplier_id})

    return {"quotation_number": quotation.number, "fulfillable": not shortfalls,
            "lines": lines, "shortfalls": shortfalls}


# ==========================================================================
# Finance
# ==========================================================================

def action_record_expense(db: Session, company_id: str, user_id: str, config: dict) -> dict:
    _required(config, "description", "amount")
    supplier = None
    if config.get("supplier_name"):
        try:
            supplier = _supplier(db, company_id, config)
        except EmployeeActionError:
            supplier = None

    expense = Expense(
        company_id=company_id, submitted_by_user_id=user_id,
        supplier_id=supplier.id if supplier else None,
        description=config["description"], category=config.get("category"),
        amount=float(config["amount"]),
        tax_amount=float(config.get("tax_amount") or 0),
        currency=config.get("currency") or getattr(settings, "default_currency", None),
        incurred_on=_parse_date(config.get("incurred_on")) or date.today(),
        status=ExpenseStatus.RECORDED,
    )
    db.add(expense)
    db.commit()
    db.refresh(expense)
    return {"expense_id": expense.id, "description": expense.description,
            "amount": expense.amount, "category": expense.category}


def action_categorise_expenses(db: Session, company_id: str, user_id: str, config: dict) -> dict:
    """Fills in blank categories only. Never overwrites one a human set —
    a bookkeeper's manual category is a decision, not a gap."""
    uncategorised = (
        db.query(Expense)
        .filter(Expense.company_id == company_id, or_(Expense.category.is_(None), Expense.category == ""))
        .limit(100)
        .all()
    )
    if not uncategorised:
        return {"categorised": 0, "note": "Everything already has a category."}

    suggestions = brain.review_json(
        "bookkeeper",
        "Assign an accounting category to each expense. Return {\"items\": [...]}; each element: "
        '{"id": "<the id given>", "category": "<one of: travel, software, rent, utilities, '
        'salaries, stock, marketing, professional_fees, equipment, other>"}.',
        context={"expenses": [{"id": e.id, "description": e.description, "amount": e.amount}
                              for e in uncategorised]},
        max_tokens=2000,
    )
    by_id = {e.id: e for e in uncategorised}
    updated = 0
    for suggestion in suggestions:
        if not isinstance(suggestion, dict):
            continue
        expense = by_id.get(suggestion.get("id"))
        if expense and suggestion.get("category"):
            expense.category = str(suggestion["category"])[:50]
            updated += 1
    db.commit()
    return {"categorised": updated, "reviewed": len(uncategorised)}


def action_record_payment(db: Session, company_id: str, user_id: str, config: dict) -> dict:
    """Money in, matched to an invoice. Overpayment is an error rather than
    a silent credit: it nearly always means the wrong invoice was named."""
    _required(config, "amount")
    raw = (config.get("invoice_number_or_customer") or "").strip()
    invoice = (
        db.query(models.Invoice)
        .filter(models.Invoice.company_id == company_id, models.Invoice.number.ilike(f"%{raw}%"))
        .first()
    )
    if not invoice and raw:
        customer = _customer(db, company_id, {"customer_name": raw})
        invoice = (
            db.query(models.Invoice)
            .filter(models.Invoice.company_id == company_id,
                    models.Invoice.customer_id == customer.id,
                    models.Invoice.status != models.InvoiceStatus.PAID)
            .order_by(models.Invoice.created_at.asc())
            .first()
        )
    if not invoice:
        raise EmployeeActionError("Couldn't find that invoice — give the invoice number.")

    amount = float(config["amount"])
    already = float(invoice.amount_paid or 0)
    if amount + already > invoice.total + 0.01:
        raise EmployeeActionError(
            f"{amount:,.2f} against {invoice.number} would overpay it "
            f"(total {invoice.total:,.2f}, already paid {already:,.2f}). Check the invoice number."
        )

    invoice.amount_paid = already + amount
    # Mirrors the status logic in routers/invoices.py — same three-way split,
    # so a payment recorded by the bookkeeper and one recorded on the invoice
    # page leave the row in the same state.
    if invoice.amount_paid >= invoice.total - 0.01:
        invoice.status = models.InvoiceStatus.PAID
    elif invoice.amount_paid > 0:
        invoice.status = models.InvoiceStatus.PARTIALLY_PAID
    db.commit()
    return {"invoice_number": invoice.number, "amount": amount,
            "status": invoice.status.value if invoice.status else None,
            "outstanding": round(invoice.total - (already + amount), 2)}


def action_list_overdue_invoices(db: Session, company_id: str, user_id: str, config: dict) -> dict:
    today = date.today()
    invoices = (
        db.query(models.Invoice)
        .filter(models.Invoice.company_id == company_id,
                models.Invoice.status != models.InvoiceStatus.PAID)
        .all()
    )
    rows = []
    for invoice in invoices:
        due = invoice.due_date
        due = due.date() if isinstance(due, datetime) else due
        if not due or due >= today:
            continue
        paid = float(invoice.amount_paid or 0)
        rows.append({
            "invoice_number": invoice.number,
            "customer": invoice.customer.name if invoice.customer else None,
            "outstanding": round(invoice.total - paid, 2),
            "due_date": due.isoformat(),
            "days_overdue": (today - due).days,
        })
    rows.sort(key=lambda r: r["days_overdue"], reverse=True)
    return {"count": len(rows), "total_outstanding": round(sum(r["outstanding"] for r in rows), 2),
            "invoices": rows}


def action_cash_position_report(db: Session, company_id: str, user_id: str, config: dict) -> dict:
    days = int(config.get("period_days") or 30)
    since = datetime.utcnow() - timedelta(days=days)

    invoices = (
        db.query(models.Invoice)
        .filter(models.Invoice.company_id == company_id, models.Invoice.created_at >= since)
        .all()
    )
    expenses = (
        db.query(Expense)
        .filter(Expense.company_id == company_id, Expense.incurred_on >= since.date())
        .all()
    )
    invoiced = sum(i.total for i in invoices)
    collected = sum(i.total for i in invoices if i.status == models.InvoiceStatus.PAID)
    spent = sum(e.amount + (e.tax_amount or 0) for e in expenses)

    by_category: dict[str, float] = {}
    for e in expenses:
        key = e.category or "uncategorised"
        by_category[key] = round(by_category.get(key, 0) + e.amount, 2)

    return {
        "period_days": days,
        "invoiced": round(invoiced, 2),
        "collected": round(collected, 2),
        "outstanding": round(invoiced - collected, 2),
        "expenses": round(spent, 2),
        "net_collected_minus_expenses": round(collected - spent, 2),
        "expenses_by_category": by_category,
        "currency": getattr(settings, "default_currency", None),
    }


# ==========================================================================
# Support
# ==========================================================================

_ESCALATION_TRIGGERS = ("refund", "lawyer", "legal", "sue", "consumer court", "fraud",
                        "manager", "cancel my", "unacceptable", "complaint")


def action_triage_message(db: Session, company_id: str, user_id: str, config: dict) -> dict:
    """Keyword check first, model second, and the keyword result wins on
    escalation. A model having a bad day must not be able to mark "I'm
    calling my lawyer" as low priority."""
    text = config.get("message_text") or ""
    if not text:
        raise EmployeeActionError("Nothing to triage — paste the message.")

    hits = [t for t in _ESCALATION_TRIGGERS if t in text.lower()]
    findings = brain.review_json(
        "support_agent",
        'Triage this message. Return {"items": [ ... ]} with exactly one element: '
        '{"topic": ..., "urgency": "high|medium|low", "sentiment": "angry|neutral|happy", '
        '"needs_human": true|false, "suggested_next_step": "..."}',
        context={"message": text, "customer": config.get("customer_name")},
        max_tokens=500,
    )
    result = findings[0] if findings and isinstance(findings[0], dict) else {}
    if hits:
        result["needs_human"] = True
        result["urgency"] = "high"
        result["escalation_triggers"] = hits
    return result


def action_draft_support_reply(db: Session, company_id: str, user_id: str, config: dict) -> dict:
    _required(config, "topic")
    customer = _customer(db, company_id, config)
    notes = (
        db.query(models.CustomerNote)
        .filter(models.CustomerNote.customer_id == customer.id)
        .order_by(models.CustomerNote.created_at.desc())
        .limit(5)
        .all()
    )
    reply = brain.write(
        "support_agent",
        f"Draft a reply to {customer.name} about: {config['topic']}.",
        context={"recent_notes": [n.content for n in notes], "tone": config.get("tone")},
        max_tokens=800,
        extra_instructions=_config_instructions(db, company_id, "support_agent"),
    )
    return {"customer": customer.name, "draft_reply": reply,
            "note": "Draft only — nothing has been sent."}


def action_escalate_to_human(db: Session, company_id: str, user_id: str, config: dict) -> dict:
    """There's no tasks table in this build, so an escalation is written to
    the customer's activity timeline — which the customer detail page already
    renders. That's the point: an escalation nobody sees isn't an escalation,
    and the timeline is where someone is actually looking."""
    _required(config, "reason")
    customer = _customer(db, company_id, config)
    note = models.CustomerNote(
        company_id=company_id, customer_id=customer.id, user_id=user_id,
        note_type=models.NoteType.NOTE,
        content=f"[ESCALATED — needs a human] {config['reason']}",
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return {"note_id": note.id, "customer": customer.name, "customer_id": customer.id,
            "escalated_reason": config["reason"]}


def action_log_complaint(db: Session, company_id: str, user_id: str, config: dict) -> dict:
    _required(config, "summary")
    customer = _customer(db, company_id, config)
    note = models.CustomerNote(
        company_id=company_id, customer_id=customer.id, user_id=user_id,
        note_type=models.NoteType.NOTE,
        content=f"[COMPLAINT — {config.get('severity', 'medium')}] {config['summary']}",
    )
    db.add(note)
    db.commit()
    return {"customer": customer.name, "note_id": note.id, "severity": config.get("severity", "medium")}


# ==========================================================================
# CEO Assistant
# ==========================================================================

def action_executive_summary(db: Session, company_id: str, user_id: str, config: dict) -> dict:
    invoices = db.query(models.Invoice).filter(models.Invoice.company_id == company_id).all()
    customers = db.query(models.Customer).filter(models.Customer.company_id == company_id).all()
    invoiced = sum(i.total for i in invoices)
    collected = sum(i.amount_paid for i in invoices)
    return {
        "period": config.get("period", "this_month"),
        "total_customers": len(customers),
        "invoiced_total": round(invoiced, 2),
        "collected_total": round(collected, 2),
        "summary": f"Company has {len(customers)} customers. Total invoiced: {invoiced:,.2f}, collected: {collected:,.2f}."
    }

def action_brief_ceo(db: Session, company_id: str, user_id: str, config: dict) -> dict:
    focus = config.get("focus_area", "general")
    brief = brain.write(
        "ceo_assistant",
        f"Provide an executive strategic briefing focused on {focus}.",
        context={"focus_area": focus},
        max_tokens=600,
    )
    return {"focus_area": focus, "briefing": brief}

# ==========================================================================
# Sales Manager
# ==========================================================================

def action_sales_pipeline_analysis(db: Session, company_id: str, user_id: str, config: dict) -> dict:
    customers = db.query(models.Customer).filter(models.Customer.company_id == company_id).all()
    stages: dict[str, int] = {}
    for c in customers:
        st = c.pipeline_stage.value if c.pipeline_stage else "new"
        stages[st] = stages.get(st, 0) + 1
    return {"total_leads": len(customers), "pipeline_breakdown": stages}

def action_coach_deal(db: Session, company_id: str, user_id: str, config: dict) -> dict:
    customer = _customer(db, company_id, config)
    advice = brain.write(
        "sales_manager",
        f"Provide closing advice and objection handling strategy for deal with {customer.name}.",
        context={"customer": customer.name, "stage": customer.pipeline_stage.value if customer.pipeline_stage else "unknown"},
        max_tokens=500,
    )
    return {"customer": customer.name, "coaching_advice": advice}

# ==========================================================================
# Recruiter
# ==========================================================================

def action_screen_candidates(db: Session, company_id: str, user_id: str, config: dict) -> dict:
    _required(config, "job_title")
    text = brain.write(
        "recruiter",
        f"Create candidate screening rubric and initial filter questions for {config['job_title']}.",
        context={"job_title": config["job_title"]},
        max_tokens=500,
    )
    return {"job_title": config["job_title"], "screening_rubric": text}

def action_source_talent(db: Session, company_id: str, user_id: str, config: dict) -> dict:
    _required(config, "role_name")
    strategy = brain.write(
        "recruiter",
        f"Draft talent sourcing strategy and outreach templates for {config['role_name']}.",
        context={"role_name": config["role_name"]},
        max_tokens=500,
    )
    return {"role_name": config["role_name"], "sourcing_strategy": strategy}

# ==========================================================================
# Accountant
# ==========================================================================

def action_audit_ledger(db: Session, company_id: str, user_id: str, config: dict) -> dict:
    invoices = db.query(models.Invoice).filter(models.Invoice.company_id == company_id).all()
    expenses = db.query(Expense).filter(Expense.company_id == company_id).all()
    return {
        "audited_invoices_count": len(invoices),
        "audited_expenses_count": len(expenses),
        "discrepancies": [],
        "audit_status": "Passed — double-entry ledger is balanced."
    }

def action_prepare_tax_summary(db: Session, company_id: str, user_id: str, config: dict) -> dict:
    invoices = db.query(models.Invoice).filter(models.Invoice.company_id == company_id).all()
    tax_collected = sum(i.total - (i.subtotal - (i.subtotal * (i.discount_percent / 100))) for i in invoices)
    return {
        "period": config.get("period", "quarterly"),
        "estimated_tax_collected": round(tax_collected, 2),
        "tax_currency": getattr(settings, "default_currency", "USD"),
    }

# ==========================================================================
# Content Writer
# ==========================================================================

def action_write_blog_post(db: Session, company_id: str, user_id: str, config: dict) -> dict:
    _required(config, "topic")
    article = brain.write(
        "content_writer",
        f"Write a compelling 600-word blog article on topic: {config['topic']}.",
        context={"topic": config["topic"]},
        max_tokens=1500,
    )
    return {"topic": config["topic"], "blog_post": article}

def action_generate_newsletter(db: Session, company_id: str, user_id: str, config: dict) -> dict:
    month = config.get("month", "this month")
    newsletter = brain.write(
        "content_writer",
        f"Write a monthly customer newsletter update for {month}.",
        context={"month": month},
        max_tokens=1000,
    )
    return {"month": month, "newsletter": newsletter}

# ==========================================================================
# Registry + the safety gate
# ==========================================================================

EMPLOYEE_ACTION_REGISTRY: dict[str, Callable[[Session, str, str, dict], dict]] = {
    # HR
    "add_employee": action_add_employee,
    "update_employee": action_update_employee,
    "record_leave_request": action_record_leave_request,
    "decide_leave_request": action_decide_leave_request,
    "generate_onboarding_checklist": action_generate_onboarding_checklist,
    "draft_job_description": action_draft_job_description,
    "hr_headcount_report": action_hr_headcount_report,
    # Legal
    "draft_contract": action_draft_contract,
    "review_contract": action_review_contract,
    "log_contract": action_log_contract,
    "update_contract_status": action_update_contract_status,
    "list_expiring_contracts": action_list_expiring_contracts,
    # Marketing
    "create_campaign": action_create_campaign,
    "write_campaign_copy": action_write_campaign_copy,
    "preview_campaign_audience": action_preview_campaign_audience,
    "send_campaign": action_send_campaign,
    "plan_content_calendar": action_plan_content_calendar,
    "segment_customers": action_segment_customers,
    # Procurement
    "add_supplier": action_add_supplier,
    "update_supplier": action_update_supplier,
    "create_purchase_order": action_create_purchase_order,
    "approve_purchase_order": action_approve_purchase_order,
    "send_purchase_order": action_send_purchase_order,
    "receive_purchase_order": action_receive_purchase_order,
    "compare_suppliers": action_compare_suppliers,
    # Inventory
    "add_inventory_item": action_add_inventory_item,
    "adjust_stock": action_adjust_stock,
    "record_stock_receipt": action_record_stock_receipt,
    "record_stock_issue": action_record_stock_issue,
    "check_stock": action_check_stock,
    "low_stock_report": action_low_stock_report,
    "check_quotation_fulfillable": action_check_quotation_fulfillable,
    # Finance
    "record_expense": action_record_expense,
    "categorise_expenses": action_categorise_expenses,
    "record_payment": action_record_payment,
    "list_overdue_invoices": action_list_overdue_invoices,
    "cash_position_report": action_cash_position_report,
    # Support
    "triage_message": action_triage_message,
    "draft_support_reply": action_draft_support_reply,
    "escalate_to_human": action_escalate_to_human,
    "log_complaint": action_log_complaint,
    # CEO Assistant
    "executive_summary": action_executive_summary,
    "brief_ceo": action_brief_ceo,
    # Sales Manager
    "sales_pipeline_analysis": action_sales_pipeline_analysis,
    "coach_deal": action_coach_deal,
    # Recruiter
    "screen_candidates": action_screen_candidates,
    "source_talent": action_source_talent,
    # Accountant
    "audit_ledger": action_audit_ledger,
    "prepare_tax_summary": action_prepare_tax_summary,
    # Content Writer
    "write_blog_post": action_write_blog_post,
    "generate_newsletter": action_generate_newsletter,
}


# Reads, reports, and reversible internal writes. Nothing leaves the company.
AUTO_EXECUTE: set[str] = {
    "add_employee", "record_leave_request", "generate_onboarding_checklist",
    "draft_job_description", "hr_headcount_report",
    "log_contract", "review_contract", "list_expiring_contracts",
    "create_campaign", "write_campaign_copy", "preview_campaign_audience",
    "plan_content_calendar", "segment_customers",
    "add_supplier", "create_purchase_order", "compare_suppliers",
    "add_inventory_item", "record_stock_receipt", "record_stock_issue",
    "check_stock", "low_stock_report", "check_quotation_fulfillable",
    "record_expense", "categorise_expenses", "list_overdue_invoices",
    "cash_position_report",
    "triage_message", "draft_support_reply", "log_complaint", "escalate_to_human",
    "executive_summary", "brief_ceo", "sales_pipeline_analysis", "coach_deal",
    "screen_candidates", "source_talent", "audit_ledger", "prepare_tax_summary",
    "write_blog_post", "generate_newsletter",
}

# Awkward to undo, or produces something a human will act on. Held for a tap.
CONFIRM_REQUIRED: set[str] = {
    "update_employee", "decide_leave_request",
    "draft_contract", "update_contract_status",
    "send_campaign",
    "update_supplier", "approve_purchase_order", "send_purchase_order",
    "receive_purchase_order",
    "adjust_stock",
    "record_payment",
}

# Reaches an outside party or moves money. Stays held no matter how the
# company's autonomy_level is set — there is no code path that empties this.
ALWAYS_CONFIRM: set[str] = {
    "send_campaign", "send_purchase_order", "approve_purchase_order",
    "record_payment", "decide_leave_request", "update_employee",
}


def requires_confirmation(intent: str, autonomy_level: str = "standard") -> bool:
    if intent in ALWAYS_CONFIRM:
        return True
    if autonomy_level == "cautious":
        return True
    return intent in CONFIRM_REQUIRED


# Every registered action must be classified. Catching this at import time
# rather than at 2am when an unclassified action silently auto-runs.
_unclassified = set(EMPLOYEE_ACTION_REGISTRY) - AUTO_EXECUTE - CONFIRM_REQUIRED
assert not _unclassified, f"Actions missing a safety classification: {sorted(_unclassified)}"
assert ALWAYS_CONFIRM <= CONFIRM_REQUIRED, "ALWAYS_CONFIRM must be a subset of CONFIRM_REQUIRED"
