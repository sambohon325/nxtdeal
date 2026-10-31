"use client";
import { WorkButton, WorkSelect, WorkInput , WorkStat, WorkOverlay} from "./WorkspaceUi";
import { WorkField } from "./WorkField";

// Operations' "Vehicles" item -- Vehicle Lifecycle Management, the flagship build
// of Operations' rebuild (session 106 follow-up). Sam's own framing, from a full
// Operations spec: "Sales should manage the customer lifecycle. Operations should
// manage the vehicle lifecycle... This should be one of the largest operational
// modules." Backend: core/vehicle_lifecycle.py / _api.py.
//
// A real 10-stage pipeline board (Acquired -> ... -> Delivered) with click-to-
// advance (not full drag-and-drop -- this pipeline has 10 stages, not 4-5 like
// Deal Desk's Kanban, so a horizontal scroll of narrow columns plus an explicit
// "Advance ->" action per card is the more usable interaction, same button-
// advance precedent as AppointmentsBoard/UpSystemBoard/BdcBoard/DemoDriveBoard).
// The detail panel covers all four of Sam's real asks: Acquisition Data (honest
// about what this graph does/doesn't track), a real Recon Checklist, real Vendor
// Coordination, and real Internal Messaging (reusing core/field_notes.py).
import { PRODUCT_ACCENT_COLORS } from "@/lib/productTheme";
import { useEffect, useState } from "react";
import {
  getLifecycleCatalog,
  getLifecycleBoard,
  getVehicleLifecycle,
  updateLifecycleStatus,
  updateReconItem,
  assignVendor,
  updateVendorStatus,
  getVehicleMessages,
  sendVehicleMessage,
  type LifecycleCatalog,
  type LifecycleBoard as LifecycleBoardData,
  type LifecycleStage,
  type VehicleLifecycle,
  type ReconItem,
  type VendorType,
  type VehicleMessage,
} from "@/lib/vehicleLifecycle";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const RIBBON = PRODUCT_ACCENT_COLORS;

const RECON_LABELS: Record<string, string> = {
  inspection: "Inspection", oil_change: "Oil Change", tires: "Tires", body_work: "Body Work", photos: "Photos",
};

const VENDOR_LABELS: Record<string, string> = {
  body_shop: "Body Shop", detail: "Detail", paint: "Paint", glass: "Glass", other: "Other",
};

function money(v: string | number | null | undefined): string {
  if (v === null || v === undefined || v === "") return "—";
  const n = typeof v === "string" ? parseFloat(v) : v;
  if (Number.isNaN(n)) return String(v);
  return `$${n.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

function fmt(ts: string | null | undefined): string {
  if (!ts) return "—";
  try {
    return new Date(ts).toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  } catch {
    return ts;
  }
}

function Kpi({ theme, label, value, color }: { theme: Theme; label: string; value: number; color: string }) { return <WorkStat label={label} value={value}/>; }

function VehicleDetailModal({
  theme,
  vehicleId,
  catalog,
  onClose,
  onChanged,
}: {
  theme: Theme;
  vehicleId: string;
  catalog: LifecycleCatalog;
  onClose: () => void;
  onChanged: () => void;
}) {
  const [data, setData] = useState<VehicleLifecycle | null>(null);
  const [messages, setMessages] = useState<VehicleMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [messageBody, setMessageBody] = useState("");
  const [vendorType, setVendorType] = useState<VendorType>("body_shop");
  const [vendorName, setVendorName] = useState("");
  const [vendorNotes, setVendorNotes] = useState("");

  function refresh() {
    setLoading(true);
    Promise.all([getVehicleLifecycle(vehicleId), getVehicleMessages(vehicleId)])
      .then(([d, m]) => {
        setData(d);
        setMessages(m);
      })
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }

  useEffect(refresh, [vehicleId]);

  const textClass = tc(theme, "bg-zinc-900 border-zinc-700 text-white placeholder:text-zinc-600", "bg-white border-zinc-300 text-black placeholder:text-zinc-400");
  const cardClass = tc(theme, "rounded-lg border border-black/20 bg-brand-charcoal p-3", "rounded-lg border border-zinc-200 bg-zinc-50 p-3");

  async function withBusy(fn: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      refresh();
      onChanged();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function handleSendMessage() {
    if (!messageBody.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await sendVehicleMessage(vehicleId, messageBody.trim());
      setMessageBody("");
      const m = await getVehicleMessages(vehicleId);
      setMessages(m);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function handleAssignVendor() {
    if (!vendorName.trim()) {
      setError("A vendor name is required.");
      return;
    }
    await withBusy(() => assignVendor(vehicleId, vendorType, vendorName.trim(), vendorNotes));
    setVendorName("");
    setVendorNotes("");
  }

  return (
    <WorkOverlay className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div
        onClick={(e) => e.stopPropagation()}
        className={tc(theme, "work-record-content w-full max-w-3xl max-h-[90vh] overflow-y-auto rounded-xl border border-black/20 bg-brand-ink text-white p-5 space-y-4", "work-record-content w-full max-w-3xl max-h-[90vh] overflow-y-auto rounded-xl border border-zinc-200 bg-white text-black p-5 space-y-4")}
      >
        {loading || !data ? (
          <div className="text-sm text-zinc-500">Loading…</div>
        ) : (
          <>
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="work-detail-title">
                  {data.year} {data.make} {data.model} {data.trim}
                </div>
                <div className="text-xs text-zinc-500 mt-0.5">
                  {data.vin} · {data.stock_number} · {money(data.price)}
                </div>
              </div>
              <WorkButton type="submit" onClick={onClose} className="text-xs text-zinc-500 hover:text-white transition">✕ Close</WorkButton>
            </div>

            {error && <div className="text-xs px-3 py-2 rounded-lg bg-red-500/15 border border-red-500/40 text-red-300">{error}</div>}

            {/* Lifecycle status */}
            <div className={cardClass}>
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">
                Lifecycle Status {data.lifecycle_status_is_default && <span className="opacity-60">(default, not yet moved)</span>}
              </div>
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-sm font-medium px-2.5 py-1 rounded bg-brand-blue text-white">{data.lifecycle_status}</span>
                <WorkField label="Move to"><WorkSelect
                  disabled={busy}
                  value=""
                  onChange={(e) => {
                    if (e.target.value) withBusy(() => updateLifecycleStatus(vehicleId, e.target.value as LifecycleStage));
                  }}
                  className={`rounded-md border px-2 py-1 text-xs ${textClass}`}
                >
                  <option value="">Move to…</option>
                  {catalog.stages.filter((s) => s !== data.lifecycle_status).map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </WorkSelect></WorkField>
              </div>
              {data.status_history.length > 0 && (
                <div className="mt-2 space-y-0.5">
                  {data.status_history.slice(-5).reverse().map((h, i) => (
                    <div key={i} className="text-xs text-zinc-500">{fmt(h.at)} — {h.status} by {h.by}</div>
                  ))}
                </div>
              )}
            </div>

            {/* Acquisition data */}
            <div className={cardClass}>
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Acquisition Data</div>
              <div className="grid grid-cols-3 gap-2 text-xs">
                <div><span className="text-zinc-500">Cost</span><div>{money(data.acquisition.cost)}</div></div>
                <div><span className="text-zinc-500">Lot</span><div>{data.acquisition.lot || "—"}</div></div>
                <div><span className="text-zinc-500">Condition</span><div>{data.acquisition.condition || "—"}</div></div>
              </div>
              {data.acquisition.auction_data ? (
                <div className="mt-2 pt-2 border-t border-zinc-800 grid grid-cols-2 gap-2 text-xs">
                  <div><span className="text-zinc-500">Auction House</span><div>{data.acquisition.auction_data.auction_house}</div></div>
                  <div><span className="text-zinc-500">Bid Amount</span><div>{money(data.acquisition.auction_data.bid_amount)}</div></div>
                  <div><span className="text-zinc-500">Purchase Date</span><div>{data.acquisition.auction_data.purchase_date || "—"}</div></div>
                  <div><span className="text-zinc-500">Carrier</span><div>{data.acquisition.auction_data.carrier || "—"}</div></div>
                </div>
              ) : (
                data.acquisition.not_yet_tracked && (
                  <div className="mt-2 text-xs text-zinc-600 italic">{data.acquisition.not_yet_tracked}</div>
                )
              )}
            </div>

            {/* Recon checklist */}
            <div className={cardClass}>
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Recon Checklist</div>
              <div className="space-y-1.5">
                {catalog.recon_items.map((item) => {
                  const entry = data.recon_checklist[item as ReconItem];
                  return (
                    <label key={item} className="flex items-center gap-2 text-xs cursor-pointer">
                      <WorkInput
                        type="checkbox"
                        checked={entry?.complete || false}
                        disabled={busy}
                        onChange={(e) => withBusy(() => updateReconItem(vehicleId, item as ReconItem, e.target.checked))}
                      />
                      <span className={entry?.complete ? "line-through text-zinc-500" : ""}>{RECON_LABELS[item] || item}</span>
                      {entry?.updated_by && <span className="text-xs text-zinc-600">— {entry.updated_by}, {fmt(entry.updated_at)}</span>}
                    </label>
                  );
                })}
              </div>
            </div>

            {/* Vendor coordination */}
            <div className={cardClass}>
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Vendor Coordination</div>
              <div className="space-y-1.5 mb-2">
                {data.vendor_assignments.length === 0 ? (
                  <div className="text-xs text-zinc-600">No vendor work assigned.</div>
                ) : (
                  data.vendor_assignments.map((v) => (
                    <div key={v.id} className="flex items-center justify-between gap-2 text-xs rounded border border-zinc-800 px-2 py-1.5">
                      <div>
                        <span className="font-medium">{VENDOR_LABELS[v.vendor_type] || v.vendor_type}</span> — {v.vendor_name}
                        {v.notes && <span className="text-zinc-500"> · {v.notes}</span>}
                      </div>
                      <div className="flex items-center gap-1.5 shrink-0">
                        <span className={`text-xs px-1.5 py-0.5 rounded ${v.status === "complete" ? "bg-green-950/40 text-green-300" : v.status === "in_progress" ? "bg-amber-950/40 text-amber-300" : "bg-zinc-800 text-zinc-400"}`}>{v.status}</span>
                        {v.status !== "complete" && (
                          <WorkButton type="submit" variant="primary"
                            disabled={busy}
                            onClick={() => withBusy(() => updateVendorStatus(vehicleId, v.id, v.status === "assigned" ? "in_progress" : "complete"))}
                            className="text-xs px-2 py-0.5 rounded bg-brand-blue text-white hover:opacity-90 transition disabled:opacity-50"
                          >
                            {v.status === "assigned" ? "Start" : "Complete"}
                          </WorkButton>
                        )}
                      </div>
                    </div>
                  ))
                )}
              </div>
              <div className="flex items-center gap-1.5">
                <WorkField label="Vendor Type"><WorkSelect value={vendorType} onChange={(e) => setVendorType(e.target.value as VendorType)} className={`rounded-md border px-2 py-1 text-xs ${textClass}`}>
                  {catalog.vendor_types.map((t) => (
                    <option key={t} value={t}>{VENDOR_LABELS[t] || t}</option>
                  ))}
                </WorkSelect></WorkField>
                <WorkField label="Vendor name"><WorkInput value={vendorName} onChange={(e) => setVendorName(e.target.value)} placeholder="Vendor name…" className={`flex-1 rounded-md border px-2 py-1 text-xs ${textClass}`} /></WorkField>
                <WorkField label="Notes (optional)"><WorkInput value={vendorNotes} onChange={(e) => setVendorNotes(e.target.value)} placeholder="Notes (optional)" className={`flex-1 rounded-md border px-2 py-1 text-xs ${textClass}`} /></WorkField>
                <WorkButton type="submit" variant="primary" disabled={busy} onClick={handleAssignVendor} className="text-xs px-2.5 py-1 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50">Assign</WorkButton>
              </div>
            </div>

            {/* Internal messaging */}
            <div className={cardClass}>
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Internal Messaging</div>
              <div className="space-y-1.5 mb-2 max-h-40 overflow-y-auto">
                {messages.length === 0 ? (
                  <div className="text-xs text-zinc-600">No messages yet.</div>
                ) : (
                  messages.map((m) => (
                    <div key={m.id} className="text-xs">
                      <span className="font-medium">{m.created_by}:</span> {m.body}
                      <span className="text-xs text-zinc-600"> — {fmt(m.created_at)}</span>
                    </div>
                  ))
                )}
              </div>
              <div className="flex items-center gap-1.5">
                <WorkField label="Message another department about this vehicle"><WorkInput
                  value={messageBody}
                  onChange={(e) => setMessageBody(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") handleSendMessage(); }}
                  placeholder="Message another department about this vehicle…"
                  className={`flex-1 rounded-md border px-2 py-1.5 text-xs ${textClass}`}
                /></WorkField>
                <WorkButton type="submit" variant="primary" disabled={busy} onClick={handleSendMessage} className="text-xs px-2.5 py-1.5 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50">Send</WorkButton>
              </div>
            </div>
          </>
        )}
      </div>
    </WorkOverlay>
  );
}

export function VehicleLifecycleBoard({ theme }: { theme: Theme }) {
  const [catalog, setCatalog] = useState<LifecycleCatalog | null>(null);
  const [board, setBoard] = useState<LifecycleBoardData>({});
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<string | null>(null);

  function refresh() {
    setLoading(true);
    Promise.all([getLifecycleCatalog(), getLifecycleBoard()])
      .then(([c, b]) => {
        setCatalog(c);
        setBoard(b);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }

  useEffect(refresh, []);

  const activeCount = catalog
    ? catalog.stages.filter((s) => s !== "Sold" && s !== "Delivered" && s !== "Front Line Ready").reduce((sum, s) => sum + (board[s]?.length || 0), 0)
    : 0;
  const frontLineCount = board["Front Line Ready"]?.length || 0;
  const soldCount = (board["Sold"]?.length || 0) + (board["Delivered"]?.length || 0);
  const totalCount = Object.values(board).reduce((sum, v) => sum + v.length, 0);

  return (
    <div className={tc(theme, "flex-1 flex flex-col min-h-0 bg-brand-ink text-white", "flex-1 flex flex-col min-h-0 bg-white text-black")}>
      <div className={tc(theme, "grid grid-cols-4 gap-3 p-4 border-b border-zinc-800", "grid grid-cols-4 gap-3 p-4 border-b border-zinc-200")}>
        <Kpi theme={theme} label="Total Vehicles" value={totalCount} color={RIBBON[0]} />
        <Kpi theme={theme} label="In Recon Pipeline" value={activeCount} color={RIBBON[1]} />
        <Kpi theme={theme} label="Front Line Ready" value={frontLineCount} color={RIBBON[2]} />
        <Kpi theme={theme} label="Sold / Delivered" value={soldCount} color={RIBBON[3]} />
      </div>

      <div className="flex-1 overflow-x-auto overflow-y-hidden p-4">
        {loading || !catalog ? (
          <div className="text-sm text-zinc-500">Loading…</div>
        ) : (
          <div className="flex gap-3 h-full min-w-max">
            {catalog.stages.map((stage, i) => {
              const cars = board[stage] || [];
              return (
                <div key={stage} className={tc(theme, "w-52 shrink-0 rounded-lg border border-zinc-800 bg-brand-charcoal flex flex-col", "w-52 shrink-0 rounded-lg border border-zinc-200 bg-zinc-50 flex flex-col")}>
                  <div className="px-2.5 py-2 border-b border-zinc-800 flex items-center justify-between">
                    <span className="text-xs font-brand uppercase tracking-wide">{stage}</span>
                    <span className="text-xs px-1.5 py-0.5 rounded" style={{ background: RIBBON[i % 4], color: "#000" }}>{cars.length}</span>
                  </div>
                  <div className="flex-1 overflow-y-auto p-1.5 space-y-1.5">
                    {cars.map((v) => (
                      <button
                        key={v.vehicle_id}
                        onClick={() => setSelected(v.vehicle_id)}
                        className={tc(theme, "w-full text-left rounded border border-zinc-800 bg-black/20 p-1.5 hover:border-brand-blue transition", "w-full text-left rounded border border-zinc-300 bg-white p-1.5 hover:border-brand-blue transition")}
                      >
                        <div className="text-xs font-medium truncate">{v.year} {v.make} {v.model}</div>
                        <div className="text-xs text-zinc-500 truncate">{v.stock_number} · {money(v.price)}</div>
                      </button>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {selected && catalog && (
        <VehicleDetailModal
          theme={theme}
          vehicleId={selected}
          catalog={catalog}
          onClose={() => setSelected(null)}
          onChanged={refresh}
        />
      )}
    </div>
  );
}
