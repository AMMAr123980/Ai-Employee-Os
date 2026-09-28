"use client";

/**
 * Hold to talk, release to send.
 *
 * Press-and-hold rather than tap-to-start-tap-to-stop, because what this
 * replaces is "tell an assistant to do it", and that's how a walkie-talkie
 * works — you're never left wondering whether it's still listening. Keyboard
 * users get space/enter as a toggle instead, since there's no "hold" on a
 * keyboard that doesn't fight key repeat.
 */
import { useCallback, useEffect, useState } from "react";
import { extensionFor, useVoiceRecorder } from "./useVoiceRecorder";

function formatSeconds(total: number): string {
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

export default function MicButton({
  onRecorded,
  disabled,
  disabledReason,
  maxSeconds = 120,
}: {
  onRecorded: (blob: Blob, filename: string, transcript?: string) => void;
  disabled?: boolean;
  disabledReason?: string;
  maxSeconds?: number;
}) {
  const { state, error, seconds, level, start, stop, cancel, isRecording } =
    useVoiceRecorder(maxSeconds);
  const [shortWarning, setShortWarning] = useState(false);

  const handleClick = useCallback(async () => {
    if (disabled) return;
    setShortWarning(false);

    if (isRecording) {
      const recording = await stop();
      if (recording && recording.blob.size > 0) {
        if (recording.blob.size < 3000 || seconds < 1) {
          console.log("[MicButton] Recording too short, discarded.");
          setShortWarning(true);
          return;
        }
        console.log("[MicButton] Recording finished. Blob size:", recording.blob.size);
        console.log("[MicButton] Live transcript from Web Speech API:", JSON.stringify(recording.transcript));
        onRecorded(recording.blob, `voice-note.${extensionFor(recording.mimeType)}`, recording.transcript);
      }
    } else {
      void start();
    }
  }, [disabled, isRecording, seconds, start, stop, onRecorded]);

  const scale = isRecording ? 1 + Math.min(level, 1) * 0.2 : 1;

  return (
    <div className="flex flex-col items-center gap-2">
      <button
        type="button"
        disabled={disabled || state === "requesting" || state === "stopping"}
        aria-label={isRecording ? "Click to stop recording and send" : "Click to start recording"}
        aria-pressed={isRecording}
        onClick={() => void handleClick()}
        onKeyDown={(event) => {
          if (disabled || (event.key !== " " && event.key !== "Enter") || event.repeat) return;
          event.preventDefault();
          void handleClick();
        }}
        style={isRecording ? { transform: `scale(${scale})` } : undefined}
        className={`relative flex h-20 w-20 items-center justify-center rounded-full transition-all duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-600 focus-visible:ring-offset-2 ${
          disabled
            ? "cursor-not-allowed bg-slate-200 text-slate-400"
            : isRecording
            ? "bg-red-600 text-white animate-pulse shadow-lg shadow-red-500/30"
            : "bg-brand-600 text-white hover:bg-brand-700 shadow-md hover:shadow-lg"
        }`}
      >
        {isRecording ? (
          <div className="h-7 w-7 rounded bg-white" aria-hidden />
        ) : (
          <svg viewBox="0 0 24 24" className="h-8 w-8" fill="currentColor" aria-hidden>
            <path d="M12 14a3 3 0 0 0 3-3V6a3 3 0 1 0-6 0v5a3 3 0 0 0 3 3z" />
            <path d="M19 11a1 1 0 1 0-2 0 5 5 0 0 1-10 0 1 1 0 1 0-2 0 7 7 0 0 0 6 6.92V21a1 1 0 1 0 2 0v-3.08A7 7 0 0 0 19 11z" />
          </svg>
        )}
      </button>

      {isRecording ? (
        <div className="flex flex-col items-center gap-1">
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-red-600 animate-ping" />
            <span className="text-xs font-semibold uppercase tracking-wider text-red-600">Recording</span>
            <span className="text-sm tabular-nums text-slate-700 font-mono">({formatSeconds(seconds)})</span>
          </div>
          <p className="text-xs text-slate-600">Click button again to stop & send</p>
          <button onClick={cancel} className="text-xs text-slate-400 hover:text-slate-600 underline mt-1">
            Discard
          </button>
        </div>
      ) : (
        <p className="text-center text-xs text-slate-600 font-medium">
          {disabled ? disabledReason ?? "Recording is unavailable" : "Click mic to start recording"}
        </p>
      )}

      {state === "requesting" && (
        <p className="text-xs text-slate-500 animate-pulse">Starting microphone…</p>
      )}
      {shortWarning && (
        <p className="max-w-xs text-center text-xs text-amber-700 font-medium bg-amber-50 px-2 py-1 rounded border border-amber-200">
          Recording was too short. Please click to start, speak your command, then click to stop.
        </p>
      )}
      {error && <p className="max-w-xs text-center text-xs text-red-600">{error}</p>}
      {isRecording && level < 0.02 && seconds > 2 && (
        <p className="text-xs text-amber-700">Nothing is coming through — check your microphone.</p>
      )}
    </div>
  );
}
