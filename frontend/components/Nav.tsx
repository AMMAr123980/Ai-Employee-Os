"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import Logo from "@/components/Logo";
import {
  LayoutDashboard,
  Bot,
  Workflow,
  GitPullRequest,
  FileSpreadsheet,
  Receipt,
  Users,
  Mail,
  MessageSquare,
  Mic,
  Video,
  Calendar,
  CheckSquare,
  Clock,
  BookOpen,
  DollarSign,
  BarChart3,
  UserCheck,
  CreditCard,
  LogOut,
  Sparkles,
  Building2,
  ChevronDown,
} from "lucide-react";
import { useAuth } from "@/components/AuthGuard";
import { logout } from "@/lib/auth";

interface NavGroup {
  label: string;
  items: {
    href: string;
    label: string;
    icon: any;
    badge?: string;
  }[];
}

const navGroups: NavGroup[] = [
  {
    label: "Core Hub",
    items: [
      { href: "/", label: "Dashboard", icon: LayoutDashboard },
      { href: "/ai-employees", label: "AI Employees", icon: Bot, badge: "Fleet" },
      { href: "/workflows", label: "Workflows", icon: Workflow },
    ],
  },
  {
    label: "Sales & CRM",
    items: [
      { href: "/pipeline", label: "Pipeline", icon: GitPullRequest },
      { href: "/quotations", label: "Quotations", icon: FileSpreadsheet },
      { href: "/invoices", label: "Invoices", icon: Receipt },
      { href: "/customers", label: "Customers", icon: Users },
    ],
  },
  {
    label: "Communications",
    items: [
      { href: "/email-assistant", label: "Email Assistant", icon: Mail },
      { href: "/whatsapp", label: "WhatsApp", icon: MessageSquare },
      { href: "/voice", label: "Voice Agent", icon: Mic, badge: "Live" },
      { href: "/meetings", label: "Meetings", icon: Video },
    ],
  },
  {
    label: "Back Office & Intel",
    items: [
      { href: "/calendar", label: "Calendar", icon: Calendar },
      { href: "/tasks", label: "Tasks", icon: CheckSquare },
      { href: "/follow-ups", label: "Follow-ups", icon: Clock },
      { href: "/knowledge-base", label: "Knowledge Base", icon: BookOpen },
      { href: "/accounting", label: "Accounting", icon: DollarSign },
      { href: "/reports", label: "Reports & Analytics", icon: BarChart3 },
    ],
  },
  {
    label: "Admin",
    items: [
      { href: "/team", label: "Team", icon: UserCheck },
      { href: "/billing", label: "Billing & Plans", icon: CreditCard },
    ],
  },
];

export default function Nav() {
  const pathname = usePathname();
  const { user, company } = useAuth();

  return (
    <aside className="w-64 shrink-0 border-r border-slate-200/80 bg-white flex flex-col h-screen sticky top-0 shadow-xs">
      {/* Workspace Brand Header */}
      <div className="p-4 border-b border-slate-200/80 bg-gradient-to-b from-slate-900/5 via-slate-50/50 to-white">
        <Logo size="md" showText={true} />
        <div className="mt-3 flex items-center justify-between px-2.5 py-1.5 rounded-xl bg-gradient-to-r from-emerald-950 via-slate-900 to-cyan-950 border border-emerald-500/30 text-[10px] font-semibold text-emerald-300 shadow-md">
          <span className="flex items-center gap-1.5 truncate">
            <span className="h-2 w-2 rounded-full bg-emerald-400 animate-ping"></span>
            <span className="truncate">{company.name || "AI Employee OS Global"}</span>
          </span>
          <span className="bg-emerald-500 text-slate-950 text-[9px] px-2 py-0.5 rounded-full font-black uppercase tracking-wider shrink-0 shadow-xs">Enterprise</span>
        </div>
      </div>

      {/* Navigation Scrollable Area */}
      <div className="flex-1 overflow-y-auto px-3 py-4 space-y-6 scrollbar-none">
        {navGroups.map((group) => (
          <div key={group.label} className="space-y-1">
            <p className="px-3 text-[10px] font-extrabold uppercase tracking-widest text-slate-400">
              {group.label}
            </p>
            <div className="mt-1 space-y-1">
              {group.items.map((item) => {
                const Icon = item.icon;
                const active = pathname === item.href || (item.href !== "/" && pathname.startsWith(item.href));
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={`group relative flex items-center justify-between rounded-xl px-3 py-2.5 text-xs transition-all duration-200 ${
                      active
                        ? "bg-gradient-to-r from-emerald-50 to-teal-50/60 text-emerald-950 font-bold border-l-3 border-emerald-600 shadow-xs"
                        : "text-slate-600 font-medium hover:bg-slate-100/70 hover:text-slate-900"
                    }`}
                  >
                    <div className="flex items-center gap-2.5">
                      <div className={`p-1 rounded-lg transition-colors ${active ? "bg-emerald-600 text-white shadow-xs" : "bg-slate-100 text-slate-500 group-hover:bg-slate-200 group-hover:text-slate-800"}`}>
                        <Icon className="h-3.5 w-3.5" />
                      </div>
                      <span className="tracking-tight">{item.label}</span>
                    </div>
                    {item.badge && (
                      <span
                        className={`rounded-full px-2 py-0.5 text-[9px] font-extrabold uppercase tracking-wider ${
                          item.badge === "Live"
                            ? "bg-rose-500 text-white shadow-xs animate-pulse"
                            : "bg-emerald-100 text-emerald-800 border border-emerald-200/60"
                        }`}
                      >
                        {item.badge}
                      </span>
                    )}
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      {/* User Profile & Logout Bottom Box */}
      <div className="p-3 border-t border-slate-100 bg-slate-50/50">
        <div className="flex items-center justify-between gap-2 p-1.5 rounded-xl bg-white border border-slate-200/70 shadow-2xs">
          <div className="flex items-center gap-2 min-w-0">
            <div className="h-7 w-7 rounded-lg bg-slate-800 text-white font-semibold text-xs flex items-center justify-center shrink-0">
              {user.name ? user.name[0].toUpperCase() : "U"}
            </div>
            <div className="min-w-0">
              <p className="text-xs font-medium text-slate-800 truncate leading-tight">
                {user.name || user.email}
              </p>
              <p className="text-[10px] text-slate-400 truncate leading-tight">
                {user.email}
              </p>
            </div>
          </div>
          <button
            onClick={logout}
            title="Log out"
            className="p-1.5 rounded-lg text-slate-400 hover:bg-rose-50 hover:text-rose-600 transition shrink-0"
          >
            <LogOut className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    </aside>
  );
}
