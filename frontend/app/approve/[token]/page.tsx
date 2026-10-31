"use client";

// The real, public, unauthenticated Customer-Facing Approval Center page --
// a customer's own real shareable link (core/approval_center.py's
// generate_approval_link()) landing here to review an RO's estimate,
// open concerns, and any flagged DVI findings, and approve or decline it
// themselves -- no staff member recording the decision on their behalf.
// Same unauthenticated-page convention as app/site/[id]/page.tsx: no
// NXTDeal chrome, no BrandRibbon, no auth headers on any call here.
import { useEffect, useState, useCallback } from "react";
import { useParams } from "next/navigation";
import {
  publicGetApprovalView,
  publicRecordApprovalDecision,
  type PublicApprovalView,
} from "@/lib/approvalCenter";

function money(v: number | null): string {
  if (v === null || v === undefined) return "—";
  return `$${v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function fmt(v: string | null): string {
  if (!v) return "";
  try {
    return new Date(v).toLocaleString();
  } catch {
    return v;
  }
}

export default function PublicApprovalPage() {
  const params = useParams();
  const token = String(params?.token ?? "");

  const [view, setView] = useState<PublicApprovalView | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [declineReason, setDeclineReason] = useState("");
  const [showDecline, setShowDecline] = useState(false);

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    setError(null);
    publicGetApprovalView(token)
      .then(setView)
      .catch((e) => setError(e instanceof Error ? e.message : "This link isn't available."))
      .finally(() => setLoading(false));
  }, [token]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleApprove() {
    setSubmitting(true);
    setError(null);
    try {
      const updated = await publicRecordApprovalDecision(token, true);
      setView(updated);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong recording your decision.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDecline() {
    if (!declineReason.trim()) {
      setError("Please let us know why so we can follow up.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const updated = await publicRecordApprovalDecision(token, false, declineReason);
      setView(updated);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong recording your decision.");
    } finally {
      setSubmitting(false);
    }
  }

  if (loading && !view) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-white text-zinc-400 text-sm">
        Loading…
      </div>
    );
  }

  if (!view) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-white text-center px-6">
        <div>
          <div className="text-lg font-semibold text-zinc-800 mb-2">This link isn&apos;t available</div>
          <div className="text-sm text-zinc-500">{error ?? "It may have expired or been revoked."}</div>
        </div>
      </div>
    );
  }

  const est = view.estimate;
  const alreadyDecided = est.approved !== null;

  return (
    <div className="min-h-screen bg-white text-zinc-900">
      <header className="border-b border-zinc-200">
        <div className="max-w-2xl mx-auto px-6 py-4">
          <div className="font-bold text-lg">Service Estimate Approval</div>
          <div className="text-sm text-zinc-500">RO {view.service_number}{view.vehicle ? ` · ${view.vehicle}` : ""}</div>
        </div>
      </header>

      <main className="max-w-2xl mx-auto px-6 py-8 space-y-6">
        {view.revoked && (
          <div className="rounded-md border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-800">
            This approval link has been revoked. Please contact the dealership if you have questions about this repair order.
          </div>
        )}

        <div className="rounded-lg border border-zinc-200 p-5">
          <div className="text-xs uppercase tracking-wide text-zinc-500 mb-1">Customer</div>
          <div className="text-sm mb-4">{view.customer_name ?? "—"}</div>

          <div className="text-xs uppercase tracking-wide text-zinc-500 mb-1">Description</div>
          <div className="text-sm mb-4">{view.description || "—"}</div>

          {view.open_concerns.length > 0 && (
            <>
              <div className="text-xs uppercase tracking-wide text-zinc-500 mb-1">Concerns</div>
              <ul className="text-sm mb-4 list-disc list-inside space-y-0.5">
                {view.open_concerns.map((c, i) => (
                  <li key={i}>{c.description}</li>
                ))}
              </ul>
            </>
          )}

          {view.flagged_inspection_findings.length > 0 && (
            <>
              <div className="text-xs uppercase tracking-wide text-zinc-500 mb-1">Inspection Findings</div>
              <ul className="text-sm mb-4 space-y-1">
                {view.flagged_inspection_findings.map((f, i) => (
                  <li key={i} className="flex items-start gap-2">
                    <span className={f.status === "red" ? "text-red-600" : "text-amber-500"}>●</span>
                    <span>
                      <span className="font-medium">{f.item}</span>
                      {f.notes ? ` — ${f.notes}` : ""}
                    </span>
                  </li>
                ))}
              </ul>
            </>
          )}

          <div className="text-xs uppercase tracking-wide text-zinc-500 mb-1">Estimate</div>
          <div className="text-2xl font-semibold mb-1">{money(est.amount)}</div>
          <div className="text-xs text-zinc-500">Sent {fmt(est.sent_at)}</div>
        </div>

        {error && (
          <div className="rounded-md border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
        )}

        {alreadyDecided ? (
          <div className={`rounded-lg border p-5 text-sm ${est.approved ? "border-green-300 bg-green-50 text-green-800" : "border-red-300 bg-red-50 text-red-800"}`}>
            {est.approved ? (
              <>✅ Approved{est.decided_at ? ` on ${fmt(est.decided_at)}` : ""}{est.decided_by_customer ? " by you" : " by the dealership"}.</>
            ) : (
              <>❌ Declined{est.decided_at ? ` on ${fmt(est.decided_at)}` : ""}{est.decline_reason ? ` — ${est.decline_reason}` : ""}.</>
            )}
          </div>
        ) : view.revoked ? null : (
          <div className="rounded-lg border border-zinc-200 p-5 space-y-3">
            <div className="text-sm text-zinc-600">Please review the estimate above and let us know how you&apos;d like to proceed.</div>
            <div className="flex items-center gap-3">
              <button
                disabled={submitting}
                onClick={handleApprove}
                className="px-4 py-2 rounded-md bg-green-600 text-white text-sm font-medium hover:opacity-90 transition disabled:opacity-50"
              >
                Approve Estimate
              </button>
              <button
                disabled={submitting}
                onClick={() => setShowDecline((s) => !s)}
                className="px-4 py-2 rounded-md border border-zinc-300 text-sm font-medium hover:bg-zinc-50 transition disabled:opacity-50"
              >
                Decline
              </button>
            </div>
            {showDecline && (
              <div className="flex items-center gap-2 pt-1">
                <input
                  value={declineReason}
                  onChange={(e) => setDeclineReason(e.target.value)}
                  placeholder="Please tell us why…"
                  className="flex-1 rounded-md border border-zinc-300 px-3 py-2 text-sm"
                />
                <button
                  disabled={submitting}
                  onClick={handleDecline}
                  className="px-3 py-2 rounded-md bg-red-600 text-white text-sm font-medium hover:opacity-90 transition disabled:opacity-50"
                >
                  Submit Decline
                </button>
              </div>
            )}
          </div>
        )}
      </main>

      <footer className="text-xs text-zinc-400 text-center py-8">Powered by NXTDeal</footer>
    </div>
  );
}
