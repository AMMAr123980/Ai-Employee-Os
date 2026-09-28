"use client";

import { useState } from "react";
import {
  CheckCircle2,
  Clock,
  AlertTriangle,
  XCircle,
  HelpCircle,
  Play,
  X,
  Bot,
  Sparkles,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import { api, EmployeeRun, RunStatus } from "@/lib/api";

const STATUS_CONFIG: Record<
  RunStatus,
  { label: string; bg: string; text: string; border: string; icon: any }
> = {
  planned: {
    label: "Planned",
    bg: "bg-slate-50",
    text: "text-slate-600",
    border: "border-slate-200",
    icon: Clock,
  },
  no_action: {
    label: "No Action Needed",
    bg: "bg-amber-50/80",
    text: "text-amber-700",
    border: "border-amber-200/60",
    icon: HelpCircle,
  },
  awaiting_confirmation: {
    label: "Needs Your Approval",
    bg: "bg-brand-50",
    text: "text-brand-700 font-semibold",
    border: "border-brand-200",
    icon: Sparkles,
  },
  executed: {
    label: "Executed Successfully",
    bg: "bg-emerald-50/80",
    text: "text-emerald-700",
    border: "border-emerald-200/60",
    icon: CheckCircle2,
  },
  failed: {
    label: "Failed",
    bg: "bg-rose-50/80",
    text: "text-rose-700",
    border: "border-rose-200/60",
    icon: AlertTriangle,
  },
  cancelled: {
    label: "Cancelled",
    bg: "bg-slate-100",
    text: "text-slate-500",
    border: "border-slate-200",
    icon: XCircle,
  },
};

function prettyKey(key: string) {
  return key.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}

function ResultValue({ value }: { value: any }) {
  if (value === null || value === undefined) return <span className="text-slate-400">—</span>;
  if (typeof value === "boolean")
    return (
      <span
        className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
          value ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-600"
        }`}
      >
        {value ? "Yes" : "No"}
      </span>
    );
  if (typeof value === "string" && value.length > 180)
    return (
      <pre className="mt-1 max-h-72 overflow-auto whitespace-pre-wrap rounded-xl border border-slate-200 bg-slate-50/80 p-3.5 text-xs font-mono leading-relaxed text-slate-700">
        {value}
      </pre>
    );
  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="text-slate-400">None</span>;
    if (typeof value[0] === "object" && value[0] !== null) {
      const cols = Array.from(new Set(value.flatMap((v: any) => Object.keys(v))));
      return (
        <div className="mt-1 overflow-x-auto rounded-xl border border-slate-200/80 shadow-2xs">
          <table className="w-full text-xs">
            <thead className="bg-slate-50/80 text-slate-600 font-semibold border-b border-slate-200/60">
              <tr>
                {cols.map((c) => (
                  <th key={c} className="px-3 py-2 text-left">
                    {prettyKey(c)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 bg-white">
              {value.slice(0, 50).map((row: any, i: number) => (
                <tr key={i} className="hover:bg-slate-50/50 transition">
                  {cols.map((c) => (
                    <td key={c} className="px-3 py-2 align-top text-slate-700">
                      {typeof row[c] === "object" && row[c] !== null
                        ? JSON.stringify(row[c])
                        : String(row[c] ?? "—")}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    }
    return <span>{value.join(", ")}</span>;
  }
  if (typeof value === "object")
    return (
      <pre className="mt-1 overflow-auto rounded-lg bg-slate-50 p-2 text-xs font-mono text-slate-700 border border-slate-200/60">
        {JSON.stringify(value, null, 2)}
      </pre>
    );
  return <span className="font-medium text-slate-800">{String(value)}</span>;
}

export default function RunCard({
  run,
  onChange,
}: {
  run: EmployeeRun;
  onChange: (updated: EmployeeRun) => void;
}) {
  const config = run.action?.config || {};
  const [overrides, setOverrides] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedResult, setExpandedResult] = useState(true);

  const pending = run.status === "awaiting_confirmation";
  const statusCfg = STATUS_CONFIG[run.status] || STATUS_CONFIG.planned;
  const StatusIcon = statusCfg.icon;

  const slotKeys = Array.from(new Set([...run.missing_info, ...Object.keys(config)]));

  async function act(fn: () => Promise<EmployeeRun>) {
    setBusy(true);
    setError(null);
    try {
      onChange(await fn());
    } catch (e: any) {
      setError(e.message || "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className={`group rounded-2xl border bg-white p-5 shadow-2xs transition-all ${
        pending
          ? "border-brand-300 ring-2 ring-brand-100 shadow-md"
          : "border-slate-200/80 hover:border-slate-300"
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3 min-w-0">
          <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-slate-100 text-slate-700 border border-slate-200/60 group-hover:bg-brand-50 group-hover:text-brand-600 transition">
            <Bot className="h-4.5 w-4.5" />
          </div>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-slate-900 leading-snug">{run.brief}</p>
            <p className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-slate-400">
              <span>{new Date(run.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
              <span>·</span>
              <span>{new Date(run.created_at).toLocaleDateString()}</span>
              {run.intent && run.intent !== "unclear" && (
                <>
                  <span>·</span>
                  <span className="font-medium text-slate-600">{prettyKey(run.intent)}</span>
                </>
              )}
              {run.trigger === "schedule" && (
                <>
                  <span>·</span>
                  <span className="rounded bg-slate-100 px-1.5 py-0.2 font-medium text-slate-600">
                    Scheduled
                  </span>
                </>
              )}
              {typeof run.confidence === "number" && run.confidence > 0 && (
                <>
                  <span>·</span>
                  <span className="text-emerald-600 font-medium">
                    {Math.round(run.confidence * 100)}% Match
                  </span>
                </>
              )}
            </p>
          </div>
        </div>
        <span
          className={`inline-flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium shadow-2xs ${statusCfg.bg} ${statusCfg.text} ${statusCfg.border}`}
        >
          <StatusIcon className="h-3.5 w-3.5" />
          <span>{statusCfg.label}</span>
        </span>
      </div>

      {run.summary && (
        <div className="mt-3.5 rounded-xl bg-slate-50/70 p-3 border border-slate-100">
          <p className={`text-sm ${pending ? "font-medium text-slate-900" : "text-slate-600"}`}>
            {run.summary}
          </p>
        </div>
      )}

      {run.error && (
        <div className="mt-3.5 rounded-xl border border-rose-200 bg-rose-50/80 p-3.5 text-sm text-rose-800 flex items-start gap-2.5">
          <AlertTriangle className="h-4 w-4 shrink-0 text-rose-600 mt-0.5" />
          <div>
            <p className="font-medium">Execution issue encountered</p>
            <p className="text-xs text-rose-700 mt-0.5">{run.error}</p>
          </div>
        </div>
      )}

      {pending && (
        <div className="mt-4 rounded-xl border border-brand-200 bg-brand-50/40 p-4">
          <div className="flex items-center gap-2 text-xs font-semibold text-brand-900 mb-3">
            <Sparkles className="h-4 w-4 text-brand-600" />
            <span>Review Planned Action Parameters</span>
          </div>

          {run.missing_info.length > 0 && (
            <p className="mb-3 text-xs font-medium text-amber-800 bg-amber-50 border border-amber-200 rounded-lg p-2.5">
              Required parameters missing: {run.missing_info.map(prettyKey).join(", ")}. Please fill in before executing.
            </p>
          )}

          <div className="space-y-2.5">
            {slotKeys.map((key) => (
              <div key={key} className="flex flex-col sm:flex-row sm:items-center gap-1.5 sm:gap-3">
                <label className="w-36 shrink-0 text-xs font-medium text-slate-600">
                  {prettyKey(key)}
                </label>
                <input
                  className="flex-1 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-800 shadow-2xs focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20"
                  defaultValue={
                    typeof config[key] === "object"
                      ? JSON.stringify(config[key])
                      : config[key] ?? ""
                  }
                  placeholder={run.missing_info.includes(key) ? "Required value..." : "Optional..."}
                  onChange={(e) => setOverrides((o) => ({ ...o, [key]: e.target.value }))}
                />
              </div>
            ))}
          </div>

          <div className="mt-4 flex items-center gap-2.5 pt-2 border-t border-brand-100">
            <button
              disabled={busy}
              onClick={() =>
                act(() =>
                  api.confirmRun(
                    run.id,
                    Object.fromEntries(
                      Object.entries(overrides).map(([k, v]) => {
                        const n = Number(v);
                        return [k, v !== "" && !Number.isNaN(n) ? n : v];
                      })
                    )
                  )
                )
              }
              className="inline-flex items-center gap-1.5 rounded-xl bg-brand-600 px-4 py-2 text-xs font-medium text-white shadow-sm hover:bg-brand-700 disabled:opacity-50 transition"
            >
              <Play className="h-3.5 w-3.5 fill-current" />
              <span>{busy ? "Executing..." : "Approve & Execute Action"}</span>
            </button>
            <button
              disabled={busy}
              onClick={() => act(() => api.cancelRun(run.id))}
              className="inline-flex items-center gap-1 rounded-xl border border-slate-200 bg-white px-3.5 py-2 text-xs font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-50 transition"
            >
              <X className="h-3.5 w-3.5" />
              <span>Cancel</span>
            </button>
          </div>
          {error && <p className="mt-2 text-xs text-rose-600">{error}</p>}
        </div>
      )}

      {run.result && Object.keys(run.result).length > 0 && (
        <div className="mt-4 border-t border-slate-100 pt-3">
          <button
            onClick={() => setExpandedResult(!expandedResult)}
            className="flex items-center justify-between w-full text-xs font-semibold uppercase tracking-wider text-slate-400 hover:text-slate-600 transition mb-2"
          >
            <span>Action Output & Result Payload</span>
            {expandedResult ? (
              <ChevronUp className="h-3.5 w-3.5" />
            ) : (
              <ChevronDown className="h-3.5 w-3.5" />
            )}
          </button>
          {expandedResult && (
            <dl className="space-y-3">
              {Object.entries(run.result).map(([key, value]) => (
                <div key={key} className="text-sm">
                  <dt className="text-xs font-semibold text-slate-500 mb-1">
                    {prettyKey(key)}
                  </dt>
                  <dd>
                    <ResultValue value={value} />
                  </dd>
                </div>
              ))}
            </dl>
          )}
        </div>
      )}
    </div>
  );
}
