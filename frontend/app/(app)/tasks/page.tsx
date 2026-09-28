"use client";

/**
 * Task manager, plus the conditional follow-up queue.
 *
 * The two belong on one screen: a pending follow-up is a task that hasn't
 * decided whether it needs to exist yet, and seeing both is the only way to
 * know what's actually coming.
 */
import { useCallback, useEffect, useState } from "react";
import { ConditionalFollowUp, Task, TaskPriority, api } from "@/lib/api";

const SOURCE_LABEL: Record<string, string> = {
  manual: "added by hand",
  voice: "from a voice command",
  followup: "from a conditional follow-up",
  meeting: "from a meeting",
  ai_employee: "from an AI employee",
};

const PRIORITY_TONE: Record<TaskPriority, string> = {
  high: "bg-red-50 text-red-700",
  normal: "bg-slate-100 text-slate-600",
  low: "bg-slate-50 text-slate-500",
};

function dueLabel(due?: string | null): { text: string; overdue: boolean } {
  if (!due) return { text: "No date", overdue: false };
  const date = new Date(due);
  return {
    text: date.toLocaleString([], { dateStyle: "medium", timeStyle: "short" }),
    overdue: date.getTime() < Date.now(),
  };
}

export default function TasksPage() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [followUps, setFollowUps] = useState<ConditionalFollowUp[]>([]);
  const [loading, setLoading] = useState(true);
  const [showDone, setShowDone] = useState(false);
  const [title, setTitle] = useState("");
  const [due, setDue] = useState("");
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    const [taskRows, followUpRows] = await Promise.all([
      api.listTasks(),
      api.listConditionalFollowUps(),
    ]);
    setTasks(taskRows);
    setFollowUps(followUpRows);
    setLoading(false);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function add() {
    if (!title.trim()) return;
    await api.createTask({ title: title.trim(), due_date: due ? new Date(due).toISOString() : null });
    setTitle("");
    setDue("");
    await load();
  }

  async function toggle(task: Task) {
    await api.updateTask(task.id, { status: task.status === "done" ? "open" : "done" });
    await load();
  }

  async function checkFollowUps() {
    const result = await api.checkConditionalFollowUpsNow();
    await load();
    setMessage(
      result.checked === 0
        ? "Nothing was due."
        : `Checked ${result.checked}: ${result.fired} turned into reminders, ${result.resolved} resolved on their own.`
    );
  }

  const visible = tasks.filter((task) => showDone || task.status !== "done");
  const waiting = followUps.filter((f) => f.status === "waiting");
  const settled = followUps.filter((f) => f.status !== "waiting").slice(0, 8);

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6">
      <header className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold">Tasks</h1>
          <p className="text-sm text-slate-500">
            Everything you or the assistant committed to — typed here, spoken into the mic, or
            pulled out of a meeting.
          </p>
        </div>
        <label className="flex items-center gap-2 text-sm text-slate-600">
          <input
            type="checkbox"
            checked={showDone}
            onChange={(event) => setShowDone(event.target.checked)}
            className="h-4 w-4 rounded border-slate-300"
          />
          Show completed
        </label>
      </header>

      <section className="rounded-xl border border-slate-200 bg-white p-4">
        <div className="flex flex-wrap gap-2">
          <input
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            onKeyDown={(event) => event.key === "Enter" && void add()}
            placeholder="What needs doing?"
            className="min-w-[16rem] flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm"
          />
          <input
            type="datetime-local"
            value={due}
            onChange={(event) => setDue(event.target.value)}
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
          />
          <button
            onClick={() => void add()}
            disabled={!title.trim()}
            className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-40"
          >
            Add task
          </button>
        </div>
      </section>

      <section className="rounded-xl border border-slate-200 bg-white">
        {loading ? (
          <p className="p-4 text-sm text-slate-500">Loading…</p>
        ) : visible.length === 0 ? (
          <p className="p-4 text-sm text-slate-500">
            Nothing outstanding. Add one above, or say &ldquo;remind me to call Acme
            tomorrow&rdquo; on the Voice screen.
          </p>
        ) : (
          <ul>
            {visible.map((task) => {
              const { text, overdue } = dueLabel(task.due_date);
              return (
                <li
                  key={task.id}
                  className="flex items-start gap-3 border-b border-slate-100 px-4 py-3 last:border-0"
                >
                  <input
                    type="checkbox"
                    checked={task.status === "done"}
                    onChange={() => void toggle(task)}
                    className="mt-1 h-4 w-4 rounded border-slate-300"
                    aria-label={`Mark "${task.title}" done`}
                  />
                  <div className="min-w-0 flex-1">
                    <p
                      className={`text-sm ${
                        task.status === "done" ? "text-slate-400 line-through" : "text-slate-900"
                      }`}
                    >
                      {task.title}
                    </p>
                    <p className="mt-1 text-xs text-slate-500">
                      <span className={overdue && task.status !== "done" ? "text-red-600" : ""}>
                        {text}
                      </span>
                      {task.customer_name && ` · ${task.customer_name}`}
                      {task.assignee_name && ` · ${task.assignee_name}`}
                      {` · ${SOURCE_LABEL[task.source] ?? task.source}`}
                    </p>
                    {task.description && (
                      <p className="mt-1 text-xs text-slate-500">{task.description}</p>
                    )}
                  </div>
                  <span className={`shrink-0 rounded px-2 py-0.5 text-xs ${PRIORITY_TONE[task.priority]}`}>
                    {task.priority}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <section className="rounded-xl border border-slate-200 bg-white">
        <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
          <div>
            <h2 className="text-sm font-medium text-slate-700">Waiting on a condition</h2>
            <p className="text-xs text-slate-500">
              These only become reminders if the thing you&apos;re waiting for still hasn&apos;t
              happened.
            </p>
          </div>
          <button
            onClick={() => void checkFollowUps()}
            className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-700"
          >
            Check now
          </button>
        </div>

        {message && <p className="px-4 pt-3 text-sm text-slate-600">{message}</p>}

        {waiting.length === 0 ? (
          <p className="p-4 text-sm text-slate-500">
            None pending. Say &ldquo;remind me if they haven&apos;t replied in three days&rdquo; to
            create one.
          </p>
        ) : (
          <ul>
            {waiting.map((followUp) => (
              <li
                key={followUp.id}
                className="flex items-start justify-between gap-3 border-b border-slate-100 px-4 py-3 last:border-0"
              >
                <div className="min-w-0">
                  <p className="text-sm text-slate-900">{followUp.reminder_title}</p>
                  <p className="mt-1 text-xs text-slate-500">
                    {followUp.customer_name && `${followUp.customer_name} · `}
                    fires {new Date(followUp.due_at).toLocaleString()} if{" "}
                    {followUp.condition_type.replace(/_/g, " ")}
                  </p>
                </div>
                <button
                  onClick={async () => {
                    await api.cancelConditionalFollowUp(followUp.id);
                    await load();
                  }}
                  className="shrink-0 text-xs text-slate-500 underline"
                >
                  Cancel
                </button>
              </li>
            ))}
          </ul>
        )}

        {settled.length > 0 && (
          <div className="border-t border-slate-100 px-4 py-3">
            <p className="text-xs uppercase tracking-wide text-slate-400">Recently settled</p>
            <ul className="mt-2 space-y-1">
              {settled.map((followUp) => (
                <li key={followUp.id} className="text-xs text-slate-500">
                  {followUp.reminder_title} — {followUp.status}
                  {followUp.resolved_reason ? ` (${followUp.resolved_reason})` : ""}
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>
    </div>
  );
}
