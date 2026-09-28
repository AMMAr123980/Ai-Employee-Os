# AI Employee OS — Enterprise Edition: Sales, Ops & Back Office Automation

**AI Employee OS** is an enterprise multi-tenant ERP/CRM platform with **17 production modules** and **12 specialized AI Employee roles**.

Built from the enterprise product spec, it provides end-to-end sales, quotation generation, automated billing, payment link QR codes, email inbox sync, calendar sync, workflow automation, AI reporting, and multi-cloud LLM provider support.

---

## 🚀 Key Enterprise Features

### 1. 💼 Sales, CRM & Pipeline Management
- **Lightweight CRM & Pipeline**: Multi-stage Kanban board (`New` → `Contacted` → `Qualified` → `Proposal` → `Negotiation` → `Won`/`Lost`).
- **Activity Timelines & Customer Summaries**: Unified timeline of customer notes, email correspondence, and stage changes, plus 2-4 sentence AI relationship summaries.

### 2. 📄 Quotations, Invoices & Payment Link QR Codes
- **AI Quotation & Invoice Generators**: Natural-language line-item drafting powered by AI.
- **Branded PDF Generation**: PDF exports with ReportLab featuring scannable **QR Codes** linked to Stripe, PayPal, UPI, or custom payment links.
- **Recurring Invoices**: Background scheduler automatically generates ready-to-send recurring invoice instances.

### 3. 📧 Inbound Email Sync & Follow-up Nudge Scheduler
- **Gmail / Outlook Inbox Sync**: Parses incoming customer email threads, links replies to CRM leads, and automatically marks pending follow-ups as `dismissed`.
- **Follow-up Nudge Scheduler**: Background job that detects un-replied emails after $N$ days and drafts polite follow-up nudges for review.

### 4. 📅 Real Google Calendar & Microsoft 365 Sync
- **Interactive Calendar Console** (`/calendar`): Dedicated scheduling interface with event creation forms, duration selectors, and meeting links.
- **Multi-Provider Sync**: One-click **+ Google Cal** links, **+ Outlook** links, and raw **.ics** file downloads for every scheduled event.

### 5. 🤖 12 Specialized AI Employee Roles
Autonomous AI employees across 12 distinct departments with human-in-the-loop confirmation gates for high-risk actions:
1. **HR Officer** (`hr_officer`) — Staff onboarding, leave management.
2. **Legal Assistant** (`legal_assistant`) — Contract drafting, risk reviews.
3. **Marketing Executive** (`marketing_executive`) — Campaigns, copy generation.
4. **Procurement Officer** (`procurement_specialist`) — Purchase orders, quote comparison.
5. **Inventory Controller** (`inventory_controller`) — Stock tracking, reorder sweeps.
6. **Bookkeeper** (`bookkeeper`) — Expense tracking, payment matching.
7. **Support Agent** (`support_agent`) — Message triage, draft replies.
8. **CEO Assistant** (`ceo_assistant`) — Operational briefings, strategic updates.
9. **Sales Manager** (`sales_manager`) — Pipeline bottleneck analysis, deal coaching.
10. **Recruiter** (`recruiter`) — Candidate screening rubrics, talent sourcing.
11. **Accountant** (`accountant`) — Ledger auditing, tax liability estimation.
12. **Content Writer** (`content_writer`) — Long-form blogs, customer newsletters.

### 6. 📱 AI WhatsApp Assistant & Generic Workflow Automation Engine
- **AI WhatsApp Assistant**: Meta Cloud API webhooks (`/api/whatsapp/webhook`), AI reply suggestions, and live chat management.
- **Generic Workflow Engine**: Trigger-action automation engine (`payment_received` → receipt PDF → CRM update → task → email/WhatsApp).

### 7. 📊 AI Reporting, Analytics & Predictive Forecasting
- **Data Aggregation**: Sales analytics, revenue trends, expense ratios, top customer LTV leaderboard, and employee productivity.
- **30/60/90-Day Predictive Forecasting**: Financial projections based on receivables and run rates.
- **AI Executive Insights**: Natural-language strategic executive summaries.

### 8. 💳 Billing, Stripe Subscriptions & Quota Enforcement
- **Subscription Tiers**: Basic ($19/mo), Pro ($79/mo), Business ($299/mo) with live telemetry usage meters.
- **Per-Plan Quota Limits**: Enforces plan limits on AI requests, transcription hours, storage, invoices, quotations, and user seats.

### 9. 📈 Excel (`.xlsx`) & CSV Data Import/Export Engine (Pro Tier)
- **High-Performance Exporters**: Styled `.xlsx` workbooks with auto-column width sizing and UTF-8 CSV fallbacks for Customers, Invoices, Quotations, Expenses, and Inventory.
- **Bulk Importers**: Multipart file upload handlers for Customers and Inventory items with duplicate detection.

### 10. 🏦 Live Accounting OAuth2 & REST HTTP Push Engine
- **OAuth2 Token Exchange**: Official OAuth2 connect flows for **QuickBooks Online**, **Xero**, and **Zoho Books**.
- **Live HTTP REST Push**: Direct HTTP POST transmission of invoices and expenses with Bearer token authentication headers.

### 11. 🔐 Security, OAuth2 SSO & TOTP Multi-Factor Authentication (MFA)
- **Multi-Tenancy Isolation**: Every model and query is strictly filtered by `company_id`.
- **OAuth2 SSO**: Google and Microsoft login integrations.
- **TOTP 2FA**: Google Authenticator and Microsoft Authenticator support.
- **Public REST API**: API key authentication (`/api/v1/`) with per-minute rate limiting.

### 12. ☁️ Multi-LLM Provider & Production Infrastructure
- **Multi-LLM Provider Abstraction**: Unified support for **OpenAI** (`gpt-4o-mini`), **Anthropic Claude** (`claude-3-5-sonnet`), and **Google Gemini** (`gemini-2.5-flash`).
- **Production Stack**: Redis caching, Elasticsearch document search, Alembic database migrations (`alembic`), Docker Compose (`docker-compose.yml`), and Kubernetes manifests (`k8s-deployment.yaml`).

---

## 🛠️ Project Structure

```
ai-employee-os/
├── backend/
│   ├── app/
│   │   ├── main.py                    FastAPI entrypoint & router inclusions
│   │   ├── config.py                  Env settings (DB, branding, AI key, JWT, SMTP)
│   │   ├── database.py                SQLAlchemy engine & SessionLocal
│   │   ├── models.py                  Company, User, Customer, Quotation, Invoice, Email
│   │   ├── schemas.py                 Pydantic models
│   │   ├── auth.py                    Password hashing, JWT & role checks
│   │   ├── sso_auth.py                OAuth2 SSO & TOTP 2FA implementation
│   │   ├── llm_provider.py            Multi-LLM Provider (OpenAI, Claude, Gemini)
│   │   ├── pdf_generator.py           ReportLab PDF generator with Payment QR Codes
│   │   ├── inbound_email_sync.py      Gmail / Outlook Inbox Sync service
│   │   ├── calendar_service.py        iCalendar (.ics), Google & Outlook link generator
│   │   ├── analytics.py               Reporting, analytics & 30/60/90-day forecasting
│   │   ├── billing.py                 Stripe & subscription plan metering service
│   │   ├── excel_service.py           openpyxl Excel (.xlsx) & CSV export/import engine
│   │   ├── accounting_sync.py         QuickBooks, Xero & Zoho Books OAuth & HTTP push
│   │   ├── redis_cache.py             Redis caching layer with in-memory fallback
│   │   ├── elasticsearch_kb.py        Elasticsearch document search integration
│   │   ├── ai_employee_registry.py    12 AI employee role definitions & intent slots
│   │   ├── ai_employee_actions.py     AI employee action functions & safety gates
│   │   └── routers/                   17 REST API Routers
│   ├── alembic/                       Alembic migration scripts & env.py
│   ├── tests/                         Pytest suite (auth, quotations, emails, tenant isolation)
│   ├── Dockerfile                     Production backend Docker container
│   ├── requirements.txt               Python dependencies (Postgres, Alembic, Pytest)
│   └── .env.example
├── frontend/
│   ├── app/
│   │   ├── (app)/                     25 Protected Enterprise Console Pages
│   │   │   ├── calendar/              Dedicated Calendar & Event Sync page
│   │   │   ├── reports/               Analytics, charts & AI Executive Insights
│   │   │   ├── billing/               Subscription tier management & usage meters
│   │   │   ├── accounting/            Accounting OAuth & Live HTTP Push console
│   │   │   ├── whatsapp/              AI WhatsApp Assistant live chat console
│   │   │   ├── workflows/             Generic Workflow Automation Engine
│   │   │   ├── customers/, invoices/, quotations/, tasks/, team/, voice/ ...
│   ├── components/                    Nav sidebar, RunCard, AuthGuard, StatusBadge
│   ├── lib/                           api.ts (typed client), auth.ts
│   └── Dockerfile                     Production frontend Docker container
├── docker-compose.yml                 Production stack (FastAPI, Next.js, Postgres, Redis)
└── k8s-deployment.yaml                Kubernetes manifests
```

---

## 💻 Local Setup & Execution

### 1. Backend Setup

```bash
cd backend
python -m venv venv
source venv/bin/activate        # On Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env

# Run database migrations
alembic upgrade head

# Start FastAPI server
uvicorn app.main:app --reload --port 8000
```

FastAPI server runs at `http://localhost:8000`. Interactive OpenAPI docs at `http://localhost:8000/docs`.

### 2. Automated Test Suite (Pytest)

Run the full pytest suite (covering Auth, Quotations, Invoices, Email Sync, and Multi-Tenancy Isolation):

```bash
cd backend
python -m pytest tests/ -v
```

### 3. Frontend Setup

```bash
cd frontend
npm install
cp .env.local.example .env.local
npm run dev
```

Open `http://localhost:3000` in your browser.

---

## 🐳 Production Deployment

### Docker Compose
```bash
docker-compose up --build -d
```

### Kubernetes
```bash
kubectl apply -f k8s-deployment.yaml
```
