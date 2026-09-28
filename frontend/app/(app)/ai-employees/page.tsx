"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Bot,
  Sparkles,
  ShieldAlert,
  ShieldCheck,
  Play,
  Clock,
  ArrowRight,
  Activity,
  Layers,
  CheckCircle2,
} from "lucide-react";
import { api, AIEmployee, Duty, EmployeeRun } from "@/lib/api";
import RunCard from "@/components/RunCard";

const DEPARTMENT_THEMES: Record<
  string,
  { badge: string; border: string; bg: string; iconBg: string; text: string }
> = {
  operations: {
    badge: "bg-blue-50 text-blue-700 border-blue-200/60",
    border: "hover:border-blue-300",
    bg: "from-blue-500/5 to-transparent",
    iconBg: "bg-blue-600 text-white",
    text: "text-blue-700",
  },
  finance: {
    badge: "bg-emerald-50 text-emerald-700 border-emerald-200/60",
    border: "hover:border-emerald-300",
    bg: "from-emerald-500/5 to-transparent",
    iconBg: "bg-emerald-600 text-white",
    text: "text-emerald-700",
  },
  sales: {
    badge: "bg-purple-50 text-purple-700 border-purple-200/60",
    border: "hover:border-purple-300",
    bg: "from-purple-500/5 to-transparent",
    iconBg: "bg-purple-600 text-white",
    text: "text-purple-700",
  },
  support: {
    badge: "bg-amber-50 text-amber-700 border-amber-200/60",
    border: "hover:border-amber-300",
    bg: "from-amber-500/5 to-transparent",
    iconBg: "bg-amber-600 text-white",
    text: "text-amber-700",
  },
};

export default function AiEmployeesPage() {
  const [employees, setEmployees] = useState<AIEmployee[]>([]);
  const [duties, setDuties] = useState<Record<string, Duty>>({});
  const [recent, setRecent] = useState<EmployeeRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [runningDuty, setRunningDuty] = useState<string | null>(null);

  async function load() {
    try {
      const [roster, dutyResp, runs] = await Promise.all([
        api.listAiEmployees(),
        api.listDuties(),
        api.listRuns(),
      ]);
      setEmployees(roster);
      setDuties(dutyResp.duties);
      setRecent(runs.slice(0, 5));
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function handleDuty(dutyKey: string, duty: Duty) {
    setRunningDuty(dutyKey);
    try {
      const run = await api.runDuty(duty.employee, dutyKey);
      setRecent((r) => [run, ...r].slice(0, 5));
    } catch (e: any) {
      setError(e.message);
    } finally {
      setRunningDuty(null);
    }
  }

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <div className="flex items-center gap-2 text-sm text-slate-500">
          <Sparkles className="h-4 w-4 animate-spin text-brand-600" />
          <span>Loading AI Workforce Roster...</span>
        </div>
      </div>
    );
  }

  const byDepartment = employees.reduce<Record<string, AIEmployee[]>>((acc, e) => {
    (acc[e.department] ||= []).push(e);
    return acc;
  }, {});

  return (
    <div className="space-y-8">
      {/* Page Header */}
      <header className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="inline-flex items-center gap-1.5 rounded-full bg-brand-50 px-2.5 py-0.5 text-xs font-semibold text-brand-700 border border-brand-200/50 mb-2">
            <Bot className="h-3.5 w-3.5" />
            <span>Multi-Agent Architecture</span>
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">
            AI Employee Fleet
          </h1>
          <p className="mt-1 text-xs md:text-sm text-slate-500 max-w-2xl">
            Autonomous specialists managing sales, finance, operations, and customer success. High-impact actions that touch customers or money require your one-click approval.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <span className="inline-flex items-center gap-1.5 rounded-xl border border-emerald-200 bg-emerald-50/80 px-3 py-1.5 text-xs font-semibold text-emerald-700">
            <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
            <span>{employees.filter((e) => e.enabled).length} Agents Active</span>
          </span>
        </div>
      </header>

      {error && (
        <div className="rounded-2xl border border-rose-200 bg-rose-50/90 p-4 text-sm text-rose-800">
          {error}
        </div>
      )}

      {/* Grouped Agent Cards by Department */}
      <div className="space-y-8">
        {Object.entries(byDepartment).map(([department, list]) => {
          const theme = DEPARTMENT_THEMES[department.toLowerCase()] || {
            badge: "bg-slate-100 text-slate-700 border-slate-200",
            border: "hover:border-slate-300",
            bg: "from-slate-500/5 to-transparent",
            iconBg: "bg-slate-800 text-white",
            text: "text-slate-700",
          };

          return (
            <section key={department} className="space-y-3">
              <div className="flex items-center gap-2">
                <span
                  className={`rounded-full border px-2.5 py-0.5 text-xs font-bold uppercase tracking-wider ${theme.badge}`}
                >
                  {department} Department
                </span>
                <div className="h-px flex-1 bg-slate-200/80" />
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                {list.map((employee) => (
                  <Link
                    key={employee.key}
                    href={`/ai-employees/${employee.key}`}
                    className={`group relative overflow-hidden rounded-2xl border bg-white p-5 shadow-2xs transition-all ${
                      employee.enabled
                        ? `border-slate-200/80 ${theme.border} hover:shadow-md`
                        : "border-slate-200 opacity-60"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex items-center gap-3">
                        <div
                          className={`flex h-10 w-10 items-center justify-center rounded-xl font-bold shadow-sm ${theme.iconBg}`}
                        >
                          {employee.display_name ? employee.display_name[0] : "A"}
                        </div>
                        <div>
                          <p className="font-bold text-slate-900 group-hover:text-brand-600 transition">
                            {employee.display_name || employee.label}
                          </p>
                          <p className="text-xs text-slate-400 capitalize">
                            Specialist · {employee.department}
                          </p>
                        </div>
                      </div>

                      <div className="flex items-center gap-1.5">
                        {!employee.enabled ? (
                          <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium text-slate-500">
                            Inactive
                          </span>
                        ) : employee.autonomy_level === "cautious" ? (
                          <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 border border-amber-200 px-2.5 py-0.5 text-xs font-semibold text-amber-700">
                            <ShieldAlert className="h-3 w-3" />
                            <span>Confirms Actions</span>
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 border border-emerald-200 px-2.5 py-0.5 text-xs font-semibold text-emerald-700">
                            <ShieldCheck className="h-3 w-3" />
                            <span>Autonomous</span>
                          </span>
                        )}
                      </div>
                    </div>

                    <p className="mt-3 text-xs md:text-sm leading-relaxed text-slate-600">
                      {employee.description}
                    </p>

                    {employee.examples[0] && (
                      <div className="mt-4 rounded-xl bg-slate-50 p-2.5 border border-slate-100/80">
                        <p className="text-[11px] font-medium text-slate-400 uppercase tracking-wide">
                          Example Prompt
                        </p>
                        <p className="text-xs italic text-slate-600 mt-0.5">
                          &ldquo;{employee.examples[0]}&rdquo;
                        </p>
                      </div>
                    )}

                    <div className="mt-4 flex items-center justify-between text-xs font-semibold text-brand-600 pt-2 border-t border-slate-100">
                      <span>Configure Persona & Tools</span>
                      <ArrowRight className="h-3.5 w-3.5 group-hover:translate-x-0.5 transition" />
                    </div>
                  </Link>
                ))}
              </div>
            </section>
          );
        })}
      </div>

      {/* Recurring Sweeps Section */}
      <section className="rounded-2xl border border-slate-200/80 bg-white p-6 shadow-2xs">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <Clock className="h-4 w-4 text-brand-600" />
            <h2 className="text-base font-bold text-slate-900">
              Automated Recurring Duties & Sweeps
            </h2>
          </div>
          <span className="text-xs font-semibold text-emerald-600 bg-emerald-50 px-2.5 py-0.5 rounded-full border border-emerald-100">
            Zero AI Token Cost
          </span>
        </div>
        <p className="text-xs text-slate-500 mb-4">
          Pre-defined deterministic sweeps that monitor ledgers, unpaid invoices, and follow-up schedules automatically.
        </p>

        <div className="divide-y divide-slate-100 rounded-xl border border-slate-200/80 overflow-hidden">
          {Object.entries(duties).map(([key, duty]) => (
            <div
              key={key}
              className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-4 bg-white hover:bg-slate-50/60 transition"
            >
              <div>
                <p className="text-sm font-semibold text-slate-800">{duty.description}</p>
                <div className="flex items-center gap-2 mt-1">
                  <span className="inline-flex items-center gap-1 text-xs font-medium text-slate-500">
                    <Bot className="h-3 w-3 text-slate-400" />
                    <span className="capitalize">{duty.employee.replace(/_/g, " ")}</span>
                  </span>
                  <span className="text-slate-300">·</span>
                  <span className="rounded bg-slate-100 px-2 py-0.2 text-[11px] font-mono text-slate-600">
                    {duty.cadence}
                  </span>
                </div>
              </div>
              <button
                onClick={() => handleDuty(key, duty)}
                disabled={runningDuty === key}
                className="inline-flex items-center justify-center gap-1.5 rounded-xl bg-slate-900 hover:bg-slate-800 px-3.5 py-2 text-xs font-semibold text-white transition disabled:opacity-50 shadow-2xs shrink-0"
              >
                <Play className="h-3 w-3 fill-current" />
                <span>{runningDuty === key ? "Executing Sweep..." : "Run Sweep Now"}</span>
              </button>
            </div>
          ))}
        </div>
      </section>

      {/* Recent Activity Log */}
      {recent.length > 0 && (
        <section className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-bold text-slate-900 flex items-center gap-2">
              <Activity className="h-4 w-4 text-brand-600" />
              <span>Recent AI Operations & Approval Queue</span>
            </h2>
            <span className="text-xs text-slate-400">Showing last 5 executions</span>
          </div>
          <div className="space-y-3">
            {recent.map((run) => (
              <RunCard
                key={run.id}
                run={run}
                onChange={(updated) =>
                  setRecent((rs) => rs.map((r) => (r.id === updated.id ? updated : r)))
                }
              />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
