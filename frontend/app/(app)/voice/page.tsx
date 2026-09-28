"use client";

/**
 * The voice command screen.
 *
 * The flow the backend was shaped around:
 *
 *   hold to talk -> upload -> poll while it transcribes and plans
 *     -> internal steps have already run by the time it comes back
 *     -> anything customer-facing waits in the sheet for a tap
 *
 * Quota is read up front rather than discovered on submit, so a company that's
 * out of AI requests sees a disabled button with a reason instead of an error
 * after speaking for thirty seconds.
 */
import { useCallback, useEffect, useState } from "react";
import MicButton from "@/components/voice/MicButton";
import VoiceHistory from "@/components/voice/VoiceHistory";
import VoicePlanSheet from "@/components/voice/VoicePlanSheet";
import { IntentCatalog, QuotaError, Usage, VoiceCommand, api } from "@/lib/api";

export default function VoicePage() {
  const [command, setCommand] = useState<VoiceCommand | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [usage, setUsage] = useState<Usage | null>(null);
  const [catalog, setCatalog] = useState<IntentCatalog | null>(null);
  const [typed, setTyped] = useState("");
  const [historyToken, setHistoryToken] = useState(0);

  const refresh = useCallback(() => {
    api.getUsage().then(setUsage).catch(() => undefined);
    setHistoryToken((value) => value + 1);
  }, []);

  useEffect(() => {
    api.getVoiceCatalog().then(setCatalog).catch(() => undefined);
    refresh();
  }, [refresh]);

  const requests = usage?.metrics?.ai_requests;
  const outOfQuota = Boolean(
    requests && !requests.unlimited && requests.limit !== null && requests.used >= requests.limit
  );

  const run = useCallback(
    async (submit: () => Promise<VoiceCommand>) => {
      setError(null);
      setBusy(true);
      try {
        const created = await submit();
        setCommand(created);
        setCommand(await api.pollVoiceCommand(created.id, setCommand));
      } catch (cause) {
        setError(
          cause instanceof QuotaError
            ? `This month's allowance for ${cause.detail.metric.replace(/_/g, " ")} is used up (${Math.round(
                cause.detail.used
              )}/${cause.detail.limit}). Upgrade the plan or wait for the reset.`
            : cause instanceof Error
            ? cause.message
            : "Something went wrong."
        );
      } finally {
        setBusy(false);
        refresh();
      }
    },
    [refresh]
  );

  async function handleConfirm(stepIds: string[]) {
    if (!command) return;
    setBusy(true);
    try {
      setCommand(await api.confirmVoiceCommand(command.id, { only_steps: stepIds }));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Couldn't run that.");
    } finally {
      setBusy(false);
      refresh();
    }
  }

  async function handleCancel() {
    if (!command) return;
    setBusy(true);
    try {
      setCommand(await api.cancelVoiceCommand(command.id));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Couldn't discard that.");
    } finally {
      setBusy(false);
      refresh();
    }
  }

  const examples = catalog
    ? Object.values(catalog.intents)
        .map((intent) => intent.example)
        .filter((example): example is string => Boolean(example))
    : [];

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6">
      <header>
        <h1 className="text-xl font-semibold">Voice commands</h1>
        <p className="text-sm text-slate-500">
          Say what you want done. One sentence can hold several actions — anything that reaches a
          customer or moves money waits for your approval.
        </p>
      </header>

      <section className="flex flex-col items-center gap-4 rounded-xl border border-slate-200 bg-white p-6">
        <MicButton
          onRecorded={(blob, filename, transcript) => void run(() => api.submitVoiceRecording(blob, filename, transcript))}
          disabled={busy || outOfQuota}
          disabledReason={outOfQuota ? "You're out of AI requests this month" : undefined}
        />

        <div className="flex w-full gap-2">
          <input
            value={typed}
            onChange={(event) => setTyped(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && typed.trim() && !busy) {
                const text = typed.trim();
                setTyped("");
                void run(() => api.submitTextCommand(text));
              }
            }}
            placeholder="…or type it"
            className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm"
          />
          <button
            disabled={busy || !typed.trim()}
            onClick={() => {
              const text = typed.trim();
              setTyped("");
              void run(() => api.submitTextCommand(text, true));
            }}
            title="Show the plan without running anything"
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-700 disabled:opacity-40"
          >
            Preview
          </button>
        </div>

        {examples.length > 0 && !command && (
          <div className="w-full">
            <p className="text-xs uppercase tracking-wide text-slate-400">Try saying</p>
            <ul className="mt-1 space-y-1">
              {examples.slice(0, 5).map((example) => (
                <li key={example} className="text-sm text-slate-600">
                  &ldquo;{example}&rdquo;
                </li>
              ))}
            </ul>
          </div>
        )}

        {usage && requests && (
          <p className="w-full text-xs text-slate-500">
            {requests.unlimited
              ? `${Math.round(requests.used)} AI requests this month on the ${usage.plan} plan (unlimited).`
              : `${Math.round(requests.used)} of ${requests.limit} AI requests used this month on the ${usage.plan} plan.`}
          </p>
        )}
        {error && <p className="w-full rounded bg-red-50 p-2 text-sm text-red-700">{error}</p>}
      </section>

      {command && (
        <VoicePlanSheet
          command={command}
          busy={busy}
          onConfirm={handleConfirm}
          onCancel={handleCancel}
          onClose={() => setCommand(null)}
        />
      )}

      <section className="rounded-xl border border-slate-200 bg-white">
        <h2 className="border-b border-slate-100 px-4 py-3 text-sm font-medium text-slate-700">
          Recent commands
        </h2>
        <VoiceHistory refreshToken={historyToken} onOpen={setCommand} />
      </section>
    </div>
  );
}
