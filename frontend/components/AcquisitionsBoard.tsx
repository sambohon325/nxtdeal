"use client";
import {RecordTable} from "./RecordTable";
import { WorkButton, WorkSelect, WorkInput , WorkStat} from "./WorkspaceUi";
import {CollectionPagination} from "./CollectionPagination";
import { WorkField } from "./WorkField";

// Inventory department's "Acquisitions" item -- the buying center (Inventory
// rebuild, second slice, Sam's own words: "probably one of the most important
// modules... an entire buying center"). A real AcquisitionRequest moves
// through Evaluate -> Price Risk -> Estimate Recon -> Review Market ->
// Approve, backed by a real 2-step Purchase Approval chain (Inventory
// Manager -> GM/Admin). The Buy Recommendation Engine and Factory Allocations
// feed are SIMULATED per Sam's direct instruction (2026-07-17) -- every
// simulated figure is surfaced with its disclaimer text visible in the UI,
// not hidden behind a clean-looking number.
import { PRODUCT_ACCENT_COLORS } from "@/lib/productTheme";
import { useEffect, useState } from "react";
import {
  getAcquisitionsCatalog,
  getAcquisitionsSummary,
  getFactoryAllocations,
  listAcquisitionRequests,
  getAcquisitionRequest,
  createAcquisitionRequest,
  recordPriceRisk,
  recordReconEstimate,
  recordMarketReview,
  submitForApproval,
  approveByInventoryManager,
  approveByGm,
  rejectAcquisitionRequest,
  markPurchased,
  type AcquisitionsCatalog,
  type AcquisitionsSummary,
  type FactoryAllocations,
  type AcquisitionRequest,
  type SourceType,
  type DirectPurchaseChannel,
} from "@/lib/acquisitions";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const RIBBON = PRODUCT_ACCENT_COLORS;

const STAGE_LABELS: Record<string, string> = {
  evaluate: "Evaluate", price_risk: "Price Risk", estimate_recon: "Estimate Recon",
  review_market: "Review Market", pending_approval: "Pending Approval",
  approved: "Approved", rejected: "Rejected", purchased: "Purchased",
};

const SOURCE_LABELS: Record<string, string> = {
  auction: "Auction", trade: "Trade", direct_purchase: "Direct Purchase",
};

const CHANNEL_LABELS: Record<string, string> = {
  we_buy_cars: "We Buy Cars", web_lead: "Web Lead", walk_in: "Walk-In Seller",
};

const STAGE_TONE: Record<string, string> = {
  evaluate: "bg-zinc-800 text-zinc-300",
  price_risk: "bg-amber-950/40 text-amber-300",
  estimate_recon: "bg-amber-950/40 text-amber-300",
  review_market: "bg-blue-950/40 text-blue-300",
  pending_approval: "bg-purple-950/40 text-purple-300",
  approved: "bg-green-950/40 text-green-300",
  rejected: "bg-red-950/40 text-red-300",
  purchased: "bg-green-950/40 text-green-300",
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

export function acquisitionIntakeError(make: string, model: string, year: string, mileage: string, acv: string) {
  if (!make.trim() || !model.trim()) return "Make and model are required.";
  if (year.trim() && !/^\d{4}$/.test(year.trim())) return "Enter a four-digit model year or leave it blank.";
  if (mileage.trim() && !/^\d+$/.test(mileage.trim())) return "Enter mileage as a whole number, zero or greater, without commas.";
  if (acv.trim() && (!/^\d+(\.\d{1,2})?$/.test(acv.trim()) || !Number.isFinite(Number(acv)))) return "Enter estimated cash value as a positive amount or zero, with up to two decimal places.";
  return null;
}

function NewRequestForm({ theme, catalog, onCreated, onDraftOpenChange,onSavingChange }: { theme: Theme; catalog: AcquisitionsCatalog; onCreated: () => void; onDraftOpenChange?:(v:boolean)=>void;onSavingChange?:(v:boolean)=>void }) {
  const [sourceType, setSourceType] = useState<SourceType>("direct_purchase");
  const [channel, setChannel] = useState<DirectPurchaseChannel>("walk_in");
  const [year, setYear] = useState("");
  const [make, setMake] = useState("");
  const [model, setModel] = useState("");
  const [trim, setTrim] = useState("");
  const [mileage, setMileage] = useState("");
  const [vin, setVin] = useState("");
  const [acv, setAcv] = useState("");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const dirty=[year,make,model,trim,mileage,vin,acv,notes].some(v=>v.trim())||sourceType!=="direct_purchase"||channel!=="walk_in";
  useEffect(()=>{onDraftOpenChange?.(dirty);return()=>onDraftOpenChange?.(false)},[dirty,onDraftOpenChange]);
  useEffect(()=>{onSavingChange?.(busy);return()=>onSavingChange?.(false)},[busy,onSavingChange]);
  const textClass = tc(theme, "bg-zinc-900 border-zinc-700 text-white placeholder:text-zinc-600", "bg-white border-zinc-300 text-black placeholder:text-zinc-400");

  async function handleSubmit() {
    const validationError = acquisitionIntakeError(make, model, year, mileage, acv);
    if (validationError) {
      setError(validationError);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await createAcquisitionRequest({
        source_type: sourceType,
        direct_purchase_channel: sourceType === "direct_purchase" ? channel : undefined,
        year: year.trim() || undefined, make: make.trim(), model: model.trim(), trim: trim.trim() || undefined,
        mileage: mileage.trim() || undefined, vin: vin.trim().toUpperCase() || undefined,
        estimated_acv: acv.trim() ? Number(acv) : undefined,
        notes,
      });
      setSourceType("direct_purchase");setChannel("walk_in");setYear(""); setMake(""); setModel(""); setTrim(""); setMileage(""); setVin(""); setAcv(""); setNotes("");
      onCreated();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={tc(theme, "rounded-lg border border-black/20 bg-brand-charcoal p-3", "rounded-lg border border-zinc-200 bg-zinc-50 p-3")}>
      <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">+ New Acquisition Request</div>
      {error && <div role="alert" className="text-xs px-3 py-2 mb-2 rounded-lg bg-red-500/15 border border-red-500/40 text-red-300">{error}</div>}
      <p className="text-xs text-zinc-500 mb-3">Create an evaluation for a potential vehicle. This does not approve a purchase or add the vehicle to stock. Only make and model are required. Your draft stays here when switching between the buying tabs.</p>
      <fieldset disabled={busy} className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <label className="text-xs">Vehicle source<WorkSelect value={sourceType} onChange={(e) => setSourceType(e.target.value as SourceType)} className={`block w-full mt-1 rounded-md border px-2 py-1.5 text-xs ${textClass}`}>
          {catalog.source_types.map((s) => <option key={s} value={s}>{SOURCE_LABELS[s] || s}</option>)}
        </WorkSelect></label>
        {sourceType === "direct_purchase" && (
          <label className="text-xs">Seller channel<WorkSelect value={channel} onChange={(e) => setChannel(e.target.value as DirectPurchaseChannel)} className={`block w-full mt-1 rounded-md border px-2 py-1.5 text-xs ${textClass}`}>
            {catalog.direct_purchase_channels.map((c) => <option key={c} value={c}>{CHANNEL_LABELS[c] || c}</option>)}
          </WorkSelect></label>
        )}
        <label className="text-xs">Model year<WorkInput value={year} onChange={(e) => setYear(e.target.value)} placeholder="Year" className={`block w-full mt-1 rounded-md border px-2 py-1.5 text-xs ${textClass}`} /></label>
        <label className="text-xs">Make (required)<WorkInput value={make} onChange={(e) => setMake(e.target.value)} placeholder="Make *" className={`block w-full mt-1 rounded-md border px-2 py-1.5 text-xs ${textClass}`} /></label>
        <label className="text-xs">Model (required)<WorkInput value={model} onChange={(e) => setModel(e.target.value)} placeholder="Model *" className={`block w-full mt-1 rounded-md border px-2 py-1.5 text-xs ${textClass}`} /></label>
        <label className="text-xs">Trim<WorkInput value={trim} onChange={(e) => setTrim(e.target.value)} placeholder="Trim" className={`block w-full mt-1 rounded-md border px-2 py-1.5 text-xs ${textClass}`} /></label>
        <label className="text-xs">Mileage<WorkInput value={mileage} onChange={(e) => setMileage(e.target.value)} placeholder="Mileage" className={`block w-full mt-1 rounded-md border px-2 py-1.5 text-xs ${textClass}`} /></label>
        <label className="text-xs">VIN (optional)<WorkInput value={vin} onChange={(e) => setVin(e.target.value)} placeholder="VIN (optional)" className={`block w-full mt-1 rounded-md border px-2 py-1.5 text-xs ${textClass}`} /></label>
        <label className="text-xs">Estimated cash value ($)<WorkInput value={acv} onChange={(e) => setAcv(e.target.value)} placeholder="Estimated ACV ($)" inputMode="decimal" className={`block w-full mt-1 rounded-md border px-2 py-1.5 text-xs ${textClass}`} /></label>
        <label className="text-xs">Intake notes<WorkInput value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Notes" className={`block w-full mt-1 rounded-md border px-2 py-1.5 text-xs ${textClass}`} /></label>
      </fieldset>
      <WorkButton type="submit" variant="primary" disabled={busy} onClick={handleSubmit} className="mt-2 text-xs px-2.5 py-1.5 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50">
        {busy ? "Creating…" : "Start Evaluation"}
      </WorkButton>
    </div>
  );
}

function RequestDetailModal({ theme, requestId, onClose, onChanged }: { theme: Theme; requestId: string; onClose: () => void; onChanged: () => void }) {
  const [data, setData] = useState<AcquisitionRequest | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [riskLevel, setRiskLevel] = useState<"low" | "medium" | "high">("medium");
  const [riskNotes, setRiskNotes] = useState("");
  const [reconEstimate, setReconEstimate] = useState("");
  const [reconNotes, setReconNotes] = useState("");
  const [marketNotes, setMarketNotes] = useState("");
  const [approvalNotes, setApprovalNotes] = useState("");
  const [rejectReason, setRejectReason] = useState("");

  const textClass = tc(theme, "bg-zinc-900 border-zinc-700 text-white placeholder:text-zinc-600", "bg-white border-zinc-300 text-black placeholder:text-zinc-400");
  const cardClass = tc(theme, "rounded-lg border border-black/20 bg-brand-charcoal p-3", "rounded-lg border border-zinc-200 bg-zinc-50 p-3");

  function refresh() {
    setLoading(true);
    getAcquisitionRequest(requestId)
      .then(setData)
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }

  useEffect(refresh, [requestId]);

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

  const [confirmClose, setConfirmClose] = useState(false);
  const [riskEdited, setRiskEdited] = useState(false);
  function requestClose() {
    if (busy) return;
    if (riskEdited || riskNotes || reconEstimate || reconNotes || marketNotes || approvalNotes || rejectReason) setConfirmClose(true);
    else onClose();
  }

  if (!data) {
    return <section aria-label="Acquisition request" className="p-4 space-y-3">
      <WorkButton type="submit" onClick={requestClose}>Back to buying queue</WorkButton>
      {error ? <div role="alert">{error} <WorkButton type="submit" onClick={refresh}>Retry request</WorkButton></div> : <p>Loading request…</p>}
    </section>;
  }

  const stage = data.stage;

  return (
    <div role="region" aria-label="Acquisition request" className="p-4">
      <div onClick={(e) => e.stopPropagation()} className={tc(theme, "w-full rounded-xl border border-black/20 bg-brand-ink text-white p-5 space-y-3", "w-full rounded-xl border border-zinc-200 bg-white text-black p-5 space-y-3")}>
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="text-sm font-brand uppercase tracking-wide">
              {data.year} {data.make} {data.model} {data.trim}
            </div>
            <div className="text-xs text-zinc-500 mt-0.5">
              {data.id} · {SOURCE_LABELS[data.source_type]}{data.direct_purchase_channel ? ` (${CHANNEL_LABELS[data.direct_purchase_channel]})` : ""} · Est. ACV {money(data.estimated_acv)}
            </div>
          </div>
          <WorkButton type="submit" disabled={busy} onClick={requestClose} className="text-xs text-zinc-500 transition">Back to buying queue</WorkButton>
        </div>

        {confirmClose && <div role="alert" className="rounded-lg border border-amber-500 p-3 text-sm">
          <p>Leave this request? Review notes still in these fields will be discarded. Saved records remain unchanged.</p>
          <WorkButton type="submit" onClick={() => setConfirmClose(false)} className="mr-4">Keep editing</WorkButton>
          <WorkButton type="submit" onClick={onClose}>Discard drafts and return</WorkButton>
        </div>}
        {loading && <p role="status">Refreshing request…</p>}
        <div className="flex items-center gap-2">
          <span className={`text-xs font-medium px-2.5 py-1 rounded ${STAGE_TONE[stage]}`}>{STAGE_LABELS[stage]}</span>
          {data.notes && <span className="text-xs text-zinc-500">{data.notes}</span>}
        </div>

        {error && <div className="text-xs px-3 py-2 rounded-lg bg-red-500/15 border border-red-500/40 text-red-300">{error}</div>}

        {stage === "evaluate" && (
          <div className={cardClass}>
            <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Step 1 — Price Risk Assessment</div>
            <div className="flex items-center gap-1.5 mb-2">
              {(["low", "medium", "high"] as const).map((lvl) => (
                <WorkButton type="submit"
                  key={lvl}
                  onClick={() => { setRiskLevel(lvl); setRiskEdited(true); }}
                  className={`text-xs px-2.5 py-1 rounded-full capitalize transition ${riskLevel === lvl ? "bg-brand-blue text-white" : "bg-zinc-200/10 text-zinc-400"}`}
                >
                  {lvl}
                </WorkButton>
              ))}
            </div>
            <WorkField label="Risk notes"><WorkInput value={riskNotes} onChange={(e) => setRiskNotes(e.target.value)} placeholder="Risk notes (e.g. frame damage, title issues)…" className={`w-full rounded-md border px-2 py-1.5 text-xs mb-2 ${textClass}`} /></WorkField>
            <WorkButton type="submit" variant="primary" disabled={busy} onClick={() => withBusy(() => recordPriceRisk(data.id, riskLevel, riskNotes))} className="text-xs px-2.5 py-1 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50">Record Price Risk</WorkButton>
          </div>
        )}

        {stage === "price_risk" && (
          <div className={cardClass}>
            <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">
              Price Risk: <span className="capitalize">{data.price_risk_level}</span> — {data.price_risk_notes}
            </div>
            <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2 mt-3">Step 2 — Estimate Recon Cost</div>
            <div className="flex items-center gap-1.5 mb-2">
              <WorkField label="Recon estimate ($)"><WorkInput value={reconEstimate} onChange={(e) => setReconEstimate(e.target.value)} type="number" placeholder="Recon estimate ($)" className={`flex-1 rounded-md border px-2 py-1.5 text-xs ${textClass}`} /></WorkField>
            </div>
            <WorkField label="Recon notes"><WorkInput value={reconNotes} onChange={(e) => setReconNotes(e.target.value)} placeholder="Recon notes…" className={`w-full rounded-md border px-2 py-1.5 text-xs mb-2 ${textClass}`} /></WorkField>
            <WorkButton type="submit" variant="primary" disabled={busy || !reconEstimate} onClick={() => withBusy(() => recordReconEstimate(data.id, parseFloat(reconEstimate), reconNotes))} className="text-xs px-2.5 py-1 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50">Record Recon Estimate</WorkButton>
          </div>
        )}

        {stage === "estimate_recon" && (
          <div className={cardClass}>
            <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">
              Recon Estimate: {money(data.recon_estimate)} — {data.recon_notes}
            </div>
            <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2 mt-3 flex items-center gap-2">
              Step 3 — Review Market (Buy Recommendation) <SimulatedBadge disclaimer="Generated from a deterministic simulated market signal seeded by make/model/year -- no real market/competitor data feed exists in this system yet." />
            </div>
            <WorkField label="Market review notes"><WorkInput value={marketNotes} onChange={(e) => setMarketNotes(e.target.value)} placeholder="Market review notes…" className={`w-full rounded-md border px-2 py-1.5 text-xs mb-2 ${textClass}`} /></WorkField>
            <WorkButton type="submit" variant="primary" disabled={busy} onClick={() => withBusy(() => recordMarketReview(data.id, marketNotes))} className="text-xs px-2.5 py-1 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50">Run Buy Recommendation</WorkButton>
          </div>
        )}

        {stage === "review_market" && data.market_review && (
          <div className={cardClass}>
            <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2 flex items-center gap-2">
              Buy Recommendation <SimulatedBadge disclaimer={data.market_review.recommendation.disclaimer} />
            </div>
            <div className="grid grid-cols-3 gap-2 text-xs mb-2">
              <div><span className="text-zinc-500">Demand</span><div>{data.market_review.recommendation.demand_level}</div></div>
              <div><span className="text-zinc-500">Avg Turn Rate</span><div>{data.market_review.recommendation.avg_turn_rate_days} days</div></div>
              <div><span className="text-zinc-500">Comparable Sales</span><div>{data.market_review.recommendation.comparable_sales_count}</div></div>
            </div>
            {data.market_review.recommendation.recommended_bid && (
              <div className="text-sm font-semibold mb-2">
                Recommended Bid: {money(data.market_review.recommendation.recommended_bid.low)} – {money(data.market_review.recommendation.recommended_bid.high)}
              </div>
            )}
            <WorkButton type="submit" variant="primary" disabled={busy} onClick={() => withBusy(() => submitForApproval(data.id))} className="text-xs px-2.5 py-1 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50">Submit for Approval</WorkButton>
          </div>
        )}

        {stage === "pending_approval" && (
          <div className={cardClass}>
            <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Purchase Approval Chain</div>
            <div className="space-y-2 mb-2">
              <div className="flex items-center justify-between text-xs">
                <span>1. Inventory Manager</span>
                {data.inventory_manager_approval ? (
                  <span className="text-green-400">✓ {data.inventory_manager_approval.approved_by}, {fmt(data.inventory_manager_approval.approved_at)}</span>
                ) : (
                  <span className="text-zinc-500">Pending</span>
                )}
              </div>
              <div className="flex items-center justify-between text-xs">
                <span>2. General Manager</span>
                {data.gm_approval ? (
                  <span className="text-green-400">✓ {data.gm_approval.approved_by}, {fmt(data.gm_approval.approved_at)}</span>
                ) : (
                  <span className="text-zinc-500">Pending</span>
                )}
              </div>
            </div>
            <WorkField label="Approval notes (optional)"><WorkInput value={approvalNotes} onChange={(e) => setApprovalNotes(e.target.value)} placeholder="Approval notes (optional)…" className={`w-full rounded-md border px-2 py-1.5 text-xs mb-2 ${textClass}`} /></WorkField>
            <div className="flex items-center gap-1.5 flex-wrap mb-2">
              {!data.inventory_manager_approval && (
                <WorkButton type="submit" variant="primary" disabled={busy} onClick={() => withBusy(() => approveByInventoryManager(data.id, approvalNotes))} className="text-xs px-2.5 py-1 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50">Approve — Inventory Manager</WorkButton>
              )}
              {data.inventory_manager_approval && !data.gm_approval && (
                <WorkButton type="submit" variant="primary" disabled={busy} onClick={() => withBusy(() => approveByGm(data.id, approvalNotes))} className="text-xs px-2.5 py-1 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50">Approve — GM (final)</WorkButton>
              )}
            </div>
            <div className="pt-2 border-t border-zinc-800">
              <WorkField label="Rejection reason"><WorkInput value={rejectReason} onChange={(e) => setRejectReason(e.target.value)} placeholder="Rejection reason…" className={`w-full rounded-md border px-2 py-1.5 text-xs mb-2 ${textClass}`} /></WorkField>
              <WorkButton type="submit" variant="danger" disabled={busy || !rejectReason.trim()} onClick={() => withBusy(() => rejectAcquisitionRequest(data.id, rejectReason))} className="text-xs px-2.5 py-1 rounded bg-red-600 text-white font-medium hover:opacity-90 transition disabled:opacity-50">Reject Request</WorkButton>
            </div>
          </div>
        )}

        {stage === "approved" && (
          <div className={cardClass}>
            <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Approved — Ready to Purchase</div>
            <div className="text-xs text-zinc-400 mb-2">Both Inventory Manager and GM have signed off. Mark this request purchased once the vehicle is actually bought.</div>
            <WorkButton type="submit" disabled={busy} onClick={() => withBusy(() => markPurchased(data.id))} className="text-xs px-2.5 py-1 rounded bg-green-600 text-white font-medium hover:opacity-90 transition disabled:opacity-50">Mark Purchased</WorkButton>
          </div>
        )}

        {stage === "rejected" && (
          <div className={cardClass}>
            <div className="text-xs font-brand uppercase tracking-wide text-red-400 mb-1">Rejected</div>
            <div className="text-xs text-zinc-400">{data.rejection_reason} — {data.rejected_by}, {fmt(data.rejected_at)}</div>
          </div>
        )}

        {stage === "purchased" && (
          <div className={cardClass}>
            <div className="text-xs font-brand uppercase tracking-wide text-green-400 mb-1">Purchased</div>
            <div className="text-xs text-zinc-400">Completed {fmt(data.purchased_at)}{data.linked_vehicle_id ? ` — linked to ${data.linked_vehicle_id}` : ""}</div>
          </div>
        )}
      </div>
    </div>
  );
}

export function acquisitionQueue(requests: AcquisitionRequest[], stage: string, query: string, page: number, pageSize = 25) {
  const term = query.trim().toLowerCase();
  const matches = requests.filter(r => (!stage || r.stage === stage) && (!term ||
    [r.id, r.year, r.make, r.model, r.trim, r.vin, r.linked_deal_id, r.linked_vehicle_id].some(v => String(v ?? "").toLowerCase().includes(term))));
  const pages = Math.max(1, Math.ceil(matches.length / pageSize));
  const current = Math.max(0, Math.min(page, pages - 1));
  return { rows: matches.slice(current * pageSize, current * pageSize + pageSize), total: matches.length, pages, current };
}

export function AcquisitionsBoard({ theme, initialTab = "pipeline",onDraftOpenChange,onSavingChange }: { theme: Theme; initialTab?: "pipeline" | "new" | "allocations";onDraftOpenChange?:(v:boolean)=>void;onSavingChange?:(v:boolean)=>void }) {
  const [tab, setTab] = useState<"pipeline" | "new" | "allocations">(initialTab);
  useEffect(()=>setTab(initialTab),[initialTab]);
  const [catalog, setCatalog] = useState<AcquisitionsCatalog | null>(null);
  const [summary, setSummary] = useState<AcquisitionsSummary | null>(null);
  const [requests, setRequests] = useState<AcquisitionRequest[]>([]);
  const [allocations, setAllocations] = useState<FactoryAllocations | null>(null);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<string | null>(null);
  const [stageFilter, setStageFilter] = useState<string>("");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(0);
  const [pageSize,setPageSize]=useState(25);
  const [error, setError] = useState<string | null>(null);

  function refresh() {
    setLoading(true);
    setError(null);
    Promise.all([getAcquisitionsCatalog(), getAcquisitionsSummary(), listAcquisitionRequests(), getFactoryAllocations()])
      .then(([c, s, r, a]) => {
        setCatalog(c);
        setSummary(s);
        setRequests(r.requests);
        setAllocations(a);
      })
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }

  useEffect(refresh, []);

  const queue = acquisitionQueue(requests, stageFilter, query, page, pageSize);

  return (
    <div className={tc(theme, "work-inventory-board", "work-inventory-board")}>
      <div hidden={!!selected}>
      <div className={tc(theme, "work-inventory-stats", "work-inventory-stats")}>
        <Kpi theme={theme} label="Total Requests" value={summary?.total_requests || 0} color={RIBBON[0]} />
        <Kpi theme={theme} label="Pending Approval" value={summary?.pending_approval_count || 0} color={RIBBON[1]} />
        <Kpi theme={theme} label="Awaiting GM Signoff" value={summary?.awaiting_gm_signoff_count || 0} color={RIBBON[2]} />
        <Kpi theme={theme} label="Purchased" value={summary?.by_stage?.purchased || 0} color={RIBBON[3]} />
      </div>

      <div className="flex items-center gap-1.5 px-4 py-2 border-b border-zinc-800">
        {([
          ["pipeline", "Pipeline"],
          ["new", "+ New Request"],
          ["allocations", "Factory Allocations"],
        ] as const).map(([key, label]) => (
          <WorkButton data-work-view aria-pressed={tab === key} type="submit"
            key={key}
            onClick={() => setTab(key)}
            className={`text-xs px-2.5 py-1 rounded-full font-brand uppercase tracking-wide transition ${tab === key ? "bg-zinc-200 text-black font-medium" : "bg-zinc-200/10 text-zinc-400 hover:text-white"}`}
          >
            {label}
          </WorkButton>
        ))}
      </div>

      <div className="flex-1 p-4">
        {catalog && <div hidden={tab !== "new"}><NewRequestForm onDraftOpenChange={onDraftOpenChange} onSavingChange={onSavingChange} theme={theme} catalog={catalog} onCreated={() => { refresh(); setTab("pipeline"); }} /></div>}
        {error ? <div role="alert">{error} <WorkButton type="submit" onClick={refresh}>Retry buying queue</WorkButton></div> : loading || !catalog ? (
          <div className="text-sm text-zinc-500">Loading…</div>
        ) : tab === "new" ? null : tab === "allocations" ? (
          <div className="space-y-2">
            {allocations && (
              <div className="text-xs px-3 py-2 rounded-lg bg-amber-950/30 border border-amber-900/50 text-amber-300">
                {allocations.disclaimer}
              </div>
            )}
            <div className="grid grid-cols-2 gap-2">
              {(allocations?.allocations || []).map((a) => (
                <div key={a.make} className={tc(theme, "rounded-lg border border-zinc-800 bg-brand-charcoal p-3", "rounded-lg border border-zinc-200 bg-zinc-50 p-3")}>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-sm font-medium">{a.make}</span>
                    <span className="text-xs px-1.5 py-0.5 rounded bg-amber-950/40 text-amber-300 font-brand uppercase">Simulated</span>
                  </div>
                  <div className="text-xs text-zinc-500">{a.allocated_units} units allocated · {a.models.join(", ")}</div>
                  <div className="text-xs text-zinc-600">Allotment in {a.allotment_month_offset} month{a.allotment_month_offset === 1 ? "" : "s"}</div>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <>
            <label className="block text-xs mb-3">Find an acquisition
              <WorkInput value={query} onChange={e => { setQuery(e.target.value); setPage(0); }} placeholder="Request ID, VIN, vehicle or linked deal" className="block w-full mt-1 rounded-md border border-zinc-500 bg-transparent px-3 py-2" />
            </label>
            <WorkField label="Stage"><WorkSelect value={stageFilter} onChange={e=>{setStageFilter(e.target.value);setPage(0);}}><option value="">All stages</option>{catalog.stages.map(stage=><option key={stage} value={stage}>{STAGE_LABELS[stage]}</option>)}</WorkSelect></WorkField>
            <RecordTable label="Acquisition requests" paginate={false}><thead><tr><th>Vehicle</th><th>Source</th><th>Estimated value</th><th>Stage</th><th>Next step</th></tr></thead><tbody>{queue.rows.map(r=><tr key={r.id}><td><strong>{r.year} {r.make} {r.model}</strong><span className="work-record-meta">{r.id}</span></td><td>{SOURCE_LABELS[r.source_type]}</td><td>{money(r.estimated_acv)}</td><td>{STAGE_LABELS[r.stage]}</td><td><WorkButton onClick={()=>setSelected(r.id)}>Open request</WorkButton></td></tr>)}</tbody></RecordTable>
            {queue.total===0&&<p>No requests match. Clear the search or choose All.</p>}
            <CollectionPagination label="Requests" total={queue.total} page={queue.current} pageSize={pageSize} onPageChange={setPage} onPageSizeChange={setPageSize}/>
          </>
        )}
      </div>


      </div>
      {selected && <RequestDetailModal theme={theme} requestId={selected} onClose={() => setSelected(null)} onChanged={refresh} />}
    </div>
  );
}
