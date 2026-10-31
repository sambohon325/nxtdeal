"use client";
import { WorkInput, WorkButton , WorkStat} from "./WorkspaceUi";
import { WorkField } from "./WorkField";

// Finance's "Payments" item -- the real payment ledger, the second slice of Sam's
// "Retail Automotive Lending Platform" expansion (2026-07-17), right after
// Portfolio. The per-loan actions (record a payment, manage Auto Drafts, track
// Promises To Pay, issue a Customer Payment Portal link) live on
// PortfolioBoard.tsx's LoanDetailModal's "Payments" tab -- reused here directly
// (imported, not duplicated) so there's only one real loan workspace in this
// codebase. This board is the department-wide view: real ledger totals, a
// "Run Due Auto Drafts" action, and cross-loan Promises To Pay / Payoff Requests
// queues.
import { PRODUCT_ACCENT_COLORS } from "@/lib/productTheme";
import { useEffect, useState } from "react";
import {
  getPaymentsDashboard,
  runDueAutoDrafts,
  listPromisesToPay,
  listPayoffRequests,
  fulfillPayoffRequest,
  type PaymentsDashboard,
  type PromiseToPay,
  type PayoffRequest,
  type PromiseStatus,
} from "@/lib/payments";
import { LoanDetailModal } from "@/components/PortfolioBoard";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const RIBBON = PRODUCT_ACCENT_COLORS;

function money(v: number | string | null | undefined): string {
  if (v === null || v === undefined || v === "") return "—";
  const n = typeof v === "string" ? parseFloat(v) : v;
  if (Number.isNaN(n)) return String(v);
  return `$${n.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}

function Kpi({ theme, label, value, color }: { theme: Theme; label: string; value: string; color: string }) { return <WorkStat label={label} value={value}/>; }

export function PaymentsBoard({ theme }: { theme: Theme }) {
  const [dashboard, setDashboard] = useState<PaymentsDashboard | null>(null);
  const [promises, setPromises] = useState<PromiseToPay[]>([]);
  const [promiseFilter, setPromiseFilter] = useState<PromiseStatus | null>(null);
  const [payoffs, setPayoffs] = useState<PayoffRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [runBusy, setRunBusy] = useState(false);
  const [runResult, setRunResult] = useState<string | null>(null);
  const [lookupId, setLookupId] = useState("");
  const [selected, setSelected] = useState<string | null>(null);

  const cardClass = tc(theme, "rounded-lg border border-black/20 bg-brand-charcoal p-3", "rounded-lg border border-zinc-200 bg-zinc-50 p-3");
  const textClass = tc(theme, "bg-zinc-900 border-zinc-700 text-white placeholder:text-zinc-600", "bg-white border-zinc-300 text-black placeholder:text-zinc-400");

  function refresh() {
    setLoading(true);
    Promise.all([
      getPaymentsDashboard(),
      listPromisesToPay(undefined, promiseFilter || undefined),
      listPayoffRequests(undefined, "requested"),
    ])
      .then(([d, p, po]) => {
        setDashboard(d);
        setPromises(p.promises);
        setPayoffs(po.requests);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }

  useEffect(refresh, [promiseFilter]);

  async function handleRunDue() {
    setRunBusy(true);
    setRunResult(null);
    try {
      const res = await runDueAutoDrafts();
      setRunResult(`Processed ${res.processed_count} due draft(s).`);
      refresh();
    } catch (e) {
      setRunResult((e as Error).message);
    } finally {
      setRunBusy(false);
    }
  }

  async function handleFulfill(loanId: string, requestId: string) {
    try {
      await fulfillPayoffRequest(loanId, requestId);
      refresh();
    } catch {
      // surfaced implicitly via refresh not removing the item
    }
  }

  return (
    <div className={tc(theme, "flex-1 flex flex-col min-h-0 bg-brand-ink text-white overflow-y-auto", "flex-1 flex flex-col min-h-0 bg-white text-black overflow-y-auto")}>
      <div className={tc(theme, "grid grid-cols-4 gap-3 p-4 border-b border-zinc-800", "grid grid-cols-4 gap-3 p-4 border-b border-zinc-200")}>
        <Kpi theme={theme} label="Total Collected" value={money(dashboard?.total_collected)} color={RIBBON[0]} />
        <Kpi theme={theme} label="Approved / Declined" value={`${dashboard?.approved_payments ?? 0} / ${dashboard?.declined_payments ?? 0}`} color={RIBBON[1]} />
        <Kpi theme={theme} label="Active Auto Drafts" value={String(dashboard?.active_auto_drafts ?? 0)} color={RIBBON[2]} />
        <Kpi theme={theme} label="Pending Payoff Requests" value={String(dashboard?.pending_payoff_requests ?? 0)} color={RIBBON[3]} />
      </div>

      {dashboard && (
        <div className="px-4 py-2 border-b border-zinc-800">
          <span className="text-xs px-2 py-1 rounded bg-amber-950/30 border border-amber-900/50 text-amber-300">
            {dashboard.disclaimer}
          </span>
        </div>
      )}

      <div className="px-4 py-3 border-b border-zinc-800 flex items-center gap-2">
        <WorkField label="Record ID"><WorkInput
          value={lookupId}
          onChange={(e) => setLookupId(e.target.value)}
          placeholder="Loan id (e.g. FIN-00001)…"
          className={`rounded-md border px-2 py-1.5 text-xs ${textClass}`}
        /></WorkField>
        <WorkButton type="submit" variant="primary"
          disabled={!lookupId}
          onClick={() => setSelected(lookupId.trim().toUpperCase())}
          className="text-xs px-2.5 py-1.5 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50"
        >
          Open Loan
        </WorkButton>
        <div className="flex-1" />
        <WorkButton type="submit"
          disabled={runBusy}
          onClick={handleRunDue}
          className="text-xs px-2.5 py-1.5 rounded bg-zinc-800 text-zinc-300 hover:text-white transition disabled:opacity-50"
        >
          {runBusy ? "Running…" : "↻ Run Due Auto Drafts"}
        </WorkButton>
        {runResult && <span className="text-xs text-zinc-500">{runResult}</span>}
      </div>

      <div className="flex-1 p-4 grid grid-cols-2 gap-3 overflow-y-auto">
        <div className={cardClass}>
          <div className="flex items-center justify-between mb-2">
            <div className="text-xs font-brand uppercase tracking-wide text-zinc-500">Promises To Pay</div>
            <div className="flex items-center gap-1">
              {(["pending", "kept", "broken"] as const).map((s) => (
                <WorkButton type="submit"
                  key={s}
                  onClick={() => setPromiseFilter(promiseFilter === s ? null : s)}
                  className={`text-xs px-1.5 py-0.5 rounded ${promiseFilter === s ? "bg-brand-blue text-white" : "bg-zinc-800 text-zinc-400"}`}
                >
                  {s}
                </WorkButton>
              ))}
            </div>
          </div>
          <div className="space-y-1 max-h-96 overflow-y-auto">
            {loading ? (
              <div className="text-xs text-zinc-500">Loading…</div>
            ) : promises.length === 0 ? (
              <div className="text-xs text-zinc-500">No promises to pay{promiseFilter ? ` (${promiseFilter})` : ""}.</div>
            ) : (
              promises.map((p) => (
                <WorkButton type="submit" key={p.id} onClick={() => setSelected(p.loan_id)} className="w-full text-left flex items-center justify-between text-xs hover:text-brand-blue transition py-0.5">
                  <span>{p.loan_id} · {p.promise_date} · {money(p.amount)}</span>
                  <span className={`text-xs px-1.5 py-0.5 rounded ${p.status === "kept" ? "bg-green-950/40 text-green-300" : p.status === "broken" ? "bg-red-950/40 text-red-300" : "bg-zinc-800 text-zinc-400"}`}>{p.status}</span>
                </WorkButton>
              ))
            )}
          </div>
        </div>

        <div className={cardClass}>
          <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Pending Payoff Requests</div>
          <div className="space-y-1 max-h-96 overflow-y-auto">
            {loading ? (
              <div className="text-xs text-zinc-500">Loading…</div>
            ) : payoffs.length === 0 ? (
              <div className="text-xs text-zinc-500">No pending payoff requests.</div>
            ) : (
              payoffs.map((r) => (
                <div key={r.id} className="flex items-center justify-between text-xs py-0.5">
                  <WorkButton type="submit" onClick={() => setSelected(r.loan_id || "")} className="text-left hover:text-brand-blue transition">
                    {r.loan_id} · {r.requested_by} · {r.notes || "—"}
                  </WorkButton>
                  <WorkButton type="submit"
                    onClick={() => r.loan_id && handleFulfill(r.loan_id, r.id)}
                    className="text-xs px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-300 hover:text-white transition"
                  >
                    Fulfill
                  </WorkButton>
                </div>
              ))
            )}
          </div>
        </div>

        <div className={`${cardClass} col-span-2`}>
          <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">By Method</div>
          <div className="flex flex-wrap gap-3 text-xs">
            {dashboard && Object.keys(dashboard.by_method).length > 0 ? (
              Object.entries(dashboard.by_method).map(([m, count]) => (
                <div key={m}><span className="text-zinc-500">{m}</span>: {count}</div>
              ))
            ) : (
              <div className="text-zinc-500">No approved payments recorded yet.</div>
            )}
          </div>
        </div>
      </div>

      {selected && (
        <LoanDetailModal theme={theme} loanId={selected} onClose={() => setSelected(null)} onChanged={refresh} />
      )}
    </div>
  );
}
