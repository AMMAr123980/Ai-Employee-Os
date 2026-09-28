"use client";

import { useState } from "react";
import { usePathname } from "next/navigation";
import Link from "next/link";
import {
  Search,
  Sparkles,
  Bell,
  Plus,
  Mic,
  ChevronRight,
  ShieldCheck,
  Zap,
} from "lucide-react";
import { useAuth } from "@/components/AuthGuard";
import CommandMenu from "./CommandMenu";

const routeNames: Record<string, string> = {
  "": "Dashboard",
  "reports": "Reports & Analytics",
  "customers": "Customers & Leads",
  "pipeline": "Sales Pipeline",
  "quotations": "Quotations",
  "invoices": "Invoices",
  "tasks": "Tasks & Actions",
  "follow-ups": "Follow-ups",
  "whatsapp": "WhatsApp Marketing",
  "workflows": "Workflows",
  "voice": "Voice Assistant",
  "meetings": "Meeting Intelligence",
  "calendar": "Calendar & Bookings",
  "ai-employees": "AI Employee Fleet",
  "knowledge-base": "Company Knowledge Base",
  "accounting": "Accounting Sync",
  "email-assistant": "Email Assistant",
  "team": "Team & Access",
  "billing": "Billing & Subscriptions",
};

export default function Header() {
  const pathname = usePathname();
  const { user, company } = useAuth();
  const [commandOpen, setCommandOpen] = useState(false);

  // Extract path segments for breadcrumbs
  const segments = pathname.split("/").filter(Boolean);
  const currentTitle = segments.length > 0 ? (routeNames[segments[0]] || segments[0]) : "Dashboard";

  return (
    <>
      <header className="sticky top-0 z-30 flex h-16 w-full items-center justify-between border-b border-slate-200/80 bg-white/85 px-6 backdrop-blur-md shadow-xs">
        {/* Breadcrumb / Title Area */}
        <div className="flex items-center gap-2.5 text-sm">
          <Link
            href="/"
            className="flex items-center gap-2 font-medium text-slate-500 hover:text-slate-900 transition"
          >
            <span className="flex h-6 w-6 items-center justify-center rounded-lg bg-emerald-950 p-0.5">
              <img src="/logo-3d.jpg" alt="Logo" className="h-full w-full rounded object-cover" />
            </span>
            <span className="font-extrabold text-slate-900 tracking-tight text-xs">AI_EMPLOYEE <span className="text-emerald-600 font-black">OS</span></span>
          </Link>
          <ChevronRight className="h-4 w-4 text-slate-300" />
          <span className="font-semibold text-slate-800">{currentTitle}</span>
          {segments.length > 1 && (
            <>
              <ChevronRight className="h-4 w-4 text-slate-300" />
              <span className="rounded-md bg-slate-100 px-2 py-0.5 text-xs font-mono font-medium text-slate-600 border border-slate-200/60">
                {segments[1]}
              </span>
            </>
          )}
        </div>

        {/* Middle / Right Actions */}
        <div className="flex items-center gap-3">
          {/* Spotlight Search Trigger */}
          <button
            onClick={() => setCommandOpen(true)}
            className="flex items-center gap-3 rounded-xl border border-slate-200/90 bg-slate-50/80 px-3.5 py-1.5 text-xs text-slate-500 shadow-2xs transition hover:border-emerald-300 hover:bg-white hover:text-slate-900"
          >
            <Search className="h-3.5 w-3.5 text-emerald-600" />
            <span className="hidden sm:inline">Search AI tools & actions...</span>
            <kbd className="hidden sm:inline-flex items-center gap-0.5 rounded border border-slate-200 bg-white px-1.5 py-0.5 font-mono text-[10px] font-semibold text-slate-500 shadow-2xs">
              ⌘K
            </kbd>
          </button>

          {/* AI Fleet Status Badge */}
          <div className="hidden lg:flex items-center gap-2 rounded-full border border-emerald-200/70 bg-gradient-to-r from-emerald-50 to-teal-50 px-3 py-1 text-xs font-semibold text-emerald-800 shadow-2xs">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500"></span>
            </span>
            <span className="text-[11px]">4 AI Fleet Active</span>
          </div>

          {/* Quick Voice Assistant Trigger */}
          <Link
            href="/voice"
            className="flex items-center gap-1.5 rounded-xl border border-indigo-200/80 bg-indigo-50/80 px-3 py-1.5 text-xs font-semibold text-indigo-700 hover:bg-indigo-100 transition shadow-2xs"
            title="Launch Voice Agent"
          >
            <Mic className="h-3.5 w-3.5 text-indigo-600 animate-pulse" />
            <span className="hidden md:inline">Voice Agent</span>
          </Link>

          {/* Quick New Action Button */}
          <Link
            href="/quotations/new"
            className="flex items-center gap-1.5 rounded-xl bg-gradient-to-r from-slate-900 via-slate-800 to-emerald-950 px-3.5 py-1.5 text-xs font-semibold text-white shadow-md hover:shadow-lg transition"
          >
            <Plus className="h-3.5 w-3.5 text-emerald-400" />
            <span>New Quote</span>
          </Link>

          {/* Company / User Avatar Pill */}
          <div className="flex items-center gap-2 pl-2 border-l border-slate-200">
            <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-gradient-to-tr from-emerald-600 via-teal-600 to-indigo-600 text-xs font-bold text-white shadow-md shadow-emerald-600/20">
              {user.name ? user.name.slice(0, 2).toUpperCase() : "US"}
            </div>
          </div>
        </div>
      </header>

      {/* Global Command Menu Modal */}
      <CommandMenu isOpen={commandOpen} onClose={() => setCommandOpen(false)} />
    </>
  );
}
