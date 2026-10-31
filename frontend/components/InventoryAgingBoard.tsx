"use client";
import { WorkButton, WorkInput , WorkStat, WorkOverlay} from "./WorkspaceUi";
import { WorkField } from "./WorkField";

// Operations' "Inventory" item -- Inventory Aging Management (session 106
// follow-up #4). Sam's spec: "price reduction / wholesale review / manager
// review / marketing campaign / auction assignment actions on aging bands."
// Backend: core/inventory_aging.py / _api.py. Distinct from Sales' own
// "Inventory" item (components/InventoryBoard.tsx) -- this is the pricing-desk
// action layer, not a sales-facing locator.

import { PRODUCT_ACCENT_COLORS } from "@/lib/productTheme";
import { useEffect, useState } from "react";
import {
  getAgingBoard,
  reduceVehiclePrice,
  requestWholesaleReview,
  requestManagerReview,
  requestAuctionAssignment,
  createMarketingTieIn,
  type AgingBoard,
  type AgingVehicleBrief,
  type PriceBand,
} from "@/lib/inventoryAging";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const RIBBON = PRODUCT_ACCENT_COLORS;

const BAND_LABELS: Record<PriceBand, string> = {
  under_15k: "Under $15k",
  "15k_25k": "$15k – $25k",
  "25k_40k": "$25k – $40k",
  "40k_plus": "$40k+",
};

const BAND_ORDER: PriceBand[] = ["under_15k", "15k_25k", "25k_40k", "40k_plus"];

function money(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return `$${v.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

function Kpi({ theme, label, value, color }: { theme: Theme; label: string; value: number; color: string }) { return <WorkStat label={label} value={value}/>; }

function VehicleActionsModal({
  theme,
  vehicle,
  onClose,
  onChanged,
}: {
  theme: Theme;
  vehicle: AgingVehicleBrief;
  onClose: () => void;
  onChanged: () => void;
}) {
  const [newPrice, setNewPrice] = useState(String(Math.max(vehicle.price - 500, 1)));
  const [reason, setReason] = useState("");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const textClass = tc(theme, "bg-zinc-900 border-zinc-700 text-white placeholder:text-zinc-600", "bg-white border-zinc-300 text-black placeholder:text-zinc-400");
  const cardClass = tc(theme, "rounded-lg border border-black/20 bg-brand-charcoal p-3", "rounded-lg border border-zinc-200 bg-zinc-50 p-3");

  async function run(fn: () => Promise<unknown>, successMsg: string) {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      await fn();
      setMessage(successMsg);
      onChanged();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <WorkOverlay className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div
        onClick={(e) => e.stopPropagation()}
        className={tc(theme, "w-full max-w-lg max-h-[90vh] overflow-y-auto rounded-xl border border-black/20 bg-brand-ink text-white p-5 space-y-3", "w-full max-w-lg max-h-[90vh] overflow-y-auto rounded-xl border border-zinc-200 bg-white text-black p-5 space-y-3")}
      >
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="text-sm font-brand uppercase tracking-wide">{vehicle.year} {vehicle.make} {vehicle.model}</div>
            <div className="text-xs text-zinc-500 mt-0.5">{vehicle.vin} · {vehicle.stock_number} · {BAND_LABELS[vehicle.price_band]}</div>
          </div>
          <WorkButton type="submit" onClick={onClose} className="text-xs text-zinc-500 hover:text-white transition">✕ Close</WorkButton>
        </div>

        {error && <div className="text-xs px-3 py-2 rounded-lg bg-red-500/15 border border-red-500/40 text-red-300">{error}</div>}
        {message && <div className="text-xs px-3 py-2 rounded-lg bg-green-500/15 border border-green-500/40 text-green-300">{message}</div>}

        <div className={cardClass}>
          <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Price Reduction</div>
          <div className="text-xs mb-2">Current price: <span className="font-medium">{money(vehicle.price)}</span> · Margin: {vehicle.margin_pct != null ? `${vehicle.margin_pct}%` : "—"}</div>
          <div className="flex items-center gap-1.5">
            <WorkField label="New price"><WorkInput value={newPrice} onChange={(e) => setNewPrice(e.target.value)} type="number" placeholder="New price" className={`w-32 rounded-md border px-2 py-1.5 text-xs ${textClass}`} /></WorkField>
            <WorkField label="Reason (optional)"><WorkInput value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Reason (optional)" className={`flex-1 rounded-md border px-2 py-1.5 text-xs ${textClass}`} /></WorkField>
            <WorkButton type="submit" variant="primary"
              disabled={busy}
              onClick={() => run(() => reduceVehiclePrice(vehicle.vehicle_id, parseFloat(newPrice), reason), "Price reduced.")}
              className="text-xs px-2.5 py-1.5 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50"
            >
              Reduce Price
            </WorkButton>
          </div>
          {vehicle.price_history_count > 0 && <div className="text-xs text-zinc-600 mt-1">{vehicle.price_history_count} prior price change(s) on file.</div>}
        </div>

        <div className={cardClass}>

          <WorkField label="Workflow Actions"><WorkInput value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Notes (optional, applies to all actions below)" className={`w-full rounded-md border px-2 py-1.5 text-xs mb-2 ${textClass}`} /></WorkField>
          <div className="flex flex-wrap gap-1.5">
            <WorkButton type="submit" disabled={busy} onClick={() => run(() => requestWholesaleReview(vehicle.vehicle_id, notes), "Wholesale review requested.")} className="text-xs px-2.5 py-1.5 rounded bg-zinc-700 text-white hover:opacity-90 transition disabled:opacity-50">Send to Wholesale Review</WorkButton>
            <WorkButton type="submit" disabled={busy} onClick={() => run(() => requestManagerReview(vehicle.vehicle_id, notes), "Manager review requested.")} className="text-xs px-2.5 py-1.5 rounded bg-amber-700 text-white hover:opacity-90 transition disabled:opacity-50">Escalate to Manager Review</WorkButton>
            <WorkButton type="submit" disabled={busy} onClick={() => run(() => requestAuctionAssignment(vehicle.vehicle_id, notes), "Auction assignment ticket created.")} className="text-xs px-2.5 py-1.5 rounded bg-zinc-700 text-white hover:opacity-90 transition disabled:opacity-50">Assign to Auction</WorkButton>
            <WorkButton type="submit" variant="primary" disabled={busy} onClick={() => run(() => createMarketingTieIn(vehicle.vehicle_id), "Draft marketing campaign created.")} className="text-xs px-2.5 py-1.5 rounded bg-brand-blue text-white hover:opacity-90 transition disabled:opacity-50">Create Marketing Campaign</WorkButton>
          </div>
          <div className="text-xs text-zinc-600 italic mt-2">
            Auction Assignment creates a coordination ticket only -- no auction-house integration exists in this system.
            Marketing Campaign creates a draft inventory_ads campaign (make/model-scoped) awaiting Marketing activation.
          </div>
        </div>
      </div>
    </WorkOverlay>
  );
}

export function InventoryAgingBoard({ theme }: { theme: Theme }) {
  const [board, setBoard] = useState<AgingBoard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<AgingVehicleBrief | null>(null);
  const [bandFilter, setBandFilter] = useState<PriceBand | "">("");

  function refresh() {
    setLoading(true);
    getAgingBoard()
      .then(setBoard)
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }

  useEffect(refresh, []);

  const bandsToShow = bandFilter ? [bandFilter] : BAND_ORDER;

  return (
    <div className={tc(theme, "work-inventory-board", "work-inventory-board")}>
      <div className={tc(theme, "work-inventory-stats", "work-inventory-stats")}>
        <Kpi theme={theme} label="Unsold Inventory" value={board?.unsold_count ?? 0} color={RIBBON[0]} />
        <Kpi theme={theme} label="Under $15k" value={board?.by_price_band.under_15k.length ?? 0} color={RIBBON[1]} />
        <Kpi theme={theme} label="$25k – $40k" value={board?.by_price_band["25k_40k"].length ?? 0} color={RIBBON[2]} />
        <Kpi theme={theme} label="$40k+" value={board?.by_price_band["40k_plus"].length ?? 0} color={RIBBON[3]} />
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {error && <div className="text-xs px-3 py-2 rounded-lg bg-red-500/15 border border-red-500/40 text-red-300">{error}</div>}
        {board?.note && <div className="text-xs text-zinc-600 italic">{board.note}</div>}

        <div className="flex flex-wrap gap-1.5">
          <WorkButton type="submit"  onClick={() => setBandFilter("")} className={`text-xs px-2.5 py-1 rounded ${!bandFilter ? "bg-brand-blue text-white" : "bg-zinc-800 text-zinc-300"}`}>All Bands</WorkButton>
          {BAND_ORDER.map((b) => (
            <WorkButton type="submit"  key={b} onClick={() => setBandFilter(b)} className={`text-xs px-2.5 py-1 rounded ${bandFilter === b ? "bg-brand-blue text-white" : "bg-zinc-800 text-zinc-300"}`}>{BAND_LABELS[b]}</WorkButton>
          ))}
        </div>

        {loading || !board ? (
          <div className="text-sm text-zinc-500">Loading…</div>
        ) : (
          bandsToShow.map((band) => (
            <div key={band} className={tc(theme, "rounded-lg border border-zinc-800 bg-brand-charcoal", "rounded-lg border border-zinc-200 bg-zinc-50")}>
              <div className="px-3 py-2 border-b border-zinc-800 flex items-center justify-between">
                <span className="text-xs font-brand uppercase tracking-wide">{BAND_LABELS[band]}</span>
                <span className="text-xs text-zinc-500">{board.by_price_band[band].length} vehicles</span>
              </div>
              <div className="p-2 grid grid-cols-2 md:grid-cols-3 gap-1.5">
                {board.by_price_band[band].length === 0 ? (
                  <div className="text-xs text-zinc-600 col-span-full py-2 text-center">None in this band.</div>
                ) : (
                  board.by_price_band[band].map((v) => (
                    <button
                      key={v.vehicle_id}
                      onClick={() => setSelected(v)}
                      className={tc(theme, "text-left rounded border border-zinc-800 bg-black/20 p-2 hover:border-brand-blue transition", "text-left rounded border border-zinc-300 bg-white p-2 hover:border-brand-blue transition")}
                    >
                      <div className="text-xs font-medium truncate">{v.year} {v.make} {v.model}</div>
                      <div className="text-xs text-zinc-500 truncate">{v.stock_number} · {money(v.price)} · {v.margin_pct != null ? `${v.margin_pct}% margin` : "—"}</div>
                      {v.price_history_count > 0 && <div className="text-xs text-amber-500 mt-0.5">{v.price_history_count} price change(s)</div>}
                    </button>
                  ))
                )}
              </div>
            </div>
          ))
        )}
      </div>

      {selected && (
        <VehicleActionsModal
          theme={theme}
          vehicle={selected}
          onClose={() => setSelected(null)}
          onChanged={() => {
            refresh();
            setSelected(null);
          }}
        />
      )}
    </div>
  );
}
