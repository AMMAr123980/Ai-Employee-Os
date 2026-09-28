"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, FollowUp } from "@/lib/api";

export default function FollowUpsPage() {
  const [followUps, setFollowUps] = useState<FollowUp[]>([]);
  const [loading, setLoading] = useState(true);
  const [checking, setChecking] = useState(false);
  const [edits, setEdits] = useState<Record<string, { subject: string; body: string }>>({});
  const [busyId, setBusyId] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  async function load() {
    const list = await api.listFollowUps();
    setFollowUps(list);
    setEdits(Object.fromEntries(list.map((f) => [f.id, { subject: f.subject, body: f.body }])));
    setLoading(false);
  }

  useEffect(() => {
    load();
  }, []);

  async function handleCheckNow() {
    setChecking(true);
    setMessage(null);
    try {
      const result = await api.checkFollowUpsNow();
      await load();
      setMessage(
        result.drafts_created > 0
          ? `Found ${result.drafts_created} new follow-up(s) due.`
          : "No follow-ups due right now."
      );
    } finally {
      setChecking(false);
    }
  }

  async function handleSend(id: string) {
    setBusyId(id);
    try {
      const edit = edits[id];
      await api.sendFollowUp(id, { subject: edit?.subject, body: edit?.body });
      setFollowUps((prev) => prev.filter((f) => f.id !== id));
    } finally {
      setBusyId(null);
    }
  }

  async function handleDismiss(id: string) {
    setBusyId(id);
    try {
      await api.dismissFollowUp(id);
      setFollowUps((prev) => prev.filter((f) => f.id !== id));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="max-w-3xl">
      <div className="flex items-center justify-between mb-1">
        <h1 className="text-2xl font-semibold">Follow-ups</h1>
        <button
          onClick={handleCheckNow}
          disabled={checking}
          className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium hover:bg-slate-100 disabled:opacity-50"
        >
          {checking ? "Checking…" : "Check Now"}
        </button>
      </div>
      <p className="text-slate-500 mb-6">
        When an email you sent has passed its follow-up date without action, AI drafts
        a nudge here automatically — nothing sends until you review and click Send.
        This runs in the background every {" "}
        <code className="text-xs bg-slate-100 px-1 py-0.5 rounded">FOLLOWUP_CHECK_INTERVAL_MINUTES</code>{" "}
        too, so "Check Now" is just for testing or getting an immediate read.
      </p>

      {message && <p className="text-sm text-brand-600 mb-4">{message}</p>}

      {loading ? (
        <p className="text-sm text-slate-400">Loading…</p>
      ) : followUps.length === 0 ? (
        <p className="text-sm text-slate-400 rounded-xl border border-dashed border-slate-300 p-5">
          No pending follow-ups. Send an email with a follow-up reminder from a
          quotation or invoice page, and it'll show up here once it's due.
        </p>
      ) : (
        <div className="space-y-4">
          {followUps.map((f) => (
            <div key={f.id} className="rounded-xl border border-slate-200 bg-white p-4">
              <div className="flex items-center justify-between mb-2">
                <Link href={`/customers/${f.customer_id}`} className="text-sm font-medium text-brand-700 hover:underline">
                  {f.customer_name}
                </Link>
                <span className="text-xs text-slate-400">{f.to_email}</span>
              </div>
              <input
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm mb-2 font-medium"
                value={edits[f.id]?.subject ?? f.subject}
                onChange={(e) => setEdits((prev) => ({ ...prev, [f.id]: { ...prev[f.id], subject: e.target.value } }))}
              />
              <textarea
                rows={5}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm mb-3"
                value={edits[f.id]?.body ?? f.body}
                onChange={(e) => setEdits((prev) => ({ ...prev, [f.id]: { ...prev[f.id], body: e.target.value } }))}
              />
              <div className="flex gap-2">
                <button
                  onClick={() => handleSend(f.id)}
                  disabled={busyId === f.id}
                  className="rounded-lg bg-brand-600 text-white px-4 py-2 text-sm font-medium hover:bg-brand-700 disabled:opacity-50"
                >
                  {busyId === f.id ? "Sending…" : "Send"}
                </button>
                <button
                  onClick={() => handleDismiss(f.id)}
                  disabled={busyId === f.id}
                  className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium hover:bg-slate-100 disabled:opacity-50"
                >
                  Dismiss
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
