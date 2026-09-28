"use client";

import { useEffect, useState } from "react";
import {
  api,
  ReportsOverview,
  SalesAnalytics,
  RevenueAnalytics,
  ExpenseAnalytics,
  CustomerAnalytics,
  ProductivityAnalytics,
  PredictiveForecasting,
  AiInsightsResponse,
} from "@/lib/api";

export default function ReportsPage() {
  const [days, setDays] = useState<number>(30);
  const [loading, setLoading] = useState<boolean>(true);
  const [insightsLoading, setInsightsLoading] = useState<boolean>(false);

  const [overview, setOverview] = useState<ReportsOverview | null>(null);
  const [sales, setSales] = useState<SalesAnalytics | null>(null);
  const [revenue, setRevenue] = useState<RevenueAnalytics | null>(null);
  const [expenses, setExpenses] = useState<ExpenseAnalytics | null>(null);
  const [customers, setCustomers] = useState<CustomerAnalytics | null>(null);
  const [productivity, setProductivity] = useState<ProductivityAnalytics | null>(null);
  const [forecasting, setForecasting] = useState<PredictiveForecasting | null>(null);
  const [aiInsights, setAiInsights] = useState<AiInsightsResponse | null>(null);

  useEffect(() => {
    loadAllReports(days);
  }, [days]);

  async function loadAllReports(periodDays: number) {
    setLoading(true);
    try {
      const [ov, sl, rv, ex, cs, pr, fc] = await Promise.all([
        api.getReportsOverview(periodDays).catch(() => null),
        api.getSalesReports(periodDays).catch(() => null),
        api.getRevenueReports(periodDays).catch(() => null),
        api.getExpenseReports(periodDays).catch(() => null),
        api.getCustomerReports(periodDays).catch(() => null),
        api.getProductivityReports(periodDays).catch(() => null),
        api.getForecastingReports(periodDays).catch(() => null),
      ]);
      setOverview(ov);
      setSales(sl);
      setRevenue(rv);
      setExpenses(ex);
      setCustomers(cs);
      setProductivity(pr);
      setForecasting(fc);
    } catch (err) {
      console.error("Failed to load reports:", err);
    } finally {
      setLoading(false);
    }
  }

  async function handleGenerateInsights() {
    setInsightsLoading(true);
    try {
      const res = await api.generateAiInsights(days);
      setAiInsights(res);
    } catch (err) {
      console.error("Failed to generate AI insights:", err);
    } finally {
      setInsightsLoading(false);
    }
  }

  return (
    <div className="space-y-8 p-6 max-w-7xl mx-auto">
      {/* Page Header & Period Selector */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-foreground">
            AI Reporting & Strategic Analytics
          </h1>
          <p className="text-muted-foreground mt-1">
            Real-time financial telemetry, pipeline metrics, team productivity, and predictive revenue forecasts.
          </p>
        </div>

        {/* Time Period Filter Pills */}
        <div className="flex items-center gap-1.5 bg-accent/40 p-1.5 rounded-xl border border-border">
          {[
            { label: "7 Days", value: 7 },
            { label: "30 Days", value: 30 },
            { label: "90 Days", value: 90 },
            { label: "1 Year", value: 365 },
          ].map((p) => (
            <button
              key={p.value}
              onClick={() => setDays(p.value)}
              className={`px-3.5 py-1.5 text-xs font-semibold rounded-lg transition-all ${
                days === p.value
                  ? "bg-primary text-primary-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground hover:bg-accent"
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {loading && (
        <div className="p-8 text-center text-muted-foreground font-medium">
          Aggregating enterprise telemetry & generating charts...
        </div>
      )}

      {!loading && overview && (
        <>
          {/* Top Metric Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
            <div className="p-5 rounded-2xl bg-card border border-border">
              <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                Gross Invoiced
              </span>
              <p className="text-2xl font-bold text-foreground mt-1">
                ${overview.total_invoiced.toLocaleString()}
              </p>
              <p className="text-xs text-muted-foreground mt-2">
                {overview.quotations_count} quotations ({overview.quotation_conversion_rate}% converted)
              </p>
            </div>

            <div className="p-5 rounded-2xl bg-card border border-emerald-500/20 bg-emerald-500/5">
              <span className="text-xs font-semibold text-emerald-400 uppercase tracking-wider">
                Net Collected Revenue
              </span>
              <p className="text-2xl font-bold text-emerald-400 mt-1">
                ${overview.total_collected.toLocaleString()}
              </p>
              <p className="text-xs text-emerald-500/80 mt-2">
                Outstanding: ${overview.total_outstanding.toLocaleString()}
              </p>
            </div>

            <div className="p-5 rounded-2xl bg-card border border-blue-500/20 bg-blue-500/5">
              <span className="text-xs font-semibold text-blue-400 uppercase tracking-wider">
                Net Profit Position
              </span>
              <p className="text-2xl font-bold text-blue-400 mt-1">
                ${overview.net_profit.toLocaleString()}
              </p>
              <p className="text-xs text-blue-500/80 mt-2">
                Expenses: ${overview.total_expenses.toLocaleString()}
              </p>
            </div>

            <div className="p-5 rounded-2xl bg-card border border-purple-500/20 bg-purple-500/5">
              <span className="text-xs font-semibold text-purple-400 uppercase tracking-wider">
                ARPU & Customer Base
              </span>
              <p className="text-2xl font-bold text-purple-400 mt-1">
                ${revenue ? revenue.arpu.toLocaleString() : "0"}
              </p>
              <p className="text-xs text-purple-500/80 mt-2">
                {overview.total_customers} active customers (+{overview.new_customers} new)
              </p>
            </div>
          </div>

          {/* AI Executive Insights Banner */}
          <div className="bg-gradient-to-r from-blue-900/30 via-purple-900/20 to-card border border-blue-500/30 p-6 rounded-2xl space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-xl">✨</span>
                <h2 className="text-lg font-bold text-foreground">AI Executive Insights & Intelligence</h2>
              </div>
              <button
                onClick={handleGenerateInsights}
                disabled={insightsLoading}
                className="px-4 py-2 rounded-xl bg-primary hover:bg-primary/90 text-primary-foreground text-xs font-semibold transition-all shadow-md"
              >
                {insightsLoading ? "Analyzing Metrics..." : "Generate Fresh Insights"}
              </button>
            </div>

            {aiInsights ? (
              <div className="p-4 rounded-xl bg-background/60 border border-border text-sm text-foreground whitespace-pre-line leading-relaxed font-sans">
                {aiInsights.insights_text}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">
                Click "Generate Fresh Insights" to run automated LLM synthesis on revenue, pipeline conversion, expense risks, and strategic recommendations.
              </p>
            )}
          </div>

          {/* Grid: Charts & Analytics Breakdown */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Sales Pipeline Distribution */}
            <div className="bg-card border border-border p-6 rounded-2xl space-y-4">
              <h3 className="text-base font-semibold text-foreground">Sales Pipeline Breakdown</h3>
              {sales && sales.pipeline_breakdown && (
                <div className="space-y-3">
                  {Object.entries(sales.pipeline_breakdown).map(([stage, count]) => {
                    const total = Object.values(sales.pipeline_breakdown).reduce((a, b) => a + b, 0) || 1;
                    const pct = Math.round((count / total) * 100);
                    return (
                      <div key={stage} className="space-y-1">
                        <div className="flex justify-between text-xs font-medium">
                          <span className="capitalize text-foreground">{stage}</span>
                          <span className="text-muted-foreground">{count} leads ({pct}%)</span>
                        </div>
                        <div className="h-2 rounded-full bg-accent overflow-hidden">
                          <div
                            className="h-full bg-primary rounded-full transition-all duration-500"
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Expenses by Category */}
            <div className="bg-card border border-border p-6 rounded-2xl space-y-4">
              <h3 className="text-base font-semibold text-foreground">Expense Distribution by Category</h3>
              {expenses && expenses.expenses_by_category && (
                <div className="space-y-3">
                  {Object.entries(expenses.expenses_by_category).length === 0 ? (
                    <p className="text-sm text-muted-foreground">No expense categories logged yet.</p>
                  ) : (
                    Object.entries(expenses.expenses_by_category).map(([category, amount]) => {
                      const totalExp = expenses.total_expenses || 1;
                      const pct = Math.round((amount / totalExp) * 100);
                      return (
                        <div key={category} className="space-y-1">
                          <div className="flex justify-between text-xs font-medium">
                            <span className="capitalize text-foreground">{category}</span>
                            <span className="text-muted-foreground">${amount.toLocaleString()} ({pct}%)</span>
                          </div>
                          <div className="h-2 rounded-full bg-accent overflow-hidden">
                            <div
                              className="h-full bg-rose-500 rounded-full transition-all duration-500"
                              style={{ width: `${pct}%` }}
                            />
                          </div>
                        </div>
                      );
                    })
                  )}
                </div>
              )}
            </div>
          </div>

          {/* Predictive Forecasting Section */}
          {forecasting && (
            <div className="bg-card border border-border p-6 rounded-2xl space-y-6">
              <div>
                <h3 className="text-lg font-bold text-foreground">Predictive Revenue & Cash Flow Forecast</h3>
                <p className="text-sm text-muted-foreground mt-0.5">
                  Statistical projections combining baseline monthly recurring volume and active receivables collection rate ({forecasting.confidence_level}).
                </p>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-5">
                <div className="p-4 rounded-xl bg-accent/30 border border-border">
                  <span className="text-xs font-semibold text-muted-foreground">30-Day Projected Revenue</span>
                  <p className="text-2xl font-bold text-foreground mt-1">
                    ${forecasting.forecast_30_days.toLocaleString()}
                  </p>
                </div>

                <div className="p-4 rounded-xl bg-accent/30 border border-border">
                  <span className="text-xs font-semibold text-muted-foreground">60-Day Projected Revenue</span>
                  <p className="text-2xl font-bold text-foreground mt-1">
                    ${forecasting.forecast_60_days.toLocaleString()}
                  </p>
                </div>

                <div className="p-4 rounded-xl bg-accent/30 border border-border">
                  <span className="text-xs font-semibold text-muted-foreground">90-Day Projected Revenue</span>
                  <p className="text-2xl font-bold text-foreground mt-1">
                    ${forecasting.forecast_90_days.toLocaleString()}
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* Grid: Top Customers LTV Leaderboard & Team Productivity */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Customer LTV Leaderboard */}
            <div className="bg-card border border-border p-6 rounded-2xl space-y-4">
              <h3 className="text-base font-semibold text-foreground">Top Customers by Lifetime Value (LTV)</h3>
              <div className="border border-border rounded-xl overflow-hidden">
                <table className="w-full text-left text-sm">
                  <thead className="bg-accent/40 text-muted-foreground text-xs font-semibold uppercase">
                    <tr>
                      <th className="p-3">Customer</th>
                      <th className="p-3">Invoices</th>
                      <th className="p-3 text-right">Total Spent</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {customers && customers.top_customers_by_ltv.length > 0 ? (
                      customers.top_customers_by_ltv.slice(0, 5).map((c) => (
                        <tr key={c.id} className="hover:bg-accent/20">
                          <td className="p-3 font-medium text-foreground">
                            {c.name} {c.company ? `(${c.company})` : ""}
                          </td>
                          <td className="p-3 text-muted-foreground">{c.invoice_count}</td>
                          <td className="p-3 text-right font-semibold text-emerald-400">
                            ${c.total_spent.toLocaleString()}
                          </td>
                        </tr>
                      ))
                    ) : (
                      <tr>
                        <td colSpan={3} className="p-3 text-center text-muted-foreground">
                          No customer LTV data available.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            {/* AI Employee & Team Productivity */}
            <div className="bg-card border border-border p-6 rounded-2xl space-y-4">
              <h3 className="text-base font-semibold text-foreground">AI Employees & Operational Velocity</h3>
              {productivity && (
                <div className="space-y-4">
                  <div className="flex justify-between items-center p-3 rounded-xl bg-accent/30 border border-border">
                    <span className="text-sm font-medium text-foreground">Total AI Employee Automated Runs</span>
                    <span className="text-lg font-bold text-primary">{productivity.total_ai_employee_runs}</span>
                  </div>

                  <div className="flex justify-between items-center p-3 rounded-xl bg-accent/30 border border-border">
                    <span className="text-sm font-medium text-foreground">Task Resolution Velocity</span>
                    <span className="text-lg font-bold text-emerald-400">
                      {productivity.completed_tasks} / {productivity.total_tasks} ({productivity.task_completion_rate_percent}%)
                    </span>
                  </div>

                  {productivity.runs_by_employee && Object.keys(productivity.runs_by_employee).length > 0 && (
                    <div className="space-y-2 pt-2">
                      <span className="text-xs font-semibold text-muted-foreground uppercase">Runs by Specialist</span>
                      {Object.entries(productivity.runs_by_employee).map(([emp, count]) => (
                        <div key={emp} className="flex justify-between text-xs py-1 border-b border-border/50">
                          <span className="capitalize text-foreground">{emp.replace(/_/g, " ")}</span>
                          <span className="font-semibold text-muted-foreground">{count} runs</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
