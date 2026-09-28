import hashlib
import logging
import secrets
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Security
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import get_current_user
from app.models import User, Customer, Invoice, Quotation, ApiKey
from app.task_models import Task, TaskPriority, TaskStatus, TaskSource

logger = logging.getLogger("routers.public_api")

router = APIRouter(tags=["public_api"])


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def require_api_key(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    db: Session = Depends(get_db)
) -> ApiKey:
    raw_key = x_api_key
    if not raw_key and authorization and authorization.startswith("Bearer ak_"):
        raw_key = authorization.replace("Bearer ", "").strip()

    if not raw_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key or Bearer API key header")

    hashed = hash_api_key(raw_key)
    api_key = db.query(ApiKey).filter(ApiKey.key_hash == hashed, ApiKey.is_active == True).first()

    if not api_key:
        raise HTTPException(status_code=401, detail="Invalid or revoked API Key")

    api_key.last_used_at = datetime.utcnow()
    db.commit()
    return api_key


class CreateApiKeySchema(BaseModel):
    name: str


# --------------------------------------------------------------------------
# API Key Management Endpoints (Session Authenticated)
# --------------------------------------------------------------------------

@router.get("/api/auth/api-keys")
def list_api_keys(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    keys = db.query(ApiKey).filter(ApiKey.company_id == current_user.company_id).all()
    return [
        {
            "id": k.id,
            "name": k.name,
            "prefix": k.prefix,
            "rate_limit_per_min": k.rate_limit_per_min,
            "is_active": k.is_active,
            "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
            "created_at": k.created_at.isoformat() if k.created_at else None,
        }
        for k in keys
    ]


@router.post("/api/auth/api-keys")
def create_api_key_route(
    payload: CreateApiKeySchema,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    raw_secret = f"ak_live_{secrets.token_hex(16)}"
    prefix = raw_secret[:12]
    hashed = hash_api_key(raw_secret)

    key_row = ApiKey(
        company_id=current_user.company_id,
        user_id=current_user.id,
        name=payload.name,
        prefix=prefix,
        key_hash=hashed,
        rate_limit_per_min=120
    )
    db.add(key_row)
    db.commit()

    return {
        "status": "created",
        "id": key_row.id,
        "name": key_row.name,
        "api_key": raw_secret,  # Shown ONCE to user
        "warning": "Save this key now. It will not be shown again."
    }


@router.delete("/api/auth/api-keys/{key_id}")
def revoke_api_key_route(
    key_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    key_row = db.query(ApiKey).filter(
        ApiKey.company_id == current_user.company_id,
        ApiKey.id == key_id
    ).first()

    if not key_row:
        raise HTTPException(status_code=404, detail="API Key not found")

    key_row.is_active = False
    db.commit()
    return {"status": "revoked"}


# --------------------------------------------------------------------------
# Public Developer REST API v1 Endpoints (API Key Authenticated)
# --------------------------------------------------------------------------

@router.get("/api/v1/customers")
def v1_list_customers(
    api_key: ApiKey = Depends(require_api_key),
    db: Session = Depends(get_db)
):
    customers = db.query(Customer).filter(Customer.company_id == api_key.company_id).all()
    return [
        {
            "id": c.id,
            "name": c.name,
            "email": c.email,
            "phone": c.phone,
            "company": c.company,
            "pipeline_stage": c.pipeline_stage.value,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in customers
    ]


@router.post("/api/v1/customers")
def v1_create_customer(
    payload: dict,
    api_key: ApiKey = Depends(require_api_key),
    db: Session = Depends(get_db)
):
    c = Customer(
        company_id=api_key.company_id,
        name=payload.get("name", "New API Customer"),
        email=payload.get("email"),
        phone=payload.get("phone"),
        company=payload.get("company"),
        notes=payload.get("notes", "Created via Developer REST API v1")
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return {"id": c.id, "name": c.name, "email": c.email}


@router.get("/api/v1/invoices")
def v1_list_invoices(
    api_key: ApiKey = Depends(require_api_key),
    db: Session = Depends(get_db)
):
    invoices = db.query(Invoice).filter(Invoice.company_id == api_key.company_id).all()
    return [
        {
            "id": inv.id,
            "number": inv.number,
            "customer_id": inv.customer_id,
            "status": inv.status.value,
            "total": inv.total,
            "amount_paid": inv.amount_paid,
            "currency": inv.currency,
            "created_at": inv.created_at.isoformat() if inv.created_at else None,
        }
        for inv in invoices
    ]


@router.get("/api/v1/tasks")
def v1_list_tasks(
    api_key: ApiKey = Depends(require_api_key),
    db: Session = Depends(get_db)
):
    tasks = db.query(Task).filter(Task.company_id == api_key.company_id).all()
    return [
        {
            "id": t.id,
            "title": t.title,
            "status": t.status.value,
            "priority": t.priority.value,
            "due_date": t.due_date.isoformat() if t.due_date else None,
        }
        for t in tasks
    ]
