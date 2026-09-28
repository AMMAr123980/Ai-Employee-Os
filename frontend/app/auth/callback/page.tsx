"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Sparkles } from "lucide-react";
import { setToken } from "@/lib/auth";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

export default function AuthCallbackPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [status, setStatus] = useState<"loading" | "success" | "error">("loading");
  const [errorMsg, setErrorMsg] = useState("");

  useEffect(() => {
    const code = searchParams.get("code");
    const provider = searchParams.get("state")
      ? (sessionStorage.getItem("oauth_provider") || "google")
      : "google";
    const error = searchParams.get("error");

    if (error) {
      setStatus("error");
      setErrorMsg(`OAuth denied: ${error}`);
      return;
    }

    if (!code) {
      setStatus("error");
      setErrorMsg("No authorization code received from provider.");
      return;
    }

    const savedProvider = sessionStorage.getItem("oauth_provider") || provider;

    (async () => {
      try {
        const res = await fetch(`${API_URL}/api/auth/oauth/callback`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            provider: savedProvider,
            code,
            redirect_uri: `${window.location.origin}/auth/callback`,
          }),
        });

        if (!res.ok) {
          const detail = await res.json().catch(() => ({}));
          throw new Error(detail.detail || `Server error (${res.status})`);
        }

        const data = await res.json();
        setToken(data.access_token);
        sessionStorage.removeItem("oauth_provider");
        setStatus("success");

        // Redirect to dashboard
        setTimeout(() => router.push("/"), 1000);
      } catch (err: any) {
        setStatus("error");
        setErrorMsg(err.message || "OAuth login failed");
      }
    })();
  }, []);

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-950">
      <div className="text-center space-y-4">
        {status === "loading" && (
          <>
            <Sparkles className="h-10 w-10 text-brand-400 animate-spin mx-auto" />
            <p className="text-white font-semibold text-lg">Completing sign in...</p>
            <p className="text-slate-400 text-sm">Verifying your account with the provider</p>
          </>
        )}
        {status === "success" && (
          <>
            <div className="h-10 w-10 rounded-full bg-emerald-500/20 text-emerald-400 flex items-center justify-center mx-auto text-2xl">✓</div>
            <p className="text-white font-semibold text-lg">Sign in successful!</p>
            <p className="text-slate-400 text-sm">Redirecting to your workspace...</p>
          </>
        )}
        {status === "error" && (
          <>
            <div className="h-10 w-10 rounded-full bg-rose-500/20 text-rose-400 flex items-center justify-center mx-auto text-2xl">✗</div>
            <p className="text-white font-semibold text-lg">Sign in failed</p>
            <p className="text-rose-400 text-sm max-w-sm">{errorMsg}</p>
            <button
              onClick={() => router.push("/login")}
              className="mt-4 px-6 py-2 rounded-xl bg-brand-600 text-white text-sm font-semibold hover:bg-brand-700 transition"
            >
              Back to Login
            </button>
          </>
        )}
      </div>
    </div>
  );
}
