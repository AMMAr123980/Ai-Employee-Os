"""
Billing Router — Subscriptions, Checkout Sessions & Webhooks.
Allows companies to view active plans, usage meters, upgrade subscriptions,
and process Stripe webhooks.
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Body
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, billing, usage_metering
from app.auth import get_current_user, require_role

router = APIRouter(prefix="/api/billing", tags=["billing"])


class ChangePlanRequest(BaseModel):
    plan: str


class CheckoutRequest(BaseModel):
    plan: str
    success_url: Optional[str] = None


@router.get("/subscription")
def get_subscription(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    company = db.get(models.Company, current_user.company_id)
    if not company:
        raise HTTPException(404, "Company not found")

    snapshot = usage_metering.usage_snapshot(db, company.id)
    price_monthly = billing.PLAN_PRICES.get(company.plan, 0.0)

    return {
        "company_id": company.id,
        "company_name": company.name,
        "plan": company.plan.value if company.plan else "pro",
        "subscription_status": company.subscription_status,
        "current_period_end": company.current_period_end.isoformat() if company.current_period_end else None,
        "price_monthly": price_monthly,
        "stripe_customer_id": company.stripe_customer_id,
        "usage": snapshot,
    }


@router.post("/create-checkout-session")
def create_checkout(
    payload: CheckoutRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role(models.UserRole.OWNER, models.UserRole.ADMIN)),
):
    try:
        res = billing.create_checkout_session(db, current_user.company_id, payload.plan, payload.success_url)
        return res
    except ValueError as err:
        raise HTTPException(400, str(err))


@router.post("/change-plan")
def change_plan(
    payload: ChangePlanRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role(models.UserRole.OWNER)),
):
    try:
        res = billing.change_company_plan(db, current_user.company_id, payload.plan)
        return res
    except ValueError as err:
        raise HTTPException(400, str(err))


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    payload_bytes = await request.body()
    sig_header = request.headers.get("Stripe-Signature", "")
    res = billing.process_stripe_webhook(db, payload_bytes, sig_header)
    return res
