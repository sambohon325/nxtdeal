"use client";

// The real, public, unauthenticated Pre-Visit Check-In page -- a customer's
// own real shareable link (core/appointment_scheduling.py's
// generate_checkin_link()) landing here to confirm their upcoming
// appointment and share a couple of pre-visit details (drop off vs. wait,
// contact preference, a note) before they arrive. Same unauthenticated-page
// convention as app/approve/[token]/page.tsx: no NXTDeal chrome, no auth
// headers on any call here.
import { useEffect, useState, useCallback } from "react";
import { useParams } from "next/navigation";
import {
  publicGetCheckinView,
  publicSubmitCheckin,
  type PublicCheckinView,
  type DropOffOrWait,
} from "@/lib/appointmentScheduling";

function fmt(v: string | null): string {
  if (!v) return "";
  try {
    return new Date(v).toLocaleString();
  } catch {
    return v;
  }
}

export default function PublicCheckinPage() {
  const params = useParams();
  const token = String(params?.token ?? "");

  const [view, setView] = useState<PublicCheckinView | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [dropOffOrWait, setDropOffOrWait] = useState<DropOffOrWait>("wait");
  const [contactPreference, setContactPreference] = useState("");
  const [notes, setNotes] = useState("");

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    setError(null);
    publicGetCheckinView(token)
      .then(setView)
      .catch((e) => setError(e instanceof Error ? e.message : "This link isn't available."))
      .finally(() => setLoading(false));
  }, [token]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleSubmit() {
    setSubmitting(true);
    setError(null);
    try {
      const updated = await publicSubmitCheckin(token, dropOffOrWait, contactPreference, notes);
      setView(updated);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong submitting your check-in.");
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
          <div className="font-bold text-lg">Pre-Visit Check-In</div>
          <div className="text-sm text-zinc-500">{view.department} · {fmt(view.scheduled_start)}</div>
        </div>
      </header>

      <main className="max-w-2xl mx-auto px-6 py-8 space-y-6">
        {view.revoked && (
          <div className="rounded-md border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-800">
            This check-in link has been revoked. Please contact the dealership if you have questions about your appointment.
          </div>
        )}

        <div className="rounded-lg border border-zinc-200 p-5">
          <div className="text-xs uppercase tracking-wide text-zinc-500 mb-1">Name</div>
          <div className="text-sm mb-4">{view.person_name ?? "—"}</div>

          {view.vehicle && (
            <>
              <div className="text-xs uppercase tracking-wide text-zinc-500 mb-1">Vehicle</div>
              <div className="text-sm mb-4">{view.vehicle}</div>
            </>
          )}

          <div className="text-xs uppercase tracking-wide text-zinc-500 mb-1">Appointment Time</div>
          <div className="text-lg font-semibold mb-1">{fmt(view.scheduled_start)}</div>
          <div className="text-xs text-zinc-500">Status: {view.status}</div>
        </div>

        {error && (
          <div className="rounded-md border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
        )}

        {view.checkin ? (
          <div className="rounded-lg border border-green-300 bg-green-50 p-5 text-sm text-green-800">
            ✅ Checked in on {fmt(view.checkin.submitted_at)} -- {view.checkin.drop_off_or_wait === "wait" ? "waiting on-site" : "dropping off the vehicle"}
            {view.checkin.notes ? ` · "${view.checkin.notes}"` : ""}
          </div>
        ) : view.revoked ? null : (
          <div className="rounded-lg border border-zinc-200 p-5 space-y-3">
            <div className="text-sm text-zinc-600">Let us know a couple of things before you arrive.</div>

            <div>
              <div className="text-xs uppercase tracking-wide text-zinc-500 mb-1.5">Will you wait, or drop off the vehicle?</div>
              <div className="flex items-center gap-3">
                <label className="flex items-center gap-1.5 text-sm">
                  <input type="radio" checked={dropOffOrWait === "wait"} onChange={() => setDropOffOrWait("wait")} /> I&apos;ll wait
                </label>
                <label className="flex items-center gap-1.5 text-sm">
                  <input type="radio" checked={dropOffOrWait === "drop_off"} onChange={() => setDropOffOrWait("drop_off")} /> I&apos;m dropping off
                </label>
              </div>
            </div>

            <div>
              <div className="text-xs uppercase tracking-wide text-zinc-500 mb-1.5">Preferred contact method (optional)</div>
              <input
                maxLength={200}
                value={contactPreference}
                onChange={(e) => setContactPreference(e.target.value)}
                placeholder="e.g. text this number, call, email…"
                className="w-full rounded-md border border-zinc-300 px-3 py-2 text-sm"
              />
            </div>

            <div>
              <div className="text-xs uppercase tracking-wide text-zinc-500 mb-1.5">Anything else we should know? (optional)</div>
              <input
                maxLength={2000}
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="e.g. running 10 minutes late…"
                className="w-full rounded-md border border-zinc-300 px-3 py-2 text-sm"
              />
            </div>

            <button
              disabled={submitting}
              onClick={handleSubmit}
              className="px-4 py-2 rounded-md bg-blue-600 text-white text-sm font-medium hover:opacity-90 transition disabled:opacity-50"
            >
              Check In
            </button>
          </div>
        )}
      </main>

      <footer className="text-xs text-zinc-400 text-center py-8">Powered by NXTDeal</footer>
    </div>
  );
}
