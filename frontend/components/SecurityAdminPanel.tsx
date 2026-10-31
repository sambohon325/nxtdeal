"use client";
import { WorkButton, WorkInput } from "./WorkspaceUi";
import { WorkField } from "./WorkField";

// Administration's "Security" item, expansion (Administration Control Center
// rebuild, continued) -- real per-employee account-lockout lookup/unlock and
// IP allowlist management (core/auth_api.py's get_lockout_status()/
// unlock_account()/set_ip_allowlist()), layered ABOVE the existing generic
// /menu/data render (which already carries the roster-wide login-activity/
// failed-logins/security-events/account-lockouts/ip-allowlist-coverage
// summary from core/administration_menu.py's security()) -- same "ABOVE, not
// instead of" precedent this codebase's other Overview enrichments (Sales,
// Operations, Service) established. Lockout lookup/unlock is ADMIN/
// OPERATIONS; setting an IP allowlist is ADMIN-only, narrower, since
// misconfiguring it can lock an employee out of the platform entirely -- the
// backend enforces both, this panel just surfaces the actions.
import { useState } from "react";
import { getLockoutStatus, unlockAccount, setIpAllowlist, type LockoutStatus } from "@/lib/securityAdmin";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

function Btn({ onClick, children, disabled, tone }: { onClick: () => void; children: React.ReactNode; disabled?: boolean; tone?: "primary" | "danger" }) {
  return (
    <WorkButton type="submit"
      onClick={onClick}
      disabled={disabled}
      className={`text-xs px-2.5 py-1 rounded font-medium disabled:opacity-40 ${
        tone === "danger" ? "bg-red-900/60 text-red-200 hover:bg-red-900" : tone === "primary" ? "bg-zinc-200 text-black hover:bg-white" : "bg-zinc-800 text-zinc-300 hover:bg-zinc-700"
      }`}
    >
      {children}
    </WorkButton>
  );
}

function fmt(ts: string | null | undefined): string {
  if (!ts) return "—";
  try {
    return new Date(ts).toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  } catch {
    return ts;
  }
}

export function SecurityAdminPanel({ theme }: { theme: Theme }) {
  const [employeeId, setEmployeeId] = useState("");
  const [status, setStatus] = useState<LockoutStatus | null>(null);
  const [ipText, setIpText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleLookup() {
    if (!employeeId.trim()) return;
    setLoading(true);
    setError(null);
    setMessage(null);
    try {
      const s = await getLockoutStatus(employeeId.trim().toUpperCase());
      setStatus(s);
      setIpText("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to look up this employee's lockout status.");
      setStatus(null);
    } finally {
      setLoading(false);
    }
  }

  async function handleUnlock() {
    if (!status) return;
    try {
      await unlockAccount(status.employee_id);
      setMessage(`${status.employee_id} unlocked.`);
      handleLookup();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to unlock this account.");
    }
  }

  async function handleSetAllowlist() {
    if (!status) return;
    const list = ipText.split(",").map((s) => s.trim()).filter(Boolean);
    try {
      await setIpAllowlist(status.employee_id, list);
      setMessage(`IP allowlist updated for ${status.employee_id} (${list.length} entr${list.length === 1 ? "y" : "ies"}).`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to set the IP allowlist (ADMIN role required).");
    }
  }

  return (
    <div className={tc(theme, "rounded-lg border border-zinc-800 bg-brand-charcoal p-3 mb-4", "rounded-lg border border-zinc-200 bg-zinc-50 p-3 mb-4")}>
      <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">
        Account Lockout &amp; IP Allowlist Lookup
      </div>
      <div className="flex items-center gap-2 mb-2">
        <WorkField label="EMP-00001"><WorkInput
          value={employeeId}
          onChange={(e) => setEmployeeId(e.target.value)}
          placeholder="EMP-00001"
          className="text-xs px-2 py-1 rounded bg-zinc-900 border border-zinc-700 text-zinc-200 placeholder:text-zinc-600 w-40"
          onKeyDown={(e) => e.key === "Enter" && handleLookup()}
        /></WorkField>
        <Btn tone="primary" onClick={handleLookup} disabled={!employeeId.trim() || loading}>{loading ? "Looking up…" : "Look Up"}</Btn>
      </div>

      {error && <div className="text-xs text-red-400 mb-2">{error}</div>}
      {message && <div className="text-xs text-emerald-400 mb-2">{message}</div>}

      {status && (
        <div className="text-xs space-y-2">
          <div className="flex items-center gap-2">
            <span className="text-zinc-200">{status.employee_id}</span>
            <span className={`px-1.5 py-0.5 rounded text-xs ${status.locked ? "bg-red-950/40 text-red-300" : "bg-emerald-950/40 text-emerald-300"}`}>
              {status.locked ? "LOCKED" : "not locked"}
            </span>
            <span className="text-zinc-500">failed attempts: {status.failed_attempts}</span>
            {status.locked_until && <span className="text-zinc-500">until {fmt(status.locked_until)}</span>}
          </div>
          {status.locked && (
            <Btn tone="primary" onClick={handleUnlock}>Unlock Account Now</Btn>
          )}

          <div className="pt-2 border-t border-zinc-800">
            <div className="text-zinc-500 mb-1">
              IP Allowlist (comma-separated, ADMIN-only — an empty list means unrestricted, the default)
            </div>
            <div className="flex items-center gap-2">
              <WorkField label="Ip Text"><WorkInput
                value={ipText}
                onChange={(e) => setIpText(e.target.value)}
                placeholder="e.g. 203.0.113.5, 198.51.100.0/24"
                className="flex-1 text-xs px-2 py-1 rounded bg-zinc-900 border border-zinc-700 text-zinc-200 placeholder:text-zinc-600"
              /></WorkField>
              <Btn tone="danger" onClick={handleSetAllowlist}>Set Allowlist</Btn>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
