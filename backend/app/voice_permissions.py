"""
Who is allowed to say what.

Being logged in used to be the only check, which meant anyone with an account
could move a deal to won, email a customer a quotation, or record a payment —
by voice, with no second pair of eyes. The product description sells
department-based permissions; this is the enforcement side of that.

The model is deliberately boring:

    intent -> permission -> role

`INTENT_PERMISSIONS` groups the intents into seven permissions, because nobody
can reason about a twenty-row grid but everyone can answer "may a member email
customers?". `ROLE_PERMISSIONS` maps this app's three roles (owner, admin,
member) onto those permissions, and `VoiceRolePermission` rows override the
defaults per company — so a company that wants members to draft quotations can
grant it without a code change, and an empty override table is a fully working
system.

Two decisions worth defending:

1. **Unknown roles get read-only.** If a role string this module has never seen
   turns up, it gets the minimum. The opposite default means adding a role to
   the User model silently grants send-email-to-customers to everyone holding it.

2. **The check runs in the executor, not only in the prompt.** Same reasoning as
   `employee_owns_intent()` in the AI employees module: a prompt is a suggestion
   to a model, an `if` is a guarantee. A user whose role can't send email gets
   PermissionDenied even if the planner cheerfully produced a send_email step.

A permission failure inside a multi-step plan fails that step and lets the rest
run. "Add a note on Acme and email them the quote" when you may do the first but
not the second should do the first.
"""
import logging
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.voice_models import VoiceRolePermission

logger = logging.getLogger(__name__)

# --- permissions ---------------------------------------------------------
READ_BUSINESS_DATA = "voice.read"           # reports, lookups, summaries
MANAGE_TASKS = "voice.tasks"                # tasks, reminders, conditional follow-ups
MANAGE_CRM = "voice.crm"                    # notes, pipeline stage
MANAGE_SALES_DOCS = "voice.sales_docs"      # draft quotations and invoices
SEND_TO_CUSTOMER = "voice.send_customer"    # email anything outward
MANAGE_FINANCE = "voice.finance"            # payments, invoice status, recurring billing
DELEGATE_EMPLOYEES = "voice.delegate"       # hand a brief to an AI employee

ALL_PERMISSIONS = {
    READ_BUSINESS_DATA, MANAGE_TASKS, MANAGE_CRM, MANAGE_SALES_DOCS,
    SEND_TO_CUSTOMER, MANAGE_FINANCE, DELEGATE_EMPLOYEES,
}

# --- intent -> permission ------------------------------------------------
INTENT_PERMISSIONS: dict[str, str] = {
    # tasks & scheduling
    "create_task": MANAGE_TASKS,
    "schedule_meeting": MANAGE_TASKS,
    "schedule_followup": MANAGE_TASKS,
    "complete_task": MANAGE_TASKS,
    # CRM
    "add_customer_note": MANAGE_CRM,
    "change_pipeline_stage": MANAGE_CRM,
    "create_customer": MANAGE_CRM,
    # sales documents
    "draft_quotation": MANAGE_SALES_DOCS,
    "create_invoice": MANAGE_SALES_DOCS,
    # outward email
    "email_quotation": SEND_TO_CUSTOMER,
    "send_invoice": SEND_TO_CUSTOMER,
    "send_payment_reminder": SEND_TO_CUSTOMER,
    "send_email": SEND_TO_CUSTOMER,
    # finance
    "record_payment": MANAGE_FINANCE,
    "set_recurring_invoice": MANAGE_FINANCE,
    # reads
    "sales_report": READ_BUSINESS_DATA,
    "outstanding_invoices": READ_BUSINESS_DATA,
    "customer_summary": READ_BUSINESS_DATA,
    "my_tasks": READ_BUSINESS_DATA,
    "email_activity_summary": READ_BUSINESS_DATA,
    "ask_documents": READ_BUSINESS_DATA,
    # delegation
    "ask_ai_employee": DELEGATE_EMPLOYEES,
}

# --- role -> permissions -------------------------------------------------
# This app has three roles. Owner and admin get everything; member is the one
# that needed a decision, and it's set to "can do the work, can't reach the
# customer or the books unaided".
ROLE_PERMISSIONS: dict[str, set[str]] = {
    "owner": set(ALL_PERMISSIONS),
    "admin": set(ALL_PERMISSIONS),
    "member": {READ_BUSINESS_DATA, MANAGE_TASKS, MANAGE_CRM, MANAGE_SALES_DOCS, DELEGATE_EMPLOYEES},
}

READ_ONLY = {READ_BUSINESS_DATA}


class PermissionDenied(Exception):
    def __init__(self, intent: str, permission: str, role: str):
        self.intent = intent
        self.permission = permission
        self.role = role
        super().__init__(f"Role '{role}' lacks {permission} (needed for {intent})")


def role_of(user) -> str:
    raw = getattr(user, "role", None)
    if raw is None:
        return "member"
    return str(getattr(raw, "value", raw)).strip().lower()


def permissions_for(db: Session, company_id: str, role: str) -> set[str]:
    base = set(ROLE_PERMISSIONS.get(role, READ_ONLY))
    if role not in ROLE_PERMISSIONS:
        logger.info("Unknown role %r in company %s — defaulting to read-only", role, company_id)

    overrides = (
        db.query(VoiceRolePermission)
        .filter(VoiceRolePermission.company_id == company_id, VoiceRolePermission.role == role)
        .all()
    )
    for row in overrides:
        if row.permission not in ALL_PERMISSIONS:
            continue
        if row.allowed:
            base.add(row.permission)
        else:
            base.discard(row.permission)
    return base


def required_permission(intent: str) -> Optional[str]:
    return INTENT_PERMISSIONS.get(intent)


def can(db: Session, user, intent: str) -> bool:
    permission = required_permission(intent)
    if permission is None:
        return True  # "unclear" and anything unmapped does nothing anyway
    return permission in permissions_for(db, user.company_id, role_of(user))


def require(db: Session, user, intent: str) -> None:
    permission = required_permission(intent)
    if permission is None:
        return
    role = role_of(user)
    if permission not in permissions_for(db, user.company_id, role):
        raise PermissionDenied(intent, permission, role)


def allowed_intents(db: Session, user, intents: Iterable[str]) -> list[str]:
    """Scopes the planning prompt: someone who can't send email is never shown
    send_email as an option, so the model doesn't propose something that will be
    refused a moment later. The executor still checks — this is ergonomics, not
    the enforcement."""
    granted = permissions_for(db, user.company_id, role_of(user))
    return [
        intent for intent in intents
        if INTENT_PERMISSIONS.get(intent) is None or INTENT_PERMISSIONS[intent] in granted
    ]
