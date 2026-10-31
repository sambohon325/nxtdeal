"use client";
import {RecordTable} from "./RecordTable";
import { WorkButton, WorkInput , WorkStat} from "./WorkspaceUi";
import { WorkField } from "./WorkField";

// Inventory department's "Wholesale" item -- the disposition center
// (Inventory rebuild, seventh slice). Real Open Offers (submit/accept/
// reject/counter/withdraw), real Sold Wholesale Units (a real
// disposition_channel flag distinguishing wholesale from retail), and real
// Fund Collection -- all internal capabilities, not simulated.
import { PRODUCT_ACCENT_COLORS } from "@/lib/productTheme";
import { useEffect, useState } from "react";
import {
  getWholesaleCandidates,
  getWholesaleDeskSummary,
  submitOffer,
  acceptOffer,
  rejectOffer,
  counterOffer,
  withdrawOffer,
  markWholesaleSold,
  recordFundsCollected,
  type WholesaleCandidatesResponse,
  type WholesaleDeskSummary,
  type WholesaleOffer,
} from "@/lib/wholesaleDesk";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const RIBBON = PRODUCT_ACCENT_COLORS;

function money(v: number | string | null | undefined): string {
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

function Kpi({ theme, label, value, color }: { theme: Theme; label: string; value: string; color: string }) { return <WorkStat label={label} value={value}/>; }

function OfferCard({ theme, offer, onAccept, onReject, onCounter, onWithdraw, onMarkSold, busy }: {
  theme: Theme; offer: WholesaleOffer;
  onAccept: () => void; onReject: (notes: string) => void; onCounter: (amount: number) => void;
  onWithdraw: () => void; onMarkSold: () => void; busy: boolean;
}) {
  const [counterAmt, setCounterAmt] = useState("");
  const [rejectNotes, setRejectNotes] = useState("");
  const textClass = tc(theme, "bg-zinc-900 border-zinc-700 text-white placeholder:text-zinc-600", "bg-white border-zinc-300 text-black placeholder:text-zinc-400");

  return (
    <div className={tc(theme, "rounded-lg border border-zinc-800 bg-brand-charcoal p-3", "rounded-lg border border-zinc-200 bg-zinc-50 p-3")}>
      <div className="flex items-center justify-between mb-1">
        <span className="text-sm font-medium">{offer.buyer_name}</span>
        <span className="text-xs capitalize text-zinc-500">{offer.status}{offer.counter_amount ? ` @ ${money(offer.counter_amount)}` : ""}</span>
      </div>
      <div className="text-xs text-zinc-500 mb-2">{offer.vehicle_id} · Offered {money(offer.offer_amount)} · {fmt(offer.submitted_at)}</div>
      {offer.status === "pending" && (
        <div className="space-y-1.5">
          <div className="flex items-center gap-1.5">
            <WorkButton type="submit" disabled={busy} onClick={onAccept} className="text-xs px-2 py-1 rounded bg-green-700 text-white font-medium hover:opacity-90 transition disabled:opacity-50">Accept</WorkButton>
            <WorkField label="Counter $"><WorkInput value={counterAmt} onChange={(e) => setCounterAmt(e.target.value)} type="number" placeholder="Counter $" className={`flex-1 rounded-md border px-2 py-1 text-xs ${textClass}`} /></WorkField>
            <WorkButton type="submit" variant="primary" disabled={busy || !counterAmt} onClick={() => onCounter(parseFloat(counterAmt))} className="text-xs px-2 py-1 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50">Counter</WorkButton>
          </div>
          <div className="flex items-center gap-1.5">
            <WorkField label="Reason (optional)"><WorkInput value={rejectNotes} onChange={(e) => setRejectNotes(e.target.value)} placeholder="Reason (optional)" className={`flex-1 rounded-md border px-2 py-1 text-xs ${textClass}`} /></WorkField>
            <WorkButton type="submit" variant="danger" disabled={busy} onClick={() => onReject(rejectNotes)} className="text-xs px-2 py-1 rounded bg-red-600 text-white font-medium hover:opacity-90 transition disabled:opacity-50">Reject</WorkButton>
          </div>
        </div>
      )}
      {(offer.status === "pending" || offer.status === "countered") && (
        <WorkButton type="submit" disabled={busy} onClick={onWithdraw} className="text-xs px-2 py-1 mt-1.5 rounded bg-zinc-700 text-white font-medium hover:opacity-90 transition disabled:opacity-50">Withdraw</WorkButton>
      )}
      {offer.status === "countered" && (
        <WorkButton type="submit" disabled={busy} onClick={onAccept} className="text-xs px-3 py-2 rounded bg-green-700 text-white">Record buyer acceptance of counteroffer</WorkButton>
      )}
      {offer.status === "accepted" && (
        <WorkButton type="submit" variant="primary" disabled={busy} onClick={onMarkSold} className="text-xs px-2.5 py-1.5 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50">Mark Wholesale Sold</WorkButton>
      )}
    </div>
  );
}

export function WholesaleDeskBoard({ theme, initialTab = "candidates" }: { theme: Theme; initialTab?: "candidates" | "offers" | "sold" | "funds" }) {
  const [tab, setTab] = useState<"candidates" | "offers" | "sold" | "funds">(initialTab);
  useEffect(()=>setTab(initialTab),[initialTab]);
  const [candidates, setCandidates] = useState<WholesaleCandidatesResponse | null>(null);
  const [summary, setSummary] = useState<WholesaleDeskSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [offerVehicle, setOfferVehicle] = useState("");
  const [offerBuyer, setOfferBuyer] = useState("");
  const [offerAmount, setOfferAmount] = useState("");

  const [fundsVehicle, setFundsVehicle] = useState("");
  const [fundsAmount, setFundsAmount] = useState("");
  const [fundsMethod, setFundsMethod] = useState("");

  const textClass = tc(theme, "bg-zinc-900 border-zinc-700 text-white placeholder:text-zinc-600", "bg-white border-zinc-300 text-black placeholder:text-zinc-400");
  const cardClass = tc(theme, "rounded-lg border border-black/20 bg-brand-charcoal p-3", "rounded-lg border border-zinc-200 bg-zinc-50 p-3");

  function refresh() {
    setLoading(true);
    setError(null);
    Promise.all([getWholesaleCandidates(), getWholesaleDeskSummary()])
      .then(([c, s]) => {
        setCandidates(c);
        setSummary(s);
      })
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }

  useEffect(refresh, []);

  async function withBusy(fn: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      refresh();
      return true;
    } catch (e) {
      setError((e as Error).message);
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function handleSubmitOffer() {
    if (!offerVehicle.trim() || !offerBuyer.trim() || !offerAmount) return;
    if (!await withBusy(() => submitOffer(offerVehicle.trim().toUpperCase(), offerBuyer, parseFloat(offerAmount)))) return;
    setOfferVehicle(""); setOfferBuyer(""); setOfferAmount("");
    setTab("offers");
  }

  async function handleMarkSold(offer: WholesaleOffer) {
    const amt = offer.counter_amount ?? offer.offer_amount;
    await withBusy(() => markWholesaleSold(offer.vehicle_id, offer.buyer_name, amt, offer.id));
  }

  async function handleRecordFunds() {
    if (!fundsVehicle.trim() || !fundsAmount) return;
    if (!await withBusy(() => recordFundsCollected(fundsVehicle.trim().toUpperCase(), parseFloat(fundsAmount), fundsMethod))) return;
    setFundsVehicle(""); setFundsAmount(""); setFundsMethod("");
  }

  return (
    <div className={tc(theme, "work-inventory-board", "work-inventory-board")}>
      <div className={tc(theme, "work-inventory-stats", "work-inventory-stats")}>
        <Kpi theme={theme} label="Wholesale Candidates" value={String(candidates?.wholesale_candidates.count || 0)} color={RIBBON[0]} />
        <Kpi theme={theme} label="Open Offers" value={String(summary?.open_offers.count || 0)} color={RIBBON[1]} />
        <Kpi theme={theme} label="Sold Wholesale" value={String(summary?.sold_wholesale_units.count || 0)} color={RIBBON[2]} />
        <Kpi theme={theme} label="Awaiting Funds" value={String(summary?.fund_collection.awaiting_collection.count || 0)} color={RIBBON[3]} />
      </div>

      <div className="flex items-center gap-1.5 px-4 py-2 border-b border-zinc-800">
        {([
          ["candidates", "Candidates"],
          ["offers", "Offers"],
          ["sold", "Sold Wholesale"],
          ["funds", "Fund Collection"],
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

      {error && <div className="mx-4 mt-3 text-xs px-3 py-2 rounded-lg bg-red-500/15 border border-red-500/40 text-red-300">{error}</div>}

      <div className="flex-1 p-4">
        {loading ? (
          <div className="text-sm text-zinc-500">Loading…</div>
        ) : tab === "candidates" ? (
          <RecordTable label="Wholesale candidates"><thead><tr><th>Vehicle</th><th>Margin</th><th>Next step</th></tr></thead><tbody>{candidates?.wholesale_candidates.candidates.map(c=><tr key={c.vehicle_id}><td><strong>{c.year} {c.make} {c.model}</strong><span className="work-record-meta">{c.vehicle_id}</span></td><td>{c.margin_pct!==null?`${(c.margin_pct*100).toFixed(1)}%`:"Not available"} ({money(c.margin)})</td><td><WorkButton onClick={()=>{setOfferVehicle(c.vehicle_id);setTab("offers");}}>Prepare offer</WorkButton></td></tr>)}</tbody></RecordTable>
        ) : tab === "offers" ? (
          <div className="space-y-3">
            <div className={cardClass}>
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Submit New Offer</div>
              <div className="grid grid-cols-3 gap-1.5 mb-2">
                <WorkField label="Vehicle ID (VEH-...)"><WorkInput value={offerVehicle} onChange={(e) => setOfferVehicle(e.target.value)} placeholder="Vehicle ID (VEH-...)" className={`rounded-md border px-2 py-1.5 text-xs ${textClass}`} /></WorkField>
                <WorkField label="Buyer name"><WorkInput value={offerBuyer} onChange={(e) => setOfferBuyer(e.target.value)} placeholder="Buyer name" className={`rounded-md border px-2 py-1.5 text-xs ${textClass}`} /></WorkField>
                <WorkField label="Offer amount ($)"><WorkInput value={offerAmount} onChange={(e) => setOfferAmount(e.target.value)} type="number" placeholder="Offer amount ($)" className={`rounded-md border px-2 py-1.5 text-xs ${textClass}`} /></WorkField>
              </div>
              <WorkButton type="submit" variant="primary" disabled={busy} onClick={handleSubmitOffer} className="text-xs px-2.5 py-1.5 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50">Submit Offer</WorkButton>
            </div>
            <RecordTable label="Wholesale offers"><thead><tr><th>Vehicle</th><th>Buyer</th><th>Offer</th><th>Status</th><th>Actions</th></tr></thead><tbody>{summary?.open_offers.offers.map(o=><tr key={o.id}><td>{o.vehicle_id}</td><td>{o.buyer_name}</td><td>{money(o.counter_amount||o.offer_amount)}</td><td>{o.status}</td><td><details><summary>Review offer</summary><OfferCard theme={theme} offer={o} busy={busy} onAccept={()=>withBusy(()=>acceptOffer(o.id))} onReject={notes=>withBusy(()=>rejectOffer(o.id,notes))} onCounter={amt=>withBusy(()=>counterOffer(o.id,amt))} onWithdraw={()=>withBusy(()=>withdrawOffer(o.id))} onMarkSold={()=>handleMarkSold(o)}/></details></td></tr>)}</tbody></RecordTable>
          </div>
        ) : tab === "sold" ? (
          <RecordTable label="Wholesale sales"><thead><tr><th>Vehicle</th><th>Buyer</th><th>Sale price</th><th>Sold</th><th>Funds</th></tr></thead><tbody>{summary?.sold_wholesale_units.vehicles.map(v=><tr key={v.vehicle_id}><td>{v.year} {v.make} {v.model}</td><td>{v.wholesale_sale.buyer_name}</td><td>{money(v.wholesale_sale.sale_price)}</td><td>{fmt(v.wholesale_sale.sold_at)}</td><td>{v.wholesale_sale.funds_collected?"Collected":"Awaiting funds"}</td></tr>)}</tbody></RecordTable>
        ) : (
          <div className="space-y-3">
            <div className={cardClass}>
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Record Funds Collected</div>
              <div className="grid grid-cols-3 gap-1.5 mb-2">
                <WorkField label="Vehicle ID (VEH-...)"><WorkInput value={fundsVehicle} onChange={(e) => setFundsVehicle(e.target.value)} placeholder="Vehicle ID (VEH-...)" className={`rounded-md border px-2 py-1.5 text-xs ${textClass}`} /></WorkField>
                <WorkField label="Amount ($)"><WorkInput value={fundsAmount} onChange={(e) => setFundsAmount(e.target.value)} type="number" placeholder="Amount ($)" className={`rounded-md border px-2 py-1.5 text-xs ${textClass}`} /></WorkField>
                <WorkField label="Method (wire, check…)"><WorkInput value={fundsMethod} onChange={(e) => setFundsMethod(e.target.value)} placeholder="Method (wire, check…)" className={`rounded-md border px-2 py-1.5 text-xs ${textClass}`} /></WorkField>
              </div>
              <WorkButton type="submit" variant="primary" disabled={busy} onClick={handleRecordFunds} className="text-xs px-2.5 py-1.5 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50">Record Funds Collected</WorkButton>
            </div>
            <div>
              <div className="text-xs font-brand uppercase tracking-wide text-amber-400 mb-1.5">Awaiting Collection ({summary?.fund_collection.awaiting_collection.count || 0}) — {money(summary?.fund_collection.awaiting_collection.total_amount)}</div>
              <RecordTable label="Awaiting collection"><thead><tr><th>Vehicle</th><th>Buyer</th><th>Amount</th></tr></thead><tbody>{summary?.fund_collection.awaiting_collection.vehicles.map(v=><tr key={v.vehicle_id}><td>{v.year} {v.make} {v.model}</td><td>{v.wholesale_sale.buyer_name}</td><td>{money(v.wholesale_sale.sale_price)}</td></tr>)}</tbody></RecordTable>
            </div>
            <div>
              <div className="text-xs font-brand uppercase tracking-wide text-green-400 mb-1.5">Collected ({summary?.fund_collection.collected.count || 0}) — {money(summary?.fund_collection.collected.total_amount)}</div>
              <RecordTable label="Collected funds"><thead><tr><th>Vehicle</th><th>Buyer</th><th>Amount</th><th>Method</th><th>Collected</th></tr></thead><tbody>{summary?.fund_collection.collected.vehicles.map(v=><tr key={v.vehicle_id}><td>{v.year} {v.make} {v.model}</td><td>{v.wholesale_sale.buyer_name}</td><td>{money(v.wholesale_sale.sale_price)}</td><td>{v.wholesale_sale.funds_collected?.method}</td><td>{fmt(v.wholesale_sale.funds_collected?.collected_at)}</td></tr>)}</tbody></RecordTable>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
