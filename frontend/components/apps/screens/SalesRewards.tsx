"use client";

// SalesRewards — the MySales "Rewards" screen (2026-07-24, Sam: rewards for getting your
// dealership to book a NXTDeal demo / convert, plus a referral code to recruit other reps).
// Reads the rep's referral summary (/referrals/me), lets them submit a dealership referral,
// and shows their shareable code + a live tracker of pending vs earned rewards.

import { useState } from "react";
import { type AppDef, type AppScreen, accentOf } from "@/lib/apps/registry";
import {
  fetchMyReferrals,
  submitDealershipReferral,
  type ReferralSummary,
  type Referral,
} from "@/lib/referrals";
import { useAsync, WiredScreen, StatGrid } from "./kit";

function money(n: number): string {
  return `$${(n ?? 0).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
}

const STATUS_STYLE: Record<string, string> = {
  submitted: "bg-white/10 text-zinc-300",
  contacted: "bg-sky-500/15 text-sky-300",
  demo_scheduled: "bg-violet-500/15 text-violet-300",
  converted: "bg-amber-500/15 text-amber-300",
  joined: "bg-white/10 text-zinc-300",
  active: "bg-sky-500/15 text-sky-300",
  rewarded: "bg-emerald-500/15 text-emerald-300",
  declined: "bg-red-500/15 text-red-300",
};

export function SalesRewards({ app, screen }: { app: AppDef; screen: AppScreen }) {
  const accent = accentOf(app);
  const { loading, error, data, reload } = useAsync<ReferralSummary>(() => fetchMyReferrals(), []);

  const [copied, setCopied] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [kind, setKind] = useState<"dealership_demo" | "dealership_conversion">("dealership_demo");
  const [name, setName] = useState("");
  const [contact, setContact] = useState("");
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  async function submit() {
    if (!name.trim() || busy) return;
    setBusy(true);
    setFormError(null);
    try {
      await submitDealershipReferral({ kind, dealership_name: name.trim(), contact_name: contact.trim() || undefined });
      setName("");
      setContact("");
      setShowForm(false);
      reload();
    } catch (e) {
      setFormError(e instanceof Error ? e.message : "Couldn't submit that referral.");
    } finally {
      setBusy(false);
    }
  }

  function copyCode(code: string) {
    try {
      navigator.clipboard?.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* ignore */
    }
  }

  return (
    <WiredScreen app={app} screen={screen} loading={loading} error={error} empty={!data}>
      {data && (
        <>
          <StatGrid
            app={app}
            stats={[
              { label: "Earned", value: money(data.totals.earned) },
              { label: "Pending", value: money(data.totals.pending) },
              { label: "Recruits", value: data.totals.recruits },
              { label: "Store referrals", value: data.totals.dealership_referrals },
            ]}
          />

          {/* Shareable code */}
          <div className="rounded-2xl border border-white/10 bg-white/[0.05] p-4 backdrop-blur-sm">
            <div className="text-[11px] uppercase tracking-wide text-zinc-500">Your referral code</div>
            <div className="mt-1 flex items-center gap-3">
              <span className={`text-2xl font-bold tracking-[0.2em] ${accent.text}`}>{data.code}</span>
              <button
                onClick={() => copyCode(data.code)}
                className="rounded-full border border-white/15 px-3 py-1 text-xs text-zinc-200 transition hover:bg-white/10"
              >
                {copied ? "Copied" : "Copy"}
              </button>
            </div>
            <p className="mt-1.5 text-[11px] text-zinc-500">
              Share it with other salespeople — you earn {money(data.tiers.rep_recruit?.reward ?? 0)} when they join MySales with your code.
            </p>
          </div>

          {/* Reward tiers */}
          <div className="grid gap-2.5 sm:grid-cols-3">
            {Object.entries(data.tiers).map(([key, tier]) => (
              <div key={key} className="rounded-2xl border border-white/10 bg-white/[0.04] p-3.5 backdrop-blur-sm">
                <div className={`text-lg font-bold ${accent.text}`}>{money(tier.reward)}</div>
                <div className="mt-0.5 text-[11px] text-zinc-300">{tier.label}</div>
              </div>
            ))}
          </div>

          {/* Refer your dealership */}
          <div className="rounded-2xl border border-white/10 bg-white/[0.05] p-4 backdrop-blur-sm">
            <div className="flex items-center justify-between">
              <div className="text-sm font-semibold text-white">Refer your dealership</div>
              {!showForm && (
                <button
                  onClick={() => setShowForm(true)}
                  className="rounded-full bg-[var(--app-accent)] px-3 py-1.5 text-xs font-semibold text-[var(--app-accent-text)]"
                >
                  Start a referral
                </button>
              )}
            </div>
            {showForm && (
              <div className="mt-3 space-y-2.5">
                <div className="flex gap-2">
                  {(["dealership_demo", "dealership_conversion"] as const).map((k) => (
                    <button
                      key={k}
                      onClick={() => setKind(k)}
                      className={`flex-1 rounded-lg border px-3 py-2 text-xs font-medium ${
                        kind === k
                          ? "border-transparent bg-[var(--app-accent)] text-[var(--app-accent-text)]"
                          : "border-white/15 text-zinc-300"
                      }`}
                    >
                      {k === "dealership_demo" ? "Book a demo" : "Convert to NXTDeal"}
                    </button>
                  ))}
                </div>
                <input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Dealership name"
                  className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white placeholder-zinc-500 focus:border-[var(--app-accent)] focus:outline-none"
                />
                <input
                  value={contact}
                  onChange={(e) => setContact(e.target.value)}
                  placeholder="Who should we contact? (optional)"
                  className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white placeholder-zinc-500 focus:border-[var(--app-accent)] focus:outline-none"
                />
                {formError && <div className="text-[11px] text-red-400">{formError}</div>}
                <div className="flex gap-2">
                  <button
                    onClick={submit}
                    disabled={busy || !name.trim()}
                    className="flex-1 rounded-full bg-[var(--app-accent)] py-2 text-sm font-semibold text-[var(--app-accent-text)] disabled:opacity-40"
                  >
                    {busy ? "Submitting…" : "Submit referral"}
                  </button>
                  <button onClick={() => setShowForm(false)} className="rounded-full border border-white/15 px-4 text-sm text-zinc-300">
                    Cancel
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* Referral list */}
          <div className="rounded-2xl border border-white/10 bg-white/[0.05] p-4 backdrop-blur-sm">
            <div className="mb-2 text-sm font-semibold text-white">Your referrals</div>
            {data.referrals.length === 0 ? (
              <p className="py-4 text-center text-xs text-zinc-500">No referrals yet — refer your store or share your code.</p>
            ) : (
              <div className="space-y-2">
                {data.referrals.map((r: Referral) => (
                  <div key={r.id} className="flex items-center justify-between gap-3 rounded-lg border border-white/5 px-3 py-2">
                    <div className="min-w-0">
                      <div className="truncate text-sm text-zinc-100">{r.subject || r.label}</div>
                      <div className="text-[11px] text-zinc-500">{r.label}</div>
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      <span className={`text-xs font-semibold ${r.earned ? "text-emerald-300" : "text-zinc-400"}`}>{money(r.reward)}</span>
                      <span className={`rounded-full px-2 py-0.5 text-[9px] font-medium capitalize ${STATUS_STYLE[r.status] ?? "bg-white/10 text-zinc-300"}`}>
                        {r.status.replace(/_/g, " ")}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </WiredScreen>
  );
}
