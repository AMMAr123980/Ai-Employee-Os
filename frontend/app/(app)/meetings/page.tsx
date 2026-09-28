"use client";

/**
 * AI Meeting Assistant.
 *
 * Upload a recording, watch the status move, then read the write-up. The action
 * items are already real tasks by the time they appear here — that's the part
 * that makes this worth doing rather than a summary you read once.
 *
 * Speaker labels are shown with a caveat when they were estimated from pauses,
 * because presenting a guess as voice identification would be a lie people
 * would then rely on.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Customer, Meeting, QuotaError, api } from "@/lib/api";

const STATUS_LABEL: Record<string, string> = {
  queued: "Queued",
  transcribing: "Transcribing",
  summarizing: "Writing it up",
  completed: "Ready",
  failed: "Failed",
};

const SPEAKER_NOTE: Record<string, string> = {
  heuristic: "Speaker labels are estimated from pauses, not voice recognition — rename them below.",
  diarized: "Speaker labels came from the diarization service.",
  provided: "Speaker names were set by a person.",
};

function duration(seconds?: number | null): string {
  if (!seconds) return "";
  const minutes = Math.round(seconds / 60);
  return minutes < 1 ? "under a minute" : `${minutes} min`;
}

export default function MeetingsPage() {
  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [selected, setSelected] = useState<Meeting | null>(null);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [calendarEvents, setCalendarEvents] = useState<any[]>([]);
  const [title, setTitle] = useState("");
  const [customerId, setCustomerId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [names, setNames] = useState<Record<string, string>>({});
  const fileRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    const [mList, cEvents] = await Promise.all([
      api.listMeetings(),
      api.listCalendarEvents().catch(() => [])
    ]);
    setMeetings(mList);
    setCalendarEvents(cEvents);
  }, []);

  useEffect(() => {
    void load();
    api.listCustomers().then(setCustomers).catch(() => undefined);
  }, [load]);

  // Poll while anything is still processing — an hour of audio takes minutes,
  // and the status is the only progress indicator there is.
  useEffect(() => {
    const working = meetings.some((m) => ["queued", "transcribing", "summarizing"].includes(m.status));
    if (!working) return;
    const timer = setInterval(() => void load(), 5000);
    return () => clearInterval(timer);
  }, [meetings, load]);


  async function upload(file: File) {
    setBusy(true);
    setError(null);
    try {
      await api.uploadMeeting(file, { title: title || undefined, customer_id: customerId || undefined });
      setTitle("");
      setCustomerId("");
      if (fileRef.current) fileRef.current.value = "";
      await load();
    } catch (cause) {
      setError(
        cause instanceof QuotaError
          ? "This plan's transcription allowance is used up. Upgrade, or wait for the monthly reset."
          : cause instanceof Error
          ? cause.message
          : "Upload failed."
      );
    } finally {
      setBusy(false);
    }
  }

  async function open(meeting: Meeting) {
    const full = await api.getMeeting(meeting.id);
    setSelected(full);
    setNames({});
  }

  async function saveNames() {
    if (!selected) return;
    const map = Object.fromEntries(
      Object.entries(names).filter(([, value]) => value.trim())
    );
    if (Object.keys(map).length === 0) return;
    setSelected(await api.renameSpeakers(selected.id, map));
    setNames({});
  }

  const speakers = selected
    ? Array.from(new Set(selected.segments.map((s) => s.speaker).filter(Boolean)))
    : [];

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6">
      <header>
        <h1 className="text-xl font-semibold">Meetings</h1>
        <p className="text-sm text-slate-500">
          Upload a recording and get a transcript, a summary, the decisions, and action items that
          land in your task list.
        </p>
      </header>

      <section className="rounded-xl border border-slate-200 bg-white p-4">
        <div className="flex flex-wrap items-center gap-2">
          <input
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="What was this meeting? (optional)"
            className="min-w-[14rem] flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm"
          />
          <select
            value={customerId}
            onChange={(event) => setCustomerId(event.target.value)}
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
          >
            <option value="">No customer</option>
            {customers.map((customer) => (
              <option key={customer.id} value={customer.id}>
                {customer.name}
              </option>
            ))}
          </select>
          <input
            ref={fileRef}
            type="file"
            accept="audio/*,video/mp4,video/webm"
            disabled={busy}
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) void upload(file);
            }}
            className="text-sm"
          />
        </div>
        {busy && <p className="mt-2 text-sm text-slate-500">Uploading…</p>}
        {error && <p className="mt-2 rounded bg-red-50 p-2 text-sm text-red-700">{error}</p>}
      </section>

      {/* CALENDAR EVENTS SYNC BOX */}
      <section className="rounded-xl border border-blue-200 bg-gradient-to-r from-blue-50 to-indigo-50 p-4 space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-sm font-bold text-blue-950">📅 Synced Calendar Events (Google & Outlook / 365)</h2>
            <p className="text-xs text-blue-700">Events scheduled by Voice commands, AI Employees, or Meeting Assistant</p>
          </div>
          <span className="text-xs bg-blue-200 text-blue-900 font-bold px-2.5 py-0.5 rounded-full">
            {calendarEvents.length} Event(s)
          </span>
        </div>

        {calendarEvents.length === 0 ? (
          <p className="text-xs text-blue-600 italic">No calendar events synced yet. Say "Schedule a meeting with Acme tomorrow" via Voice to test!</p>
        ) : (
          <div className="divide-y divide-blue-100/60 max-h-48 overflow-y-auto">
            {calendarEvents.map((ev) => (
              <div key={ev.id} className="py-2.5 flex items-center justify-between text-xs">
                <div>
                  <p className="font-bold text-slate-800">{ev.title}</p>
                  <p className="text-slate-500">
                    {new Date(ev.starts_at).toLocaleString()} {ev.customer_name ? `· Customer: ${ev.customer_name}` : ""}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <a
                    href={ev.google_url}
                    target="_blank"
                    rel="noreferrer"
                    className="px-2.5 py-1 bg-white border border-blue-300 text-blue-800 font-semibold rounded hover:bg-blue-100 text-[11px]"
                  >
                    + Google Cal
                  </a>
                  <a
                    href={ev.outlook_url}
                    target="_blank"
                    rel="noreferrer"
                    className="px-2.5 py-1 bg-white border border-blue-300 text-blue-800 font-semibold rounded hover:bg-blue-100 text-[11px]"
                  >
                    + Outlook
                  </a>
                  <button
                    onClick={() => api.exportCalendarEventIcs(ev.id)}
                    className="px-2.5 py-1 bg-blue-600 text-white font-semibold rounded hover:bg-blue-700 text-[11px]"
                  >
                    📥 .ics File
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="rounded-xl border border-slate-200 bg-white">
        <h2 className="border-b border-slate-100 px-4 py-3 text-sm font-medium text-slate-700">
          Recordings
        </h2>

        {meetings.length === 0 ? (
          <p className="p-4 text-sm text-slate-500">
            Nothing uploaded yet. Any common audio file works — m4a, mp3, webm, wav.
          </p>
        ) : (
          <ul>
            {meetings.map((meeting) => (
              <li
                key={meeting.id}
                className="flex items-center justify-between gap-3 border-b border-slate-100 px-4 py-3 last:border-0"
              >
                <button onClick={() => void open(meeting)} className="min-w-0 flex-1 text-left">
                  <p className="truncate text-sm text-slate-900">{meeting.title || "Untitled"}</p>
                  <p className="mt-1 text-xs text-slate-500">
                    {new Date(meeting.created_at).toLocaleString()}
                    {meeting.duration_seconds ? ` · ${duration(meeting.duration_seconds)}` : ""}
                    {meeting.action_items?.length
                      ? ` · ${meeting.action_items.length} action item(s)`
                      : ""}
                  </p>
                  {meeting.error && <p className="mt-1 text-xs text-red-600">{meeting.error}</p>}
                </button>
                <span
                  className={`shrink-0 rounded px-2 py-0.5 text-xs ${
                    meeting.status === "completed"
                      ? "bg-emerald-50 text-emerald-700"
                      : meeting.status === "failed"
                      ? "bg-red-50 text-red-700"
                      : "bg-slate-100 text-slate-600"
                  }`}
                >
                  {STATUS_LABEL[meeting.status] ?? meeting.status}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      {selected && (
        <section className="rounded-xl border border-slate-200 bg-white p-4">
          <div className="flex items-start justify-between gap-4">
            <h2 className="text-base font-medium">{selected.title || "Untitled"}</h2>
            <button
              onClick={() => setSelected(null)}
              className="rounded px-2 py-1 text-sm text-slate-500 hover:bg-slate-100"
            >
              Close
            </button>
          </div>

          {selected.summary && <p className="mt-3 text-sm text-slate-700">{selected.summary}</p>}

          {selected.decisions?.length > 0 && (
            <div className="mt-4">
              <h3 className="text-xs uppercase tracking-wide text-slate-400">Decisions</h3>
              <ul className="mt-1 list-disc pl-5 text-sm text-slate-700">
                {selected.decisions.map((decision) => (
                  <li key={decision}>{decision}</li>
                ))}
              </ul>
            </div>
          )}

          {selected.action_items?.length > 0 && (
            <div className="mt-4">
              <h3 className="text-xs uppercase tracking-wide text-slate-400">
                Action items — already in{" "}
                <Link href="/tasks" className="text-brand-600 underline">
                  Tasks
                </Link>
              </h3>
              <ul className="mt-1 space-y-1 text-sm text-slate-700">
                {selected.action_items.map((item) => (
                  <li key={item.task_id}>
                    {item.title}
                    <span className="text-slate-500">
                      {item.owner ? ` · ${item.owner}` : ""}
                      {item.due ? ` · ${item.due}` : ""}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {selected.deadlines?.length > 0 && (
            <div className="mt-4">
              <h3 className="text-xs uppercase tracking-wide text-slate-400">Dates mentioned</h3>
              <ul className="mt-1 text-sm text-slate-700">
                {selected.deadlines.map((deadline) => (
                  <li key={`${deadline.what}-${deadline.date}`}>
                    {deadline.date} — {deadline.what}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {selected.open_questions?.length > 0 && (
            <div className="mt-4">
              <h3 className="text-xs uppercase tracking-wide text-slate-400">Left unresolved</h3>
              <ul className="mt-1 list-disc pl-5 text-sm text-slate-700">
                {selected.open_questions.map((question) => (
                  <li key={question}>{question}</li>
                ))}
              </ul>
            </div>
          )}

          {speakers.length > 0 && (
            <div className="mt-4 rounded-lg bg-slate-50 p-3">
              <p className="text-xs text-slate-500">
                {SPEAKER_NOTE[selected.speaker_method ?? "heuristic"]}
              </p>
              <div className="mt-2 flex flex-wrap gap-2">
                {speakers.map((speaker) => (
                  <input
                    key={speaker}
                    value={names[speaker] ?? ""}
                    onChange={(event) =>
                      setNames((current) => ({ ...current, [speaker]: event.target.value }))
                    }
                    placeholder={speaker}
                    className="w-40 rounded border border-slate-300 px-2 py-1 text-sm"
                  />
                ))}
                <button
                  onClick={() => void saveNames()}
                  className="rounded-lg border border-slate-300 px-3 py-1 text-sm text-slate-700"
                >
                  Save names
                </button>
              </div>
            </div>
          )}

          {selected.segments?.length > 0 && (
            <details className="mt-4">
              <summary className="cursor-pointer text-sm text-slate-600">Full transcript</summary>
              <div className="mt-2 max-h-96 overflow-auto rounded bg-slate-50 p-3 text-sm text-slate-700">
                {selected.segments.map((segment, index) => (
                  <p key={index} className="mb-1">
                    <span className="text-slate-400">{segment.speaker}:</span> {segment.text}
                  </p>
                ))}
              </div>
            </details>
          )}
        </section>
      )}
    </div>
  );
}
