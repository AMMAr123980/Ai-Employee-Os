"use client";

import { useEffect, useState } from "react";
import { api, SubscriptionInfo } from "@/lib/api";

export default function BillingPage() {
  const [subscription, setSubscription] = useState<SubscriptionInfo | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    loadSubscription();
  }, []);

  async function loadSubscription() {
    setLoading(true);
    try {
      const data = await api.getSubscription();
      setSubscription(data);
    } catch (err: any) {
      console.error("Failed to load subscription info:", err);
    } finally {
      setLoading(false);
    }
  }

  async function handlePlanUpgrade(planKey: "basic" | "pro" | "business") {
    setActionLoading(planKey);
    setMessage(null);
    try {
      const checkout = await api.createCheckoutSession(planKey);
      if (checkout.mode === "stripe" && checkout.checkout_url) {
        window.location.href = checkout.checkout_url;
      } else {
        // Sandbox mode upgrade fallback
        const res = await api.changePlan(planKey);
        setMessage(`Successfully switched plan to ${res.plan.toUpperCase()}!`);
        loadSubscription();
      }
    } catch (err: any) {
      setMessage(`Upgrade failed: ${err.message}`);
    } finally {
      setActionLoading(null);
    }
  }

  const plans = [
    {
      key: "basic",
      name: "Basic Plan",
      price: "$19",
      period: "per month",
      description: "Essential AI assistance for small teams and solo operators.",
      features: [
        "500 AI Model Requests / mo",
        "3 Audio Transcription Hours / mo",
        "1 GB Storage Allowance",
        "30 Invoices & 30 Quotations / mo",
        "Up to 3 Team Seats",
        "All 12 AI Employee Roles Included",
      ],
      color: "border-border",
    },
    {
      key: "pro",
      name: "Pro Plan",
      price: "$79",
      period: "per month",
      description: "High-volume operations with priority processing and higher limits.",
      features: [
        "10,000 AI Model Requests / mo",
        "40 Audio Transcription Hours / mo",
        "20 GB Storage Allowance",
        "500 Invoices & 500 Quotations / mo",
        "Up to 15 Team Seats",
        "Gmail / Outlook Inbound Sync",
        "Multi-LLM Provider Switching (Claude & Gemini)",
      ],
      popular: true,
      color: "border-primary bg-primary/5",
    },
    {
      key: "business",
      name: "Business Enterprise",
      price: "$299",
      period: "per month",
      description: "Unlimited scale, developer REST API access, and dedicated support.",
      features: [
        "Unlimited AI Model Requests (Fair Use)",
        "Unlimited Audio Transcription Hours",
        "200 GB High-Speed Storage",
        "Unlimited Invoices & Quotations",
        "Unlimited Team Seats",
        "Public Developer REST API Key Access",
        "QuickBooks / Xero / Zoho Books Integration",
        "Redis & Elasticsearch Vector Fallback",
      ],
      color: "border-purple-500/40 bg-purple-500/5",
    },
  ];

  return (
    <div className="space-y-8 p-6 max-w-6xl mx-auto">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight text-foreground">
          Billing, Plans & Subscription
        </h1>
        <p className="text-muted-foreground mt-1">
          Manage your subscription tier, billing period, and monitor real-time resource consumption.
        </p>
      </div>

      {message && (
        <div className="p-4 rounded-xl bg-blue-500/10 border border-blue-500/20 text-blue-400 font-medium">
          {message}
        </div>
      )}

      {loading && (
        <div className="p-8 text-center text-muted-foreground font-medium">
          Loading subscription details & usage counters...
        </div>
      )}

      {!loading && subscription && (
        <>
          {/* Active Subscription Status Banner */}
          <div className="bg-card border border-border p-6 rounded-2xl flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div>
              <div className="flex items-center gap-3">
                <span className="text-sm font-medium text-muted-foreground">Current Plan:</span>
                <span className="px-3 py-1 text-xs font-bold uppercase rounded-full bg-primary/20 text-primary">
                  {subscription.plan} Tier
                </span>
                <span className="px-2.5 py-0.5 text-xs font-semibold rounded-full bg-emerald-500/20 text-emerald-400 capitalize">
                  {subscription.subscription_status}
                </span>
              </div>
              <p className="text-sm text-muted-foreground mt-2">
                Renewal price: <span className="font-semibold text-foreground">${subscription.price_monthly}/month</span>
                {subscription.current_period_end && (
                  <span> · Next billing date: {new Date(subscription.current_period_end).toLocaleDateString()}</span>
                )}
              </p>
            </div>
            <div className="flex items-center gap-3">
              <span className="text-xs text-muted-foreground">
                Company ID: <code className="font-mono bg-accent px-2 py-1 rounded">{subscription.company_id}</code>
              </span>
            </div>
          </div>

          {/* Pricing Tier Cards */}
          <div>
            <h2 className="text-xl font-bold text-foreground mb-4">Select Subscription Plan</h2>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              {plans.map((p) => {
                const isCurrent = subscription.plan.toLowerCase() === p.key;
                return (
                  <div
                    key={p.key}
                    className={`p-6 rounded-2xl border flex flex-col justify-between relative transition-all ${p.color}`}
                  >
                    {p.popular && (
                      <span className="absolute -top-3 right-6 px-3 py-0.5 text-[10px] font-bold uppercase tracking-wider bg-primary text-primary-foreground rounded-full shadow-sm">
                        Most Popular
                      </span>
                    )}

                    <div>
                      <h3 className="text-lg font-bold text-foreground">{p.name}</h3>
                      <p className="text-xs text-muted-foreground mt-1 min-h-[32px]">{p.description}</p>

                      <div className="my-4 flex items-baseline gap-1">
                        <span className="text-3xl font-extrabold text-foreground">{p.price}</span>
                        <span className="text-xs text-muted-foreground">{p.period}</span>
                      </div>

                      <ul className="space-y-2.5 text-xs text-muted-foreground my-6">
                        {p.features.map((f, i) => (
                          <li key={i} className="flex items-center gap-2 text-foreground/90">
                            <span className="text-emerald-400 font-bold">✓</span>
                            <span>{f}</span>
                          </li>
                        ))}
                      </ul>
                    </div>

                    <button
                      onClick={() => handlePlanUpgrade(p.key as any)}
                      disabled={isCurrent || actionLoading === p.key}
                      className={`w-full py-2.5 rounded-xl text-sm font-semibold transition-all ${
                        isCurrent
                          ? "bg-accent text-muted-foreground cursor-default"
                          : "bg-primary hover:bg-primary/90 text-primary-foreground shadow-md"
                      }`}
                    >
                      {isCurrent
                        ? "Active Plan"
                        : actionLoading === p.key
                        ? "Processing..."
                        : `Upgrade to ${p.name}`}
                    </button>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Real-time Usage Telemetry Gauges */}
          <div className="bg-card border border-border p-6 rounded-2xl space-y-6">
            <div>
              <h2 className="text-xl font-bold text-foreground">Usage Telemetry & Metering</h2>
              <p className="text-sm text-muted-foreground mt-0.5">
                Real-time usage counters enforced by usage_metering engine.
              </p>
            </div>

            {subscription.usage && subscription.usage.metrics && (
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                {Object.entries(subscription.usage.metrics).map(([metricKey, item]) => {
                  const label = metricKey.replace(/_/g, " ").toUpperCase();
                  return (
                    <div key={metricKey} className="p-4 rounded-xl bg-accent/30 border border-border space-y-2">
                      <div className="flex justify-between items-center text-xs font-semibold">
                        <span className="text-foreground">{label}</span>
                        <span className="text-muted-foreground">
                          {item.unlimited ? "Unlimited" : `${item.used} / ${item.limit}`}
                        </span>
                      </div>
                      {!item.unlimited && (
                        <div className="h-2 rounded-full bg-accent overflow-hidden">
                          <div
                            className="h-full bg-primary rounded-full transition-all duration-500"
                            style={{ width: `${item.percent || 0}%` }}
                          />
                        </div>
                      )}
                      <p className="text-[11px] text-muted-foreground">
                        {item.unlimited
                          ? "Fair use policy active"
                          : `${item.percent || 0}% of monthly plan quota used`}
                      </p>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
