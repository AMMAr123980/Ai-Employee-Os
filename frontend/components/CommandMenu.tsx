"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Search,
  LayoutDashboard,
  Users,
  GitPullRequest,
  FileSpreadsheet,
  Receipt,
  CheckSquare,
  Clock,
  MessageSquare,
  Workflow,
  Mic,
  Video,
  Calendar,
  Bot,
  BookOpen,
  DollarSign,
  Mail,
  UserCheck,
  CreditCard,
  BarChart3,
  X,
  Sparkles,
  ArrowRight,
} from "lucide-react";

interface CommandItem {
  icon: any;
  label: string;
  category: string;
  href: string;
  badge?: string;
  keywords?: string[];
}

const commands: CommandItem[] = [
  { icon: LayoutDashboard, label: "Dashboard", category: "Navigation", href: "/", keywords: ["home", "overview", "stats"] },
  { icon: BarChart3, label: "Reports & Analytics", category: "Navigation", href: "/reports", keywords: ["analytics", "metrics", "revenue"] },
  { icon: Users, label: "Customers & Leads", category: "CRM & Sales", href: "/customers", keywords: ["contacts", "clients", "accounts"] },
  { icon: GitPullRequest, label: "Sales Pipeline", category: "CRM & Sales", href: "/pipeline", keywords: ["deals", "stages", "kanban"] },
  { icon: FileSpreadsheet, label: "Quotations & Estimates", category: "CRM & Sales", href: "/quotations", keywords: ["quotes", "proposals"] },
  { icon: Receipt, label: "Invoices & Billing", category: "Financials", href: "/invoices", keywords: ["invoicing", "payments", "bills"] },
  { icon: DollarSign, label: "Accounting Sync", category: "Financials", href: "/accounting", keywords: ["xero", "quickbooks", "ledger"] },
  { icon: CreditCard, label: "Billing & Plans", category: "Admin", href: "/billing", keywords: ["subscription", "credits", "stripe"] },
  { icon: Bot, label: "AI Employees Fleet", category: "AI Agents", href: "/ai-employees", badge: "AI Core", keywords: ["agents", "roster", "assistants", "duties"] },
  { icon: Mail, label: "Email Assistant", category: "Communications", href: "/email-assistant", keywords: ["inbox", "drafts", "gmail"] },
  { icon: MessageSquare, label: "WhatsApp Marketing", category: "Communications", href: "/whatsapp", keywords: ["messaging", "chat", "broadcast"] },
  { icon: Mic, label: "Voice Assistant & Calls", category: "Communications", href: "/voice", badge: "Voice", keywords: ["speech", "audio", "recording"] },
  { icon: Video, label: "Meeting AI & Summaries", category: "Communications", href: "/meetings", keywords: ["zoom", "meet", "transcript"] },
  { icon: Calendar, label: "Calendar & Schedule", category: "Productivity", href: "/calendar", keywords: ["events", "bookings", "agenda"] },
  { icon: CheckSquare, label: "Tasks & To-Dos", category: "Productivity", href: "/tasks", keywords: ["todos", "actions"] },
  { icon: Clock, label: "Follow-ups Automation", category: "Productivity", href: "/follow-ups", keywords: ["reminders", "cadence"] },
  { icon: Workflow, label: "Workflow Builder", category: "Automation", href: "/workflows", keywords: ["triggers", "automation", "flows"] },
  { icon: BookOpen, label: "Company Knowledge Base", category: "AI Agents", href: "/knowledge-base", keywords: ["docs", "rag", "embeddings", "training"] },
  { icon: UserCheck, label: "Team & Permissions", category: "Admin", href: "/team", keywords: ["members", "roles", "users"] },
];

export default function CommandMenu({
  isOpen,
  onClose,
}: {
  isOpen: boolean;
  onClose: () => void;
}) {
  const router = useRouter();
  const [search, setSearch] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        if (isOpen) {
          onClose();
        } else {
          // Open
          setSearch("");
        }
      }
      if (e.key === "Escape" && isOpen) {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  const filtered = commands.filter((cmd) => {
    if (!search.trim()) return true;
    const query = search.toLowerCase();
    return (
      cmd.label.toLowerCase().includes(query) ||
      cmd.category.toLowerCase().includes(query) ||
      cmd.keywords?.some((k) => k.includes(query))
    );
  });

  useEffect(() => {
    setSelectedIndex(0);
  }, [search]);

  const handleSelect = (href: string) => {
    router.push(href);
    onClose();
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-20 bg-slate-900/40 backdrop-blur-sm transition-opacity animate-in fade-in duration-150">
      <div
        className="w-full max-w-xl overflow-hidden rounded-2xl bg-white shadow-2xl border border-slate-200/80 transition-all scale-100"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Search Input Bar */}
        <div className="flex items-center gap-3 border-b border-slate-100 px-4 py-3.5">
          <Search className="h-5 w-5 text-slate-400 shrink-0" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Type a command or search tools, AI agents, documents..."
            className="flex-1 bg-transparent text-sm font-medium text-slate-800 placeholder-slate-400 outline-none"
            autoFocus
          />
          <button
            onClick={onClose}
            className="rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600 transition"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Quick Suggestion / AI Hint */}
        <div className="flex items-center justify-between bg-brand-50/60 px-4 py-2 text-xs text-brand-700 border-b border-brand-100/40">
          <div className="flex items-center gap-1.5 font-medium">
            <Sparkles className="h-3.5 w-3.5 text-brand-600" />
            <span>AI Command Palette</span>
          </div>
          <div className="flex items-center gap-2 text-[11px] text-slate-400">
            <span>Navigate with <kbd className="rounded bg-white px-1.5 py-0.5 border border-slate-200 shadow-2xs font-mono text-slate-600">↑</kbd> <kbd className="rounded bg-white px-1.5 py-0.5 border border-slate-200 shadow-2xs font-mono text-slate-600">↓</kbd></span>
            <span>Select with <kbd className="rounded bg-white px-1.5 py-0.5 border border-slate-200 shadow-2xs font-mono text-slate-600">↵</kbd></span>
          </div>
        </div>

        {/* Command List */}
        <div className="max-h-80 overflow-y-auto p-2 space-y-1">
          {filtered.length === 0 ? (
            <div className="py-8 text-center text-sm text-slate-400">
              No matching commands found for &ldquo;{search}&rdquo;
            </div>
          ) : (
            filtered.map((cmd, idx) => {
              const Icon = cmd.icon;
              const isSelected = idx === selectedIndex;
              return (
                <button
                  key={cmd.href + cmd.label}
                  onClick={() => handleSelect(cmd.href)}
                  onMouseEnter={() => setSelectedIndex(idx)}
                  className={`flex w-full items-center justify-between rounded-xl px-3 py-2.5 text-left text-sm transition ${
                    isSelected
                      ? "bg-slate-100 text-slate-900"
                      : "text-slate-600 hover:bg-slate-50"
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <div
                      className={`flex h-8 w-8 items-center justify-center rounded-lg ${
                        isSelected
                          ? "bg-brand-600 text-white shadow-sm"
                          : "bg-slate-100 text-slate-500"
                      }`}
                    >
                      <Icon className="h-4 w-4" />
                    </div>
                    <div>
                      <p className="font-medium text-slate-800">{cmd.label}</p>
                      <p className="text-xs text-slate-400">{cmd.category}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {cmd.badge && (
                      <span className="rounded-full bg-brand-50 px-2 py-0.5 text-[10px] font-semibold text-brand-700">
                        {cmd.badge}
                      </span>
                    )}
                    {isSelected && <ArrowRight className="h-3.5 w-3.5 text-slate-400" />}
                  </div>
                </button>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}
