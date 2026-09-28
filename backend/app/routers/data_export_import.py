"""
Data Export/Import Router — Excel & CSV Pro-Tier Feature.
Provides REST API endpoints to export enterprise data (Customers, Invoices,
Quotations, Expenses, Inventory) and bulk import via file uploads.
"""
from typing import Optional
from fastapi import APIRouter, Depends, Query, UploadFile, File, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, excel_service
from app.auth import get_current_user

router = APIRouter(prefix="/api/data", tags=["data-export-import"])


@router.get("/export/{entity}")
def export_entity(
    entity: str,
    format: str = Query("xlsx", regex="^(xlsx|csv)$"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    entity = entity.lower()
    if entity == "customers":
        content, filename = excel_service.export_customers(db, current_user.company_id, format)
    elif entity == "invoices":
        content, filename = excel_service.export_invoices(db, current_user.company_id, format)
    elif entity == "quotations":
        content, filename = excel_service.export_quotations(db, current_user.company_id, format)
    elif entity == "expenses":
        content, filename = excel_service.export_expenses(db, current_user.company_id, format)
    elif entity == "inventory":
        content, filename = excel_service.export_inventory(db, current_user.company_id, format)
    else:
        raise HTTPException(400, f"Unsupported export entity: {entity}")

    media_type = "text/csv" if format == "csv" else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/import/{entity}")
async def import_entity(
    entity: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    entity = entity.lower()
    file_bytes = await file.read()
    filename = file.filename or "upload.csv"

    if entity == "customers":
        res = excel_service.import_customers(db, current_user.company_id, file_bytes, filename)
    elif entity == "inventory":
        res = excel_service.import_inventory(db, current_user.company_id, file_bytes, filename)
    else:
        raise HTTPException(400, f"Unsupported import entity: {entity}")

    return res


@router.get("/template/{entity}")
def download_template(entity: str):
    content, filename = excel_service.get_sample_template(entity.lower())
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
