"use client";

import { useEffect, useState, useRef } from "react";
import Link from "next/link";
import {
  Users,
  Plus,
  Search,
  FileSpreadsheet,
  FileText,
  UploadCloud,
  Download,
  Building2,
  Mail,
  Phone,
  ArrowUpDown,
  Sparkles,
  X,
} from "lucide-react";
import { api, Customer, PipelineStage, exportDataFile, importDataFile, downloadSampleTemplate } from "@/lib/api";

const STAGE_LABELS: Record<PipelineStage, string> = {
  new: "New Lead",
  contacted: "Contacted",
  qualified: "Qualified",
  proposal: "Proposal Sent",
  negotiation: "In Negotiation",
  won: "Closed Won",
  lost: "Closed Lost",
};

const STAGE_STYLES: Record<PipelineStage, { bg: string; text: string; dot: string; border: string }> = {
  new: { bg: "bg-slate-50", text: "text-slate-700", dot: "bg-slate-400", border: "border-slate-200" },
  contacted: { bg: "bg-blue-50/80", text: "text-blue-700", dot: "bg-blue-500", border: "border-blue-200/60" },
  qualified: { bg: "bg-indigo-50/80", text: "text-indigo-700", dot: "bg-indigo-500", border: "border-indigo-200/60" },
  proposal: { bg: "bg-purple-50/80", text: "text-purple-700", dot: "bg-purple-500", border: "border-purple-200/60" },
  negotiation: { bg: "bg-amber-50/80", text: "text-amber-700", dot: "bg-amber-500", border: "border-amber-200/60" },
  won: { bg: "bg-emerald-50/80", text: "text-emerald-700", dot: "bg-emerald-500", border: "border-emerald-200/60" },
  lost: { bg: "bg-rose-50/80", text: "text-rose-700", dot: "bg-rose-500", border: "border-rose-200/60" },
};

export default function CustomersPage() {
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({ name: "", company: "", email: "", phone: "", address: "", lead_source: "" });
  const [importing, setImporting] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  async function load() {
    setLoading(true);
    try {
      setCustomers(await api.listCustomers());
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function handleFileImport(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setImporting(true);
    setMsg(null);
    try {
      const res = await importDataFile("customers", file);
      setMsg(`Imported ${res.imported_count} customers (${res.skipped_count} skipped/duplicates)`);
      await load();
    } catch (err: any) {
      setMsg(`Import error: ${err.message}`);
    } finally {
      setImporting(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!form.name.trim()) return;
    setSaving(true);
    try {
      await api.createCustomer(form);
      setForm({ name: "", company: "", email: "", phone: "", address: "", lead_source: "" });
      setShowForm(false);
      await load();
    } finally {
      setSaving(false);
    }
  }

  const filteredCustomers = customers.filter((c) => {
    if (!search.trim()) return true;
    const q = search.toLowerCase();
    return (
      c.name.toLowerCase().includes(q) ||
      (c.company && c.company.toLowerCase().includes(q)) ||
      (c.email && c.email.toLowerCase().includes(q)) ||
      (c.phone && c.phone.includes(q))
    );
  });

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="inline-flex items-center gap-1.5 rounded-full bg-blue-50 px-2.5 py-0.5 text-xs font-semibold text-blue-700 border border-blue-200/60 mb-2">
            <Users className="h-3.5 w-3.5" />
            <span>CRM & Contact Database</span>
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">Customers & Accounts</h1>
          <p className="text-xs md:text-sm text-slate-500">
            Manage your accounts, track lead sources, and sync CRM deals.
          </p>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-2 flex-wrap">
          <button
            onClick={() => exportDataFile("customers", "xlsx")}
            className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-700 shadow-2xs hover:bg-slate-50 transition"
          >
            <FileSpreadsheet className="h-3.5 w-3.5 text-emerald-600" />
            <span>Excel</span>
          </button>
          <button
            onClick={() => exportDataFile("customers", "csv")}
            className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-700 shadow-2xs hover:bg-slate-50 transition"
          >
            <FileText className="h-3.5 w-3.5 text-blue-600" />
            <span>CSV</span>
          </button>
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={importing}
            className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-700 shadow-2xs hover:bg-slate-50 disabled:opacity-50 transition"
          >
            <UploadCloud className="h-3.5 w-3.5 text-brand-600" />
            <span>{importing ? "Importing..." : "Bulk Import"}</span>
          </button>
          <button
            onClick={() => downloadSampleTemplate("customers")}
            className="text-xs text-brand-600 hover:text-brand-700 font-medium px-2 py-1"
          >
            Sample Template
          </button>
          <input
            type="file"
            ref={fileInputRef}
            onChange={handleFileImport}
            accept=".csv,.xlsx"
            className="hidden"
          />
          <button
            onClick={() => setShowForm((v) => !v)}
            className="inline-flex items-center gap-1.5 rounded-xl bg-brand-600 px-4 py-2 text-xs font-semibold text-white shadow-sm hover:bg-brand-700 transition ml-1"
          >
            {showForm ? <X className="h-3.5 w-3.5" /> : <Plus className="h-3.5 w-3.5" />}
            <span>{showForm ? "Cancel" : "Add Customer"}</span>
          </button>
        </div>
      </div>

      {msg && (
        <div className="rounded-xl bg-brand-50 border border-brand-200/80 p-3.5 text-xs text-brand-900 flex justify-between items-center">
          <span>{msg}</span>
          <button onClick={() => setMsg(null)} className="font-bold hover:text-brand-950">×</button>
        </div>
      )}

      {/* New Customer Form Drawer */}
      {showForm && (
        <form
          onSubmit={handleSubmit}
          className="rounded-2xl border border-brand-200 bg-white p-6 shadow-md grid grid-cols-1 md:grid-cols-2 gap-4 animate-in fade-in duration-200"
        >
          <div className="md:col-span-2 flex items-center justify-between border-b border-slate-100 pb-3">
            <h2 className="text-sm font-bold text-slate-900 flex items-center gap-2">
              <Plus className="h-4 w-4 text-brand-600" />
              <span>Create New Customer Account</span>
            </h2>
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1">Contact Name *</label>
            <input
              required
              placeholder="e.g. Sarah Connor"
              className="w-full rounded-xl border border-slate-200 bg-slate-50/50 px-3 py-2 text-xs text-slate-800 outline-none focus:border-brand-500 focus:bg-white focus:ring-2 focus:ring-brand-500/10"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1">Company / Organization</label>
            <input
              placeholder="e.g. Cyberdyne Systems"
              className="w-full rounded-xl border border-slate-200 bg-slate-50/50 px-3 py-2 text-xs text-slate-800 outline-none focus:border-brand-500 focus:bg-white focus:ring-2 focus:ring-brand-500/10"
              value={form.company}
              onChange={(e) => setForm({ ...form, company: e.target.value })}
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1">Email Address</label>
            <input
              type="email"
              placeholder="sarah@example.com"
              className="w-full rounded-xl border border-slate-200 bg-slate-50/50 px-3 py-2 text-xs text-slate-800 outline-none focus:border-brand-500 focus:bg-white focus:ring-2 focus:ring-brand-500/10"
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1">Phone Number</label>
            <input
              placeholder="+1 555 019 2831"
              className="w-full rounded-xl border border-slate-200 bg-slate-50/50 px-3 py-2 text-xs text-slate-800 outline-none focus:border-brand-500 focus:bg-white focus:ring-2 focus:ring-brand-500/10"
              value={form.phone}
              onChange={(e) => setForm({ ...form, phone: e.target.value })}
            />
          </div>

          <div className="md:col-span-2">
            <label className="block text-xs font-semibold text-slate-700 mb-1">Billing / Shipping Address</label>
            <textarea
              rows={2}
              placeholder="Full street address, city, country..."
              className="w-full rounded-xl border border-slate-200 bg-slate-50/50 p-3 text-xs text-slate-800 outline-none focus:border-brand-500 focus:bg-white focus:ring-2 focus:ring-brand-500/10"
              value={form.address}
              onChange={(e) => setForm({ ...form, address: e.target.value })}
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1">Lead Source</label>
            <input
              placeholder="e.g. Website, Referral, Cold Email"
              className="w-full rounded-xl border border-slate-200 bg-slate-50/50 px-3 py-2 text-xs text-slate-800 outline-none focus:border-brand-500 focus:bg-white focus:ring-2 focus:ring-brand-500/10"
              value={form.lead_source}
              onChange={(e) => setForm({ ...form, lead_source: e.target.value })}
            />
          </div>

          <div className="md:col-span-2 flex justify-end gap-2 pt-3 border-t border-slate-100">
            <button
              type="button"
              onClick={() => setShowForm(false)}
              className="rounded-xl border border-slate-200 px-4 py-2 text-xs font-medium text-slate-600 hover:bg-slate-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving}
              className="rounded-xl bg-brand-600 px-5 py-2 text-xs font-semibold text-white hover:bg-brand-700 disabled:opacity-50 shadow-sm"
            >
              {saving ? "Saving..." : "Save Customer"}
            </button>
          </div>
        </form>
      )}

      {/* Filter and Search Bar */}
      <div className="flex items-center gap-3 rounded-2xl border border-slate-200/80 bg-white p-3 shadow-2xs">
        <Search className="h-4 w-4 text-slate-400 shrink-0 ml-1" />
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Filter by customer name, company, email, or phone..."
          className="w-full bg-transparent text-xs md:text-sm text-slate-800 placeholder-slate-400 outline-none"
        />
        {search && (
          <button
            onClick={() => setSearch("")}
            className="text-xs text-slate-400 hover:text-slate-600 mr-1"
          >
            Clear
          </button>
        )}
      </div>

      {/* Modern 21st.dev Table */}
      <div className="overflow-hidden rounded-2xl border border-slate-200/80 bg-white shadow-2xs">
        {loading ? (
          <div className="flex h-48 items-center justify-center text-xs text-slate-400">
            <Sparkles className="h-4 w-4 animate-spin text-brand-600 mr-2" />
            <span>Loading Customers...</span>
          </div>
        ) : filteredCustomers.length === 0 ? (
          <div className="p-12 text-center text-xs text-slate-400">
            No matching customers found.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50/80 text-slate-500 font-semibold border-b border-slate-200/60">
                <tr>
                  <th className="py-3 px-4">Contact</th>
                  <th className="py-3 px-4">Company</th>
                  <th className="py-3 px-4">Email</th>
                  <th className="py-3 px-4">Phone</th>
                  <th className="py-3 px-4">Pipeline Stage</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filteredCustomers.map((c) => {
                  const stageStyle = STAGE_STYLES[c.pipeline_stage] || STAGE_STYLES.new;
                  return (
                    <tr key={c.id} className="hover:bg-slate-50/50 transition">
                      <td className="py-3 px-4">
                        <Link
                          href={`/customers/${c.id}`}
                          className="font-bold text-slate-900 hover:text-brand-600 transition"
                        >
                          {c.name}
                        </Link>
                      </td>
                      <td className="py-3 px-4 text-slate-600">
                        {c.company ? (
                          <div className="flex items-center gap-1.5">
                            <Building2 className="h-3.5 w-3.5 text-slate-400" />
                            <span>{c.company}</span>
                          </div>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td className="py-3 px-4 text-slate-600">
                        {c.email ? (
                          <div className="flex items-center gap-1.5">
                            <Mail className="h-3.5 w-3.5 text-slate-400" />
                            <span>{c.email}</span>
                          </div>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td className="py-3 px-4 text-slate-600">
                        {c.phone ? (
                          <div className="flex items-center gap-1.5">
                            <Phone className="h-3.5 w-3.5 text-slate-400" />
                            <span>{c.phone}</span>
                          </div>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td className="py-3 px-4">
                        <span
                          className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-medium shadow-2xs ${stageStyle.bg} ${stageStyle.text} ${stageStyle.border}`}
                        >
                          <span className={`h-1.5 w-1.5 rounded-full ${stageStyle.dot}`} />
                          <span>{STAGE_LABELS[c.pipeline_stage] || c.pipeline_stage}</span>
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
