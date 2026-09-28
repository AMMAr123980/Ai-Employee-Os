"""
Who the AI employees are and what each one is allowed to do.

EMPLOYEE_CATALOG plays the same role here that EVENT_CATALOG plays for the
workflow engine and INTENT_CATALOG plays for voice: one dict, read by three
different consumers so they can't drift apart —

- the UI, via GET /api/ai-employees, to render the roster and the "try
  asking..." examples on each employee's panel;
- ai_employee_brain.py, to build that employee's planning prompt from its
  persona + the intents it owns;
- routers/ai_employees.py, to check that the intent the model picked is one
  this employee is actually allowed to run. That last check is the load-
  bearing one: it's what stops "ask the Marketing employee to raise a
  purchase order" from working. Departmental separation is enforced here,
  at the catalog, rather than trusted to the prompt.

Adding a department is one entry here + its action functions in
ai_employee_actions.py. Nothing else changes — no new router, no new
schema file, no new confirmation UI.

On personas: `system_prompt` is short and job-shaped on purpose. It exists
to bias slot extraction ("annual leave" -> leave_type=annual), not to give
the model a personality. Long character prompts make the JSON output worse,
and none of this text is ever shown to an end user.
"""
from typing import Any

EMPLOYEE_CATALOG: dict[str, dict[str, Any]] = {

    "hr_officer": {
        "label": "HR Officer",
        "department": "People",
        "description": "Keeps staff records, handles leave requests, runs onboarding checklists, "
                       "and drafts job descriptions and offer letters.",
        "system_prompt": (
            "You are an HR officer for a small-to-mid-sized business. You handle staff records, "
            "leave, onboarding and recruitment paperwork. Leave types are annual, sick, unpaid, "
            "parental or other; default to annual when a reason isn't given. Dates spoken as "
            "'next Monday' or 'the 15th' must be resolved to ISO dates against the supplied "
            "current date, or left out if genuinely ambiguous."
        ),
        "intents": [
            "add_employee", "update_employee", "record_leave_request", "decide_leave_request",
            "generate_onboarding_checklist", "draft_job_description", "hr_headcount_report",
        ],
        "examples": [
            "Add Bilal Ahmed as a warehouse supervisor starting the 1st, reporting to Sana.",
            "Fatima wants annual leave from the 12th to the 16th.",
            "Approve Fatima's leave request.",
            "Build an onboarding checklist for our new accounts assistant.",
            "Write a job description for a junior sales executive.",
            "How many people are on probation right now?",
        ],
    },

    "legal_assistant": {
        "label": "Legal Assistant",
        "department": "Legal",
        "description": "Drafts contracts from your templates, flags risky clauses in documents "
                       "you've received, and tracks renewal and expiry dates.",
        "system_prompt": (
            "You are a contracts assistant for a small business. You draft standard commercial "
            "documents (NDA, MSA, SOW, supply agreement, employment contract) and review "
            "counterparty drafts for commercial risk. You are not a lawyer, you do not give "
            "legal advice, and anything you produce is a draft for a qualified person to check. "
            "When reviewing, focus on: liability caps, indemnities, termination rights, payment "
            "terms, auto-renewal, IP ownership, exclusivity, and governing law."
        ),
        "intents": [
            "draft_contract", "review_contract", "log_contract", "update_contract_status",
            "list_expiring_contracts",
        ],
        "examples": [
            "Draft an NDA for Acme Corp, two years, governed by Pakistani law.",
            "Review the supply agreement Zenith sent and flag anything one-sided.",
            "Log the signed MSA with Acme — starts March 1st, runs 12 months, auto-renews.",
            "What's expiring in the next 60 days?",
        ],
        # Nothing this employee produces should ever leave the building
        # unreviewed, so every intent that generates text lands in
        # CONFIRM_REQUIRED — see ai_employee_actions.py.
    },

    "marketing_executive": {
        "label": "Marketing Executive",
        "department": "Marketing",
        "description": "Plans campaigns, writes email and WhatsApp copy, segments your customer "
                       "list, and keeps a content calendar.",
        "system_prompt": (
            "You are a marketing executive at a small business. You plan and write campaigns for "
            "email, WhatsApp and social. Audiences are described as rules over the CRM, using any "
            "of: pipeline_stage, tag, no_contact_since_days, min_lifetime_value, city. Copy should "
            "be concrete and short; no filler superlatives. For WhatsApp, keep messages under 500 "
            "characters and never open with a wall of text."
        ),
        "intents": [
            "create_campaign", "write_campaign_copy", "preview_campaign_audience",
            "send_campaign", "plan_content_calendar", "segment_customers",
        ],
        "examples": [
            "Set up an email campaign for customers we haven't spoken to in 60 days.",
            "Write the copy for the Ramadan promotion campaign.",
            "How many people would that campaign actually reach?",
            "Plan two weeks of LinkedIn posts about our new product line.",
        ],
    },

    "procurement_officer": {
        "label": "Procurement Officer",
        "department": "Procurement",
        "description": "Manages suppliers, raises purchase orders, compares supplier pricing, "
                       "and chases deliveries.",
        "system_prompt": (
            "You are a procurement officer. You maintain supplier records, raise purchase orders "
            "and compare quotes. Quantities and unit prices must come from what the user actually "
            "said — never estimate a price. If a price wasn't given, leave it out and list it in "
            "missing_info rather than guessing from what things usually cost."
        ),
        "intents": [
            "add_supplier", "update_supplier", "create_purchase_order", "approve_purchase_order",
            "send_purchase_order", "receive_purchase_order", "compare_suppliers",
        ],
        "examples": [
            "Add Zenith Traders as a supplier, Net 30, contact Imran on 0300-1234567.",
            "Raise a PO to Zenith for 50 keyboards at 2,400 each.",
            "Mark PO-000004 as received.",
            "Who should we buy laptops from?",
        ],
    },

    "inventory_controller": {
        "label": "Inventory Controller",
        "department": "Operations",
        "description": "Tracks stock levels, records movements, warns you before you run out, "
                       "and checks whether you can actually fulfil a quotation.",
        "system_prompt": (
            "You are an inventory controller. You track stock items, record receipts, issues and "
            "count adjustments, and flag items at or below their reorder point. Quantities are "
            "numbers with a unit; if the user says 'a couple of boxes' and a box size isn't "
            "established, put quantity in missing_info rather than assuming."
        ),
        "intents": [
            "add_inventory_item", "adjust_stock", "record_stock_receipt", "record_stock_issue",
            "check_stock", "low_stock_report", "check_quotation_fulfillable",
        ],
        "examples": [
            "Add 'Logitech MX Master 3' as a stock item, reorder at 10, we hold 25.",
            "We just received 40 keyboards from Zenith.",
            "How many monitors do we have left?",
            "What's running low?",
            "Can we actually fulfil the quotation we sent Acme?",
        ],
    },

    "bookkeeper": {
        "label": "Bookkeeper",
        "department": "Finance",
        "description": "Records expenses, matches payments against invoices, chases overdue "
                       "money, and tells you where the month actually stands.",
        "system_prompt": (
            "You are a bookkeeper for a small business. You record expenses, reconcile customer "
            "payments against issued invoices, and report on cash position. Amounts must be exact "
            "figures the user stated. Never infer an amount from a description."
        ),
        "intents": [
            "record_expense", "categorise_expenses", "record_payment", "list_overdue_invoices",
            "cash_position_report",
        ],
        "examples": [
            "Record 18,000 for the office internet bill this month.",
            "Acme paid 250,000 against INV-000012.",
            "Who owes us money and how late are they?",
            "How did last month actually finish?",
        ],
    },

    "support_agent": {
        "label": "Support Agent",
        "department": "Customer Service",
        "description": "Triages incoming customer messages, drafts replies, and escalates the "
                       "ones that need a human.",
        "system_prompt": (
            "You are a customer support agent. You triage inbound messages by urgency and topic, "
            "draft replies in the company's voice, and escalate anything involving refunds, "
            "legal threats, safety, or an angry customer asking for a manager. Never promise a "
            "refund, a discount, or a delivery date that wasn't already confirmed in the record."
        ),
        "intents": [
            "triage_message", "draft_support_reply", "escalate_to_human", "log_complaint",
        ],
        "examples": [
            "Triage the messages that came in overnight.",
            "Draft a reply to Acme about the delayed shipment.",
            "Escalate this one — they're asking for a refund.",
        ],
    },

    "ceo_assistant": {
        "label": "CEO Assistant",
        "department": "Executive",
        "description": "Provides high-level executive briefings, synthesizes department metrics, and prioritizes strategic goals.",
        "system_prompt": (
            "You are an executive CEO assistant. You synthesize company-wide operational metrics into daily briefings "
            "and assist leadership with high-level decision support."
        ),
        "intents": ["executive_summary", "brief_ceo"],
        "examples": [
            "Give me an executive summary of this week's operations.",
            "Brief the CEO on open risks and financial status.",
        ],
    },

    "sales_manager": {
        "label": "Sales Manager",
        "department": "Sales",
        "description": "Analyzes deal pipelines, coaches representatives, and optimizes lead conversion strategies.",
        "system_prompt": (
            "You are a sales manager. You review deals in the sales pipeline, coach account representatives, "
            "and suggest closing strategies."
        ),
        "intents": ["sales_pipeline_analysis", "coach_deal"],
        "examples": [
            "Analyze our current sales pipeline bottleneck.",
            "Coach me on closing the deal with Acme Corp.",
        ],
    },

    "recruiter": {
        "label": "Recruiter",
        "department": "Talent",
        "description": "Screens candidate applications, organizes interview schedules, and manages talent acquisition pipelines.",
        "system_prompt": (
            "You are a talent recruiter. You screen job candidates against requirements and maintain talent sourcing pipelines."
        ),
        "intents": ["screen_candidates", "source_talent"],
        "examples": [
            "Screen candidate profiles for the senior developer role.",
            "Source talent strategies for our engineering expansion.",
        ],
    },

    "accountant": {
        "label": "Accountant",
        "department": "Finance & Accounting",
        "description": "Audits general ledgers, prepares tax liability summaries, and reconciles financial accounts.",
        "system_prompt": (
            "You are a professional accountant. You handle general ledger audits, tax summaries, and account reconciliation."
        ),
        "intents": ["audit_ledger", "prepare_tax_summary"],
        "examples": [
            "Audit our recent ledger entries for anomalies.",
            "Prepare a quarterly tax estimate summary.",
        ],
    },

    "content_writer": {
        "label": "Content Writer",
        "department": "Content & Media",
        "description": "Crafts long-form blog articles, drafts company newsletters, and writes official press releases.",
        "system_prompt": (
            "You are a skilled content writer. You author engaging articles, company newsletters, and press releases."
        ),
        "intents": ["write_blog_post", "generate_newsletter"],
        "examples": [
            "Write a blog post about AI automation in operations.",
            "Draft our monthly customer newsletter.",
        ],
    },
}


# What each intent needs extracted. Kept here rather than in
# ai_employee_actions.py so ai_employee_brain.py depends only on this module
# and never imports the code that touches the database — the planner can be
# unit-tested without a session. Slots marked (optional) are never put in
# missing_info; everything else is required and will block auto-execution.
INTENT_SLOTS: dict[str, list[str]] = {
    # HR
    "add_employee": ["full_name", "job_title (optional)", "department (optional)",
                     "email (optional)", "phone (optional)", "joined_on (optional)",
                     "manager_name (optional)", "employment_status (optional)"],
    "update_employee": ["employee_name", "field", "value"],
    "record_leave_request": ["employee_name", "starts_on", "ends_on", "leave_type (optional)",
                             "reason (optional)"],
    "decide_leave_request": ["employee_name", "decision", "decision_note (optional)"],
    "generate_onboarding_checklist": ["employee_name", "role_context (optional)"],
    "draft_job_description": ["job_title", "seniority (optional)", "requirements_note (optional)"],
    "hr_headcount_report": [],

    # Legal
    "draft_contract": ["contract_type", "counterparty_name", "key_terms (optional)",
                       "value_amount (optional)", "starts_on (optional)", "ends_on (optional)",
                       "governing_law (optional)"],
    "review_contract": ["contract_title_or_id"],
    "log_contract": ["title", "counterparty_name", "contract_type (optional)",
                     "starts_on (optional)", "ends_on (optional)", "value_amount (optional)",
                     "auto_renews (optional)", "notice_period_days (optional)"],
    "update_contract_status": ["contract_title_or_id", "status"],
    "list_expiring_contracts": ["within_days (optional)"],

    # Marketing
    "create_campaign": ["name", "goal (optional)", "channel (optional)", "audience (optional)",
                        "scheduled_for (optional)"],
    "write_campaign_copy": ["campaign_name", "angle (optional)", "tone (optional)"],
    "preview_campaign_audience": ["campaign_name"],
    "send_campaign": ["campaign_name"],
    "plan_content_calendar": ["theme", "channel (optional)", "pieces (optional)",
                              "start_on (optional)"],
    "segment_customers": ["audience"],

    # Procurement
    "add_supplier": ["name", "contact_person (optional)", "email (optional)", "phone (optional)",
                     "payment_terms (optional)", "lead_time_days (optional)"],
    "update_supplier": ["supplier_name", "field", "value"],
    "create_purchase_order": ["supplier_name", "items", "expected_on (optional)",
                              "notes (optional)"],
    "approve_purchase_order": ["po_number"],
    "send_purchase_order": ["po_number"],
    "receive_purchase_order": ["po_number", "received_on (optional)", "partial_items (optional)"],
    "compare_suppliers": ["item_description"],

    # Inventory
    "add_inventory_item": ["name", "sku (optional)", "unit (optional)",
                           "quantity_on_hand (optional)", "reorder_point (optional)",
                           "reorder_quantity (optional)", "cost_price (optional)",
                           "sale_price (optional)"],
    "adjust_stock": ["item_name", "new_quantity", "reason (optional)"],
    "record_stock_receipt": ["item_name", "quantity", "supplier_name (optional)",
                             "po_number (optional)"],
    "record_stock_issue": ["item_name", "quantity", "reason (optional)"],
    "check_stock": ["item_name"],
    "low_stock_report": [],
    "check_quotation_fulfillable": ["quotation_number_or_customer"],

    # Finance
    "record_expense": ["description", "amount", "category (optional)", "incurred_on (optional)",
                       "supplier_name (optional)"],
    "categorise_expenses": ["period (optional)"],
    "record_payment": ["invoice_number_or_customer", "amount", "paid_on (optional)"],
    "list_overdue_invoices": [],
    "cash_position_report": ["period (optional)"],

    # Support
    "triage_message": ["message_text (optional)", "customer_name (optional)"],
    "draft_support_reply": ["customer_name", "topic"],
    "escalate_to_human": ["customer_name", "reason"],
    "log_complaint": ["customer_name", "summary", "severity (optional)"],

    # CEO Assistant
    "executive_summary": ["period (optional)"],
    "brief_ceo": ["focus_area (optional)"],

    # Sales Manager
    "sales_pipeline_analysis": [],
    "coach_deal": ["customer_name"],

    # Recruiter
    "screen_candidates": ["job_title"],
    "source_talent": ["role_name"],

    # Accountant
    "audit_ledger": [],
    "prepare_tax_summary": ["period (optional)"],

    # Content Writer
    "write_blog_post": ["topic"],
    "generate_newsletter": ["month (optional)"],
}


# Recurring duties: things an employee should do without being asked. The
# scheduler that already runs followups can call
# POST /api/ai-employees/{key}/run-duty/{duty} on this cadence; there is
# deliberately no new scheduler in this module.
DUTIES: dict[str, dict[str, Any]] = {
    "low_stock_sweep": {
        "employee": "inventory_controller",
        "intent": "low_stock_report",
        "cadence": "daily",
        "description": "Flags every item at or below its reorder point and opens a task for each.",
    },
    "contract_expiry_sweep": {
        "employee": "legal_assistant",
        "intent": "list_expiring_contracts",
        "cadence": "weekly",
        "description": "Surfaces contracts expiring or auto-renewing inside their notice window.",
    },
    "overdue_invoice_sweep": {
        "employee": "bookkeeper",
        "intent": "list_overdue_invoices",
        "cadence": "daily",
        "description": "Lists invoices past their due date, oldest first.",
    },
    "leave_balance_check": {
        "employee": "hr_officer",
        "intent": "hr_headcount_report",
        "cadence": "monthly",
        "description": "Headcount, probation endings and remaining leave balances.",
    },
}


def get_employee(key: str) -> dict[str, Any]:
    employee = EMPLOYEE_CATALOG.get(key)
    if employee is None:
        raise KeyError(f"Unknown AI employee: {key}")
    return employee


def employee_owns_intent(key: str, intent: str) -> bool:
    """The departmental boundary. Called by the router before execution, not
    by the prompt — a model that hallucinates an intent outside its own
    catalog entry gets rejected rather than obeyed."""
    try:
        return intent in get_employee(key)["intents"]
    except KeyError:
        return False


def employee_for_intent(intent: str) -> str | None:
    """Reverse lookup, for voice commands and workflow steps that name an
    intent without naming an employee."""
    for key, info in EMPLOYEE_CATALOG.items():
        if intent in info["intents"]:
            return key
    return None
