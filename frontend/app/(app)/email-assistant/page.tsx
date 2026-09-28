"use client";

import { useState } from "react";
import { api } from "@/lib/api";

const PRIORITY_COLORS: Record<string, string> = {
  urgent: "bg-red-100 text-red-700",
  high: "bg-amber-100 text-amber-700",
  normal: "bg-blue-100 text-blue-700",
  low: "bg-slate-100 text-slate-600",
};

const CATEGORY_COLORS: Record<string, string> = {
  complaint: "bg-red-100 text-red-700",
  billing: "bg-purple-100 text-purple-700",
  sales: "bg-green-100 text-green-700",
  support: "bg-blue-100 text-blue-700",
  spam: "bg-slate-100 text-slate-500",
  other: "bg-slate-100 text-slate-600",
};

export default function EmailAssistantPage() {
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const [summary, setSummary] = useState<{ summary: string; action_items: string[] } | null>(null);
  const [classification, setClassification] = useState<{
    category: string;
    priority: string;
    reasoning: string;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Inbound Sync State
  const [syncing, setSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState<string | null>(null);
  const [simFromEmail, setSimFromEmail] = useState("client@acmecorp.com");
  const [simSubject, setSimSubject] = useState("Re: Quotation #QUO-000001 Approved!");
  const [simBody, setSimBody] = useState("We received the quotation and invoice. We approve it and would like to proceed!");

  async function handleSyncNow() {
    setSyncing(true);
    setSyncResult(null);
    try {
      const res = await api.syncInboxNow();
      setSyncResult(`Inbox synced! Processed ${res.synced_count} email(s) and auto-resolved ${res.followups_resolved} pending follow-up nudge(s).`);
    } catch (e: any) {
      alert("Error syncing inbox: " + e.message);
    } finally {
      setSyncing(false);
    }
  }

  async function handleSimulateInbound() {
    setSyncing(true);
    setSyncResult(null);
    try {
      const res = await api.simulateInboundEmail({
        from_email: simFromEmail,
        subject: simSubject,
        body: simBody,
      });
      setSyncResult(`Inbound email received! Auto-logged to customer timeline and auto-resolved ${res.followups_auto_resolved} pending follow-up nudge(s).`);
    } catch (e: any) {
      alert("Error simulating email: " + e.message);
    } finally {
      setSyncing(false);
    }
  }

  async function handleAnalyze() {
    if (!text.trim()) return;
    setLoading(true);
    setError(null);
    setSummary(null);
    setClassification(null);
    try {
      const [s, c] = await Promise.all([api.summarizeText(text), api.classifyText(text)]);
      setSummary(s);
      setClassification(c);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold mb-1">Email Assistant & Inbound Sync</h1>
        <p className="text-slate-500">
          Inbound email sync engine, thread triaging, automatic follow-up nudge resolution, and AI classification.
        </p>
      </div>

      {/* Inbound Sync Control Box */}
      <div className="rounded-xl border border-indigo-200 bg-gradient-to-r from-indigo-50 to-purple-50 p-5 space-y-3 shadow-sm">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="font-bold text-indigo-950 text-sm">📥 Gmail / Outlook Inbound Sync & Reply Detector</h3>
            <p className="text-xs text-indigo-700">Auto-syncs customer replies, logs activity timelines, and dismisses pending follow-ups.</p>
          </div>
          <button
            onClick={handleSyncNow}
            disabled={syncing}
            className="px-3.5 py-2 bg-indigo-600 hover:bg-indigo-700 text-white font-bold text-xs rounded-lg shadow transition disabled:opacity-50"
          >
            {syncing ? "Syncing..." : "🔄 Sync Inbox Now"}
          </button>
        </div>

        {syncResult && (
          <div className="p-3 bg-white border border-indigo-200 text-indigo-900 rounded-lg text-xs font-semibold">
            {syncResult}
          </div>
        )}

        <div className="pt-2 border-t border-indigo-100">
          <p className="text-xs font-bold text-indigo-900 uppercase mb-2">Simulate Incoming Customer Email (Dev Test)</p>
          <div className="space-y-2">
            <input
              type="text"
              value={simFromEmail}
              onChange={(e) => setSimFromEmail(e.target.value)}
              placeholder="Customer Email"
              className="w-full p-2 bg-white border border-indigo-200 rounded text-xs"
            />
            <input
              type="text"
              value={simSubject}
              onChange={(e) => setSimSubject(e.target.value)}
              placeholder="Email Subject"
              className="w-full p-2 bg-white border border-indigo-200 rounded text-xs"
            />
            <textarea
              rows={2}
              value={simBody}
              onChange={(e) => setSimBody(e.target.value)}
              placeholder="Email Body"
              className="w-full p-2 bg-white border border-indigo-200 rounded text-xs"
            />
            <button
              onClick={handleSimulateInbound}
              disabled={syncing}
              className="px-3 py-1.5 bg-purple-600 hover:bg-purple-700 text-white font-bold text-xs rounded shadow transition"
            >
              📩 Inject Test Inbound Reply
            </button>
          </div>
        </div>
      </div>


      <div className="rounded-xl border border-slate-200 bg-white p-5 space-y-4">
        <textarea
          rows={8}
          className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
          placeholder="Paste the email text here…"
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        <button
          onClick={handleAnalyze}
          disabled={loading}
          className="rounded-lg bg-brand-600 text-white px-4 py-2 text-sm font-medium hover:bg-brand-700 disabled:opacity-50"
        >
          {loading ? "Analyzing…" : "Analyze"}
        </button>
        {error && <p className="text-sm text-red-500">{error}</p>}
      </div>

      {(summary || classification) && (
        <div className="mt-6 space-y-4">
          {classification && (
            <div className="rounded-xl border border-slate-200 bg-white p-5">
              <div className="flex gap-2 mb-2">
                <span
                  className={`text-xs font-medium rounded-full px-2.5 py-0.5 capitalize ${
                    CATEGORY_COLORS[classification.category] || "bg-slate-100 text-slate-600"
                  }`}
                >
                  {classification.category}
                </span>
                <span
                  className={`text-xs font-medium rounded-full px-2.5 py-0.5 capitalize ${
                    PRIORITY_COLORS[classification.priority] || "bg-slate-100 text-slate-600"
                  }`}
                >
                  {classification.priority} priority
                </span>
              </div>
              <p className="text-sm text-slate-600">{classification.reasoning}</p>
            </div>
          )}

          {summary && (
            <div className="rounded-xl border border-slate-200 bg-white p-5">
              <p className="text-sm font-medium mb-2">Summary</p>
              <p className="text-sm text-slate-600 mb-3">{summary.summary}</p>
              {summary.action_items.length > 0 && (
                <>
                  <p className="text-sm font-medium mb-1">Action Items</p>
                  <ul className="list-disc list-inside text-sm text-slate-600 space-y-0.5">
                    {summary.action_items.map((item, i) => (
                      <li key={i}>{item}</li>
                    ))}
                  </ul>
                </>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
