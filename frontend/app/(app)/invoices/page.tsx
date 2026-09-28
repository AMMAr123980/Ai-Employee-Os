"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, Invoice, Customer, exportDataFile } from "@/lib/api";
import StatusBadge from "@/components/StatusBadge";

export default function InvoicesPage() {
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [customers, setCustomers] = useState<Record<string, Customer>>({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      const [is, cs] = await Promise.all([api.listInvoices(), api.listCustomers()]);
      setInvoices(is);
      setCustomers(Object.fromEntries(cs.map((c) => [c.id, c])));
      setLoading(false);
    })();
  }, []);

  return (
    <div>
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-semibold">Invoices</h1>
          <p className="text-xs text-slate-500">Track client billing & export financial records</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => exportDataFile("invoices", "xlsx")}
            className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-medium text-slate-700 hover:bg-slate-50"
          >
            📊 Export Excel
          </button>
          <button
            onClick={() => exportDataFile("invoices", "csv")}
            className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-medium text-slate-700 hover:bg-slate-50"
          >
            📄 Export CSV
          </button>
        </div>
      </div>

      <div className="rounded-xl border border-slate-200 bg-white overflow-hidden">
        {loading ? (
          <p className="p-5 text-sm text-slate-400">Loading…</p>
        ) : invoices.length === 0 ? (
          <p className="p-5 text-sm text-slate-400">
            No invoices yet. Convert a quotation, or create one from an approved quotation.
          </p>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-slate-500 text-xs uppercase">
              <tr>
                <th className="px-4 py-3">Number</th>
                <th className="px-4 py-3">Customer</th>
                <th className="px-4 py-3">Total</th>
                <th className="px-4 py-3">Paid</th>
                <th className="px-4 py-3">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {invoices.map((inv) => (
                <tr key={inv.id} className="hover:bg-slate-50">
                  <td className="px-4 py-3">
                    <Link href={`/invoices/${inv.id}`} className="font-medium text-brand-700">
                      {inv.number}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-slate-500">
                    {customers[inv.customer_id]?.name || "—"}
                  </td>
                  <td className="px-4 py-3">
                    {inv.currency} {inv.total.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                  </td>
                  <td className="px-4 py-3 text-slate-500">
                    {inv.currency} {inv.amount_paid.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={inv.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
