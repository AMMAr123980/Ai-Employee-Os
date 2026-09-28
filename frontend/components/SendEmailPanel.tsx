"use client";

import { useState } from "react";
import { api } from "@/lib/api";

export default function SendEmailPanel({
  customerId,
  customerEmail,
  quotationId,
  invoiceId,
  onSent,
}: {
  customerId: string;
  customerEmail?: string | null;
  quotationId?: string;
  invoiceId?: string;
  onSent?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [instructions, setInstructions] = useState("");
  const [drafting, setDrafting] = useState(false);
  const [sending, setSending] = useState(false);
  const [toEmail, setToEmail] = useState(customerEmail || "");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [attachPdf, setAttachPdf] = useState(true);
  const [followUpDays, setFollowUpDays] = useState<string>("3");
  const [error, setError] = useState<string | null>(null);
  const [sentResult, setSentResult] = useState<{ status: string; error_message?: string | null } | null>(null);

  async function handleDraft() {
    setDrafting(true);
    setError(null);
    try {
      const draft = await api.draftEmail({
        customer_id: customerId,
        quotation_id: quotationId,
        invoice_id: invoiceId,
        instructions: instructions || undefined,
      });
      setSubject(draft.subject);
      setBody(draft.body);
      if (draft.to_email && !toEmail) setToEmail(draft.to_email);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setDrafting(false);
    }
  }

  async function handleSend() {
    if (!toEmail.trim() || !subject.trim() || !body.trim()) {
      setError("Recipient, subject, and body are all required.");
      return;
    }
    setSending(true);
    setError(null);
    setSentResult(null);
    try {
      const result = await api.sendEmail({
        customer_id: customerId,
        to_email: toEmail,
        subject,
        body,
        quotation_id: quotationId,
        invoice_id: invoiceId,
        attach_pdf: attachPdf,
        follow_up_in_days: followUpDays ? parseInt(followUpDays, 10) : undefined,
      });
      setSentResult({ status: result.status, error_message: result.error_message });
      if (result.status === "sent") {
        onSent?.();
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSending(false);
    }
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium hover:bg-slate-100"
      >
        ✉ Email Customer
      </button>
    );
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 space-y-4 w-full">
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium">Send Email</p>
        <button onClick={() => setOpen(false)} className="text-slate-400 hover:text-slate-600 text-sm">
          Close
        </button>
      </div>

      <div className="flex gap-2">
        <input
          className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm"
          placeholder="Optional instructions, e.g. 'mention the discount ends Friday'"
          value={instructions}
          onChange={(e) => setInstructions(e.target.value)}
        />
        <button
          onClick={handleDraft}
          disabled={drafting}
          className="rounded-lg bg-brand-600 text-white px-4 py-2 text-sm font-medium hover:bg-brand-700 disabled:opacity-50 whitespace-nowrap"
        >
          {drafting ? "Drafting…" : "AI Draft"}
        </button>
      </div>

      <div>
        <label className="block text-xs font-medium text-slate-500 mb-1">To</label>
        <input
          type="email"
          className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
          value={toEmail}
          onChange={(e) => setToEmail(e.target.value)}
          placeholder="customer@example.com"
        />
      </div>

      <div>
        <label className="block text-xs font-medium text-slate-500 mb-1">Subject</label>
        <input
          className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
          value={subject}
          onChange={(e) => setSubject(e.target.value)}
        />
      </div>

      <div>
        <label className="block text-xs font-medium text-slate-500 mb-1">Body</label>
        <textarea
          rows={6}
          className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
          value={body}
          onChange={(e) => setBody(e.target.value)}
        />
      </div>

      {(quotationId || invoiceId) && (
        <label className="flex items-center gap-2 text-sm text-slate-600">
          <input type="checkbox" checked={attachPdf} onChange={(e) => setAttachPdf(e.target.checked)} />
          Attach PDF
        </label>
      )}

      <div className="flex items-center gap-2">
        <label className="text-sm text-slate-600 whitespace-nowrap">Remind me if no reply within</label>
        <input
          type="number"
          min={0}
          className="w-16 rounded-lg border border-slate-300 px-2 py-1 text-sm"
          value={followUpDays}
          onChange={(e) => setFollowUpDays(e.target.value)}
        />
        <span className="text-sm text-slate-600">day(s) (0 = no reminder)</span>
      </div>

      {error && <p className="text-sm text-red-500">{error}</p>}
      {sentResult && sentResult.status === "sent" && (
        <p className="text-sm text-green-600">Email sent.</p>
      )}
      {sentResult && sentResult.status === "failed" && (
        <p className="text-sm text-amber-600">
          Logged, but sending failed: {sentResult.error_message || "unknown error"}. If you
          haven't configured SMTP_* in backend/.env yet, that's expected.
        </p>
      )}

      <button
        onClick={handleSend}
        disabled={sending}
        className="w-full rounded-lg bg-brand-600 text-white px-4 py-2.5 text-sm font-medium hover:bg-brand-700 disabled:opacity-50"
      >
        {sending ? "Sending…" : "Send Email"}
      </button>
    </div>
  );
}
