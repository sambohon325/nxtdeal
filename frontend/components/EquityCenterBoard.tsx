"use client";
import { WorkButton, WorkInput , WorkStat} from "./WorkspaceUi";
import { WorkField } from "./WorkField";

// Sales + Finance (F&I) "Equity Center" board -- a staff-facing surface over
// core/equity_center.py's graph-native equity / trade-up opportunity engine.
// Three sections: overview KPIs (positive-equity / lease-maturing / upgrade-ready
// counts + total estimated dollar opportunity), a live opportunities list
// (customer + the plain reason they're a candidate), and a per-customer panel
// that looks up an estimated equity position, records a real upgrade offer, and
// pulls an AI upgrade-offer draft with an honest disabled/fallback path.
// Read/act through lib/equityCenter.ts -- same shape and styling vocabulary as
// OperationsCustomerJourneyBoard.tsx (RIBBON palette, theme-aware classes).
//
// EVERYTHING here is ESTIMATED -- there is no lender payoff API and no valuation
// vendor connected. The backend stamps every figure is_estimated with a real
// disclaimer; this board surfaces those disclaimers, never presenting a figure
// as a real payoff or a binding appraisal.
import { PRODUCT_ACCENT_COLORS } from "@/lib/productTheme";
import { useEffect, useState } from "react";
import {
  getEquityOverview,
  getOpportunities,
  getCustomerEquity,
  createOffer,
  generateUpgradeOffer,
  type EquityOverview,
  type EquityOpportunity,
  type EquityPosition,
  type UpgradeOffer,
} from "@/lib/equityCenter";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const RIBBON = PRODUCT_ACCENT_COLORS;

// Estimated-equity status -> a readable label + a ribbon-derived accent color.
const STATUS_LABEL: Record<string, string> = {
  positive: "Positive Equity",
  negative: "Negative Equity",
  near_even: "Near Even",
  unknown: "Unknown",
};

const STATUS_COLOR: Record<string, string> = {
  positive: RIBBON[1],
  negative: RIBBON[3],
  near_even: RIBBON[2],
  unknown: "#9CA3AF",
};

function statusLabel(status: string | null | undefined): string {
  if (!status) return "—";
  return STATUS_LABEL[status] ?? status;
}

function statusColor(status: string | null | undefined): string {
  if (!status) return "#9CA3AF";
  return STATUS_COLOR[status] ?? "#9CA3AF";
}

// Estimated USD, never presented as a real figure. null -> an em dash.
function usd(amount: number | null | undefined): string {
  if (amount === null || amount === undefined) return "—";
  try {
    return amount.toLocaleString(undefined, {
      style: "currency",
      currency: "USD",
      maximumFractionDigits: 0,
    });
  } catch {
    return `$${amount}`;
  }
}

function fmt(ts: string | null | undefined): string {
  if (!ts) return "—";
  try {
    return new Date(ts).toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  } catch {
    return ts;
  }
}

function Kpi({ theme, label, value, color }: { theme: Theme; label: string; value: string; color: string }) { return <WorkStat label={label} value={value}/>; }

function StatusBadge({ status }: { status: string | null | undefined }) {
  const color = statusColor(status);
  return (
    <span
      className="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-brand uppercase tracking-wide"
      style={{ background: `${color}22`, color }}
    >
      {statusLabel(status)}
    </span>
  );
}

// The estimate disclaimer, surfaced verbatim from the backend wherever a dollar
// figure is shown. Honest real-vs-estimated disclosure, never suppressed.
function EstimateNote({ text }: { text: string | null | undefined }) {
  if (!text) return null;
  return <div className="text-xs text-zinc-600 mt-2 italic leading-snug break-words">{text}</div>;
}

function UpgradeOfferCard({ theme, offer }: { theme: Theme; offer: UpgradeOffer }) {
  const tag = offer.ai_generated ? "" : offer.disabled ? "(disabled — fallback)" : "(fallback)";
  return (
    <div className={tc(theme, "rounded-md border border-zinc-700 bg-black/20 p-3", "rounded-md border border-zinc-300 bg-white p-3")}>
      <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1">
        🤖 AI Upgrade Offer {tag}
      </div>
      <div className="text-sm font-medium text-zinc-200">{offer.headline || "—"}</div>
      {offer.message && <div className="text-xs text-zinc-400 mt-1 break-words">{offer.message}</div>}
      {offer.suggested_next_step && (
        <div className="text-xs text-zinc-500 mt-2">
          <span className="font-brand uppercase tracking-wide text-zinc-600 mr-1">Next Step</span>
          {offer.suggested_next_step}
        </div>
      )}
      {offer.fallback_reason && (
        <div className="text-xs text-zinc-600 mt-2 italic break-words">Fallback reason: {offer.fallback_reason}</div>
      )}
    </div>
  );
}

export function EquityCenterBoard({ theme }: { theme: Theme }) {
  const [overview, setOverview] = useState<EquityOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [opportunities, setOpportunities] = useState<EquityOpportunity[]>([]);
  const [oppLoading, setOppLoading] = useState(true);
  const [oppError, setOppError] = useState<string | null>(null);

  // Per-customer lookup state -- distinct from the overview above.
  const [lookupId, setLookupId] = useState("");
  const [position, setPosition] = useState<EquityPosition | null>(null);
  const [positionLoading, setPositionLoading] = useState(false);
  const [positionError, setPositionError] = useState<string | null>(null);

  const [note, setNote] = useState("");
  const [offerBusy, setOfferBusy] = useState(false);
  const [offerNotice, setOfferNotice] = useState<string | null>(null);

  const [aiOffer, setAiOffer] = useState<UpgradeOffer | null>(null);
  const [aiBusy, setAiBusy] = useState(false);

  function refresh() {
    setLoading(true);
    setError(null);
    getEquityOverview()
      .then(setOverview)
      .catch((e) => setError(e instanceof Error ? e.message : "Unable to load the Equity Center overview."))
      .finally(() => setLoading(false));

    setOppLoading(true);
    setOppError(null);
    getOpportunities()
      .then(setOpportunities)
      .catch((e) => setOppError(e instanceof Error ? e.message : "Unable to load equity opportunities."))
      .finally(() => setOppLoading(false));
  }

  useEffect(refresh, []);

  function loadPosition(customerId: string) {
    const id = customerId.trim();
    if (!id) {
      setPositionError("Enter a customer id to look up.");
      return;
    }
    setPositionLoading(true);
    setPositionError(null);
    setOfferNotice(null);
    setAiOffer(null);
    getCustomerEquity(id)
      .then(setPosition)
      .catch((e) => {
        setPosition(null);
        setPositionError(e instanceof Error ? e.message : "Unable to load this customer's equity position.");
      })
      .finally(() => setPositionLoading(false));
  }

  async function handleRecordOffer() {
    if (!position) return;
    setOfferBusy(true);
    setPositionError(null);
    setOfferNotice(null);
    try {
      const recorded = await createOffer(position.customer_id, note);
      setOfferNotice(`Upgrade offer ${recorded.id} recorded ${fmt(recorded.created_at)}.`);
      setNote("");
    } catch (e) {
      setPositionError(e instanceof Error ? e.message : "Unable to record an upgrade offer.");
    } finally {
      setOfferBusy(false);
    }
  }

  async function handleGenerateOffer() {
    if (!position) return;
    setAiBusy(true);
    setPositionError(null);
    try {
      const result = await generateUpgradeOffer(position.customer_id);
      setAiOffer(result);
    } catch (e) {
      setPositionError(e instanceof Error ? e.message : "Unable to generate an AI upgrade offer.");
    } finally {
      setAiBusy(false);
    }
  }

  return (
    <div className={tc(theme, "flex-1 flex flex-col min-h-0 bg-brand-ink text-white overflow-y-auto", "flex-1 flex flex-col min-h-0 bg-white text-black overflow-y-auto")}>
      {/* Header */}
      <div className={tc(theme, "p-4 border-b border-zinc-800", "p-4 border-b border-zinc-200")}>
        <div className="flex items-center justify-between gap-2">
          <div className="text-sm font-brand uppercase tracking-wide text-zinc-400">💰 Equity Center</div>
          <WorkButton type="submit" onClick={refresh} className="text-xs px-2.5 py-1 rounded-full bg-zinc-200/10 text-zinc-400 hover:text-white">
            ↻ Refresh
          </WorkButton>
        </div>
        <div className="text-xs text-zinc-500 mt-1">Estimated equity mining, lease-maturity trade-up, and upgrade offers.</div>
      </div>

      {/* Overview KPIs */}
      <div className={tc(theme, "p-4 border-b border-zinc-800", "p-4 border-b border-zinc-200")}>
        {loading && <div className="text-sm text-zinc-500">Loading…</div>}
        {error && <div className="text-sm text-red-400">{error}</div>}
        {!loading && !error && (
          <>
            <div className="grid grid-cols-4 gap-3">
              <Kpi theme={theme} label="Positive Equity" value={String(overview?.positive_equity ?? 0)} color={RIBBON[1]} />
              <Kpi theme={theme} label="Lease Maturing Soon" value={String(overview?.lease_maturing_soon ?? 0)} color={RIBBON[2]} />
              <Kpi theme={theme} label="Upgrade Ready" value={String(overview?.upgrade_ready ?? 0)} color={RIBBON[3]} />
              <Kpi theme={theme} label="Est. Opportunity" value={usd(overview?.total_estimated_opportunity)} color={RIBBON[0]} />
            </div>
            <div className="flex flex-wrap gap-x-4 gap-y-1 mt-3 text-xs text-zinc-500">
              <span>
                <span className="font-brand uppercase tracking-wide text-zinc-600 mr-1">Customers</span>
                {overview?.total_customers ?? 0}
              </span>
              <span>
                <span className="font-brand uppercase tracking-wide text-zinc-600 mr-1">With Estimates</span>
                {overview?.customers_with_estimates ?? 0}
              </span>
              <span>
                <span className="font-brand uppercase tracking-wide text-zinc-600 mr-1">Horizon</span>
                {overview?.lease_maturity_horizon_days ?? 0} day(s)
              </span>
            </div>
            <EstimateNote text={overview?.disclaimer} />
          </>
        )}
      </div>

      {/* Opportunities list */}
      <div className={tc(theme, "p-4 border-b border-zinc-800 space-y-2", "p-4 border-b border-zinc-200 space-y-2")}>
        <div className="text-sm font-brand uppercase tracking-wide text-zinc-400">🎯 Upgrade Opportunities</div>
        {oppLoading && <div className="text-sm text-zinc-500">Loading…</div>}
        {oppError && <div className="text-sm text-red-400">{oppError}</div>}
        {!oppLoading && !oppError && opportunities.length === 0 && (
          <div className="text-xs text-zinc-500">No estimated upgrade opportunities right now.</div>
        )}
        {!oppLoading && !oppError && opportunities.length > 0 && (
          <div className="space-y-1.5">
            {opportunities.map((opp) => (
              <div
                key={opp.customer_id}
                className={tc(theme, "rounded-md border border-zinc-800 bg-brand-charcoal p-2.5", "rounded-md border border-zinc-200 bg-zinc-50 p-2.5")}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="min-w-0">
                    <div className="text-sm font-medium text-zinc-200 truncate">{opp.name ?? opp.customer_id}</div>
                    <div className="text-xs text-zinc-500">{opp.customer_id}</div>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    {opp.upgrade_ready && (
                      <span className="text-xs font-brand uppercase tracking-wide text-emerald-400">Upgrade Ready</span>
                    )}
                    <StatusBadge status={opp.status} />
                    <span className="text-sm font-semibold" style={{ color: statusColor(opp.status) }}>
                      {usd(opp.equity_amount)}
                    </span>
                  </div>
                </div>
                {opp.reason && <div className="text-xs text-zinc-400 mt-1 break-words">{opp.reason}</div>}
                <WorkButton type="submit"
                  onClick={() => {
                    setLookupId(opp.customer_id);
                    loadPosition(opp.customer_id);
                  }}
                  className="text-xs text-zinc-500 hover:text-white mt-1 underline underline-offset-2"
                >
                  Open in customer panel →
                </WorkButton>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Per-customer equity panel */}
      <div className={tc(theme, "p-4 space-y-3", "p-4 space-y-3")}>
        <div className="text-sm font-brand uppercase tracking-wide text-zinc-400">👤 Per-Customer Equity</div>

        <div className="flex items-center gap-2">
          <WorkField label="Record ID"><WorkInput
            value={lookupId}
            onChange={(e) => setLookupId(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") loadPosition(lookupId);
            }}
            placeholder="Customer id (e.g. CUST-00123)"
            className={tc(
              theme,
              "flex-1 text-xs rounded border border-zinc-700 bg-black/30 px-2 py-1.5 text-white",
              "flex-1 text-xs rounded border border-zinc-300 bg-white px-2 py-1.5 text-black"
            )}
          /></WorkField>
          <WorkButton type="submit"
            onClick={() => loadPosition(lookupId)}
            disabled={positionLoading}
            className="text-xs px-3 py-1.5 rounded-full bg-zinc-200 text-black font-medium disabled:opacity-50 whitespace-nowrap"
          >
            {positionLoading ? "Loading…" : "Look Up"}
          </WorkButton>
        </div>

        {positionError && <div className="text-sm text-red-400">{positionError}</div>}

        {position && (
          <div className={tc(theme, "rounded-lg border border-zinc-800 bg-brand-charcoal p-3 space-y-3", "rounded-lg border border-zinc-200 bg-zinc-50 p-3 space-y-3")}>
            <div className="flex items-center justify-between gap-2">
              <div className="min-w-0">
                <div className="text-sm font-medium text-zinc-200 truncate">{position.name ?? position.customer_id}</div>
                <div className="text-xs text-zinc-500">{position.customer_id}</div>
              </div>
              <StatusBadge status={position.status} />
            </div>

            {/* Estimated equity figures */}
            <div className="grid grid-cols-3 gap-2">
              <div className={tc(theme, "rounded-md border border-zinc-800 bg-black/20 px-3 py-2", "rounded-md border border-zinc-200 bg-white px-3 py-2")}>
                <div className="text-sm font-semibold text-zinc-200">{usd(position.estimated_value)}</div>
                <div className="text-xs font-brand uppercase tracking-wide text-zinc-500">Est. Value</div>
              </div>
              <div className={tc(theme, "rounded-md border border-zinc-800 bg-black/20 px-3 py-2", "rounded-md border border-zinc-200 bg-white px-3 py-2")}>
                <div className="text-sm font-semibold text-zinc-200">{usd(position.estimated_payoff)}</div>
                <div className="text-xs font-brand uppercase tracking-wide text-zinc-500">Est. Payoff</div>
              </div>
              <div className={tc(theme, "rounded-md border border-zinc-800 bg-black/20 px-3 py-2", "rounded-md border border-zinc-200 bg-white px-3 py-2")}>
                <div className="text-sm font-semibold" style={{ color: statusColor(position.status) }}>
                  {usd(position.equity_amount)}
                </div>
                <div className="text-xs font-brand uppercase tracking-wide text-zinc-500">Est. Equity</div>
              </div>
            </div>

            <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-zinc-500">
              <span>
                <span className="font-brand uppercase tracking-wide text-zinc-600 mr-1">Lease Matures</span>
                {position.lease_maturity_date ?? "—"}
              </span>
              {position.days_to_lease_maturity !== null && (
                <span>
                  <span className="font-brand uppercase tracking-wide text-zinc-600 mr-1">Days Out</span>
                  {position.days_to_lease_maturity}
                </span>
              )}
              {position.lease_maturing_soon && (
                <span className="text-amber-400 font-brand uppercase tracking-wide">Maturing Soon</span>
              )}
              {!position.has_estimate_inputs && (
                <span className="text-zinc-500 italic">No desk-entered estimate inputs on file.</span>
              )}
            </div>

            <EstimateNote text={position.disclaimer} />

            {/* Record an upgrade offer -- a real, persisted employee action */}
            <div className="space-y-2 pt-1">
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500">Record Upgrade Offer</div>
              <div className="flex items-center gap-2">
                <WorkField label="Optional note"><WorkInput
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  placeholder="Optional note"
                  className={tc(
                    theme,
                    "flex-1 text-xs rounded border border-zinc-700 bg-black/30 px-2 py-1.5 text-white",
                    "flex-1 text-xs rounded border border-zinc-300 bg-white px-2 py-1.5 text-black"
                  )}
                /></WorkField>
                <WorkButton type="submit"
                  onClick={handleRecordOffer}
                  disabled={offerBusy}
                  className="text-xs px-3 py-1.5 rounded-full bg-zinc-200 text-black font-medium disabled:opacity-50 whitespace-nowrap"
                >
                  {offerBusy ? "…" : "Record Offer"}
                </WorkButton>
                <WorkButton type="submit"
                  onClick={handleGenerateOffer}
                  disabled={aiBusy}
                  className="text-xs px-3 py-1.5 rounded-full bg-zinc-200/10 text-zinc-400 hover:text-white disabled:opacity-50 whitespace-nowrap"
                >
                  {aiBusy ? "Generating…" : "✨ Generate AI Upgrade Offer"}
                </WorkButton>
              </div>
              {offerNotice && <div className="text-xs text-emerald-400">{offerNotice}</div>}
            </div>

            {aiOffer && <UpgradeOfferCard theme={theme} offer={aiOffer} />}
          </div>
        )}
      </div>
    </div>
  );
}
