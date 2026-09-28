import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Column, String, Float, Integer, DateTime, ForeignKey, Enum, Text, Boolean, UniqueConstraint
)
from sqlalchemy.orm import relationship

from app.database import Base


def gen_id() -> str:
    return uuid.uuid4().hex[:12]


class QuotationStatus(str, enum.Enum):
    DRAFT = "draft"
    SENT = "sent"
    APPROVED = "approved"
    REJECTED = "rejected"
    CONVERTED = "converted"  # converted to invoice


class InvoiceStatus(str, enum.Enum):
    UNPAID = "unpaid"
    PARTIALLY_PAID = "partially_paid"
    PAID = "paid"
    OVERDUE = "overdue"


class UserRole(str, enum.Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


class PipelineStage(str, enum.Enum):
    NEW = "new"
    CONTACTED = "contacted"
    QUALIFIED = "qualified"
    PROPOSAL = "proposal"
    NEGOTIATION = "negotiation"
    WON = "won"
    LOST = "lost"


class Plan(str, enum.Enum):
    """Billing tier. Drives the AI-request, transcription and storage caps in
    usage_metering.py — without this column those limits are a pricing page,
    not a system."""

    BASIC = "basic"
    PRO = "pro"
    BUSINESS = "business"


class Company(Base):
    __tablename__ = "companies"

    id = Column(String, primary_key=True, default=gen_id)
    name = Column(String, nullable=False)
    plan = Column(Enum(Plan), default=Plan.PRO, nullable=False)
    # IANA name, e.g. "Asia/Karachi". Spoken times like "Friday at 3" are
    # resolved in this zone unless the browser supplies its own.
    timezone = Column(String, nullable=True)
    stripe_customer_id = Column(String, nullable=True)
    stripe_subscription_id = Column(String, nullable=True)
    subscription_status = Column(String, default="active", nullable=False)
    current_period_end = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    users = relationship("User", back_populates="company")


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=gen_id)
    company_id = Column(String, ForeignKey("companies.id"), nullable=False)
    email = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    name = Column(String, nullable=False)
    role = Column(Enum(UserRole), default=UserRole.OWNER)

    mfa_enabled = Column(Boolean, default=False, nullable=False)
    mfa_secret = Column(String, nullable=True)
    sso_provider = Column(String, nullable=True)  # "google", "microsoft", "saml"
    sso_id = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    company = relationship("Company", back_populates="users")



class Customer(Base):
    __tablename__ = "customers"

    id = Column(String, primary_key=True, default=gen_id)
    company_id = Column(String, ForeignKey("companies.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    company = Column(String, nullable=True)
    email = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    address = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)

    pipeline_stage = Column(Enum(PipelineStage), default=PipelineStage.NEW, nullable=False)
    lead_source = Column(String, nullable=True)  # e.g. "referral", "website", "cold outreach"

    ai_relationship_summary = Column(Text, nullable=True)
    ai_summary_generated_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    quotations = relationship("Quotation", back_populates="customer")
    invoices = relationship("Invoice", back_populates="customer")


class Quotation(Base):
    __tablename__ = "quotations"
    __table_args__ = (UniqueConstraint("company_id", "number", name="uq_quotation_company_number"),)

    id = Column(String, primary_key=True, default=gen_id)
    company_id = Column(String, ForeignKey("companies.id"), nullable=False, index=True)
    number = Column(String, nullable=False)  # unique per-company, enforced at query time
    customer_id = Column(String, ForeignKey("customers.id"), nullable=False)
    status = Column(Enum(QuotationStatus), default=QuotationStatus.DRAFT)

    subtotal = Column(Float, default=0.0)
    discount_percent = Column(Float, default=0.0)
    tax_percent = Column(Float, default=0.0)
    total = Column(Float, default=0.0)
    currency = Column(String, default="USD")

    notes = Column(Text, nullable=True)
    ai_summary = Column(Text, nullable=True)  # AI-generated cover summary

    valid_until = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    customer = relationship("Customer", back_populates="quotations")
    items = relationship("QuotationItem", back_populates="quotation", cascade="all, delete-orphan")
    invoice = relationship("Invoice", back_populates="quotation", uselist=False)


class QuotationItem(Base):
    __tablename__ = "quotation_items"

    id = Column(String, primary_key=True, default=gen_id)
    quotation_id = Column(String, ForeignKey("quotations.id"), nullable=False)
    description = Column(String, nullable=False)
    quantity = Column(Float, default=1.0)
    unit_price = Column(Float, default=0.0)
    line_total = Column(Float, default=0.0)

    quotation = relationship("Quotation", back_populates="items")


class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (UniqueConstraint("company_id", "number", name="uq_invoice_company_number"),)

    id = Column(String, primary_key=True, default=gen_id)
    company_id = Column(String, ForeignKey("companies.id"), nullable=False, index=True)
    number = Column(String, nullable=False)  # unique per-company, enforced at query time
    customer_id = Column(String, ForeignKey("customers.id"), nullable=False)
    quotation_id = Column(String, ForeignKey("quotations.id"), nullable=True)

    status = Column(Enum(InvoiceStatus), default=InvoiceStatus.UNPAID)

    subtotal = Column(Float, default=0.0)
    discount_percent = Column(Float, default=0.0)
    tax_percent = Column(Float, default=0.0)
    total = Column(Float, default=0.0)
    amount_paid = Column(Float, default=0.0)
    currency = Column(String, default="USD")

    due_date = Column(DateTime, nullable=True)
    is_recurring = Column(Boolean, default=False)
    recurrence_interval_days = Column(Integer, nullable=True)
    next_recurrence_at = Column(DateTime, nullable=True)  # when the scheduler should generate the next occurrence
    recurrence_parent_id = Column(String, ForeignKey("invoices.id"), nullable=True)  # set on generated occurrences

    notes = Column(Text, nullable=True)
    payment_link = Column(String, nullable=True)  # Payment link URL (Stripe, PayPal, UPI, custom)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    customer = relationship("Customer", back_populates="invoices")
    quotation = relationship("Quotation", back_populates="invoice")
    items = relationship("InvoiceItem", back_populates="invoice", cascade="all, delete-orphan")


class InvoiceItem(Base):
    __tablename__ = "invoice_items"

    id = Column(String, primary_key=True, default=gen_id)
    invoice_id = Column(String, ForeignKey("invoices.id"), nullable=False)
    description = Column(String, nullable=False)
    quantity = Column(Float, default=1.0)
    unit_price = Column(Float, default=0.0)
    line_total = Column(Float, default=0.0)

    invoice = relationship("Invoice", back_populates="items")


class EmailStatus(str, enum.Enum):
    DRAFT = "draft"
    SENT = "sent"
    FAILED = "failed"


class FollowUpStatus(str, enum.Enum):
    PENDING = "pending"  # follow_up_at set, not yet due or not yet processed
    DONE = "done"        # scheduler already created a follow-up draft for this


class EmailMessage(Base):
    """Outbound & Inbound email log — customer activity timeline entry."""

    __tablename__ = "email_messages"

    id = Column(String, primary_key=True, default=gen_id)
    company_id = Column(String, ForeignKey("companies.id"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=True)
    customer_id = Column(String, ForeignKey("customers.id"), nullable=False, index=True)
    quotation_id = Column(String, ForeignKey("quotations.id"), nullable=True)
    invoice_id = Column(String, ForeignKey("invoices.id"), nullable=True)
    parent_email_id = Column(String, ForeignKey("email_messages.id"), nullable=True)

    direction = Column(String, default="outbound", nullable=False)  # "outbound" or "inbound"
    inbound_message_id = Column(String, nullable=True, index=True)

    to_email = Column(String, nullable=False)
    subject = Column(String, nullable=False)
    body = Column(Text, nullable=False)
    status = Column(Enum(EmailStatus), default=EmailStatus.DRAFT)
    error_message = Column(Text, nullable=True)

    follow_up_at = Column(DateTime, nullable=True)
    follow_up_status = Column(Enum(FollowUpStatus), nullable=True)  # set only when follow_up_at is set
    auto_generated = Column(Boolean, default=False)  # True if the scheduler drafted this
    dismissed = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    sent_at = Column(DateTime, nullable=True)

    customer = relationship("Customer")
    quotation = relationship("Quotation")
    invoice = relationship("Invoice")
    user = relationship("User")


class InboundEmailConfig(Base):
    """Configuration for Gmail / Outlook / IMAP inbox synchronization."""

    __tablename__ = "inbound_email_configs"

    id = Column(String, primary_key=True, default=gen_id)
    company_id = Column(String, ForeignKey("companies.id"), nullable=False, unique=True, index=True)
    provider = Column(String, default="gmail", nullable=False)  # "gmail", "outlook", "imap"
    email_address = Column(String, nullable=True)
    access_token = Column(String, nullable=True)
    refresh_token = Column(String, nullable=True)

    auto_sync_enabled = Column(Boolean, default=True, nullable=False)
    auto_classify = Column(Boolean, default=True, nullable=False)
    last_synced_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)



class NoteType(str, enum.Enum):
    NOTE = "note"
    CALL = "call"
    MEETING = "meeting"
    STATUS_CHANGE = "status_change"


class CustomerNote(Base):
    """Manual activity-timeline entries (notes, logged calls/meetings, and
    auto-logged pipeline stage changes). Merged with EmailMessage rows in the
    customer detail view to form the full activity timeline."""

    __tablename__ = "customer_notes"

    id = Column(String, primary_key=True, default=gen_id)
    company_id = Column(String, ForeignKey("companies.id"), nullable=False, index=True)
    customer_id = Column(String, ForeignKey("customers.id"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)

    note_type = Column(Enum(NoteType), default=NoteType.NOTE)
    content = Column(Text, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)

    customer = relationship("Customer")
    user = relationship("User")


class ApiKey(Base):
    """Developer API Keys for public REST API access (Business tier)."""

    __tablename__ = "api_keys"

    id = Column(String, primary_key=True, default=gen_id)
    company_id = Column(String, ForeignKey("companies.id"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)

    name = Column(String, nullable=False)
    prefix = Column(String, nullable=False)  # e.g. "ak_live_a1b2"
    key_hash = Column(String, nullable=False, index=True)
    rate_limit_per_min = Column(Integer, default=120, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    last_used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    company = relationship("Company")
    user = relationship("User")

