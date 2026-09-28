import json
import logging
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import get_current_user
from app.models import User, Invoice, Customer
from app.workflow_models import Workflow, WorkflowStep, WorkflowRun, WorkflowRunStep
from app.workflow_engine import trigger_event

logger = logging.getLogger("routers.workflows")
router = APIRouter(prefix="/api/workflows", tags=["workflows"])


class WorkflowStepSchema(BaseModel):
    step_order: int
    name: str
    action_type: str
    config_json: Optional[Dict[str, Any]] = None


class WorkflowCreateSchema(BaseModel):
    name: str
    description: Optional[str] = None
    trigger_type: str
    is_active: bool = True
    steps: List[WorkflowStepSchema]


class TestTriggerSchema(BaseModel):
    event_type: str
    invoice_id: Optional[str] = None
    customer_id: Optional[str] = None
    amount: Optional[float] = None


PREBUILT_TEMPLATES = [
    {
        "id": "tpl_payment_chain",
        "name": "Payment Received → Receipt PDF → CRM Update → Task → Email & WhatsApp",
        "description": "Complete payment processing automation: when an invoice payment is received, generates a receipt PDF, moves the customer pipeline stage to 'Won', creates a sales follow-up task, and sends email + WhatsApp notifications.",
        "trigger_type": "payment_received",
        "steps": [
            {
                "step_order": 1,
                "name": "Generate Payment Receipt PDF",
                "action_type": "generate_receipt",
                "config_json": {}
            },
            {
                "step_order": 2,
                "name": "Update Customer Stage to Won",
                "action_type": "update_crm_stage",
                "config_json": {"stage": "won"}
            },
            {
                "step_order": 3,
                "name": "Create Sales Follow-up Task",
                "action_type": "create_task",
                "config_json": {"title": "Send Thank You Gift / Onboarding Pack", "priority": "normal"}
            },
            {
                "step_order": 4,
                "name": "Send Email Receipt to Customer",
                "action_type": "send_email",
                "config_json": {
                    "subject": "Payment Received & Receipt — Invoice #{invoice_number}",
                    "body": "Dear {customer_name},\n\nWe have received your payment. Attached is your official receipt.\n\nThank you for choosing us!"
                }
            },
            {
                "step_order": 5,
                "name": "Send WhatsApp Confirmation",
                "action_type": "send_whatsapp",
                "config_json": {
                    "message": "Hi {customer_name}! Your payment of {amount} for Invoice #{invoice_number} has been received. Thank you!"
                }
            }
        ]
    },
    {
        "id": "tpl_quotation_approved",
        "name": "Quotation Approved → Update CRM → Notify Team",
        "description": "When a quotation is marked approved, moves customer to 'Proposal' stage and notifies the team.",
        "trigger_type": "quotation_approved",
        "steps": [
            {
                "step_order": 1,
                "name": "Move Stage to Proposal / Negotiation",
                "action_type": "update_crm_stage",
                "config_json": {"stage": "proposal"}
            },
            {
                "step_order": 2,
                "name": "Create Task to Convert to Invoice",
                "action_type": "create_task",
                "config_json": {"title": "Convert Approved Quotation to Invoice", "priority": "high"}
            }
        ]
    },
    {
        "id": "tpl_customer_welcome",
        "name": "New Customer Created → Send Welcome WhatsApp & Task",
        "description": "When a new lead or customer is created in CRM, sends a welcome WhatsApp message and creates an initial contact task.",
        "trigger_type": "customer_created",
        "steps": [
            {
                "step_order": 1,
                "name": "Send Welcome WhatsApp",
                "action_type": "send_whatsapp",
                "config_json": {"message": "Welcome {customer_name}! Thank you for reaching out. How can we assist you today?"}
            },
            {
                "step_order": 2,
                "name": "Create Outreach Task",
                "action_type": "create_task",
                "config_json": {"title": "Initial Lead Discovery Call", "priority": "normal"}
            }
        ]
    }
]


@router.get("")
def list_workflows(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    workflows = db.query(Workflow).filter(
        Workflow.company_id == current_user.company_id
    ).order_by(Workflow.created_at.desc()).all()

    return [
        {
            "id": w.id,
            "name": w.name,
            "description": w.description,
            "trigger_type": w.trigger_type,
            "is_active": w.is_active,
            "created_at": w.created_at.isoformat() if w.created_at else None,
            "steps": [
                {
                    "id": s.id,
                    "step_order": s.step_order,
                    "name": s.name,
                    "action_type": s.action_type,
                    "config_json": json.loads(s.config_json) if s.config_json else {}
                }
                for s in w.steps
            ],
            "runs_count": len(w.runs)
        }
        for w in workflows
    ]


@router.get("/templates")
def list_workflow_templates():
    return PREBUILT_TEMPLATES


@router.post("/templates/{template_id}/enable")
def enable_workflow_template(
    template_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    tpl = next((t for t in PREBUILT_TEMPLATES if t["id"] == template_id), None)
    if not tpl:
        raise HTTPException(status_code=404, detail="Template not found")

    wf = Workflow(
        company_id=current_user.company_id,
        name=tpl["name"],
        description=tpl["description"],
        trigger_type=tpl["trigger_type"],
        is_active=True,
    )
    db.add(wf)
    db.flush()

    for step_data in tpl["steps"]:
        step = WorkflowStep(
            workflow_id=wf.id,
            step_order=step_data["step_order"],
            name=step_data["name"],
            action_type=step_data["action_type"],
            config_json=json.dumps(step_data.get("config_json", {}))
        )
        db.add(step)

    db.commit()
    return {"status": "success", "workflow_id": wf.id}


@router.post("")
def create_workflow(
    payload: WorkflowCreateSchema,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    wf = Workflow(
        company_id=current_user.company_id,
        name=payload.name,
        description=payload.description,
        trigger_type=payload.trigger_type,
        is_active=payload.is_active,
    )
    db.add(wf)
    db.flush()

    for s_data in payload.steps:
        step = WorkflowStep(
            workflow_id=wf.id,
            step_order=s_data.step_order,
            name=s_data.name,
            action_type=s_data.action_type,
            config_json=json.dumps(s_data.config_json or {})
        )
        db.add(step)

    db.commit()
    return {"status": "created", "workflow_id": wf.id}


@router.put("/{workflow_id}")
def update_workflow(
    workflow_id: str,
    payload: WorkflowCreateSchema,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    wf = db.query(Workflow).filter(
        Workflow.company_id == current_user.company_id,
        Workflow.id == workflow_id
    ).first()

    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")

    wf.name = payload.name
    wf.description = payload.description
    wf.trigger_type = payload.trigger_type
    wf.is_active = payload.is_active

    # Re-create steps
    db.query(WorkflowStep).filter(WorkflowStep.workflow_id == wf.id).delete()
    db.flush()

    for s_data in payload.steps:
        step = WorkflowStep(
            workflow_id=wf.id,
            step_order=s_data.step_order,
            name=s_data.name,
            action_type=s_data.action_type,
            config_json=json.dumps(s_data.config_json or {})
        )
        db.add(step)

    db.commit()
    return {"status": "updated"}


@router.delete("/{workflow_id}")
def delete_workflow(
    workflow_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    wf = db.query(Workflow).filter(
        Workflow.company_id == current_user.company_id,
        Workflow.id == workflow_id
    ).first()

    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")

    db.delete(wf)
    db.commit()
    return {"status": "deleted"}


@router.get("/runs")
def list_workflow_runs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    runs = db.query(WorkflowRun).filter(
        WorkflowRun.company_id == current_user.company_id
    ).order_by(WorkflowRun.started_at.desc()).limit(30).all()

    return [
        {
            "id": r.id,
            "workflow_name": r.workflow.name if r.workflow else "Deleted Workflow",
            "trigger_event": r.trigger_event,
            "status": r.status.value,
            "error_message": r.error_message,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            "steps": [
                {
                    "id": sr.id,
                    "step_order": sr.step_order,
                    "action_type": sr.action_type,
                    "status": sr.status.value,
                    "output": json.loads(sr.output_json) if sr.output_json else None,
                    "error": sr.error_message,
                    "executed_at": sr.executed_at.isoformat() if sr.executed_at else None,
                }
                for sr in r.step_runs
            ]
        }
        for r in runs
    ]


@router.post("/test-trigger")
def test_trigger_workflow(
    payload: TestTriggerSchema,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    event_payload = {
        "invoice_id": payload.invoice_id,
        "customer_id": payload.customer_id,
        "amount": payload.amount,
        "user_id": current_user.id
    }

    # If test trigger payload missing invoice_id or customer_id, attempt auto-select
    if not payload.invoice_id:
        inv = db.query(Invoice).filter(Invoice.company_id == current_user.company_id).first()
        if inv:
            event_payload["invoice_id"] = inv.id
            event_payload["customer_id"] = inv.customer_id
            event_payload["amount"] = inv.total

    if not event_payload.get("customer_id"):
        cust = db.query(Customer).filter(Customer.company_id == current_user.company_id).first()
        if cust:
            event_payload["customer_id"] = cust.id

    results = trigger_event(
        db=db,
        company_id=current_user.company_id,
        event_type=payload.event_type,
        payload=event_payload
    )

    return {"status": "triggered", "event_type": payload.event_type, "results": results}
