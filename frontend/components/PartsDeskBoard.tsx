"use client";
import {CollectionPagination} from "./CollectionPagination";
import { WorkInput, WorkButton, WorkSelect , WorkStat} from "./WorkspaceUi";
import { formatCalendarDate } from "@/lib/calendarDate";

// Service department's "Parts" item, fifth slice of Service's rebuild -- a
// real department-wide Parts Request Queue, Special Order Tracking
// (vendor/ETA), and Inventory Recommendations (real, off PartSale velocity
// vs. QuantityOnHand). RO Parts Status itself isn't duplicated here -- it's
// already real inside each RO's own Parts tab (RepairOrderWorkspaceBoard.tsx).
import { PRODUCT_ACCENT_COLORS } from "@/lib/productTheme";
import { useEffect, useState } from "react";
import {
  getPartsRequestQueue,
  getSpecialOrders,
  getInventoryRecommendations,
  markSpecialOrder,
  type PartsRequestQueue,
  type SpecialOrders,
  type InventoryRecommendations,
  type PartRequestEntry,
} from "@/lib/partsDesk";
import { getRoCatalog, type RoCatalog } from "@/lib/repairOrders";
import { RoWorkspaceModal } from "@/components/RepairOrderWorkspaceBoard";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const RIBBON = PRODUCT_ACCENT_COLORS;

function fmt(ts: string | null | undefined): string {
  if (!ts) return "—";
  try {
    return formatCalendarDate(ts);
  } catch {
    return ts;
  }
}

function Kpi({ theme, label, value, color }: { theme: Theme; label: string; value: string | number; color: string }) { return <WorkStat label={label} value={value}/>; }

const STATUS_TONE: Record<string, string> = {
  requested: "border-zinc-700 bg-zinc-900/40 text-zinc-300",
  in_stock: "border-emerald-900 bg-emerald-950/30 text-emerald-300",
  ordered: "border-amber-900 bg-amber-950/30 text-amber-300",
  received: "border-blue-900 bg-blue-950/30 text-blue-300",
  installed: "border-zinc-800 bg-zinc-900/20 text-zinc-500",
};

export function SpecialOrderWorkspace({
  theme,
  request,
  onClose,
  onDone,
}: {
  theme: Theme;
  request: PartRequestEntry;
  onClose: () => void;
  onDone: () => void;
}) {
  const [vendor, setVendor] = useState(request.vendor || "");
  const [eta, setEta] = useState(request.eta || "");
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit() {
    if (!confirmed || !vendor.trim() || !eta) return;
    setBusy(true);
    setError(null);
    try {
      await markSpecialOrder(request.ro_id, request.id, vendor, eta);
      onDone();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div role="region" aria-label="Record supplier order" className="p-4">
      <div
        onClick={(e) => e.stopPropagation()}
        className={tc(theme, "w-full max-w-2xl rounded-xl border border-black/20 bg-brand-charcoal text-white p-4 space-y-3", "w-full max-w-2xl rounded-xl border border-zinc-200 bg-white text-black p-4 space-y-3")}
      >
        <h3 className="text-lg font-semibold">Record an existing supplier order</h3>
        <p className="text-sm">Place the order through your approved supplier process first. This saves its vendor and expected arrival for the dealership; it does not send an order or pay the supplier.</p>
        <div className="text-xs text-zinc-500">{request.description} — {request.service_number}</div>
        {error && <div className="text-xs px-3 py-2 rounded-lg bg-red-500/15 border border-red-500/40 text-red-300">{error}</div>}
        <div>
          <label htmlFor="parts-order-vendor" className="text-sm">Vendor</label>
          <WorkInput
            id="parts-order-vendor"
            value={vendor}
            onChange={(e) => setVendor(e.target.value)}
            placeholder="e.g. ACME Parts Co"
            className={tc(theme, "w-full text-xs rounded-md border border-zinc-700 bg-zinc-900 text-white px-2 py-1.5 mt-0.5", "w-full text-xs rounded-md border border-zinc-300 bg-white text-black px-2 py-1.5 mt-0.5")}
          />
        </div>
        <div>
          <label htmlFor="parts-order-eta" className="text-sm">Expected arrival</label>
          <WorkInput
            id="parts-order-eta"
            type="date"
            value={eta}
            onChange={(e) => setEta(e.target.value)}
            className={tc(theme, "w-full text-xs rounded-md border border-zinc-700 bg-zinc-900 text-white px-2 py-1.5 mt-0.5", "w-full text-xs rounded-md border border-zinc-300 bg-white text-black px-2 py-1.5 mt-0.5")}
          />
        </div>
        <label className="flex items-center gap-2 text-sm"><WorkInput type="checkbox" checked={confirmed} onChange={event => setConfirmed(event.target.checked)} />Supplier order has already been placed</label>
        <div className="flex items-center gap-2 justify-end">
          <WorkButton type="submit" disabled={busy} onClick={onClose} className="text-xs px-3 py-1.5 rounded text-zinc-500 hover:text-white transition">Cancel</WorkButton>
          <WorkButton type="submit" variant="primary" disabled={busy || !confirmed || !vendor.trim() || !eta} onClick={handleSubmit} className="text-xs px-3 py-1.5 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50">
            {busy ? "Saving…" : "Save supplier order record"}
          </WorkButton>
        </div>
      </div>
    </div>
  );
}

export function PartsDeskBoard({ theme, onDraftOpenChange, onSavingChange }: { theme: Theme; onDraftOpenChange?: (open: boolean) => void; onSavingChange?: (saving: boolean) => void }) {
  const [queue, setQueue] = useState<PartsRequestQueue | null>(null);
  const [specialOrders, setSpecialOrders] = useState<SpecialOrders | null>(null);
  const [recommendations, setRecommendations] = useState<InventoryRecommendations | null>(null);
  const [catalog, setCatalog] = useState<RoCatalog | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [specialOrderTarget, setSpecialOrderTarget] = useState<PartRequestEntry | null>(null);
  const [openRoId, setOpenRoId] = useState<string | null>(null);

  const [query, setQuery] = useState("");
  const [page, setPage] = useState(0);

  function refresh() {
    setLoading(true);
    setError(null);
    Promise.all([getPartsRequestQueue(), getSpecialOrders(), getInventoryRecommendations(), getRoCatalog()])
      .then(([q, so, rec, c]) => { setQueue(q); setSpecialOrders(so); setRecommendations(rec); setCatalog(c); })
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }

  useEffect(refresh, []);

  const visibleRequests = (queue?.requests ?? []).filter(request =>
    (!statusFilter || request.status === statusFilter) &&
    [request.description, request.service_number, request.customer_name, request.vehicle, request.vendor]
      .join(" ").toLowerCase().includes(query.trim().toLowerCase())
  );

  const totalPages = Math.max(1, Math.ceil(visibleRequests.length / 4));
  const currentPage = Math.min(page, totalPages - 1);

  if (specialOrderTarget) return <SpecialOrderWorkspace theme={theme} request={specialOrderTarget} onClose={() => setSpecialOrderTarget(null)} onDone={() => { setSpecialOrderTarget(null); refresh(); }} />;

  if (openRoId && catalog) return <RoWorkspaceModal inline initialTab="parts" returnLabel="Back to Parts queue" onDraftOpenChange={onDraftOpenChange} onSavingChange={onSavingChange} theme={theme} roId={openRoId} catalog={catalog} onClose={() => setOpenRoId(null)} onChanged={refresh} />;

  const cardClass = tc(theme, "rounded-lg border border-black/20 bg-brand-charcoal p-3", "rounded-lg border border-zinc-200 bg-zinc-50 p-3");

  if (error && !queue) {
    return <div role="alert" className="p-4 text-sm"><p>Unable to load the Parts Desk: {error}</p><WorkButton type="submit" disabled={loading} onClick={refresh} className="min-h-11 underline">Retry loading parts</WorkButton></div>;
  }

  if (loading && !queue) {
    return <div className="p-4 text-sm text-zinc-500">Loading Parts Desk…</div>;
  }

  return (
    <div className={tc(theme, "flex-1 flex flex-col min-h-0 bg-brand-ink text-white overflow-y-auto", "flex-1 flex flex-col min-h-0 bg-white text-black overflow-y-auto")}>
      <div className={tc(theme, "grid grid-cols-2 md:grid-cols-4 gap-3 p-4 border-b border-zinc-800", "grid grid-cols-2 md:grid-cols-4 gap-3 p-4 border-b border-zinc-200")}>
        <Kpi theme={theme} label="Part Requests" value={queue?.count ?? 0} color={RIBBON[0]} />
        <Kpi theme={theme} label="Special Orders" value={specialOrders?.count ?? 0} color={RIBBON[2]} />
        <Kpi theme={theme} label="Overdue Special Orders" value={specialOrders?.overdue_count ?? 0} color={RIBBON[3]} />
        <Kpi theme={theme} label="Reorder Recommendations" value={recommendations?.count ?? 0} color={RIBBON[1]} />
      </div>

      {error && <div role="alert" className="mx-4 mt-2 text-sm px-3 py-2 rounded-lg bg-red-500/15 border border-red-500/40"><p>{error}</p><WorkButton type="submit" disabled={loading} onClick={refresh} className="min-h-11 underline">Retry loading parts</WorkButton></div>}
      {loading && queue && <p role="status" className="px-4 text-sm">Refreshing parts…</p>}

      <div className="p-4 space-y-5">
        <div>
          <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
            <div className="text-xs font-brand uppercase tracking-wide text-zinc-500">Parts Request Queue ({queue?.count ?? 0})</div>
            <WorkSelect
              aria-label="Request status"
              value={statusFilter}
              onChange={(e) => { setStatusFilter(e.target.value); setPage(0); }}
              className={tc(theme, "min-h-11 text-base rounded border border-zinc-700 bg-zinc-900 text-white px-2 py-1", "min-h-11 text-base rounded border border-zinc-300 bg-white text-black px-2 py-1")}
            >
              <option value="">All statuses</option>
              {["requested", "in_stock", "ordered", "received", "installed"].map((s) => (
                <option key={s} value={s}>{s.replace(/_/g, " ")}</option>
              ))}
            </WorkSelect>
          </div>
          <label className="block text-sm mb-3">Find a part request
            <WorkInput type="search" value={query} onChange={event => { setQuery(event.target.value); setPage(0); }} placeholder="Part, repair order, customer, vehicle or vendor" className={tc(theme, "block w-full mt-1 min-h-11 rounded border border-zinc-700 bg-zinc-900 px-3 text-base", "block w-full mt-1 min-h-11 rounded border border-zinc-300 bg-white px-3 text-base")} />
          </label>
          <p className="text-sm mb-3">Showing {visibleRequests.length} of {queue?.count ?? 0} requests. Open a request to review receipt or installation in its repair order. Receiving a part does not mark it installed.</p>
          {visibleRequests.length === 0 ? (
            <div role="status" className="text-sm">{error && !queue ? "Parts could not be loaded. Retry above." : query || statusFilter ? "No requests match these filters." : "No part requests right now."}{(query || statusFilter) && <WorkButton type="submit" onClick={() => { setQuery(""); setStatusFilter(""); }} className="ml-3 min-h-11 underline">Clear filters</WorkButton>}</div>
          ) : (
            <div className="space-y-1.5">
              {visibleRequests.slice(currentPage * 4, currentPage * 4 + 4).map((r) => (
                <div key={`${r.ro_id}-${r.id}`} className={`${cardClass} flex flex-wrap items-center justify-between gap-3`}>
                  <button onClick={() => setOpenRoId(r.ro_id)} className="text-left min-w-0 min-h-11">
                    <div className="text-sm font-medium">{r.description}</div>
                    <div className="text-sm text-blue-400">{r.status === "received" || r.status === "in_stock" ? "Review technician handoff" : r.status === "installed" ? "Review installed part" : "Review request & receipt"} →</div>
                    <div className="text-xs text-zinc-500 truncate">{r.service_number} · {r.customer_name || "—"} · {r.vehicle || "—"}</div>
                  </button>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className={`text-xs px-2 py-0.5 rounded-full border ${STATUS_TONE[r.status] || STATUS_TONE.requested}`}>{r.status.replace(/_/g, " ")}</span>
                    {r.is_special_order ? (
                      <span className="text-xs text-zinc-500">{r.vendor} · ETA {fmt(r.eta)}</span>
                    ) : (
                      <WorkButton type="submit" variant="primary" onClick={() => setSpecialOrderTarget(r)} className="text-sm min-h-11 px-3 py-2 rounded bg-brand-blue text-white hover:opacity-90 transition">
                        Record supplier order
                      </WorkButton>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <CollectionPagination label="Parts requests" total={visibleRequests.length} page={currentPage} pageSize={4} onPageChange={setPage} busy={loading}/>

        <details>
          <summary className="cursor-pointer min-h-11 text-sm font-semibold">Special orders & arrival tracking ({specialOrders?.count ?? 0})</summary>
          <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1.5">
            Special Order Tracking ({specialOrders?.count ?? 0}, {specialOrders?.overdue_count ?? 0} overdue)
          </div>
          {(specialOrders?.special_orders.length ?? 0) === 0 ? (
            <div className="text-xs text-zinc-600">No special orders on file.</div>
          ) : (
            <div className="space-y-1.5">
              {specialOrders!.special_orders.map((so) => (
                <button key={`${so.ro_id}-${so.id}`} onClick={() => setOpenRoId(so.ro_id)} className={`${cardClass} w-full text-left flex items-center justify-between gap-2 hover:border-brand-blue/60 transition`}>
                  <div className="min-w-0">
                    <div className="text-xs font-medium truncate">{so.description} — {so.vendor}</div>
                    <div className="text-xs text-zinc-500 truncate">{so.service_number} · {so.customer_name || "—"}</div>
                  </div>
                  <div className={`text-xs shrink-0 ${so.overdue ? "text-red-400" : "text-zinc-500"}`}>
                    {so.overdue ? `${Math.abs(so.days_until_eta ?? 0)}d overdue` : `ETA ${fmt(so.eta)} (${so.days_until_eta}d)`}
                  </div>
                </button>
              ))}
            </div>
          )}
        </details>

        <details>
          <summary className="cursor-pointer min-h-11 text-sm font-semibold">Inventory recommendations ({recommendations?.count ?? 0})</summary>
          <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1.5">
            Inventory Recommendations ({recommendations?.count ?? 0})
          </div>
          {(recommendations?.recommendations.length ?? 0) === 0 ? (
            <div className="text-xs text-zinc-600">No reorder recommendations right now.</div>
          ) : (
            <div className="space-y-1.5">
              {recommendations!.recommendations.map((r) => (
                <div key={r.part_id} className={`${cardClass} flex flex-wrap items-center justify-between gap-3`}>
                  <div className="min-w-0">
                    <div className="text-xs font-medium truncate">{r.description} ({r.part_number})</div>
                    <div className="text-xs text-zinc-500 truncate">{r.recommendation}</div>
                  </div>
                  <div className="text-xs text-zinc-500 shrink-0">On hand: {r.quantity_on_hand} · Sold: {r.total_units_sold}</div>
                </div>
              ))}
            </div>
          )}
          {recommendations && (
            <div className="text-xs text-zinc-600 italic mt-1.5">
              {recommendations.not_yet_tracked.reorder_points}
            </div>
          )}
        </details>
      </div>
    </div>
  );
}
