"use client";
import { WorkButton } from "./WorkspaceUi";

// Buy-Propensity board (Phase 1, 2026-07-25): the Behavior-Prediction-style 0-100
// leaderboard — rank customers/leads by likelihood to buy, see WHY (factor breakdown),
// draft outreach off the top signal, and run third-party enrichment. Backed by
// lib/propensity.ts (backend/api/routers/buy_propensity.py).
import { useEffect, useState } from "react";
import {
  rankPropensity,
  getPropensity,
  draftOutreach,
  enrichCustomer,
  type RankResult,
  type PropensityScore,
  type OutreachDraft,
} from "@/lib/propensity";

type Theme = "dark" | "light";
type Segment = "customers" | "leads" | "all";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

function tierColor(tier: string): string {
  return tier === "hot" ? "bg-red-500 text-white" : tier === "warm" ? "bg-brand-yellow text-black" : "bg-zinc-700 text-zinc-200";
}

export function PropensityBoard({ theme }: { theme: Theme }) {
  const [segment, setSegment] = useState<Segment>("customers");
  const [data, setData] = useState<RankResult | null>(null);
  const [selected, setSelected] = useState<PropensityScore | null>(null);
  const [draft, setDraft] = useState<OutreachDraft | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [flash, setFlash] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const card = tc(theme, "rounded-md border border-zinc-800 bg-zinc-900/60 p-3", "rounded-md border border-zinc-200 bg-white p-3");

  function refresh() {
    rankPropensity(segment)
      .then((d) => { setData(d); setError(null); })
      .catch((e) => setError(e instanceof Error ? e.message : "Couldn't load rankings."));
  }

  useEffect(refresh, [segment]);

  async function open(entityId: string) {
    setDraft(null); setFlash(null); setError(null);
    try { setSelected(await getPropensity(entityId)); }
    catch (e) { setError(e instanceof Error ? e.message : "Couldn't load score."); }
  }

  async function outreach(channel: "email" | "sms") {
    if (!selected) return;
    setBusy(true);
    try { setDraft(await draftOutreach(selected.entity_id, channel)); }
    catch (e) { setError(e instanceof Error ? e.message : "Couldn't draft outreach."); } finally { setBusy(false); }
  }

  async function enrich() {
    if (!selected || selected.entity_type !== "Customer") return;
    setBusy(true); setFlash(null);
    try {
      const r = await enrichCustomer(selected.entity_id);
      setFlash(r.mode === "live"
        ? `Enriched: appended ${r.appended_count} field(s) from ${r.provider}.`
        : "Enrichment ran — no provider connected, so nothing was appended. Connect one under Administration ▸ Connections.");
    } catch (e) { setError(e instanceof Error ? e.message : "Couldn't enrich."); } finally { setBusy(false); }
  }

  if (!data) return <div className="p-4 text-sm text-zinc-500">Loading buy signals…</div>;

  return (
    <div className="flex-1 min-h-0 flex flex-col overflow-hidden">
      <div className="px-3 pt-3 shrink-0">
        <div className="text-base font-brand">Buy Signals</div>
        <div className="text-xs text-zinc-500">
          Everyone ranked 0-100 on likelihood to buy — from real engagement, equity, loan/lease maturity, and service activity. Highest first.
        </div>
      </div>

      {error && <div className="mx-3 mt-2 rounded-md bg-red-500/10 border border-red-500/30 px-3 py-2 text-xs text-red-400">{error}</div>}
      {flash && <div className="mx-3 mt-2 rounded-md bg-brand-teal/15 border border-brand-teal/40 px-3 py-2 text-xs text-brand-teal">{flash}</div>}

      <div className="flex items-center gap-1.5 px-3 pt-3 shrink-0">
        {(["customers", "leads", "all"] as Segment[]).map((s) => (
          <WorkButton aria-pressed={segment === s} type="submit"
            key={s}
            onClick={() => { setSegment(s); setSelected(null); }}
            className={segment === s ? "text-xs px-3 py-1 rounded-full bg-brand-teal text-black capitalize" : tc(theme, "text-xs px-3 py-1 rounded-full bg-zinc-900 text-zinc-300 capitalize", "text-xs px-3 py-1 rounded-full bg-zinc-100 text-zinc-600 capitalize")}
          >
            {s}
          </WorkButton>
        ))}
        <div className="ml-auto text-xs text-zinc-500">
          {data.by_tier.hot ?? 0} hot · {data.by_tier.warm ?? 0} warm · {data.by_tier.cool ?? 0} cool
        </div>
      </div>

      <div className="flex-1 min-h-0 flex gap-3 p-3 overflow-hidden">
        {/* leaderboard */}
        <div className="w-1/2 min-w-0 overflow-y-auto space-y-1">
          {data.ranked.map((r, i) => (
            <WorkButton type="submit"
              key={r.entity_id}
              onClick={() => open(r.entity_id)}
              className={
                (selected?.entity_id === r.entity_id
                  ? tc(theme, "bg-zinc-800", "bg-zinc-100")
                  : tc(theme, "hover:bg-zinc-900", "hover:bg-zinc-50")) +
                " w-full text-left flex items-center gap-2 px-2 py-1.5 rounded-md text-xs"
              }
            >
              <span className="text-zinc-600 w-5">{i + 1}</span>
              <span className={`w-9 text-center py-0.5 rounded font-bold ${tierColor(r.tier)}`}>{r.score}</span>
              <span className="flex-1 truncate">{r.name}</span>
              <span className="text-zinc-500 truncate max-w-[110px]">{r.top_factor}</span>
            </WorkButton>
          ))}
          {data.ranked.length === 0 && <div className="text-xs text-zinc-500 p-2">No {segment} to rank yet.</div>}
        </div>

        {/* detail */}
        <div className="w-1/2 min-w-0 overflow-y-auto">
          {!selected ? (
            <div className="text-xs text-zinc-500 p-2">Select someone to see why they rank and draft outreach.</div>
          ) : (
            <div className="space-y-2">
              <div className={card}>
                <div className="flex items-center gap-2">
                  <span className={`w-11 text-center py-1 rounded font-bold text-sm ${tierColor(selected.tier)}`}>{selected.score}</span>
                  <div className="min-w-0">
                    <div className="text-sm font-semibold truncate">{selected.name}</div>
                    <div className="text-xs uppercase tracking-wide text-zinc-500">{selected.tier} · {selected.entity_type}</div>
                  </div>
                </div>
                <div className="text-xs text-brand-teal mt-2">{selected.recommended_action}</div>
              </div>

              <div className={card}>
                <div className="text-xs font-semibold mb-1">Why</div>
                {selected.factors.length === 0 && <div className="text-xs text-zinc-500">No positive signals yet.</div>}
                {selected.factors.map((f) => (
                  <div key={f.label} className="flex items-center gap-2 text-xs py-0.5">
                    <span className="w-8 text-right font-semibold text-brand-teal">+{f.points}</span>
                    <span className="w-32 truncate">{f.label}</span>
                    <span className="text-zinc-500 truncate flex-1">{f.detail}</span>
                  </div>
                ))}
                <div className="text-xs text-zinc-600 mt-1">{selected.basis}</div>
              </div>

              <div className="flex gap-2">
                <WorkButton type="submit" onClick={() => outreach("email")} disabled={busy} className="text-xs px-3 py-1.5 rounded-md bg-brand-teal text-black font-semibold disabled:opacity-50">Draft email</WorkButton>
                <WorkButton type="submit" onClick={() => outreach("sms")} disabled={busy} className="text-xs px-3 py-1.5 rounded-md bg-zinc-700 text-white disabled:opacity-50">Draft SMS</WorkButton>
                {selected.entity_type === "Customer" && (
                  <WorkButton type="submit" onClick={enrich} disabled={busy} className="text-xs px-3 py-1.5 rounded-md border border-zinc-700 text-zinc-300 disabled:opacity-50">Enrich</WorkButton>
                )}
              </div>

              {draft && (
                <div className={card}>
                  {draft.subject && <div className="text-xs font-semibold mb-1">Subject: {draft.subject}</div>}
                  <div className="text-xs text-zinc-400 whitespace-pre-wrap">{draft.body}</div>
                  <div className="text-xs text-zinc-600 mt-1">Based on: {draft.based_on.join(", ") || "general activity"}</div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default PropensityBoard;
