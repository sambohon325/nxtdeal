"use client";

// My Garage "Approvals" — the verified customer's repair-order estimates that need a
// decision (approve / decline) or, once approved, a payment. Behind CustomerVerifyGate,
// reads/writes the token-scoped /public/garage/approvals endpoints (core/garage.py). Every
// action re-checks server-side that the RO is on the caller's account before touching it.
// Payment is honestly labeled "simulated" until a payments provider is connected.

import { useRef, useState } from "react";
import { type AppDef, type AppScreen, accentOf } from "@/lib/apps/registry";
import {
  getMyApprovals,
  respondToApproval,
  payMyRo,
  type GarageApprovalsView,
  type GarageApprovalItem,
} from "@/lib/garage";
import { CustomerVerifyGate } from "@/components/apps/CustomerVerifyGate";
import { useAsync, ListCard, EmptyNote } from "./kit";

function money(v: number | null): string {
  return v === null || v === undefined ? "—" : `$${Math.round(v).toLocaleString()}`;
}

function Card({ item, onChanged }: { item: GarageApprovalItem; onChanged: (notice?: string) => void }) {
  const inFlight = useRef(false);
  const [busy, setBusy] = useState<null | "approve" | "decline" | "pay">(null);
  const [err, setErr] = useState<string | null>(null);
  const [declining, setDeclining] = useState(false);
  const [reason, setReason] = useState("");

  async function run(kind: "approve" | "decline" | "pay") {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(kind);
    setErr(null);
    try {
      let notice: string;
      if (kind === "pay") {
        const result = await payMyRo(item.ro_id);
        if (!result.ok) throw new Error("Unconfirmed payment");
        notice = result.mode === "simulated"
          ? "Demo payment recorded — no money was collected. Confirm the balance with the service desk."
          : "Payment recorded. Confirm the receipt with the service desk.";
      } else {
        const result = await respondToApproval(item.ro_id, kind === "approve", reason);
        if (!result.ok) throw new Error("Unconfirmed response");
        notice = kind === "approve" ? "Estimate approval recorded." : "Estimate decline recorded.";
      }
      onChanged(notice);
    } catch {
      inFlight.current = false;
      setErr("This action could not be confirmed. Refresh your records or check with the service desk before retrying.");
      setBusy(null);
    }
  }

  const pending = item.estimate_status === "pending";
  const approvedUnpaid = item.estimate_status === "approved" && !item.paid;

  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.05] p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-white">{item.vehicle}</div>
          <div className="truncate text-[11px] text-zinc-500">
            {item.description || "Repair order"} · #{item.service_number}
          </div>
        </div>
        <div className="shrink-0 text-right">
          <div className="text-lg font-bold text-white">{money(item.estimate_amount)}</div>
          <div className="text-[10px] uppercase tracking-wide text-zinc-500">
            {pending ? "Needs approval" : "Approved · unpaid"}
          </div>
        </div>
      </div>

      {item.concerns.length > 0 && (
        <ul className="mt-2 space-y-0.5">
          {item.concerns.map((c, i) => (
            <li key={i} className="text-[11px] text-zinc-400">• {c.description}</li>
          ))}
        </ul>
      )}

      {err && <div role="alert" className="mt-2 rounded-lg bg-red-500/10 px-2.5 py-1.5 text-[11px] text-red-300">{err}<button onClick={() => onChanged()} className="ml-2 underline">Refresh records</button></div>}

      {declining ? (
        <div className="mt-3 space-y-2">
          <textarea
            aria-label="Decline reason (optional)"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Reason (optional)"
            rows={2}
            className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white placeholder-zinc-500 focus:border-[var(--app-accent)] focus:outline-none"
          />
          <div className="flex gap-2">
            <button
              onClick={() => run("decline")}
              disabled={busy !== null}
              className="flex-1 rounded-lg bg-red-500/80 px-3 py-2 text-[12px] font-semibold text-white disabled:opacity-50"
            >
              {busy === "decline" ? "Declining…" : "Confirm decline"}
            </button>
            <button
              onClick={() => { setDeclining(false); setReason(""); }}
              disabled={busy !== null}
              className="rounded-lg border border-white/10 px-3 py-2 text-[12px] text-zinc-300 disabled:opacity-50"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <div className="mt-3 flex gap-2">
          {pending && (
            <>
              <button
                onClick={() => run("approve")}
                disabled={busy !== null}
                className="flex-1 rounded-lg bg-emerald-500/90 px-3 py-2 text-[12px] font-semibold text-white disabled:opacity-50"
              >
                {busy === "approve" ? "Approving…" : "Approve"}
              </button>
              <button
                onClick={() => setDeclining(true)}
                disabled={busy !== null}
                className="rounded-lg border border-white/10 px-3 py-2 text-[12px] text-zinc-300 disabled:opacity-50"
              >
                Decline
              </button>
            </>
          )}
          {approvedUnpaid && (
            <button
              onClick={() => run("pay")}
              disabled={busy !== null}
              className="flex-1 rounded-lg bg-emerald-500/90 px-3 py-2 text-[12px] font-semibold text-white disabled:opacity-50"
            >
              {busy === "pay" ? "Processing…" : `Pay ${money(item.estimate_amount)}`}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function Inner({ app }: { app: AppDef }) {
  const accent = accentOf(app);
  const [notice, setNotice] = useState<string | null>(null);
  const { loading, error, data, reload } = useAsync<GarageApprovalsView>(() => getMyApprovals(), []);
  function changed(message?: string) {
    if (message) setNotice(message);
    reload();
  }

  if (loading) {
    return <div className="flex justify-center py-12"><div className={`h-6 w-6 animate-spin rounded-full border-2 border-white/15 ${accent.text} border-t-current`} /></div>;
  }
  if (error) {
    return (
      <div className="rounded-2xl border border-white/10 bg-white/[0.05] p-4 text-center">
        {notice && <p role="status" className="mb-2 text-sm text-[var(--app-accent)]">{notice}</p>}
        <p role="alert" className="text-sm text-zinc-300">We couldn&apos;t load your approvals.</p>
        <button onClick={reload} className="mt-2 text-sm text-[var(--app-accent)] underline">Try again</button>
      </div>
    );
  }
  if (!data) return null;

  return (
    <div className="space-y-3">
      {notice && <p role="status" className="text-sm text-[var(--app-accent)]">{notice}</p>}
      {data.count === 0 ? (
        <ListCard title="Approvals" count={0}>
          <EmptyNote>Nothing needs your approval right now.</EmptyNote>
        </ListCard>
      ) : (
        <>
          <div className="text-[11px] text-zinc-400">Amounts shown are the dealership&apos;s estimate. Payment processing may be simulated; a saved record does not prove money was collected. Confirm payment with the service desk.</div>
          {data.approvals.map((a) => (
            <Card key={a.ro_id} item={a} onChanged={changed} />
          ))}
        </>
      )}
    </div>
  );
}

export function MyGarageApprovals({ app, screen }: { app: AppDef; screen: AppScreen }) {
  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-xl font-bold text-white">{screen.heading}</h2>
        <p className="mt-0.5 text-sm text-zinc-400">{screen.intro}</p>
      </div>
      <CustomerVerifyGate what="your repair-order estimates and approvals">
        <Inner app={app} />
      </CustomerVerifyGate>
    </div>
  );
}
