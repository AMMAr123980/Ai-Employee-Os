"use client";

/**
 * Microphone recording with MediaRecorder.
 *
 * Deliberately small: ask for permission, record, hand back a Blob. It doesn't
 * upload and doesn't know what a command is, so the meeting recorder can reuse
 * it without dragging the command pipeline along.
 *
 * Two things worth knowing:
 *
 * - **Codec negotiation.** Safari doesn't do webm; Chrome and Firefox do.
 *   `pickMimeType()` asks the browser what it supports instead of assuming,
 *   because a hardcoded "audio/webm" produces a zero-byte blob on iOS and a
 *   very confusing bug report.
 * - **The stream is always released.** A MediaStream left running keeps the
 *   browser's recording indicator lit, which people reasonably read as an app
 *   listening when it shouldn't be. Every exit path — stop, cancel, unmount,
 *   error — stops every track.
 */
import { useCallback, useEffect, useRef, useState } from "react";

const CANDIDATE_TYPES = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/ogg;codecs=opus",
  "audio/mp4",
];

function pickMimeType(): string | undefined {
  if (typeof MediaRecorder === "undefined") return undefined;
  return CANDIDATE_TYPES.find((type) => MediaRecorder.isTypeSupported(type));
}

export function extensionFor(mimeType: string | undefined): string {
  if (!mimeType) return "webm";
  if (mimeType.includes("mp4")) return "m4a";
  if (mimeType.includes("ogg")) return "ogg";
  return "webm";
}

export type RecorderState = "idle" | "requesting" | "recording" | "stopping" | "error";

export function useVoiceRecorder(maxSeconds = 120) {
  const [state, setState] = useState<RecorderState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [seconds, setSeconds] = useState(0);
  const [level, setLevel] = useState(0);

  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const rafRef = useRef<number | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const speechRecognitionRef = useRef<any>(null);
  const liveTranscriptRef = useRef<string>("");

  const teardown = useCallback(() => {
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    if (timerRef.current) clearInterval(timerRef.current);
    rafRef.current = null;
    timerRef.current = null;

    if (speechRecognitionRef.current) {
      try { speechRecognitionRef.current.stop(); } catch (_) {}
      speechRecognitionRef.current = null;
    }

    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;

    audioContextRef.current?.close().catch(() => undefined);
    audioContextRef.current = null;
    setLevel(0);
  }, []);

  useEffect(() => teardown, [teardown]);

  const start = useCallback(async () => {
    setError(null);
    setSeconds(0);
    liveTranscriptRef.current = "";
    setState("requesting");

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true },
      });
      streamRef.current = stream;

      // Initialize Web Speech API if supported in browser
      const SpeechRecognition =
        (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
      if (SpeechRecognition) {
        try {
          const recognition = new SpeechRecognition();
          recognition.continuous = true;
          recognition.interimResults = true;
          recognition.lang = "";  // auto-detect language
          recognition.onresult = (event: any) => {
            let finalText = "";
            let interimText = "";
            for (let i = 0; i < event.results.length; i++) {
              if (event.results[i].isFinal) {
                finalText += event.results[i][0].transcript + " ";
              } else {
                interimText += event.results[i][0].transcript + " ";
              }
            }
            const combined = (finalText + interimText).trim();
            liveTranscriptRef.current = combined;
            console.log("[SpeechRecognition] onresult — final:", JSON.stringify(finalText.trim()), "interim:", JSON.stringify(interimText.trim()));
          };
          recognition.onerror = (event: any) => {
            console.warn("[SpeechRecognition] error:", event.error, event.message);
          };
          recognition.onend = () => {
            console.log("[SpeechRecognition] ended. Final transcript:", JSON.stringify(liveTranscriptRef.current));
          };
          recognition.start();
          speechRecognitionRef.current = recognition;
          console.log("[SpeechRecognition] started successfully");
        } catch (e) {
          console.warn("SpeechRecognition init error:", e);
        }
      } else {
        console.warn("[SpeechRecognition] NOT available in this browser");
      }

      const mimeType = pickMimeType();
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      chunksRef.current = [];
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };
      recorder.start();
      recorderRef.current = recorder;
      setState("recording");

      timerRef.current = setInterval(() => setSeconds((value) => value + 1), 1000);

      // Level meter.
      const context = new AudioContext();
      const analyser = context.createAnalyser();
      analyser.fftSize = 256;
      context.createMediaStreamSource(stream).connect(analyser);
      audioContextRef.current = context;

      const data = new Uint8Array(analyser.frequencyBinCount);
      const tick = () => {
        analyser.getByteTimeDomainData(data);
        let peak = 0;
        for (const sample of data) peak = Math.max(peak, Math.abs(sample - 128) / 128);
        setLevel(peak);
        rafRef.current = requestAnimationFrame(tick);
      };
      tick();
    } catch (cause) {
      teardown();
      setState("error");
      setError(
        cause instanceof DOMException && cause.name === "NotAllowedError"
          ? "Microphone access is blocked. Allow it in your browser settings, then try again."
          : "Couldn't start recording on this device."
      );
    }
  }, [teardown]);

  const stop = useCallback(async (): Promise<{ blob: Blob; mimeType: string; transcript?: string } | null> => {
    const recorder = recorderRef.current;
    if (!recorder || recorder.state === "inactive") return null;
    setState("stopping");

    const finalTranscript = liveTranscriptRef.current;
    console.log("[useVoiceRecorder] stop() called. liveTranscriptRef.current =", JSON.stringify(finalTranscript));

    const blob = await new Promise<Blob>((resolve) => {
      recorder.onstop = () =>
        resolve(new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" }));
      recorder.stop();
    });

    teardown();
    recorderRef.current = null;
    setState("idle");
    return { blob, mimeType: recorder.mimeType || "audio/webm", transcript: finalTranscript };
  }, [teardown]);

  const cancel = useCallback(() => {
    const recorder = recorderRef.current;
    if (recorder && recorder.state !== "inactive") {
      recorder.onstop = null;
      recorder.stop();
    }
    chunksRef.current = [];
    liveTranscriptRef.current = "";
    recorderRef.current = null;
    teardown();
    setState("idle");
    setSeconds(0);
  }, [teardown]);

  useEffect(() => {
    if (state === "recording" && seconds >= maxSeconds) {
      void stop();
    }
  }, [state, seconds, maxSeconds, stop]);

  return { state, error, seconds, level, start, stop, cancel, isRecording: state === "recording" };
}
