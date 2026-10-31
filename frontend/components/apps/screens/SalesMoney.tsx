"use client";

// SalesMoney — the MySales "Money" screen (2026-07-24, Sam: a light self-accounting app,
// connect banks via Plaid, budgets, bank accounts + commissions together, AI budget advisor).
// Reads /finance/overview and lets the rep link a bank (Plaid seam — simulated until a real
// provider is connected), set budgets, and log commissions. The AI advisor is rules-based.

import { useRef, useState } from "react";
import { type AppDef, type AppScreen, accentOf } from "@/lib/apps/registry";
import {
  fetchFinanceOverview,
  linkBank,
  setBudget,
  recordCommission,
  type FinanceOverview,
  type AdvisorInsight,
} from "@/lib/repFinance";
import { useAsync, WiredScreen, StatGrid } from "./kit";

function money(n: number): string {
  return `$${(n ?? 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

const INSIGHT_STYLE: Record<AdvisorInsight["type"], string> = {
  warning: "border-amber-500/30 bg-amber-500/10",
  tip: "border-sky-500/30 bg-sky-500/10",
  win: "border-emerald-500/30 bg-emerald-500/10",
};
const INSIGHT_ICON: Record<AdvisorInsight["type"], string> = { warning: "⚠️", tip: "💡", win: "✅" };

const CATEGORIES = ["Groceries", "Dining", "Transportation", "Shopping", "Bills", "Entertainment"];

export function SalesMoney({ app, screen }: { app: AppDef; screen: AppScreen }) {
  const accent = accentOf(app);
  const { loading, error, data, reload } = useAsync<FinanceOverview>(() => fetchFinanceOverview(), []);
  const inFlight = useRef(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // budget form
  const [cat, setCat] = useState(CATEGORIES[0]);
  const [limit, setLimit] = useState("");
  // commission form
  const [commAmt, setCommAmt] = useState("");
  const [commStatus, setCommStatus] = useState<"projected" | "pending" | "paid">("pending");

  async function doLink() {
    if (inFlight.current) return;
    inFlight.current = true;
    setActionError(null);
    setBusy(true);
    try {
      await linkBank();
      reload();
    } catch {
      setActionError("Your change could not be confirmed. Refresh the screen before trying again.");
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  async function saveBudget() {
    const n = Number(limit);
    if (!Number.isFinite(n) || n <= 0 || busy) return;
    if (inFlight.current) return;
    inFlight.current = true;
    setActionError(null);
    setBusy(true);
    try {
      await setBudget(cat, n);
      setLimit("");
      reload();
    } catch {
      setActionError("Your change could not be confirmed. Refresh the screen before trying again.");
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  async function logCommission() {
    const n = Number(commAmt);
    if (!Number.isFinite(n) || n <= 0 || busy) return;
    if (inFlight.current) return;
    inFlight.current = true;
    setActionError(null);
    setBusy(true);
    try {
      await recordCommission({ amount: n, status: commStatus });
      setCommAmt("");
      reload();
    } catch {
      setActionError("Your change could not be confirmed. Refresh the screen before trying again.");
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  const inputCls =
    "w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white placeholder-zinc-500 focus:border-[var(--app-accent)] focus:outline-none";

  return (
    <WiredScreen app={app} screen={screen} loading={loading} error={error} empty={!data} onRetry={reload}>
      {data && (
        <>
          {actionError && <div role="alert" className="text-sm text-amber-200">{actionError} <button onClick={reload} className="underline">Refresh</button></div>}
          {data.accounts.length > 0 && (
            <p role="status" className="rounded-xl border border-amber-500/20 p-3 text-xs text-amber-200">Bank feed not verified: the current linking flow loads demo balances and spending, even when a provider is listed as available.</p>
          )}
          {!data.linked ? (
            <div className="rounded-2xl border border-white/10 bg-white/[0.05] p-5 text-center backdrop-blur-sm">
              <div className="text-3xl">🏦</div>
              <h3 className="mt-2 text-sm font-semibold text-white">Bank accounts</h3>
              <p className="mx-auto mt-1 max-w-sm text-xs text-zinc-400">
                Review balances and spending alongside your budgets. A live bank connection requires a configured provider; demo accounts contain simulated data.
              </p>
              <button
                onClick={doLink}
                disabled={busy}
                className="mt-3 rounded-full bg-[var(--app-accent)] px-5 py-2.5 text-sm font-semibold text-[var(--app-accent-text)] disabled:opacity-50"
              >
                {busy ? "Loading…" : "Load demo bank accounts"}
              </button>
            </div>
          ) : (
            <StatGrid
              app={app}
              stats={[
                { label: "Cash", value: money(data.cash_total) },
                { label: "Paid", value: money(data.commissions.totals.paid ?? 0), hint: "commissions" },
                { label: "Pending", value: money(data.commissions.totals.pending ?? 0), hint: "commissions" },
                { label: "Projected", value: money(data.commissions.totals.projected ?? 0), hint: "commissions" },
              ]}
            />
          )}

          {/* Existing rules-based budget observations; no assistant panel. */}
          {data.advisor.length > 0 && (
            <div className="space-y-2">
              <div className="text-[11px] uppercase tracking-wide text-zinc-500">Budget observations</div>
              {data.advisor.map((ins, i) => (
                <div key={i} className={`flex gap-2.5 rounded-xl border p-3 ${INSIGHT_STYLE[ins.type]}`}>
                  <span className="text-base leading-none">{INSIGHT_ICON[ins.type]}</span>
                  <div>
                    <div className="text-sm font-semibold text-white">{ins.title}</div>
                    <div className="text-[11px] text-zinc-300">{ins.detail}</div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Accounts */}
          {data.accounts.length > 0 && (
            <div className="rounded-2xl border border-white/10 bg-white/[0.05] p-4 backdrop-blur-sm">
              <div className="mb-2 text-sm font-semibold text-white">Accounts</div>
              <div className="space-y-2">
                {data.accounts.map((a) => (
                  <div key={a.id} className="flex items-center justify-between rounded-lg border border-white/5 px-3 py-2">
                    <div className="text-sm text-zinc-100">
                      {a.name} <span className="text-[11px] text-zinc-500">••{a.mask} · {a.type}</span>
                    </div>
                    <div className={`text-sm font-semibold ${accent.text}`}>{money(a.balance)}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Budgets */}
          <div className="rounded-2xl border border-white/10 bg-white/[0.05] p-4 backdrop-blur-sm">
            <div className="mb-2 text-sm font-semibold text-white">Budgets</div>
            <div className="space-y-2.5">
              {data.budgets.map((b) => (
                <div key={b.id}>
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-zinc-200">{b.category}</span>
                    <span className={b.over ? "text-amber-300" : "text-zinc-400"}>
                      {money(b.spent)} / {money(b.limit)}
                    </span>
                  </div>
                  <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-white/10">
                    <div
                      className={`h-full rounded-full ${b.over ? "bg-amber-400" : "bg-[var(--app-accent)]"}`}
                      style={{ width: `${Math.min(b.pct, 100)}%` }}
                    />
                  </div>
                </div>
              ))}
              {data.budgets.length === 0 && <p className="text-xs text-zinc-500">No budgets yet — add one below.</p>}
            </div>
            <div className="mt-3 flex gap-2">
              <select aria-label="Budget category" value={cat} onChange={(e) => setCat(e.target.value)} className={`${inputCls} flex-1`}>
                {CATEGORIES.map((c) => (
                  <option key={c} value={c} className="bg-zinc-900">{c}</option>
                ))}
              </select>
              <input
                aria-label="Monthly budget amount"
                value={limit}
                onChange={(e) => setLimit(e.target.value)}
                inputMode="decimal"
                placeholder="Monthly $"
                className={`${inputCls} w-28`}
              />
              <button
                onClick={saveBudget}
                disabled={busy || !limit}
                className="rounded-full bg-[var(--app-accent)] px-4 text-sm font-semibold text-[var(--app-accent-text)] disabled:opacity-40"
              >
                Set
              </button>
            </div>
          </div>

          {/* Commissions */}
          <div className="rounded-2xl border border-white/10 bg-white/[0.05] p-4 backdrop-blur-sm">
            <div className="mb-2 text-sm font-semibold text-white">Commissions</div>
            <div className="space-y-1.5">
              {data.commissions.recent.map((c) => (
                <div key={c.id} className="flex items-center justify-between rounded-lg border border-white/5 px-3 py-1.5 text-xs">
                  <span className="text-zinc-400">{c.date}{c.source ? ` · ${c.source}` : ""}</span>
                  <span className="flex items-center gap-2">
                    <span className="capitalize text-zinc-500">{c.status}</span>
                    <span className="font-semibold text-zinc-100">{money(c.amount)}</span>
                  </span>
                </div>
              ))}
              {data.commissions.recent.length === 0 && <p className="text-xs text-zinc-500">No commissions logged yet.</p>}
            </div>
            <div className="mt-3 flex gap-2">
              <input
                aria-label="Commission amount"
                value={commAmt}
                onChange={(e) => setCommAmt(e.target.value)}
                inputMode="decimal"
                placeholder="Amount $"
                className={`${inputCls} flex-1`}
              />
              <select aria-label="Commission status" value={commStatus} onChange={(e) => setCommStatus(e.target.value as typeof commStatus)} className={`${inputCls} w-32`}>
                <option value="projected" className="bg-zinc-900">Projected</option>
                <option value="pending" className="bg-zinc-900">Pending</option>
                <option value="paid" className="bg-zinc-900">Paid</option>
              </select>
              <button
                onClick={logCommission}
                disabled={busy || !commAmt}
                className="rounded-full bg-[var(--app-accent)] px-4 text-sm font-semibold text-[var(--app-accent-text)] disabled:opacity-40"
              >
                Log
              </button>
            </div>
          </div>
        </>
      )}
    </WiredScreen>
  );
}
