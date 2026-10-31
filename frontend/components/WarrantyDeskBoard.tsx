"use client";
import { WorkButton, WorkInput, WorkTextarea, WorkSelect , WorkStat} from "./WorkspaceUi";
import {CollectionPagination} from "./CollectionPagination";
import { formatCalendarDate } from "@/lib/calendarDate";
import { WorkField } from "./WorkField";

// Service department's "Warranty" item, sixth slice of Service's rebuild --
// Warranty Eligibility Check, a real Submission Workflow (draft -> submitted
// -> approved/rejected -> paid), a Rejected Claims Queue, and Recall
// Management (real per-vehicle recall-completion tracking).
import { PRODUCT_ACCENT_COLORS } from "@/lib/productTheme";
import { useEffect, useRef, useState } from "react";
import {
  getClaimsQueue,
  getRejectedClaims,
  getRecallManagementQueue,
  submitWarrantyClaim,
  recordWarrantyDecision,
  recordWarrantyPayment,
  markRecallCompleted,
  type ClaimsQueue,
  type RecallManagementQueue,
  type WarrantyClaim,
  type RecallCampaign,
  type RecallVehicleBrief,
} from "@/lib/warrantyDesk";
import { getRoCatalog, type RoCatalog } from "@/lib/repairOrders";
import { RoWorkspaceModal } from "@/components/RepairOrderWorkspaceBoard";

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

function fmt(ts: string | null | undefined): string {
  if (!ts) return "—";
  try {
    return formatCalendarDate(ts);
  } catch {
    return ts;
  }
}

const STATUS_TONE: Record<string, string> = {
  draft: "border-zinc-700 bg-zinc-900/40 text-zinc-300",
  submitted: "border-amber-900 bg-amber-950/30 text-amber-300",
  approved: "border-emerald-900 bg-emerald-950/30 text-emerald-300",
  rejected: "border-red-900 bg-red-950/30 text-red-300",
  paid: "border-blue-900 bg-blue-950/30 text-blue-300",
};

function Kpi({ theme, label, value, color }: { theme: Theme; label: string; value: string | number; color: string }) { return <WorkStat label={label} value={value}/>; }

type WorkState = { onDraftOpenChange?: (open:boolean)=>void; onSavingChange?: (saving:boolean)=>void };
function ClaimActionModal({
  theme,
  claim,
  onClose,
  onDone,
  onViewRo,
  onDraftOpenChange,
  onSavingChange,
}: WorkState & {
  theme: Theme;
  claim: WarrantyClaim;
  onClose: () => void;
  onDone: () => void;
  onViewRo: (roId: string) => void;
}) {
  const [oemNumber, setOemNumber] = useState(claim.oem_claim_number || "");
  const [rejectionReason, setRejectionReason] = useState("");
  const [paidAmount, setPaidAmount] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const pending = useRef(false);
  const [exitTarget, setExitTarget] = useState<"queue" | "ro" | null>(null);
  const dirty = oemNumber !== (claim.oem_claim_number || "") || !!rejectionReason || !!paidAmount;
  useEffect(()=>{onDraftOpenChange?.(dirty);return ()=>onDraftOpenChange?.(false);},[dirty,onDraftOpenChange]);
  useEffect(()=>{onSavingChange?.(busy);return ()=>onSavingChange?.(false);},[busy,onSavingChange]);
  function leave(target: "queue" | "ro") {
    if (pending.current) return;
    if (dirty) setExitTarget(target);
    else if (target === "ro") onViewRo(claim.ro_id); else onClose();
  }
  async function run(fn: () => Promise<unknown>) {
    if (pending.current) return;
    pending.current = true;
    setBusy(true);
    setError(null);
    try {
      await fn();
      onDone();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }

  return (
    <div role="region" aria-label="Warranty claim work" className="workspace-inline-editor">
      <fieldset disabled={busy} className="workspace-editor-surface p-4 space-y-3">
        {exitTarget && <section role="alert"><p>You have unfinished claim changes.</p><WorkButton type="submit" onClick={()=>setExitTarget(null)}>Keep editing claim</WorkButton><WorkButton type="submit" onClick={()=>{if(pending.current)return; if(exitTarget==="ro")onViewRo(claim.ro_id);else onClose();}}>Discard changes and continue</WorkButton></section>}
        <div className="text-sm font-brand uppercase tracking-wide">Warranty Claim — {claim.service_number}</div>
        <div className="text-xs text-zinc-500">{claim.customer_name} · {claim.ro_description}</div>
        <span className={`inline-block text-xs px-2 py-0.5 rounded-full border ${STATUS_TONE[claim.status]}`}>{claim.status}</span>
        {error && <div role="alert" className="text-xs px-3 py-2 rounded-lg bg-red-500/15 border border-red-500/40 text-red-300">{error}</div>}

        {(claim.status === "draft" || claim.status === "rejected") && (
          <div className="space-y-2">
            <div>
              <label className="text-xs text-zinc-500 uppercase tracking-wide">OEM Claim Number (optional)</label>
              <WorkInput aria-label="OEM Claim Number (optional)"
                value={oemNumber}
                onChange={(e) => setOemNumber(e.target.value)}
                className={tc(theme, "w-full text-xs rounded-md border border-zinc-700 bg-zinc-900 text-white px-2 py-1.5 mt-0.5", "w-full text-xs rounded-md border border-zinc-300 bg-white text-black px-2 py-1.5 mt-0.5")}
              />
            </div>
            <WorkButton type="submit" variant="primary" disabled={busy} onClick={() => run(() => submitWarrantyClaim(claim.ro_id, oemNumber || undefined))} className="w-full text-xs px-3 py-1.5 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50">
              Submit Claim
            </WorkButton>
          </div>
        )}

        {claim.status === "submitted" && (
          <div className="space-y-2">
            <WorkButton type="submit" disabled={busy} onClick={() => run(() => recordWarrantyDecision(claim.ro_id, true))} className="w-full text-xs px-3 py-1.5 rounded bg-emerald-600 text-white font-medium hover:opacity-90 transition disabled:opacity-50">
              Approve Claim
            </WorkButton>
            <WorkField label="Rejection reason (required to decline)"><WorkTextarea
              value={rejectionReason}
              onChange={(e) => setRejectionReason(e.target.value)}
              placeholder="Rejection reason (required to decline)…"
              rows={2}
              className={tc(theme, "w-full text-xs rounded-md border border-zinc-700 bg-zinc-900 text-white px-2 py-1.5", "w-full text-xs rounded-md border border-zinc-300 bg-white text-black px-2 py-1.5")}
            /></WorkField>
            <WorkButton type="submit" variant="danger" disabled={busy || !rejectionReason.trim()} onClick={() => run(() => recordWarrantyDecision(claim.ro_id, false, rejectionReason))} className="w-full text-xs px-3 py-1.5 rounded border border-red-700 text-red-400 hover:bg-red-950/30 transition disabled:opacity-50">
              Decline Claim
            </WorkButton>
          </div>
        )}

        {claim.status === "approved" && (
          <div className="space-y-2">
            <div>
              <label className="text-xs text-zinc-500 uppercase tracking-wide">Paid Amount</label>
              <WorkInput aria-label="Paid Amount"
                type="number"
                value={paidAmount}
                onChange={(e) => setPaidAmount(e.target.value)}
                className={tc(theme, "w-full text-xs rounded-md border border-zinc-700 bg-zinc-900 text-white px-2 py-1.5 mt-0.5", "w-full text-xs rounded-md border border-zinc-300 bg-white text-black px-2 py-1.5 mt-0.5")}
              />
            </div>
            <WorkButton type="submit" variant="primary" disabled={busy || !paidAmount} onClick={() => run(() => recordWarrantyPayment(claim.ro_id, parseFloat(paidAmount)))} className="w-full text-xs px-3 py-1.5 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50">
              Record Payment
            </WorkButton>
          </div>
        )}

        {(claim.status === "paid" || claim.status === "rejected") && claim.status === "rejected" && claim.rejection_reason && (
          <div className="text-xs text-red-300">Reason: {claim.rejection_reason}</div>
        )}
        {claim.status === "paid" && (
          <div className="text-xs text-zinc-500">Paid {money(claim.paid_amount)} on {fmt(claim.paid_at)}</div>
        )}

        <div className="flex justify-between">
          <WorkButton type="submit" onClick={() => leave("ro")} className="text-xs px-3 py-1.5 rounded text-brand-blue hover:opacity-80 transition">View Full RO →</WorkButton>
          <WorkButton type="submit" onClick={() => leave("queue")} className="text-xs px-3 py-1.5 rounded text-zinc-500 hover:text-white transition">Back to warranty queue</WorkButton>
        </div>
      </fieldset>
    </div>
  );
}

function RecallCampaignCard({
  theme,
  campaign,
  onMarkComplete,
}: {
  theme: Theme;
  campaign: RecallCampaign;
  onMarkComplete: (v: RecallVehicleBrief, campaign: RecallCampaign) => void;
}) {
  const [page, setPage] = useState(0);
  const pageCount = Math.max(1, Math.ceil(campaign.needs_repair.length / 25));
  const currentPage = Math.min(page, pageCount - 1);
  const cardClass = tc(theme, "rounded-lg border border-black/20 bg-brand-charcoal p-3", "rounded-lg border border-zinc-200 bg-zinc-50 p-3");
  return (
    <div className={cardClass}>
      <div className="flex items-center justify-between mb-1.5">
        <div className="text-xs font-medium">{campaign.recall_number} — {campaign.make} {campaign.model}</div>
        <div className="text-xs text-zinc-500">{campaign.needs_repair.length} need repair · {campaign.completed.length} completed</div>
      </div>
      <div className="text-xs text-zinc-500 mb-2">{campaign.description}</div>
      {campaign.needs_repair.length > 0 && (
        <div className="space-y-1">
          {campaign.needs_repair.slice(currentPage * 25, (currentPage + 1) * 25).map((v) => (
            <div key={v.vehicle_id} className="flex items-center justify-between gap-2 text-xs">
              <span className="truncate">{v.customer_name} — {v.vin}</span>
              <WorkButton type="submit" variant="primary" onClick={() => onMarkComplete(v, campaign)} className="shrink-0 text-xs px-2 py-0.5 rounded bg-brand-blue text-white hover:opacity-90 transition">
                Mark Completed
              </WorkButton>
            </div>
          ))}
          <CollectionPagination label="Recall vehicles" total={campaign.needs_repair.length} page={currentPage} pageSize={25} onPageChange={setPage}/>
        </div>
      )}
    </div>
  );
}

function MarkCompleteModal({
  theme,
  vehicle,
  campaign,
  onClose,
  onDone,
  onDraftOpenChange,
  onSavingChange,
}: WorkState & {
  theme: Theme;
  vehicle: RecallVehicleBrief;
  campaign: RecallCampaign;
  onClose: () => void;
  onDone: () => void;
}) {
  const [roId, setRoId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const pending = useRef(false);
  const [confirmExit, setConfirmExit] = useState(false);
  useEffect(()=>{onDraftOpenChange?.(!!roId);return ()=>onDraftOpenChange?.(false);},[roId,onDraftOpenChange]);
  useEffect(()=>{onSavingChange?.(busy);return ()=>onSavingChange?.(false);},[busy,onSavingChange]);
  function leave() {
    if (pending.current) return;
    if (roId) setConfirmExit(true); else onClose();
  }
  async function handleSubmit() {
    if (pending.current || !roId.trim()) return;
    pending.current = true;
    setBusy(true);
    setError(null);
    try {
      await markRecallCompleted(vehicle.vehicle_id, campaign.recall_id, roId.trim());
      onDone();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }

  return (
    <section role="region" aria-label="Recall completion work" className="workspace-inline-editor">
      <fieldset disabled={busy} className="workspace-editor-surface p-4 space-y-3">
        <div className="text-sm font-brand uppercase tracking-wide">Mark Recall Completed</div>
        <div className="text-xs text-zinc-500">{vehicle.customer_name} — {vehicle.vin} — {campaign.recall_number}</div>
        {error && <div role="alert" className="text-xs px-3 py-2 rounded-lg bg-red-500/15 border border-red-500/40 text-red-300">{error}</div>}
        <div>
          <label htmlFor="recall-repair-order" className="text-xs text-zinc-500 uppercase tracking-wide">Repair Order ID (SRV-…)</label>
          <WorkInput id="recall-repair-order"
            value={roId}
            onChange={(e) => setRoId(e.target.value)}
            placeholder="SRV-00123"
            className={tc(theme, "w-full text-xs rounded-md border border-zinc-700 bg-zinc-900 text-white px-2 py-1.5 mt-0.5", "w-full text-xs rounded-md border border-zinc-300 bg-white text-black px-2 py-1.5 mt-0.5")}
          />
        </div>
        <div className="flex items-center gap-2 justify-end">
          <WorkButton type="submit" onClick={leave} className="text-xs px-3 py-1.5 rounded text-zinc-500 hover:text-white transition">Back to recall queue</WorkButton>
          <WorkButton type="submit" variant="primary" disabled={busy || !roId.trim()} onClick={handleSubmit} className="text-xs px-3 py-1.5 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50">
            Mark Completed
          </WorkButton>
        </div>
        {confirmExit && <div role="alert"><p>Discard this repair order entry?</p>
          <WorkButton type="submit" onClick={()=>setConfirmExit(false)}>Keep editing recall</WorkButton>
          <WorkButton type="submit" onClick={onClose}>Discard recall entry</WorkButton>
        </div>}
      </fieldset>
    </section>
  );
}

export function WarrantyDeskBoard({ theme, onDraftOpenChange, onSavingChange }: WorkState & { theme: Theme }) {
  const [claims, setClaims] = useState<ClaimsQueue | null>(null);
  const [rejected, setRejected] = useState<ClaimsQueue | null>(null);
  const [recalls, setRecalls] = useState<RecallManagementQueue | null>(null);
  const [catalog, setCatalog] = useState<RoCatalog | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState("");
  const [claimTarget, setClaimTarget] = useState<WarrantyClaim | null>(null);
  const [completeTarget, setCompleteTarget] = useState<{ vehicle: RecallVehicleBrief; campaign: RecallCampaign } | null>(null);
  const [openRoId, setOpenRoId] = useState<string | null>(null);

  function refresh() {
    setLoading(true);
    Promise.all([getClaimsQueue(statusFilter || undefined), getRejectedClaims(), getRecallManagementQueue(), getRoCatalog()])
      .then(([c, r, rc, cat]) => { setClaims(c); setRejected(r); setRecalls(rc); setCatalog(cat); })
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }

  useEffect(refresh, [statusFilter]);

  const cardClass = tc(theme, "rounded-lg border border-black/20 bg-brand-charcoal p-3", "rounded-lg border border-zinc-200 bg-zinc-50 p-3");

  if (loading && !claims) {
    return <div className="p-4 text-sm text-zinc-500">Loading Warranty Desk…</div>;
  }

  if (openRoId && catalog) return <RoWorkspaceModal inline theme={theme} roId={openRoId}
    catalog={catalog} returnLabel="Back to warranty queue" onDraftOpenChange={onDraftOpenChange}
    onSavingChange={onSavingChange} onClose={()=>setOpenRoId(null)} onChanged={refresh} />;

  if (completeTarget) return <MarkCompleteModal theme={theme} vehicle={completeTarget.vehicle}
    campaign={completeTarget.campaign} onDraftOpenChange={onDraftOpenChange} onSavingChange={onSavingChange}
    onClose={()=>setCompleteTarget(null)} onDone={()=>{setCompleteTarget(null);refresh();}} />;

  if (claimTarget) return <ClaimActionModal onDraftOpenChange={onDraftOpenChange} onSavingChange={onSavingChange} key={claimTarget.ro_id} theme={theme} claim={claimTarget}
    onClose={()=>setClaimTarget(null)} onDone={()=>{setClaimTarget(null);refresh();}}
    onViewRo={roId=>{setClaimTarget(null);setOpenRoId(roId);}} />;

  return (
    <div className={tc(theme, "flex-1 flex flex-col min-h-0 bg-brand-ink text-white overflow-y-auto", "flex-1 flex flex-col min-h-0 bg-white text-black overflow-y-auto")}>
      <div className={tc(theme, "grid grid-cols-4 gap-3 p-4 border-b border-zinc-800", "grid grid-cols-4 gap-3 p-4 border-b border-zinc-200")}>
        <Kpi theme={theme} label="Warranty Claims" value={claims?.count ?? 0} color={RIBBON[0]} />
        <Kpi theme={theme} label="Rejected Claims" value={rejected?.count ?? 0} color={RIBBON[3]} />
        <Kpi theme={theme} label="Recall Campaigns" value={recalls?.campaign_count ?? 0} color={RIBBON[1]} />
        <Kpi theme={theme} label="Vehicles Needing Recall Repair" value={recalls?.total_needs_repair ?? 0} color={RIBBON[2]} />
      </div>

      {error && <div className="mx-4 mt-2 text-xs px-3 py-2 rounded-lg bg-red-500/15 border border-red-500/40 text-red-300">{error}</div>}

      <div className="p-4 space-y-5">
        <div>
          <div className="flex items-center justify-between mb-1.5">
            <div className="text-xs font-brand uppercase tracking-wide text-zinc-500">Submission Workflow ({claims?.count ?? 0})</div>
            <WorkField label="Status"><WorkSelect
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className={tc(theme, "text-xs rounded border border-zinc-700 bg-zinc-900 text-white px-2 py-1", "text-xs rounded border border-zinc-300 bg-white text-black px-2 py-1")}
            >
              <option value="">All statuses</option>
              {["draft", "submitted", "approved", "rejected", "paid"].map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </WorkSelect></WorkField>
          </div>
          {(claims?.claims.length ?? 0) === 0 ? (
            <div className="text-xs text-zinc-600">No warranty claims in this status.</div>
          ) : (
            <div className="space-y-1.5 max-h-80 overflow-y-auto">
              {claims!.claims.map((c) => (
                <button key={c.ro_id} onClick={() => setClaimTarget(c)} className={`${cardClass} w-full text-left flex items-center justify-between gap-2 hover:border-brand-blue/60 transition`}>
                  <div className="min-w-0">
                    <div className="text-xs font-medium truncate">{c.customer_name || "—"} — {c.ro_description || c.service_number}</div>
                    <div className="text-xs text-zinc-500 truncate">{c.service_number} · {money(c.cost)}</div>
                  </div>
                  <span className={`shrink-0 text-xs px-2 py-0.5 rounded-full border ${STATUS_TONE[c.status]}`}>{c.status}</span>
                </button>
              ))}
            </div>
          )}
        </div>

        <div>
          <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1.5">Rejected Claims Queue ({rejected?.count ?? 0})</div>
          {(rejected?.claims.length ?? 0) === 0 ? (
            <div className="text-xs text-zinc-600">No rejected claims.</div>
          ) : (
            <div className="space-y-1.5">
              {rejected!.claims.map((c) => (
                <button key={c.ro_id} onClick={() => setClaimTarget(c)} className={`${cardClass} w-full text-left hover:border-brand-blue/60 transition`}>
                  <div className="text-xs font-medium truncate">{c.customer_name} — {c.service_number}</div>
                  <div className="text-xs text-red-300 truncate">{c.rejection_reason}</div>
                </button>
              ))}
            </div>
          )}
        </div>

        <div>
          <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1.5">
            Recall Management ({recalls?.total_needs_repair ?? 0} need repair · {recalls?.total_completed ?? 0} completed)
          </div>
          {(recalls?.campaigns.length ?? 0) === 0 ? (
            <div className="text-xs text-zinc-600">No open recall campaigns.</div>
          ) : (
            <div className="space-y-2">
              {recalls!.campaigns.map((c) => (
                <RecallCampaignCard key={c.recall_id} theme={theme} campaign={c} onMarkComplete={(v, campaign) => setCompleteTarget({ vehicle: v, campaign })} />
              ))}
            </div>
          )}
        </div>
      </div>


    </div>
  );
}
