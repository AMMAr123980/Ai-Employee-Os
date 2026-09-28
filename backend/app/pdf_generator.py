"""
Generates branded quotation/invoice PDFs with reportlab.

Kept framework-agnostic (returns bytes) so routers can either stream the PDF
directly or, in a later phase, hand the bytes to the Email Assistant to attach
and send.
"""
import io
from datetime import datetime
from typing import List, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_RIGHT
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing

from app.config import settings

BRAND_COLOR = colors.HexColor("#4F46E5")


def _styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="DocTitle", fontSize=22, textColor=BRAND_COLOR, spaceAfter=2))
    styles.add(ParagraphStyle(name="Muted", fontSize=9, textColor=colors.grey))
    styles.add(ParagraphStyle(name="RightMuted", fontSize=9, textColor=colors.grey, alignment=TA_RIGHT))
    styles.add(ParagraphStyle(name="RightBold", fontSize=12, alignment=TA_RIGHT))
    return styles


def _make_qr_code_drawing(url: str, size_pt: float = 65.0) -> Drawing:
    qr_code = QrCodeWidget(url)
    bounds = qr_code.getBounds()
    width = bounds[2] - bounds[0]
    height = bounds[3] - bounds[1]
    drawing = Drawing(size_pt, size_pt, transform=[size_pt / width, 0, 0, size_pt / height, 0, 0])
    drawing.add(qr_code)
    return drawing


def _build_document(
    *,
    doc_label: str,
    doc_number: str,
    doc_date: datetime,
    due_or_valid_label: str,
    due_or_valid_date: Optional[datetime],
    customer_name: str,
    customer_company: Optional[str],
    customer_address: Optional[str],
    items: List[dict],
    subtotal: float,
    discount_percent: float,
    tax_percent: float,
    total: float,
    currency: str,
    notes: Optional[str],
    ai_summary: Optional[str],
    payment_link: Optional[str] = None,
) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm, bottomMargin=18 * mm,
    )
    styles = _styles()
    story = []

    # Header: company on left, doc info on right
    header_data = [[
        Paragraph(f"<b>{settings.company_name}</b><br/>"
                  f"<font size=9 color='grey'>{settings.company_address}<br/>"
                  f"{settings.company_email} &nbsp;|&nbsp; {settings.company_phone}</font>", styles["Normal"]),
        Paragraph(f"<para align='right'><font size=22 color='#4F46E5'><b>{doc_label}</b></font><br/>"
                  f"<font size=10>#{doc_number}</font></para>", styles["Normal"]),
    ]]
    header_table = Table(header_data, colWidths=[100 * mm, 70 * mm])
    header_table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(header_table)
    story.append(Spacer(1, 10 * mm))

    # Bill-to / dates
    meta_data = [[
        Paragraph(f"<font size=9 color='grey'>BILL TO</font><br/>"
                  f"<b>{customer_name}</b>"
                  f"{'<br/>' + customer_company if customer_company else ''}"
                  f"{'<br/>' + customer_address.replace(chr(10), '<br/>') if customer_address else ''}",
                  styles["Normal"]),
        Paragraph(f"<para align='right'><font size=9 color='grey'>DATE</font><br/>"
                  f"{doc_date.strftime('%d %b %Y')}<br/><br/>"
                  f"<font size=9 color='grey'>{due_or_valid_label}</font><br/>"
                  f"{due_or_valid_date.strftime('%d %b %Y') if due_or_valid_date else '—'}</para>",
                  styles["Normal"]),
    ]]
    meta_table = Table(meta_data, colWidths=[100 * mm, 70 * mm])
    story.append(meta_table)
    story.append(Spacer(1, 8 * mm))

    if ai_summary:
        story.append(Paragraph(f"<i>{ai_summary}</i>", styles["Normal"]))
        story.append(Spacer(1, 6 * mm))

    # Line items table
    table_data = [["Description", "Qty", "Unit Price", "Line Total"]]
    for it in items:
        table_data.append([
            it["description"],
            f"{it['quantity']:g}",
            f"{currency} {it['unit_price']:,.2f}",
            f"{currency} {it['line_total']:,.2f}",
        ])
    items_table = Table(table_data, colWidths=[80 * mm, 20 * mm, 35 * mm, 35 * mm])
    items_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BRAND_COLOR),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.white),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 6 * mm))

    discount_amount = subtotal * (discount_percent / 100)
    tax_amount = (subtotal - discount_amount) * (tax_percent / 100)

    totals_rows = [["Subtotal", f"{currency} {subtotal:,.2f}"]]
    if discount_percent:
        totals_rows.append([f"Discount ({discount_percent:g}%)", f"- {currency} {discount_amount:,.2f}"])
    if tax_percent:
        totals_rows.append([f"Tax ({tax_percent:g}%)", f"{currency} {tax_amount:,.2f}"])
    totals_rows.append(["Total", f"{currency} {total:,.2f}"])

    totals_table = Table(totals_rows, colWidths=[135 * mm, 35 * mm])
    style_cmds = [
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LINEABOVE", (0, -1), (-1, -1), 1, BRAND_COLOR),
        ("FONTSIZE", (0, -1), (-1, -1), 13),
        ("TEXTCOLOR", (0, -1), (-1, -1), BRAND_COLOR),
    ]
    totals_table.setStyle(TableStyle(style_cmds))
    story.append(totals_table)

    if notes:
        story.append(Spacer(1, 6 * mm))
        story.append(Paragraph(f"<font size=9 color='grey'>NOTES</font><br/>{notes}", styles["Normal"]))

    if payment_link:
        story.append(Spacer(1, 6 * mm))
        try:
            qr_drawing = _make_qr_code_drawing(payment_link, size_pt=60)
            qr_table_data = [[
                qr_drawing,
                Paragraph(
                    f"<font size=9 color='grey'>SCAN TO PAY ONLINE</font><br/>"
                    f"<b>Payment Link:</b> <font color='#4F46E5'>{payment_link}</font><br/>"
                    f"<font size=8 color='grey'>Scan the QR code with your smartphone camera to complete payment instantly.</font>",
                    styles["Normal"]
                )
            ]]
            qr_table = Table(qr_table_data, colWidths=[25 * mm, 145 * mm])
            qr_table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
            story.append(qr_table)
        except Exception as err:
            story.append(Paragraph(f"<b>Pay Online:</b> {payment_link}", styles["Normal"]))

    story.append(Spacer(1, 10 * mm))
    story.append(Paragraph(
        f"<font size=8 color='grey'>Generated automatically by AI Employee OS "
        f"for {settings.company_name}. {settings.company_tax_id or ''}</font>",
        styles["Normal"],
    ))

    doc.build(story)
    return buf.getvalue()


def generate_quotation_pdf(quotation, customer) -> bytes:
    items = [
        {"description": i.description, "quantity": i.quantity, "unit_price": i.unit_price,
         "line_total": i.line_total}
        for i in quotation.items
    ]
    return _build_document(
        doc_label="QUOTATION",
        doc_number=quotation.number,
        doc_date=quotation.created_at,
        due_or_valid_label="VALID UNTIL",
        due_or_valid_date=quotation.valid_until,
        customer_name=customer.name,
        customer_company=customer.company,
        customer_address=customer.address,
        items=items,
        subtotal=quotation.subtotal,
        discount_percent=quotation.discount_percent,
        tax_percent=quotation.tax_percent,
        total=quotation.total,
        currency=quotation.currency,
        notes=quotation.notes,
        ai_summary=quotation.ai_summary,
    )


def generate_invoice_pdf(invoice, customer) -> bytes:
    items = [
        {"description": i.description, "quantity": i.quantity, "unit_price": i.unit_price,
         "line_total": i.line_total}
        for i in invoice.items
    ]
    return _build_document(
        doc_label="INVOICE",
        doc_number=invoice.number,
        doc_date=invoice.created_at,
        due_or_valid_label="DUE DATE",
        due_or_valid_date=invoice.due_date,
        customer_name=customer.name,
        customer_company=customer.company,
        customer_address=customer.address,
        items=items,
        subtotal=invoice.subtotal,
        discount_percent=invoice.discount_percent,
        tax_percent=invoice.tax_percent,
        total=invoice.total,
        currency=invoice.currency,
        notes=invoice.notes,
        ai_summary=None,
        payment_link=getattr(invoice, "payment_link", None),
    )



def generate_receipt_pdf(invoice, customer, payment_amount: Optional[float] = None, payment_date: Optional[datetime] = None) -> bytes:
    amount = payment_amount if payment_amount is not None else invoice.amount_paid
    date_val = payment_date or datetime.utcnow()
    items = [
        {"description": f"Payment Received for Invoice #{invoice.number}", "quantity": 1.0, "unit_price": amount, "line_total": amount}
    ]
    notes_text = f"Payment of {invoice.currency} {amount:,.2f} received on {date_val.strftime('%d %b %Y')}. Thank you for your business!"
    if invoice.notes:
        notes_text += f"\nInvoice Reference Notes: {invoice.notes}"

    return _build_document(
        doc_label="RECEIPT",
        doc_number=f"REC-{invoice.number}",
        doc_date=date_val,
        due_or_valid_label="INVOICE REF",
        due_or_valid_date=None,
        customer_name=customer.name,
        customer_company=customer.company,
        customer_address=customer.address,
        items=items,
        subtotal=amount,
        discount_percent=0.0,
        tax_percent=0.0,
        total=amount,
        currency=invoice.currency,
        notes=notes_text,
        ai_summary="Official Payment Receipt — Thank You!",
    )

