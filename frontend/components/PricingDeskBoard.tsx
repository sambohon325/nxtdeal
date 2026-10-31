"use client";
import {RecordTable} from "./RecordTable";
import { WorkButton, WorkInput , WorkStat, WorkOverlay} from "./WorkspaceUi";
import { WorkField } from "./WorkField";

// Inventory department's "Pricing" item -- the pricing desk (Inventory
// rebuild, third slice). A real, ranked worklist (worst real margin first)
// with SIMULATED market pricing/competitor comps/age-based adjustment
// blended into a real recommendation, floored at a real 3% margin over
// cost. Applying a recommendation is a real, bidirectional Vehicle.Price
// mutation -- every simulated figure carries its own visible "Simulated"
// badge + disclaimer, never presented as real.
import { PRODUCT_ACCENT_COLORS } from "@/lib/productTheme";
import { useEffect, useState } from "react";
import {
  getPricingQueue,
  getPricingView,
  applyPriceRecommendation,
  type PricingQueue,
  type PricingView,
  type PricePosition,
} from "@/lib/pricingDesk";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const RIBBON = PRODUCT_ACCENT_COLORS;

const POSITION_TONE: Record<PricePosition, string> = {
  below_market: "bg-blue-950/40 text-blue-300",
  at_market: "bg-green-950/40 text-green-300",
  above_market: "bg-amber-950/40 text-amber-300",
};

const POSITION_LABEL: Record<PricePosition, string> = {
  below_market: "Below Market", at_market: "At Market", above_market: "Above Market",
};

function money(v: number | string | null | undefined): string {
  if (v === null || v === undefined || v === "") return "—";
  const n = typeof v === "string" ? parseFloat(v) : v;
  if (Number.isNaN(n)) return String(v);
  return `$${n.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

function pct(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return `${(v * 100).toFixed(1)}%`;
}

function Kpi({ theme, label, value, color }: { theme: Theme; label: string; value: string; color: string }) { return <WorkStat label={label} value={value}/>; }

function SimulatedBadge({ disclaimer }: { disclaimer: string }) {
  const [open, setOpen] = useState(false);
  return (
    <span className="relative inline-block">
      <WorkButton type="submit"
        onClick={() => setOpen((o) => !o)}
        className="text-xs px-1.5 py-0.5 rounded bg-amber-950/40 text-amber-300 font-brand uppercase tracking-wide cursor-help"
        title={disclaimer}
      >
        Simulated
      </WorkButton>
      {open && (
        <div className="absolute z-10 top-full left-0 mt-1 w-64 text-xs leading-snug p-2 rounded-lg bg-zinc-950 border border-amber-900/50 text-amber-200 shadow-xl">
          {disclaimer}
        </div>
      )}
    </span>
  );
}

function VehicleDetailModal({ theme, vehicleId, onClose, onChanged }: { theme: Theme; vehicleId: string; onClose: () => void; onChanged: () => void }) {
  const [data, setData] = useState<PricingView | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [newPrice, setNewPrice] = useState("");
  const [reason, setReason] = useState("");

  const cardClass = tc(theme, "rounded-lg border border-black/20 bg-brand-charcoal p-3", "rounded-lg border border-zinc-200 bg-zinc-50 p-3");
  const textClass = tc(theme, "bg-zinc-900 border-zinc-700 text-white placeholder:text-zinc-600", "bg-white border-zinc-300 text-black placeholder:text-zinc-400");

  function refresh() {
    setLoading(true);
    setError(null);
    getPricingView(vehicleId)
      .then((v) => {
        setData(v);
        setNewPrice(v.recommendation.recommended_price ? String(v.recommendation.recommended_price) : "");
      })
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }

  useEffect(refresh, [vehicleId]);

  async function handleApply() {
    if (!newPrice) return;
    setBusy(true);
    setError(null);
    try {
      await applyPriceRecommendation(vehicleId, parseFloat(newPrice), reason);
      refresh();
      onChanged();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (loading || !data) {
    return (
      <WorkOverlay className="work-inventory-detail">
        <div onClick={(e) => e.stopPropagation()} className={tc(theme, "rounded-xl border border-black/20 bg-brand-ink text-white p-5", "rounded-xl border border-zinc-200 bg-white text-black p-5")}>
          {loading ? <div className="text-sm text-zinc-500" role="status">Loading…</div> : <div role="alert"><p>{error || "Unable to load this record."}</p><WorkButton type="submit" onClick={refresh}>Try again</WorkButton></div>}
          <WorkButton type="submit" onClick={onClose}>Back to pricing</WorkButton>
        </div>
      </WorkOverlay>
    );
  }

  const { vehicle, market_pricing, competitor_comparisons, age_based_adjustment, recommendation } = data;

  return (
    <WorkOverlay className="work-inventory-detail">
      <div onClick={(e) => e.stopPropagation()} className={tc(theme, "w-full rounded-xl border border-black/20 bg-brand-ink text-white p-5 space-y-3", "w-full rounded-xl border border-zinc-200 bg-white text-black p-5 space-y-3")}>
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="text-sm font-brand uppercase tracking-wide">
              {vehicle.year} {vehicle.make} {vehicle.model}
            </div>
            <div className="text-xs text-zinc-500 mt-0.5">
              {vehicle.vehicle_id} · VIN {vehicle.vin || "—"} · Stock #{vehicle.stock_number || "—"} · Current {money(vehicle.price)} · Margin {vehicle.margin_pct !== null ? `${vehicle.margin_pct}%` : "—"}
            </div>
          </div>
          <WorkButton type="submit" onClick={onClose} className="text-xs text-zinc-500 hover:text-white transition">Back to pricing</WorkButton>
        </div>

        {error && <div className="text-xs px-3 py-2 rounded-lg bg-red-500/15 border border-red-500/40 text-red-300">{error}</div>}

        <div className={cardClass}>
          <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2 flex items-center gap-2">
            Market Pricing <SimulatedBadge disclaimer={market_pricing.disclaimer} />
          </div>
          <div className="grid grid-cols-3 gap-2 text-xs">
            <div><span className="text-zinc-500">Market Avg</span><div>{money(market_pricing.market_avg_price)}</div></div>
            <div>
              <span className="text-zinc-500">Position</span>
              <div>
                {market_pricing.price_position && (
                  <span className={`text-xs px-1.5 py-0.5 rounded ${POSITION_TONE[market_pricing.price_position]}`}>
                    {POSITION_LABEL[market_pricing.price_position]}
                  </span>
                )}
              </div>
            </div>
            <div><span className="text-zinc-500">Market Days Supply</span><div>{market_pricing.market_days_supply}</div></div>
          </div>
        </div>

        <div className={cardClass}>
          <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2 flex items-center gap-2">
            Competitor Comparisons <SimulatedBadge disclaimer={competitor_comparisons.disclaimer} />
          </div>
          <div className="space-y-1">
            {competitor_comparisons.comparisons.map((c, i) => (
              <div key={i} className="flex items-center justify-between text-xs">
                <span>{c.dealer_name} · {c.distance_miles} mi</span>
                <span>{money(c.price)} · {c.mileage.toLocaleString()} mi</span>
              </div>
            ))}
          </div>
        </div>

        <div className={cardClass}>
          <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2 flex items-center gap-2">
            Age-Based Adjustment <SimulatedBadge disclaimer={age_based_adjustment.disclaimer} />
          </div>
          <div className="grid grid-cols-3 gap-2 text-xs">
            <div><span className="text-zinc-500">Est. Listing Age</span><div>{age_based_adjustment.estimated_listing_age_days} days ({age_based_adjustment.age_band})</div></div>
            <div><span className="text-zinc-500">Suggested Adj.</span><div>{pct(age_based_adjustment.suggested_adjustment_pct)}</div></div>
            <div><span className="text-zinc-500">Suggested Price</span><div>{money(age_based_adjustment.suggested_price)}</div></div>
          </div>
        </div>

        <div className={cardClass}>
          <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2 flex items-center gap-2">
            Recommendation <SimulatedBadge disclaimer={recommendation.disclaimer} />
          </div>
          <div className="text-lg font-semibold mb-1">{money(recommendation.recommended_price)}</div>
          {recommendation.margin_floor_applied && (
            <div className="text-xs text-amber-400 mb-2">Floored at a real 3% margin over cost ({money(recommendation.margin_floor)})</div>
          )}
          <div className="flex items-center gap-1.5">
            <WorkField label="New price ($)"><WorkInput value={newPrice} onChange={(e) => setNewPrice(e.target.value)} type="number" placeholder="New price ($)" className={`flex-1 rounded-md border px-2 py-1.5 text-xs ${textClass}`} /></WorkField>
          </div>
          <WorkField label="Reason (optional)"><WorkInput value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Reason (optional)…" className={`w-full rounded-md border px-2 py-1.5 text-xs my-2 ${textClass}`} /></WorkField>
          <WorkButton type="submit" variant="primary" disabled={busy || !newPrice} onClick={handleApply} className="text-xs px-2.5 py-1.5 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50">
            {busy ? "Applying…" : "Apply Price"}
          </WorkButton>
        </div>
      </div>
    </WorkOverlay>
  );
}

export function PricingDeskBoard({ theme }: { theme: Theme }) {
  const [queue, setQueue] = useState<PricingQueue | null>(null);
  const [queueError,setQueueError]=useState("");
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<string | null>(null);

  function refresh() {
    setLoading(true);
    getPricingQueue(200)
      .then(data=>{setQueue(data);setQueueError("");})
      .catch(()=>setQueueError("Pricing could not be loaded. Try again."))
      .finally(() => setLoading(false));
  }

  useEffect(refresh, []);

  const zeroPriceCount = queue?.vehicles.filter((v) => !v.price || v.price <= 0).length || 0;
  const belowMarketCount = queue?.vehicles.filter((v) => v.recommendation?.recommended_price && v.price && v.recommendation.recommended_price > v.price).length || 0;
  const flooredCount = queue?.vehicles.filter((v) => v.recommendation?.margin_floor_applied).length || 0;

  return (
    <div className={tc(theme, "work-inventory-board", "work-inventory-board")}>
      <div hidden={!!selected}>
      <div className={tc(theme, "work-inventory-stats", "work-inventory-stats")}>
        <Kpi theme={theme} label="In Pricing Queue" value={String(queue?.count || 0)} color={RIBBON[0]} />
        <Kpi theme={theme} label="Missing Price" value={String(zeroPriceCount)} color={RIBBON[1]} />
        <Kpi theme={theme} label="Priced Below Market" value={String(belowMarketCount)} color={RIBBON[2]} />
        <Kpi theme={theme} label="Margin Floor Hit" value={String(flooredCount)} color={RIBBON[3]} />
      </div>

      <div className="px-4 py-2 border-b border-zinc-800">
        <span className="text-xs px-2 py-1 rounded bg-amber-950/30 border border-amber-900/50 text-amber-300">
          Market Pricing, Competitor Comparisons, and Age-Based Adjustments below are SIMULATED -- no real market/competitor data feed exists yet. Click any "Simulated" badge for details.
        </span>
      </div>

      <div className="flex-1 p-4">
        {queueError ? <p role="alert">{queueError} <WorkButton onClick={refresh}>Retry</WorkButton></p> : loading || !queue ? (
          <div className="text-sm text-zinc-500" role="status">Loading…</div>
        ) : (
          <RecordTable label="Pricing vehicles"><thead><tr><th>Vehicle</th><th>Current price</th><th>Simulated recommendation</th><th>Margin</th><th>Next step</th></tr></thead><tbody>{queue.vehicles.map(v=><tr key={v.vehicle_id}><td><strong>{v.year} {v.make} {v.model}</strong><span className="work-record-meta">{v.vehicle_id}</span></td><td>{money(v.price)}</td><td>{money(v.recommendation?.recommended_price)}{v.recommendation?.margin_floor_applied&&<span className="work-record-meta">Margin floor applied</span>}</td><td>{v.margin_pct!==null?`${v.margin_pct}%`:"No margin data"}</td><td><WorkButton onClick={()=>setSelected(v.vehicle_id)}>Review pricing</WorkButton></td></tr>)}</tbody></RecordTable>
        )}
      </div>

      </div>
      {selected && (
        <VehicleDetailModal theme={theme} vehicleId={selected} onClose={() => setSelected(null)} onChanged={refresh} />
      )}
    </div>
  );
}
