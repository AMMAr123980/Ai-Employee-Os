"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  GitPullRequest,
  Building2,
  Phone,
  Mail,
  ArrowRight,
  Sparkles,
  MoveRight,
} from "lucide-react";
import { api, Customer, PipelineStage, PIPELINE_STAGES } from "@/lib/api";

const STAGE_CONFIG: Record<
  PipelineStage,
  { label: string; accent: string; badge: string }
> = {
  new: { label: "New Lead", accent: "border-t-slate-400 bg-slate-500", badge: "bg-slate-100 text-slate-700" },
  contacted: { label: "Contacted", accent: "border-t-blue-500 bg-blue-500", badge: "bg-blue-50 text-blue-700" },
  qualified: { label: "Qualified", accent: "border-t-indigo-500 bg-indigo-500", badge: "bg-indigo-50 text-indigo-700" },
  proposal: { label: "Proposal Sent", accent: "border-t-purple-500 bg-purple-500", badge: "bg-purple-50 text-purple-700" },
  negotiation: { label: "Negotiation", accent: "border-t-amber-500 bg-amber-500", badge: "bg-amber-50 text-amber-700" },
  won: { label: "Closed Won", accent: "border-t-emerald-500 bg-emerald-500", badge: "bg-emerald-50 text-emerald-700" },
  lost: { label: "Closed Lost", accent: "border-t-rose-500 bg-rose-500", badge: "bg-rose-50 text-rose-700" },
};

export default function PipelinePage() {
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [loading, setLoading] = useState(true);
  const [movingId, setMovingId] = useState<string | null>(null);

  async function load() {
    setCustomers(await api.listCustomers());
    setLoading(false);
  }

  useEffect(() => {
    load();
  }, []);

  async function moveStage(customer: Customer, newStage: PipelineStage) {
    setMovingId(customer.id);
    try {
      const updated = await api.updatePipelineStage(customer.id, newStage);
      setCustomers((prev) => prev.map((c) => (c.id === updated.id ? updated : c)));
    } finally {
      setMovingId(null);
    }
  }

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center text-xs text-slate-400">
        <Sparkles className="h-4 w-4 animate-spin text-brand-600 mr-2" />
        <span>Loading Pipeline Deals...</span>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div>
        <div className="inline-flex items-center gap-1.5 rounded-full bg-indigo-50 px-2.5 py-0.5 text-xs font-semibold text-indigo-700 border border-indigo-200/60 mb-2">
          <GitPullRequest className="h-3.5 w-3.5" />
          <span>Sales & Opportunity Board</span>
        </div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">Sales Pipeline</h1>
        <p className="text-xs md:text-sm text-slate-500">
          Track stage progression and customer interactions. Updates automatically sync with client activity timelines.
        </p>
      </div>

      {/* Kanban Board Horizontal Scroll */}
      <div className="flex gap-4 overflow-x-auto pb-6 pt-1">
        {PIPELINE_STAGES.map((stage) => {
          const stageCustomers = customers.filter((c) => c.pipeline_stage === stage);
          const config = STAGE_CONFIG[stage];

          return (
            <div
              key={stage}
              className="w-72 shrink-0 rounded-2xl border border-slate-200/80 bg-slate-100/50 p-3 shadow-2xs flex flex-col"
            >
              {/* Column Header */}
              <div className="flex items-center justify-between pb-3 pt-1 px-1 border-b border-slate-200/60 mb-3">
                <div className="flex items-center gap-2">
                  <span className={`h-2.5 w-2.5 rounded-full ${config.accent.split(" ")[1]}`} />
                  <p className="text-xs font-bold text-slate-800">{config.label}</p>
                </div>
                <span className={`rounded-full px-2 py-0.2 text-[11px] font-bold ${config.badge}`}>
                  {stageCustomers.length}
                </span>
              </div>

              {/* Column Cards */}
              <div className="space-y-2.5 flex-1 min-h-[220px]">
                {stageCustomers.map((c) => (
                  <div
                    key={c.id}
                    className="group rounded-xl border border-slate-200/80 bg-white p-3.5 shadow-2xs transition hover:border-brand-300 hover:shadow-md"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <Link
                        href={`/customers/${c.id}`}
                        className="font-bold text-xs text-slate-900 group-hover:text-brand-600 transition"
                      >
                        {c.name}
                      </Link>
                    </div>

                    {c.company && (
                      <p className="text-[11px] text-slate-500 flex items-center gap-1 mt-1">
                        <Building2 className="h-3 w-3 text-slate-400" />
                        <span className="truncate">{c.company}</span>
                      </p>
                    )}

                    {c.email && (
                      <p className="text-[11px] text-slate-400 truncate mt-0.5">
                        {c.email}
                      </p>
                    )}

                    <div className="mt-3 pt-2.5 border-t border-slate-100 flex items-center justify-between gap-2">
                      <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">
                        Stage:
                      </span>
                      <select
                        className="text-xs rounded-lg border border-slate-200 bg-slate-50 px-2 py-1 text-slate-700 outline-none focus:border-brand-500 focus:bg-white font-medium"
                        value={stage}
                        disabled={movingId === c.id}
                        onChange={(e) => moveStage(c, e.target.value as PipelineStage)}
                      >
                        {PIPELINE_STAGES.map((s) => (
                          <option key={s} value={s}>
                            {STAGE_CONFIG[s].label}
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>
                ))}

                {stageCustomers.length === 0 && (
                  <div className="flex h-32 items-center justify-center rounded-xl border border-dashed border-slate-200/80 text-[11px] text-slate-400">
                    No deals in stage
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
