from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas, ai_assistant
from app.auth import get_current_user
from app.config import settings
from app.pdf_generator import generate_quotation_pdf

router = APIRouter(prefix="/api/quotations", tags=["quotations"])


def _next_number(db: Session, company_id: str, prefix: str, model) -> str:
    count = db.query(model).filter(model.company_id == company_id).count() + 1
    return f"{prefix}-{count:06d}"


def _compute_totals(items: list[schemas.ItemIn], discount_percent: float, tax_percent: float):
    subtotal = sum(i.quantity * i.unit_price for i in items)
    discount_amount = subtotal * (discount_percent / 100)
    taxable = subtotal - discount_amount
    tax_amount = taxable * (tax_percent / 100)
    total = taxable + tax_amount
    return subtotal, total


def _get_owned_quotation(db: Session, current_user: models.User, quotation_id: str) -> models.Quotation:
    quotation = (
        db.query(models.Quotation)
        .filter(models.Quotation.id == quotation_id, models.Quotation.company_id == current_user.company_id)
        .first()
    )
    if not quotation:
        raise HTTPException(404, "Quotation not found")
    return quotation


def _get_owned_customer(db: Session, current_user: models.User, customer_id: str) -> models.Customer:
    customer = (
        db.query(models.Customer)
        .filter(models.Customer.id == customer_id, models.Customer.company_id == current_user.company_id)
        .first()
    )
    if not customer:
        raise HTTPException(404, "Customer not found")
    return customer


@router.post("/ai-draft", response_model=schemas.AIDraftItemsResponse)
def ai_draft_items(
    payload: schemas.AIDraftItemsRequest,
    current_user: models.User = Depends(get_current_user),
):
    """Turn a natural-language request into structured quotation line items."""
    result = ai_assistant.draft_items_from_prompt(payload.prompt)
    return result


@router.get("", response_model=list[schemas.QuotationOut])
def list_quotations(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return (
        db.query(models.Quotation)
        .filter(models.Quotation.company_id == current_user.company_id)
        .order_by(models.Quotation.created_at.desc())
        .all()
    )


@router.post("", response_model=schemas.QuotationOut)
def create_quotation(
    payload: schemas.QuotationCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    from app import usage_metering
    try:
        usage_metering.check(db, current_user.company_id, usage_metering.QUOTATIONS_PER_MONTH)
    except usage_metering.QuotaExceeded as exc:
        raise HTTPException(402, detail=str(exc))

    customer = _get_owned_customer(db, current_user, payload.customer_id)

    tax_percent = payload.tax_percent if payload.tax_percent is not None else settings.default_tax_rate
    subtotal, total = _compute_totals(payload.items, payload.discount_percent, tax_percent)

    quotation = models.Quotation(
        company_id=current_user.company_id,
        number=_next_number(db, current_user.company_id, "QUO", models.Quotation),
        customer_id=customer.id,
        subtotal=subtotal,
        discount_percent=payload.discount_percent,
        tax_percent=tax_percent,
        total=total,
        currency=payload.currency or settings.default_currency,
        notes=payload.notes,
        valid_until=payload.valid_until,
    )
    db.add(quotation)
    db.flush()  # get quotation.id before adding items

    for item in payload.items:
        line_total = item.quantity * item.unit_price
        db.add(models.QuotationItem(
            quotation_id=quotation.id,
            description=item.description,
            quantity=item.quantity,
            unit_price=item.unit_price,
            line_total=line_total,
        ))

    db.commit()
    usage_metering.consume(db, current_user.company_id, usage_metering.QUOTATIONS_PER_MONTH)
    db.refresh(quotation)

    if payload.generate_ai_summary:
        items_dicts = [{"description": i.description, "quantity": i.quantity} for i in quotation.items]
        summary = ai_assistant.summarize_quotation(customer.name, items_dicts, quotation.total, quotation.currency)
        if summary:
            quotation.ai_summary = summary
            db.commit()
            db.refresh(quotation)

    return quotation


@router.get("/{quotation_id}", response_model=schemas.QuotationOut)
def get_quotation(
    quotation_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return _get_owned_quotation(db, current_user, quotation_id)


@router.patch("/{quotation_id}/status", response_model=schemas.QuotationOut)
def update_status(
    quotation_id: str,
    payload: schemas.QuotationStatusUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    quotation = _get_owned_quotation(db, current_user, quotation_id)
    quotation.status = payload.status
    quotation.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(quotation)
    return quotation


@router.get("/{quotation_id}/pdf")
def download_quotation_pdf(
    quotation_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    quotation = _get_owned_quotation(db, current_user, quotation_id)
    pdf_bytes = generate_quotation_pdf(quotation, quotation.customer)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{quotation.number}.pdf"'},
    )


@router.post("/{quotation_id}/convert-to-invoice", response_model=schemas.InvoiceOut)
def convert_to_invoice(
    quotation_id: str,
    payload: schemas.InvoiceFromQuotation = schemas.InvoiceFromQuotation(),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    quotation = _get_owned_quotation(db, current_user, quotation_id)
    if quotation.invoice:
        raise HTTPException(400, "Quotation already converted to an invoice")

    next_recurrence_at = None
    if payload.is_recurring and payload.recurrence_interval_days:
        next_recurrence_at = datetime.utcnow() + timedelta(days=payload.recurrence_interval_days)

    invoice = models.Invoice(
        company_id=current_user.company_id,
        number=_next_number(db, current_user.company_id, "INV", models.Invoice),
        customer_id=quotation.customer_id,
        quotation_id=quotation.id,
        subtotal=quotation.subtotal,
        discount_percent=quotation.discount_percent,
        tax_percent=quotation.tax_percent,
        total=quotation.total,
        currency=quotation.currency,
        notes=quotation.notes,
        due_date=payload.due_date,
        is_recurring=payload.is_recurring,
        recurrence_interval_days=payload.recurrence_interval_days,
        next_recurrence_at=next_recurrence_at,
    )
    db.add(invoice)
    db.flush()

    for item in quotation.items:
        db.add(models.InvoiceItem(
            invoice_id=invoice.id,
            description=item.description,
            quantity=item.quantity,
            unit_price=item.unit_price,
            line_total=item.line_total,
        ))

    quotation.status = models.QuotationStatus.CONVERTED
    db.commit()
    db.refresh(invoice)
    return invoice
