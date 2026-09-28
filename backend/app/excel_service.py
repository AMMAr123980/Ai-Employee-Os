"""
Excel (.xlsx) and CSV Import/Export Service.
Provides high-performance data exporting and structured bulk importing for
Customers, Invoices, Quotations, Expenses, and Inventory items.
Supports openpyxl for Excel spreadsheet generation and standard CSV processing.
"""
import io
import csv
import logging
from datetime import datetime
from typing import List, Dict, Any, Tuple, Optional
from sqlalchemy.orm import Session

from app import models
from app.ai_employee_models import Expense, InventoryItem, ExpenseStatus

logger = logging.getLogger(__name__)

# Try to import openpyxl, fallback gracefully if not installed
try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False


def _create_excel_workbook(headers: List[str], rows: List[List[Any]], sheet_name: str = "Data") -> bytes:
    if not HAS_OPENPYXL:
        # Fallback to CSV bytes if openpyxl is missing
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(headers)
        writer.writerows(rows)
        return output.getvalue().encode("utf-8")

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_name

    # Header style
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
    center_align = Alignment(horizontal="left", vertical="center")

    ws.append(headers)
    for cell in ws[1]:
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center_align

    # Data rows
    for row in rows:
        ws.append(row)

    # Auto-adjust column widths
    for col in ws.columns:
        max_len = max(len(str(cell.value or "")) for cell in col)
        col_letter = openpyxl.utils.get_column_letter(col[0].column)
        ws.column_dimensions[col_letter].width = max(max_len + 3, 12)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _create_csv_bytes(headers: List[str], rows: List[List[Any]]) -> bytes:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


# --------------------------------------------------------------------------
# EXPORTERS
# --------------------------------------------------------------------------

def export_customers(db: Session, company_id: str, fmt: str = "xlsx") -> Tuple[bytes, str]:
    customers = db.query(models.Customer).filter(models.Customer.company_id == company_id).all()
    headers = ["ID", "Name", "Company", "Email", "Phone", "Pipeline Stage", "Lead Source", "Address", "Notes", "Created At"]
    rows = []
    for c in customers:
        rows.append([
            c.id, c.name, c.company or "", c.email or "", c.phone or "",
            c.pipeline_stage.value if c.pipeline_stage else "new",
            c.lead_source or "", c.address or "", c.notes or "",
            c.created_at.strftime("%Y-%m-%d %H:%M") if c.created_at else ""
        ])

    if fmt.lower() == "csv":
        return _create_csv_bytes(headers, rows), "customers_export.csv"
    return _create_excel_workbook(headers, rows, "Customers"), "customers_export.xlsx"


def export_invoices(db: Session, company_id: str, fmt: str = "xlsx") -> Tuple[bytes, str]:
    invoices = db.query(models.Invoice).filter(models.Invoice.company_id == company_id).all()
    headers = ["Invoice Number", "Customer Name", "Status", "Subtotal", "Tax %", "Total", "Amount Paid", "Balance Due", "Due Date", "Created At"]
    rows = []
    for inv in invoices:
        cust_name = inv.customer.name if inv.customer else "Unknown"
        bal = inv.total - (inv.amount_paid or 0.0)
        rows.append([
            inv.number, cust_name, inv.status.value if inv.status else "unpaid",
            inv.subtotal, inv.tax_percent, inv.total, inv.amount_paid, bal,
            inv.due_date.strftime("%Y-%m-%d") if inv.due_date else "",
            inv.created_at.strftime("%Y-%m-%d %H:%M") if inv.created_at else ""
        ])

    if fmt.lower() == "csv":
        return _create_csv_bytes(headers, rows), "invoices_export.csv"
    return _create_excel_workbook(headers, rows, "Invoices"), "invoices_export.xlsx"


def export_quotations(db: Session, company_id: str, fmt: str = "xlsx") -> Tuple[bytes, str]:
    quotations = db.query(models.Quotation).filter(models.Quotation.company_id == company_id).all()
    headers = ["Quotation Number", "Customer Name", "Status", "Subtotal", "Discount %", "Tax %", "Total", "Valid Until", "Created At"]
    rows = []
    for q in quotations:
        cust_name = q.customer.name if q.customer else "Unknown"
        rows.append([
            q.number, cust_name, q.status.value if q.status else "draft",
            q.subtotal, q.discount_percent, q.tax_percent, q.total,
            q.valid_until.strftime("%Y-%m-%d") if q.valid_until else "",
            q.created_at.strftime("%Y-%m-%d %H:%M") if q.created_at else ""
        ])

    if fmt.lower() == "csv":
        return _create_csv_bytes(headers, rows), "quotations_export.csv"
    return _create_excel_workbook(headers, rows, "Quotations"), "quotations_export.xlsx"


def export_expenses(db: Session, company_id: str, fmt: str = "xlsx") -> Tuple[bytes, str]:
    expenses = db.query(Expense).filter(Expense.company_id == company_id).all()
    headers = ["ID", "Description", "Amount", "Category", "Incurred On", "Supplier ID", "Status"]
    rows = []
    for e in expenses:
        rows.append([
            e.id, e.description, e.amount, e.category or "",
            e.incurred_on.strftime("%Y-%m-%d") if e.incurred_on else "",
            e.supplier_id or "", e.status.value if e.status else "recorded"
        ])

    if fmt.lower() == "csv":
        return _create_csv_bytes(headers, rows), "expenses_export.csv"
    return _create_excel_workbook(headers, rows, "Expenses"), "expenses_export.xlsx"


def export_inventory(db: Session, company_id: str, fmt: str = "xlsx") -> Tuple[bytes, str]:
    items = db.query(InventoryItem).filter(InventoryItem.company_id == company_id).all()
    headers = ["SKU", "Item Name", "Category", "Unit", "Quantity On Hand", "Reorder Point", "Cost Price", "Sale Price"]
    rows = []
    for item in items:
        rows.append([
            item.sku or "", item.name, item.category or "", item.unit or "pcs",
            item.quantity_on_hand, item.reorder_point or 0, item.cost_price or 0.0, item.sale_price or 0.0
        ])

    if fmt.lower() == "csv":
        return _create_csv_bytes(headers, rows), "inventory_export.csv"
    return _create_excel_workbook(headers, rows, "Inventory"), "inventory_export.xlsx"


# --------------------------------------------------------------------------
# IMPORTERS
# --------------------------------------------------------------------------

def _parse_uploaded_rows(file_bytes: bytes, filename: str) -> List[Dict[str, str]]:
    rows = []
    if filename.endswith(".xlsx") and HAS_OPENPYXL:
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
        ws = wb.active
        headers = [str(cell.value or "").strip() for cell in ws[1]]
        for row in ws.iter_rows(min_row=2, values_only=True):
            if any(row):
                row_dict = {headers[i]: str(row[i] or "").strip() for i in range(min(len(headers), len(row)))}
                rows.append(row_dict)
    else:
        text = file_bytes.decode("utf-8", errors="ignore")
        reader = csv.DictReader(io.StringIO(text))
        for row in reader:
            cleaned = {str(k or "").strip(): str(v or "").strip() for k, v in row.items()}
            rows.append(cleaned)
    return rows


def import_customers(db: Session, company_id: str, file_bytes: bytes, filename: str) -> Dict[str, Any]:
    parsed = _parse_uploaded_rows(file_bytes, filename)
    imported = 0
    skipped = 0

    for r in parsed:
        name = r.get("Name") or r.get("name") or r.get("Customer Name")
        if not name:
            skipped += 1
            continue

        existing = (
            db.query(models.Customer)
            .filter(models.Customer.company_id == company_id, models.Customer.name.ilike(name))
            .first()
        )
        if existing:
            skipped += 1
            continue

        stage_str = (r.get("Pipeline Stage") or r.get("pipeline_stage") or "new").lower()
        try:
            stage = models.PipelineStage(stage_str)
        except ValueError:
            stage = models.PipelineStage.NEW

        c = models.Customer(
            company_id=company_id,
            name=name,
            company=r.get("Company") or r.get("company"),
            email=r.get("Email") or r.get("email"),
            phone=r.get("Phone") or r.get("phone"),
            address=r.get("Address") or r.get("address"),
            lead_source=r.get("Lead Source") or r.get("lead_source"),
            notes=r.get("Notes") or r.get("notes"),
            pipeline_stage=stage,
        )
        db.add(c)
        imported += 1

    db.commit()
    return {"entity": "customers", "imported_count": imported, "skipped_count": skipped}


def import_inventory(db: Session, company_id: str, file_bytes: bytes, filename: str) -> Dict[str, Any]:
    parsed = _parse_uploaded_rows(file_bytes, filename)
    imported = 0
    skipped = 0

    for r in parsed:
        name = r.get("Item Name") or r.get("name") or r.get("Name")
        if not name:
            skipped += 1
            continue

        sku = r.get("SKU") or r.get("sku")
        qty = float(r.get("Quantity On Hand") or r.get("quantity_on_hand") or 0)
        reorder = float(r.get("Reorder Point") or r.get("reorder_point") or 0)
        cost = float(r.get("Cost Price") or r.get("cost_price") or 0)
        sale = float(r.get("Sale Price") or r.get("sale_price") or 0)

        item = InventoryItem(
            company_id=company_id,
            name=name,
            sku=sku,
            category=r.get("Category") or r.get("category"),
            unit=r.get("Unit") or r.get("unit") or "pcs",
            quantity_on_hand=qty,
            reorder_point=reorder,
            cost_price=cost,
            sale_price=sale,
        )
        db.add(item)
        imported += 1

    db.commit()
    return {"entity": "inventory", "imported_count": imported, "skipped_count": skipped}


def get_sample_template(entity: str) -> Tuple[bytes, str]:
    if entity == "customers":
        headers = ["Name", "Company", "Email", "Phone", "Pipeline Stage", "Lead Source", "Address", "Notes"]
        sample = [["Acme Traders", "Acme Corp", "contact@acme.com", "+1-555-0199", "qualified", "referral", "100 Market St", "Key account"]]
        return _create_csv_bytes(headers, sample), "sample_customers_template.csv"
    elif entity == "inventory":
        headers = ["SKU", "Item Name", "Category", "Unit", "Quantity On Hand", "Reorder Point", "Cost Price", "Sale Price"]
        sample = [["SKU-1001", "Wireless Keyboard", "Hardware", "pcs", "50", "10", "25.00", "45.00"]]
        return _create_csv_bytes(headers, sample), "sample_inventory_template.csv"
    else:
        headers = ["Description", "Amount", "Category"]
        sample = [["Office Internet Bill", "150.00", "utilities"]]
        return _create_csv_bytes(headers, sample), f"sample_{entity}_template.csv"
