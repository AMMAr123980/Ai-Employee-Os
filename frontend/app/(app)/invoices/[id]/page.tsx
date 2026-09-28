"use client";

import { use, useEffect, useState } from "react";
import { api, Invoice, Customer } from "@/lib/api";
import StatusBadge from "@/components/StatusBadge";
import SendEmailPanel from "@/components/SendEmailPanel";

export default function InvoiceDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const [invoice, setInvoice] = useState<Invoice | null>(null);
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [paymentAmount, setPaymentAmount] = useState("");
  const [recording, setRecording] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);
  const [checkMessage, setCheckMessage] = useState<string | null>(null);

  async function load() {
    const inv = await api.getInvoice(id);
    setInvoice(inv);
    setCustomer(await api.getCustomer(inv.customer_id));
  }

  useEffect(() => {
    load();
  }, [id]);

  async function handleRecordPayment() {
    const amount = parseFloat(paymentAmount);
    if (!amount || amount <= 0 || !invoice) return;
    setRecording(true);
    setError(null);
    try {
      setInvoice(await api.recordPayment(invoice.id, amount));
      setPaymentAmount("");
    } catch (e: any) {
      setError(e.message);
    } finally {
      setRecording(false);
    }
  }

  async function handleCheckNow() {
    setChecking(true);
    setCheckMessage(null);
    try {
      const result = await api.checkRecurringNow();
      setCheckMessage(
        result.invoices_created > 0
          ? `Generated ${result.invoices_created} new invoice(s) — check the Invoices list.`
          : "Nothing due yet."
      );
      await load();
    } finally {
      setChecking(false);
    }
  }

  if (!invoice || !customer) {
    return <p className="text-sm text-slate-400">Loading…</p>;
  }

  const balanceDue = invoice.total - invoice.amount_paid;

  return (
    <div className="max-w-4xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold">{invoice.number}</h1>
          <p className="text-slate-500 text-sm">
            {customer.name} {customer.company ? `· ${customer.company}` : ""}
          </p>
        </div>
        <StatusBadge status={invoice.status} />
      </div>

      {invoice.is_recurring && (
        <div className="rounded-xl border border-brand-100 bg-brand-50 p-4 mb-6 flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-brand-700">
              Recurring every {invoice.recurrence_interval_days} day(s)
            </p>
            {invoice.next_recurrence_at && (
              <p className="text-xs text-brand-400">
                Next invoice generates on {new Date(invoice.next_recurrence_at).toLocaleDateString()}
              </p>
            )}
          </div>
          <button
            onClick={handleCheckNow}
            disabled={checking}
            className="text-xs font-medium text-brand-600 hover:underline disabled:opacity-50 whitespace-nowrap"
          >
            {checking ? "Checking…" : "Check Now"}
          </button>
        </div>
      )}
      {invoice.recurrence_parent_id && (
        <p className="text-xs text-slate-400 mb-6">
          Auto-generated from a recurring invoice.
        </p>
      )}
      {checkMessage && <p className="text-sm text-brand-600 mb-4">{checkMessage}</p>}

      <div className="flex flex-wrap items-center gap-3 mb-6">
        <button
          onClick={() => api.openInvoicePdf(invoice.id)}
          className="rounded-lg bg-brand-600 text-white px-4 py-2 text-sm font-medium hover:bg-brand-700"
        >
          View / Download PDF (Includes QR Code)
        </button>
        {invoice.payment_link ? (
          <div className="flex items-center gap-2 bg-emerald-50 text-emerald-800 border border-emerald-200 px-3 py-1.5 rounded-lg text-xs font-semibold">
            <span>📲 Scannable QR Code Active</span>
            <a href={invoice.payment_link} target="_blank" rel="noreferrer" className="underline text-emerald-900">
              {invoice.payment_link}
            </a>
          </div>
        ) : (
          <span className="text-xs text-slate-400">No custom payment link configured</span>
        )}
      </div>


      <div className="mb-6">
        <SendEmailPanel
          customerId={customer.id}
          customerEmail={customer.email}
          invoiceId={invoice.id}
        />
      </div>

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
            {invoice.items.map((item) => (
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

      <div className="grid grid-cols-2 gap-6">
        <div className="rounded-xl border border-slate-200 bg-white p-5">
          <p className="text-sm font-medium mb-3">Record a payment</p>
          <div className="flex gap-2">
            <input
              type="number"
              className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm"
              placeholder="Amount"
              value={paymentAmount}
              onChange={(e) => setPaymentAmount(e.target.value)}
            />
            <button
              onClick={handleRecordPayment}
              disabled={recording}
              className="rounded-lg bg-brand-600 text-white px-4 py-2 text-sm font-medium hover:bg-brand-700 disabled:opacity-50"
            >
              {recording ? "Saving…" : "Record"}
            </button>
          </div>
          {error && <p className="text-sm text-red-500 mt-2">{error}</p>}
        </div>

        <div className="text-right text-sm space-y-1 self-end">
          <p className="text-slate-500">Subtotal: {invoice.currency} {invoice.subtotal.toFixed(2)}</p>
          {invoice.tax_percent > 0 && <p className="text-slate-500">Tax: {invoice.tax_percent}%</p>}
          <p className="text-slate-500">
            Paid: {invoice.currency} {invoice.amount_paid.toFixed(2)}
          </p>
          <p className="text-lg font-semibold text-brand-700">
            Balance Due: {invoice.currency} {balanceDue.toFixed(2)}
          </p>
        </div>
      </div>
    </div>
  );
}
