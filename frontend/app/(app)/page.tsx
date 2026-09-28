"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import Image from "next/image";
import {
  Users,
  FileSpreadsheet,
  Receipt,
  DollarSign,
  Bot,
  Sparkles,
  ArrowUpRight,
  TrendingUp,
  Plus,
  Mic,
  MessageSquare,
  ArrowRight,
  ShieldCheck,
  Zap,
  Activity,
  Calendar,
  Clock,
  Send,
} from "lucide-react";
import { api, Customer, Quotation, Invoice, AIEmployee } from "@/lib/api";
import { useAuth } from "@/components/AuthGuard";
import StatusBadge from "@/components/StatusBadge";

export default function DashboardPage() {
  const { user, company } = useAuth();
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [quotations, setQuotations] = useState<Quotation[]>([]);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [employees, setEmployees] = useState<AIEmployee[]>([]);
  const [loading, setLoading] = useState(true);
  const [promptInput, setPromptInput] = useState("");

  useEffect(() => {
    Promise.all([
      api.listCustomers().catch(() => []),
      api.listQuotations().catch(() => []),
      api.listInvoices().catch(() => []),
      api.listAiEmployees().catch(() => []),
    ]).then(([c, q, i, emp]) => {
      setCustomers(c);
      setQuotations(q);
      setInvoices(i);
      setEmployees(emp);
      setLoading(false);
    });
  }, []);

  const totalRevenue = invoices
    .filter((i) => i.status === "paid")
    .reduce((sum, i) => sum + i.total, 0);

  const outstanding = invoices
    .filter((i) => i.status !== "paid")
    .reduce((sum, i) => sum + (i.total - i.amount_paid), 0);

  const stats = [
    {
      label: "Total Customers",
      value: customers.length,
      change: "+12% this month",
      icon: Users,
      href: "/customers",
      color: "from-blue-500/10 to-indigo-500/5 text-blue-600 border-blue-100",
    },
    {
      label: "Active Quotations",
      value: quotations.length,
      change: `${quotations.filter((q) => q.status === "sent").length} awaiting approval`,
      icon: FileSpreadsheet,
      href: "/quotations",
      color: "from-amber-500/10 to-orange-500/5 text-amber-600 border-amber-100",
    },
    {
      label: "Paid Invoices",
      value: `$${totalRevenue.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`,
      change: `${invoices.filter((i) => i.status === "paid").length} cleared`,
      icon: Receipt,
      href: "/invoices",
      color: "from-emerald-500/10 to-teal-500/5 text-emerald-600 border-emerald-100",
    },
    {
      label: "Outstanding Balance",
      value: `$${outstanding.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`,
      change: `${invoices.filter((i) => i.status === "overdue").length} overdue`,
      icon: DollarSign,
      href: "/invoices",
      color: "from-rose-500/10 to-pink-500/5 text-rose-600 border-rose-100",
    },
  ];

  return (
    <div className="space-y-8">
      {/* Hero Welcome & Quick Dispatch */}
      <div className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-slate-950 via-slate-900 to-emerald-950 p-6 md:p-8 text-white shadow-2xl border border-emerald-900/30">
        <div className="absolute -right-20 -top-20 h-64 w-64 rounded-full bg-emerald-500/20 blur-3xl" />
        <div className="absolute -left-20 -bottom-20 h-64 w-64 rounded-full bg-indigo-500/20 blur-3xl" />

        <div className="relative z-10">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
            <div className="flex items-start gap-4">
              <div className="hidden sm:flex h-16 w-16 shrink-0 items-center justify-center rounded-2xl bg-slate-900/80 p-1.5 border border-emerald-500/40 shadow-lg shadow-emerald-900/30">
                <img src="/logo-3d.jpg" alt="3D Logo" className="h-full w-full rounded-xl object-cover" />
              </div>
              <div>
                <div className="inline-flex items-center gap-2 rounded-full bg-emerald-500/10 px-3 py-1 text-xs font-semibold text-emerald-300 backdrop-blur-md border border-emerald-500/20 mb-2">
                  <Sparkles className="h-3.5 w-3.5 text-emerald-400 animate-pulse" />
                  <span>AI_EMPLOYEE OS Enterprise Autonomous Engine</span>
                </div>
                <h1 className="text-2xl md:text-3xl font-extrabold tracking-tight">
                  Welcome back, {user.name ? user.name.split(" ")[0] : "Admin"}
                </h1>
                <p className="mt-1 text-sm text-slate-300 max-w-xl">
                  {company.name || "AI Employee OS"} is actively coordinating live WhatsApp chats, quotation drafting, financial syncing, and voice commands.
                </p>
              </div>
            </div>

            {/* Quick Action Buttons */}
            <div className="flex flex-wrap items-center gap-2.5">
              <Link
                href="/quotations/new"
                className="inline-flex items-center gap-2 rounded-xl bg-white px-4 py-2.5 text-xs font-semibold text-slate-900 shadow-md hover:bg-slate-100 transition"
              >
                <Plus className="h-3.5 w-3.5" />
                <span>New Quotation</span>
              </Link>
              <Link
                href="/voice"
                className="inline-flex items-center gap-2 rounded-xl bg-brand-600/90 hover:bg-brand-600 border border-brand-400/30 px-4 py-2.5 text-xs font-semibold text-white shadow-md transition"
              >
                <Mic className="h-3.5 w-3.5" />
                <span>Voice Command</span>
              </Link>
            </div>
          </div>

          {/* Natural Language AI Dispatch Bar */}
          <div className="mt-6 rounded-2xl bg-white/10 p-2 backdrop-blur-md border border-white/15">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                if (promptInput.trim()) {
                  window.location.href = `/ai-employees?dispatch=${encodeURIComponent(promptInput)}`;
                }
              }}
              className="flex items-center gap-2"
            >
              <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-brand-500 text-white shrink-0">
                <Bot className="h-5 w-5" />
              </div>
              <input
                type="text"
                value={promptInput}
                onChange={(e) => setPromptInput(e.target.value)}
                placeholder="Give an instruction to your AI team (e.g. 'Audit overdue invoices and prepare follow-ups' or 'Draft a sales quote for Acme Corp')..."
                className="flex-1 bg-transparent px-2 text-sm text-white placeholder-slate-400 outline-none"
              />
              <button
                type="submit"
                className="inline-flex items-center gap-1.5 rounded-xl bg-brand-500 hover:bg-brand-400 px-4 py-2 text-xs font-semibold text-white transition shadow-sm"
              >
                <span>Dispatch</span>
                <Send className="h-3 w-3" />
              </button>
            </form>
          </div>
        </div>
      </div>

      {/* KPI Stats Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {stats.map((s) => {
          const Icon = s.icon;
          return (
            <Link
              key={s.label}
              href={s.href}
              className="group relative overflow-hidden rounded-2xl border border-slate-200/80 bg-white p-5 shadow-2xs transition-all hover:border-brand-300 hover:shadow-md"
            >
              <div className="flex items-center justify-between">
                <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                  {s.label}
                </p>
                <div
                  className={`flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br border ${s.color}`}
                >
                  <Icon className="h-4.5 w-4.5" />
                </div>
              </div>
              <div className="mt-4 flex items-baseline justify-between">
                <p className="text-2xl font-bold tracking-tight text-slate-900">
                  {loading ? "…" : s.value}
                </p>
                <ArrowUpRight className="h-4 w-4 text-slate-300 group-hover:text-brand-600 transition" />
              </div>
              <p className="mt-1 text-xs font-medium text-slate-500 flex items-center gap-1">
                <span>{s.change}</span>
              </p>
            </Link>
          );
        })}
      </div>

      {/* AI Employees Fleet Overview */}
      <div className="rounded-2xl border border-slate-200/80 bg-white p-6 shadow-2xs">
        <div className="flex items-center justify-between mb-5">
          <div>
            <h2 className="text-base font-bold text-slate-900 flex items-center gap-2">
              <Bot className="h-4 w-4 text-brand-600" />
              <span>AI Employee Fleet</span>
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Autonomous specialized agents actively monitoring and executing operations
            </p>
          </div>
          <Link
            href="/ai-employees"
            className="inline-flex items-center gap-1 text-xs font-semibold text-brand-600 hover:text-brand-700 transition"
          >
            <span>View All Specialists</span>
            <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3.5">
          {employees.slice(0, 4).map((emp) => (
            <Link
              key={emp.key}
              href={`/ai-employees/${emp.key}`}
              className="group rounded-xl border border-slate-100 bg-slate-50/50 p-4 transition hover:border-brand-200 hover:bg-brand-50/20"
            >
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <div className="h-7 w-7 rounded-lg bg-white border border-slate-200 flex items-center justify-center text-xs font-bold text-slate-700 group-hover:bg-brand-600 group-hover:text-white transition shadow-2xs">
                    {emp.display_name ? emp.display_name[0] : "A"}
                  </div>
                  <div>
                    <p className="text-xs font-bold text-slate-800 leading-none">
                      {emp.display_name || emp.label}
                    </p>
                    <p className="text-[10px] text-slate-400 capitalize mt-0.5">
                      {emp.department}
                    </p>
                  </div>
                </div>
                <span className="flex h-2 w-2 rounded-full bg-emerald-500"></span>
              </div>
              <p className="text-xs text-slate-500 line-clamp-2 leading-relaxed">
                {emp.description}
              </p>
            </Link>
          ))}
        </div>
      </div>

      {/* Split Activity: Recent Invoices & Quick Tools */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Recent Invoices Table (2 cols) */}
        <div className="lg:col-span-2 rounded-2xl border border-slate-200/80 bg-white p-6 shadow-2xs">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-base font-bold text-slate-900">Recent Invoices</h2>
              <p className="text-xs text-slate-500">Latest billing and payment collection activity</p>
            </div>
            <Link
              href="/invoices"
              className="text-xs font-semibold text-brand-600 hover:text-brand-700"
            >
              View Invoices
            </Link>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50 text-slate-500 font-semibold border-y border-slate-100">
                <tr>
                  <th className="py-2.5 px-3">Invoice #</th>
                  <th className="py-2.5 px-3">Status</th>
                  <th className="py-2.5 px-3">Total</th>
                  <th className="py-2.5 px-3">Due Date</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {invoices.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="py-6 text-center text-slate-400">
                      No invoices recorded yet
                    </td>
                  </tr>
                ) : (
                  invoices.slice(0, 5).map((inv) => (
                    <tr key={inv.id} className="hover:bg-slate-50/50 transition">
                      <td className="py-3 px-3 font-medium text-slate-800">
                        <Link href={`/invoices/${inv.id}`} className="hover:underline font-mono">
                          {inv.number}
                        </Link>
                      </td>
                      <td className="py-3 px-3">
                        <StatusBadge status={inv.status} />
                      </td>
                      <td className="py-3 px-3 font-semibold text-slate-800">
                        ${inv.total.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                      </td>
                      <td className="py-3 px-3 text-slate-500">
                        {inv.due_date || "Upon Receipt"}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Quick Automation Launchpad (1 col) */}
        <div className="rounded-2xl border border-slate-200/80 bg-white p-6 shadow-2xs space-y-4">
          <div>
            <h2 className="text-base font-bold text-slate-900">Automation Hub</h2>
            <p className="text-xs text-slate-500">One-click operational triggers</p>
          </div>

          <div className="space-y-2.5">
            <Link
              href="/whatsapp"
              className="flex items-center gap-3 p-3 rounded-xl border border-slate-100 bg-slate-50/60 hover:bg-brand-50/40 hover:border-brand-200 transition group"
            >
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-100 text-emerald-700 shrink-0">
                <MessageSquare className="h-4 w-4" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-xs font-bold text-slate-800 group-hover:text-brand-700">
                  WhatsApp Campaigns
                </p>
                <p className="text-[11px] text-slate-500 truncate">
                  AI-driven quotation broadcasts
                </p>
              </div>
              <ArrowRight className="h-3.5 w-3.5 text-slate-400 group-hover:text-brand-600" />
            </Link>

            <Link
              href="/accounting"
              className="flex items-center gap-3 p-3 rounded-xl border border-slate-100 bg-slate-50/60 hover:bg-brand-50/40 hover:border-brand-200 transition group"
            >
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-100 text-blue-700 shrink-0">
                <DollarSign className="h-4 w-4" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-xs font-bold text-slate-800 group-hover:text-brand-700">
                  Accounting Reconcile
                </p>
                <p className="text-[11px] text-slate-500 truncate">
                  Sync ledger & invoice status
                </p>
              </div>
              <ArrowRight className="h-3.5 w-3.5 text-slate-400 group-hover:text-brand-600" />
            </Link>

            <Link
              href="/knowledge-base"
              className="flex items-center gap-3 p-3 rounded-xl border border-slate-100 bg-slate-50/60 hover:bg-brand-50/40 hover:border-brand-200 transition group"
            >
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-violet-100 text-violet-700 shrink-0">
                <Sparkles className="h-4 w-4" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-xs font-bold text-slate-800 group-hover:text-brand-700">
                  Knowledge Embeddings
                </p>
                <p className="text-[11px] text-slate-500 truncate">
                  Train AI on price lists & terms
                </p>
              </div>
              <ArrowRight className="h-3.5 w-3.5 text-slate-400 group-hover:text-brand-600" />
            </Link>
          </div>

          <div className="pt-2">
            <div className="rounded-xl bg-slate-900 p-3.5 text-white">
              <div className="flex items-center gap-2 mb-1">
                <ShieldCheck className="h-4 w-4 text-emerald-400" />
                <span className="text-xs font-bold">Multi-tenant Security</span>
              </div>
              <p className="text-[11px] text-slate-300 leading-relaxed">
                All AI actions, financial calculations, and customer data are fully isolated to {company.name}.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
