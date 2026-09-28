from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.auth import get_current_user
from app.email_sender import send_email, EmailSendError
from app.pdf_generator import generate_quotation_pdf, generate_invoice_pdf
from app.followup_scheduler import check_and_create_followups

router = APIRouter(prefix="/api/follow-ups", tags=["follow-ups"])


def _get_owned_draft(db: Session, current_user: models.User, email_id: str) -> models.EmailMessage:
    row = (
        db.query(models.EmailMessage)
        .filter(
            models.EmailMessage.id == email_id,
            models.EmailMessage.company_id == current_user.company_id,
            models.EmailMessage.auto_generated == True,  # noqa: E712
        )
        .first()
    )
    if not row:
        raise HTTPException(404, "Follow-up draft not found")
    return row


@router.get("", response_model=list[schemas.FollowUpOut])
def list_followups(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    rows = (
        db.query(models.EmailMessage)
        .filter(
            models.EmailMessage.company_id == current_user.company_id,
            models.EmailMessage.auto_generated == True,  # noqa: E712
            models.EmailMessage.status == models.EmailStatus.DRAFT,
            models.EmailMessage.dismissed == False,  # noqa: E712
        )
        .order_by(models.EmailMessage.created_at.desc())
        .all()
    )
    return [
        schemas.FollowUpOut(
            id=r.id,
            customer_id=r.customer_id,
            customer_name=r.customer.name if r.customer else "Unknown",
            to_email=r.to_email,
            subject=r.subject,
            body=r.body,
            parent_email_id=r.parent_email_id,
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.post("/check-now", response_model=schemas.FollowUpCheckResult)
def check_now(current_user: models.User = Depends(get_current_user)):
    """Manually trigger the scheduler's check for this company — useful for
    testing, or for a "check now" button instead of waiting for the interval."""
    created = check_and_create_followups(company_id=current_user.company_id)
    return schemas.FollowUpCheckResult(drafts_created=created)


@router.post("/{email_id}/send", response_model=schemas.EmailOut)
def send_followup(
    email_id: str,
    payload: schemas.FollowUpSendRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    draft = _get_owned_draft(db, current_user, email_id)

    subject = payload.subject or draft.subject
    body = payload.body or draft.body

    attachment_bytes, attachment_filename = None, None
    if payload.attach_pdf and draft.quotation_id:
        quotation = db.get(models.Quotation, draft.quotation_id)
        if quotation:
            attachment_bytes = generate_quotation_pdf(quotation, quotation.customer)
            attachment_filename = f"{quotation.number}.pdf"
    elif payload.attach_pdf and draft.invoice_id:
        invoice = db.get(models.Invoice, draft.invoice_id)
        if invoice:
            attachment_bytes = generate_invoice_pdf(invoice, invoice.customer)
            attachment_filename = f"{invoice.number}.pdf"

    draft.subject = subject
    draft.body = body

    try:
        send_email(
            to_email=draft.to_email,
            subject=subject,
            body=body,
            attachment_bytes=attachment_bytes,
            attachment_filename=attachment_filename,
        )
        draft.status = models.EmailStatus.SENT
        draft.sent_at = datetime.utcnow()
    except EmailSendError as exc:
        draft.status = models.EmailStatus.FAILED
        draft.error_message = str(exc)

    db.commit()
    db.refresh(draft)
    return draft


@router.post("/{email_id}/dismiss")
def dismiss_followup(
    email_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    draft = _get_owned_draft(db, current_user, email_id)
    draft.dismissed = True
    db.commit()
    return {"ok": True}
