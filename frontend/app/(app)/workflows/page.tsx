"use client";

import { useEffect, useState } from "react";
import { api, Workflow, WorkflowRun, WorkflowTemplate, WorkflowStep } from "@/lib/api";

const TRIGGER_TYPES = [
  { value: "payment_received", label: "💳 Payment Received", desc: "Fires when a customer payment is recorded" },
  { value: "invoice_paid", label: "✅ Invoice Paid", desc: "Fires when invoice balance reaches zero" },
  { value: "quotation_approved", label: "📋 Quotation Approved", desc: "Fires when quotation status is marked approved" },
  { value: "customer_created", label: "👤 New Customer Created", desc: "Fires when a lead/customer is added" },
  { value: "pipeline_stage_changed", label: "🔄 Pipeline Stage Changed", desc: "Fires when CRM stage updates" },
  { value: "stock_low", label: "📦 Low Stock Warning", desc: "Fires when inventory hits reorder point" },
  { value: "whatsapp_message_received", label: "💬 WhatsApp Message Received", desc: "Fires when customer sends WhatsApp message" },
];

const ACTION_TYPES = [
  { value: "generate_receipt", label: "🧾 Generate Payment Receipt PDF", params: [] },
  { value: "update_crm_stage", label: "📈 Update CRM Pipeline Stage", params: [{ key: "stage", label: "Stage (won/proposal/qualified)", default: "won" }] },
  { value: "send_email", label: "✉️ Send Email Notification to Customer", params: [{ key: "subject", label: "Subject Template", default: "Payment Receipt — Invoice #{invoice_number}" }] },
  { value: "send_whatsapp", label: "📱 Send WhatsApp Message to Customer", params: [{ key: "message", label: "Message Template", default: "Hi {customer_name}, your payment of {amount} has been received!" }] },
  { value: "create_task", label: "📌 Create Task for Sales Team", params: [{ key: "title", label: "Task Title", default: "Follow up with customer" }] },
  { value: "trigger_ai_employee", label: "🤖 Trigger AI Employee Action", params: [{ key: "employee_key", label: "Employee Key", default: "bookkeeper" }] },
];

export default function WorkflowsPage() {
  const [activeTab, setActiveTab] = useState<"workflows" | "templates" | "runs">("workflows");

  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [templates, setTemplates] = useState<WorkflowTemplate[]>([]);
  const [runs, setRuns] = useState<WorkflowRun[]>([]);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // New/Edit Workflow Modal State
  const [showModal, setShowModal] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [triggerType, setTriggerType] = useState("payment_received");
  const [steps, setSteps] = useState<WorkflowStep[]>([
    { step_order: 1, name: "Generate Receipt", action_type: "generate_receipt", config_json: {} },
    { step_order: 2, name: "Update Stage to Won", action_type: "update_crm_stage", config_json: { stage: "won" } }
  ]);

  // Test Trigger Modal State
  const [showTestModal, setShowTestModal] = useState(false);
  const [testTriggerType, setTestTriggerType] = useState("payment_received");
  const [testTesting, setTestTesting] = useState(false);
  const [testResults, setTestResults] = useState<any>(null);

  useEffect(() => {
    loadAll();
  }, []);

  const loadAll = async () => {
    setLoading(true);
    setError(null);
    try {
      const [wfList, tplList, runList] = await Promise.all([
        api.listWorkflows(),
        api.listWorkflowTemplates(),
        api.listWorkflowRuns()
      ]);
      setWorkflows(wfList);
      setTemplates(tplList);
      setRuns(runList);
    } catch (err: any) {
      setError(err.message || "Failed to load workflows");
    } finally {
      setLoading(false);
    }
  };

  const handleToggleWorkflow = async (wf: Workflow) => {
    try {
      await api.updateWorkflow(wf.id, {
        name: wf.name,
        description: wf.description || undefined,
        trigger_type: wf.trigger_type,
        is_active: !wf.is_active,
        steps: wf.steps
      });
      await loadAll();
    } catch (err: any) {
      alert("Failed to toggle workflow: " + err.message);
    }
  };

  const handleDeleteWorkflow = async (id: string) => {
    if (!confirm("Are you sure you want to delete this workflow?")) return;
    try {
      await api.deleteWorkflow(id);
      await loadAll();
    } catch (err: any) {
      alert("Failed to delete workflow: " + err.message);
    }
  };

  const handleEnableTemplate = async (templateId: string) => {
    try {
      await api.enableWorkflowTemplate(templateId);
      await loadAll();
      setActiveTab("workflows");
    } catch (err: any) {
      alert("Failed to enable template: " + err.message);
    }
  };

  const handleSaveWorkflow = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;

    try {
      if (editingId) {
        await api.updateWorkflow(editingId, {
          name,
          description,
          trigger_type: triggerType,
          is_active: true,
          steps
        });
      } else {
        await api.createWorkflow({
          name,
          description,
          trigger_type: triggerType,
          is_active: true,
          steps
        });
      }
      setShowModal(false);
      resetForm();
      await loadAll();
    } catch (err: any) {
      alert("Failed to save workflow: " + err.message);
    }
  };

  const resetForm = () => {
    setEditingId(null);
    setName("");
    setDescription("");
    setTriggerType("payment_received");
    setSteps([
      { step_order: 1, name: "Generate Receipt", action_type: "generate_receipt", config_json: {} },
      { step_order: 2, name: "Update Stage to Won", action_type: "update_crm_stage", config_json: { stage: "won" } }
    ]);
  };

  const handleAddStep = () => {
    setSteps([
      ...steps,
      {
        step_order: steps.length + 1,
        name: `Step ${steps.length + 1}`,
        action_type: "send_email",
        config_json: {}
      }
    ]);
  };

  const handleRemoveStep = (idx: number) => {
    const updated = steps.filter((_, i) => i !== idx).map((s, i) => ({ ...s, step_order: i + 1 }));
    setSteps(updated);
  };

  const handleRunTestTrigger = async () => {
    setTestTesting(true);
    setTestResults(null);
    try {
      const res = await api.testTriggerWorkflow({
        event_type: testTriggerType,
      });
      setTestResults(res);
      await loadAll();
    } catch (err: any) {
      alert("Error firing test event: " + err.message);
    } finally {
      setTestTesting(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header Banner */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-gradient-to-r from-indigo-600 via-purple-600 to-pink-600 p-6 rounded-2xl text-white shadow-xl">
        <div>
          <span className="bg-white/20 text-white text-xs font-semibold px-2.5 py-1 rounded-full uppercase tracking-wider">
            Engine Active
          </span>
          <h1 className="text-2xl font-bold mt-2">Generic Workflow Automation Engine</h1>
          <p className="text-indigo-100 text-sm mt-1">
            Configurable trigger-action chains (payment → receipt → CRM → notify → email → whatsapp).
          </p>
        </div>

        {/* Tab Switcher & Buttons */}
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex bg-black/20 p-1.5 rounded-xl border border-white/10">
            <button
              onClick={() => setActiveTab("workflows")}
              className={`px-3.5 py-2 text-xs font-semibold rounded-lg transition-all ${
                activeTab === "workflows" ? "bg-white text-indigo-900 shadow" : "text-white/80 hover:text-white"
              }`}
            >
              ⚡ Active Rules ({workflows.length})
            </button>
            <button
              onClick={() => setActiveTab("templates")}
              className={`px-3.5 py-2 text-xs font-semibold rounded-lg transition-all ${
                activeTab === "templates" ? "bg-white text-indigo-900 shadow" : "text-white/80 hover:text-white"
              }`}
            >
              📚 Gallery ({templates.length})
            </button>
            <button
              onClick={() => setActiveTab("runs")}
              className={`px-3.5 py-2 text-xs font-semibold rounded-lg transition-all ${
                activeTab === "runs" ? "bg-white text-indigo-900 shadow" : "text-white/80 hover:text-white"
              }`}
            >
              📜 Audit Logs ({runs.length})
            </button>
          </div>

          <button
            onClick={() => { setShowTestModal(true); setTestResults(null); }}
            className="px-3.5 py-2 bg-amber-400 hover:bg-amber-300 text-slate-900 font-bold text-xs rounded-xl shadow transition flex items-center gap-1.5"
          >
            ⚡ Test Event Simulation
          </button>
        </div>
      </div>

      {loading ? (
        <div className="p-12 text-center text-slate-500 bg-white rounded-xl border border-slate-200">
          <div className="inline-block animate-spin w-8 h-8 border-4 border-indigo-600 border-t-transparent rounded-full mb-3"></div>
          <p className="font-medium">Loading Workflow Engine...</p>
        </div>
      ) : error ? (
        <div className="p-6 bg-red-50 text-red-700 rounded-xl border border-red-200">
          <p className="font-bold">Error loading Workflows</p>
          <p className="text-sm mt-1">{error}</p>
        </div>
      ) : activeTab === "workflows" ? (
        /* WORKFLOWS LIST TAB */
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-bold text-slate-800">Active Automation Workflows</h2>
            <button
              onClick={() => { resetForm(); setShowModal(true); }}
              className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white font-bold text-sm rounded-xl transition shadow"
            >
              + Create Custom Workflow
            </button>
          </div>

          {workflows.length === 0 ? (
            <div className="p-12 text-center bg-white rounded-2xl border border-slate-200 space-y-3">
              <p className="text-4xl">⚡</p>
              <h3 className="font-bold text-slate-800">No active workflows configured</h3>
              <p className="text-sm text-slate-500 max-w-md mx-auto">
                Enable a pre-packaged template from the Gallery tab or click <strong>+ Create Custom Workflow</strong> to build your first trigger chain.
              </p>
              <button
                onClick={() => setActiveTab("templates")}
                className="mt-2 px-4 py-2 bg-indigo-50 text-indigo-700 font-bold text-xs rounded-xl hover:bg-indigo-100 transition"
              >
                Browse Template Gallery
              </button>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-4">
              {workflows.map((wf) => {
                const trgInfo = TRIGGER_TYPES.find(t => t.value === wf.trigger_type);
                return (
                  <div
                    key={wf.id}
                    className={`bg-white rounded-2xl border p-5 transition shadow-sm ${
                      wf.is_active ? "border-slate-200 hover:border-indigo-300" : "border-slate-200 opacity-60 bg-slate-50/50"
                    }`}
                  >
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                      <div className="space-y-1">
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-bold px-2.5 py-0.5 rounded-full bg-indigo-50 text-indigo-700 border border-indigo-200">
                            {trgInfo?.label || wf.trigger_type}
                          </span>
                          <span className="text-xs text-slate-400 font-medium">
                            {wf.steps.length} Steps • {wf.runs_count || 0} Runs
                          </span>
                        </div>
                        <h3 className="text-lg font-bold text-slate-900">{wf.name}</h3>
                        {wf.description && <p className="text-xs text-slate-500">{wf.description}</p>}
                      </div>

                      <div className="flex items-center gap-3">
                        <label className="relative inline-flex items-center cursor-pointer">
                          <input
                            type="checkbox"
                            checked={wf.is_active}
                            onChange={() => handleToggleWorkflow(wf)}
                            className="sr-only peer"
                          />
                          <div className="w-11 h-6 bg-slate-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-emerald-600"></div>
                        </label>
                        <button
                          onClick={() => handleDeleteWorkflow(wf.id)}
                          className="p-2 text-slate-400 hover:text-red-600 rounded-lg hover:bg-red-50 transition"
                          title="Delete workflow"
                        >
                          🗑️
                        </button>
                      </div>
                    </div>

                    {/* Step Visual Chain */}
                    <div className="mt-4 pt-4 border-t border-slate-100 flex flex-wrap items-center gap-2">
                      <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider mr-1">Steps:</span>
                      {wf.steps.map((s, idx) => (
                        <div key={idx} className="flex items-center gap-2">
                          <div className="bg-slate-100 border border-slate-200 text-slate-800 text-xs px-2.5 py-1 rounded-lg font-medium flex items-center gap-1.5">
                            <span className="w-4 h-4 rounded-full bg-indigo-600 text-white text-[10px] font-bold flex items-center justify-center">
                              {s.step_order}
                            </span>
                            {s.name}
                          </div>
                          {idx < wf.steps.length - 1 && (
                            <span className="text-slate-300 text-sm">➔</span>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      ) : activeTab === "templates" ? (
        /* TEMPLATES TAB */
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-bold text-slate-800">Pre-Packaged Automation Templates</h2>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {templates.map((tpl) => (
              <div key={tpl.id} className="bg-white rounded-2xl border border-slate-200 p-6 flex flex-col justify-between shadow-sm hover:shadow-md transition">
                <div className="space-y-3">
                  <span className="text-xs font-bold px-2.5 py-1 rounded-full bg-purple-50 text-purple-700 border border-purple-200 inline-block">
                    {TRIGGER_TYPES.find(t => t.value === tpl.trigger_type)?.label || tpl.trigger_type}
                  </span>
                  <h3 className="text-lg font-bold text-slate-900">{tpl.name}</h3>
                  <p className="text-xs text-slate-500 leading-relaxed">{tpl.description}</p>

                  <div className="space-y-1.5 pt-2">
                    <p className="text-xs font-bold text-slate-700 uppercase">Included Step Chain:</p>
                    {tpl.steps.map((st, i) => (
                      <div key={i} className="text-xs text-slate-600 bg-slate-50 p-2 rounded-lg border border-slate-100 flex items-center gap-2">
                        <span className="font-bold text-indigo-600">{i + 1}.</span> {st.name}
                      </div>
                    ))}
                  </div>
                </div>

                <button
                  onClick={() => handleEnableTemplate(tpl.id)}
                  className="mt-6 w-full py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white font-bold text-xs rounded-xl shadow transition"
                >
                  ⚡ Enable Pre-Built Template
                </button>
              </div>
            ))}
          </div>
        </div>
      ) : (
        /* RUNS AUDIT LOGS TAB */
        <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm space-y-4">
          <div className="flex items-center justify-between border-b border-slate-100 pb-4">
            <h2 className="text-lg font-bold text-slate-800">Workflow Run Execution History</h2>
            <button
              onClick={loadAll}
              className="text-xs bg-slate-100 hover:bg-slate-200 text-slate-700 px-3 py-1.5 rounded-lg font-medium"
            >
              🔄 Refresh Logs
            </button>
          </div>

          {runs.length === 0 ? (
            <div className="p-8 text-center text-slate-400 text-sm">
              No workflow executions logged yet. Use <strong>⚡ Test Event Simulation</strong> above to trigger a test run.
            </div>
          ) : (
            <div className="divide-y divide-slate-100">
              {runs.map((r) => {
                const isSuccess = r.status === "success";
                return (
                  <div key={r.id} className="py-4 space-y-2">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className={`text-xs font-bold px-2.5 py-0.5 rounded-full ${
                          isSuccess ? "bg-emerald-100 text-emerald-800" : "bg-red-100 text-red-800"
                        }`}>
                          {r.status.toUpperCase()}
                        </span>
                        <h4 className="font-bold text-sm text-slate-900">{r.workflow_name}</h4>
                        <span className="text-xs text-slate-400">({r.trigger_event})</span>
                      </div>
                      <span className="text-xs text-slate-400">{r.started_at ? new Date(r.started_at).toLocaleString() : ""}</span>
                    </div>

                    {r.error_message && (
                      <p className="text-xs text-red-600 bg-red-50 p-2 rounded border border-red-200 font-mono">
                        Error: {r.error_message}
                      </p>
                    )}

                    {/* Step Runs */}
                    <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2 pt-1">
                      {r.steps.map((sr) => (
                        <div key={sr.id} className="p-2 bg-slate-50 border border-slate-200 rounded-lg text-xs space-y-1">
                          <div className="flex items-center justify-between">
                            <span className="font-bold text-slate-700">Step {sr.step_order}: {sr.action_type}</span>
                            <span className={`text-[10px] font-bold px-1.5 py-0.2 rounded ${
                              sr.status === "success" ? "bg-emerald-200 text-emerald-900" : "bg-slate-200 text-slate-700"
                            }`}>{sr.status}</span>
                          </div>
                          {sr.output && (
                            <p className="text-[11px] text-slate-500 font-mono truncate">{JSON.stringify(sr.output)}</p>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* CREATE / EDIT WORKFLOW MODAL */}
      {showModal && (
        <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-sm flex items-center justify-center p-4 z-50 overflow-y-auto">
          <div className="bg-white rounded-2xl max-w-2xl w-full p-6 shadow-2xl space-y-6 my-8">
            <h3 className="text-xl font-bold text-slate-800">
              {editingId ? "Edit Workflow" : "Create Custom Workflow"}
            </h3>

            <form onSubmit={handleSaveWorkflow} className="space-y-4">
              <div>
                <label className="block text-xs font-bold text-slate-700 uppercase mb-1">Workflow Name</label>
                <input
                  type="text"
                  required
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Payment Received -> Send Receipt & WhatsApp"
                  className="w-full p-2.5 border border-slate-200 rounded-xl text-sm focus:ring-2 focus:ring-indigo-500"
                />
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-700 uppercase mb-1">Trigger Event</label>
                <select
                  value={triggerType}
                  onChange={(e) => setTriggerType(e.target.value)}
                  className="w-full p-2.5 border border-slate-200 rounded-xl text-sm focus:ring-2 focus:ring-indigo-500"
                >
                  {TRIGGER_TYPES.map((t) => (
                    <option key={t.value} value={t.value}>{t.label} — {t.desc}</option>
                  ))}
                </select>
              </div>

              {/* Step Chain Builder */}
              <div className="space-y-3 pt-2">
                <div className="flex items-center justify-between">
                  <label className="block text-xs font-bold text-slate-700 uppercase">Action Step Sequence</label>
                  <button
                    type="button"
                    onClick={handleAddStep}
                    className="text-xs font-bold text-indigo-600 hover:text-indigo-800"
                  >
                    + Add Step
                  </button>
                </div>

                <div className="space-y-3">
                  {steps.map((st, idx) => (
                    <div key={idx} className="p-3 bg-slate-50 border border-slate-200 rounded-xl space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold text-indigo-700">Step {idx + 1}</span>
                        {steps.length > 1 && (
                          <button
                            type="button"
                            onClick={() => handleRemoveStep(idx)}
                            className="text-xs text-red-500 hover:underline"
                          >
                            Remove
                          </button>
                        )}
                      </div>
                      <div className="grid grid-cols-2 gap-2">
                        <input
                          type="text"
                          value={st.name}
                          onChange={(e) => {
                            const updated = [...steps];
                            updated[idx].name = e.target.value;
                            setSteps(updated);
                          }}
                          placeholder="Step Name"
                          className="p-2 border border-slate-200 rounded-lg text-xs"
                        />
                        <select
                          value={st.action_type}
                          onChange={(e) => {
                            const updated = [...steps];
                            updated[idx].action_type = e.target.value;
                            setSteps(updated);
                          }}
                          className="p-2 border border-slate-200 rounded-lg text-xs"
                        >
                          {ACTION_TYPES.map((a) => (
                            <option key={a.value} value={a.value}>{a.label}</option>
                          ))}
                        </select>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="flex justify-end gap-2 pt-4 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setShowModal(false)}
                  className="px-4 py-2 text-sm text-slate-600 hover:bg-slate-100 rounded-xl"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-5 py-2 text-sm font-bold bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl shadow"
                >
                  Save Workflow
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* TEST TRIGGER SIMULATION MODAL */}
      {showTestModal && (
        <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-2xl max-w-md w-full p-6 shadow-2xl space-y-4">
            <h3 className="text-lg font-bold text-slate-800">⚡ Test Workflow Event Simulation</h3>
            <p className="text-xs text-slate-500">Fire a test event to test all active matching workflows end-to-end.</p>

            <div>
              <label className="block text-xs font-bold text-slate-700 uppercase mb-1">Select Event Type</label>
              <select
                value={testTriggerType}
                onChange={(e) => setTestTriggerType(e.target.value)}
                className="w-full p-3 border border-slate-200 rounded-xl text-sm focus:ring-2 focus:ring-amber-500"
              >
                {TRIGGER_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>{t.label}</option>
                ))}
              </select>
            </div>

            {testResults && (
              <div className="p-3 bg-slate-900 text-emerald-400 font-mono text-xs rounded-xl overflow-x-auto max-h-48">
                <pre>{JSON.stringify(testResults, null, 2)}</pre>
              </div>
            )}

            <div className="flex justify-end gap-2 pt-2">
              <button
                onClick={() => setShowTestModal(false)}
                className="px-4 py-2 text-sm text-slate-600 hover:bg-slate-100 rounded-xl"
              >
                Close
              </button>
              <button
                onClick={handleRunTestTrigger}
                disabled={testTesting}
                className="px-5 py-2 text-sm font-bold bg-amber-500 hover:bg-amber-600 text-slate-900 rounded-xl shadow disabled:opacity-50"
              >
                {testTesting ? "Simulating..." : "🔥 Fire Test Event"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
