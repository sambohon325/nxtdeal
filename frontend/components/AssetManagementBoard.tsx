"use client";
import { WorkInput, WorkButton , WorkStat, WorkOverlay} from "./WorkspaceUi";
import { WorkField } from "./WorkField";

// Finance's "Assets" item -- the sixth slice of Sam's "Retail Automotive Lending
// Platform" expansion (2026-07-17): Collateral / Asset Management. A KPI strip off
// the real portfolio-wide aggregate (book value, SIMULATED market value, average
// LTV, missing-title/lapsed-insurance/active-lien counts), a loan-id lookup, and a
// detail modal covering real Title status, real Lien tracking (release gated on the
// loan being paid off), real dealer-entered Insurance tracking, and a real
// Collateral Valuation & LTV blending real + SIMULATED inputs.
import { PRODUCT_ACCENT_COLORS } from "@/lib/productTheme";
import { useEffect, useState } from "react";
import {
  getAssetPortfolioDashboard,
  getAssetSummary,
  updateLienholder,
  releaseLien,
  updateInsurance,
  type AssetPortfolioDashboard,
  type AssetSummary,
} from "@/lib/assetManagement";
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

export function AssetManagementBoard({ theme }: { theme: Theme }) {
  const [dashboard, setDashboard] = useState<AssetPortfolioDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [lookupId, setLookupId] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [fullLoanId, setFullLoanId] = useState<string | null>(null);

  const textClass = tc(theme, "bg-zinc-900 border-zinc-700 text-white placeholder:text-zinc-600", "bg-white border-zinc-300 text-black placeholder:text-zinc-400");
  const cardClass = tc(theme, "rounded-lg border border-black/20 bg-brand-charcoal p-3", "rounded-lg border border-zinc-200 bg-zinc-50 p-3");

  function refresh() {
    setLoading(true);
    getAssetPortfolioDashboard()
      .then(setDashboard)
      .catch(() => {})
      .finally(() => setLoading(false));
  }

  useEffect(refresh, []);

  return (
    <div className={tc(theme, "flex-1 flex flex-col min-h-0 bg-brand-ink text-white overflow-y-auto", "flex-1 flex flex-col min-h-0 bg-white text-black overflow-y-auto")}>
      <div className={tc(theme, "grid grid-cols-4 gap-3 p-4 border-b border-zinc-800", "grid grid-cols-4 gap-3 p-4 border-b border-zinc-200")}>
        <Kpi theme={theme} label="Total Book Value" value={money(dashboard?.total_book_value)} color={RIBBON[0]} />
        <Kpi theme={theme} label="Avg Loan-to-Value" value={dashboard?.average_loan_to_value_pct != null ? `${dashboard.average_loan_to_value_pct}%` : "—"} color={RIBBON[1]} />
        <Kpi theme={theme} label="Missing Title / Lapsed Insurance" value={`${dashboard?.missing_title_count ?? 0} / ${dashboard?.lapsed_insurance_count ?? 0}`} color={RIBBON[2]} />
        <Kpi theme={theme} label="Active Liens" value={String(dashboard?.active_lien_count ?? 0)} color={RIBBON[3]} />
      </div>

      <div className="px-4 py-2 border-b border-zinc-800">
        <span className="text-xs px-2 py-1 rounded bg-amber-950/30 border border-amber-900/50 text-amber-300">
          {dashboard?.note}
        </span>
      </div>

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
          Open Assets
        </WorkButton>
      </div>

      <div className="flex-1 p-4 overflow-y-auto">
        <div className={`${cardClass} grid grid-cols-3 gap-4`}>
          <div>
            <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1">Total Market Value</div>
            <div className="text-lg font-semibold">{money(dashboard?.total_market_value)}</div>
            <div className="text-xs text-amber-400">Simulated</div>
          </div>
          <div>
            <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1">Total Outstanding Balance</div>
            <div className="text-lg font-semibold">{money(dashboard?.total_outstanding_balance)}</div>
          </div>
          <div>
            <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1">No Insurance On File</div>
            <div className="text-lg font-semibold">{dashboard?.no_insurance_on_file_count ?? 0} / {dashboard?.total_loans ?? 0}</div>
          </div>
        </div>
      </div>

      {selected && (
        <AssetDetailModal
          theme={theme}
          loanId={selected}
          onClose={() => setSelected(null)}
          onChanged={refresh}
          onViewFullLoan={(id) => setFullLoanId(id)}
        />
      )}

      {fullLoanId && (
        <LoanDetailModal theme={theme} loanId={fullLoanId} onClose={() => setFullLoanId(null)} onChanged={refresh} />
      )}
    </div>
  );
}

function AssetDetailModal({
  theme,
  loanId,
  onClose,
  onChanged,
  onViewFullLoan,
}: {
  theme: Theme;
  loanId: string;
  onClose: () => void;
  onChanged: () => void;
  onViewFullLoan: (id: string) => void;
}) {
  const [summary, setSummary] = useState<AssetSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const [lienholderName, setLienholderName] = useState("");
  const [releaseReason, setReleaseReason] = useState("");
  const [carrier, setCarrier] = useState("");
  const [policyNumber, setPolicyNumber] = useState("");
  const [expirationDate, setExpirationDate] = useState("");
  const [lossPayeeConfirmed, setLossPayeeConfirmed] = useState(false);

  const cardClass = tc(theme, "rounded-lg border border-zinc-800 bg-zinc-950 p-3", "rounded-lg border border-zinc-200 bg-zinc-50 p-3");
  const textClass = tc(theme, "bg-zinc-900 border-zinc-700 text-white placeholder:text-zinc-600", "bg-white border-zinc-300 text-black placeholder:text-zinc-400");

  function load() {
    setLoading(true);
    setError(null);
    getAssetSummary(loanId)
      .then((s) => {
        setSummary(s);
        setLienholderName(s.lien.lienholder_name);
        if (s.insurance.on_file) {
          setCarrier(s.insurance.carrier || "");
          setPolicyNumber(s.insurance.policy_number || "");
          setExpirationDate(s.insurance.expiration_date || "");
          setLossPayeeConfirmed(s.insurance.loss_payee_confirmed || false);
        }
      })
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }

  useEffect(load, [loanId]);

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
      <div className={tc(theme, "w-full max-w-3xl max-h-[85vh] overflow-y-auto rounded-lg border border-zinc-800 bg-brand-ink text-white p-5", "w-full max-w-3xl max-h-[85vh] overflow-y-auto rounded-lg border border-zinc-200 bg-white text-black p-5")}>
        <div className="flex items-center justify-between mb-3">
          <div className="text-sm font-semibold">Collateral Assets — {loanId}</div>
          <div className="flex items-center gap-2">
            <WorkButton type="submit" onClick={() => onViewFullLoan(loanId)} className="text-xs px-2 py-1 rounded bg-zinc-800 text-zinc-300 hover:text-white transition">
              View Full Loan →
            </WorkButton>
            <WorkButton type="submit" onClick={onClose} className="text-xs px-2 py-1 rounded bg-zinc-800 text-zinc-300 hover:text-white transition">Close</WorkButton>
          </div>
        </div>

        {error && <div className="text-xs text-red-400 mb-2">{error}</div>}
        {loading ? (
          <div className="text-xs text-zinc-500">Loading…</div>
        ) : !summary ? (
          <div className="text-xs text-zinc-500">Unable to load asset summary.</div>
        ) : (
          <div className="space-y-3">
            <div className={cardClass}>
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1">Title Status</div>
              <div className={`text-sm font-semibold ${summary.title.is_complete ? "text-green-400" : "text-red-400"}`}>
                {summary.title.is_complete ? "On File" : `Missing: ${summary.title.missing_types.join(", ")}`}
              </div>
            </div>

            <div className={cardClass}>
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Collateral Valuation</div>
              <div className="grid grid-cols-4 gap-3 text-xs">
                <div><span className="text-zinc-500">Book Value</span><div className="font-semibold">{money(summary.valuation.book_value)}</div></div>
                <div><span className="text-zinc-500">Market Value <span className="text-amber-400">(Sim)</span></span><div className="font-semibold">{money(summary.valuation.market_value)}</div></div>
                <div><span className="text-zinc-500">Balance</span><div className="font-semibold">{money(summary.valuation.current_balance)}</div></div>
                <div><span className="text-zinc-500">LTV</span><div className="font-semibold">{summary.valuation.loan_to_value_pct != null ? `${summary.valuation.loan_to_value_pct}%` : "—"}</div></div>
              </div>
              {summary.valuation.vin_match && summary.valuation.vin_match.checked && (
                <div className="mt-2 pt-2 border-t border-zinc-800 text-xs">
                  <span className="text-zinc-500">VIN Match Check</span>
                  {summary.valuation.vin_match.valid_format ? (
                    summary.valuation.vin_match.mismatches.length > 0 ? (
                      <div className="text-amber-400 mt-0.5">
                        ⚠ {summary.valuation.vin_match.mismatches.map((m) => `${m.field}: stored "${m.stored}" vs. decoded "${m.decoded}"`).join("; ")}
                      </div>
                    ) : summary.valuation.vin_match.compared_something ? (
                      <div className="text-green-400 mt-0.5">✅ VIN matches on-file Year/Make</div>
                    ) : (
                      <div className="text-zinc-500 mt-0.5">{summary.valuation.vin_match.note}</div>
                    )
                  ) : (
                    <div className="text-zinc-500 mt-0.5">{summary.valuation.vin_match.format_error}</div>
                  )}
                </div>
              )}
            </div>

            <div className={cardClass}>
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Lien</div>
              <div className="flex items-center gap-2 mb-2">
                <span className={`text-xs px-1.5 py-0.5 rounded ${summary.lien.lien_status === "released" ? "bg-green-950/40 text-green-300" : "bg-zinc-800 text-zinc-400"}`}>
                  {summary.lien.lien_status}
                </span>
                <span className="text-xs">{summary.lien.lienholder_name}</span>
              </div>
              {summary.lien.lien_status === "active" && (
                <>
                  <div className="flex items-center gap-2 mb-2">
                    <WorkField label="Lienholder name"><WorkInput value={lienholderName} onChange={(e) => setLienholderName(e.target.value)} placeholder="Lienholder name…" className={`flex-1 rounded-md border px-2 py-1.5 text-xs ${textClass}`} /></WorkField>
                    <WorkButton type="submit" disabled={busy || !lienholderName.trim()} onClick={() => run(() => updateLienholder(loanId, lienholderName))} className="text-xs px-2.5 py-1.5 rounded bg-zinc-800 text-zinc-300 hover:text-white transition disabled:opacity-50">
                      Update Lienholder
                    </WorkButton>
                  </div>
                  <div className="flex items-center gap-2">
                    <WorkField label="Release reason"><WorkInput value={releaseReason} onChange={(e) => setReleaseReason(e.target.value)} placeholder="Release reason…" className={`flex-1 rounded-md border px-2 py-1.5 text-xs ${textClass}`} /></WorkField>
                    <WorkButton type="submit" disabled={busy} onClick={() => run(() => releaseLien(loanId, releaseReason))} className="text-xs px-2.5 py-1.5 rounded bg-green-800 text-white font-medium hover:opacity-90 transition disabled:opacity-50">
                      Release Lien
                    </WorkButton>
                  </div>
                  <div className="text-xs text-zinc-600 mt-1">Release is only allowed once the loan is fully paid off.</div>
                </>
              )}
            </div>

            <div className={cardClass}>
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Insurance</div>
              {summary.insurance.on_file && (
                <div className="flex items-center gap-2 mb-2">
                  <span className={`text-xs px-1.5 py-0.5 rounded ${summary.insurance.is_lapsed ? "bg-red-950/40 text-red-300" : "bg-green-950/40 text-green-300"}`}>
                    {summary.insurance.is_lapsed ? "lapsed" : "current"}
                  </span>
                  <span className="text-xs">{summary.insurance.carrier} · {summary.insurance.policy_number} · exp {summary.insurance.expiration_date}</span>
                </div>
              )}
              <div className="grid grid-cols-2 gap-2 mb-2">
                <WorkField label="Carrier"><WorkInput value={carrier} onChange={(e) => setCarrier(e.target.value)} placeholder="Carrier…" className={`rounded-md border px-2 py-1.5 text-xs ${textClass}`} /></WorkField>
                <WorkField label="Policy number"><WorkInput value={policyNumber} onChange={(e) => setPolicyNumber(e.target.value)} placeholder="Policy number…" className={`rounded-md border px-2 py-1.5 text-xs ${textClass}`} /></WorkField>
                <WorkField label="Expiration Date"><WorkInput type="date" value={expirationDate} onChange={(e) => setExpirationDate(e.target.value)} className={`rounded-md border px-2 py-1.5 text-xs ${textClass}`} /></WorkField>
                <label className="flex items-center gap-1 text-xs text-zinc-400">
                  <WorkInput type="checkbox" checked={lossPayeeConfirmed} onChange={(e) => setLossPayeeConfirmed(e.target.checked)} />
                  Loss payee confirmed
                </label>
              </div>
              <WorkButton type="submit" variant="primary"
                disabled={busy || !carrier.trim() || !policyNumber.trim() || !expirationDate}
                onClick={() => run(() => updateInsurance(loanId, carrier, policyNumber, expirationDate, lossPayeeConfirmed))}
                className="text-xs px-2.5 py-1.5 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50"
              >
                Save Insurance
              </WorkButton>
            </div>
          </div>
        )}
      </div>
    </WorkOverlay>
  );
}
