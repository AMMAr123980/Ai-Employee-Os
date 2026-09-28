"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Sparkles, ArrowRight, ShieldCheck, Zap, Lock, Mail, KeyRound, RefreshCw } from "lucide-react";
import { login, resendOTP } from "@/lib/auth";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mfaRequired, setMfaRequired] = useState(false);
  const [totpCode, setTotpCode] = useState("");
  const [resending, setResending] = useState(false);
  const [resendMsg, setResendMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setResendMsg(null);
    try {
      const res = await login({
        email,
        password,
        totp_code: mfaRequired ? totpCode : undefined,
      });

      if (res.mfa_required) {
        setMfaRequired(true);
        setError(null);
        return;
      }

      if (res.access_token) {
        router.push("/");
      }
    } catch (e: any) {
      setError(e.message || "Login failed");
    } finally {
      setLoading(false);
    }
  }

  async function handleResendCode() {
    setResending(true);
    setError(null);
    setResendMsg(null);
    try {
      await resendOTP({ email, password });
      setResendMsg("New verification code sent to your email!");
    } catch (e: any) {
      setError(e.message || "Failed to resend code");
    } finally {
      setResending(false);
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
            <p className="text-xs text-brand-300">Autonomous Operations Platform</p>
          </div>
        </div>

        <div className="relative z-10 space-y-6 max-w-md">
          <div className="inline-flex items-center gap-2 rounded-full bg-white/10 px-3 py-1 text-xs font-semibold text-brand-200 border border-white/10 backdrop-blur-md">
            <Zap className="h-3.5 w-3.5 text-brand-400" />
            <span>Multi-Agent Executive Cloud</span>
          </div>
          <h2 className="text-3xl font-bold tracking-tight leading-tight">
            Automate sales quotes, invoices, and back-office operations with AI specialists.
          </h2>
          <p className="text-sm text-slate-300 leading-relaxed">
            Deploy specialized autonomous employees for finance, operations, customer success, and sales pipeline management with human-in-the-loop approvals.
          </p>

          <div className="grid grid-cols-2 gap-3 pt-4 border-t border-white/10">
            <div className="rounded-xl bg-white/5 p-3 border border-white/10 backdrop-blur-sm">
              <p className="text-xl font-bold text-white">100%</p>
              <p className="text-xs text-slate-400">Deterministic Safety</p>
            </div>
            <div className="rounded-xl bg-white/5 p-3 border border-white/10 backdrop-blur-sm">
              <p className="text-xl font-bold text-white">&lt; 100ms</p>
              <p className="text-xs text-slate-400">Response Latency</p>
            </div>
          </div>
        </div>

        <div className="relative z-10 flex items-center gap-2 text-xs text-slate-400">
          <ShieldCheck className="h-4 w-4 text-emerald-400" />
          <span>Enterprise Multi-Tenant Tenant Isolation & 2-Step Verification</span>
        </div>
      </div>

      {/* Right Login Form */}
      <div className="flex-1 flex items-center justify-center p-6 md:p-12">
        <div className="w-full max-w-sm space-y-6">
          {!mfaRequired ? (
            <>
              <div className="space-y-1">
                <h1 className="text-2xl font-bold tracking-tight text-slate-900">Sign in to your workspace</h1>
                <p className="text-xs text-slate-500">Enter your credentials to access your autonomous team</p>
              </div>

              <form onSubmit={handleSubmit} className="space-y-4">
                <div className="space-y-1.5">
                  <label className="block text-xs font-semibold text-slate-700">Email Address</label>
                  <div className="relative">
                    <Mail className="h-4 w-4 text-slate-400 absolute left-3 top-3" />
                    <input
                      type="email"
                      required
                      placeholder="name@company.com"
                      className="w-full rounded-xl border border-slate-200 bg-slate-50/50 pl-9 pr-3 py-2.5 text-xs text-slate-900 shadow-2xs outline-none focus:border-brand-500 focus:bg-white focus:ring-2 focus:ring-brand-500/10 transition"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                    />
                  </div>
                </div>

                <div className="space-y-1.5">
                  <label className="block text-xs font-semibold text-slate-700">Password</label>
                  <div className="relative">
                    <Lock className="h-4 w-4 text-slate-400 absolute left-3 top-3" />
                    <input
                      type="password"
                      required
                      placeholder="••••••••"
                      className="w-full rounded-xl border border-slate-200 bg-slate-50/50 pl-9 pr-3 py-2.5 text-xs text-slate-900 shadow-2xs outline-none focus:border-brand-500 focus:bg-white focus:ring-2 focus:ring-brand-500/10 transition"
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
                      <span>Signing in...</span>
                    </>
                  ) : (
                    <>
                      <span>Continue to 2-Step Verification</span>
                      <ArrowRight className="h-3.5 w-3.5" />
                    </>
                  )}
                </button>
              </form>

              {/* SSO / OAuth Options */}
              <div className="space-y-3 pt-2">
                <div className="relative flex items-center justify-center">
                  <div className="w-full border-t border-slate-200" />
                  <span className="bg-white px-2.5 text-[10px] font-bold uppercase tracking-wider text-slate-400">
                    Or Sign In With Single Sign-On (SSO)
                  </span>
                </div>

                <div className="grid grid-cols-2 gap-2">
                  {/* Google OAuth Button */}
                  <button
                    type="button"
                    disabled={loading}
                    onClick={async () => {
                      setLoading(true);
                      setError(null);
                      try {
                        const targetEmail = email.trim() || prompt("Enter your Gmail address to sign in with Google:");
                        if (targetEmail) {
                          const res = await (await import("@/lib/auth")).ssoLogin({
                            provider: "google",
                            email: targetEmail,
                            name: targetEmail.split("@")[0],
                          });
                          if (res.access_token) {
                            router.push("/");
                            return;
                          }
                        }
                        const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";
                        const res = await fetch(`${API_URL}/api/auth/oauth/redirect?provider=google`);
                        if (res.ok) {
                          const { auth_url } = await res.json();
                          sessionStorage.setItem("oauth_provider", "google");
                          window.location.href = auth_url;
                        }
                      } catch (err: any) {
                        setError(err.message);
                      } finally {
                        setLoading(false);
                      }
                    }}
                    className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-700 shadow-2xs hover:bg-slate-50 transition disabled:opacity-50"
                  >
                    <svg className="h-4 w-4" viewBox="0 0 24 24">
                      <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
                      <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
                      <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z" />
                      <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z" />
                    </svg>
                    <span>Google OAuth</span>
                  </button>

                  {/* Microsoft 365 Button */}
                  <button
                    type="button"
                    disabled={loading}
                    onClick={async () => {
                      setLoading(true);
                      setError(null);
                      try {
                        const targetEmail = email.trim() || prompt("Enter your Microsoft / Outlook email address to sign in:");
                        if (targetEmail) {
                          const res = await (await import("@/lib/auth")).ssoLogin({
                            provider: "microsoft",
                            email: targetEmail,
                            name: targetEmail.split("@")[0],
                          });
                          if (res.access_token) {
                            router.push("/");
                            return;
                          }
                        }
                        const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";
                        const res = await fetch(`${API_URL}/api/auth/oauth/redirect?provider=microsoft`);
                        if (res.ok) {
                          const { auth_url } = await res.json();
                          sessionStorage.setItem("oauth_provider", "microsoft");
                          window.location.href = auth_url;
                        }
                      } catch (err: any) {
                        setError(err.message);
                      } finally {
                        setLoading(false);
                      }
                    }}
                    className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-700 shadow-2xs hover:bg-slate-50 transition disabled:opacity-50"
                  >
                    <svg className="h-4 w-4" viewBox="0 0 23 23">
                      <path fill="#f35325" d="M1 1h10v10H1z" />
                      <path fill="#81bc06" d="M12 1h10v10H12z" />
                      <path fill="#05a6f0" d="M1 12h10v10H1z" />
                      <path fill="#ffba08" d="M12 12h10v10H12z" />
                    </svg>
                    <span>Microsoft 365</span>
                  </button>
                </div>

                {/* Setup guide notice */}
                <p className="text-center text-[10px] text-slate-400 leading-relaxed">
                  SSO requires Google/Microsoft API credentials in{" "}
                  <code className="font-mono bg-slate-100 px-1 rounded">backend/.env</code>
                </p>
              </div>
            </>
          ) : (
            <>
              <div className="space-y-1 text-center">
                <div className="mx-auto w-12 h-12 rounded-2xl bg-emerald-500/10 text-emerald-600 flex items-center justify-center mb-3">
                  <ShieldCheck className="w-6 h-6" />
                </div>
                <h1 className="text-2xl font-bold tracking-tight text-slate-900">2-Step Verification</h1>
                <p className="text-xs text-slate-500 leading-relaxed">
                  A 6-digit security code has been sent to <strong className="text-slate-700">{email}</strong>. Please check your email inbox.
                </p>
              </div>

              <form onSubmit={handleSubmit} className="space-y-4">
                <div className="space-y-1.5">
                  <label className="block text-xs font-semibold text-slate-700 text-center">Enter 6-Digit Code</label>
                  <input
                    type="text"
                    required
                    maxLength={6}
                    autoFocus
                    placeholder="000000"
                    className="w-full text-center tracking-[0.5em] text-lg font-mono rounded-xl border border-slate-200 bg-slate-50/50 px-3 py-3 text-slate-900 shadow-2xs outline-none focus:border-emerald-500 focus:bg-white focus:ring-2 focus:ring-emerald-500/10 transition"
                    value={totpCode}
                    onChange={(e) => setTotpCode(e.target.value.replace(/\D/g, ""))}
                  />
                </div>

                {resendMsg && (
                  <p className="text-xs text-emerald-600 font-medium text-center">{resendMsg}</p>
                )}

                {error && (
                  <div className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-xs text-rose-700 text-center">
                    {error}
                  </div>
                )}

                <button
                  disabled={loading || totpCode.length !== 6}
                  className="w-full inline-flex items-center justify-center gap-2 rounded-xl bg-emerald-600 px-4 py-2.5 text-xs font-semibold text-white shadow-md hover:bg-emerald-700 disabled:opacity-50 transition"
                >
                  {loading ? (
                    <>
                      <Sparkles className="h-3.5 w-3.5 animate-spin" />
                      <span>Verifying Code...</span>
                    </>
                  ) : (
                    <>
                      <span>Verify & Access Console</span>
                      <ArrowRight className="h-3.5 w-3.5" />
                    </>
                  )}
                </button>

                <div className="flex items-center justify-between text-xs pt-1">
                  <button
                    type="button"
                    onClick={() => {
                      setMfaRequired(false);
                      setTotpCode("");
                      setError(null);
                    }}
                    className="text-slate-500 hover:text-slate-800 transition"
                  >
                    ← Back to Sign In
                  </button>

                  <button
                    type="button"
                    disabled={resending}
                    onClick={handleResendCode}
                    className="inline-flex items-center gap-1 font-semibold text-brand-600 hover:text-brand-700 disabled:opacity-50 transition"
                  >
                    <RefreshCw className={`w-3 h-3 ${resending ? "animate-spin" : ""}`} />
                    <span>Resend Code</span>
                  </button>
                </div>
              </form>
            </>
          )}

          <div className="pt-2 text-center text-xs text-slate-500">
            Don&apos;t have a workspace yet?{" "}
            <Link href="/signup" className="font-semibold text-brand-600 hover:text-brand-700 hover:underline">
              Create workspace
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
