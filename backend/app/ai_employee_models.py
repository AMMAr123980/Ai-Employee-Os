"""
Specialized AI Employees — data model.

The existing modules (quotations, invoices, emails, followups, meetings,
tasks, reporting, workflows, voice) all serve one department: sales. This
module adds the back-office departments — HR, Legal, Marketing, Procurement,
Inventory, Finance — as *employees* rather than as six more feature areas.

The distinction matters and drives the whole design:

- A **feature area** is a set of screens a human drives. Adding six of them
  means six routers, six schema files, six sets of CRUD endpoints, and six
  places to re-implement "who's allowed to send this to a real person".
- An **employee** is a declarative definition (persona, the actions it may
  take, the tables it owns) plus ONE shared run pipeline: brief in, Claude
  call, structured action, safety gate, execute, log. Adding a seventh
  department is then one catalog entry + N action functions — exactly the
  open/closed shape workflow_actions.ACTION_REGISTRY and
  voice_actions.VOICE_ACTION_REGISTRY already use.

So there are two kinds of table in here, and they are deliberately separate:

1. `AIEmployeeRun` — the audit log, one row per brief handed to any
   employee, in any department. Same job VoiceCommand does for voice: it
   answers "why did the AI raise that purchase order?" long after the fact,
   and it holds AWAITING_CONFIRMATION state between the plan and the tap.
   Mirrors VoiceCommand's column set on purpose (status enum, action_json,
   summary, missing_info_json, result_json) so the confirmation UI built for
   voice commands renders an employee run with no changes.

2. The domain tables — Employee, LeaveRequest, Contract, Campaign,
   Supplier, PurchaseOrder, InventoryItem, StockMovement, Expense. These are
   plain business records. They are useful with the AI switched off entirely,
   and nothing in them references AIEmployeeRun. That's intentional: if the
   AI drafts a contract and you later decide to write contracts by hand, the
   contracts table doesn't become dead weight.

Inventory gets the only cross-module hook: StockMovement can carry a
`quotation_id`/`invoice_id`, because "we quoted 25 laptops we don't have"
is the one question a sales-only system genuinely cannot answer.

Drop-in with one import line, diffable on its own — same reasoning as
workflow_models.py and voice_models.py.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, Date, ForeignKey, Enum, Text,
)
from sqlalchemy.orm import relationship

from app.database import Base


def gen_id() -> str:
    return uuid.uuid4().hex[:12]


# --------------------------------------------------------------------------
# 1. The shared run log
# --------------------------------------------------------------------------

class AIEmployeeRunStatus(str, enum.Enum):
    PLANNED = "planned"                                # brief parsed, nothing done yet
    NO_ACTION = "no_action"                            # brief didn't map to anything this employee does
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    EXECUTED = "executed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AIEmployeeRunTrigger(str, enum.Enum):
    USER = "user"          # someone typed a brief in the employee's chat panel
    VOICE = "voice"        # arrived via voice_commands.py
    WORKFLOW = "workflow"  # a workflow chain called this employee as a step
    SCHEDULE = "schedule"  # a recurring duty (see ai_employee_registry.DUTIES)


class AIEmployeeRun(Base):
    __tablename__ = "ai_employee_runs"

    id = Column(String, primary_key=True, default=gen_id)
    company_id = Column(String, ForeignKey("companies.id"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=True)  # null for SCHEDULE runs

    employee_key = Column(String, nullable=False, index=True)  # "hr_officer", "legal_assistant", ...
    trigger = Column(Enum(AIEmployeeRunTrigger), default=AIEmployeeRunTrigger.USER, nullable=False)

    brief = Column(Text, nullable=False)  # what the human asked for, verbatim
    intent = Column(String, nullable=True)
    confidence = Column(Float, nullable=True)
    action_json = Column(Text, nullable=True)   # {"type": ..., "config": {...}} — same shape as a
                                                # workflow step and a voice command, on purpose
    summary = Column(Text, nullable=True)
    missing_info_json = Column(Text, nullable=True)

    status = Column(Enum(AIEmployeeRunStatus), default=AIEmployeeRunStatus.PLANNED, nullable=False, index=True)
    result_json = Column(Text, nullable=True)
    error = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    executed_at = Column(DateTime, nullable=True)

    user = relationship("User")


class AIEmployeeConfig(Base):
    """Per-company on/off switch and tuning for one employee.

    Absent row = employee enabled with catalog defaults. Deliberately
    not seeded at signup: a company that never opens the HR panel should
    have no HR rows at all, and the catalog is the source of truth for
    defaults anyway (same reason EVENT_CATALOG isn't mirrored into a table).
    """
    __tablename__ = "ai_employee_configs"

    id = Column(String, primary_key=True, default=gen_id)
    company_id = Column(String, ForeignKey("companies.id"), nullable=False, index=True)
    employee_key = Column(String, nullable=False, index=True)

    enabled = Column(Boolean, default=True, nullable=False)
    display_name = Column(String, nullable=True)   # "Ayesha" instead of "HR Officer", if they want
    autonomy_level = Column(String, default="standard", nullable=False)
    # "standard"  — the catalog's own AUTO_EXECUTE/CONFIRM_REQUIRED split
    # "cautious"  — everything is held for confirmation, including internal writes
    # (there is deliberately no "full" level that auto-sends external messages;
    #  see ai_employee_actions.py, ALWAYS_CONFIRM.)
    instructions = Column(Text, nullable=True)  # appended to the employee's system prompt:
                                                # "we're a 40-person firm in Lahore, PKR, Sun-Thu week"

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# --------------------------------------------------------------------------
# 2. HR
# --------------------------------------------------------------------------

class EmploymentStatus(str, enum.Enum):
    ACTIVE = "active"
    PROBATION = "probation"
    NOTICE = "notice"
    TERMINATED = "terminated"


class Employee(Base):
    """A staff member of the customer's company.

    Not the same thing as `User`: a User is someone who logs into this
    system, an Employee is someone on the payroll. A warehouse packer has
    an Employee row and no User row; a contracted developer may have a
    User row and no Employee row. `user_id` links them when both exist.
    """
    __tablename__ = "hr_employees"

    id = Column(String, primary_key=True, default=gen_id)
    company_id = Column(String, ForeignKey("companies.id"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=True)

    full_name = Column(String, nullable=False)
    email = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    job_title = Column(String, nullable=True)
    department = Column(String, nullable=True)
    manager_employee_id = Column(String, ForeignKey("hr_employees.id"), nullable=True)

    employment_status = Column(Enum(EmploymentStatus), default=EmploymentStatus.ACTIVE, nullable=False)
    joined_on = Column(Date, nullable=True)
    ended_on = Column(Date, nullable=True)

    # Salary is stored but never included in an LLM prompt — see
    # ai_employee_brain.py, _redact().
    salary_amount = Column(Float, nullable=True)
    salary_currency = Column(String, nullable=True)

    annual_leave_days = Column(Float, default=20.0, nullable=False)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    manager = relationship("Employee", remote_side=[id])


class LeaveType(str, enum.Enum):
    ANNUAL = "annual"
    SICK = "sick"
    UNPAID = "unpaid"
    PARENTAL = "parental"
    OTHER = "other"


class LeaveStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class LeaveRequest(Base):
    __tablename__ = "hr_leave_requests"

    id = Column(String, primary_key=True, default=gen_id)
    company_id = Column(String, ForeignKey("companies.id"), nullable=False, index=True)
    employee_id = Column(String, ForeignKey("hr_employees.id"), nullable=False, index=True)

    leave_type = Column(Enum(LeaveType), default=LeaveType.ANNUAL, nullable=False)
    starts_on = Column(Date, nullable=False)
    ends_on = Column(Date, nullable=False)
    days = Column(Float, nullable=False)
    reason = Column(Text, nullable=True)

    status = Column(Enum(LeaveStatus), default=LeaveStatus.PENDING, nullable=False, index=True)
    decided_by_user_id = Column(String, ForeignKey("users.id"), nullable=True)
    decided_at = Column(DateTime, nullable=True)
    decision_note = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    employee = relationship("Employee")


class OnboardingTask(Base):
    """Checklist items generated when someone joins. Separate from the main
    `Task` table because these are templated, employee-scoped, and shouldn't
    flood the sales team's task list."""
    __tablename__ = "hr_onboarding_tasks"

    id = Column(String, primary_key=True, default=gen_id)
    company_id = Column(String, ForeignKey("companies.id"), nullable=False, index=True)
    employee_id = Column(String, ForeignKey("hr_employees.id"), nullable=False, index=True)

    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    owner = Column(String, nullable=True)  # free text: "IT", "Line manager", "Finance"
    due_on = Column(Date, nullable=True)
    completed = Column(Boolean, default=False, nullable=False)
    completed_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    employee = relationship("Employee")


# --------------------------------------------------------------------------
# 3. Legal
# --------------------------------------------------------------------------

class ContractStatus(str, enum.Enum):
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    SENT = "sent"
    SIGNED = "signed"
    ACTIVE = "active"
    EXPIRED = "expired"
    TERMINATED = "terminated"


class ContractParty(str, enum.Enum):
    CUSTOMER = "customer"
    SUPPLIER = "supplier"
    EMPLOYEE = "employee"
    OTHER = "other"


class Contract(Base):
    __tablename__ = "legal_contracts"

    id = Column(String, primary_key=True, default=gen_id)
    company_id = Column(String, ForeignKey("companies.id"), nullable=False, index=True)

    title = Column(String, nullable=False)
    contract_type = Column(String, nullable=True)  # "NDA", "MSA", "SOW", "employment", "supply"
    counterparty_type = Column(Enum(ContractParty), default=ContractParty.OTHER, nullable=False)
    counterparty_name = Column(String, nullable=True)
    customer_id = Column(String, ForeignKey("customers.id"), nullable=True)
    supplier_id = Column(String, ForeignKey("proc_suppliers.id"), nullable=True)
    employee_id = Column(String, ForeignKey("hr_employees.id"), nullable=True)

    status = Column(Enum(ContractStatus), default=ContractStatus.DRAFT, nullable=False, index=True)
    body = Column(Text, nullable=True)           # the drafted text
    value_amount = Column(Float, nullable=True)
    value_currency = Column(String, nullable=True)

    starts_on = Column(Date, nullable=True)
    ends_on = Column(Date, nullable=True, index=True)
    notice_period_days = Column(Integer, nullable=True)
    auto_renews = Column(Boolean, default=False, nullable=False)

    # Populated by the review action: [{"clause": ..., "risk": "high",
    # "why": ..., "suggestion": ...}]. Stored rather than regenerated so the
    # same document doesn't get a different answer on every open.
    risk_findings_json = Column(Text, nullable=True)
    reviewed_at = Column(DateTime, nullable=True)

    # No documents table in this build, so this is a plain reference rather than
    # an FK — see README "What's deliberately not here". Populate it if/when a
    # document store lands.
    document_ref = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# --------------------------------------------------------------------------
# 4. Marketing
# --------------------------------------------------------------------------

class CampaignChannel(str, enum.Enum):
    EMAIL = "email"
    WHATSAPP = "whatsapp"
    SOCIAL = "social"
    MIXED = "mixed"


class CampaignStatus(str, enum.Enum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    SENDING = "sending"
    SENT = "sent"
    PAUSED = "paused"
    CANCELLED = "cancelled"


class Campaign(Base):
    __tablename__ = "mkt_campaigns"

    id = Column(String, primary_key=True, default=gen_id)
    company_id = Column(String, ForeignKey("companies.id"), nullable=False, index=True)
    created_by_user_id = Column(String, ForeignKey("users.id"), nullable=True)

    name = Column(String, nullable=False)
    goal = Column(Text, nullable=True)
    channel = Column(Enum(CampaignChannel), default=CampaignChannel.EMAIL, nullable=False)
    status = Column(Enum(CampaignStatus), default=CampaignStatus.DRAFT, nullable=False, index=True)

    # How the recipient list is chosen, e.g.
    # {"pipeline_stage": "negotiation", "no_contact_since_days": 30, "tag": "wholesale"}
    # Stored as a *rule*, not a frozen list of ids, so the list is re-resolved
    # at send time — a customer who unsubscribed yesterday drops out on their own.
    audience_json = Column(Text, nullable=True)
    audience_size = Column(Integer, nullable=True)  # cached count from the last preview

    subject = Column(String, nullable=True)
    body = Column(Text, nullable=True)
    scheduled_for = Column(DateTime, nullable=True)
    sent_at = Column(DateTime, nullable=True)

    sent_count = Column(Integer, default=0, nullable=False)
    failed_count = Column(Integer, default=0, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ContentPiece(Base):
    """A single dated item on the content calendar — a post, a newsletter,
    a product announcement. Not a Campaign: a Campaign sends to a list, a
    ContentPiece is something a human publishes."""
    __tablename__ = "mkt_content_pieces"

    id = Column(String, primary_key=True, default=gen_id)
    company_id = Column(String, ForeignKey("companies.id"), nullable=False, index=True)
    campaign_id = Column(String, ForeignKey("mkt_campaigns.id"), nullable=True)

    title = Column(String, nullable=False)
    channel = Column(String, nullable=True)  # "linkedin", "instagram", "blog", "newsletter"
    body = Column(Text, nullable=True)
    hashtags = Column(String, nullable=True)
    publish_on = Column(Date, nullable=True, index=True)
    published = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)


# --------------------------------------------------------------------------
# 5. Procurement
# --------------------------------------------------------------------------

class Supplier(Base):
    __tablename__ = "proc_suppliers"

    id = Column(String, primary_key=True, default=gen_id)
    company_id = Column(String, ForeignKey("companies.id"), nullable=False, index=True)

    name = Column(String, nullable=False, index=True)
    contact_person = Column(String, nullable=True)
    email = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    address = Column(Text, nullable=True)
    payment_terms = Column(String, nullable=True)   # "Net 30", "50% advance"
    lead_time_days = Column(Integer, nullable=True)
    currency = Column(String, nullable=True)

    # Rolling averages maintained by the procurement employee, not typed in.
    rating = Column(Float, nullable=True)              # 0-5, quality/reliability
    on_time_rate = Column(Float, nullable=True)        # 0-1, from received POs
    notes = Column(Text, nullable=True)
    active = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PurchaseOrderStatus(str, enum.Enum):
    DRAFT = "draft"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    SENT = "sent"
    PARTIALLY_RECEIVED = "partially_received"
    RECEIVED = "received"
    CANCELLED = "cancelled"


class PurchaseOrder(Base):
    __tablename__ = "proc_purchase_orders"

    id = Column(String, primary_key=True, default=gen_id)
    company_id = Column(String, ForeignKey("companies.id"), nullable=False, index=True)
    supplier_id = Column(String, ForeignKey("proc_suppliers.id"), nullable=False, index=True)
    created_by_user_id = Column(String, ForeignKey("users.id"), nullable=True)

    number = Column(String, nullable=False)  # "PO-000001", same scheme as QUO-/INV-
    status = Column(Enum(PurchaseOrderStatus), default=PurchaseOrderStatus.DRAFT, nullable=False, index=True)

    subtotal = Column(Float, default=0.0, nullable=False)
    tax_percent = Column(Float, default=0.0, nullable=False)
    total = Column(Float, default=0.0, nullable=False)
    currency = Column(String, nullable=True)

    expected_on = Column(Date, nullable=True)
    received_on = Column(Date, nullable=True)
    notes = Column(Text, nullable=True)

    approved_by_user_id = Column(String, ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    supplier = relationship("Supplier")
    items = relationship("PurchaseOrderItem", back_populates="purchase_order", cascade="all, delete-orphan")


class PurchaseOrderItem(Base):
    __tablename__ = "proc_purchase_order_items"

    id = Column(String, primary_key=True, default=gen_id)
    purchase_order_id = Column(String, ForeignKey("proc_purchase_orders.id"), nullable=False, index=True)
    inventory_item_id = Column(String, ForeignKey("inv_items.id"), nullable=True)

    description = Column(String, nullable=False)
    quantity = Column(Float, nullable=False)
    unit_price = Column(Float, nullable=False)
    line_total = Column(Float, nullable=False)
    quantity_received = Column(Float, default=0.0, nullable=False)

    purchase_order = relationship("PurchaseOrder", back_populates="items")


# --------------------------------------------------------------------------
# 6. Inventory
# --------------------------------------------------------------------------

class InventoryItem(Base):
    __tablename__ = "inv_items"

    id = Column(String, primary_key=True, default=gen_id)
    company_id = Column(String, ForeignKey("companies.id"), nullable=False, index=True)

    sku = Column(String, nullable=True, index=True)
    name = Column(String, nullable=False, index=True)
    description = Column(Text, nullable=True)
    category = Column(String, nullable=True)
    unit = Column(String, default="pcs", nullable=False)

    quantity_on_hand = Column(Float, default=0.0, nullable=False)
    quantity_reserved = Column(Float, default=0.0, nullable=False)  # committed to open quotations/orders
    reorder_point = Column(Float, nullable=True)
    reorder_quantity = Column(Float, nullable=True)

    cost_price = Column(Float, nullable=True)
    sale_price = Column(Float, nullable=True)
    currency = Column(String, nullable=True)

    preferred_supplier_id = Column(String, ForeignKey("proc_suppliers.id"), nullable=True)
    location = Column(String, nullable=True)
    active = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def quantity_available(self) -> float:
        return (self.quantity_on_hand or 0.0) - (self.quantity_reserved or 0.0)

    @property
    def needs_reorder(self) -> bool:
        if self.reorder_point is None:
            return False
        return self.quantity_available <= self.reorder_point


class StockMovementType(str, enum.Enum):
    RECEIPT = "receipt"          # arrived from a supplier
    ISSUE = "issue"              # went out to a customer
    ADJUSTMENT = "adjustment"    # stock count correction
    RESERVATION = "reservation"  # held for an open quotation
    RELEASE = "release"          # reservation freed (quotation lost/expired)
    RETURN = "return"


class StockMovement(Base):
    """Append-only ledger. `InventoryItem.quantity_on_hand` is a cached
    running total, and this table is the truth — if they ever disagree, the
    ledger wins and the cache gets rebuilt. Worth the extra table: "who
    changed the stock figure and when" is the first question asked whenever
    a count doesn't match, and a mutable quantity column cannot answer it.
    """
    __tablename__ = "inv_stock_movements"

    id = Column(String, primary_key=True, default=gen_id)
    company_id = Column(String, ForeignKey("companies.id"), nullable=False, index=True)
    item_id = Column(String, ForeignKey("inv_items.id"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=True)

    movement_type = Column(Enum(StockMovementType), nullable=False)
    quantity = Column(Float, nullable=False)  # signed: +receipt, -issue
    balance_after = Column(Float, nullable=True)
    reason = Column(Text, nullable=True)

    # Cross-module links — the point of the whole module, see file docstring.
    quotation_id = Column(String, ForeignKey("quotations.id"), nullable=True)
    invoice_id = Column(String, ForeignKey("invoices.id"), nullable=True)
    purchase_order_id = Column(String, ForeignKey("proc_purchase_orders.id"), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    item = relationship("InventoryItem")


# --------------------------------------------------------------------------
# 7. Finance / bookkeeping
# --------------------------------------------------------------------------

class ExpenseStatus(str, enum.Enum):
    RECORDED = "recorded"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    REIMBURSED = "reimbursed"


class Expense(Base):
    """Money going out. Invoices already cover money coming in; without this
    the reporting module can only ever show half a picture."""
    __tablename__ = "fin_expenses"

    id = Column(String, primary_key=True, default=gen_id)
    company_id = Column(String, ForeignKey("companies.id"), nullable=False, index=True)
    submitted_by_user_id = Column(String, ForeignKey("users.id"), nullable=True)
    employee_id = Column(String, ForeignKey("hr_employees.id"), nullable=True)
    supplier_id = Column(String, ForeignKey("proc_suppliers.id"), nullable=True)
    purchase_order_id = Column(String, ForeignKey("proc_purchase_orders.id"), nullable=True)

    description = Column(String, nullable=False)
    category = Column(String, nullable=True)  # "travel", "software", "rent", "stock"
    amount = Column(Float, nullable=False)
    tax_amount = Column(Float, default=0.0, nullable=False)
    currency = Column(String, nullable=True)
    incurred_on = Column(Date, nullable=True, index=True)

    status = Column(Enum(ExpenseStatus), default=ExpenseStatus.RECORDED, nullable=False, index=True)
    receipt_ref = Column(String, nullable=True)  # plain reference; see Contract.document_ref
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
