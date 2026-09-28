from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas, crm_assistant
from app.auth import get_current_user, require_role
from app.config import settings

router = APIRouter(prefix="/api/customers", tags=["customers"])


def _get_owned_customer(db: Session, current_user: models.User, customer_id: str) -> models.Customer:
    customer = (
        db.query(models.Customer)
        .filter(models.Customer.id == customer_id, models.Customer.company_id == current_user.company_id)
        .first()
    )
    if not customer:
        raise HTTPException(404, "Customer not found")
    return customer


@router.get("", response_model=list[schemas.CustomerOut])
def list_customers(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return (
        db.query(models.Customer)
        .filter(models.Customer.company_id == current_user.company_id)
        .order_by(models.Customer.created_at.desc())
        .all()
    )


@router.post("", response_model=schemas.CustomerOut)
def create_customer(
    payload: schemas.CustomerCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    customer = models.Customer(company_id=current_user.company_id, **payload.model_dump())
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer


@router.get("/{customer_id}", response_model=schemas.CustomerOut)
def get_customer(
    customer_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return _get_owned_customer(db, current_user, customer_id)


@router.put("/{customer_id}", response_model=schemas.CustomerOut)
def update_customer(
    customer_id: str,
    payload: schemas.CustomerCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    customer = _get_owned_customer(db, current_user, customer_id)
    for k, v in payload.model_dump().items():
        setattr(customer, k, v)
    db.commit()
    db.refresh(customer)
    return customer


@router.delete("/{customer_id}")
def delete_customer(
    customer_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role(models.UserRole.OWNER, models.UserRole.ADMIN)),
):
    customer = _get_owned_customer(db, current_user, customer_id)
    db.delete(customer)
    db.commit()
    return {"ok": True}


@router.patch("/{customer_id}/stage", response_model=schemas.CustomerOut)
def update_pipeline_stage(
    customer_id: str,
    payload: schemas.PipelineStageUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    customer = _get_owned_customer(db, current_user, customer_id)
    old_stage = customer.pipeline_stage
    customer.pipeline_stage = payload.pipeline_stage

    if old_stage != payload.pipeline_stage:
        db.add(models.CustomerNote(
            company_id=current_user.company_id,
            customer_id=customer.id,
            user_id=current_user.id,
            note_type=models.NoteType.STATUS_CHANGE,
            content=f"Pipeline stage changed from {old_stage.value} to {payload.pipeline_stage.value}.",
        ))

    db.commit()
    db.refresh(customer)
    return customer


@router.post("/{customer_id}/notes", response_model=schemas.CustomerNoteOut)
def create_note(
    customer_id: str,
    payload: schemas.CustomerNoteCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _get_owned_customer(db, current_user, customer_id)  # 404s if not owned
    note = models.CustomerNote(
        company_id=current_user.company_id,
        customer_id=customer_id,
        user_id=current_user.id,
        note_type=payload.note_type,
        content=payload.content,
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return schemas.CustomerNoteOut(
        id=note.id,
        customer_id=note.customer_id,
        note_type=note.note_type,
        content=note.content,
        created_at=note.created_at,
        user_name=current_user.name,
    )


@router.get("/{customer_id}/activity", response_model=list[schemas.ActivityItem])
def get_activity(
    customer_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _get_owned_customer(db, current_user, customer_id)  # 404s if not owned

    notes = (
        db.query(models.CustomerNote)
        .filter(
            models.CustomerNote.company_id == current_user.company_id,
            models.CustomerNote.customer_id == customer_id,
        )
        .all()
    )
    emails = (
        db.query(models.EmailMessage)
        .filter(
            models.EmailMessage.company_id == current_user.company_id,
            models.EmailMessage.customer_id == customer_id,
        )
        .all()
    )

    items: list[schemas.ActivityItem] = []
    for n in notes:
        items.append(schemas.ActivityItem(
            kind="note",
            id=n.id,
            created_at=n.created_at,
            note_type=n.note_type.value,
            content=n.content,
            user_name=n.user.name if n.user else None,
        ))
    for e in emails:
        items.append(schemas.ActivityItem(
            kind="email",
            id=e.id,
            created_at=e.created_at,
            subject=e.subject,
            content=e.body,
            to_email=e.to_email,
            status=e.status.value,
            error_message=e.error_message,
            quotation_id=e.quotation_id,
            invoice_id=e.invoice_id,
        ))

    items.sort(key=lambda i: i.created_at, reverse=True)
    return items


@router.post("/{customer_id}/ai-summary", response_model=schemas.AISummaryResponse)
def generate_ai_summary(
    customer_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    customer = _get_owned_customer(db, current_user, customer_id)

    quotations = customer.quotations
    invoices = customer.invoices
    paid_invoices = [i for i in invoices if i.status == models.InvoiceStatus.PAID]
    outstanding_total = sum(i.total - i.amount_paid for i in invoices if i.status != models.InvoiceStatus.PAID)
    currency = invoices[0].currency if invoices else (quotations[0].currency if quotations else settings.default_currency)

    email_count = (
        db.query(models.EmailMessage)
        .filter(
            models.EmailMessage.company_id == current_user.company_id,
            models.EmailMessage.customer_id == customer_id,
        )
        .count()
    )

    recent_notes = (
        db.query(models.CustomerNote)
        .filter(
            models.CustomerNote.company_id == current_user.company_id,
            models.CustomerNote.customer_id == customer_id,
        )
        .order_by(models.CustomerNote.created_at.desc())
        .limit(5)
        .all()
    )
    recent_activity = "\n".join(f"- [{n.note_type.value}] {n.content}" for n in recent_notes)

    stats = {
        "quotation_count": len(quotations),
        "invoice_count": len(invoices),
        "paid_invoice_count": len(paid_invoices),
        "outstanding_total": outstanding_total,
        "currency": currency,
        "email_count": email_count,
        "pipeline_stage": customer.pipeline_stage.value,
    }

    result = crm_assistant.generate_customer_summary(
        customer_name=customer.name,
        stats=stats,
        recent_activity=recent_activity,
    )

    customer.ai_relationship_summary = result["summary"]
    customer.ai_summary_generated_at = datetime.utcnow()
    db.commit()
    db.refresh(customer)

    return schemas.AISummaryResponse(
        summary=customer.ai_relationship_summary,
        generated_at=customer.ai_summary_generated_at,
    )
