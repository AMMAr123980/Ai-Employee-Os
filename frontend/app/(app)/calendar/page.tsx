"use client";

import { useEffect, useState } from "react";
import { api, CalendarEvent, Customer } from "@/lib/api";

export default function CalendarPage() {
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [filter, setFilter] = useState<"all" | "upcoming" | "past">("all");
  const [msg, setMsg] = useState<string | null>(null);

  const [form, setForm] = useState({
    title: "",
    description: "",
    starts_at: new Date(Date.now() + 3600000).toISOString().slice(0, 16),
    duration_minutes: 30,
    customer_id: "",
    location: "",
    meeting_link: "",
    provider: "google",
  });

  async function load() {
    setLoading(true);
    try {
      const [evList, custs] = await Promise.all([
        api.listCalendarEvents(),
        api.listCustomers(),
      ]);
      setEvents(evList);
      setCustomers(custs);
    } catch (err: any) {
      setMsg(`Failed to load calendar events: ${err.message}`);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!form.title.trim() || !form.starts_at) return;
    setSaving(true);
    setMsg(null);
    try {
      const payload = {
        title: form.title,
        description: form.description || undefined,
        starts_at: new Date(form.starts_at).toISOString(),
        duration_minutes: Number(form.duration_minutes),
        customer_id: form.customer_id || undefined,
        location: form.location || undefined,
        meeting_link: form.meeting_link || undefined,
        provider: form.provider,
      };
      await api.createCalendarEvent(payload);
      setForm({
        title: "",
        description: "",
        starts_at: new Date(Date.now() + 3600000).toISOString().slice(0, 16),
        duration_minutes: 30,
        customer_id: "",
        location: "",
        meeting_link: "",
        provider: "google",
      });
      setShowForm(false);
      setMsg("Event scheduled successfully!");
      await load();
    } catch (err: any) {
      setMsg(`Error creating event: ${err.message}`);
    } finally {
      setSaving(false);
    }
  }

  const now = new Date();
  const filteredEvents = events.filter((e) => {
    const eventTime = new Date(e.starts_at);
    if (filter === "upcoming") return eventTime >= now;
    if (filter === "past") return eventTime < now;
    return true;
  });

  const upcomingCount = events.filter((e) => new Date(e.starts_at) >= now).length;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Calendar & Event Sync</h1>
          <p className="text-xs text-slate-500">
            Schedule meetings, customer demos & sync seamlessly with Google Calendar and Microsoft 365.
          </p>
        </div>
        <button
          onClick={() => setShowForm((v) => !v)}
          className="rounded-lg bg-brand-600 text-white px-4 py-2 text-xs font-medium hover:bg-brand-700 transition"
        >
          {showForm ? "Cancel" : "+ Schedule Event"}
        </button>
      </div>

      {msg && (
        <div className="rounded-lg bg-indigo-50 border border-indigo-200 p-3 text-xs text-indigo-900 flex justify-between items-center">
          <span>{msg}</span>
          <button onClick={() => setMsg(null)} className="font-bold text-indigo-950 ml-2">
            ×
          </button>
        </div>
      )}

      {/* Overview Metric Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="rounded-xl border border-slate-200 bg-white p-4 flex items-center gap-4">
          <div className="h-10 w-10 rounded-lg bg-brand-100 text-brand-700 flex items-center justify-center font-bold text-lg">
            📅
          </div>
          <div>
            <p className="text-xs font-medium text-slate-500">Total Scheduled Events</p>
            <p className="text-xl font-bold text-slate-900">{events.length}</p>
          </div>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-4 flex items-center gap-4">
          <div className="h-10 w-10 rounded-lg bg-green-100 text-green-700 flex items-center justify-center font-bold text-lg">
            ⏰
          </div>
          <div>
            <p className="text-xs font-medium text-slate-500">Upcoming Meetings</p>
            <p className="text-xl font-bold text-slate-900">{upcomingCount}</p>
          </div>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-4 flex items-center gap-4">
          <div className="h-10 w-10 rounded-lg bg-purple-100 text-purple-700 flex items-center justify-center font-bold text-lg">
            🔄
          </div>
          <div>
            <p className="text-xs font-medium text-slate-500">Calendar Sync Provider</p>
            <p className="text-sm font-semibold text-slate-800">Google Cal & Outlook 365</p>
          </div>
        </div>
      </div>

      {/* Event Schedule Form */}
      {showForm && (
        <form
          onSubmit={handleSubmit}
          className="rounded-xl border border-slate-200 bg-white p-5 space-y-4 shadow-sm"
        >
          <h2 className="text-sm font-semibold text-slate-900 border-b border-slate-100 pb-2">
            Schedule New Meeting / Event
          </h2>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">Event Title *</label>
              <input
                required
                placeholder="Client Demo & Intro Call"
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                value={form.title}
                onChange={(e) => setForm({ ...form, title: e.target.value })}
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">Associated Customer</label>
              <select
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                value={form.customer_id}
                onChange={(e) => setForm({ ...form, customer_id: e.target.value })}
              >
                <option value="">-- Optional Customer --</option>
                {customers.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name} {c.company ? `(${c.company})` : ""}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">Start Date & Time *</label>
              <input
                type="datetime-local"
                required
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                value={form.starts_at}
                onChange={(e) => setForm({ ...form, starts_at: e.target.value })}
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">Duration (Minutes)</label>
              <select
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                value={form.duration_minutes}
                onChange={(e) => setForm({ ...form, duration_minutes: Number(e.target.value) })}
              >
                <option value={15}>15 Minutes</option>
                <option value={30}>30 Minutes</option>
                <option value={45}>45 Minutes</option>
                <option value={60}>1 Hour</option>
                <option value={90}>1.5 Hours</option>
                <option value={120}>2 Hours</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">Location / Room</label>
              <input
                placeholder="Office Boardroom / Online"
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                value={form.location}
                onChange={(e) => setForm({ ...form, location: e.target.value })}
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">Meeting Link (Google Meet / Zoom)</label>
              <input
                placeholder="https://meet.google.com/xyz-abc"
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                value={form.meeting_link}
                onChange={(e) => setForm({ ...form, meeting_link: e.target.value })}
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">Description & Agenda</label>
            <textarea
              rows={2}
              placeholder="Meeting objectives, key discussion points..."
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
            />
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={() => setShowForm(false)}
              className="rounded-lg border border-slate-300 px-4 py-2 text-xs font-medium text-slate-600 hover:bg-slate-50"
            >
              Cancel
            </button>
            <button
              disabled={saving}
              type="submit"
              className="rounded-lg bg-brand-600 text-white px-5 py-2 text-xs font-medium hover:bg-brand-700 disabled:opacity-50"
            >
              {saving ? "Scheduling..." : "Confirm & Schedule Event"}
            </button>
          </div>
        </form>
      )}

      {/* Events Filter Tabs & List */}
      <div className="rounded-xl border border-slate-200 bg-white overflow-hidden shadow-sm">
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-3 bg-slate-50">
          <h3 className="text-sm font-semibold text-slate-800">Event Schedule</h3>
          <div className="flex items-center gap-1 bg-white border border-slate-200 rounded-lg p-0.5">
            {(["all", "upcoming", "past"] as const).map((f) => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={`px-3 py-1 text-xs font-medium rounded-md capitalize transition ${
                  filter === f
                    ? "bg-brand-600 text-white"
                    : "text-slate-600 hover:text-slate-900"
                }`}
              >
                {f}
              </button>
            ))}
          </div>
        </div>

        {loading ? (
          <div className="p-8 text-center text-sm text-slate-400">Loading schedule...</div>
        ) : filteredEvents.length === 0 ? (
          <div className="p-8 text-center text-sm text-slate-400">
            No events found. Schedule your first event using the button above.
          </div>
        ) : (
          <div className="divide-y divide-slate-100">
            {filteredEvents.map((ev) => {
              const startDate = new Date(ev.starts_at);
              const endDate = new Date(ev.ends_at);
              const isPast = startDate < now;

              return (
                <div
                  key={ev.id}
                  className="p-5 flex flex-col md:flex-row md:items-center justify-between gap-4 hover:bg-slate-50 transition"
                >
                  <div className="flex items-start gap-4">
                    <div className="shrink-0 w-14 text-center rounded-lg border border-slate-200 bg-slate-50 p-2">
                      <p className="text-xs uppercase font-bold text-slate-400">
                        {startDate.toLocaleDateString("en-US", { month: "short" })}
                      </p>
                      <p className="text-lg font-extrabold text-slate-900 leading-none mt-0.5">
                        {startDate.getDate()}
                      </p>
                    </div>

                    <div className="space-y-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <h4 className="font-semibold text-slate-900">{ev.title}</h4>
                        {ev.customer_name && (
                          <span className="bg-indigo-50 text-indigo-700 border border-indigo-200 text-xs px-2 py-0.5 rounded-md font-medium">
                            👤 {ev.customer_name}
                          </span>
                        )}
                        {isPast && (
                          <span className="bg-slate-100 text-slate-500 text-xs px-2 py-0.5 rounded-md">
                            Past
                          </span>
                        )}
                      </div>

                      <p className="text-xs text-slate-500 flex items-center gap-3">
                        <span>
                          🕒 {startDate.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })} –{" "}
                          {endDate.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                        </span>
                        {ev.location && <span>📍 {ev.location}</span>}
                      </p>

                      {ev.description && (
                        <p className="text-xs text-slate-600 line-clamp-2 pt-1">{ev.description}</p>
                      )}

                      {ev.meeting_link && (
                        <a
                          href={ev.meeting_link}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-block text-xs font-medium text-brand-600 hover:underline pt-1"
                        >
                          🔗 Join Online Meeting
                        </a>
                      )}
                    </div>
                  </div>

                  {/* External Calendar Sync Buttons */}
                  <div className="flex items-center gap-2 flex-wrap shrink-0">
                    <a
                      href={ev.google_url}
                      target="_blank"
                      rel="noreferrer"
                      className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 transition"
                    >
                      + Google Cal
                    </a>
                    <a
                      href={ev.outlook_url}
                      target="_blank"
                      rel="noreferrer"
                      className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 transition"
                    >
                      + Outlook
                    </a>
                    <button
                      onClick={() => api.exportCalendarEventIcs(ev.id)}
                      className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 transition"
                    >
                      📥 .ics File
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
