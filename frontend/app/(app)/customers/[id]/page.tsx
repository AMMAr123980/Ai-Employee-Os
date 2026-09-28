"use client";

import { use, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api, Customer, ActivityItem, PipelineStage, PIPELINE_STAGES } from "@/lib/api";
import { useAuth } from "@/components/AuthGuard";

const STAGE_LABELS: Record<PipelineStage, string> = {
  new: "New",
  contacted: "Contacted",
  qualified: "Qualified",
  proposal: "Proposal",
  negotiation: "Negotiation",
  won: "Won",
  lost: "Lost",
};

const EMAIL_STATUS_COLORS: Record<string, string> = {
  sent: "bg-green-100 text-green-700",
  failed: "bg-red-100 text-red-700",
  draft: "bg-slate-100 text-slate-600",
};

const NOTE_TYPE_LABELS: Record<string, string> = {
  note: "📝 Note",
  call: "📞 Call",
  meeting: "🤝 Meeting",
  status_change: "🔄 Stage change",
};

export default function CustomerDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();
  const { user } = useAuth();
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [activity, setActivity] = useState<ActivityItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [stageUpdating, setStageUpdating] = useState(false);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [noteText, setNoteText] = useState("");
  const [noteType, setNoteType] = useState("note");
  const [noteSaving, setNoteSaving] = useState(false);

  async function load() {
    const [c, a] = await Promise.all([api.getCustomer(id), api.getActivity(id)]);
    setCustomer(c);
    setActivity(a);
    setLoading(false);
  }

  useEffect(() => {
    load();
  }, [id]);

  async function handleStageChange(stage: PipelineStage) {
    setStageUpdating(true);
    try {
      const updated = await api.updatePipelineStage(id, stage);
      setCustomer(updated);
      setActivity(await api.getActivity(id));
    } finally {
      setStageUpdating(false);
    }
  }

  async function handleGenerateSummary() {
    setSummaryLoading(true);
    try {
      await api.generateAiSummary(id);
      setCustomer(await api.getCustomer(id));
    } finally {
      setSummaryLoading(false);
    }
  }

  async function handleAddNote() {
    if (!noteText.trim()) return;
    setNoteSaving(true);
    try {
      await api.addNote(id, noteText, noteType);
      setNoteText("");
      setActivity(await api.getActivity(id));
    } finally {
      setNoteSaving(false);
    }
  }

  async function handleDelete() {
    if (!confirm(`Delete ${customer?.name}? This can't be undone.`)) return;
    setDeleting(true);
    setDeleteError(null);
    try {
      await api.deleteCustomer(id);
      router.push("/customers");
    } catch (e: any) {
      setDeleteError(e.message || "Failed to delete — you may not have permission.");
      setDeleting(false);
    }
  }

  if (loading || !customer) {
    return <p className="text-sm text-slate-400">Loading…</p>;
  }

  return (
    <div className="max-w-3xl">
      <div className="flex items-start justify-between mb-2">
        <div>
          <h1 className="text-2xl font-semibold">{customer.name}</h1>
          <p className="text-slate-500 text-sm">
            {customer.company && <>{customer.company} · </>}
            {customer.email || "no email on file"} {customer.phone && <>· {customer.phone}</>}
          </p>
          {customer.address && <p className="text-slate-400 text-sm mt-1">{customer.address}</p>}
          {customer.lead_source && (
            <p className="text-slate-400 text-xs mt-1">Source: {customer.lead_source}</p>
          )}
        </div>
        <div className="flex flex-col items-end gap-2">
          <select
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium"
            value={customer.pipeline_stage}
            disabled={stageUpdating}
            onChange={(e) => handleStageChange(e.target.value as PipelineStage)}
          >
            {PIPELINE_STAGES.map((s) => (
              <option key={s} value={s}>
                {STAGE_LABELS[s]}
              </option>
            ))}
          </select>
          {(user.role === "owner" || user.role === "admin") && (
            <button
              onClick={handleDelete}
              disabled={deleting}
              className="text-xs font-medium text-slate-400 hover:text-red-500 disabled:opacity-50"
            >
              {deleting ? "Deleting…" : "Delete customer"}
            </button>
          )}
        </div>
      </div>
      {deleteError && <p className="text-sm text-red-500 mb-4">{deleteError}</p>}

      <div className="rounded-xl border border-brand-100 bg-brand-50 p-4 mb-6 mt-4">
        <div className="flex items-center justify-between mb-1">
          <p className="text-sm font-medium text-brand-700">AI Relationship Summary</p>
          <button
            onClick={handleGenerateSummary}
            disabled={summaryLoading}
            className="text-xs font-medium text-brand-600 hover:underline disabled:opacity-50"
          >
            {summaryLoading ? "Generating…" : customer.ai_relationship_summary ? "Refresh" : "Generate"}
          </button>
        </div>
        {customer.ai_relationship_summary ? (
          <>
            <p className="text-sm text-brand-800">{customer.ai_relationship_summary}</p>
            {customer.ai_summary_generated_at && (
              <p className="text-xs text-brand-400 mt-1">
                Generated {new Date(customer.ai_summary_generated_at).toLocaleString()}
              </p>
            )}
          </>
        ) : (
          <p className="text-sm text-brand-400 italic">
            No summary yet — click Generate to get an AI snapshot of this relationship.
          </p>
        )}
      </div>

      <div className="rounded-xl border border-slate-200 bg-white p-4 mb-6">
        <p className="text-sm font-medium mb-2">Add Activity</p>
        <div className="flex gap-2">
          <select
            className="rounded-lg border border-slate-300 px-2 py-2 text-sm"
            value={noteType}
            onChange={(e) => setNoteType(e.target.value)}
          >
            <option value="note">Note</option>
            <option value="call">Call</option>
            <option value="meeting">Meeting</option>
          </select>
          <input
            className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm"
            placeholder="e.g. Called to follow up, wants a revised quote"
            value={noteText}
            onChange={(e) => setNoteText(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleAddNote()}
          />
          <button
            onClick={handleAddNote}
            disabled={noteSaving}
            className="rounded-lg bg-brand-600 text-white px-4 py-2 text-sm font-medium hover:bg-brand-700 disabled:opacity-50"
          >
            {noteSaving ? "Saving…" : "Add"}
          </button>
        </div>
      </div>

      <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wide mb-3">
        Activity Timeline
      </h2>

      {activity.length === 0 ? (
        <p className="text-sm text-slate-400 rounded-xl border border-dashed border-slate-300 p-5">
          No activity yet. Add a note above, or send an email from a quotation/invoice page.
        </p>
      ) : (
        <div className="space-y-3">
          {activity.map((item) => (
            <div key={`${item.kind}-${item.id}`} className="rounded-xl border border-slate-200 bg-white p-4">
              {item.kind === "note" ? (
                <>
                  <div className="flex items-center justify-between mb-1">
                    <p className="text-sm font-medium">{NOTE_TYPE_LABELS[item.note_type || "note"]}</p>
                    <p className="text-xs text-slate-400">
                      {new Date(item.created_at).toLocaleString(undefined, {
                        dateStyle: "medium",
                        timeStyle: "short",
                      })}
                    </p>
                  </div>
                  <p className="text-sm text-slate-600 whitespace-pre-line">{item.content}</p>
                  {item.user_name && <p className="text-xs text-slate-400 mt-1">— {item.user_name}</p>}
                </>
              ) : (
                <>
                  <div className="flex items-center justify-between mb-1">
                    <p className="text-sm font-medium">✉ {item.subject}</p>
                    <span
                      className={`text-xs font-medium rounded-full px-2 py-0.5 capitalize ${
                        EMAIL_STATUS_COLORS[item.status || ""] || "bg-slate-100 text-slate-600"
                      }`}
                    >
                      {item.status}
                    </span>
                  </div>
                  <p className="text-xs text-slate-400 mb-2">
                    To {item.to_email} ·{" "}
                    {new Date(item.created_at).toLocaleString(undefined, {
                      dateStyle: "medium",
                      timeStyle: "short",
                    })}
                    {item.quotation_id && (
                      <>
                        {" "}
                        ·{" "}
                        <Link href={`/quotations/${item.quotation_id}`} className="text-brand-600 hover:underline">
                          related quotation
                        </Link>
                      </>
                    )}
                    {item.invoice_id && (
                      <>
                        {" "}
                        ·{" "}
                        <Link href={`/invoices/${item.invoice_id}`} className="text-brand-600 hover:underline">
                          related invoice
                        </Link>
                      </>
                    )}
                  </p>
                  <p className="text-sm text-slate-600 whitespace-pre-line">{item.content}</p>
                  {item.status === "failed" && item.error_message && (
                    <p className="text-xs text-amber-600 mt-2">Error: {item.error_message}</p>
                  )}
                </>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
