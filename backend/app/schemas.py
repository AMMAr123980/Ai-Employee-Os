from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr

from app.models import QuotationStatus, InvoiceStatus, UserRole, PipelineStage, NoteType


# ---------- Auth ----------

class SignupRequest(BaseModel):
    company_name: str
    name: str
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    totp_code: Optional[str] = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    company_id: str
    name: str
    email: str
    role: UserRole
    mfa_enabled: bool = False


class CompanyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str


class TokenResponse(BaseModel):
    access_token: Optional[str] = None
    token_type: str = "bearer"
    user: Optional[UserOut] = None
    company: Optional[CompanyOut] = None
    mfa_required: bool = False
    mfa_type: Optional[str] = None
    otp_dev_hint: Optional[str] = None
    message: Optional[str] = None


class ResendOTPRequest(BaseModel):
    email: EmailStr
    password: str


class Setup2FAResponse(BaseModel):
    secret: str
    qr_uri: str


class Verify2FARequest(BaseModel):
    secret: str
    code: str


class Disable2FARequest(BaseModel):
    code: str


class MeResponse(BaseModel):
    user: UserOut
    company: CompanyOut


# ---------- Team Management ----------

class TeamInviteRequest(BaseModel):
    name: str
    email: EmailStr
    password: str
    role: UserRole = UserRole.MEMBER


class TeamMemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    email: str
    role: UserRole
    created_at: datetime


class RoleUpdateRequest(BaseModel):
    role: UserRole


# ---------- Customers ----------

class CustomerCreate(BaseModel):
    name: str
    company: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None
    lead_source: Optional[str] = None


class CustomerOut(CustomerCreate):
    model_config = ConfigDict(from_attributes=True)
    id: str
    created_at: datetime
    pipeline_stage: PipelineStage
    ai_relationship_summary: Optional[str] = None
    ai_summary_generated_at: Optional[datetime] = None


class PipelineStageUpdate(BaseModel):
    pipeline_stage: PipelineStage


class CustomerNoteCreate(BaseModel):
    content: str
    note_type: NoteType = NoteType.NOTE


class CustomerNoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    customer_id: str
    note_type: NoteType
    content: str
    created_at: datetime
    user_name: Optional[str] = None


class AISummaryResponse(BaseModel):
    summary: str
    generated_at: datetime


class ActivityItem(BaseModel):
    """Unified shape for the customer activity timeline — either a CustomerNote
    or an EmailMessage, discriminated by `kind`."""
    kind: str  # "note" | "email"
    id: str
    created_at: datetime
    note_type: Optional[str] = None
    content: Optional[str] = None
    user_name: Optional[str] = None
    subject: Optional[str] = None
    to_email: Optional[str] = None
    status: Optional[str] = None
    error_message: Optional[str] = None
    quotation_id: Optional[str] = None
    invoice_id: Optional[str] = None


# ---------- Quotation items ----------

class ItemIn(BaseModel):
    description: str
    quantity: float = 1.0
    unit_price: float = 0.0


class ItemOut(ItemIn):
    model_config = ConfigDict(from_attributes=True)
    id: str
    line_total: float


# ---------- Quotations ----------

class QuotationCreate(BaseModel):
    customer_id: str
    items: List[ItemIn]
    discount_percent: float = 0.0
    tax_percent: Optional[float] = None  # falls back to DEFAULT_TAX_RATE
    currency: Optional[str] = None
    notes: Optional[str] = None
    valid_until: Optional[datetime] = None
    generate_ai_summary: bool = True


class QuotationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    number: str
    customer_id: str
    status: QuotationStatus
    subtotal: float
    discount_percent: float
    tax_percent: float
    total: float
    currency: str
    notes: Optional[str] = None
    ai_summary: Optional[str] = None
    valid_until: Optional[datetime] = None
    created_at: datetime
    items: List[ItemOut] = []


class QuotationStatusUpdate(BaseModel):
    status: QuotationStatus


# ---------- AI draft assist ----------

class AIDraftItemsRequest(BaseModel):
    """Natural-language request, e.g. 'quotation for 25 Dell laptops and 5 wireless mice'."""
    prompt: str
    customer_id: Optional[str] = None


class AIDraftItemsResponse(BaseModel):
    items: List[ItemIn]
    suggested_notes: Optional[str] = None


# ---------- Invoices ----------

class InvoiceFromQuotation(BaseModel):
    due_date: Optional[datetime] = None
    is_recurring: bool = False
    recurrence_interval_days: Optional[int] = None


class InvoiceCreate(BaseModel):
    customer_id: str
    items: List[ItemIn]
    discount_percent: float = 0.0
    tax_percent: Optional[float] = None
    currency: Optional[str] = None
    notes: Optional[str] = None
    payment_link: Optional[str] = None
    due_date: Optional[datetime] = None
    is_recurring: bool = False
    recurrence_interval_days: Optional[int] = None


class InvoiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    number: str
    customer_id: str
    quotation_id: Optional[str] = None
    status: InvoiceStatus
    subtotal: float
    discount_percent: float
    tax_percent: float
    total: float
    amount_paid: float
    currency: str
    due_date: Optional[datetime] = None
    is_recurring: bool
    recurrence_interval_days: Optional[int] = None
    next_recurrence_at: Optional[datetime] = None
    recurrence_parent_id: Optional[str] = None
    notes: Optional[str] = None
    payment_link: Optional[str] = None
    created_at: datetime
    items: List[ItemOut] = []



class PaymentIn(BaseModel):
    amount: float


# ---------- AI Email Assistant ----------

class EmailDraftRequest(BaseModel):
    customer_id: str
    quotation_id: Optional[str] = None
    invoice_id: Optional[str] = None
    instructions: Optional[str] = None  # e.g. "friendly follow-up, mention the discount ends Friday"


class EmailDraftResponse(BaseModel):
    to_email: Optional[str] = None
    subject: str
    body: str


class EmailSendRequest(BaseModel):
    customer_id: str
    to_email: str
    subject: str
    body: str
    quotation_id: Optional[str] = None
    invoice_id: Optional[str] = None
    attach_pdf: bool = True
    follow_up_in_days: Optional[int] = None


class EmailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    customer_id: str
    quotation_id: Optional[str] = None
    invoice_id: Optional[str] = None
    to_email: str
    subject: str
    body: str
    status: str
    error_message: Optional[str] = None
    follow_up_at: Optional[datetime] = None
    created_at: datetime
    sent_at: Optional[datetime] = None


# ---------- Follow-up Scheduler ----------

class FollowUpOut(BaseModel):
    id: str
    customer_id: str
    customer_name: str
    to_email: str
    subject: str
    body: str
    parent_email_id: Optional[str] = None
    created_at: datetime


class FollowUpSendRequest(BaseModel):
    subject: Optional[str] = None  # override the AI draft if edited
    body: Optional[str] = None
    attach_pdf: bool = False


class FollowUpCheckResult(BaseModel):
    drafts_created: int


class RecurringCheckResult(BaseModel):
    invoices_created: int


class EmailSummarizeRequest(BaseModel):
    text: str


class EmailSummarizeResponse(BaseModel):
    summary: str
    action_items: List[str] = []


class EmailClassifyRequest(BaseModel):
    text: str


class EmailClassifyResponse(BaseModel):
    category: str  # sales | support | billing | complaint | spam | other
    priority: str  # low | normal | high | urgent
    reasoning: str
