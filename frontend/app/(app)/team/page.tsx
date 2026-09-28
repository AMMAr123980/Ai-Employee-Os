"use client";

import { useEffect, useState } from "react";
import { api, TeamMember, UserRole } from "@/lib/api";
import { useAuth } from "@/components/AuthGuard";
import { setup2FA, enable2FA, disable2FA } from "@/lib/auth";
import { ShieldCheck, ShieldAlert, KeyRound, Copy, Check, Sparkles, X } from "lucide-react";

const ROLE_LABELS: Record<UserRole, string> = {
  owner: "Owner",
  admin: "Admin",
  member: "Member",
};

const ROLE_COLORS: Record<UserRole, string> = {
  owner: "bg-purple-100 text-purple-700",
  admin: "bg-blue-100 text-blue-700",
  member: "bg-slate-100 text-slate-600",
};

export default function TeamPage() {
  const { user, refreshUser } = useAuth();
  const [members, setMembers] = useState<TeamMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: "", email: "", password: "", role: "member" as UserRole });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  // 2FA state
  const [mfaEnabled, setMfaEnabled] = useState<boolean>(!!user?.mfa_enabled);
  const [setupModalOpen, setSetupModalOpen] = useState(false);
  const [disableModalOpen, setDisableModalOpen] = useState(false);
  const [qrUri, setQrUri] = useState<string>("");
  const [secretKey, setSecretKey] = useState<string>("");
  const [totpInput, setTotpInput] = useState<string>("");
  const [mfaError, setMfaError] = useState<string | null>(null);
  const [mfaLoading, setMfaLoading] = useState(false);
  const [copiedSecret, setCopiedSecret] = useState(false);

  const canManage = user.role === "owner" || user.role === "admin";
  const isOwner = user.role === "owner";

  async function load() {
    setMembers(await api.listTeam());
    setLoading(false);
  }

  useEffect(() => {
    load();
    if (user?.mfa_enabled !== undefined) {
      setMfaEnabled(user.mfa_enabled);
    }
  }, [user]);

  async function handleInvite(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await api.inviteTeamMember(form);
      setForm({ name: "", email: "", password: "", role: "member" });
      setShowForm(false);
      await load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  async function handleRoleChange(memberId: string, role: UserRole) {
    setBusyId(memberId);
    setError(null);
    try {
      await api.updateTeamRole(memberId, role);
      await load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusyId(null);
    }
  }

  async function handleRemove(memberId: string) {
    setBusyId(memberId);
    setError(null);
    try {
      await api.removeTeamMember(memberId);
      await load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusyId(null);
    }
  }

  async function handleStart2FASetup() {
    setMfaError(null);
    setMfaLoading(true);
    try {
      const res = await setup2FA();
      setSecretKey(res.secret);
      setQrUri(res.qr_uri);
      setTotpInput("");
      setSetupModalOpen(true);
    } catch (e: any) {
      setMfaError(e.message || "Failed to start 2FA setup");
    } finally {
      setMfaLoading(false);
    }
  }

  async function handleEnable2FA(e: React.FormEvent) {
    e.preventDefault();
    setMfaError(null);
    setMfaLoading(true);
    try {
      await enable2FA(totpInput, secretKey);
      setMfaEnabled(true);
      setSetupModalOpen(false);
      if (refreshUser) refreshUser();
    } catch (e: any) {
      setMfaError(e.message || "Invalid verification code");
    } finally {
      setMfaLoading(false);
    }
  }

  async function handleDisable2FA(e: React.FormEvent) {
    e.preventDefault();
    setMfaError(null);
    setMfaLoading(true);
    try {
      await disable2FA(totpInput);
      setMfaEnabled(false);
      setDisableModalOpen(false);
      if (refreshUser) refreshUser();
    } catch (e: any) {
      setMfaError(e.message || "Invalid verification code");
    } finally {
      setMfaLoading(false);
    }
  }

  function copyToClipboard(text: string) {
    navigator.clipboard.writeText(text);
    setCopiedSecret(true);
    setTimeout(() => setCopiedSecret(false), 2000);
  }

  return (
    <div className="max-w-3xl space-y-8">
      <div>
        <div className="flex items-center justify-between mb-1">
          <h1 className="text-2xl font-semibold text-slate-900">Team Management</h1>
          {canManage && (
            <button
              onClick={() => setShowForm((v) => !v)}
              className="rounded-lg bg-brand-600 text-white px-4 py-2 text-sm font-medium hover:bg-brand-700 transition"
            >
              {showForm ? "Cancel" : "+ Invite Member"}
            </button>
          )}
        </div>
        <p className="text-slate-500 text-sm">
          Owners can manage everything including the team. Admins can invite members and
          delete records, but can't change roles or grant the owner role.
        </p>
      </div>

      {showForm && canManage && (
        <form onSubmit={handleInvite} className="rounded-xl border border-slate-200 bg-white p-5 grid grid-cols-2 gap-4 shadow-xs">
          <input
            required
            placeholder="Name"
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500/20"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
          <input
            required
            type="email"
            placeholder="Email"
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500/20"
            value={form.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })}
          />
          <input
            required
            type="password"
            minLength={8}
            placeholder="Temporary password"
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500/20"
            value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
          />
          <select
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500/20"
            value={form.role}
            onChange={(e) => setForm({ ...form, role: e.target.value as UserRole })}
          >
            <option value="member">Member</option>
            <option value="admin">Admin</option>
            {isOwner && <option value="owner">Owner</option>}
          </select>
          {error && <p className="col-span-2 text-sm text-red-500">{error}</p>}
          <button
            disabled={saving}
            className="col-span-2 rounded-lg bg-brand-600 text-white px-4 py-2 text-sm font-medium hover:bg-brand-700 disabled:opacity-50 transition"
          >
            {saving ? "Inviting…" : "Invite"}
          </button>
        </form>
      )}

      {error && !showForm && <p className="text-sm text-red-500 mb-4">{error}</p>}

      <div className="rounded-xl border border-slate-200 bg-white overflow-hidden shadow-2xs">
        {loading ? (
          <p className="p-5 text-sm text-slate-400">Loading…</p>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-slate-500 text-xs uppercase">
              <tr>
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">Email</th>
                <th className="px-4 py-3">Role</th>
                {isOwner && <th className="px-4 py-3">Actions</th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {members.map((m) => (
                <tr key={m.id}>
                  <td className="px-4 py-3 font-medium">
                    {m.name} {m.id === user.id && <span className="text-xs text-slate-400">(you)</span>}
                  </td>
                  <td className="px-4 py-3 text-slate-500">{m.email}</td>
                  <td className="px-4 py-3">
                    {isOwner ? (
                      <select
                        className="text-xs rounded-full border-0 px-2 py-1 font-medium"
                        style={{ backgroundColor: "transparent" }}
                        value={m.role}
                        disabled={busyId === m.id}
                        onChange={(e) => handleRoleChange(m.id, e.target.value as UserRole)}
                      >
                        <option value="owner">Owner</option>
                        <option value="admin">Admin</option>
                        <option value="member">Member</option>
                      </select>
                    ) : (
                      <span className={`text-xs font-medium rounded-full px-2 py-0.5 ${ROLE_COLORS[m.role]}`}>
                        {ROLE_LABELS[m.role]}
                      </span>
                    )}
                  </td>
                  {isOwner && (
                    <td className="px-4 py-3">
                      {m.id !== user.id && (
                        <button
                          onClick={() => handleRemove(m.id)}
                          disabled={busyId === m.id}
                          className="text-xs font-medium text-slate-400 hover:text-red-500 disabled:opacity-50"
                        >
                          Remove
                        </button>
                      )}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Two-Factor Authentication Security Card */}
      <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-2xs space-y-4">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <div className={`p-3 rounded-xl ${mfaEnabled ? "bg-emerald-50 text-emerald-600" : "bg-amber-50 text-amber-600"}`}>
              {mfaEnabled ? <ShieldCheck className="w-6 h-6" /> : <ShieldAlert className="w-6 h-6" />}
            </div>
            <div>
              <h2 className="text-base font-semibold text-slate-900 flex items-center gap-2">
                <span>Two-Factor Authentication (2FA)</span>
                <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${mfaEnabled ? "bg-emerald-100 text-emerald-800" : "bg-amber-100 text-amber-800"}`}>
                  {mfaEnabled ? "Enabled" : "Disabled"}
                </span>
              </h2>
              <p className="text-xs text-slate-500 mt-0.5">
                Add an extra layer of security to your account using Google Authenticator, Authy, or 1Password.
              </p>
            </div>
          </div>

          <div>
            {!mfaEnabled ? (
              <button
                onClick={handleStart2FASetup}
                disabled={mfaLoading}
                className="inline-flex items-center gap-2 rounded-xl bg-brand-600 text-white px-4 py-2 text-xs font-semibold hover:bg-brand-700 disabled:opacity-50 transition shadow-xs"
              >
                <KeyRound className="w-4 h-4" />
                <span>Enable 2FA</span>
              </button>
            ) : (
              <button
                onClick={() => {
                  setTotpInput("");
                  setMfaError(null);
                  setDisableModalOpen(true);
                }}
                className="inline-flex items-center gap-2 rounded-xl bg-rose-50 text-rose-700 border border-rose-200 px-4 py-2 text-xs font-semibold hover:bg-rose-100 transition"
              >
                <span>Disable 2FA</span>
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Enable 2FA Setup Modal */}
      {setupModalOpen && (
        <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-md w-full p-6 shadow-2xl space-y-5 border border-slate-100">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <div className="flex items-center gap-2">
                <ShieldCheck className="w-5 h-5 text-emerald-600" />
                <h3 className="font-semibold text-slate-900 text-base">Setup 2-Factor Authentication</h3>
              </div>
              <button onClick={() => setSetupModalOpen(false)} className="text-slate-400 hover:text-slate-600">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-4">
              <p className="text-xs text-slate-600">
                1. Scan this QR code with your authenticator app (Google Authenticator, Authy, or 1Password):
              </p>

              <div className="flex flex-col items-center justify-center p-4 bg-slate-50 rounded-xl border border-slate-200 space-y-3">
                {qrUri && (
                  <img
                    src={`https://api.qrserver.com/v1/create-qr-code/?size=180x180&data=${encodeURIComponent(qrUri)}`}
                    alt="2FA QR Code"
                    className="w-44 h-44 rounded-lg shadow-xs"
                  />
                )}
                <div className="text-center w-full">
                  <p className="text-[11px] text-slate-400 font-medium uppercase mb-1">Manual Entry Code</p>
                  <div className="flex items-center justify-center gap-2 bg-white px-3 py-1.5 rounded-lg border border-slate-200">
                    <code className="text-xs font-mono font-bold text-slate-800 tracking-wider">{secretKey}</code>
                    <button
                      type="button"
                      onClick={() => copyToClipboard(secretKey)}
                      className="text-slate-400 hover:text-brand-600 transition"
                      title="Copy Secret"
                    >
                      {copiedSecret ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5" />}
                    </button>
                  </div>
                </div>
              </div>

              <form onSubmit={handleEnable2FA} className="space-y-3 pt-2">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
                    2. Enter 6-digit verification code from your app:
                  </label>
                  <input
                    type="text"
                    required
                    maxLength={6}
                    placeholder="000000"
                    className="w-full text-center tracking-[0.5em] text-lg font-mono rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-slate-900 outline-none focus:border-emerald-500 focus:bg-white focus:ring-2 focus:ring-emerald-500/10 transition"
                    value={totpInput}
                    onChange={(e) => setTotpInput(e.target.value.replace(/\D/g, ""))}
                  />
                </div>

                {mfaError && (
                  <div className="rounded-xl border border-rose-200 bg-rose-50 p-2.5 text-xs text-rose-700 text-center font-medium">
                    {mfaError}
                  </div>
                )}

                <div className="flex gap-2 pt-2">
                  <button
                    type="button"
                    onClick={() => setSetupModalOpen(false)}
                    className="flex-1 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 transition"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={mfaLoading || totpInput.length !== 6}
                    className="flex-1 rounded-xl bg-emerald-600 px-4 py-2.5 text-xs font-semibold text-white shadow-xs hover:bg-emerald-700 disabled:opacity-50 transition"
                  >
                    {mfaLoading ? "Verifying…" : "Verify & Enable"}
                  </button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}

      {/* Disable 2FA Modal */}
      {disableModalOpen && (
        <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-md w-full p-6 shadow-2xl space-y-5 border border-slate-100">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <div className="flex items-center gap-2 text-rose-600">
                <ShieldAlert className="w-5 h-5" />
                <h3 className="font-semibold text-slate-900 text-base">Disable Two-Factor Authentication</h3>
              </div>
              <button onClick={() => setDisableModalOpen(false)} className="text-slate-400 hover:text-slate-600">
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleDisable2FA} className="space-y-4">
              <p className="text-xs text-slate-600 leading-relaxed">
                Disabling 2FA will lower your account security. Please enter your 6-digit authenticator code to confirm.
              </p>

              <div>
                <input
                  type="text"
                  required
                  maxLength={6}
                  placeholder="000000"
                  className="w-full text-center tracking-[0.5em] text-lg font-mono rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-slate-900 outline-none focus:border-rose-500 focus:bg-white focus:ring-2 focus:ring-rose-500/10 transition"
                  value={totpInput}
                  onChange={(e) => setTotpInput(e.target.value.replace(/\D/g, ""))}
                />
              </div>

              {mfaError && (
                <div className="rounded-xl border border-rose-200 bg-rose-50 p-2.5 text-xs text-rose-700 text-center font-medium">
                  {mfaError}
                </div>
              )}

              <div className="flex gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setDisableModalOpen(false)}
                  className="flex-1 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={mfaLoading || totpInput.length !== 6}
                  className="flex-1 rounded-xl bg-rose-600 px-4 py-2.5 text-xs font-semibold text-white shadow-xs hover:bg-rose-700 disabled:opacity-50 transition"
                >
                  {mfaLoading ? "Disabling…" : "Confirm Disable"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
