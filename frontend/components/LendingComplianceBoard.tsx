"use client";
import { WorkButton, WorkInput , WorkStat, WorkOverlay} from "./WorkspaceUi";
import { WorkField } from "./WorkField";

// Finance's "Compliance" item, extended (2026-07-17, session 112 follow-up) -- the
// seventh slice of Sam's "Retail Automotive Lending Platform" expansion, and the last
// explicitly-named item on his original 13-item Finance menu spec. Real OFAC/SDN
// screening (a human-recorded, checkable precondition wired as a blocking deal_fund
// rule -- no live SDN feed exists in this sandbox) and real IRS Form 8300 cash-payment
// tracking with an honestly-computed pending/overdue obligation status off the real
// 15-day IRS filing window. Also surfaces the pre-existing general compliance rule
// catalog / open exceptions / deal jacket audits (via the generic /menu/data call)
// so this is one real Compliance home screen, not two disconnected surfaces.
import { PRODUCT_ACCENT_COLORS } from "@/lib/productTheme";
import { useEffect, useState } from "react";
import {
  getLendingComplianceDashboard,
  getOfacStatus,
  recordOfacScreening,
  recordCashPayment,
  getForm8300Status,
  fileForm8300,
  getFinanceComplianceOverview,
  type LendingComplianceDashboard,
  type OfacStatus,
  type Form8300Status,
  type FinanceComplianceOverview,
} from "@/lib/lendingCompliance";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const RIBBON = PRODUCT_ACCENT_COLORS;

function money(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return `$${v.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}

function Kpi({ theme, label, value, color }: { theme: Theme; label: string; value: string; color: string }) { return <WorkStat label={label} value={value}/>; }

function statusBadge(status: string) {
  const map: Record<string, string> = {
    cleared: "bg-green-950/40 text-green-300",
    filed: "bg-green-950/40 text-green-300",
    not_screened: "bg-zinc-800 text-zinc-400",
    none: "bg-zinc-800 text-zinc-400",
    pending: "bg-amber-950/30 text-amber-300",
    potential_match: "bg-red-950/40 text-red-300",
    overdue: "bg-red-950/40 text-red-300",
  };
  return `text-[10px] px-1.5 py-0.5 rounded ${map[status] || "bg-zinc-800 text-zinc-400"}`;
}

export function LendingComplianceBoard({ theme }: { theme: Theme }) {
  const [dashboard, setDashboard] = useState<LendingComplianceDashboard | null>(null);
  const [overview, setOverview] = useState<FinanceComplianceOverview | null>(null);
  const [showRules, setShowRules] = useState(false);
  const [lookupId, setLookupId] = useState("");
  const [selected, setSelected] = useState<string | null>(null);

  const cardClass = tc(theme, "rounded-lg border border-zinc-800 bg-zinc-950 p-3", "rounded-lg border border-zinc-200 bg-zinc-50 p-3");
  const textClass = tc(theme, "bg-zinc-900 border-zinc-700 text-white placeholder:text-zinc-600", "bg-white border-zinc-300 text-black placeholder:text-zinc-400");

  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  function refresh() {
    setLoading(true);
    setLoadError(null);
    Promise.all([getLendingComplianceDashboard(), getFinanceComplianceOverview()])
      .then(([nextDashboard, nextOverview]) => { setDashboard(nextDashboard); setOverview(nextOverview); })
      .catch((error: unknown) => setLoadError(error instanceof Error ? error.message : "Unable to load compliance records."))
      .finally(() => setLoading(false));
  }

  useEffect(refresh, []);

  if (!dashboard) {
    return <div className="p-4 text-sm">{loading ? <p role="status">Loading finance compliance…</p> : <div role="alert"><p>Compliance status is unavailable. No clearance or counts can be confirmed.</p><p>{loadError}</p><WorkButton type="submit" onClick={refresh} className="min-h-11 underline">Retry compliance</WorkButton></div>}</div>;
  }

  const exceptionsBlocked = overview?.compliance_exceptions && "error" in (overview.compliance_exceptions as { error?: string });

  return (
    <div className={tc(theme, "flex-1 flex flex-col min-h-0 bg-brand-ink text-white overflow-y-auto", "flex-1 flex flex-col min-h-0 bg-white text-black overflow-y-auto")}>
      {loadError && <div role="alert" className="p-4 text-sm"><p>Refresh failed. Showing the last loaded records: {loadError}</p><WorkButton type="submit" disabled={loading} onClick={refresh} className="min-h-11 underline">Retry compliance</WorkButton></div>}
      <div className={tc(theme, "grid grid-cols-2 md:grid-cols-4 gap-3 p-4 border-b border-zinc-800", "grid grid-cols-2 md:grid-cols-4 gap-3 p-4 border-b border-zinc-200")}>
        <Kpi theme={theme} label="OFAC Unscreened / Potential Match" value={String(dashboard?.ofac.unscreened_or_potential_match_count ?? 0)} color={RIBBON[0]} />
        <Kpi theme={theme} label="Form 8300 Overdue" value={String(dashboard?.form_8300.overdue_count ?? 0)} color={RIBBON[3]} />
        <Kpi theme={theme} label="Form 8300 Pending" value={String(dashboard?.form_8300.pending_count ?? 0)} color={RIBBON[2]} />
        <Kpi theme={theme} label="Form 8300 Filed" value={String(dashboard?.form_8300.filed_count ?? 0)} color={RIBBON[1]} />
      </div>

      <div className="px-4 py-2 border-b border-zinc-800">
        <span className="text-xs px-2 py-1 rounded bg-amber-950/30 border border-amber-900/50 text-amber-300">
          {dashboard?.note}
        </span>
      </div>

      <div className="px-4 py-3 border-b border-zinc-800 flex items-center gap-2">
        <WorkInput
          aria-label="Deal ID"
          value={lookupId}
          onChange={(e) => setLookupId(e.target.value)}
          placeholder="Deal id (e.g. DEAL-00001)…"
          className={`rounded-md border px-2 py-1.5 text-xs ${textClass}`}
        />
        <WorkButton type="submit" variant="primary"
          disabled={!lookupId}
          onClick={() => setSelected(lookupId.trim().toUpperCase())}
          className="text-xs px-2.5 py-1.5 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50"
        >
          Open Deal Compliance
        </WorkButton>
      </div>

      <div className="flex-1 p-4 overflow-y-auto space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <div className={cardClass}>
            <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">OFAC — Unscreened / Potential Match</div>
            {(dashboard?.ofac.deals ?? []).length === 0 ? (
              <div className="text-xs text-zinc-600">Nothing needs screening right now.</div>
            ) : (
              <div className="space-y-1 max-h-64 overflow-y-auto">
                {dashboard!.ofac.deals.map((d) => (
                  <WorkButton type="submit"
                    key={d.deal_id}
                    onClick={() => setSelected(d.deal_id)}
                    className="w-full flex items-center justify-between text-xs px-2 py-1.5 rounded hover:bg-zinc-800/60 transition text-left"
                  >
                    <span>{d.deal_id}</span>
                    <span className={statusBadge(d.status)}>{d.status.replace(/_/g, " ")}</span>
                  </WorkButton>
                ))}
              </div>
            )}
          </div>

          <div className={cardClass}>
            <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Form 8300 — Overdue / Pending</div>
            {[...(dashboard?.form_8300.overdue ?? []), ...(dashboard?.form_8300.pending ?? [])].length === 0 ? (
              <div className="text-xs text-zinc-600">No cash-reporting obligations right now.</div>
            ) : (
              <div className="space-y-1 max-h-64 overflow-y-auto">
                {[...(dashboard?.form_8300.overdue ?? []), ...(dashboard?.form_8300.pending ?? [])].map((f) => (
                  <WorkButton type="submit"
                    key={f.deal_id}
                    onClick={() => setSelected(f.deal_id)}
                    className="w-full flex items-center justify-between text-xs px-2 py-1.5 rounded hover:bg-zinc-800/60 transition text-left"
                  >
                    <span>{f.deal_id} · {money(f.total_cash_received)}</span>
                    <span className={statusBadge(f.status)}>
                      {f.status === "overdue" ? `${f.days_overdue}d overdue` : `${f.days_remaining}d left`}
                    </span>
                  </WorkButton>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div className={cardClass}>
            <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1">Deal Jacket Audits</div>
            <div className="text-sm font-semibold">{overview?.deal_jacket_audits?.count ?? 0} funded deal(s) missing a Deal Jacket</div>
          </div>
          <div className={cardClass}>
            <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1">Open Compliance Exceptions</div>
            {exceptionsBlocked ? (
              <div className="text-xs text-zinc-600">Admin/Operations only.</div>
            ) : (
              <div className="text-sm font-semibold">
                {(overview?.compliance_exceptions as { alerts?: unknown[] })?.alerts?.length ?? 0} open
              </div>
            )}
          </div>
        </div>

        <div className={cardClass}>
          <WorkButton type="submit" onClick={() => setShowRules((s) => !s)} className="text-xs font-brand uppercase tracking-wide text-zinc-500 flex items-center gap-1">
            {showRules ? "▾" : "▸"} Rule Catalog ({overview?.rule_catalog?.rules?.length ?? 0} real federal rules)
          </WorkButton>
          {showRules && (
            <div className="mt-2 space-y-1.5">
              {(overview?.rule_catalog?.rules ?? []).map((r) => (
                <div key={r.id} className="text-xs flex items-center justify-between border-b border-zinc-900 pb-1">
                  <span>{r.law} <span className="text-zinc-600">({r.citation})</span></span>
                  <span className="text-zinc-500">{r.category} · {r.severity}</span>
                </div>
              ))}
              <div className="text-xs text-zinc-600 pt-1">{overview?.rule_catalog?.notice}</div>
            </div>
          )}
        </div>
      </div>

      {selected && (
        <DealComplianceModal theme={theme} dealId={selected} onClose={() => setSelected(null)} onChanged={refresh} />
      )}
    </div>
  );
}

function DealComplianceModal({
  theme,
  dealId,
  onClose,
  onChanged,
}: {
  theme: Theme;
  dealId: string;
  onClose: () => void;
  onChanged: () => void;
}) {
  const [ofac, setOfac] = useState<OfacStatus | null>(null);
  const [form8300, setForm8300] = useState<Form8300Status | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const [notes, setNotes] = useState("");
  const [cashAmount, setCashAmount] = useState("");
  const [cashDate, setCashDate] = useState("");

  const cardClass = tc(theme, "rounded-lg border border-zinc-800 bg-zinc-950 p-3", "rounded-lg border border-zinc-200 bg-zinc-50 p-3");
  const textClass = tc(theme, "bg-zinc-900 border-zinc-700 text-white placeholder:text-zinc-600", "bg-white border-zinc-300 text-black placeholder:text-zinc-400");

  function load() {
    setLoading(true);
    setError(null);
    Promise.all([getOfacStatus(dealId), getForm8300Status(dealId)])
      .then(([o, f]) => {
        setOfac(o);
        setForm8300(f);
      })
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }

  useEffect(load, [dealId]);

  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      load();
      onChanged();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <WorkOverlay className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className={tc(theme, "w-full max-w-2xl max-h-[85vh] overflow-y-auto rounded-lg border border-zinc-800 bg-brand-ink text-white p-5", "w-full max-w-2xl max-h-[85vh] overflow-y-auto rounded-lg border border-zinc-200 bg-white text-black p-5")}>
        <div className="flex items-center justify-between mb-3">
          <div className="text-sm font-semibold">Lending Compliance — {dealId}</div>
          <WorkButton type="submit" onClick={onClose} className="text-xs px-2 py-1 rounded bg-zinc-800 text-zinc-300 hover:text-white transition">Close</WorkButton>
        </div>

        {error && <div className="text-xs text-red-400 mb-2">{error}</div>}
        {loading ? (
          <div className="text-xs text-zinc-500">Loading…</div>
        ) : (
          <div className="space-y-3">
            <div className={cardClass}>
              <div className="flex items-center justify-between mb-2">
                <div className="text-xs font-brand uppercase tracking-wide text-zinc-500">OFAC / SDN Screening</div>
                {ofac && <span className={statusBadge(ofac.status)}>{ofac.status.replace(/_/g, " ")}</span>}
              </div>
              {ofac?.screened_by && (
                <div className="text-xs text-zinc-500 mb-2">
                  Last screened by {ofac.screened_by} at {ofac.screened_at ? new Date(ofac.screened_at).toLocaleString() : "—"}
                  {ofac.notes ? ` — "${ofac.notes}"` : ""}
                </div>
              )}
              <div className="flex items-center gap-2">
                <WorkField label="Screening notes"><WorkInput value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Screening notes…" className={`flex-1 rounded-md border px-2 py-1.5 text-xs ${textClass}`} /></WorkField>
                <WorkButton type="submit" disabled={busy} onClick={() => run(() => recordOfacScreening(dealId, true, notes))} className="text-xs px-2.5 py-1.5 rounded bg-green-800 text-white font-medium hover:opacity-90 transition disabled:opacity-50">
                  Clear
                </WorkButton>
                <WorkButton type="submit" variant="danger" disabled={busy} onClick={() => run(() => recordOfacScreening(dealId, false, notes))} className="text-xs px-2.5 py-1.5 rounded bg-red-800 text-white font-medium hover:opacity-90 transition disabled:opacity-50">
                  Flag Match
                </WorkButton>
              </div>
              <div className="text-xs text-zinc-600 mt-1">A cleared screening is required before this deal can fund.</div>
            </div>

            <div className={cardClass}>
              <div className="flex items-center justify-between mb-2">
                <div className="text-xs font-brand uppercase tracking-wide text-zinc-500">IRS Form 8300 — Cash Reporting</div>
                {form8300 && <span className={statusBadge(form8300.status)}>{form8300.status}</span>}
              </div>
              <div className="text-xs mb-2">
                Total cash recorded: <span className="font-semibold">{money(form8300?.total_cash_received)}</span> / {money(form8300?.threshold)} threshold
                {form8300?.status === "overdue" && <span className="text-red-400"> — {form8300.days_overdue} day(s) overdue</span>}
                {form8300?.status === "pending" && <span className="text-amber-400"> — {form8300.days_remaining} day(s) remaining</span>}
              </div>
              <div className="grid grid-cols-3 gap-2 mb-2">
                <WorkField label="Amount"><WorkInput value={cashAmount} onChange={(e) => setCashAmount(e.target.value)} placeholder="Amount…" className={`rounded-md border px-2 py-1.5 text-xs ${textClass}`} /></WorkField>
                <WorkField label="Cash Date"><WorkInput type="date" value={cashDate} onChange={(e) => setCashDate(e.target.value)} className={`rounded-md border px-2 py-1.5 text-xs ${textClass}`} /></WorkField>
                <WorkButton type="submit"
                  disabled={busy || !cashAmount}
                  onClick={() => run(() => recordCashPayment(dealId, parseFloat(cashAmount), cashDate))}
                  className="text-xs px-2.5 py-1.5 rounded bg-zinc-800 text-zinc-300 hover:text-white transition disabled:opacity-50"
                >
                  Log Cash Payment
                </WorkButton>
              </div>
              <WorkButton type="submit" variant="primary"
                disabled={busy || !form8300?.obligation || form8300?.filed}
                onClick={() => run(() => fileForm8300(dealId))}
                className="text-xs px-2.5 py-1.5 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50"
              >
                File Form 8300
              </WorkButton>
              {form8300?.filing && (
                <div className="text-xs text-zinc-600 mt-1">
                  Filed by {form8300.filing.filed_by} on {form8300.filing.filing_date}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </WorkOverlay>
  );
}
