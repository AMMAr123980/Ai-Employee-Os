"use client";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";
const TOKEN_KEY = "ai_employee_os_token";

export type AuthUser = {
  id: string;
  company_id: string;
  name: string;
  email: string;
  role: "owner" | "admin" | "member";
  mfa_enabled?: boolean;
};

export type AuthCompany = {
  id: string;
  name: string;
};

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string) {
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  window.localStorage.removeItem(TOKEN_KEY);
}

async function authRequest<T>(path: string, body: object, authRequired = false): Promise<T> {
  try {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (authRequired) {
      const token = getToken();
      if (token) headers["Authorization"] = `Bearer ${token}`;
    }
    const res = await fetch(`${API_URL}${path}`, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}));
      throw new Error(detail.detail || `Request failed (${res.status})`);
    }
    return res.json();
  } catch (err: any) {
    if (err.message && err.message.includes("Failed to fetch")) {
      throw new Error(`Cannot connect to backend server at ${API_URL}. Please ensure 'python run_backend.py' is running.`);
    }
    throw err;
  }
}

export async function signup(data: {
  company_name: string;
  name: string;
  email: string;
  password: string;
}) {
  const result = await authRequest<{ access_token: string; user: AuthUser; company: AuthCompany }>(
    "/api/auth/signup",
    data
  );
  setToken(result.access_token);
  return result;
}

export async function login(data: { email: string; password: string; totp_code?: string }) {
  const result = await authRequest<{
    access_token?: string;
    user?: AuthUser;
    company?: AuthCompany;
    mfa_required?: boolean;
    mfa_type?: string;
    otp_dev_hint?: string;
    message?: string;
  }>("/api/auth/login", data);
  if (result.access_token) {
    setToken(result.access_token);
  }
  return result;
}

export async function ssoLogin(data: { provider: string; email?: string; name?: string; token?: string }) {
  const result = await authRequest<{
    access_token?: string;
    user?: AuthUser;
    company?: AuthCompany;
  }>("/api/auth/sso", data);
  if (result.access_token) {
    setToken(result.access_token);
  }
  return result;
}

export async function resendOTP(data: { email: string; password: string }) {
  return authRequest<{ status: string; message: string; otp_dev_hint?: string }>("/api/auth/resend-otp", data);
}

export async function setup2FA() {
  return authRequest<{ secret: string; qr_uri: string }>("/api/auth/2fa/setup", {}, true);
}

export async function enable2FA(code: string, secret: string) {
  return authRequest<{ success: boolean; message: string }>("/api/auth/2fa/enable", { code, secret }, true);
}

export async function disable2FA(code: string) {
  return authRequest<{ success: boolean; message: string }>("/api/auth/2fa/disable", { code }, true);
}

export async function fetchMe(): Promise<{ user: AuthUser; company: AuthCompany } | null> {
  const token = getToken();
  if (!token) return null;
  try {
    const res = await fetch(`${API_URL}/api/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    });
    if (!res.ok) {
      clearToken();
      return null;
    }
    return res.json();
  } catch (err) {
    console.warn(`Could not reach backend API at ${API_URL}. Is the backend running?`);
    return null;
  }
}

export function logout() {
  clearToken();
  window.location.href = "/login";
}
