from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas, email_assistant
from app.email_sender import send_email, EmailSendError
from app.auth import get_current_user
from app.pdf_generator import generate_quotation_pdf, generate_invoice_pdf

router = APIRouter(prefix="/api/emails", tags=["emails"])


def _get_owned_customer(db: Session, current_user: models.User, customer_id: str) -> models.Customer:
    customer = (
        db.query(models.Customer)
        .filter(models.Customer.id == customer_id, models.Customer.company_id == current_user.company_id)
        .first()
    )
    if not customer:
        raise HTTPException(404, "Customer not found")
    return customer


def _get_owned_quotation(db: Session, current_user: models.User, quotation_id: str) -> models.Quotation:
    q = (
        db.query(models.Quotation)
        .filter(models.Quotation.id == quotation_id, models.Quotation.company_id == current_user.company_id)
        .first()
    )
    if not q:
        raise HTTPException(404, "Quotation not found")
    return q


def _get_owned_invoice(db: Session, current_user: models.User, invoice_id: str) -> models.Invoice:
    inv = (
        db.query(models.Invoice)
        .filter(models.Invoice.id == invoice_id, models.Invoice.company_id == current_user.company_id)
        .first()
    )
    if not inv:
        raise HTTPException(404, "Invoice not found")
    return inv


@router.post("/draft", response_model=schemas.EmailDraftResponse)
def draft(
    payload: schemas.EmailDraftRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    customer = _get_owned_customer(db, current_user, payload.customer_id)

    context_parts = []
    if payload.quotation_id:
        q = _get_owned_quotation(db, current_user, payload.quotation_id)
        item_lines = ", ".join(f"{i.description} x{i.quantity:g}" for i in q.items)
        context_parts.append(
            f"Quotation {q.number} for {item_lines}, total {q.currency} {q.total:,.2f}."
        )
    if payload.invoice_id:
        inv = _get_owned_invoice(db, current_user, payload.invoice_id)
        balance = inv.total - inv.amount_paid
        context_parts.append(
            f"Invoice {inv.number}, total {inv.currency} {inv.total:,.2f}, "
            f"balance due {inv.currency} {balance:,.2f}"
            + (f", due {inv.due_date.strftime('%d %b %Y')}" if inv.due_date else "") + "."
        )
    if not context_parts:
        context_parts.append("General follow-up with this customer.")

    draft_result = email_assistant.draft_email(
        customer_name=customer.name,
        company_name=current_user.company.name,
        context=" ".join(context_parts),
        instructions=payload.instructions,
    )
    return schemas.EmailDraftResponse(
        to_email=customer.email,
        subject=draft_result["subject"],
        body=draft_result["body"],
    )


@router.post("/send", response_model=schemas.EmailOut)
def send(
    payload: schemas.EmailSendRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    customer = _get_owned_customer(db, current_user, payload.customer_id)

    quotation = _get_owned_quotation(db, current_user, payload.quotation_id) if payload.quotation_id else None
    invoice = _get_owned_invoice(db, current_user, payload.invoice_id) if payload.invoice_id else None

    follow_up_at = (
        datetime.utcnow() + timedelta(days=payload.follow_up_in_days)
        if payload.follow_up_in_days else None
    )
    email_row = models.EmailMessage(
        company_id=current_user.company_id,
        user_id=current_user.id,
        customer_id=customer.id,
        quotation_id=quotation.id if quotation else None,
        invoice_id=invoice.id if invoice else None,
        to_email=payload.to_email,
        subject=payload.subject,
        body=payload.body,
        status=models.EmailStatus.DRAFT,
        follow_up_at=follow_up_at,
    )
    db.add(email_row)
    db.flush()

    attachment_bytes, attachment_filename = None, None
    if payload.attach_pdf and quotation:
        attachment_bytes = generate_quotation_pdf(quotation, customer)
        attachment_filename = f"{quotation.number}.pdf"
    elif payload.attach_pdf and invoice:
        attachment_bytes = generate_invoice_pdf(invoice, customer)
        attachment_filename = f"{invoice.number}.pdf"

    try:
        send_email(
            to_email=payload.to_email,
            subject=payload.subject,
            body=payload.body,
            attachment_bytes=attachment_bytes,
            attachment_filename=attachment_filename,
        )
        email_row.status = models.EmailStatus.SENT
        email_row.sent_at = datetime.utcnow()
        if follow_up_at:
            email_row.follow_up_status = models.FollowUpStatus.PENDING
        if quotation and quotation.status == models.QuotationStatus.DRAFT:
            quotation.status = models.QuotationStatus.SENT
    except EmailSendError as exc:
        email_row.status = models.EmailStatus.FAILED
        email_row.error_message = str(exc)
        email_row.follow_up_at = None  # no point following up on an email that never sent

    db.commit()
    db.refresh(email_row)

    if email_row.status == models.EmailStatus.FAILED:
        # Still return 200 with the logged failure — the caller can see exactly why
        # (usually "SMTP not configured") rather than a generic 500.
        pass

    return email_row


@router.get("", response_model=list[schemas.EmailOut])
def list_emails(
    customer_id: str = Query(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _get_owned_customer(db, current_user, customer_id)  # 404s if not owned
    return (
        db.query(models.EmailMessage)
        .filter(
            models.EmailMessage.company_id == current_user.company_id,
            models.EmailMessage.customer_id == customer_id,
        )
        .order_by(models.EmailMessage.created_at.desc())
        .all()
    )


@router.post("/summarize", response_model=schemas.EmailSummarizeResponse)
def summarize(
    payload: schemas.EmailSummarizeRequest,
    current_user: models.User = Depends(get_current_user),
):
    return email_assistant.summarize_thread(payload.text)


@router.post("/classify", response_model=schemas.EmailClassifyResponse)
def classify(
    payload: schemas.EmailClassifyRequest,
    current_user: models.User = Depends(get_current_user),
):
    return email_assistant.classify_email(payload.text)


# ---------- Inbound Inbox Sync Endpoints ----------

@router.get("/sync-config")
def get_sync_config(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    config = db.query(models.InboundEmailConfig).filter(
        models.InboundEmailConfig.company_id == current_user.company_id
    ).first()

    if not config:
        config = models.InboundEmailConfig(
            company_id=current_user.company_id,
            email_address=f"sales@{current_user.company.name.lower().replace(' ', '')}.com",
            provider="gmail",
            auto_sync_enabled=True,
            auto_classify=True
        )
        db.add(config)
        db.commit()
        db.refresh(config)

    return {
        "provider": config.provider,
        "email_address": config.email_address,
        "auto_sync_enabled": config.auto_sync_enabled,
        "auto_classify": config.auto_classify,
        "last_synced_at": config.last_synced_at.isoformat() if config.last_synced_at else None
    }


@router.post("/sync-config")
def update_sync_config(
    payload: dict,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    config = db.query(models.InboundEmailConfig).filter(
        models.InboundEmailConfig.company_id == current_user.company_id
    ).first()

    if not config:
        config = models.InboundEmailConfig(company_id=current_user.company_id)
        db.add(config)

    config.provider = payload.get("provider", "gmail")
    config.email_address = payload.get("email_address")
    config.auto_sync_enabled = payload.get("auto_sync_enabled", True)
    config.auto_classify = payload.get("auto_classify", True)

    db.commit()
    return {"status": "updated"}


@router.post("/sync-inbox")
def sync_inbox_now(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    from app.inbound_email_sync import sync_company_inbox
    res = sync_company_inbox(db, current_user.company_id)
    return res


@router.post("/simulate-inbound")
def simulate_inbound_email(
    payload: dict,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Simulates an incoming email from a customer to test inbox sync & follow-up resolution."""
    from_email = payload.get("from_email", "customer@client.com")
    subject = payload.get("subject", "Re: Quotation & Order Inquiry")
    body = payload.get("body", "Thank you for sending the quote. We approve it and would like to move forward!")

    config = db.query(models.InboundEmailConfig).filter(
        models.InboundEmailConfig.company_id == current_user.company_id
    ).first()

    # Find or create customer
    customer = db.query(models.Customer).filter(
        models.Customer.company_id == current_user.company_id,
        models.Customer.email.ilike(from_email)
    ).first()

    if not customer:
        customer = models.Customer(
            company_id=current_user.company_id,
            name=payload.get("from_name", "Acme Client"),
            email=from_email,
            notes="Created via simulated inbound email"
        )
        db.add(customer)
        db.flush()

    msg = models.EmailMessage(
        company_id=current_user.company_id,
        user_id=None,
        customer_id=customer.id,
        direction="inbound",
        inbound_message_id=f"sim_inbound_{datetime.utcnow().timestamp()}",
        to_email=config.email_address if config else "inbox@company.com",
        subject=subject,
        body=body,
        status=models.EmailStatus.SENT,
        auto_generated=False
    )
    db.add(msg)

    # Auto-resolve pending follow-ups for customer!
    followups = db.query(models.EmailMessage).filter(
        models.EmailMessage.company_id == current_user.company_id,
        models.EmailMessage.customer_id == customer.id,
        models.EmailMessage.follow_up_status == models.FollowUpStatus.PENDING
    ).all()

    resolved_count = 0
    for fup in followups:
        fup.follow_up_status = models.FollowUpStatus.DONE
        fup.dismissed = True
        resolved_count += 1

    db.commit()
    return {"status": "inbound_simulated", "email_id": msg.id, "customer_id": customer.id, "followups_auto_resolved": resolved_count}

