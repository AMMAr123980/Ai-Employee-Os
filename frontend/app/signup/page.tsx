"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Sparkles, ArrowRight, Building2, User, Mail, Lock, ShieldCheck, Zap } from "lucide-react";
import { signup } from "@/lib/auth";

export default function SignupPage() {
  const router = useRouter();
  const [companyName, setCompanyName] = useState("");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await signup({ company_name: companyName, name, email, password });
      router.push("/");
    } catch (e: any) {
      setError(e.message || "Signup failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex bg-white antialiased">
      {/* Left Brand Showcase Banner */}
      <div className="hidden lg:flex lg:w-1/2 bg-gradient-to-br from-slate-950 via-slate-900 to-indigo-950 p-12 flex-col justify-between relative overflow-hidden text-white">
        <div className="absolute -right-24 -top-24 h-96 w-96 rounded-full bg-brand-500/20 blur-3xl" />
        <div className="absolute -left-24 -bottom-24 h-96 w-96 rounded-full bg-indigo-500/20 blur-3xl" />

        <div className="relative z-10 flex items-center gap-3">
          <div className="h-10 w-10 rounded-2xl bg-gradient-to-tr from-brand-500 to-indigo-500 flex items-center justify-center text-white font-bold shadow-lg shadow-brand-500/30">
            <Sparkles className="h-5 w-5 text-white" />
          </div>
          <div>
            <p className="font-bold text-lg tracking-tight">AI Employee OS</p>
            <p className="text-xs text-brand-300">Enterprise Multi-Tenant Suite</p>
          </div>
        </div>

        <div className="relative z-10 space-y-6 max-w-md">
          <div className="inline-flex items-center gap-2 rounded-full bg-white/10 px-3 py-1 text-xs font-semibold text-brand-200 border border-white/10 backdrop-blur-md">
            <Zap className="h-3.5 w-3.5 text-brand-400" />
            <span>Instant Workspace Provisioning</span>
          </div>
          <h2 className="text-3xl font-bold tracking-tight leading-tight">
            Launch your dedicated company AI workspace in seconds.
          </h2>
          <p className="text-sm text-slate-300 leading-relaxed">
            Get instant access to AI quotation generators, automated invoice tracking, WhatsApp outreach, and custom-trained AI employee personas.
          </p>

          <div className="space-y-2.5 pt-2">
            {[
              "Automated quotation and PDF generator",
              "AI payment tracking and accounting sync",
              "Pre-configured specialists for Sales, Ops, and Finance",
            ].map((feature, i) => (
              <div key={i} className="flex items-center gap-2 text-xs text-slate-200">
                <ShieldCheck className="h-4 w-4 text-emerald-400 shrink-0" />
                <span>{feature}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="relative z-10 flex items-center gap-2 text-xs text-slate-400">
          <ShieldCheck className="h-4 w-4 text-emerald-400" />
          <span>SOC2 & GDPR Compliant Infrastructure</span>
        </div>
      </div>

      {/* Right Registration Form */}
      <div className="flex-1 flex items-center justify-center p-6 md:p-12">
        <div className="w-full max-w-sm space-y-6">
          <div className="space-y-1">
            <h1 className="text-2xl font-bold tracking-tight text-slate-900">Create your workspace</h1>
            <p className="text-xs text-slate-500">Set up your company and administrator credentials</p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-3.5">
            <div className="space-y-1">
              <label className="block text-xs font-semibold text-slate-700">Company Name</label>
              <div className="relative">
                <Building2 className="h-4 w-4 text-slate-400 absolute left-3 top-3" />
                <input
                  type="text"
                  required
                  placeholder="Acme Global Inc"
                  className="w-full rounded-xl border border-slate-200 bg-slate-50/50 pl-9 pr-3 py-2 text-xs text-slate-900 shadow-2xs outline-none focus:border-brand-500 focus:bg-white focus:ring-2 focus:ring-brand-500/10 transition"
                  value={companyName}
                  onChange={(e) => setCompanyName(e.target.value)}
                />
              </div>
            </div>

            <div className="space-y-1">
              <label className="block text-xs font-semibold text-slate-700">Your Full Name</label>
              <div className="relative">
                <User className="h-4 w-4 text-slate-400 absolute left-3 top-3" />
                <input
                  type="text"
                  required
                  placeholder="Jane Doe"
                  className="w-full rounded-xl border border-slate-200 bg-slate-50/50 pl-9 pr-3 py-2 text-xs text-slate-900 shadow-2xs outline-none focus:border-brand-500 focus:bg-white focus:ring-2 focus:ring-brand-500/10 transition"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
              </div>
            </div>

            <div className="space-y-1">
              <label className="block text-xs font-semibold text-slate-700">Work Email</label>
              <div className="relative">
                <Mail className="h-4 w-4 text-slate-400 absolute left-3 top-3" />
                <input
                  type="email"
                  required
                  placeholder="jane@acme.com"
                  className="w-full rounded-xl border border-slate-200 bg-slate-50/50 pl-9 pr-3 py-2 text-xs text-slate-900 shadow-2xs outline-none focus:border-brand-500 focus:bg-white focus:ring-2 focus:ring-brand-500/10 transition"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </div>
            </div>

            <div className="space-y-1">
              <label className="block text-xs font-semibold text-slate-700">Password</label>
              <div className="relative">
                <Lock className="h-4 w-4 text-slate-400 absolute left-3 top-3" />
                <input
                  type="password"
                  required
                  minLength={8}
                  placeholder="At least 8 characters"
                  className="w-full rounded-xl border border-slate-200 bg-slate-50/50 pl-9 pr-3 py-2 text-xs text-slate-900 shadow-2xs outline-none focus:border-brand-500 focus:bg-white focus:ring-2 focus:ring-brand-500/10 transition"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </div>
            </div>

            {error && (
              <div className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-xs text-rose-700">
                {error}
              </div>
            )}

            <button
              disabled={loading}
              className="w-full inline-flex items-center justify-center gap-2 rounded-xl bg-brand-600 px-4 py-2.5 text-xs font-semibold text-white shadow-md hover:bg-brand-700 disabled:opacity-50 transition"
            >
              {loading ? (
                <>
                  <Sparkles className="h-3.5 w-3.5 animate-spin" />
                  <span>Provisioning Workspace...</span>
                </>
              ) : (
                <>
                  <span>Create Workspace</span>
                  <ArrowRight className="h-3.5 w-3.5" />
                </>
              )}
            </button>
          </form>

          <div className="pt-1 text-center text-xs text-slate-500">
            Already have a workspace?{" "}
            <Link href="/login" className="font-semibold text-brand-600 hover:text-brand-700 hover:underline">
              Sign in
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
