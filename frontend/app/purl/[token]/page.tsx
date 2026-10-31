"use client";

// The real, public, unauthenticated PURL landing page -- core/purls.py's
// get_personalized_offer(). Same unauthenticated-page convention as
// app/pay/[token]/page.tsx, app/approve/[token]/page.tsx, and
// app/checkin/[token]/page.tsx: no NXTDeal chrome, no auth headers on any call
// here. Records a real visit on load (record_purl_visit) and lets the visitor
// submit themselves as a real Lead (submit_purl_lead) with no staff intermediary.
import { useEffect, useState, useCallback, useRef } from "react";
import { useParams } from "next/navigation";
import { publicGetPurlOffer, publicRecordPurlVisit, publicSubmitPurlLead, type PersonalizedOffer } from "@/lib/purls";

function money(v: number | string | null | undefined): string {
  if (v === null || v === undefined || v === "") return "—";
  const n = typeof v === "string" ? parseFloat(v) : v;
  if (Number.isNaN(n)) return String(v);
  return `$${n.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}

export default function PublicPurlPage() {
  const params = useParams();
  const token = String(params?.token ?? "");

  const [offer, setOffer] = useState<PersonalizedOffer | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [notes, setNotes] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const visitLogged = useRef(false);

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    setError(null);
    publicGetPurlOffer(token)
      .then(setOffer)
      .catch((e) => setError(e instanceof Error ? e.message : "This link isn't available."))
      .finally(() => setLoading(false));
  }, [token]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (token && !visitLogged.current) {
      visitLogged.current = true;
      publicRecordPurlVisit(token, typeof navigator !== "undefined" ? navigator.userAgent : undefined).catch(() => {});
    }
  }, [token]);

  async function handleSubmit() {
    setSubmitting(true);
    setError(null);
    try {
      await publicSubmitPurlLead(token, notes);
      setSubmitted(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong submitting your request.");
    } finally {
      setSubmitting(false);
    }
  }

  if (loading && !offer) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-white text-zinc-400 text-sm">
        Loading your personalized offer…
      </div>
    );
  }

  if (!offer || offer.error) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-white text-center px-6">
        <div>
          <div className="text-lg font-semibold text-zinc-800 mb-2">This link isn&apos;t available</div>
          <div className="text-sm text-zinc-500">{offer?.error ?? error ?? "It may have expired or been revoked."}</div>
        </div>
      </div>
    );
  }

  const alreadyDone = offer.already_submitted || submitted;

  return (
    <div className="min-h-screen bg-white text-zinc-900">
      <header className="border-b border-zinc-200">
        <div className="max-w-2xl mx-auto px-6 py-5">
          <div className="text-xs uppercase tracking-wide text-zinc-400">Just for you</div>
          <div className="text-2xl font-bold">Hi {offer.person.name || "there"} 👋</div>
        </div>
      </header>

      <main className="max-w-2xl mx-auto px-6 py-8 space-y-6">
        {offer.revoked && (
          <div className="rounded-md border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-800">
            This link is no longer active. Please contact the dealership if you have questions.
          </div>
        )}

        {offer.current_vehicles.length > 0 && (
          <div className="rounded-lg border border-zinc-200 p-5">
            <div className="text-sm font-semibold mb-2">Your Current Vehicle</div>
            {offer.current_vehicles.map((v) => (
              <div key={v.id} className="text-sm text-zinc-700">
                {v.year} {v.make} {v.model} <span className="text-zinc-400">({v.vin})</span>
              </div>
            ))}
          </div>
        )}

        {offer.trade_equity.eligible && (
          <div className="rounded-lg border border-zinc-200 p-5">
            <div className="text-sm font-semibold mb-1">Your Trade Equity Position</div>
            <div className="text-2xl font-semibold mb-1">
              {Math.round((offer.trade_equity as { pct_term_elapsed: number }).pct_term_elapsed * 100)}% of your loan term paid down
            </div>
            <div className="text-xs text-zinc-400">{(offer.trade_equity as { disclaimer: string }).disclaimer}</div>
          </div>
        )}

        {offer.payment_reduction.eligible && (
          <div className="rounded-lg border border-zinc-200 p-5">
            <div className="text-sm font-semibold mb-2">A Lower Payment Could Be Waiting</div>
            <div className="flex items-baseline gap-3 mb-1">
              <span className="text-sm text-zinc-400 line-through">
                {money((offer.payment_reduction as { current_monthly_payment: number }).current_monthly_payment)}/mo
              </span>
              <span className="text-2xl font-semibold text-emerald-600">
                {money((offer.payment_reduction as { estimated_new_monthly_payment: number }).estimated_new_monthly_payment)}/mo
              </span>
            </div>
            <div className="text-xs text-zinc-400 mb-2">{(offer.payment_reduction as { disclaimer: string }).disclaimer}</div>
          </div>
        )}

        {offer.inventory_matches.length > 0 && (
          <div className="rounded-lg border border-zinc-200 p-5">
            <div className="text-sm font-semibold mb-2">Vehicles We Think You&apos;ll Love</div>
            <div className="space-y-2">
              {offer.inventory_matches.map((v) => (
                <div key={v.id} className="flex items-center justify-between text-sm">
                  <span>
                    {v.year} {v.make} {v.model} {v.trim ?? ""}
                  </span>
                  <span className="font-medium">{money(v.price)}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {error && <div className="rounded-md border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>}

        <div className="rounded-lg border border-zinc-200 p-5">
          <div className="text-sm font-semibold mb-2">Interested? Let us know.</div>
          {alreadyDone ? (
            <div className="text-sm text-green-700">Thanks — we&apos;ve got your request and someone will reach out shortly.</div>
          ) : offer.revoked ? (
            <div className="text-sm text-zinc-500">This offer is no longer active.</div>
          ) : (
            <div className="space-y-2">
              <textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="Any details you'd like to share (optional)"
                className="w-full rounded-md border border-zinc-300 px-3 py-2 text-sm"
                rows={3}
              />
              <button
                disabled={submitting}
                onClick={handleSubmit}
                className="px-4 py-2 rounded-md bg-blue-600 text-white text-sm font-medium hover:opacity-90 transition disabled:opacity-50"
              >
                {submitting ? "Submitting…" : "Request More Info"}
              </button>
            </div>
          )}
        </div>
      </main>

      <footer className="text-xs text-zinc-400 text-center py-8">Powered by NXTDeal</footer>
    </div>
  );
}
