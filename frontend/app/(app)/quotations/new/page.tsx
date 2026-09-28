"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, Customer, LineItem } from "@/lib/api";

const emptyItem = (): LineItem => ({ description: "", quantity: 1, unit_price: 0 });

export default function NewQuotationPage() {
  const router = useRouter();
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [customerId, setCustomerId] = useState("");
  const [items, setItems] = useState<LineItem[]>([emptyItem()]);
  const [discount, setDiscount] = useState(0);
  const [tax, setTax] = useState(0);
  const [notes, setNotes] = useState("");
  const [aiPrompt, setAiPrompt] = useState("");
  const [aiLoading, setAiLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.listCustomers().then(setCustomers);
  }, []);

  const subtotal = items.reduce((s, i) => s + i.quantity * i.unit_price, 0);
  const discountAmount = subtotal * (discount / 100);
  const taxAmount = (subtotal - discountAmount) * (tax / 100);
  const total = subtotal - discountAmount + taxAmount;

  function updateItem(idx: number, patch: Partial<LineItem>) {
    setItems((prev) => prev.map((it, i) => (i === idx ? { ...it, ...patch } : it)));
  }

  function addItem() {
    setItems((prev) => [...prev, emptyItem()]);
  }

  function removeItem(idx: number) {
    setItems((prev) => prev.filter((_, i) => i !== idx));
  }

  async function handleAiDraft() {
    if (!aiPrompt.trim()) return;
    setAiLoading(true);
    setError(null);
    try {
      const result = await api.aiDraftItems(aiPrompt);
      setItems(result.items.length ? result.items : [emptyItem()]);
      if (result.suggested_notes) setNotes(result.suggested_notes);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setAiLoading(false);
    }
  }

  async function handleSubmit() {
    if (!customerId) {
      setError("Select a customer first.");
      return;
    }
    const validItems = items.filter((i) => i.description.trim());
    if (!validItems.length) {
      setError("Add at least one line item.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const quotation = await api.createQuotation({
        customer_id: customerId,
        items: validItems,
        discount_percent: discount,
        tax_percent: tax,
        notes: notes || undefined,
        generate_ai_summary: true,
      });
      router.push(`/quotations/${quotation.id}`);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="max-w-3xl">
      <h1 className="text-2xl font-semibold mb-6">New Quotation</h1>

      {/* AI draft box */}
      <div className="mb-6 rounded-xl border border-brand-100 bg-brand-50 p-4">
        <label className="block text-sm font-medium text-brand-700 mb-2">
          Describe it in plain English — AI drafts the line items
        </label>
        <div className="flex gap-2">
          <input
            className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm"
            placeholder="e.g. Quotation for 25 Dell laptops at $600 each and 25 wireless mice at $15"
            value={aiPrompt}
            onChange={(e) => setAiPrompt(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleAiDraft()}
          />
          <button
            onClick={handleAiDraft}
            disabled={aiLoading}
            className="rounded-lg bg-brand-600 text-white px-4 py-2 text-sm font-medium hover:bg-brand-700 disabled:opacity-50 whitespace-nowrap"
          >
            {aiLoading ? "Drafting…" : "AI Draft"}
          </button>
        </div>
        <p className="text-xs text-brand-500 mt-2">
          Without an ANTHROPIC_API_KEY configured on the backend, this falls back to adding your
          text as a single editable line item.
        </p>
      </div>

      <div className="rounded-xl border border-slate-200 bg-white p-5 space-y-5">
        <div>
          <label className="block text-sm font-medium mb-1">Customer</label>
          <select
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            value={customerId}
            onChange={(e) => setCustomerId(e.target.value)}
          >
            <option value="">Select a customer…</option>
            {customers.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name} {c.company ? `(${c.company})` : ""}
              </option>
            ))}
          </select>
          {customers.length === 0 && (
            <p className="text-xs text-slate-400 mt-1">
              No customers yet — add one on the Customers page first.
            </p>
          )}
        </div>

        <div>
          <label className="block text-sm font-medium mb-2">Line Items</label>
          <div className="space-y-2">
            {items.map((item, idx) => (
              <div key={idx} className="flex gap-2 items-center">
                <input
                  className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm"
                  placeholder="Description"
                  value={item.description}
                  onChange={(e) => updateItem(idx, { description: e.target.value })}
                />
                <input
                  type="number"
                  className="w-20 rounded-lg border border-slate-300 px-3 py-2 text-sm"
                  placeholder="Qty"
                  value={item.quantity}
                  onChange={(e) => updateItem(idx, { quantity: parseFloat(e.target.value) || 0 })}
                />
                <input
                  type="number"
                  className="w-28 rounded-lg border border-slate-300 px-3 py-2 text-sm"
                  placeholder="Unit price"
                  value={item.unit_price}
                  onChange={(e) => updateItem(idx, { unit_price: parseFloat(e.target.value) || 0 })}
                />
                <span className="w-24 text-right text-sm text-slate-500">
                  {(item.quantity * item.unit_price).toFixed(2)}
                </span>
                <button
                  onClick={() => removeItem(idx)}
                  className="text-slate-400 hover:text-red-500 px-1"
                  aria-label="Remove item"
                >
                  ✕
                </button>
              </div>
            ))}
          </div>
          <button onClick={addItem} className="mt-2 text-sm text-brand-600 hover:underline">
            + Add line item
          </button>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium mb-1">Discount %</label>
            <input
              type="number"
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              value={discount}
              onChange={(e) => setDiscount(parseFloat(e.target.value) || 0)}
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Tax %</label>
            <input
              type="number"
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              value={tax}
              onChange={(e) => setTax(parseFloat(e.target.value) || 0)}
            />
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium mb-1">Notes</label>
          <textarea
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
          />
        </div>

        <div className="border-t border-slate-100 pt-4 text-right space-y-1 text-sm">
          <p className="text-slate-500">Subtotal: {subtotal.toFixed(2)}</p>
          {discount > 0 && <p className="text-slate-500">Discount: -{discountAmount.toFixed(2)}</p>}
          {tax > 0 && <p className="text-slate-500">Tax: {taxAmount.toFixed(2)}</p>}
          <p className="text-lg font-semibold text-brand-700">Total: {total.toFixed(2)}</p>
        </div>

        {error && <p className="text-sm text-red-500">{error}</p>}

        <button
          onClick={handleSubmit}
          disabled={saving}
          className="w-full rounded-lg bg-brand-600 text-white px-4 py-2.5 text-sm font-medium hover:bg-brand-700 disabled:opacity-50"
        >
          {saving ? "Creating…" : "Create Quotation"}
        </button>
      </div>
    </div>
  );
}
