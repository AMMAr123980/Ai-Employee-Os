"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  ArrowLeft,
  Bot,
  Sparkles,
  Send,
  Sliders,
  Database,
  Briefcase,
  CheckCircle2,
  ShieldAlert,
  ShieldCheck,
  Check,
} from "lucide-react";
import { api, AIEmployee, EmployeeRecords, EmployeeRun } from "@/lib/api";
import RunCard from "@/components/RunCard";

type Tab = "work" | "records" | "settings";

function prettyKey(key: string) {
  return key.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}

function formatCell(value: any) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "yes" : "no";
  if (typeof value === "number") return Number.isInteger(value) ? value : value.toFixed(2);
  if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}T/.test(value))
    return new Date(value).toLocaleDateString();
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export default function EmployeePage() {
  const { key } = useParams<{ key: string }>();

  const [employee, setEmployee] = useState<AIEmployee | null>(null);
  const [runs, setRuns] = useState<EmployeeRun[]>([]);
  const [records, setRecords] = useState<EmployeeRecords>({});
  const [tab, setTab] = useState<Tab>("work");
  const [brief, setBrief] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [instructions, setInstructions] = useState("");
  const [saved, setSaved] = useState(false);

  async function load() {
    try {
      const [roster, runList, recordSet] = await Promise.all([
        api.listAiEmployees(),
        api.listRuns(key),
        api.listEmployeeRecords(key).catch(() => ({})),
      ]);
      const found = roster.find((e) => e.key === key) || null;
      setEmployee(found);
      setInstructions(found?.instructions || "");
      setRuns(runList);
      setRecords(recordSet as EmployeeRecords);
    } catch (e: any) {
      setError(e.message);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  async function send(text: string) {
    if (!text.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      const run = await api.submitBrief(key, text.trim());
      setRuns((r) => [run, ...r]);
      setBrief("");
      if (run.status === "executed") api.listEmployeeRecords(key).then(setRecords).catch(() => {});
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function saveConfig(patch: Parameters<typeof api.updateEmployeeConfig>[1]) {
    const updated = await api.updateEmployeeConfig(key, patch);
    setEmployee(updated);
    setSaved(true);
    setTimeout(() => setSaved(false), 2500);
  }

  if (!employee) {
    return (
      <div className="flex h-64 items-center justify-center">
        <div className="flex items-center gap-2 text-sm text-slate-500">
          <Sparkles className="h-4 w-4 animate-spin text-brand-600" />
          <span>{error ? error : "Loading Specialist..."}</span>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header & Back Link */}
      <header>
        <Link
          href="/ai-employees"
          className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-500 hover:text-slate-800 transition mb-3"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          <span>Back to AI Fleet</span>
        </Link>
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mt-1">
          <div className="flex items-center gap-3.5">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-tr from-brand-600 to-indigo-600 font-bold text-lg text-white shadow-md shadow-brand-500/20">
              {employee.display_name ? employee.display_name[0] : "A"}
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-2xl font-bold tracking-tight text-slate-900">
                  {employee.display_name || employee.label}
                </h1>
                {employee.enabled ? (
                  <span className="flex h-2.5 w-2.5 rounded-full bg-emerald-500" />
                ) : (
                  <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-500">
                    Off
                  </span>
                )}
              </div>
              <p className="text-xs text-slate-500 mt-0.5">{employee.description}</p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {employee.autonomy_level === "cautious" ? (
              <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 border border-amber-200 px-3 py-1 text-xs font-semibold text-amber-700">
                <ShieldAlert className="h-3.5 w-3.5" />
                <span>Approval Mode</span>
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 border border-emerald-200 px-3 py-1 text-xs font-semibold text-emerald-700">
                <ShieldCheck className="h-3.5 w-3.5" />
                <span>Autonomous Mode</span>
              </span>
            )}
          </div>
        </div>
      </header>

      {/* Tabs */}
      <nav className="flex gap-2 border-b border-slate-200/80 pb-1">
        {[
          { id: "work", label: "Operations & Briefs", icon: Briefcase },
          { id: "records", label: "Ledger & Records", icon: Database, hide: Object.keys(records).length === 0 },
          { id: "settings", label: "Persona & Autonomy Settings", icon: Sliders },
        ]
          .filter((t) => !t.hide)
          .map((t) => {
            const Icon = t.icon;
            const active = tab === t.id;
            return (
              <button
                key={t.id}
                onClick={() => setTab(t.id as Tab)}
                className={`flex items-center gap-2 rounded-xl px-4 py-2 text-xs font-semibold transition ${
                  active
                    ? "bg-brand-50 text-brand-700 shadow-2xs"
                    : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
                }`}
              >
                <Icon className="h-4 w-4" />
                <span>{t.label}</span>
              </button>
            );
          })}
      </nav>

      {/* Work Tab */}
      {tab === "work" && (
        <div className="space-y-6">
          {!employee.enabled && (
            <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-xs font-medium text-amber-800">
              This AI employee is currently switched off. Turn it back on under Settings to dispatch instructions.
            </div>
          )}

          {/* Interactive Instruction Box */}
          <div className="rounded-2xl border border-slate-200/80 bg-white p-4 shadow-2xs">
            <textarea
              value={brief}
              onChange={(e) => setBrief(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) send(brief);
              }}
              rows={3}
              placeholder={`Instruct ${employee.display_name || employee.label} in plain language (e.g. "Prepare vendor contract review for Q3" or "Draft outbound payment batch")...`}
              className="w-full resize-none rounded-xl border border-slate-200 bg-slate-50/50 p-3.5 text-xs md:text-sm text-slate-800 placeholder-slate-400 outline-none focus:border-brand-500 focus:bg-white focus:ring-2 focus:ring-brand-500/10 transition"
            />
            <div className="mt-3 flex items-center justify-between">
              <span className="text-[11px] text-slate-400">
                Press <kbd className="font-mono bg-slate-100 px-1.5 py-0.5 rounded border border-slate-200 text-slate-600">⌘+Enter</kbd> to dispatch
              </span>
              <button
                onClick={() => send(brief)}
                disabled={busy || !brief.trim() || !employee.enabled}
                className="inline-flex items-center gap-1.5 rounded-xl bg-brand-600 px-4 py-2 text-xs font-semibold text-white shadow-sm hover:bg-brand-700 disabled:opacity-50 transition"
              >
                {busy ? (
                  <>
                    <Sparkles className="h-3.5 w-3.5 animate-spin" />
                    <span>Agent Planning...</span>
                  </>
                ) : (
                  <>
                    <Send className="h-3.5 w-3.5" />
                    <span>Send Instruction</span>
                  </>
                )}
              </button>
            </div>
          </div>

          {error && (
            <div className="rounded-xl bg-rose-50 border border-rose-200 p-3 text-xs text-rose-700">
              {error}
            </div>
          )}

          {/* Example Prompts */}
          {runs.length === 0 && (
            <div className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-2xs">
              <p className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-3">
                Suggested Directives & Prompts
              </p>
              <div className="grid gap-2 sm:grid-cols-2">
                {employee.examples.map((example) => (
                  <button
                    key={example}
                    onClick={() => send(example)}
                    disabled={!employee.enabled}
                    className="flex items-center justify-between rounded-xl border border-slate-200/80 bg-slate-50/50 p-3 text-left text-xs font-medium text-slate-700 transition hover:border-brand-300 hover:bg-brand-50/30 hover:text-brand-700 disabled:opacity-50"
                  >
                    <span>&ldquo;{example}&rdquo;</span>
                    <Sparkles className="h-3.5 w-3.5 text-brand-500 shrink-0 ml-2" />
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Run Log */}
          <div className="space-y-3">
            {runs.map((run) => (
              <RunCard
                key={run.id}
                run={run}
                onChange={(updated) => {
                  setRuns((rs) => rs.map((r) => (r.id === updated.id ? updated : r)));
                  if (updated.status === "executed")
                    api.listEmployeeRecords(key).then(setRecords).catch(() => {});
                }}
              />
            ))}
          </div>
        </div>
      )}

      {/* Records Tab */}
      {tab === "records" && (
        <div className="space-y-6">
          {Object.entries(records).map(([title, table]) => (
            <section key={title} className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-2xs">
              <h2 className="mb-3 text-sm font-bold text-slate-800 flex items-center justify-between">
                <span>{title}</span>
                <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-normal text-slate-500">
                  {table.rows.length} rows
                </span>
              </h2>
              {table.rows.length === 0 ? (
                <div className="rounded-xl border border-dashed border-slate-200 p-8 text-center text-xs text-slate-400">
                  No records stored yet.
                </div>
              ) : (
                <div className="overflow-x-auto rounded-xl border border-slate-100">
                  <table className="w-full text-left text-xs">
                    <thead className="bg-slate-50 text-slate-500 font-semibold border-b border-slate-100">
                      <tr>
                        {table.columns.map((column) => (
                          <th key={column} className="whitespace-nowrap px-3 py-2.5">
                            {prettyKey(column)}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {table.rows.map((row, i) => (
                        <tr key={i} className="hover:bg-slate-50/50 transition">
                          {table.columns.map((column) => (
                            <td
                              key={column}
                              className={`whitespace-nowrap px-3 py-2.5 ${
                                row.low && column === "name" ? "font-bold text-rose-600" : "text-slate-700"
                              }`}
                            >
                              {formatCell(row[column])}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          ))}
        </div>
      )}

      {/* Settings Tab */}
      {tab === "settings" && (
        <div className="max-w-2xl space-y-5">
          <div className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-2xs flex items-center justify-between">
            <div>
              <p className="text-sm font-bold text-slate-900">Active Status</p>
              <p className="text-xs text-slate-500">
                When inactive, this specialist will decline execution requests.
              </p>
            </div>
            <button
              onClick={() => saveConfig({ enabled: !employee.enabled })}
              className={`rounded-xl px-4 py-2 text-xs font-semibold shadow-2xs transition ${
                employee.enabled
                  ? "bg-emerald-600 text-white hover:bg-emerald-700"
                  : "bg-slate-200 text-slate-600 hover:bg-slate-300"
              }`}
            >
              {employee.enabled ? "Active" : "Disabled"}
            </button>
          </div>

          <div className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-2xs space-y-3">
            <div>
              <p className="text-sm font-bold text-slate-900">Autonomy & Approval Policy</p>
              <p className="text-xs text-slate-500">
                Standard holds sensitive external actions (sending payments, emailing clients). Cautious holds all actions for review.
              </p>
            </div>
            <div className="flex gap-2.5 pt-1">
              {(["standard", "cautious"] as const).map((level) => (
                <button
                  key={level}
                  onClick={() => saveConfig({ autonomy_level: level })}
                  className={`flex-1 rounded-xl border p-3 text-left transition ${
                    employee.autonomy_level === level
                      ? "border-brand-500 bg-brand-50/60 ring-2 ring-brand-500/20"
                      : "border-slate-200 hover:bg-slate-50"
                  }`}
                >
                  <p className="text-xs font-bold text-slate-800 capitalize">{level} Autonomy</p>
                  <p className="text-[11px] text-slate-500 mt-0.5">
                    {level === "standard"
                      ? "Requires approval for money, contracts, and external messages"
                      : "Requires manual approval for all actions"}
                  </p>
                </button>
              ))}
            </div>
          </div>

          <div className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-2xs space-y-3">
            <div>
              <p className="text-sm font-bold text-slate-900">Custom Business Directives & Prompting</p>
              <p className="text-xs text-slate-500">
                Inject custom instructions for this agent (e.g. &ldquo;Always use USD&rdquo;, &ldquo;Company payment terms are Net 30&rdquo;).
              </p>
            </div>
            <textarea
              rows={3}
              key={employee.instructions || "blank"}
              defaultValue={instructions}
              onChange={(e) => setInstructions(e.target.value)}
              className="w-full resize-none rounded-xl border border-slate-200 p-3 text-xs text-slate-800 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/10"
            />
            <div className="flex items-center gap-3">
              <button
                onClick={() => saveConfig({ instructions })}
                className="rounded-xl bg-brand-600 px-4 py-2 text-xs font-semibold text-white hover:bg-brand-700 shadow-2xs transition"
              >
                Save Persona Instructions
              </button>
              {saved && (
                <span className="flex items-center gap-1 text-xs font-semibold text-emerald-600">
                  <Check className="h-3.5 w-3.5" />
                  <span>Saved successfully</span>
                </span>
              )}
            </div>
          </div>

          <div className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-2xs">
            <p className="text-sm font-bold text-slate-900">Supported Intent Actions</p>
            <div className="mt-3 flex flex-wrap gap-1.5">
              {employee.intents.map((intent) => (
                <span
                  key={intent}
                  className="rounded-lg bg-slate-100 px-2.5 py-1 text-xs font-mono font-medium text-slate-700"
                >
                  {prettyKey(intent)}
                </span>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
