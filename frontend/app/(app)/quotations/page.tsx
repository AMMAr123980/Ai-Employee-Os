"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, Quotation, Customer, exportDataFile } from "@/lib/api";
import StatusBadge from "@/components/StatusBadge";

export default function QuotationsPage() {
  const [quotations, setQuotations] = useState<Quotation[]>([]);
  const [customers, setCustomers] = useState<Record<string, Customer>>({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      const [qs, cs] = await Promise.all([api.listQuotations(), api.listCustomers()]);
      setQuotations(qs);
      setCustomers(Object.fromEntries(cs.map((c) => [c.id, c])));
      setLoading(false);
    })();
  }, []);

  return (
    <div>
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-semibold">Quotations</h1>
          <p className="text-xs text-slate-500">Manage client proposals & export history</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => exportDataFile("quotations", "xlsx")}
            className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-medium text-slate-700 hover:bg-slate-50"
          >
            📊 Export Excel
          </button>
          <button
            onClick={() => exportDataFile("quotations", "csv")}
            className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-medium text-slate-700 hover:bg-slate-50"
          >
            📄 Export CSV
          </button>
          <Link
            href="/quotations/new"
            className="rounded-lg bg-brand-600 text-white px-4 py-2 text-xs font-medium hover:bg-brand-700 ml-2"
          >
            + New Quotation
          </Link>
        </div>
      </div>

      <div className="rounded-xl border border-slate-200 bg-white overflow-hidden">
        {loading ? (
          <p className="p-5 text-sm text-slate-400">Loading…</p>
        ) : quotations.length === 0 ? (
          <p className="p-5 text-sm text-slate-400">
            No quotations yet.{" "}
            <Link href="/quotations/new" className="text-brand-600 underline">
              Create one
            </Link>
            .
          </p>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-slate-500 text-xs uppercase">
              <tr>
                <th className="px-4 py-3">Number</th>
                <th className="px-4 py-3">Customer</th>
                <th className="px-4 py-3">Total</th>
                <th className="px-4 py-3">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {quotations.map((q) => (
                <tr key={q.id} className="hover:bg-slate-50">
                  <td className="px-4 py-3">
                    <Link href={`/quotations/${q.id}`} className="font-medium text-brand-700">
                      {q.number}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-slate-500">
                    {customers[q.customer_id]?.name || "—"}
                  </td>
                  <td className="px-4 py-3">
                    {q.currency} {q.total.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={q.status} />
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
