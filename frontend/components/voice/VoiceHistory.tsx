"use client";

/**
 * Every command that's come in — what was said, what the system decided that
 * meant, what it did, and the original recording while it's still inside its
 * retention window.
 *
 * The audio player is the part that makes this an audit trail rather than a
 * feed: if someone disputes "you told it to move Acme to lost", a transcript
 * the same AI produced isn't evidence.
 */
import { useEffect, useState } from "react";
import { VoiceCommand, api } from "@/lib/api";

const TONE: Record<string, string> = {
  executed: "bg-emerald-50 text-emerald-700",
  partially_executed: "bg-amber-50 text-amber-700",
  awaiting_confirmation: "bg-brand-50 text-brand-700",
  failed: "bg-red-50 text-red-700",
  cancelled: "bg-slate-100 text-slate-600",
  no_action: "bg-slate-100 text-slate-600",
  queued: "bg-slate-100 text-slate-600",
  processing: "bg-slate-100 text-slate-600",
  transcribed: "bg-slate-100 text-slate-600",
};

const LABEL: Record<string, string> = {
  executed: "Done",
  partially_executed: "Partly done",
  awaiting_confirmation: "Waiting for approval",
  failed: "Failed",
  cancelled: "Discarded",
  no_action: "No action taken",
  queued: "Queued",
  processing: "Working on it",
  transcribed: "Transcribed",
};

function Row({
  command,
  onOpen,
}: {
  command: VoiceCommand;
  onOpen: (command: VoiceCommand) => void;
}) {
  const [audio, setAudio] = useState<string | null>(null);
  const [audioError, setAudioError] = useState<string | null>(null);
  const done = command.steps.filter((s) => s.status === "executed").length;

  return (
    <li className="border-b border-slate-100 px-4 py-3 last:border-0">
      <div className="flex items-start justify-between gap-3">
        <button onClick={() => onOpen(command)} className="min-w-0 flex-1 text-left">
          <p className="truncate text-sm text-slate-900">
            {command.transcript || "(no transcript)"}
          </p>
          <p className="mt-1 text-xs text-slate-500">
            {new Date(command.created_at).toLocaleString()}
            {command.steps.length > 0 && ` · ${done}/${command.steps.length} steps`}
            {command.detected_language && ` · ${command.detected_language}`}
            {command.source === "text" && " · typed"}
          </p>
        </button>
        <span
          className={`shrink-0 rounded px-2 py-0.5 text-xs ${
            TONE[command.status] ?? "bg-slate-100 text-slate-600"
          }`}
        >
          {LABEL[command.status] ?? command.status}
        </span>
      </div>

      {command.error && <p className="mt-1 text-xs text-red-600">{command.error}</p>}

      {command.audio_url && (
        <div className="mt-2">
          {audio ? (
            <audio controls src={audio} className="h-8 w-full max-w-sm" />
          ) : (
            <button
              onClick={() =>
                api
                  .getCommandAudioUrl(command.id)
                  .then(setAudio)
                  .catch((cause) => setAudioError(cause.message))
              }
              className="text-xs text-slate-500 underline"
            >
              Play the recording
            </button>
          )}
          {audioError && <p className="text-xs text-red-600">{audioError}</p>}
        </div>
      )}
    </li>
  );
}

export default function VoiceHistory({
  refreshToken,
  onOpen,
}: {
  refreshToken?: unknown;
  onOpen: (command: VoiceCommand) => void;
}) {
  const [commands, setCommands] = useState<VoiceCommand[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .listVoiceCommands(30)
      .then((rows) => !cancelled && setCommands(rows))
      .catch((cause) => !cancelled && setError(cause.message));
    return () => {
      cancelled = true;
    };
  }, [refreshToken]);

  if (error) return <p className="p-4 text-sm text-red-600">Couldn&apos;t load the history: {error}</p>;
  if (!commands) return <p className="p-4 text-sm text-slate-500">Loading…</p>;
  if (commands.length === 0) {
    return (
      <p className="p-4 text-sm text-slate-500">
        Nothing here yet. Hold the microphone and try &ldquo;remind me to call Acme
        tomorrow&rdquo;.
      </p>
    );
  }

  return (
    <ul>
      {commands.map((command) => (
        <Row key={command.id} command={command} onOpen={onOpen} />
      ))}
    </ul>
  );
}
