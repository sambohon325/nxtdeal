"use client";

// NXTDeal Hub -- NXTDeal Network Connect console panel (2026-07-19).
//
// The NXTDeal-staff-facing half of the free-tier flywheel Sam described
// ("Give Value -> Collect Data -> Create Insight -> Create Dependency ->
// Upgrade To NXTDeal"). The prospect-facing half is the browser extension
// (network-connect-extension/) -- signup, connector self-reporting, KPI
// submission, and the benchmark dashboard all happen there, gated by an
// account_token/pseudonym the extension holds locally. This panel is the
// OTHER side: the real account roster, tier/status administration,
// Migration Readiness scoring, and the one-click "convert to a real Dealer"
// action -- all gated by the same per-employee bearer token (POST
// /hub/auth/login, see lib/hubApi.ts) every other Hub-console panel already
// uses.
//
// See hub/core/network_connect.py's own module docstring for the full
// "two data flows, two privacy postures" design: everything on this panel
// (company name, contact email, connected systems, tier, migration
// readiness) is the IDENTIFIED half NXTDeal legitimately knows -- this
// panel deliberately has no access to, and cannot join against, the
// anonymized KPI benchmark pool (hub/storage/network_snapshots.json),
// which is keyed only by a pseudonym never stored on any account record.

import { useEffect, useState } from "react";
import {
  HubApiError,
  getNetworkConnectOverview,
  listNetworkConnectAccounts,
  getNetworkConnectAccount,
  setNetworkConnectTier,
  setNetworkConnectStatus,
  setNetworkConnectReadiness,
  convertNetworkConnectAccountToDealer,
  type NetworkConnectOverview,
  type NetworkConnectAccountSummary,
  type NetworkConnectAccountDetail,
  type NetworkConnectGoLiveStatus,
  type ConvertToDealerResult,
} from "@/lib/hubApi";

function errorMessage(error: unknown): string {
  return error instanceof HubApiError ? error.message : "Unable to reach the Hub.";
}

function KpiCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="bg-zinc-900 rounded-lg p-4">
      <div className="text-2xl font-semibold">{value}</div>
      <div className="text-[11px] uppercase tracking-wide text-zinc-500 mt-1">{label}</div>
    </div>
  );
}

function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="mb-4 text-sm text-red-400 bg-red-950/30 border border-red-900 rounded-lg px-4 py-3">
      {message}
    </div>
  );
}

const GO_LIVE_STYLE: Record<NetworkConnectGoLiveStatus, { text: string; label: string }> = {
  not_started: { text: "text-zinc-500", label: "Not Started" },
  blocked: { text: "text-red-400", label: "Blocked" },
  at_risk: { text: "text-amber-400", label: "At Risk" },
  ready: { text: "text-emerald-400", label: "Ready" },
};

const READINESS_LABELS: Record<string, string> = {
  crm: "CRM Migration",
  inventory: "Inventory",
  service: "Service",
  finance: "Finance",
};

export default function NetworkConnectSection() {
  const [overview, setOverview] = useState<NetworkConnectOverview | null>(null);
  const [accounts, setAccounts] = useState<NetworkConnectAccountSummary[] | null>(null);
  const [error, setError] = useState("");
  const [selectedAccountId, setSelectedAccountId] = useState<string | null>(null);

  async function load() {
    try {
      const [o, a] = await Promise.all([getNetworkConnectOverview(), listNetworkConnectAccounts()]);
      setOverview(o);
      setAccounts(a.accounts);
      setError("");
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  useEffect(() => {
    load();
  }, []);

  if (selectedAccountId) {
    return (
      <AccountDetailPanel
        accountId={selectedAccountId}
        onBack={() => setSelectedAccountId(null)}
        onChanged={load}
      />
    );
  }

  return (
    <div>
      <div className="mb-4">
        <h2 className="text-lg font-brand font-bold tracking-tight">NXTDeal Network Connect</h2>
        <p className="text-xs text-zinc-500 mt-1 max-w-2xl leading-relaxed">
          The free-tier pre-customer flywheel -- prospects sign up and submit KPIs through
          the browser extension, completely anonymously for benchmarking. This panel is the
          identified half: who signed up, what they told us they use, their Migration
          Readiness, and converting them into a real NXTDeal tenant.
        </p>
      </div>

      {error && <ErrorBanner message={error} />}

      <div className="grid grid-cols-3 gap-3 mb-3">
        <KpiCard label="Total Accounts" value={overview?.total_accounts ?? "..."} />
        <KpiCard label="Free Tier" value={overview?.by_tier.free ?? "..."} />
        <KpiCard label="Premium Tier" value={overview?.by_tier.premium ?? "..."} />
      </div>
      <div className="grid grid-cols-4 gap-3 mb-6">
        <KpiCard label="Ready" value={overview?.by_go_live_status.ready ?? "..."} />
        <KpiCard label="At Risk" value={overview?.by_go_live_status.at_risk ?? "..."} />
        <KpiCard label="Blocked" value={overview?.by_go_live_status.blocked ?? "..."} />
        <KpiCard label="Converted To Dealer" value={overview?.converted_to_dealer_count ?? "..."} />
      </div>

      {overview && (
        <div className="mb-6">
          <div className="text-[11px] uppercase tracking-wide text-zinc-500 mb-2">
            Connector Adoption (self-reported)
          </div>
          <div className="grid grid-cols-5 gap-3">
            {Object.entries(overview.connector_adoption).map(([category, count]) => (
              <div key={category} className="bg-zinc-900 rounded-lg p-3 text-center">
                <div className="text-lg font-semibold">{count}</div>
                <div className="text-[10px] uppercase tracking-wide text-zinc-500 mt-1">{category}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      <h3 className="font-brand font-bold uppercase tracking-wide text-sm mb-3">Accounts</h3>

      {accounts && accounts.length === 0 && (
        <div className="text-sm text-zinc-500 bg-zinc-900 rounded-lg p-5">
          No Network Connect accounts have signed up yet -- accounts are created via the
          browser extension&apos;s signup screen (network-connect-extension/), not from this
          console.
        </div>
      )}

      {accounts && accounts.length > 0 && (
        <div className="bg-zinc-900 rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-[10px] uppercase tracking-wide text-zinc-500 border-b border-zinc-800">
                <th className="text-left px-4 py-2">Company</th>
                <th className="text-left px-4 py-2">Contact</th>
                <th className="text-left px-4 py-2">Tier</th>
                <th className="text-left px-4 py-2">Status</th>
                <th className="text-left px-4 py-2">Connected</th>
                <th className="text-left px-4 py-2">Go-Live</th>
                <th className="text-left px-4 py-2">Created</th>
              </tr>
            </thead>
            <tbody>
              {accounts.map((a) => {
                const goLive = GO_LIVE_STYLE[a.go_live_status];
                return (
                  <tr
                    key={a.account_id}
                    onClick={() => setSelectedAccountId(a.account_id)}
                    className="border-b border-zinc-800/60 last:border-0 hover:bg-zinc-800/40 cursor-pointer"
                  >
                    <td className="px-4 py-3 font-medium">{a.company_name}</td>
                    <td className="px-4 py-3 text-zinc-400 text-xs">{a.contact_email}</td>
                    <td className="px-4 py-3">
                      <span
                        className={
                          a.tier === "premium"
                            ? "text-[10px] uppercase tracking-wide bg-yellow-950/40 text-yellow-400 px-2 py-0.5 rounded"
                            : "text-[10px] uppercase tracking-wide bg-zinc-800 text-zinc-400 px-2 py-0.5 rounded"
                        }
                      >
                        {a.tier}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-xs text-zinc-400">{a.status}</td>
                    <td className="px-4 py-3 text-xs text-zinc-400">{a.connected_system_count} / 5</td>
                    <td className={`px-4 py-3 text-xs ${goLive.text}`}>{goLive.label}</td>
                    <td className="px-4 py-3 text-xs text-zinc-500">
                      {new Date(a.created_at).toLocaleDateString()}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {overview && <p className="text-[11px] text-zinc-500 mt-4 leading-relaxed">{overview.note}</p>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Account detail -- tier/status/readiness administration + convert-to-dealer
// ---------------------------------------------------------------------------

function AccountDetailPanel({
  accountId,
  onBack,
  onChanged,
}: {
  accountId: string;
  onBack: () => void;
  onChanged: () => void;
}) {
  const [account, setAccount] = useState<NetworkConnectAccountDetail | null>(null);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState("");
  const [readinessInputs, setReadinessInputs] = useState<Record<string, string>>({});
  const [convertResult, setConvertResult] = useState<ConvertToDealerResult | null>(null);
  const [converting, setConverting] = useState(false);
  const [confirmingConvert, setConfirmingConvert] = useState(false);

  async function load() {
    try {
      const detail = await getNetworkConnectAccount(accountId);
      setAccount(detail);
      const initial: Record<string, string> = {};
      detail.migration_readiness_detail.forEach((r) => {
        initial[r.key] = r.pct !== null ? String(r.pct) : "";
      });
      setReadinessInputs(initial);
      setError("");
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accountId]);

  async function handleTierChange(tier: "free" | "premium") {
    setSaving("tier");
    try {
      const updated = await setNetworkConnectTier(accountId, tier);
      setAccount(updated);
      onChanged();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setSaving("");
    }
  }

  async function handleStatusChange(status: "active" | "trial_expired" | "churned") {
    setSaving("status");
    try {
      const updated = await setNetworkConnectStatus(accountId, status);
      setAccount(updated);
      onChanged();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setSaving("");
    }
  }

  async function handleReadinessSave(category: string) {
    const raw = readinessInputs[category];
    const pct = Number(raw);
    if (raw === "" || Number.isNaN(pct) || pct < 0 || pct > 100) {
      setError(`${READINESS_LABELS[category] ?? category} readiness must be a number between 0 and 100.`);
      return;
    }
    setSaving(`readiness_${category}`);
    try {
      const updated = await setNetworkConnectReadiness(accountId, category, pct);
      setAccount(updated);
      setError("");
      onChanged();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setSaving("");
    }
  }

  async function handleConvert() {
    setConverting(true);
    setError("");
    try {
      const result = await convertNetworkConnectAccountToDealer(accountId, "Standard");
      setConvertResult(result);
      setConfirmingConvert(false);
      await load();
      onChanged();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setConverting(false);
    }
  }

  if (!account) {
    return (
      <div>
        <button onClick={onBack} className="text-xs text-zinc-500 hover:text-white underline mb-4">
          ← Back to Accounts
        </button>
        {error && <ErrorBanner message={error} />}
        <p className="text-sm text-zinc-500">Loading…</p>
      </div>
    );
  }

  const goLive = GO_LIVE_STYLE[account.go_live_status];
  const alreadyConverted = account.status === "converted_to_dealer";

  return (
    <div>
      <button onClick={onBack} className="text-xs text-zinc-500 hover:text-white underline mb-4">
        ← Back to Accounts
      </button>

      {error && <ErrorBanner message={error} />}

      <div className="flex items-start justify-between mb-6">
        <div>
          <h2 className="text-lg font-brand font-bold tracking-tight">{account.company_name}</h2>
          <div className="text-xs text-zinc-500 mt-1">
            {account.contact_email}
            {account.contact_name ? ` · ${account.contact_name}` : ""}
            {account.contact_phone ? ` · ${account.contact_phone}` : ""}
          </div>
          <div className="text-[11px] text-zinc-600 mt-1">{account.account_id}</div>
        </div>
        <div className={`text-sm font-semibold ${goLive.text}`}>{goLive.label}</div>
      </div>

      {convertResult && (
        <div className="mb-6 bg-emerald-950/30 border border-emerald-800 rounded-lg p-5">
          <div className="text-sm font-semibold text-emerald-300 mb-2">
            Converted to a real NXTDeal tenant -- {convertResult.dealer.dealer_id}
          </div>
          <p className="text-xs text-zinc-400 mb-3 leading-relaxed">{convertResult.note}</p>
          <div className="text-xs text-zinc-300 space-y-1 bg-zinc-950/60 rounded p-3">
            <div>
              Admin login: <span className="font-mono">{convertResult.admin_employee_id}</span>
            </div>
            <div>
              Temp password: <span className="font-mono">{convertResult.admin_temp_password}</span>
            </div>
          </div>
          <p className="text-[11px] text-yellow-500 mt-3">
            Save this password now -- it is shown exactly once, same as any other Hub-provisioned
            dealer.
          </p>
        </div>
      )}

      <div className="grid grid-cols-2 gap-4 mb-6">
        <div className="bg-zinc-900 rounded-lg p-4">
          <div className="text-[11px] uppercase tracking-wide text-zinc-500 mb-2">Tier</div>
          <div className="flex gap-2">
            {(["free", "premium"] as const).map((t) => (
              <button
                key={t}
                onClick={() => handleTierChange(t)}
                disabled={saving === "tier" || alreadyConverted}
                className={
                  account.tier === t
                    ? "bg-zinc-200 text-black font-medium px-3 py-1.5 rounded text-xs disabled:opacity-50"
                    : "bg-zinc-800 text-zinc-400 hover:text-white px-3 py-1.5 rounded text-xs transition disabled:opacity-50"
                }
              >
                {t}
              </button>
            ))}
          </div>
        </div>

        <div className="bg-zinc-900 rounded-lg p-4">
          <div className="text-[11px] uppercase tracking-wide text-zinc-500 mb-2">Status</div>
          <div className="flex gap-2 flex-wrap">
            {(["active", "trial_expired", "churned"] as const).map((s) => (
              <button
                key={s}
                onClick={() => handleStatusChange(s)}
                disabled={saving === "status" || alreadyConverted}
                className={
                  account.status === s
                    ? "bg-zinc-200 text-black font-medium px-3 py-1.5 rounded text-xs disabled:opacity-50"
                    : "bg-zinc-800 text-zinc-400 hover:text-white px-3 py-1.5 rounded text-xs transition disabled:opacity-50"
                }
              >
                {s.replace("_", " ")}
              </button>
            ))}
          </div>
        </div>
      </div>

      <h3 className="font-brand font-bold uppercase tracking-wide text-sm mb-2">Connected Systems</h3>
      <p className="text-[11px] text-zinc-500 mb-3">
        Self-reported by the account via the browser extension -- no real connector/OAuth
        integration exists for any of these yet (a separately-scoped later slice).
      </p>
      <div className="grid grid-cols-5 gap-3 mb-6">
        {account.connected_systems_detail.map((c) => (
          <div key={c.category} className="bg-zinc-900 rounded-lg p-3">
            <div className="text-[10px] uppercase tracking-wide text-zinc-500 mb-1">{c.label}</div>
            <div className="text-xs font-medium">
              {c.provider_display_name ?? <span className="text-zinc-600">Not connected</span>}
            </div>
          </div>
        ))}
      </div>

      <h3 className="font-brand font-bold uppercase tracking-wide text-sm mb-2">Migration Readiness</h3>
      <p className="text-[11px] text-zinc-500 mb-3 leading-relaxed">{account.migration_readiness_note}</p>
      <div className="grid grid-cols-2 gap-3 mb-2">
        {account.migration_readiness_detail.map((r) => (
          <div key={r.key} className="bg-zinc-900 rounded-lg p-4">
            <div className="text-[11px] uppercase tracking-wide text-zinc-500 mb-2">{r.label}</div>
            <div className="flex items-center gap-2">
              <input
                type="number"
                min={0}
                max={100}
                value={readinessInputs[r.key] ?? ""}
                onChange={(e) =>
                  setReadinessInputs((prev) => ({ ...prev, [r.key]: e.target.value }))
                }
                placeholder="pct"
                className="w-20 h-8 px-2 rounded bg-zinc-950 border border-zinc-800 text-sm"
              />
              <span className="text-xs text-zinc-500">%</span>
              <button
                onClick={() => handleReadinessSave(r.key)}
                disabled={saving === `readiness_${r.key}`}
                className="ml-auto bg-zinc-800 hover:bg-zinc-700 text-zinc-300 px-3 py-1.5 rounded text-xs transition disabled:opacity-50"
              >
                Save
              </button>
            </div>
          </div>
        ))}
      </div>
      <p className="text-[11px] text-zinc-600 mb-6">
        Go-Live reason: {account.go_live_reason}
      </p>

      <div className="border-t border-zinc-800 pt-5">
        <h3 className="font-brand font-bold uppercase tracking-wide text-sm mb-2">
          Convert To NXTDeal Tenant
        </h3>
        {alreadyConverted ? (
          <p className="text-sm text-emerald-400">
            Already converted -- dealer {account.converted_dealer_id}.
          </p>
        ) : (
          <>
            <p className="text-[11px] text-zinc-500 mb-3 max-w-xl leading-relaxed">
              Scaffolds a real, empty NXTDeal tenant instance (same as any other
              Hub-provisioned dealer) and generates a real admin login. No data import
              happens here -- walk the new dealer through real data import the same way any
              other new dealer onboarding does.
            </p>
            {!confirmingConvert ? (
              <button
                onClick={() => setConfirmingConvert(true)}
                className="brand-cta font-brand font-bold uppercase tracking-wide text-xs px-5 py-2.5"
              >
                Convert To Dealer
              </button>
            ) : (
              <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4 max-w-md">
                <p className="text-sm mb-3">
                  Create a real NXTDeal tenant for <strong>{account.company_name}</strong>?
                  This action cannot be undone from this screen.
                </p>
                <div className="flex gap-2">
                  <button
                    onClick={handleConvert}
                    disabled={converting}
                    className="brand-cta font-brand font-bold uppercase tracking-wide text-xs px-4 py-2 disabled:opacity-50"
                  >
                    {converting ? "Converting…" : "Confirm"}
                  </button>
                  <button
                    onClick={() => setConfirmingConvert(false)}
                    disabled={converting}
                    className="bg-zinc-800 text-zinc-400 hover:text-white px-4 py-2 rounded text-xs transition"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
