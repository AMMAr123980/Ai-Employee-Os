"use client";

import { use, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, Quotation, Customer } from "@/lib/api";
import StatusBadge from "@/components/StatusBadge";
import SendEmailPanel from "@/components/SendEmailPanel";

export default function QuotationDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();
  const [quotation, setQuotation] = useState<Quotation | null>(null);
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [converting, setConverting] = useState(false);
  const [showRecurringOptions, setShowRecurringOptions] = useState(false);
  const [makeRecurring, setMakeRecurring] = useState(false);
  const [recurrenceDays, setRecurrenceDays] = useState("30");
  const [error, setError] = useState<string | null>(null);

  async function load() {
    const q = await api.getQuotation(id);
    setQuotation(q);
    setCustomer(await api.getCustomer(q.customer_id));
  }

  useEffect(() => {
    load();
  }, [id]);

  async function handleStatus(status: Quotation["status"]) {
    if (!quotation) return;
    setQuotation(await api.updateQuotationStatus(quotation.id, status));
  }

  async function handleConvert() {
    if (!quotation) return;
    setConverting(true);
    setError(null);
    try {
      const invoice = await api.convertToInvoice(quotation.id, {
        is_recurring: makeRecurring,
        recurrence_interval_days: makeRecurring ? parseInt(recurrenceDays, 10) : undefined,
      });
      router.push(`/invoices/${invoice.id}`);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setConverting(false);
    }
  }

  if (!quotation || !customer) {
    return <p className="text-sm text-slate-400">Loading…</p>;
  }

  return (
    <div className="max-w-4xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold">{quotation.number}</h1>
          <p className="text-slate-500 text-sm">
            {customer.name} {customer.company ? `· ${customer.company}` : ""}
          </p>
        </div>
        <StatusBadge status={quotation.status} />
      </div>

      <div className="flex flex-wrap gap-2 mb-6">
        <button
          onClick={() => api.openQuotationPdf(quotation.id)}
          className="rounded-lg bg-brand-600 text-white px-4 py-2 text-sm font-medium hover:bg-brand-700"
        >
          View / Download PDF
        </button>
        {quotation.status === "draft" && (
          <button
            onClick={() => handleStatus("sent")}
            className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium hover:bg-slate-100"
          >
            Mark as Sent
          </button>
        )}
        {(quotation.status === "sent" || quotation.status === "draft") && (
          <button
            onClick={() => handleStatus("approved")}
            className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium hover:bg-slate-100"
          >
            Mark as Approved
          </button>
        )}
        {quotation.status !== "converted" && (
          <button
            onClick={() => setShowRecurringOptions((v) => !v)}
            className="rounded-lg border border-brand-300 text-brand-700 px-4 py-2 text-sm font-medium hover:bg-brand-50"
          >
            Convert to Invoice
          </button>
        )}
      </div>

      {showRecurringOptions && quotation.status !== "converted" && (
        <div className="rounded-xl border border-slate-200 bg-white p-4 mb-6 space-y-3">
          <label className="flex items-center gap-2 text-sm text-slate-600">
            <input
              type="checkbox"
              checked={makeRecurring}
              onChange={(e) => setMakeRecurring(e.target.checked)}
            />
            Make this a recurring invoice
          </label>
          {makeRecurring && (
            <div className="flex items-center gap-2 text-sm text-slate-600">
              <span>Repeat every</span>
              <input
                type="number"
                min={1}
                className="w-16 rounded-lg border border-slate-300 px-2 py-1 text-sm"
                value={recurrenceDays}
                onChange={(e) => setRecurrenceDays(e.target.value)}
              />
              <span>day(s) — the next occurrence is generated automatically and ready to send.</span>
            </div>
          )}
          <button
            onClick={handleConvert}
            disabled={converting}
            className="rounded-lg bg-brand-600 text-white px-4 py-2 text-sm font-medium hover:bg-brand-700 disabled:opacity-50"
          >
            {converting ? "Converting…" : "Confirm & Create Invoice"}
          </button>
        </div>
      )}

      <div className="mb-6">
        <SendEmailPanel
          customerId={customer.id}
          customerEmail={customer.email}
          quotationId={quotation.id}
          onSent={() => handleStatus("sent")}
        />
      </div>

      {error && <p className="text-sm text-red-500 mb-4">{error}</p>}

      {quotation.ai_summary && (
        <div className="mb-6 rounded-xl border border-brand-100 bg-brand-50 p-4 text-sm italic text-brand-700">
          {quotation.ai_summary}
        </div>
      )}

      <div className="rounded-xl border border-slate-200 bg-white overflow-hidden mb-6">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-slate-500 text-xs uppercase">
            <tr>
              <th className="px-4 py-3">Description</th>
              <th className="px-4 py-3 text-right">Qty</th>
              <th className="px-4 py-3 text-right">Unit Price</th>
              <th className="px-4 py-3 text-right">Line Total</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {quotation.items.map((item) => (
              <tr key={item.id}>
                <td className="px-4 py-3">{item.description}</td>
                <td className="px-4 py-3 text-right">{item.quantity}</td>
                <td className="px-4 py-3 text-right">{item.unit_price.toFixed(2)}</td>
                <td className="px-4 py-3 text-right">{item.line_total?.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="text-right text-sm space-y-1">
        <p className="text-slate-500">Subtotal: {quotation.currency} {quotation.subtotal.toFixed(2)}</p>
        {quotation.discount_percent > 0 && (
          <p className="text-slate-500">Discount: {quotation.discount_percent}%</p>
        )}
        {quotation.tax_percent > 0 && <p className="text-slate-500">Tax: {quotation.tax_percent}%</p>}
        <p className="text-lg font-semibold text-brand-700">
          Total: {quotation.currency} {quotation.total.toFixed(2)}
        </p>
      </div>
    </div>
  );
}
