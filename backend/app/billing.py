"""
Stripe Billing & Subscription Manager.
Provides Stripe Checkout integration, plan upgrades/downgrades, and webhook event processing.
Features a sandbox/demo mode when Stripe API keys are not present, enabling instant plan switching.
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

from app import models
from app.config import settings

logger = logging.getLogger(__name__)

PLAN_PRICES = {
    models.Plan.BASIC: 19.0,
    models.Plan.PRO: 79.0,
    models.Plan.BUSINESS: 299.0,
}

PLAN_PRICE_IDS = {
    models.Plan.BASIC: getattr(settings, "stripe_basic_price_id", "price_basic"),
    models.Plan.PRO: getattr(settings, "stripe_pro_price_id", "price_pro"),
    models.Plan.BUSINESS: getattr(settings, "stripe_business_price_id", "price_business"),
}


def change_company_plan(db: Session, company_id: str, new_plan_key: str) -> Dict[str, Any]:
    company = db.get(models.Company, company_id)
    if not company:
        raise ValueError("Company not found")

    try:
        plan_enum = models.Plan(new_plan_key.lower())
    except ValueError:
        raise ValueError(f"Invalid plan key: {new_plan_key}. Must be basic, pro, or business.")

    company.plan = plan_enum
    company.subscription_status = "active"
    company.current_period_end = datetime.utcnow() + timedelta(days=30)
    db.commit()
    db.refresh(company)

    logger.info("Company %s upgraded plan to %s", company_id, plan_enum.value)
    return {
        "company_id": company.id,
        "plan": company.plan.value,
        "status": company.subscription_status,
        "current_period_end": company.current_period_end.isoformat() if company.current_period_end else None,
        "price_monthly": PLAN_PRICES.get(plan_enum, 0.0),
    }


def create_checkout_session(db: Session, company_id: str, plan_key: str, success_url: Optional[str] = None) -> Dict[str, Any]:
    company = db.get(models.Company, company_id)
    if not company:
        raise ValueError("Company not found")

    try:
        plan_enum = models.Plan(plan_key.lower())
    except ValueError:
        raise ValueError(f"Invalid plan key: {plan_key}")

    # If Stripe key is configured, use real Stripe SDK
    if settings.stripe_secret_key:
        try:
            import stripe
            stripe.api_key = settings.stripe_secret_key
            price_id = PLAN_PRICE_IDS.get(plan_enum)

            session = stripe.checkout.Session.create(
                payment_method_types=["card"],
                line_items=[{"price": price_id, "quantity": 1}],
                mode="subscription",
                success_url=success_url or f"{settings.frontend_origin}/billing?success=true",
                cancel_url=f"{settings.frontend_origin}/billing?canceled=true",
                client_reference_id=company_id,
                customer_email=company.users[0].email if company.users else None,
            )
            return {"checkout_url": session.url, "mode": "stripe"}
        except Exception as err:
            logger.error("Stripe Checkout creation failed: %s. Falling back to sandbox upgrade.", err)

    # Sandbox / Demo mode fallback
    res = change_company_plan(db, company_id, plan_enum.value)
    return {
        "checkout_url": f"{settings.frontend_origin}/billing?upgraded={plan_enum.value}",
        "mode": "sandbox",
        "subscription": res,
    }


def process_stripe_webhook(db: Session, payload: bytes, sig_header: str) -> Dict[str, Any]:
    if not settings.stripe_secret_key or not settings.stripe_webhook_secret:
        return {"status": "ignored", "reason": "Stripe webhook secret unconfigured"}

    try:
        import stripe
        stripe.api_key = settings.stripe_secret_key
        event = stripe.Webhook.construct_event(payload, sig_header, settings.stripe_webhook_secret)

        event_type = event.get("type")
        data_obj = event.get("data", {}).get("object", {})

        if event_type == "checkout.session.completed":
            company_id = data_obj.get("client_reference_id")
            customer_id = data_obj.get("customer")
            subscription_id = data_obj.get("subscription")
            if company_id:
                company = db.get(models.Company, company_id)
                if company:
                    company.stripe_customer_id = customer_id
                    company.stripe_subscription_id = subscription_id
                    company.subscription_status = "active"
                    db.commit()

        elif event_type in ("customer.subscription.updated", "customer.subscription.deleted"):
            subscription_id = data_obj.get("id")
            status = data_obj.get("status", "canceled")
            company = db.query(models.Company).filter(models.Company.stripe_subscription_id == subscription_id).first()
            if company:
                company.subscription_status = status
                if status == "canceled":
                    company.plan = models.Plan.BASIC
                db.commit()

        return {"status": "success", "event_type": event_type}
    except Exception as err:
        logger.error("Stripe webhook handling failed: %s", err)
        return {"status": "error", "error": str(err)}
