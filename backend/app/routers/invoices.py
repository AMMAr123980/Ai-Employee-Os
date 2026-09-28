from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.auth import get_current_user
from app.config import settings
from app.pdf_generator import generate_invoice_pdf

router = APIRouter(prefix="/api/invoices", tags=["invoices"])


def _next_number(db: Session, company_id: str) -> str:
    count = db.query(models.Invoice).filter(models.Invoice.company_id == company_id).count() + 1
    return f"INV-{count:06d}"


def _compute_totals(items, discount_percent: float, tax_percent: float):
    subtotal = sum(i.quantity * i.unit_price for i in items)
    discount_amount = subtotal * (discount_percent / 100)
    taxable = subtotal - discount_amount
    tax_amount = taxable * (tax_percent / 100)
    return subtotal, taxable + tax_amount


def _get_owned_invoice(db: Session, current_user: models.User, invoice_id: str) -> models.Invoice:
    invoice = (
        db.query(models.Invoice)
        .filter(models.Invoice.id == invoice_id, models.Invoice.company_id == current_user.company_id)
        .first()
    )
    if not invoice:
        raise HTTPException(404, "Invoice not found")
    return invoice


def _get_owned_customer(db: Session, current_user: models.User, customer_id: str) -> models.Customer:
    customer = (
        db.query(models.Customer)
        .filter(models.Customer.id == customer_id, models.Customer.company_id == current_user.company_id)
        .first()
    )
    if not customer:
        raise HTTPException(404, "Customer not found")
    return customer


@router.get("", response_model=list[schemas.InvoiceOut])
def list_invoices(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return (
        db.query(models.Invoice)
        .filter(models.Invoice.company_id == current_user.company_id)
        .order_by(models.Invoice.created_at.desc())
        .all()
    )


@router.post("", response_model=schemas.InvoiceOut)
def create_invoice(
    payload: schemas.InvoiceCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Create a standalone invoice (not tied to a quotation)."""
    from app import usage_metering
    try:
        usage_metering.check(db, current_user.company_id, usage_metering.INVOICES_PER_MONTH)
    except usage_metering.QuotaExceeded as exc:
        raise HTTPException(402, detail=str(exc))

    customer = _get_owned_customer(db, current_user, payload.customer_id)

    tax_percent = payload.tax_percent if payload.tax_percent is not None else settings.default_tax_rate
    subtotal, total = _compute_totals(payload.items, payload.discount_percent, tax_percent)

    next_recurrence_at = None
    if payload.is_recurring and payload.recurrence_interval_days:
        next_recurrence_at = datetime.utcnow() + timedelta(days=payload.recurrence_interval_days)

    invoice = models.Invoice(
        company_id=current_user.company_id,
        number=_next_number(db, current_user.company_id),
        customer_id=customer.id,
        subtotal=subtotal,
        discount_percent=payload.discount_percent,
        tax_percent=tax_percent,
        total=total,
        currency=payload.currency or settings.default_currency,
        notes=payload.notes,
        payment_link=payload.payment_link,
        due_date=payload.due_date,
        is_recurring=payload.is_recurring,
        recurrence_interval_days=payload.recurrence_interval_days,
        next_recurrence_at=next_recurrence_at,
    )

    db.add(invoice)
    db.flush()

    for item in payload.items:
        db.add(models.InvoiceItem(
            invoice_id=invoice.id,
            description=item.description,
            quantity=item.quantity,
            unit_price=item.unit_price,
            line_total=item.quantity * item.unit_price,
        ))

    db.commit()
    usage_metering.consume(db, current_user.company_id, usage_metering.INVOICES_PER_MONTH)
    db.refresh(invoice)
    return invoice


@router.get("/{invoice_id}", response_model=schemas.InvoiceOut)
def get_invoice(
    invoice_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return _get_owned_invoice(db, current_user, invoice_id)


@router.post("/{invoice_id}/payments", response_model=schemas.InvoiceOut)
def record_payment(
    invoice_id: str,
    payload: schemas.PaymentIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    invoice = _get_owned_invoice(db, current_user, invoice_id)

    invoice.amount_paid += payload.amount
    if invoice.amount_paid >= invoice.total:
        invoice.status = models.InvoiceStatus.PAID
    elif invoice.amount_paid > 0:
        invoice.status = models.InvoiceStatus.PARTIALLY_PAID
    invoice.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(invoice)

    try:
        from app.workflow_engine import trigger_event
        trigger_event(
            db=db,
            company_id=current_user.company_id,
            event_type="payment_received",
            payload={
                "invoice_id": invoice.id,
                "customer_id": invoice.customer_id,
                "amount": payload.amount,
                "user_id": current_user.id
            }
        )
        if invoice.status == models.InvoiceStatus.PAID:
            trigger_event(
                db=db,
                company_id=current_user.company_id,
                event_type="invoice_paid",
                payload={
                    "invoice_id": invoice.id,
                    "customer_id": invoice.customer_id,
                    "amount": invoice.amount_paid,
                    "user_id": current_user.id
                }
            )
    except Exception as exc:
        import logging
        logging.getLogger("invoices").error(f"Error triggering workflow on payment: {exc}")

    return invoice



@router.get("/{invoice_id}/pdf")
def download_invoice_pdf(
    invoice_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    invoice = _get_owned_invoice(db, current_user, invoice_id)
    pdf_bytes = generate_invoice_pdf(invoice, invoice.customer)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{invoice.number}.pdf"'},
    )


@router.post("/recurring/check-now", response_model=schemas.RecurringCheckResult)
def check_recurring_now(current_user: models.User = Depends(get_current_user)):
    """Manually trigger the recurring-invoice generator for this company — useful
    for testing, or a "generate now" button instead of waiting for the interval."""
    from app.recurring_invoices import generate_due_recurring_invoices
    created = generate_due_recurring_invoices(company_id=current_user.company_id)
    return schemas.RecurringCheckResult(invoices_created=created)
