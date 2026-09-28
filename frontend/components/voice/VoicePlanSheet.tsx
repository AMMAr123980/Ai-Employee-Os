"use client";

/**
 * The confirmation sheet for a plan.
 *
 * A plan can hold several actions and they aren't equally risky, so this shows
 * the steps in execution order, marks what already ran (the internal ones run
 * before this appears), and lets you approve a subset — "yes to the quotation,
 * no to the email" — without re-recording the whole thing.
 *
 * Each row shows the sentence naming the values that will be written, not the
 * intent name: "Send email" tells you nothing about which address is about to
 * receive what.
 */
import { useMemo, useState } from "react";
import { VoiceCommand, VoiceStep } from "@/lib/api";

const STATUS_LABEL: Record<string, string> = {
  executed: "Done",
  failed: "Failed",
  cancelled: "Skipped",
  skipped: "Skipped",
  pending: "Waiting for you",
};

function stepTitle(step: VoiceStep): string {
  return step.summary?.trim() || step.intent.replace(/_/g, " ");
}

function ResultLine({ step }: { step: VoiceStep }) {
  const result = step.result;
  if (!result) return null;

  // Read-only steps are the answer, not a receipt, so they're worth rendering
  // in full rather than as a status line.
  if (step.read_only) {
    return (
      <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap rounded bg-slate-50 p-2 text-xs text-slate-700">
        {JSON.stringify(result, null, 2)}
      </pre>
    );
  }

  const bits: string[] = [];
  if (result.quotation_number) bits.push(String(result.quotation_number));
  if (result.invoice_number) bits.push(String(result.invoice_number));
  if (result.task_id && result.due) bits.push(`due ${result.due}`);
  if (result.sent === false && result.error) bits.push(`not sent: ${result.error}`);
  if (result.sent === true) bits.push(`sent to ${result.to}`);
  if (result.needs_pricing?.length) bits.push(`needs pricing: ${result.needs_pricing.join(", ")}`);

  return bits.length ? <p className="mt-1 text-xs text-slate-500">{bits.join(" · ")}</p> : null;
}

export default function VoicePlanSheet({
  command,
  busy,
  onConfirm,
  onCancel,
  onClose,
}: {
  command: VoiceCommand;
  busy?: boolean;
  onConfirm: (stepIds: string[]) => void;
  onCancel: () => void;
  onClose: () => void;
}) {
  const pending = useMemo(
    () => command.steps.filter((s) => s.status === "pending" && s.requires_confirmation),
    [command.steps]
  );
  const [selected, setSelected] = useState<string[]>(() => pending.map((s) => s.id));

  const toggle = (id: string) =>
    setSelected((current) =>
      current.includes(id) ? current.filter((value) => value !== id) : [...current, id]
    );

  const awaiting = command.status === "awaiting_confirmation";
  const working = command.status === "queued" || command.status === "processing";

  const speakText = (text: string) => {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 1.0;
    window.speechSynthesis.speak(utterance);
  };

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="text-xs uppercase tracking-wide text-slate-400">You said</p>
          <p className="mt-1 text-sm italic text-slate-900">
            {command.transcript || (working ? "Listening…" : "(nothing was picked up)")}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {command.summary && (
            <button
              onClick={() => speakText(command.summary || "")}
              title="Speak Response"
              className="inline-flex items-center gap-1 rounded px-2.5 py-1 text-xs font-medium bg-brand-50 text-brand-700 hover:bg-brand-100 transition"
            >
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.536 8.464a5 5 0 010 7.072m2.828-9.9a9 9 0 010 12.728M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707C10.923 3.663 12 4.109 12 5v14c0 .891-1.077 1.337-1.707.707L5.586 15z" />
              </svg>
              <span>Listen</span>
            </button>
          )}
          <button
            onClick={onClose}
            className="shrink-0 rounded px-2 py-1 text-sm text-slate-500 hover:bg-slate-100"
          >
            Close
          </button>
        </div>
      </div>

      {command.summary && <p className="mt-3 text-sm text-slate-700">{command.summary}</p>}
      {working && <p className="mt-3 text-sm text-slate-500">Working on it…</p>}

      {command.steps.length > 0 && (
        <ul className="mt-3">
          {command.steps.map((step) => {
            const selectable = step.status === "pending" && step.requires_confirmation;
            return (
              <li key={step.id} className="flex gap-3 border-b border-slate-100 py-3 last:border-0">
                <div className="pt-1">
                  {selectable ? (
                    <input
                      type="checkbox"
                      checked={selected.includes(step.id)}
                      onChange={() => toggle(step.id)}
                      className="h-4 w-4 rounded border-slate-300"
                      aria-label={`Include: ${stepTitle(step)}`}
                    />
                  ) : (
                    <span
                      aria-hidden
                      className={`block h-2 w-2 translate-y-1 rounded-full ${
                        step.status === "executed"
                          ? "bg-emerald-500"
                          : step.status === "failed"
                          ? "bg-red-500"
                          : "bg-slate-300"
                      }`}
                    />
                  )}
                </div>

                <div className="min-w-0 flex-1">
                  <p className="text-sm text-slate-900">{stepTitle(step)}</p>
                  {step.missing_info.length > 0 && (
                    <p className="mt-1 text-xs text-amber-700">
                      Missing: {step.missing_info.join(", ")} — fill these in before running it.
                    </p>
                  )}
                  {step.error && <p className="mt-1 text-xs text-red-600">{step.error}</p>}
                  {typeof step.confidence === "number" &&
                    step.confidence < 0.6 &&
                    step.status === "pending" && (
                      <p className="mt-1 text-xs text-slate-500">
                        Low confidence — check the details before approving.
                      </p>
                    )}
                  <ResultLine step={step} />
                </div>

                <span className="shrink-0 text-xs text-slate-500">
                  {STATUS_LABEL[step.status] ?? step.status}
                </span>
              </li>
            );
          })}
        </ul>
      )}

      {command.error && (
        <p className="mt-3 rounded bg-red-50 p-2 text-sm text-red-700">{command.error}</p>
      )}

      {awaiting && pending.length > 0 && (
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <button
            disabled={busy || selected.length === 0}
            onClick={() => onConfirm(selected)}
            className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-40"
          >
            {selected.length === pending.length
              ? pending.length === 1
                ? "Run it"
                : `Run all ${pending.length}`
              : `Run ${selected.length} of ${pending.length}`}
          </button>
          <button
            disabled={busy}
            onClick={onCancel}
            className="rounded-lg border border-slate-300 px-4 py-2 text-sm text-slate-700 disabled:opacity-40"
          >
            Discard
          </button>
        </div>
      )}
    </div>
  );
}
