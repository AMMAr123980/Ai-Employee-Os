import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import Base, engine
from app.config import settings

# IMPORTANT:
# Import the main application models first so Customer, Invoice, etc.
# are registered with SQLAlchemy before WhatsApp models reference them.
from app import models

from app.routers import (
    auth,
    customers,
    quotations,
    invoices,
    emails,
    followups,
    team,
    ai_employees,
    voice_commands,
    voice_meetings,
    tasks,
    documents,
    whatsapp,
    workflows,
    calendar,
    accounting,
    public_api,
    reports,
    billing,
    data_export_import,
)

from app import (
    ai_employee_models,
    task_models,
    voice_models,
    document_models,
    whatsapp_models,
    workflow_models,
    calendar_models,
    accounting_sync,
)

from app.followup_scheduler import (
    start_scheduler as start_followup_scheduler,
    stop_scheduler as stop_followup_scheduler,
)

from app.recurring_invoices import (
    start_scheduler as start_recurring_scheduler,
    stop_scheduler as stop_recurring_scheduler,
)

from app.voice_scheduler import (
    start_scheduler as start_voice_scheduler,
    stop_scheduler as stop_voice_scheduler,
)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


# ============================================================
# Database
# ============================================================

Base.metadata.create_all(bind=engine)


# ============================================================
# FastAPI application
# ============================================================

app = FastAPI(
    title="AI Employee OS — Enterprise Edition",
    description=(
        "AI-assisted quotations and invoices, PDF generation, CRM-lite customers, "
        "plus seven specialized AI employees, multi-step voice commands, "
        "a meeting assistant, task manager, AI WhatsApp Assistant, "
        "Generic Workflow Automation Engine, Calendar Sync, "
        "Accounting Integrations, and Public Developer REST API."
    ),
    version="1.0.0",
)


# ============================================================
# CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# API Routers
# ============================================================

app.include_router(auth.router)
app.include_router(customers.router)
app.include_router(quotations.router)
app.include_router(invoices.router)
app.include_router(emails.router)
app.include_router(followups.router)
app.include_router(team.router)
app.include_router(ai_employees.router)
app.include_router(voice_commands.router)
app.include_router(voice_meetings.router)
app.include_router(tasks.router)
app.include_router(documents.router)
app.include_router(whatsapp.router)
app.include_router(workflows.router)
app.include_router(calendar.router)
app.include_router(accounting.router)
app.include_router(public_api.router)
app.include_router(reports.router)
app.include_router(billing.router)
app.include_router(data_export_import.router)


# ============================================================
# Startup
# ============================================================

@app.on_event("startup")
def _on_startup():
    start_followup_scheduler()
    start_recurring_scheduler()
    start_voice_scheduler()


# ============================================================
# Shutdown
# ============================================================

@app.on_event("shutdown")
def _on_shutdown():
    stop_followup_scheduler()
    stop_recurring_scheduler()
    stop_voice_scheduler()


# ============================================================
# Health Check
# ============================================================

@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "service": "ai-employee-os-backend",
    }