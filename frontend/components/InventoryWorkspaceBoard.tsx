"use client";
import { WorkButton, WorkSelect, WorkInput , WorkStat} from "./WorkspaceUi";
import {CollectionPagination} from "./CollectionPagination";
import {RecordTable} from "./RecordTable";
import { WorkField } from "./WorkField";

// Inventory department's "Inventory" item -- the Master Vehicle Workspace,
// first slice of Inventory's rebuild (Sam picked this over Acquisitions/
// Pricing/Overview: "Inventory manages the dealership's largest asset:
// Vehicles"). Reuses core/vehicle_lifecycle.py's real 10-stage Kanban board
// engine (already built for Operations' "Vehicles" item, session 106) for the
// pipeline view + lifecycle/recon/vendor/messaging sections, and adds this
// slice's own new real pieces on top: Cost Breakdown, Ownership assignment,
// and a composed Activity Feed (core/vehicle_lifecycle.py's
// get_vehicle_workspace/get_cost_breakdown/assign_ownership/
// get_vehicle_activity_feed). A search bar (VIN/stock/free-text, via
// core/inventory_menu.py's inventory(role, query)) sits above the board so a
// specific unit can be found without scrolling all 10 Kanban columns.
import { PRODUCT_ACCENT_COLORS } from "@/lib/productTheme";
import { useEffect, useMemo, useState } from "react";
import {
  getLifecycleCatalog,
  getLifecycleBoard,
  getVehicleWorkspace,
  updateLifecycleStatus,
  updateReconItem,
  assignVendor,
  updateVendorStatus,
  updateCostBreakdown,
  assignOwnership,
  getVehicleMessages,
  sendVehicleMessage,
  type LifecycleCatalog,
  type LifecycleBoard as LifecycleBoardData,
  type LifecycleStage,
  type VehicleWorkspace,
  type ReconItem,
  type VendorType,
  type CostField,
  type OwnershipRole,
  type VehicleMessage,
} from "@/lib/vehicleLifecycle";
import { searchInventory, type InventorySearchResults } from "@/lib/inventoryWorkspace";
import {
  getVehicleAgingBrief,
  reduceVehiclePrice,
  requestWholesaleReview,
  requestManagerReview,
  requestAuctionAssignment,
  createMarketingTieIn,
  type VehicleAgingBrief,
} from "@/lib/inventoryAging";
import {
  getVehicleVinDecode,
  applyVinDecodeToVehicle,
  type VinDecodeAppliedRecord,
  type VinDecodeResolved,
} from "@/lib/vinDecoder";

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

const COST_LABELS: Record<CostField, string> = {
  acquisition_cost: "Acquisition Cost",
  transport_cost: "Transport Cost",
  recon_cost: "Recon Cost",
  floorplan_interest: "Floorplan Interest",
  marketing_cost: "Marketing Cost",
};

const OWNERSHIP_LABELS: Record<OwnershipRole, string> = {
  buyer: "Buyer",
  inventory_manager: "Inventory Manager",
  recon_manager: "Recon Manager",
  sales_manager: "Sales Manager",
};

export function ownershipChanges(drafts: Partial<Record<OwnershipRole, string>>, current: Partial<Record<OwnershipRole, string | null>>) {
  const changes: Partial<Record<OwnershipRole, string>> = {};
  for (const role of Object.keys(OWNERSHIP_LABELS) as OwnershipRole[]) {
    const value = drafts[role];
    if (value !== undefined && value.trim() !== (current[role] || "")) changes[role] = value.trim();
  }
  return changes;
}

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

const ACTIVITY_ICONS: Record<string, string> = {
  lifecycle_status: "→", recon_item: "✓", vendor_assigned: "🔧", vendor_completed: "✔",
  price_change: "$", document_uploaded: "📄", document_approved: "✅", document_rejected: "✕",
  cost_breakdown_updated: "$", ownership_updated: "👤",
};

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
  const [data, setData] = useState<VehicleWorkspace | null>(null);
  const [messages, setMessages] = useState<VehicleMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [messageBody, setMessageBody] = useState("");
  const [vendorType, setVendorType] = useState<VendorType>("body_shop");
  const [vendorName, setVendorName] = useState("");
  const [vendorNotes, setVendorNotes] = useState("");
  const [costDrafts, setCostDrafts] = useState<Partial<Record<CostField, string>>>({});
  const [ownerDrafts, setOwnerDrafts] = useState<Partial<Record<OwnershipRole, string>>>({});
  const [tab, setTab] = useState<"lifecycle" | "cost" | "ownership" | "activity" | "messages" | "aging" | "vin">("lifecycle");
  const [aging, setAging] = useState<VehicleAgingBrief | null>(null);
  const [agingLoading, setAgingLoading] = useState(false);
  const [newPrice, setNewPrice] = useState("");
  const [priceReason, setPriceReason] = useState("");
  const [actionNotes, setActionNotes] = useState("");
  const [actionMsg, setActionMsg] = useState<string | null>(null);
  const [vinRecord, setVinRecord] = useState<VinDecodeAppliedRecord | null>(null);
  const [vinNote, setVinNote] = useState<string | null>(null);
  const [vinChecked, setVinChecked] = useState(false);
  const [vinLoading, setVinLoading] = useState(false);
  const [vinDecoding, setVinDecoding] = useState(false);
  const [vinMsg, setVinMsg] = useState<string | null>(null);

  const [stageDraft, setStageDraft] = useState("");
  const [confirmClose, setConfirmClose] = useState(false);
  function requestClose() {
    if (busy || vinDecoding) return;
    if (stageDraft || messageBody || vendorName || vendorNotes || Object.keys(costDrafts).length || Object.keys(ownerDrafts).length || newPrice || priceReason || actionNotes) setConfirmClose(true);
    else onClose();
  }

  function refresh() {
    setLoading(true);
    Promise.all([getVehicleWorkspace(vehicleId), getVehicleMessages(vehicleId)])
      .then(([d, m]) => {
        setData(d);
        setMessages(m);
        setAging(null);
        setActionMsg(null);
        setVinRecord(null);
        setVinNote(null);
        setVinChecked(false);
        setVinMsg(null);
      })
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }

  useEffect(refresh, [vehicleId]);

  function loadAging() {
    setAgingLoading(true);
    getVehicleAgingBrief(vehicleId)
      .then((a) => setAging(a))
      .catch((e) => setError((e as Error).message))
      .finally(() => setAgingLoading(false));
  }

  useEffect(() => {
    if (tab === "aging" && !aging) loadAging();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, vehicleId]);

  function loadVin() {
    setVinLoading(true);
    getVehicleVinDecode(vehicleId)
      .then((r) => {
        setVinRecord(r.vin_decode);
        setVinNote(r.note || null);
      })
      .catch((e) => setError((e as Error).message))
      .finally(() => {
        setVinChecked(true);
        setVinLoading(false);
      });
  }

  useEffect(() => {
    if (tab === "vin" && !vinChecked) loadVin();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, vehicleId]);

  const textClass = tc(theme, "bg-zinc-900 border-zinc-700 text-white placeholder:text-zinc-600", "bg-white border-zinc-300 text-black placeholder:text-zinc-400");
  const cardClass = tc(theme, "rounded-lg border border-black/20 bg-brand-charcoal p-3", "rounded-lg border border-zinc-200 bg-zinc-50 p-3");

  async function withBusy(fn: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      refresh();
      onChanged();
      return true;
    } catch (e) {
      setError((e as Error).message);
      return false;
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
    if (await withBusy(() => assignVendor(vehicleId, vendorType, vendorName.trim(), vendorNotes))) {
      setVendorName("");
      setVendorNotes("");
    }
  }

  async function handleSaveCosts() {
    const fields: Partial<Record<CostField, number>> = {};
    for (const [k, v] of Object.entries(costDrafts)) {
      if (v !== undefined && v !== "") {
        const n = parseFloat(v);
        if (!Number.isNaN(n)) fields[k as CostField] = n;
      }
    }
    if (Object.keys(fields).length === 0) return;
    if (await withBusy(() => updateCostBreakdown(vehicleId, fields))) setCostDrafts({});
  }

  async function handleSaveOwnership() {
    const roles = ownershipChanges(ownerDrafts, data?.ownership.assignments || {});
    if (Object.keys(roles).length === 0) return;
    if (await withBusy(() => assignOwnership(vehicleId, roles))) setOwnerDrafts({});
  }

  async function handleReducePrice() {
    const n = parseFloat(newPrice);
    if (Number.isNaN(n) || n <= 0) {
      setError("Enter a valid new price.");
      return;
    }
    setBusy(true);
    setError(null);
    setActionMsg(null);
    try {
      await reduceVehiclePrice(vehicleId, n, priceReason);
      setNewPrice("");
      setPriceReason("");
      setActionMsg("Price reduced.");
      loadAging();
      onChanged();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function handleAgingAction(kind: "wholesale" | "manager" | "auction" | "marketing") {
    setBusy(true);
    setError(null);
    setActionMsg(null);
    try {
      if (kind === "wholesale") {
        await requestWholesaleReview(vehicleId, actionNotes);
        setActionMsg("Wholesale review task created.");
      } else if (kind === "manager") {
        await requestManagerReview(vehicleId, actionNotes);
        setActionMsg("Manager review task created.");
      } else if (kind === "auction") {
        await requestAuctionAssignment(vehicleId, actionNotes);
        setActionMsg("Auction assignment task created.");
      } else {
        await createMarketingTieIn(vehicleId);
        setActionMsg("Draft marketing campaign + tie-in task created.");
      }
      setActionNotes("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function handleDecodeVin() {
    setVinDecoding(true);
    setError(null);
    setVinMsg(null);
    try {
      const result = await applyVinDecodeToVehicle(vehicleId);
      setVinRecord(result.applied);
      setVinNote(null);
      setVinChecked(true);
      setVinMsg(
        result.applied.backfilled_fields.length > 0
          ? `Applied -- backfilled: ${result.applied.backfilled_fields.join(", ")}`
          : "Decoded -- no blank Vehicle fields to backfill (record already has these fields on file)."
      );
      onChanged();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setVinDecoding(false);
    }
  }

  const TABS: { key: typeof tab; label: string }[] = [
    { key: "lifecycle", label: "Lifecycle" },
    { key: "cost", label: "Cost Breakdown" },
    { key: "ownership", label: "Responsible staff" },
    { key: "activity", label: "Activity Feed" },
    { key: "aging", label: "Aging Actions" },
    { key: "vin", label: "VIN Decoder" },
    { key: "messages", label: "Messaging" },
  ];

  return (
    <div data-department-work="" className="workspace-inline-editor">
      <div
        onClick={(e) => e.stopPropagation()}
        role="region" aria-label="Vehicle workspace"
        className="workspace-editor-surface work-record-content p-5 space-y-4"
      >
        <WorkButton type="submit" disabled={busy || vinDecoding} onClick={requestClose} className="min-h-11 underline">Back to inventory</WorkButton>
        {confirmClose && <section role="alert"><p>You have unsaved vehicle changes.</p><WorkButton type="submit" className="min-h-11 border rounded px-3" onClick={()=>setConfirmClose(false)}>Keep editing</WorkButton><WorkButton type="submit" className="min-h-11 underline px-3" onClick={onClose}>Discard draft and return</WorkButton></section>}
        {loading || !data ? (
          <div role={error ? "alert" : "status"}>{error || "Loading vehicle…"}{error && <WorkButton type="submit" className="min-h-11 underline" onClick={refresh}>Retry vehicle</WorkButton>}</div>
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
              <WorkButton type="submit" disabled={busy || vinDecoding} onClick={requestClose} className="min-h-11 text-sm underline">Close vehicle</WorkButton>
            </div>

            {error && <div className="text-xs px-3 py-2 rounded-lg bg-red-500/15 border border-red-500/40 text-red-300">{error}</div>}

            <div className="flex items-center gap-1.5 flex-wrap border-b border-zinc-800 pb-2">
              {TABS.map((t) => (
                <WorkButton data-work-view aria-pressed={tab === t.key} type="submit"
                  key={t.key}
                  onClick={() => setTab(t.key)}
                  className={`text-xs px-2.5 py-1 rounded-full font-brand uppercase tracking-wide transition ${
                    tab === t.key ? "bg-brand-blue text-white" : "bg-zinc-200/10 text-zinc-400 hover:text-white"
                  }`}
                >
                  {t.label}
                </WorkButton>
              ))}
            </div>

            {tab === "lifecycle" && (
              <>
                <div className={cardClass}>
                  <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">
                    Lifecycle Status {data.lifecycle_status_is_default && <span className="opacity-60">(default, not yet moved)</span>}
                  </div>
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-medium px-2.5 py-1 rounded bg-brand-blue text-white">{data.lifecycle_status}</span>
                    <WorkSelect
                      disabled={busy}
                      aria-label="Next vehicle stage"
                      value={stageDraft}
                      onChange={(e) => setStageDraft(e.target.value)}
                      className={`rounded-md border px-2 py-1 text-xs ${textClass}`}
                    >
                      <option value="">Move to…</option>
                      {catalog.stages.filter((s) => s !== data.lifecycle_status).map((s) => (
                        <option key={s} value={s}>{s}</option>
                      ))}
                    </WorkSelect>
                    <WorkButton type="submit" variant="primary" disabled={busy || !stageDraft} className="min-h-11 rounded bg-brand-blue text-white px-3 disabled:opacity-50" onClick={()=>withBusy(()=>updateLifecycleStatus(vehicleId,stageDraft as LifecycleStage)).then(saved=>{if(saved)setStageDraft("");})}>Save stage</WorkButton>
                    <p className="text-sm">Select the next stage, then save after confirming the work is complete. Selecting alone does not change the vehicle.</p>
                  </div>
                  {data.status_history.length > 0 && (
                    <div className="mt-2 space-y-0.5">
                      {data.status_history.slice(-5).reverse().map((h, i) => (
                        <div key={i} className="text-xs text-zinc-500">{fmt(h.at)} — {h.status} by {h.by}</div>
                      ))}
                    </div>
                  )}
                </div>

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
                  <div className="flex items-center gap-1.5 flex-wrap">
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
              </>
            )}

            {tab === "cost" && (
              <div className={cardClass}>
                <div className="flex items-center justify-between mb-2">
                  <div className="text-xs font-brand uppercase tracking-wide text-zinc-500">Cost Breakdown</div>
                  <div className="text-sm font-semibold">{money(data.cost_breakdown.total_investment)} total</div>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  {(Object.keys(COST_LABELS) as CostField[]).map((field) => (
                    <div key={field} className="text-xs">
                      <div className="text-zinc-500 mb-0.5">
                        {COST_LABELS[field]}
                        {field === "acquisition_cost" && data.cost_breakdown.acquisition_cost_is_default && (
                          <span className="opacity-60"> (from Vehicle.Cost)</span>
                        )}
                      </div>
                      <WorkInput
                        type="number"
                        aria-label={COST_LABELS[field]} placeholder={money(data.cost_breakdown.breakdown[field])}
                        value={costDrafts[field] ?? ""}
                        onChange={(e) => setCostDrafts((d) => ({ ...d, [field]: e.target.value }))}
                        className={`w-full rounded-md border px-2 py-1 text-xs ${textClass}`}
                      />
                    </div>
                  ))}
                </div>
                <WorkButton type="submit" variant="primary" disabled={busy} onClick={handleSaveCosts} className="mt-3 text-xs px-2.5 py-1 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50">Save Cost Changes</WorkButton>
                {data.cost_breakdown.updated_at && (
                  <div className="mt-2 text-xs text-zinc-600">Last updated {fmt(data.cost_breakdown.updated_at)} by {data.cost_breakdown.updated_by}</div>
                )}
              </div>
            )}

            {tab === "ownership" && (
              <div className={cardClass}>
                <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Responsible staff</div>
                <p className="text-xs text-zinc-500 mb-3">Record who is responsible for buying, inventory, reconditioning and sales. These are internal staff assignments, not vehicle title or legal ownership. Enter an employee ID; clear a field and save to remove its assignment. This records responsibility only; it does not send a notification or create a task.</p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  {(Object.keys(OWNERSHIP_LABELS) as OwnershipRole[]).map((role) => (
                    <div key={role} className="text-xs">
                      <div className="text-zinc-500 mb-0.5">{OWNERSHIP_LABELS[role]}</div>
                      <WorkInput
                        aria-label={`${OWNERSHIP_LABELS[role]} employee ID`}
                        disabled={busy}
                        placeholder="Unassigned — employee ID"
                        value={ownerDrafts[role] ?? data.ownership.assignments[role] ?? ""}
                        onChange={(e) => setOwnerDrafts((d) => ({ ...d, [role]: e.target.value }))}
                        className={`w-full rounded-md border px-2 py-1 text-xs ${textClass}`}
                      />
                    </div>
                  ))}
                </div>
                <WorkButton type="submit" variant="primary" disabled={busy || !Object.keys(ownershipChanges(ownerDrafts, data.ownership.assignments)).length} onClick={handleSaveOwnership} className="mt-3 text-xs px-2.5 py-1 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50">Save staff assignments</WorkButton>
                {data.ownership.updated_at && (
                  <div className="mt-2 text-xs text-zinc-600">Last updated {fmt(data.ownership.updated_at)} by {data.ownership.updated_by}</div>
                )}
              </div>
            )}

            {tab === "activity" && (
              <div className={cardClass}>
                <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Activity Feed — Full Audit Trail</div>
                {data.activity_feed.events.length === 0 ? (
                  <div className="text-xs text-zinc-600">No activity recorded yet.</div>
                ) : (
                  <div className="space-y-1.5 max-h-96 overflow-y-auto">
                    {data.activity_feed.events.map((e, i) => (
                      <div key={i} className="flex items-start gap-2 text-xs border-b border-zinc-800/60 pb-1.5">
                        <span className="shrink-0 w-4 text-center opacity-70">{ACTIVITY_ICONS[e.type] || "•"}</span>
                        <div className="flex-1">
                          <div>{e.label}</div>
                          {e.notes && <div className="text-xs text-zinc-500 italic">{e.notes}</div>}
                        </div>
                        <div className="text-xs text-zinc-500 text-right shrink-0">
                          <div>{fmt(e.at)}</div>
                          {e.by && <div>{e.by}</div>}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {tab === "aging" && (
              <>
                <div className="text-xs text-zinc-600 italic px-1">
                  Same real Inventory Aging Management engine backing Operations&rsquo; Aging Action Center
                  (core/inventory_aging.py) -- price banding is the honest proxy for true days-on-lot
                  aging, since Vehicle has no acquisition/stock-date field in this system yet.
                </div>

                {actionMsg && <div className="text-xs px-3 py-2 rounded-lg bg-green-500/15 border border-green-500/40 text-green-300">{actionMsg}</div>}

                {agingLoading || !aging ? (
                  <div className="text-sm text-zinc-500">Loading…</div>
                ) : (
                  <>
                    <div className={cardClass}>
                      <div className="flex items-center justify-between mb-2">
                        <div className="text-xs font-brand uppercase tracking-wide text-zinc-500">Price Band</div>
                        <span className="text-xs px-1.5 py-0.5 rounded bg-brand-blue/30">{aging.vehicle.price_band}</span>
                      </div>
                      <div className="grid grid-cols-3 gap-2 text-xs">
                        <div><span className="text-zinc-500">Price</span><div>{money(aging.vehicle.price)}</div></div>
                        <div><span className="text-zinc-500">Cost</span><div>{money(aging.vehicle.cost)}</div></div>
                        <div><span className="text-zinc-500">Margin</span><div>{aging.vehicle.margin_pct ?? "—"}%</div></div>
                      </div>
                    </div>

                    <div className={cardClass}>
                      <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Price Reduction</div>
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <WorkField label="New (lower) price"><WorkInput
                          type="number"
                          value={newPrice}
                          onChange={(e) => setNewPrice(e.target.value)}
                          placeholder="New (lower) price…"
                          className={`w-36 rounded-md border px-2 py-1 text-xs ${textClass}`}
                        /></WorkField>
                        <WorkField label="Reason (optional)"><WorkInput
                          value={priceReason}
                          onChange={(e) => setPriceReason(e.target.value)}
                          placeholder="Reason (optional)"
                          className={`flex-1 rounded-md border px-2 py-1 text-xs ${textClass}`}
                        /></WorkField>
                        <WorkButton type="submit" variant="primary" disabled={busy} onClick={handleReducePrice} className="text-xs px-2.5 py-1 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50">Reduce Price</WorkButton>
                      </div>
                      {aging.price_history.length > 0 && (
                        <div className="mt-2 space-y-0.5">
                          {aging.price_history.slice(-5).reverse().map((h, i) => (
                            <div key={i} className="text-xs text-zinc-500">{fmt(h.updated_at)} — {money(h.old_price)} → {money(h.new_price)} by {h.updated_by}{h.reason ? ` (${h.reason})` : ""}</div>
                          ))}
                        </div>
                      )}
                    </div>

                    <div className={cardClass}>

                      <WorkField label="Review &amp; Assignment Actions"><WorkInput
                        value={actionNotes}
                        onChange={(e) => setActionNotes(e.target.value)}
                        placeholder="Notes (optional, applies to the next action clicked)"
                        className={`w-full rounded-md border px-2 py-1.5 text-xs mb-2 ${textClass}`}
                      /></WorkField>
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <WorkButton type="submit" disabled={busy} onClick={() => handleAgingAction("wholesale")} className="text-xs px-2.5 py-1 rounded bg-zinc-200/10 hover:bg-zinc-200/20 transition disabled:opacity-50">Request Wholesale Review</WorkButton>
                        <WorkButton type="submit" disabled={busy} onClick={() => handleAgingAction("manager")} className="text-xs px-2.5 py-1 rounded bg-zinc-200/10 hover:bg-zinc-200/20 transition disabled:opacity-50">Request Manager Review</WorkButton>
                        <WorkButton type="submit" disabled={busy} onClick={() => handleAgingAction("auction")} className="text-xs px-2.5 py-1 rounded bg-zinc-200/10 hover:bg-zinc-200/20 transition disabled:opacity-50">Request Auction Assignment</WorkButton>
                        <WorkButton type="submit" disabled={busy} onClick={() => handleAgingAction("marketing")} className="text-xs px-2.5 py-1 rounded bg-zinc-200/10 hover:bg-zinc-200/20 transition disabled:opacity-50">Create Marketing Tie-In</WorkButton>
                      </div>
                    </div>
                  </>
                )}
              </>
            )}

            {tab === "vin" && (
              <>
                <div className="text-xs text-zinc-600 italic px-1">
                  NXTDeal VIN Intelligence (core/vin_decoder.py) -- two real, honestly distinct
                  sources: offline decode (format / check digit / WMI / model year, per FMVSS 115
                  / ISO 3779) is always deterministic; a live NHTSA vPIC lookup (Model / Trim /
                  Engine / Body Style) needs real outbound network access this environment may
                  not have -- a missing live field is reported honestly, never guessed at.
                  Decoding only ever backfills a currently-blank Vehicle field, never overwrites
                  data already on file.
                </div>

                {vinMsg && <div className="text-xs px-3 py-2 rounded-lg bg-green-500/15 border border-green-500/40 text-green-300">{vinMsg}</div>}

                {vinLoading ? (
                  <div className="text-sm text-zinc-500">Loading…</div>
                ) : !vinRecord ? (
                  <div className={cardClass}>
                    <div className="text-xs text-zinc-500 mb-2">{vinNote || "This vehicle has not been decoded yet."}</div>
                    <WorkButton type="submit" variant="primary" disabled={vinDecoding} onClick={handleDecodeVin} className="text-xs px-2.5 py-1 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50">
                      {vinDecoding ? "Decoding…" : `Decode ${data.vin || "VIN"}`}
                    </WorkButton>
                  </div>
                ) : (
                  <>
                    <div className={cardClass}>
                      <div className="flex items-center justify-between mb-2">
                        <div className="text-xs font-brand uppercase tracking-wide text-zinc-500">VIN Validation</div>
                        <span
                          className={`text-xs px-1.5 py-0.5 rounded ${
                            vinRecord.check_digit_valid === true
                              ? "bg-green-950/40 text-green-300"
                              : vinRecord.check_digit_valid === false
                              ? "bg-red-950/40 text-red-300"
                              : "bg-zinc-800 text-zinc-400"
                          }`}
                        >
                          {vinRecord.check_digit_valid === true
                            ? "Check digit valid"
                            : vinRecord.check_digit_valid === false
                            ? "Check digit invalid / non-standard VIN"
                            : "Check digit not evaluated"}
                        </span>
                      </div>
                      <div className="grid grid-cols-4 gap-2 text-xs">
                        {(Object.keys(vinRecord.resolved) as (keyof VinDecodeResolved)[]).map((field) => (
                          <div key={field}>
                            <div className="text-zinc-500 capitalize">{field.replace(/_/g, " ")}</div>
                            <div>{vinRecord.resolved[field] ?? "—"}</div>
                            <div className="text-xs text-zinc-600">{vinRecord.basis[field]}</div>
                          </div>
                        ))}
                      </div>
                    </div>

                    {vinRecord.gaps.length > 0 && (
                      <div className={cardClass}>
                        <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1">Honest Gaps</div>
                        <ul className="text-xs text-zinc-400 list-disc list-inside space-y-0.5">
                          {vinRecord.gaps.map((g) => (
                            <li key={g}>{g}</li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {vinRecord.live_error && (
                      <div className="text-xs text-zinc-600 italic px-1">Live NHTSA lookup: {vinRecord.live_error}</div>
                    )}

                    <div className={cardClass}>
                      <div className="flex items-center justify-between gap-2 flex-wrap">
                        <div className="text-xs text-zinc-600">
                          Decoded {fmt(vinRecord.decoded_at)} by {vinRecord.decoded_by}
                          {vinRecord.backfilled_fields.length > 0 && ` — backfilled: ${vinRecord.backfilled_fields.join(", ")}`}
                        </div>
                        <WorkButton type="submit" disabled={vinDecoding} onClick={handleDecodeVin} className="text-xs px-2.5 py-1 rounded bg-zinc-200/10 hover:bg-zinc-200/20 transition disabled:opacity-50">
                          {vinDecoding ? "Re-decoding…" : "Re-decode / Apply Again"}
                        </WorkButton>
                      </div>
                    </div>
                  </>
                )}
              </>
            )}

            {tab === "messages" && (
              <div className={cardClass}>
                <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Internal Messaging</div>
                <div className="space-y-1.5 mb-2 max-h-64 overflow-y-auto">
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
            )}
          </>
        )}
      </div>
    </div>
  );
}

export function inventoryStageNames(stages: string[], board: LifecycleBoardData) {
  return Array.from(new Set([...stages, ...Object.keys(board)]));
}

export function InventoryWorkspaceBoard({ theme, compact = false, onBoardUpdated }: { theme: Theme; compact?: boolean; onBoardUpdated?: (board: LifecycleBoardData) => void }) {
  const [catalog, setCatalog] = useState<LifecycleCatalog | null>(null);
  const [board, setBoard] = useState<LifecycleBoardData>({});
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [searchResults, setSearchResults] = useState<InventorySearchResults | null>(null);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);

  const [stageFilter, setStageFilter] = useState("");
  const [page, setPage] = useState(0);
  const [pageSize,setPageSize]=useState(25);
  const [loadError, setLoadError] = useState("");

  function refresh() {
    setLoadError("");
    setLoading(true);
    Promise.all([getLifecycleCatalog(), getLifecycleBoard()])
      .then(([c, b]) => {
        setCatalog(c);
        setBoard(b);
        onBoardUpdated?.(b);
      })
      .catch(e => setLoadError(e instanceof Error ? e.message : "Inventory could not load."))
      .finally(() => setLoading(false));
  }

  useEffect(refresh, []);

  async function handleSearch() {
    if (!query.trim()) {
      setSearchResults(null);
      return;
    }
    setSearching(true);
    setSearchError(null);
    try {
      const r = await searchInventory(query.trim());
      setSearchResults(r);
      setPage(0);
    } catch (e) {
      setSearchError((e as Error).message);
    } finally {
      setSearching(false);
    }
  }

  const activeCount = catalog
    ? catalog.stages.filter((s) => s !== "Sold" && s !== "Delivered" && s !== "Front Line Ready").reduce((sum, s) => sum + (board[s]?.length || 0), 0)
    : 0;
  const frontLineCount = board["Front Line Ready"]?.length || 0;
  const soldCount = (board["Sold"]?.length || 0) + (board["Delivered"]?.length || 0);
  const totalCount = Object.values(board).reduce((sum, v) => sum + v.length, 0);

  const searchVehicleIds = useMemo(
    () => (searchResults?.results || []).map((r) => r.id),
    [searchResults]
  );

  const stageNames = inventoryStageNames(catalog?.stages ?? [], board);
  const stageVehicles = stageNames.filter(stage=>!stageFilter || stage===stageFilter).flatMap(stage=>(board[stage]??[]).map(vehicle=>({...vehicle, stage})));
  const count = searchResults ? searchVehicleIds.length : stageVehicles.length;
  const pages = Math.max(1, Math.ceil(count/pageSize));
  const currentPage = Math.min(page,pages-1);
  if(selected && catalog) return <VehicleDetailModal theme={theme} vehicleId={selected} catalog={catalog} onClose={()=>setSelected(null)} onChanged={refresh}/>;

  return (
    <div className={tc(theme, "work-inventory-board", "work-inventory-board")}>
      {!compact && <div className={tc(theme, "work-inventory-stats", "work-inventory-stats")}>
        <Kpi theme={theme} label="Total Vehicles" value={totalCount} color={RIBBON[0]} />
        <Kpi theme={theme} label="In Recon Pipeline" value={activeCount} color={RIBBON[1]} />
        <Kpi theme={theme} label="Front Line Ready" value={frontLineCount} color={RIBBON[2]} />
        <Kpi theme={theme} label="Sold / Delivered" value={soldCount} color={RIBBON[3]} />
      </div>}

      <div className={tc(theme, "flex items-center gap-2 px-4 py-3 border-b border-zinc-800", "flex items-center gap-2 px-4 py-3 border-b border-zinc-200")}>
        <WorkField label="Search by VIN, stock number, VEH- id, year/make/model"><WorkInput
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") handleSearch(); }}
          placeholder="Search by VIN, stock number, VEH- id, year/make/model…"
          className={`flex-1 rounded-md border px-3 py-1.5 text-sm ${tc(theme, "bg-zinc-900 border-zinc-700 text-white placeholder:text-zinc-600", "bg-white border-zinc-300 text-black placeholder:text-zinc-400")}`}
        /></WorkField>
        <WorkButton type="submit" variant="primary" disabled={searching} onClick={handleSearch} className="text-xs px-3 py-1.5 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50">
          {searching ? "Searching…" : "Search"}
        </WorkButton>
        {searchResults && (
          <WorkButton type="submit" onClick={() => { setSearchResults(null); setQuery(""); }} className="text-xs px-2.5 py-1.5 rounded bg-zinc-200/10 text-zinc-400 hover:text-white transition">
            Clear
          </WorkButton>
        )}
      </div>

      {loadError && <div role="alert" className="p-4">{loadError}<WorkButton type="submit" onClick={refresh} className="min-h-11 underline px-3">Retry inventory</WorkButton></div>}
      {searchError && <div className="mx-4 mt-2 text-xs px-3 py-2 rounded-lg bg-red-500/15 border border-red-500/40 text-red-300">{searchError}</div>}

      {searchResults ? (
        <div className="flex-1 overflow-y-auto p-4">
          <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">
            {searchResults.count} result{searchResults.count === 1 ? "" : "s"} for &ldquo;{searchResults.query}&rdquo;
          </div>
          <RecordTable label="Vehicle search results" paginate={false}><thead><tr><th>Vehicle</th><th>Stock / VIN</th><th>Price</th><th>Next step</th></tr></thead><tbody>
            {searchVehicleIds.slice(currentPage*pageSize,currentPage*pageSize+pageSize).map(id=>{
              const a=searchResults.results.find(x=>x.id===id)!.attributes;
              return <tr key={id}><td><strong>{String(a.Year||"")} {String(a.Make||"")} {String(a.Model||"")}</strong></td><td>{String(a.StockNumber||id)}<span className="work-record-meta">{String(a.VIN||"")}</span></td><td>{money(a.Price as string|number)}</td><td><WorkButton onClick={()=>setSelected(id)}>Open vehicle</WorkButton></td></tr>;
            })}
          </tbody></RecordTable>
          {searchResults.count === 0 && <div className="text-sm text-zinc-500">No vehicles matched.</div>}
        </div>
      ) : (
        <section aria-label="Inventory work queue" className="p-4 space-y-3">
          <p>Choose a stage, open a vehicle, then review reconditioning, vendor work and ownership before changing its status.</p>
          <label className="block">Vehicle stage<WorkSelect className="block min-h-11 rounded border px-3 bg-inherit" value={stageFilter} onChange={e=>{setStageFilter(e.target.value);setPage(0);}}><option value="">All stages ({totalCount})</option>{stageNames.map(stage=><option key={stage} value={stage}>{stage} ({board[stage]?.length??0})</option>)}</WorkSelect></label>
          {loading ? <p role="status">Loading inventory…</p> : <RecordTable label="Inventory vehicles" paginate={false}><thead><tr><th>Vehicle</th><th>Stock</th><th>Price</th><th>Stage</th><th>Next step</th></tr></thead><tbody>{stageVehicles.slice(currentPage*pageSize,currentPage*pageSize+pageSize).map(v=><tr key={v.vehicle_id}><td><strong>{v.year} {v.make} {v.model}</strong></td><td>{v.stock_number || v.vehicle_id}</td><td>{money(v.price)}</td><td>{v.stage}</td><td><WorkButton onClick={()=>setSelected(v.vehicle_id)}>Open vehicle →</WorkButton></td></tr>)}</tbody></RecordTable>}
          {!loading && !loadError && !count && <p>No vehicles in this stage. Choose another stage to continue.</p>}
        </section>
      )}

      <CollectionPagination label="Vehicles" total={count} page={currentPage} pageSize={pageSize} onPageChange={setPage} onPageSizeChange={setPageSize}/>
    </div>
  );
}
