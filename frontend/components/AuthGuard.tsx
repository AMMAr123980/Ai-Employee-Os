"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { fetchMe, AuthUser, AuthCompany } from "@/lib/auth";

type AuthContextValue = {
  user: AuthUser;
  company: AuthCompany;
  refreshUser: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthGuard");
  return ctx;
}

export default function AuthGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [state, setState] = useState<
    { status: "loading" } | { status: "authed"; value: AuthContextValue } | { status: "redirecting" }
  >({ status: "loading" });

  const loadUser = async () => {
    const me = await fetchMe();
    if (!me) {
      setState({ status: "redirecting" });
      router.replace("/login");
    } else {
      setState({
        status: "authed",
        value: { user: me.user, company: me.company, refreshUser: loadUser },
      });
    }
  };

  useEffect(() => {
    let cancelled = false;
    fetchMe().then((me) => {
      if (cancelled) return;
      if (!me) {
        setState({ status: "redirecting" });
        router.replace("/login");
      } else {
        setState({
          status: "authed",
          value: { user: me.user, company: me.company, refreshUser: loadUser },
        });
      }
    });
    return () => {
      cancelled = true;
    };
  }, [router]);

  if (state.status === "loading" || state.status === "redirecting") {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-slate-400">
        Loading…
      </div>
    );
  }

  return <AuthContext.Provider value={state.value}>{children}</AuthContext.Provider>;
}
