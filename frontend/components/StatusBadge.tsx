import { CheckCircle2, Clock, AlertCircle, FileText, Send, XCircle } from "lucide-react";

interface StatusConfig {
  bg: string;
  text: string;
  border: string;
  dot: string;
  icon?: any;
}

const STATUS_MAP: Record<string, StatusConfig> = {
  draft: {
    bg: "bg-slate-50",
    text: "text-slate-700",
    border: "border-slate-200",
    dot: "bg-slate-400",
    icon: FileText,
  },
  sent: {
    bg: "bg-blue-50/80",
    text: "text-blue-700",
    border: "border-blue-200/60",
    dot: "bg-blue-500",
    icon: Send,
  },
  approved: {
    bg: "bg-emerald-50/80",
    text: "text-emerald-700",
    border: "border-emerald-200/60",
    dot: "bg-emerald-500",
    icon: CheckCircle2,
  },
  rejected: {
    bg: "bg-rose-50/80",
    text: "text-rose-700",
    border: "border-rose-200/60",
    dot: "bg-rose-500",
    icon: XCircle,
  },
  converted: {
    bg: "bg-purple-50/80",
    text: "text-purple-700",
    border: "border-purple-200/60",
    dot: "bg-purple-500",
  },
  unpaid: {
    bg: "bg-amber-50/80",
    text: "text-amber-700",
    border: "border-amber-200/60",
    dot: "bg-amber-500",
    icon: Clock,
  },
  partially_paid: {
    bg: "bg-indigo-50/80",
    text: "text-indigo-700",
    border: "border-indigo-200/60",
    dot: "bg-indigo-500",
  },
  paid: {
    bg: "bg-emerald-50/80",
    text: "text-emerald-700",
    border: "border-emerald-200/60",
    dot: "bg-emerald-500",
    icon: CheckCircle2,
  },
  overdue: {
    bg: "bg-rose-50/80",
    text: "text-rose-700",
    border: "border-rose-200/60",
    dot: "bg-rose-500 animate-pulse",
    icon: AlertCircle,
  },
};

export default function StatusBadge({ status }: { status: string }) {
  const config = STATUS_MAP[status] || {
    bg: "bg-slate-50",
    text: "text-slate-700",
    border: "border-slate-200",
    dot: "bg-slate-400",
  };

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium capitalize tracking-wide shadow-2xs ${config.bg} ${config.text} ${config.border}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${config.dot}`} />
      <span>{status.replace(/_/g, " ")}</span>
    </span>
  );
}
