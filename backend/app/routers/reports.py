"""
Reports Router — AI Reporting & Analytics REST API.
Provides endpoints for executive overview, sales analytics, revenue reports,
expense reports, customer analytics, productivity, forecasting, and AI insights.
"""
from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, analytics
from app.auth import get_current_user

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/overview")
def get_overview(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return analytics.get_overview_metrics(db, current_user.company_id, days)


@router.get("/sales")
def get_sales(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return analytics.get_sales_analytics(db, current_user.company_id, days)


@router.get("/revenue")
def get_revenue(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return analytics.get_revenue_analytics(db, current_user.company_id, days)


@router.get("/expenses")
def get_expenses(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return analytics.get_expense_analytics(db, current_user.company_id, days)


@router.get("/customers")
def get_customers(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return analytics.get_customer_analytics(db, current_user.company_id, days)


@router.get("/productivity")
def get_productivity(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return analytics.get_productivity_analytics(db, current_user.company_id, days)


@router.get("/forecasting")
def get_forecasting(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return analytics.get_predictive_forecasting(db, current_user.company_id, days)


@router.post("/ai-insights")
def generate_insights(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return analytics.generate_ai_insights(db, current_user.company_id, days)
