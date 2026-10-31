"use client";
import { WorkInput, WorkSelect, WorkButton } from "./WorkspaceUi";
import { WorkField } from "./WorkField";

// Operations' 4 job-workflow-catalog buttons get real bespoke tabs (session 106
// follow-up #9, "keep going" autonomous continuation, the ninth and final slice
// of Operations' rebuild -- same "working process, not just a list" treatment
// session 103 gave Sales' workflow tabs). One shared panel covers all 20 named
// tabs across Vehicle Intake & Recon, Compliance & Deal Jacket, Inventory
// Reconciliation, and Interdepartmental SLA -- reusing this session's own
// already-built engines directly (vehicle_lifecycle, document_workflows,
// inventory_aging, operations_tasks, operations_alerts, operations_scheduling,
// plus lib/deals.ts) rather than duplicating any of their logic. Three tabs are
// honest gaps (Registration & Insurance, Parts Allocation, Financial Routing) --
// no entity model for any of the three exists anywhere in this codebase, said so
// rather than faked.

import { useEffect, useState } from "react";
import {
  getVehicleLifecycle,
  updateReconItem,
  updateLifecycleStatus,
  assignVendor,
  type VehicleLifecycle,
  type ReconItem,
  type LifecycleStage,
} from "@/lib/vehicleLifecycle";
import { getDeal, type Deal } from "@/lib/deals";
import {
  getDealJacketStatus,
  getDocumentPacket,
  approveDocument,
  rejectDocument,
  requestDocument,
  type CompletenessCheck,
} from "@/lib/documentWorkflows";
import {
  getAgingBoard,
  reduceVehiclePrice,
  requestWholesaleReview,
  type AgingBoard,
} from "@/lib/inventoryAging";
import {
  listOperationsTasks,
  createOperationsTask,
  closeOperationsTask,
  type OperationsTask,
} from "@/lib/operationsTasks";
import { getAlertFeed, type Alert } from "@/lib/operationsAlerts";
import { getReconSchedule, type ReconSchedule } from "@/lib/operationsScheduling";

export type OperationsWorkflowSection =
  | "stock_source" | "inspection" | "repair_recon" | "media_merchandising" | "frontline_readiness"
  | "customer_verification" | "contract_audit" | "lender_requirements" | "registration_insurance" | "compliance_approval"
  | "floorplan_ledger" | "lot_audit" | "aging_analysis" | "pricing_adjustments" | "reconciliation_review"
  | "request_intake" | "parts_allocation" | "service_scheduling" | "financial_routing" | "completion_verification";

const VEHICLE_SECTIONS = new Set<OperationsWorkflowSection>([
  "stock_source", "inspection", "repair_recon", "media_merchandising", "frontline_readiness",
  "floorplan_ledger", "lot_audit", "aging_analysis", "pricing_adjustments", "reconciliation_review",
]);
const DEAL_SECTIONS = new Set<OperationsWorkflowSection>([
  "customer_verification", "contract_audit", "lender_requirements", "registration_insurance", "compliance_approval",
]);

function money(v: string | number | null | undefined): string {
  if (v === null || v === undefined || v === "") return "—";
  const n = Number(v);
  return Number.isNaN(n) ? String(v) : `$${n.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

function GapNote({ children }: { children: React.ReactNode }) {
  return (
    <div className="p-3 rounded-lg border border-dashed border-zinc-800 bg-zinc-900/40">
      <p className="text-xs text-zinc-500 leading-relaxed">{children}</p>
    </div>
  );
}

function NoEntity({ label }: { label: string }) {
  return (
    <div className="p-4 rounded-lg border border-dashed border-zinc-800 bg-zinc-900/40">
      <p className="text-xs text-zinc-500 leading-relaxed">
        This tab works against a specific {label}. Start or track an instance of this
        workflow from the <span className="text-zinc-300">Overview</span> tab with a real
        ID to see it here.
      </p>
    </div>
  );
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800">
      <div className="text-xs font-medium text-zinc-200 mb-2">{title}</div>
      {children}
    </div>
  );
}

// --- Vehicle-typed tabs (operations.recon, operations.inventory_reconciliation) ---

function VehiclePanel({ vehicleId, section }: { vehicleId: string; section: OperationsWorkflowSection }) {
  const [lifecycle, setLifecycle] = useState<VehicleLifecycle | null>(null);
  const [aging, setAging] = useState<AgingBoard | null>(null);
  const [alertFeed, setAlertFeed] = useState<Alert[] | null>(null);
  const [reconciliationTasks, setReconciliationTasks] = useState<OperationsTask[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [vendorType, setVendorType] = useState("body_shop");
  const [vendorName, setVendorName] = useState("");
  const [newPrice, setNewPrice] = useState("");

  function refresh() {
    setLoading(true);
    Promise.all([
      getVehicleLifecycle(vehicleId),
      section === "aging_analysis" || section === "pricing_adjustments" ? getAgingBoard() : Promise.resolve(null),
      section === "lot_audit" ? getAlertFeed() : Promise.resolve(null),
      section === "reconciliation_review" ? listOperationsTasks({}) : Promise.resolve(null),
    ])
      .then(([lc, ab, feed, tasks]) => {
        setLifecycle(lc);
        if (ab) setAging(ab);
        if (feed) setAlertFeed(feed.alerts);
        if (tasks) setReconciliationTasks(tasks.tasks.filter((t) => t.task_type === "confirm_lot_audit"));
        setError(null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Unable to load this vehicle."))
      .finally(() => setLoading(false));
  }

  useEffect(refresh, [vehicleId, section]);

  async function withBusy(fn: () => Promise<VehicleLifecycle>, successMsg?: string) {
    setBusy(true);
    setError(null);
    try {
      const lc = await fn();
      setLifecycle(lc);
      if (successMsg) setMessage(successMsg);
    } catch (e) {
      setError(e instanceof Error ? e.message : "That didn't go through.");
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <div className="text-xs text-zinc-600">Loading…</div>;
  if (!lifecycle) return <div className="text-xs text-zinc-600">{error || "Vehicle not found."}</div>;

  return (
    <div className="mb-5">
      {error && <div className="text-xs text-red-400 mb-2">{error}</div>}
      {message && <div className="text-xs text-emerald-400 mb-2">{message}</div>}

      {section === "stock_source" && (
        <Card title="Stock Assignment & Source">
          <div className="text-xs text-zinc-300 space-y-1">
            <div>{lifecycle.year} {lifecycle.make} {lifecycle.model} {lifecycle.trim} — VIN {lifecycle.vin}</div>
            <div>Stock #{lifecycle.stock_number} · Lot {lifecycle.acquisition.lot || "—"} · Cost {money(lifecycle.acquisition.cost)}</div>
            <div>Condition: {lifecycle.acquisition.condition || "—"}</div>
            {lifecycle.acquisition.auction_data ? (
              <div className="mt-2 pt-2 border-t border-zinc-800">
                Auction: {lifecycle.acquisition.auction_data.auction_house} · Bid {money(lifecycle.acquisition.auction_data.bid_amount)} on {lifecycle.acquisition.auction_data.purchase_date}
              </div>
            ) : (
              <div className="mt-2 pt-2 border-t border-zinc-800 text-zinc-600">{lifecycle.acquisition.not_yet_tracked}</div>
            )}
          </div>
        </Card>
      )}

      {section === "inspection" && (
        <Card title="Inspection & Condition Report">
          <label className="flex items-center gap-2 text-xs text-zinc-300">
            <WorkInput
              type="checkbox"
              checked={lifecycle.recon_checklist.inspection.complete}
              disabled={busy}
              onChange={(e) => withBusy(() => updateReconItem(vehicleId, "inspection", e.target.checked), "Inspection updated.")}
            />
            Inspection complete
          </label>
          <div className="text-xs text-zinc-500 mt-1">Condition on file: {lifecycle.acquisition.condition || "—"}</div>
        </Card>
      )}

      {section === "repair_recon" && (
        <div className="space-y-2">
          <Card title="Repair & Recon Checklist">
            {(Object.keys(lifecycle.recon_checklist) as ReconItem[]).map((item) => (
              <label key={item} className="flex items-center gap-2 text-xs text-zinc-300 mb-1">
                <WorkInput
                  type="checkbox"
                  checked={lifecycle.recon_checklist[item].complete}
                  disabled={busy}
                  onChange={(e) => withBusy(() => updateReconItem(vehicleId, item, e.target.checked), `${item} updated.`)}
                />
                {item.replace(/_/g, " ")}
              </label>
            ))}
          </Card>
          <Card title="Vendor Assignments">
            {lifecycle.vendor_assignments.length === 0 ? (
              <div className="text-xs text-zinc-600 mb-2">No vendors assigned yet.</div>
            ) : (
              <div className="space-y-1 mb-2">
                {lifecycle.vendor_assignments.map((v) => (
                  <div key={v.id} className="text-xs text-zinc-400">{v.vendor_type} — {v.vendor_name} ({v.status})</div>
                ))}
              </div>
            )}
            <div className="flex items-center gap-1.5">
              <WorkField label="Vendor Type"><WorkSelect value={vendorType} onChange={(e) => setVendorType(e.target.value)} className="rounded-md border border-zinc-700 bg-zinc-950 px-2 py-1 text-xs text-white">
                <option value="body_shop">Body Shop</option>
                <option value="detail">Detail</option>
                <option value="paint">Paint</option>
                <option value="glass">Glass</option>
                <option value="other">Other</option>
              </WorkSelect></WorkField>
              <WorkField label="Vendor name"><WorkInput value={vendorName} onChange={(e) => setVendorName(e.target.value)} placeholder="Vendor name…" className="flex-1 rounded-md border border-zinc-700 bg-zinc-950 px-2 py-1 text-xs text-white placeholder:text-zinc-600" /></WorkField>
              <WorkButton type="submit" variant="primary"
                disabled={busy || !vendorName.trim()}
                onClick={() => { withBusy(() => assignVendor(vehicleId, vendorType as never, vendorName), "Vendor assigned."); setVendorName(""); }}
                className="text-xs px-2.5 py-1.5 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50"
              >
                Assign
              </WorkButton>
            </div>
          </Card>
        </div>
      )}

      {section === "media_merchandising" && (
        <Card title="Media & Merchandising">
          <label className="flex items-center gap-2 text-xs text-zinc-300">
            <WorkInput
              type="checkbox"
              checked={lifecycle.recon_checklist.photos.complete}
              disabled={busy}
              onChange={(e) => withBusy(() => updateReconItem(vehicleId, "photos", e.target.checked), "Photos flag updated.")}
            />
            Photos taken
          </label>
          <div className="text-xs text-zinc-600 mt-2">
            No Image entities exist anywhere in this graph (confirmed session 63/session 106) -- this is a completion flag, not a real photo count or gallery.
          </div>
        </Card>
      )}

      {section === "frontline_readiness" && (
        <Card title="Frontline Readiness">
          <div className="text-xs text-zinc-300 mb-2">Current stage: <span className="text-zinc-100">{lifecycle.lifecycle_status}</span></div>
          {lifecycle.status_history.length > 0 && (
            <div className="text-xs text-zinc-600 mb-2">
              {lifecycle.status_history.slice(-3).map((h, i) => (
                <div key={i}>{h.status} — {new Date(h.at).toLocaleString()} by {h.by}</div>
              ))}
            </div>
          )}
          <WorkButton type="submit"
            disabled={busy}
            onClick={() => withBusy(() => updateLifecycleStatus(vehicleId, "Front Line Ready" as LifecycleStage), "Marked Front Line Ready.")}
            className="text-xs px-2.5 py-1.5 rounded bg-green-800 text-white font-medium hover:opacity-90 transition disabled:opacity-50"
          >
            Mark Front Line Ready
          </WorkButton>
        </Card>
      )}

      {section === "floorplan_ledger" && (
        <Card title="Floorplan Ledger">
          <div className="text-xs text-zinc-300">Floorplan principal (HEURISTIC: Vehicle.Cost): {money(lifecycle.acquisition.cost)}</div>
          <div className="text-xs text-zinc-600 mt-2">
            No real floorplan/amortization ledger exists in this codebase -- unsold Vehicle.Cost is the same proxy `core/finance_menu.py`'s Floorplan item already uses.
          </div>
        </Card>
      )}

      {section === "lot_audit" && (
        <Card title="Physical Lot Audit">
          {(() => {
            const hit = alertFeed?.find((a) => a.alert_type === "ownership_mismatch" && a.linked_entity_id === vehicleId);
            return hit ? (
              <div className="text-xs text-amber-300">Flagged: {hit.detail}</div>
            ) : (
              <div className="text-xs text-emerald-400">No ownership mismatch on file for this vehicle.</div>
            );
          })()}
          <div className="text-xs text-zinc-600 mt-2">
            {alertFeed ? alertFeed.filter((a) => a.alert_type === "ownership_mismatch").length : 0} real ownership mismatches open dealership-wide.
          </div>
        </Card>
      )}

      {section === "aging_analysis" && aging && (
        <Card title="Aging Analysis">
          <div className="text-xs text-zinc-300">Price band: <span className="text-zinc-100">{
            Object.entries(aging.by_price_band).find(([, vs]) => vs.some((v) => v.vehicle_id === vehicleId))?.[0] || "—"
          }</span></div>
          <div className="text-xs text-zinc-600 mt-2">{aging.note}</div>
        </Card>
      )}

      {section === "pricing_adjustments" && (
        <Card title="Pricing Adjustments">
          <div className="text-xs text-zinc-300 mb-2">Current price: {money(lifecycle.price)}</div>
          <div className="flex items-center gap-1.5">
            <WorkField label="New price"><WorkInput type="number" value={newPrice} onChange={(e) => setNewPrice(e.target.value)} placeholder="New price…" className="w-28 rounded-md border border-zinc-700 bg-zinc-950 px-2 py-1 text-xs text-white placeholder:text-zinc-600" /></WorkField>
            <WorkButton type="submit" variant="primary"
              disabled={busy || !newPrice}
              onClick={async () => {
                setBusy(true); setError(null);
                try { await reduceVehiclePrice(vehicleId, Number(newPrice), "Reduced from Reconciliation workflow"); setMessage("Price updated."); setNewPrice(""); refresh(); }
                catch (e) { setError(e instanceof Error ? e.message : "That didn't go through."); }
                finally { setBusy(false); }
              }}
              className="text-xs px-2.5 py-1.5 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50"
            >
              Reduce Price
            </WorkButton>
            <WorkButton type="submit"
              disabled={busy}
              onClick={async () => {
                setBusy(true); setError(null);
                try { await requestWholesaleReview(vehicleId); setMessage("Wholesale review requested."); }
                catch (e) { setError(e instanceof Error ? e.message : "That didn't go through."); }
                finally { setBusy(false); }
              }}
              className="text-xs px-2.5 py-1.5 rounded bg-zinc-800 text-zinc-200 font-medium hover:opacity-90 transition disabled:opacity-50"
            >
              Request Wholesale Review
            </WorkButton>
          </div>
        </Card>
      )}

      {section === "reconciliation_review" && (
        <Card title="Reconciliation Review">
          {(() => {
            const mine = reconciliationTasks?.filter((t) => t.linked_entity_id === vehicleId) || [];
            if (mine.length === 0) return <div className="text-xs text-zinc-600">No lot-audit task on file for this vehicle.</div>;
            return mine.map((t) => (
              <div key={t.id} className="text-xs text-zinc-300 mb-1.5">
                {t.detail} — <span className="text-zinc-100">{t.status}</span>
                {t.status !== "closed" && (
                  <WorkButton type="submit"
                    disabled={busy}
                    onClick={async () => {
                      setBusy(true);
                      try { await closeOperationsTask(t.id, "Confirmed during reconciliation review"); refresh(); }
                      finally { setBusy(false); }
                    }}
                    className="ml-2 text-xs px-2 py-0.5 rounded bg-green-800 text-white hover:opacity-90 transition"
                  >
                    Confirm & Close
                  </WorkButton>
                )}
              </div>
            ));
          })()}
        </Card>
      )}
    </div>
  );
}

// --- Deal-typed tabs (operations.deal_jacket_audit) ---

function DealAuditPanel({ dealId, section }: { dealId: string; section: OperationsWorkflowSection }) {
  const [deal, setDeal] = useState<Deal | null>(null);
  const [jacket, setJacket] = useState<CompletenessCheck | null>(null);
  const [customerPacket, setCustomerPacket] = useState<CompletenessCheck | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [rejectReason, setRejectReason] = useState<Record<string, string>>({});

  function refresh() {
    setLoading(true);
    getDeal(dealId)
      .then((d) => {
        setDeal(d);
        const jobs: Promise<unknown>[] = [getDealJacketStatus(dealId).then(setJacket)];
        if (section === "customer_verification" && d.customer_id) {
          jobs.push(getDocumentPacket("Customer", d.customer_id).then(setCustomerPacket));
        }
        return Promise.all(jobs);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Unable to load this deal."))
      .finally(() => setLoading(false));
  }

  useEffect(refresh, [dealId, section]);

  if (loading) return <div className="text-xs text-zinc-600">Loading…</div>;
  if (!deal) return <div className="text-xs text-zinc-600">{error || "Deal not found."}</div>;

  return (
    <div className="mb-5">
      {error && <div className="text-xs text-red-400 mb-2">{error}</div>}
      {message && <div className="text-xs text-emerald-400 mb-2">{message}</div>}

      {section === "customer_verification" && (
        <Card title="Customer Verification">
          <div className="text-xs text-zinc-300 mb-1">{deal.customer?.name || deal.customer_id}</div>
          {customerPacket ? (
            <div className="text-xs text-zinc-400">
              Compliance File on file: {customerPacket.is_complete ? <span className="text-emerald-400">yes</span> : <span className="text-amber-400">missing</span>}
            </div>
          ) : (
            <div className="text-xs text-zinc-600">Loading customer document packet…</div>
          )}
        </Card>
      )}

      {(section === "contract_audit" || section === "compliance_approval") && jacket && (
        <Card title={section === "contract_audit" ? "Contract Audit" : "Compliance Approval"}>
          <div className="text-xs text-zinc-300 mb-1.5">
            {jacket.is_complete ? <span className="text-emerald-400">Deal Jacket complete</span> : <span className="text-amber-400">Missing: {jacket.missing_types.join(", ")}</span>}
          </div>
          <div className="space-y-1.5">
            {jacket.documents.map((d) => (
              <div key={d.id} className="text-xs flex items-center justify-between gap-2">
                <span>{d.document_type} — {d.approval_status}</span>
                {section === "compliance_approval" && d.approval_status === "pending" && (
                  <span className="flex items-center gap-1">
                    <WorkButton type="submit"
                      disabled={busy}
                      onClick={async () => { setBusy(true); try { await approveDocument(d.id); refresh(); } finally { setBusy(false); } }}
                      className="text-xs px-2 py-0.5 rounded bg-green-800 text-white hover:opacity-90 transition"
                    >
                      Approve
                    </WorkButton>
                    <WorkField label="Reason"><WorkInput
                      value={rejectReason[d.id] || ""}
                      onChange={(e) => setRejectReason((p) => ({ ...p, [d.id]: e.target.value }))}
                      placeholder="Reason…"
                      className="w-24 rounded border border-zinc-700 bg-zinc-950 px-1.5 py-0.5 text-xs text-white placeholder:text-zinc-600"
                    /></WorkField>
                    <WorkButton type="submit" variant="danger"
                      disabled={busy || !rejectReason[d.id]}
                      onClick={async () => { setBusy(true); try { await rejectDocument(d.id, rejectReason[d.id]); refresh(); } finally { setBusy(false); } }}
                      className="text-xs px-2 py-0.5 rounded bg-red-800 text-white hover:opacity-90 transition disabled:opacity-50"
                    >
                      Reject
                    </WorkButton>
                  </span>
                )}
              </div>
            ))}
          </div>
          {jacket.missing_types.map((t) => (
            <WorkButton type="submit" variant="primary"
              key={t}
              disabled={busy}
              onClick={async () => { setBusy(true); try { await requestDocument("Deal", dealId, t); setMessage(`${t} requested.`); refresh(); } finally { setBusy(false); } }}
              className="mt-2 mr-1.5 text-xs px-2.5 py-1 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition"
            >
              Request {t}
            </WorkButton>
          ))}
        </Card>
      )}

      {section === "lender_requirements" && (
        <Card title="Lender Requirements">
          <div className="text-xs text-zinc-300 space-y-1">
            <div>Financing type: {deal.financing_type}</div>
            <div>Status: {deal.financing_status}</div>
            {deal.financing_terms && (
              <div className="text-zinc-500">Terms on file: APR {deal.financing_terms.apr ?? "—"}, Term {deal.financing_terms.term_months ?? "—"}mo</div>
            )}
          </div>
        </Card>
      )}

      {section === "registration_insurance" && (
        <GapNote>
          No Registration or Insurance entity exists anywhere in this codebase (confirmed by grep) --
          this is an honest gap, not a fabricated status. The Deal Jacket/Documents vault
          (Contract Audit tab) is the closest real paperwork-completeness signal available today.
        </GapNote>
      )}
    </div>
  );
}

// --- Interdepartmental SLA (operations.interdept_sla, entity optional) ---

function InterdeptPanel({ entityId, section }: { entityId: string | null; section: OperationsWorkflowSection }) {
  const [detail, setDetail] = useState("");
  const [ownerBucket, setOwnerBucket] = useState("Service Manager");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [recon, setRecon] = useState<ReconSchedule | null>(null);
  const [closedTasks, setClosedTasks] = useState<OperationsTask[] | null>(null);

  useEffect(() => {
    if (section === "service_scheduling") getReconSchedule().then(setRecon).catch(() => {});
    if (section === "completion_verification") {
      listOperationsTasks({ status: "closed" }).then((r) => {
        setClosedTasks(entityId ? r.tasks.filter((t) => t.linked_entity_id === entityId) : r.tasks.slice(0, 10));
      }).catch(() => {});
    }
  }, [section, entityId]);

  if (section === "parts_allocation") {
    return (
      <GapNote>
        No parts-allocation/request entity exists in this codebase -- Part and PartSale
        (session 35) track inventory and completed sales, but nothing models a
        cross-department parts REQUEST tied to an interdepartmental job. Honest gap, not
        a fabricated queue.
      </GapNote>
    );
  }

  if (section === "financial_routing") {
    return (
      <GapNote>
        No cross-department billing/routing entity exists in this codebase -- there is no
        way to track which department gets billed for an interdepartmental job today.
        Honest gap.
      </GapNote>
    );
  }

  if (section === "request_intake") {
    return (
      <div className="mb-5">
        {error && <div className="text-xs text-red-400 mb-2">{error}</div>}
        {message && <div className="text-xs text-emerald-400 mb-2">{message}</div>}
        <Card title="Request Intake">
          <div className="space-y-1.5">
            <WorkField label="What does the requesting department need?"><WorkInput value={detail} onChange={(e) => setDetail(e.target.value)} placeholder="What does the requesting department need?" className="w-full rounded-md border border-zinc-700 bg-zinc-950 px-2 py-1.5 text-xs text-white placeholder:text-zinc-600" /></WorkField>
            <WorkField label="Responsible team"><WorkSelect value={ownerBucket} onChange={(e) => setOwnerBucket(e.target.value)} className="rounded-md border border-zinc-700 bg-zinc-950 px-2 py-1 text-xs text-white">
              <option>Service Manager</option>
              <option>Inventory Manager</option>
              <option>Title Clerk</option>
              <option>Lot Manager</option>
              <option>Accounting</option>
            </WorkSelect></WorkField>
            <WorkButton type="submit" variant="primary"
              disabled={busy || !detail.trim()}
              onClick={async () => {
                setBusy(true); setError(null);
                try {
                  await createOperationsTask({ task_type: "custom", detail, owner_bucket: ownerBucket as never, linked_entity_id: entityId });
                  setMessage("Request logged as a real Operations Task.");
                  setDetail("");
                } catch (e) { setError(e instanceof Error ? e.message : "That didn't go through."); }
                finally { setBusy(false); }
              }}
              className="text-xs px-2.5 py-1.5 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50"
            >
              Log Request
            </WorkButton>
          </div>
          <div className="text-xs text-zinc-600 mt-2">Reuses the real Universal Operations Work Queue -- see the Tasks item on the Top Menu to track it through to close.</div>
        </Card>
      </div>
    );
  }

  if (section === "service_scheduling") {
    return (
      <Card title="Service Scheduling">
        <div className="text-xs text-zinc-300">{recon ? `${recon.used_unsold_count} used unsold units in the real Operations<->Service recon queue.` : "Loading…"}</div>
        <div className="text-xs text-zinc-600 mt-2">Reuses Scheduling's real recon board -- the closest genuine Operations/Service coordination data this codebase has.</div>
      </Card>
    );
  }

  if (section === "completion_verification") {
    return (
      <Card title="Completion Verification">
        {closedTasks && closedTasks.length > 0 ? (
          closedTasks.map((t) => (
            <div key={t.id} className="text-xs text-zinc-400 mb-1">{t.detail} — closed {t.closed_at ? new Date(t.closed_at).toLocaleDateString() : ""}</div>
          ))
        ) : (
          <div className="text-xs text-zinc-600">No closed tasks {entityId ? "for this entity" : "yet"}.</div>
        )}
      </Card>
    );
  }

  return null;
}

export function OperationsWorkflowPanel({
  workflowKey,
  entityId,
  section,
}: {
  workflowKey: string;
  entityId: string | null;
  section: OperationsWorkflowSection;
}) {
  if (workflowKey === "operations.interdept_sla") {
    return <InterdeptPanel entityId={entityId} section={section} />;
  }

  if (VEHICLE_SECTIONS.has(section)) {
    if (!entityId) return <NoEntity label="Vehicle (VIN)" />;
    return <VehiclePanel vehicleId={entityId} section={section} />;
  }

  if (DEAL_SECTIONS.has(section)) {
    if (!entityId) return <NoEntity label="Deal" />;
    return <DealAuditPanel dealId={entityId} section={section} />;
  }

  return null;
}
