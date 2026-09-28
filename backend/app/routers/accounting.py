import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import get_current_user
from app.models import User
from app.accounting_sync import (
    AccountingConfig, export_invoices_to_accounting,
    export_expenses_to_accounting, sync_accounting_now,
    push_invoices_to_accounting_api, push_expenses_to_accounting_api,
    get_oauth_authorize_url, handle_oauth_callback
)

logger = logging.getLogger("routers.accounting")
router = APIRouter(prefix="/api/accounting", tags=["accounting"])


class AccountingConfigSchema(BaseModel):
    provider: str = "quickbooks"  # "quickbooks", "xero", "zoho"
    realm_id: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    auto_sync: bool = True
    is_connected: Optional[bool] = None


@router.get("/config")
def get_accounting_config(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    config = db.query(AccountingConfig).filter(
        AccountingConfig.company_id == current_user.company_id
    ).first()

    if not config:
        config = AccountingConfig(company_id=current_user.company_id, provider="quickbooks")
        db.add(config)
        db.commit()
        db.refresh(config)

    user_role = getattr(current_user.role, "value", str(current_user.role)).lower()
    can_manage = user_role in ["owner", "admin", "finance", "accountant"]

    is_connected = bool(config.access_token)
    return {
        "provider": config.provider,
        "realm_id": config.realm_id,
        "client_id": config.client_id,
        "auto_sync": config.auto_sync,
        "is_connected": is_connected,
        "user_role": user_role,
        "can_manage_integrations": can_manage,
        "token_expires_at": config.token_expires_at.isoformat() if config.token_expires_at else None,
        "last_synced_at": config.last_synced_at.isoformat() if config.last_synced_at else None
    }


@router.post("/config")
def update_accounting_config(
    payload: AccountingConfigSchema,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    config = db.query(AccountingConfig).filter(
        AccountingConfig.company_id == current_user.company_id
    ).first()

    if not config:
        config = AccountingConfig(company_id=current_user.company_id)
        db.add(config)

    config.provider = payload.provider.lower()
    config.realm_id = payload.realm_id
    config.client_id = payload.client_id
    if payload.client_secret:
        config.client_secret = payload.client_secret
    config.auto_sync = payload.auto_sync

    if payload.is_connected or payload.is_connected is True:
        if not config.access_token:
            config.access_token = f"mock_{payload.provider.lower()}_bearer_token_active"

    db.commit()
    return {"status": "updated"}


@router.get("/oauth/authorize")
def oauth_authorize(
    provider: str = Query("quickbooks"),
    current_user: User = Depends(get_current_user)
):
    """Generates official OAuth2 Authorization URL for QuickBooks, Xero, or Zoho Books."""
    url = get_oauth_authorize_url(provider)
    return {"provider": provider, "authorize_url": url}


@router.get("/oauth/callback")
def oauth_callback(
    code: str = Query(...),
    provider: str = Query("quickbooks"),
    realmId: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Exchanges OAuth code for access/refresh tokens and stores connection."""
    config = handle_oauth_callback(db, current_user.company_id, provider, code, realmId)
    return {
        "status": "connected",
        "provider": config.provider,
        "realm_id": config.realm_id,
        "is_connected": True
    }


@router.post("/push-invoices")
def push_invoices_route(
    payload: Optional[dict] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Triggers live HTTP push of company invoices to accounting provider REST API."""
    invoice_ids = payload.get("invoice_ids") if payload else None
    res = push_invoices_to_accounting_api(db, current_user.company_id, invoice_ids)
    return res


@router.post("/push-expenses")
def push_expenses_route(
    payload: Optional[dict] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Triggers live HTTP push of expenses to accounting provider REST API."""
    expense_ids = payload.get("expense_ids") if payload else None
    res = push_expenses_to_accounting_api(db, current_user.company_id, expense_ids)
    return res


@router.post("/export-invoices")
def export_invoices_route(
    payload: Optional[dict] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    invoice_ids = payload.get("invoice_ids") if payload else None
    res = export_invoices_to_accounting(db, current_user.company_id, invoice_ids)
    return res


@router.post("/export-expenses")
def export_expenses_route(
    payload: Optional[dict] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    expense_ids = payload.get("expense_ids") if payload else None
    res = export_expenses_to_accounting(db, current_user.company_id, expense_ids)
    return res


@router.post("/sync-now")
def sync_accounting_now_route(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Executes live HTTP API push sync for both invoices and expenses."""
    res = sync_accounting_now(db, current_user.company_id)
    return res
