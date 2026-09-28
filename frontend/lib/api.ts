import { getToken, clearToken } from "./auth";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

export type PipelineStage =
  | "new"
  | "contacted"
  | "qualified"
  | "proposal"
  | "negotiation"
  | "won"
  | "lost";

export const PIPELINE_STAGES: PipelineStage[] = [
  "new",
  "contacted",
  "qualified",
  "proposal",
  "negotiation",
  "won",
  "lost",
];

export type Customer = {
  id: string;
  name: string;
  company?: string | null;
  email?: string | null;
  phone?: string | null;
  address?: string | null;
  notes?: string | null;
  lead_source?: string | null;
  created_at: string;
  pipeline_stage: PipelineStage;
  ai_relationship_summary?: string | null;
  ai_summary_generated_at?: string | null;
};

export type ActivityItem = {
  kind: "note" | "email";
  id: string;
  created_at: string;
  note_type?: string | null;
  content?: string | null;
  user_name?: string | null;
  subject?: string | null;
  to_email?: string | null;
  status?: string | null;
  error_message?: string | null;
  quotation_id?: string | null;
  invoice_id?: string | null;
};

export type DocumentStatus = "processing" | "ready" | "failed";

export type KBDocument = {
  id: string;
  title: string;
  filename: string;
  content_type?: string | null;
  size_bytes: number;
  category?: string | null;
  status: DocumentStatus;
  error?: string | null;
  chunk_count: number;
  char_count: number;
  ocr_used: boolean;
  uploaded_by_name?: string | null;
  created_at: string;
  processed_at?: string | null;
};

export type KBSource = {
  chunk_id: string;
  document_id: string;
  document_title: string;
  chunk_index: number;
  content: string;
  score: number;
};

export type KBAskResponse = {
  answer?: string | null;
  sources: KBSource[];
  mode: "answered" | "passages_only" | "no_match";
  error?: string | null;
};

export type ClauseRiskLevel = "standard" | "attention" | "high_risk" | "unreviewed";

export type ContractClause = {
  clause_type: string;
  label: string;
  title?: string | null;
  excerpt: string;
  plain_english: string;
  risk_level: ClauseRiskLevel;
  chunk_id?: string | null;
};

export type MissingClauseType = {
  clause_type: string;
  label: string;
  description: string;
};

export type ContractAnalysisResponse = {
  document_id: string;
  document_title: string;
  mode: "answered" | "keyword_fallback";
  truncated: boolean;
  clauses: ContractClause[];
  missing_clause_types: MissingClauseType[];
  error?: string | null;
  cached: boolean;
};

export type UserRole = "owner" | "admin" | "member";

export type TeamMember = {
  id: string;
  name: string;
  email: string;
  role: UserRole;
  created_at: string;
};

export type FollowUp = {
  id: string;
  customer_id: string;
  customer_name: string;
  to_email: string;
  subject: string;
  body: string;
  parent_email_id?: string | null;
  created_at: string;
};

export type NoteOut = {
  id: string;
  customer_id: string;
  note_type: string;
  content: string;
  created_at: string;
  user_name?: string | null;
};

export type LineItem = {
  id?: string;
  description: string;
  quantity: number;
  unit_price: number;
  line_total?: number;
};

export type Quotation = {
  id: string;
  number: string;
  customer_id: string;
  status: "draft" | "sent" | "approved" | "rejected" | "converted";
  subtotal: number;
  discount_percent: number;
  tax_percent: number;
  total: number;
  currency: string;
  notes?: string | null;
  ai_summary?: string | null;
  valid_until?: string | null;
  created_at: string;
  items: LineItem[];
};

export type Invoice = {
  id: string;
  number: string;
  customer_id: string;
  quotation_id?: string | null;
  status: "unpaid" | "partially_paid" | "paid" | "overdue";
  subtotal: number;
  discount_percent: number;
  tax_percent: number;
  total: number;
  amount_paid: number;
  currency: string;
  due_date?: string | null;
  is_recurring: boolean;
  recurrence_interval_days?: number | null;
  next_recurrence_at?: string | null;
  recurrence_parent_id?: string | null;
  notes?: string | null;
  payment_link?: string | null;
  created_at: string;
  items: LineItem[];
};


export type EmailMessage = {
  id: string;
  customer_id: string;
  quotation_id?: string | null;
  invoice_id?: string | null;
  to_email: string;
  subject: string;
  body: string;
  status: "draft" | "sent" | "failed";
  error_message?: string | null;
  follow_up_at?: string | null;
  created_at: string;
  sent_at?: string | null;
};

// ---- AI Employees ----

export type AIEmployee = {
  key: string;
  label: string;
  department: string;
  description: string;
  intents: string[];
  examples: string[];
  enabled: boolean;
  display_name?: string | null;
  autonomy_level: "standard" | "cautious";
  instructions?: string | null;
};

export type RunStatus =
  | "planned"
  | "no_action"
  | "awaiting_confirmation"
  | "executed"
  | "failed"
  | "cancelled";

export type EmployeeRun = {
  id: string;
  employee_key: string;
  trigger: "user" | "voice" | "workflow" | "schedule";
  brief: string;
  intent?: string | null;
  confidence?: number | null;
  action?: { type: string; config: Record<string, any> } | null;
  summary?: string | null;
  missing_info: string[];
  status: RunStatus;
  result?: Record<string, any> | null;
  error?: string | null;
  created_at: string;
  executed_at?: string | null;
};

export type RecordTable = { columns: string[]; rows: Record<string, any>[] };
export type EmployeeRecords = Record<string, RecordTable>;

export type Duty = {
  employee: string;
  intent: string;
  cadence: string;
  description: string;
};


// ---- Voice, meetings & tasks ----

export type VoiceStatus =
  | "queued"
  | "processing"
  | "transcribed"
  | "no_action"
  | "awaiting_confirmation"
  | "executed"
  | "partially_executed"
  | "failed"
  | "cancelled";

export type VoiceStepStatus = "pending" | "executed" | "failed" | "skipped" | "cancelled";

export type VoiceStep = {
  id: string;
  position: number;
  intent: string;
  config: Record<string, any>;
  summary?: string | null;
  confidence?: number | null;
  missing_info: string[];
  requires_confirmation: boolean;
  read_only: boolean;
  status: VoiceStepStatus;
  result?: Record<string, any> | null;
  error?: string | null;
  executed_at?: string | null;
};

export type VoiceCommand = {
  id: string;
  source: "app" | "text" | "whatsapp_team" | "whatsapp_customer";
  detected_language?: string | null;
  locale?: string | null;
  timezone?: string | null;
  transcript: string;
  intent?: string | null;
  confidence?: number | null;
  summary?: string | null;
  missing_info: string[];
  status: VoiceStatus;
  result?: Record<string, any> | null;
  error?: string | null;
  steps: VoiceStep[];
  audio_url?: string | null;
  audio_duration_seconds?: number | null;
  created_at: string;
  executed_at?: string | null;
};

/** Statuses the backend will never move on its own — stop polling here. */
export const TERMINAL_VOICE_STATUSES: VoiceStatus[] = [
  "no_action",
  "awaiting_confirmation",
  "executed",
  "partially_executed",
  "failed",
  "cancelled",
];

export type IntentCatalog = {
  intents: Record<string, { label: string; example: string | null; slots: string[] }>;
  read_only: string[];
  requires_confirmation: string[];
  auto_execute: string[];
};

export type Usage = {
  plan: string;
  period: string;
  metrics: Record<
    string,
    { used: number; limit: number | null; unlimited: boolean; percent: number | null }
  >;
};

export type MeetingStatus =
  | "queued"
  | "transcribing"
  | "summarizing"
  | "completed"
  | "failed";

export type MeetingSegment = { start: number; end: number; speaker: string; text: string };

export type Meeting = {
  id: string;
  title?: string | null;
  customer_id?: string | null;
  occurred_at?: string | null;
  duration_seconds?: number | null;
  detected_language?: string | null;
  status: MeetingStatus;
  transcript?: string | null;
  segments: MeetingSegment[];
  speaker_method?: "provided" | "diarized" | "heuristic" | null;
  summary?: string | null;
  decisions: string[];
  action_items: { task_id: string; title: string; owner?: string | null; due?: string | null }[];
  deadlines: { what: string; date: string }[];
  open_questions: string[];
  error?: string | null;
  created_at: string;
  completed_at?: string | null;
};

export type TaskStatus = "open" | "in_progress" | "done" | "cancelled";
export type TaskPriority = "low" | "normal" | "high";

export type Task = {
  id: string;
  title: string;
  description?: string | null;
  status: TaskStatus;
  priority: TaskPriority;
  due_date?: string | null;
  completed_at?: string | null;
  customer_id?: string | null;
  customer_name?: string | null;
  assigned_to_user_id?: string | null;
  assignee_name?: string | null;
  source: "manual" | "voice" | "followup" | "meeting" | "ai_employee";
  created_at: string;
};

export type ConditionalFollowUp = {
  id: string;
  customer_id?: string | null;
  customer_name?: string | null;
  condition_type: string;
  reminder_title: string;
  due_at: string;
  status: "waiting" | "fired" | "resolved" | "cancelled";
  resolved_reason?: string | null;
  fired_task_id?: string | null;
  created_at: string;
};

/** Thrown on a 402 so the UI can say "500 of 500 used" rather than "request failed". */
export class QuotaError extends Error {
  constructor(
    public detail: { metric: string; limit: number; used: number; plan: string; message?: string }
  ) {
    super(detail?.message || "Quota exceeded");
    this.name = "QuotaError";
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const token = getToken();
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(options?.headers || {}),
      },
      cache: "no-store",
    });
  } catch (err: any) {
    throw new Error(`Unable to connect to backend server (${API_URL}${path}). Make sure backend is running.`);
  }

  if (res.status === 401) {
    clearToken();
    if (typeof window !== "undefined") window.location.href = "/login";
    throw new Error("Not authenticated");
  }
  if (res.status === 402) {
    const body = await res.json().catch(() => ({}));
    throw new QuotaError(body.detail ?? body);
  }
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`API ${path} failed (${res.status}): ${text}`);
  }
  return res.json();
}

/** Fetches a PDF with the auth header attached and opens it in a new tab.
 * A plain <a href> can't carry an Authorization header, so PDFs must be
 * fetched as a blob client-side rather than linked directly. */
async function openPdf(path: string) {
  const token = getToken();
  const res = await fetch(`${API_URL}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) throw new Error(`Failed to load PDF (${res.status})`);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  window.open(url, "_blank");
}

/** Multipart POST — FormData sets its own Content-Type boundary, so unlike
 * request() this must not send a JSON content type. */
async function upload<T>(path: string, form: FormData): Promise<T> {
  const token = getToken();
  const res = await fetch(`${API_URL}${path}`, {
    method: "POST",
    body: form,
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (res.status === 401) {
    clearToken();
    if (typeof window !== "undefined") window.location.href = "/login";
    throw new Error("Not authenticated");
  }
  if (res.status === 402) {
    const body = await res.json().catch(() => ({}));
    throw new QuotaError(body.detail ?? body);
  }
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`Upload failed (${res.status}): ${text}`);
  }
  return res.json();
}

/** Fetches audio with the auth header and returns a blob URL.
 * An <audio src> tag can't carry an Authorization header, which is exactly why
 * the backend streams recordings through an authenticated route instead of
 * handing out signed links. */
async function fetchAudioUrl(path: string): Promise<string> {
  const token = getToken();
  const res = await fetch(`${API_URL}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) throw new Error(`Couldn't load that recording (${res.status})`);
  return URL.createObjectURL(await res.blob());
}

export const api = {
  // Customers
  listCustomers: () => request<Customer[]>("/api/customers"),
  createCustomer: (data: Partial<Customer>) =>
    request<Customer>("/api/customers", { method: "POST", body: JSON.stringify(data) }),
  deleteCustomer: (id: string) =>
    request<{ ok: boolean }>(`/api/customers/${id}`, { method: "DELETE" }),
  getCustomer: (id: string) => request<Customer>(`/api/customers/${id}`),
  updatePipelineStage: (id: string, stage: PipelineStage) =>
    request<Customer>(`/api/customers/${id}/stage`, {
      method: "PATCH",
      body: JSON.stringify({ pipeline_stage: stage }),
    }),
  addNote: (id: string, content: string, note_type: string = "note") =>
    request<NoteOut>(`/api/customers/${id}/notes`, {
      method: "POST",
      body: JSON.stringify({ content, note_type }),
    }),
  getActivity: (id: string) => request<ActivityItem[]>(`/api/customers/${id}/activity`),
  generateAiSummary: (id: string) =>
    request<{ summary: string; generated_at: string }>(`/api/customers/${id}/ai-summary`, {
      method: "POST",
    }),

  // Quotations
  listQuotations: () => request<Quotation[]>("/api/quotations"),
  getQuotation: (id: string) => request<Quotation>(`/api/quotations/${id}`),
  createQuotation: (data: {
    customer_id: string;
    items: LineItem[];
    discount_percent: number;
    tax_percent?: number;
    notes?: string;
    generate_ai_summary?: boolean;
  }) => request<Quotation>("/api/quotations", { method: "POST", body: JSON.stringify(data) }),
  aiDraftItems: (prompt: string) =>
    request<{ items: LineItem[]; suggested_notes: string | null }>("/api/quotations/ai-draft", {
      method: "POST",
      body: JSON.stringify({ prompt }),
    }),
  updateQuotationStatus: (id: string, status: Quotation["status"]) =>
    request<Quotation>(`/api/quotations/${id}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    }),
  convertToInvoice: (
    id: string,
    options?: { is_recurring?: boolean; recurrence_interval_days?: number }
  ) =>
    request<Invoice>(`/api/quotations/${id}/convert-to-invoice`, {
      method: "POST",
      body: JSON.stringify(options || {}),
    }),
  openQuotationPdf: (id: string) => openPdf(`/api/quotations/${id}/pdf`),

  // Invoices
  listInvoices: () => request<Invoice[]>("/api/invoices"),
  getInvoice: (id: string) => request<Invoice>(`/api/invoices/${id}`),
  recordPayment: (id: string, amount: number) =>
    request<Invoice>(`/api/invoices/${id}/payments`, {
      method: "POST",
      body: JSON.stringify({ amount }),
    }),
  openInvoicePdf: (id: string) => openPdf(`/api/invoices/${id}/pdf`),
  checkRecurringNow: () =>
    request<{ invoices_created: number }>("/api/invoices/recurring/check-now", { method: "POST" }),

  // AI Email Assistant
  draftEmail: (data: { customer_id: string; quotation_id?: string; invoice_id?: string; instructions?: string }) =>
    request<{ to_email: string | null; subject: string; body: string }>("/api/emails/draft", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  sendEmail: (data: {
    customer_id: string;
    to_email: string;
    subject: string;
    body: string;
    quotation_id?: string;
    invoice_id?: string;
    attach_pdf?: boolean;
    follow_up_in_days?: number;
  }) => request<EmailMessage>("/api/emails/send", { method: "POST", body: JSON.stringify(data) }),
  listEmails: (customerId: string) =>
    request<EmailMessage[]>(`/api/emails?customer_id=${customerId}`),
  summarizeText: (text: string) =>
    request<{ summary: string; action_items: string[] }>("/api/emails/summarize", {
      method: "POST",
      body: JSON.stringify({ text }),
    }),
  classifyText: (text: string) =>
    request<{ category: string; priority: string; reasoning: string }>("/api/emails/classify", {
      method: "POST",
      body: JSON.stringify({ text }),
    }),

  // Follow-up Scheduler
  listFollowUps: () => request<FollowUp[]>("/api/follow-ups"),
  checkFollowUpsNow: () =>
    request<{ drafts_created: number }>("/api/follow-ups/check-now", { method: "POST" }),
  sendFollowUp: (id: string, data: { subject?: string; body?: string; attach_pdf?: boolean }) =>
    request<EmailMessage>(`/api/follow-ups/${id}/send`, { method: "POST", body: JSON.stringify(data) }),
  dismissFollowUp: (id: string) =>
    request<{ ok: boolean }>(`/api/follow-ups/${id}/dismiss`, { method: "POST" }),

  // AI Employees
  listAiEmployees: () => request<AIEmployee[]>("/api/ai-employees"),
  listDuties: () => request<{ duties: Record<string, Duty> }>("/api/ai-employees/duties"),
  updateEmployeeConfig: (
    key: string,
    data: { enabled?: boolean; display_name?: string; autonomy_level?: string; instructions?: string }
  ) =>
    request<AIEmployee>(`/api/ai-employees/${key}/config`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  submitBrief: (key: string, brief: string, dry_run = false) =>
    request<EmployeeRun>(`/api/ai-employees/${key}/brief`, {
      method: "POST",
      body: JSON.stringify({ brief, dry_run }),
    }),
  confirmRun: (runId: string, overrides: Record<string, any> = {}) =>
    request<EmployeeRun>(`/api/ai-employees/runs/${runId}/confirm`, {
      method: "POST",
      body: JSON.stringify({ overrides }),
    }),
  cancelRun: (runId: string) =>
    request<EmployeeRun>(`/api/ai-employees/runs/${runId}/cancel`, { method: "POST" }),
  listRuns: (key?: string) =>
    request<EmployeeRun[]>(`/api/ai-employees/runs${key ? `?employee_key=${key}` : ""}`),
  listEmployeeRecords: (key: string) =>
    request<EmployeeRecords>(`/api/ai-employees/${key}/records`),
  runDuty: (key: string, duty: string) =>
    request<EmployeeRun>(`/api/ai-employees/${key}/run-duty/${duty}`, { method: "POST" }),

  // Team management
  listTeam: () => request<TeamMember[]>("/api/team"),
  inviteTeamMember: (data: { name: string; email: string; password: string; role: UserRole }) =>
    request<TeamMember>("/api/team/invite", { method: "POST", body: JSON.stringify(data) }),
  updateTeamRole: (userId: string, role: UserRole) =>
    request<TeamMember>(`/api/team/${userId}/role`, { method: "PATCH", body: JSON.stringify({ role }) }),
  removeTeamMember: (userId: string) =>
    request<{ ok: boolean }>(`/api/team/${userId}`, { method: "DELETE" }),

  // Voice commands
  submitVoiceRecording: (blob: Blob, filename = "voice-note.webm", transcript?: string) => {
    const form = new FormData();
    form.append("audio", blob, filename);
    if (transcript) form.append("transcript", transcript);
    // The browser is the only thing that knows where the words were spoken.
    form.append("timezone", Intl.DateTimeFormat().resolvedOptions().timeZone);
    return upload<VoiceCommand>("/api/voice-commands", form);
  },
  submitTextCommand: (text: string, dry_run = false) =>
    request<VoiceCommand>("/api/voice-commands/text", {
      method: "POST",
      body: JSON.stringify({
        text,
        dry_run,
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
      }),
    }),
  getVoiceCommand: (id: string) => request<VoiceCommand>(`/api/voice-commands/${id}`),
  listVoiceCommands: (limit = 30) =>
    request<VoiceCommand[]>(`/api/voice-commands?limit=${limit}`),
  confirmVoiceCommand: (
    id: string,
    options: { only_steps?: string[] | null; step_overrides?: Record<string, Record<string, any>> } = {}
  ) =>
    request<VoiceCommand>(`/api/voice-commands/${id}/confirm`, {
      method: "POST",
      body: JSON.stringify({
        only_steps: options.only_steps ?? null,
        step_overrides: options.step_overrides ?? {},
        overrides: {},
      }),
    }),
  cancelVoiceCommand: (id: string) =>
    request<VoiceCommand>(`/api/voice-commands/${id}/cancel`, { method: "POST" }),
  getVoiceCatalog: () => request<IntentCatalog>("/api/voice-commands/intents/catalog"),
  getUsage: () => request<Usage>("/api/voice-commands/usage"),
  getCommandAudioUrl: (id: string) => fetchAudioUrl(`/api/voice-commands/${id}/audio`),

  // Meetings
  uploadMeeting: (file: File, opts: { title?: string; customer_id?: string } = {}) => {
    const form = new FormData();
    form.append("audio", file, file.name);
    if (opts.title) form.append("title", opts.title);
    if (opts.customer_id) form.append("customer_id", opts.customer_id);
    form.append("timezone", Intl.DateTimeFormat().resolvedOptions().timeZone);
    return upload<Meeting>("/api/meetings", form);
  },
  listMeetings: () => request<Meeting[]>("/api/meetings"),
  getMeeting: (id: string) => request<Meeting>(`/api/meetings/${id}`),
  renameSpeakers: (id: string, speaker_map: Record<string, string>) =>
    request<Meeting>(`/api/meetings/${id}/speakers`, {
      method: "POST",
      body: JSON.stringify({ speaker_map }),
    }),
  deleteMeeting: (id: string) =>
    request<{ ok: boolean }>(`/api/meetings/${id}`, { method: "DELETE" }),

  // Tasks
  listTasks: (params: { status?: TaskStatus; mine?: boolean; customer_id?: string } = {}) => {
    const query = new URLSearchParams();
    if (params.status) query.set("status", params.status);
    if (params.mine) query.set("mine", "true");
    if (params.customer_id) query.set("customer_id", params.customer_id);
    const qs = query.toString();
    return request<Task[]>(`/api/tasks${qs ? `?${qs}` : ""}`);
  },
  createTask: (data: {
    title: string;
    description?: string;
    priority?: TaskPriority;
    due_date?: string | null;
    customer_id?: string | null;
  }) => request<Task>("/api/tasks", { method: "POST", body: JSON.stringify(data) }),
  updateTask: (
    id: string,
    data: { status?: TaskStatus; priority?: TaskPriority; title?: string; due_date?: string | null }
  ) => request<Task>(`/api/tasks/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  deleteTask: (id: string) => request<{ ok: boolean }>(`/api/tasks/${id}`, { method: "DELETE" }),

  // Conditional follow-ups ("remind me if they don't reply")
  listConditionalFollowUps: () =>
    request<ConditionalFollowUp[]>("/api/tasks/followups/pending"),
  checkConditionalFollowUpsNow: () =>
    request<{ checked: number; fired: number; resolved: number; errors: number }>(
      "/api/tasks/followups/check-now",
      { method: "POST" }
    ),
  cancelConditionalFollowUp: (id: string) =>
    request<ConditionalFollowUp>(`/api/tasks/followups/${id}/cancel`, { method: "POST" }),

  // Knowledge base
  listDocuments: (category?: string) =>
    request<KBDocument[]>(`/api/documents${category ? `?category=${encodeURIComponent(category)}` : ""}`),
  uploadDocument: (file: File, opts: { title?: string; category?: string } = {}) => {
    const form = new FormData();
    form.append("file", file, file.name);
    if (opts.title) form.append("title", opts.title);
    if (opts.category) form.append("category", opts.category);
    return upload<KBDocument>("/api/documents", form);
  },
  getDocument: (id: string) => request<KBDocument>(`/api/documents/${id}`),
  updateDocument: (id: string, data: { title?: string; category?: string }) =>
    request<KBDocument>(`/api/documents/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  deleteDocument: (id: string) =>
    request<{ ok: boolean }>(`/api/documents/${id}`, { method: "DELETE" }),
  askDocuments: (question: string, document_id?: string) =>
    request<KBAskResponse>("/api/documents/ask", {
      method: "POST",
      body: JSON.stringify({ question, document_id }),
    }),
  analyzeContract: (documentId: string, opts: { refresh?: boolean } = {}) =>
    request<ContractAnalysisResponse>(
      `/api/documents/${documentId}/contract-analysis${opts.refresh ? "?refresh=true" : ""}`,
      { method: "POST" }
    ),
  getContractAnalysis: (documentId: string) =>
    request<ContractAnalysisResponse>(`/api/documents/${documentId}/contract-analysis`),

  /** Polls a command until it reaches a terminal status. Backs off from 600ms
   * to 3s: a short command is usually done on the second poll, and a long one
   * shouldn't generate sixty requests while it works. */
  pollVoiceCommand: async (
    id: string,
    onUpdate: (command: VoiceCommand) => void,
    timeoutMs = 150_000
  ): Promise<VoiceCommand> => {
    const startedAt = Date.now();
    let delay = 600;
    for (;;) {
      const command = await request<VoiceCommand>(`/api/voice-commands/${id}`);
      onUpdate(command);
      if (TERMINAL_VOICE_STATUSES.includes(command.status)) return command;
      if (Date.now() - startedAt > timeoutMs) {
        throw new Error("Still working on it — check the history in a moment.");
      }
      await new Promise((resolve) => setTimeout(resolve, delay));
      delay = Math.min(delay * 1.4, 3000);
    }
  },

  // WhatsApp Assistant
  getWhatsAppConfig: () => request<WhatsAppConfig>("/api/whatsapp/config"),
  updateWhatsAppConfig: (data: Partial<WhatsAppConfig>) =>
    request<{ status: string }>("/api/whatsapp/config", { method: "POST", body: JSON.stringify(data) }),
  listWhatsAppConversations: () => request<WhatsAppConversation[]>("/api/whatsapp/conversations"),
  getWhatsAppMessages: (phone: string) =>
    request<WhatsAppMessage[]>(`/api/whatsapp/conversations/${encodeURIComponent(phone)}/messages`),
  sendWhatsAppMessage: (data: { recipient_phone: string; message_text: string }) =>
    request<{ status: string; message_id: string }>("/api/whatsapp/send", { method: "POST", body: JSON.stringify(data) }),
  suggestWhatsAppAiReply: (data: { recipient_phone: string; incoming_text: string }) =>
    request<{ suggested_reply: string }>("/api/whatsapp/ai-suggest", { method: "POST", body: JSON.stringify(data) }),

  // Generic Workflow Automation
  listWorkflows: () => request<Workflow[]>("/api/workflows"),
  createWorkflow: (data: any) =>
    request<{ status: string; workflow_id: string }>("/api/workflows", { method: "POST", body: JSON.stringify(data) }),
  updateWorkflow: (id: string, data: any) =>
    request<{ status: string }>(`/api/workflows/${id}`, { method: "PUT", body: JSON.stringify(data) }),
  deleteWorkflow: (id: string) =>
    request<{ status: string }>(`/api/workflows/${id}`, { method: "DELETE" }),
  listWorkflowTemplates: () => request<WorkflowTemplate[]>("/api/workflows/templates"),
  enableWorkflowTemplate: (templateId: string) =>
    request<{ status: string; workflow_id: string }>(`/api/workflows/templates/${templateId}/enable`, { method: "POST" }),
  listWorkflowRuns: () => request<WorkflowRun[]>("/api/workflows/runs"),
  testTriggerWorkflow: (data: { event_type: string; invoice_id?: string; customer_id?: string; amount?: number }) =>
    request<{ status: string; results: any[] }>("/api/workflows/test-trigger", { method: "POST", body: JSON.stringify(data) }),

  // Inbound Email Sync
  getInboxSyncConfig: () => request<InboundEmailSyncConfig>("/api/emails/sync-config"),
  updateInboxSyncConfig: (data: Partial<InboundEmailSyncConfig>) =>
    request<{ status: string }>("/api/emails/sync-config", { method: "POST", body: JSON.stringify(data) }),
  syncInboxNow: () => request<{ synced_count: number; followups_resolved: number; last_synced_at: string }>("/api/emails/sync-inbox", { method: "POST" }),
  simulateInboundEmail: (data: { from_email: string; from_name?: string; subject: string; body: string }) =>
    request<{ status: string; email_id: string; followups_auto_resolved: number }>("/api/emails/simulate-inbound", { method: "POST", body: JSON.stringify(data) }),

  // Calendar Events
  listCalendarEvents: () => request<CalendarEvent[]>("/api/calendar/events"),
  createCalendarEvent: (data: {
    title: string;
    description?: string;
    starts_at: string;
    duration_minutes?: number;
    customer_id?: string;
    location?: string;
    meeting_link?: string;
  }) => request<{ status: string; event_id: string; google_url: string; outlook_url: string }>("/api/calendar/events", { method: "POST", body: JSON.stringify(data) }),
  exportCalendarEventIcs: (eventId: string) => openPdf(`/api/calendar/events/${eventId}/export.ics`),

  // Accounting Software Sync & Live HTTP Push Engine
  getAccountingConfig: () => request<AccountingConfig>("/api/accounting/config"),
  saveAccountingConfig: (data: Partial<AccountingConfig>) =>
    request<{ status: string }>("/api/accounting/config", { method: "POST", body: JSON.stringify(data) }),
  getAccountingAuthorizeUrl: (provider: string) =>
    request<{ provider: string; authorize_url: string }>(`/api/accounting/oauth/authorize?provider=${provider}`),
  handleAccountingOAuthCallback: (provider: string, code: string, realmId?: string) =>
    request<{ status: string; provider: string; is_connected: boolean }>(
      `/api/accounting/oauth/callback?provider=${provider}&code=${code}${realmId ? `&realmId=${realmId}` : ""}`
    ),
  pushInvoicesToAccounting: (invoiceIds?: string[]) =>
    request<{ status: string; provider: string; pushed_count: number; details: any[] }>(
      "/api/accounting/export-invoices",
      { method: "POST", body: JSON.stringify({ invoice_ids: invoiceIds }) }
    ),
  pushExpensesToAccounting: (expenseIds?: string[]) =>
    request<{ status: string; provider: string; pushed_count: number; details: any[] }>(
      "/api/accounting/export-expenses",
      { method: "POST", body: JSON.stringify({ expense_ids: expenseIds }) }
    ),
  exportInvoicesToAccounting: (invoiceIds?: string[]) =>
    request<{ provider: string; exported_count: number }>("/api/accounting/export-invoices", { method: "POST", body: JSON.stringify({ invoice_ids: invoiceIds }) }),
  syncAccountingNow: () =>
    request<{ status: string; provider: string; invoices_pushed: number; expenses_pushed: number; details: any[]; last_synced_at: string }>("/api/accounting/sync-now", { method: "POST" }),

  // MFA & SSO Auth
  setupMFA: () => request<MfaSetupResponse>("/api/auth/mfa/setup", { method: "POST" }),
  verifyMFA: (code: string) =>
    request<{ status: string }>("/api/auth/mfa/verify", { method: "POST", body: JSON.stringify({ code }) }),

  // Public Developer API Keys
  listApiKeys: () => request<ApiKeyItem[]>("/api/auth/api-keys"),
  createApiKey: (name: string) =>
    request<{ id: string; name: string; api_key: string; prefix: string }>("/api/auth/api-keys", { method: "POST", body: JSON.stringify({ name }) }),
  revokeApiKey: (id: string) =>
    request<{ status: string }>(`/api/auth/api-keys/${id}`, { method: "DELETE" }),

  // AI Reporting & Analytics
  getReportsOverview: (days = 30) => request<ReportsOverview>(`/api/reports/overview?days=${days}`),
  getSalesReports: (days = 30) => request<SalesAnalytics>(`/api/reports/sales?days=${days}`),
  getRevenueReports: (days = 30) => request<RevenueAnalytics>(`/api/reports/revenue?days=${days}`),
  getExpenseReports: (days = 30) => request<ExpenseAnalytics>(`/api/reports/expenses?days=${days}`),
  getCustomerReports: (days = 30) => request<CustomerAnalytics>(`/api/reports/customers?days=${days}`),
  getProductivityReports: (days = 30) => request<ProductivityAnalytics>(`/api/reports/productivity?days=${days}`),
  getForecastingReports: (days = 30) => request<PredictiveForecasting>(`/api/reports/forecasting?days=${days}`),
  generateAiInsights: (days = 30) => request<AiInsightsResponse>(`/api/reports/ai-insights?days=${days}`, { method: "POST" }),

  // Subscriptions & Billing
  getSubscription: () => request<SubscriptionInfo>("/api/billing/subscription"),
  createCheckoutSession: (plan: string, success_url?: string) =>
    request<{ checkout_url: string; mode: string }>("/api/billing/create-checkout-session", {
      method: "POST",
      body: JSON.stringify({ plan, success_url }),
    }),
  changePlan: (plan: string) =>
    request<{ company_id: string; plan: string; status: string; price_monthly: number }>("/api/billing/change-plan", {
      method: "POST",
      body: JSON.stringify({ plan }),
    }),
};

export type SubscriptionInfo = {
  company_id: string;
  company_name: string;
  plan: "basic" | "pro" | "business";
  subscription_status: string;
  current_period_end?: string | null;
  price_monthly: number;
  stripe_customer_id?: string | null;
  usage: Usage;
};

export type ReportsOverview = {
  period_days: number;
  total_invoiced: number;
  total_collected: number;
  total_outstanding: number;
  total_expenses: number;
  net_profit: number;
  quotations_count: number;
  quotations_value: number;
  quotation_conversion_rate: number;
  total_customers: number;
  new_customers: number;
  currency: string;
};

export type SalesAnalytics = {
  period_days: number;
  pipeline_breakdown: Record<string, number>;
  quotation_status_breakdown: Record<string, number>;
  lead_sources: Record<string, number>;
  average_deal_size: number;
};

export type RevenueAnalytics = {
  period_days: number;
  revenue_by_status: Record<string, number>;
  monthly_revenue_trend: Record<string, number>;
  arpu: number;
  recurring_invoices_count: number;
};

export type ExpenseAnalytics = {
  period_days: number;
  total_expenses: number;
  expenses_by_category: Record<string, number>;
  expense_to_revenue_ratio_percent: number;
};

export type CustomerAnalytics = {
  total_customers: number;
  top_customers_by_ltv: { id: string; name: string; company?: string | null; total_spent: number; invoice_count: number }[];
};

export type ProductivityAnalytics = {
  period_days: number;
  total_ai_employee_runs: number;
  runs_by_employee: Record<string, number>;
  total_tasks: number;
  completed_tasks: number;
  task_completion_rate_percent: number;
};

export type PredictiveForecasting = {
  baseline_monthly_revenue: number;
  current_receivables: number;
  forecast_30_days: number;
  forecast_60_days: number;
  forecast_90_days: number;
  confidence_level: string;
};

export type AiInsightsResponse = {
  insights_text: string;
  generated_at: string;
  period_days: number;
};

export type AccountingConfig = {
  provider: "quickbooks" | "xero" | "zoho" | "zoho_books" | "none" | string;
  is_connected: boolean;
  auto_sync_invoices: boolean;
  auto_sync_expenses: boolean;
  last_synced_at?: string | null;
};

export type ApiKeyItem = {
  id: string;
  name: string;
  prefix: string;
  created_at: string;
  last_used_at?: string | null;
};

export type MfaSetupResponse = {
  secret: string;
  qr_code_url: string;
  otpauth_uri: string;
};

// Inbound Email Sync Config
export type InboundEmailSyncConfig = {
  provider: string;
  email_address?: string | null;
  auto_sync_enabled: boolean;
  auto_classify: boolean;
  last_synced_at?: string | null;
};

// Calendar Event Type
export type CalendarEvent = {
  id: string;
  title: string;
  description?: string | null;
  starts_at: string;
  ends_at: string;
  location?: string | null;
  meeting_link?: string | null;
  provider: string;
  customer_id?: string | null;
  customer_name?: string | null;
  google_url: string;
  outlook_url: string;
  created_at: string;
};

// WhatsApp Types
export type WhatsAppConfig = {
  phone_number_id?: string | null;
  waba_id?: string | null;
  access_token?: string | null;
  verify_token?: string | null;
  auto_reply_enabled: boolean;
  ai_instructions?: string | null;
  webhook_url: string;
};

export type WhatsAppConversation = {
  id: string;
  customer_id?: string | null;
  customer_phone: string;
  customer_name: string;
  unread_count: number;
  last_message_at?: string | null;
  last_message_preview?: string | null;
};

export type WhatsAppMessage = {
  id: string;
  direction: "inbound" | "outbound";
  status: "sent" | "delivered" | "read" | "failed" | "received";
  message_type: string;
  body?: string | null;
  media_url?: string | null;
  ai_generated: boolean;
  created_at: string;
};

// Workflow Types
export type WorkflowStep = {
  id?: string;
  step_order: number;
  name: string;
  action_type: string;
  config_json?: Record<string, any>;
};

export type Workflow = {
  id: string;
  name: string;
  description?: string | null;
  trigger_type: string;
  is_active: boolean;
  created_at: string;
  steps: WorkflowStep[];
  runs_count?: number;
};

export type WorkflowRunStep = {
  id: string;
  step_order: number;
  action_type: string;
  status: "pending" | "success" | "failed" | "skipped";
  output?: Record<string, any> | null;
  error?: string | null;
  executed_at?: string | null;
};

export type WorkflowRun = {
  id: string;
  workflow_name: string;
  trigger_event: string;
  status: "running" | "success" | "failed" | "partial_failure";
  error_message?: string | null;
  started_at: string;
  completed_at?: string | null;
  steps: WorkflowRunStep[];
};

export type WorkflowTemplate = {
  id: string;
  name: string;
  description: string;
  trigger_type: string;
  steps: WorkflowStep[];
};

// ---- Data Export / Bulk Import API Helpers ----

export async function exportDataFile(entity: string, format: "xlsx" | "csv" = "xlsx"): Promise<void> {
  const token = getToken();
  const res = await fetch(`${API_URL}/api/data/export/${entity}?format=${format}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`Export failed (${res.status}): ${text}`);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${entity}_export.${format}`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export async function importDataFile(
  entity: string,
  file: File
): Promise<{ entity: string; imported_count: number; skipped_count: number }> {
  const token = getToken();
  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch(`${API_URL}/api/data/import/${entity}`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: formData,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`Import failed (${res.status}): ${text}`);
  }
  return res.json();
}

export async function downloadSampleTemplate(entity: string): Promise<void> {
  const token = getToken();
  const res = await fetch(`${API_URL}/api/data/template/${entity}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) throw new Error(`Template download failed (${res.status})`);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `sample_${entity}_template.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}


