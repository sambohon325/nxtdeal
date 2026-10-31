"use client";

// The real, public, unauthenticated Customer Payment Portal -- a customer's own
// real shareable link (core/payments.py's generate_payment_portal_link()) landing
// here to view their balance, make a payment, see auto-draft status, and request a
// payoff. Same unauthenticated-page convention as app/approve/[token]/page.tsx and
// app/checkin/[token]/page.tsx: no NXTDeal chrome, no auth headers on any call here.
import { useEffect, useState, useCallback } from "react";
import { useParams } from "next/navigation";
import {
  publicGetPortalView,
  publicSubmitPayment,
  publicSubmitPayoffRequest,
  PAYMENT_METHODS,
  type PublicPortalView,
  type PaymentMethod,
} from "@/lib/payments";

function money(v: number | string | null | undefined): string {
  if (v === null || v === undefined || v === "") return "—";
  const n = typeof v === "string" ? parseFloat(v) : v;
  if (Number.isNaN(n)) return String(v);
  return `$${n.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}

export default function PublicPaymentPortalPage() {
  const params = useParams();
  const token = String(params?.token ?? "");

  const [view, setView] = useState<PublicPortalView | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [amount, setAmount] = useState("");
  const [method, setMethod] = useState<PaymentMethod>("debit_card");
  const [payoffRequested, setPayoffRequested] = useState(false);
  const [confirmation, setConfirmation] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    setError(null);
    publicGetPortalView(token)
      .then(setView)
      .catch((e) => setError(e instanceof Error ? e.message : "This link isn't available."))
      .finally(() => setLoading(false));
  }, [token]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleSubmitPayment() {
    if (!amount) return;
    setSubmitting(true);
    setError(null);
    setConfirmation(null);
    try {
      const updated = await publicSubmitPayment(token, parseFloat(amount), method);
      setView(updated);
      setAmount("");
      setConfirmation("Payment submitted.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong submitting your payment.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleRequestPayoff() {
    setSubmitting(true);
    setError(null);
    try {
      await publicSubmitPayoffRequest(token, "Requested via customer payment portal");
      setPayoffRequested(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong requesting your payoff.");
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

  return (
    <div className="min-h-screen bg-white text-zinc-900">
      <header className="border-b border-zinc-200">
        <div className="max-w-2xl mx-auto px-6 py-4">
          <div className="font-bold text-lg">Payment Portal</div>
          <div className="text-sm text-zinc-500">{view.finance_number} · {view.customer_name}</div>
        </div>
      </header>

      <main className="max-w-2xl mx-auto px-6 py-8 space-y-6">
        {view.revoked && (
          <div className="rounded-md border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-800">
            This payment link has been revoked. Please contact the dealership if you have questions about your account.
          </div>
        )}

        <div className="rounded-lg border border-zinc-200 p-5">
          <div className="text-xs uppercase tracking-wide text-zinc-500 mb-1">Vehicle</div>
          <div className="text-sm mb-4">{view.vehicle || "—"}</div>

          <div className="text-xs uppercase tracking-wide text-zinc-500 mb-1">Current Balance</div>
          <div className="text-2xl font-semibold mb-1">{money(view.balance)}</div>
          <div className="text-[11px] text-zinc-400 mb-4">
            {view.balance_basis === "real_payment_ledger" ? "Based on your actual recorded payment history." : "Estimated from your original contract terms (no payments recorded yet)."}
          </div>

          <div className="text-xs uppercase tracking-wide text-zinc-500 mb-1">Monthly Payment</div>
          <div className="text-lg">{money(view.monthly_payment)}</div>
        </div>

        {error && (
          <div className="rounded-md border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
        )}
        {confirmation && (
          <div className="rounded-md border border-green-300 bg-green-50 px-4 py-3 text-sm text-green-800">{confirmation}</div>
        )}

        {!view.revoked && (
          <div className="rounded-lg border border-zinc-200 p-5 space-y-3">
            <div className="text-sm font-semibold">Make a Payment</div>
            <div className="flex items-center gap-2">
              <input
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                type="number"
                placeholder="Amount ($)"
                className="w-32 rounded-md border border-zinc-300 px-3 py-2 text-sm"
              />
              <select value={method} onChange={(e) => setMethod(e.target.value as PaymentMethod)} className="rounded-md border border-zinc-300 px-3 py-2 text-sm">
                {PAYMENT_METHODS.map((m) => <option key={m} value={m}>{m.replace(/_/g, " ")}</option>)}
              </select>
              <button
                disabled={submitting || !amount}
                onClick={handleSubmitPayment}
                className="px-4 py-2 rounded-md bg-blue-600 text-white text-sm font-medium hover:opacity-90 transition disabled:opacity-50"
              >
                Pay
              </button>
            </div>
          </div>
        )}

        <div className="rounded-lg border border-zinc-200 p-5">
          <div className="text-sm font-semibold mb-2">Recent Payments</div>
          {view.recent_payments.length === 0 ? (
            <div className="text-sm text-zinc-500">No payments on file yet.</div>
          ) : (
            <div className="space-y-1">
              {view.recent_payments.slice().reverse().map((p, i) => (
                <div key={i} className="flex items-center justify-between text-sm">
                  <span>{p.payment_date} · {p.method.replace(/_/g, " ")} · {p.status}</span>
                  <span>{money(p.amount)}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {view.active_auto_drafts.length > 0 && (
          <div className="rounded-lg border border-zinc-200 p-5">
            <div className="text-sm font-semibold mb-2">Auto Pay</div>
            {view.active_auto_drafts.map((d) => (
              <div key={d.id} className="text-sm">{money(d.amount)}/mo via {d.method.replace(/_/g, " ")}, on the {d.day_of_month}{d.day_of_month === 1 ? "st" : d.day_of_month === 2 ? "nd" : d.day_of_month === 3 ? "rd" : "th"} of each month.</div>
            ))}
          </div>
        )}

        {!view.revoked && (
          <div className="rounded-lg border border-zinc-200 p-5">
            <div className="text-sm font-semibold mb-2">Payoff Request</div>
            {payoffRequested ? (
              <div className="text-sm text-green-700">Your payoff request has been sent to the dealership.</div>
            ) : (
              <button
                disabled={submitting}
                onClick={handleRequestPayoff}
                className="px-4 py-2 rounded-md bg-zinc-800 text-white text-sm font-medium hover:opacity-90 transition disabled:opacity-50"
              >
                Request Payoff Amount
              </button>
            )}
          </div>
        )}

        <div className="text-xs text-zinc-400 text-center space-y-1">
          {Object.values(view.not_yet_tracked).map((note, i) => <div key={i}>{note}</div>)}
        </div>
      </main>

      <footer className="text-xs text-zinc-400 text-center py-8">Powered by NXTDeal</footer>
    </div>
  );
}
