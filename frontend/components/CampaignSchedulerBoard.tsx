"use client";
import { WorkButton, WorkSelect, WorkInput } from "./WorkspaceUi";
import { WorkField } from "./WorkField";

// Bumper-parity campaign tooling (2026-07-25): Duplication Station, Recurring Schedule,
// and Multi-Planner in one board. Backed by lib/campaignTools.ts. Reuses the campaigns()
// glance (lib/marketingCrm.ts) for the pick-a-campaign lists.
import { useEffect, useState } from "react";
import { getSession } from "@/lib/auth";
import { fetchCampaignsData, type CampaignsData } from "@/lib/marketingCrm";
import {
  duplicateCampaign,
  bulkCreateCampaigns,
  listRecurringSchedules,
  createRecurringSchedule,
  setScheduleActive,
  runDueSchedules,
  sendCampaign,
  getDeliveryStats,
  type RecurringSchedule,
  type DeliveryStats,
} from "@/lib/campaignTools";

type Theme = "dark" | "light";
type Tab = "duplicate" | "recurring" | "planner" | "delivery";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

type PlannerRow = { campaign_type: string; name: string; channel: string };

export function CampaignSchedulerBoard({ theme }: { theme: Theme }) {
  const [tab, setTab] = useState<Tab>("duplicate");
  const [data, setData] = useState<CampaignsData | null>(null);
  const [schedules, setSchedules] = useState<RecurringSchedule[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [flash, setFlash] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const session = getSession();
  const canManage = session?.role === "ADMIN" || session?.role === "MARKETING";

  const card = tc(theme, "rounded-md border border-zinc-800 bg-zinc-900/60 p-3", "rounded-md border border-zinc-200 bg-white p-3");
  const input = tc(theme, "rounded-md bg-zinc-950 border border-zinc-800 px-2 py-1.5 text-[12px]", "rounded-md bg-white border border-zinc-300 px-2 py-1.5 text-[12px]");

  // recurring form
  const [baseId, setBaseId] = useState("");
  const [cadence, setCadence] = useState<"daily" | "weekly" | "monthly">("monthly");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");

  // planner rows
  const [rows, setRows] = useState<PlannerRow[]>([{ campaign_type: "general", name: "", channel: "email" }]);

  // delivery
  const [stats, setStats] = useState<Record<string, DeliveryStats>>({});

  async function send(id: string) {
    setBusy(true); setFlash(null); setError(null);
    try {
      const r = await sendCampaign(id);
      setFlash(`Delivery run (${r.mode}): ${r.delivered} delivered, ${r.no_contact} no-contact, ${r.skipped} already-sent.`);
      const s = await getDeliveryStats(id);
      setStats((prev) => ({ ...prev, [id]: s }));
    } catch (e) { setError(e instanceof Error ? e.message : "Couldn't send."); } finally { setBusy(false); }
  }

  async function loadStats(id: string) {
    try { const s = await getDeliveryStats(id); setStats((prev) => ({ ...prev, [id]: s })); }
    catch (e) { setError(e instanceof Error ? e.message : "Couldn't load delivery."); }
  }

  function refresh() {
    Promise.all([fetchCampaignsData(), listRecurringSchedules()])
      .then(([d, s]) => {
        setData(d);
        setSchedules(s);
        setError(null);
        if (!baseId && d.recent_campaigns[0]) setBaseId(d.recent_campaigns[0].id);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Couldn't load campaigns."));
  }

  useEffect(refresh, []);

  async function dup(id: string) {
    setBusy(true); setFlash(null); setError(null);
    try {
      const c = await duplicateCampaign(id);
      setFlash(`Duplicated into draft ${String(c.id)}.`);
      refresh();
    } catch (e) { setError(e instanceof Error ? e.message : "Couldn't duplicate."); } finally { setBusy(false); }
  }

  async function makeRecurring() {
    setBusy(true); setFlash(null); setError(null);
    try {
      await createRecurringSchedule({ base_campaign_id: baseId, cadence, start_date: startDate, end_date: endDate || null });
      setFlash("Recurring schedule created.");
      refresh();
    } catch (e) { setError(e instanceof Error ? e.message : "Couldn't create schedule."); } finally { setBusy(false); }
  }

  async function toggleSchedule(s: RecurringSchedule) {
    try { await setScheduleActive(s.id, !s.active); refresh(); }
    catch (e) { setError(e instanceof Error ? e.message : "Couldn't update schedule."); }
  }

  async function runNow() {
    setBusy(true); setFlash(null); setError(null);
    try {
      const r = await runDueSchedules();
      setFlash(`Launched ${r.launched_count} due campaign(s).`);
      refresh();
    } catch (e) { setError(e instanceof Error ? e.message : "Couldn't run schedules."); } finally { setBusy(false); }
  }

  async function planAll() {
    setBusy(true); setFlash(null); setError(null);
    try {
      const r = await bulkCreateCampaigns(rows.filter((x) => x.name.trim()).map((x) => ({ ...x, params: {} })));
      setFlash(`Created ${r.created_count} draft campaign(s). ${r.errors.length ? `${r.errors.length} row(s) had errors.` : ""}`);
      refresh();
    } catch (e) { setError(e instanceof Error ? e.message : "Couldn't create campaigns."); } finally { setBusy(false); }
  }

  if (!data) return <div className="p-4 text-sm text-zinc-500">Loading…</div>;

  const types = data.available_types;
  const channels = data.available_channels;

  return (
    <div className="flex-1 min-h-0 flex flex-col overflow-y-auto">
      <div className="px-3 pt-3 shrink-0">
        <div className="text-base font-brand">Campaign Tools</div>
        <div className="text-xs text-zinc-500">Duplicate a campaign, set one to repeat on a cadence, or plan several at once.</div>
      </div>

      <div className="flex gap-1.5 px-3 pt-3">
        {(["duplicate", "recurring", "planner", "delivery"] as Tab[]).map((t) => (
          <WorkButton data-work-view aria-pressed={tab === t} type="submit"
            key={t}
            onClick={() => setTab(t)}
            className={tab === t ? "text-xs px-3 py-1 rounded-full bg-brand-teal text-black capitalize" : tc(theme, "text-xs px-3 py-1 rounded-full bg-zinc-900 text-zinc-300 capitalize", "text-xs px-3 py-1 rounded-full bg-zinc-100 text-zinc-600 capitalize")}
          >
            {t === "planner" ? "Multi-Planner" : t}
          </WorkButton>
        ))}
      </div>

      {flash && <div className="mx-3 mt-2 rounded-md bg-brand-teal/15 border border-brand-teal/40 px-3 py-2 text-xs text-brand-teal">{flash}</div>}
      {error && <div className="mx-3 mt-2 rounded-md bg-red-500/10 border border-red-500/30 px-3 py-2 text-xs text-red-400">{error}</div>}
      {!canManage && <div className="mx-3 mt-2 text-xs text-zinc-500">You can view these tools; activating recurring runs needs a Marketing/Admin role.</div>}

      <div className="p-3 space-y-2">
        {tab === "duplicate" && (
          <div className={card}>
            <div className="text-xs font-semibold mb-2">Duplicate a campaign</div>
            {data.recent_campaigns.map((c) => (
              <div key={c.id} className="flex items-center gap-2 text-xs py-1 border-b border-zinc-800/50">
                <div className="flex-1 truncate">{c.name}</div>
                <div className="text-zinc-500 w-20 truncate">{c.status}</div>
                <WorkButton type="submit" onClick={() => dup(c.id)} disabled={busy} className="text-xs px-2 py-0.5 rounded bg-zinc-700 text-white disabled:opacity-50">Duplicate</WorkButton>
              </div>
            ))}
            {data.recent_campaigns.length === 0 && <div className="text-xs text-zinc-500">No campaigns yet.</div>}
          </div>
        )}

        {tab === "recurring" && (
          <>
            <div className={card}>
              <div className="text-xs font-semibold mb-2">New recurring schedule</div>
              <div className="flex flex-wrap gap-2 items-center">
                <WorkField label="Campaign template"><WorkSelect value={baseId} onChange={(e) => setBaseId(e.target.value)} className={input + " min-w-[180px]"}>
                  {data.recent_campaigns.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                </WorkSelect></WorkField>
                <WorkField label="Cadence"><WorkSelect value={cadence} onChange={(e) => setCadence(e.target.value as "daily" | "weekly" | "monthly")} className={input}>
                  <option value="daily">Daily</option>
                  <option value="weekly">Weekly</option>
                  <option value="monthly">Monthly</option>
                </WorkSelect></WorkField>
                <WorkField label="Start Date"><WorkInput type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} className={input} /></WorkField>
                <WorkField label="end (optional)"><WorkInput type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} className={input} placeholder="end (optional)" /></WorkField>
                <WorkButton type="submit" onClick={makeRecurring} disabled={busy || !baseId || !startDate} className="text-xs px-3 py-1.5 rounded-md bg-brand-teal text-black font-semibold disabled:opacity-50">Create</WorkButton>
              </div>
            </div>
            <div className={card}>
              <div className="flex items-center justify-between mb-2">
                <div className="text-xs font-semibold">Schedules ({schedules.length})</div>
                {canManage && <WorkButton type="submit" onClick={runNow} disabled={busy} className="text-xs px-2.5 py-1 rounded-md bg-zinc-700 text-white disabled:opacity-50">Run due now</WorkButton>}
              </div>
              {schedules.map((s) => (
                <div key={s.id} className="flex items-center gap-2 text-xs py-1 border-b border-zinc-800/50">
                  <div className="flex-1 truncate">{s.name}</div>
                  <div className="text-zinc-500">{s.cadence}</div>
                  <div className="text-zinc-500 w-24">next {s.next_run_date || "—"}</div>
                  <WorkButton type="submit" onClick={() => toggleSchedule(s)} className={s.active ? "text-xs px-2 py-0.5 rounded bg-brand-teal text-black" : "text-xs px-2 py-0.5 rounded bg-zinc-700 text-white"}>
                    {s.active ? "Active" : "Paused"}
                  </WorkButton>
                </div>
              ))}
              {schedules.length === 0 && <div className="text-xs text-zinc-500">No schedules yet.</div>}
            </div>
          </>
        )}

        {tab === "planner" && (
          <div className={card}>
            <div className="text-xs font-semibold mb-2">Plan several campaigns at once</div>
            {rows.map((r, i) => (
              <div key={i} className="flex gap-2 mb-1.5">
                <WorkField label="Campaign type"><WorkSelect value={r.campaign_type} onChange={(e) => setRows(rows.map((x, j) => j === i ? { ...x, campaign_type: e.target.value } : x))} className={input}>
                  {types.map((t) => <option key={t.key} value={t.key}>{t.name}</option>)}
                </WorkSelect></WorkField>
                <WorkField label="Campaign name"><WorkInput value={r.name} placeholder="Campaign name" onChange={(e) => setRows(rows.map((x, j) => j === i ? { ...x, name: e.target.value } : x))} className={input + " flex-1"} /></WorkField>
                <WorkField label="Channel"><WorkSelect value={r.channel} onChange={(e) => setRows(rows.map((x, j) => j === i ? { ...x, channel: e.target.value } : x))} className={input}>
                  {channels.map((c) => <option key={c} value={c}>{c}</option>)}
                </WorkSelect></WorkField>
                <WorkButton type="submit" onClick={() => setRows(rows.filter((_, j) => j !== i))} className="text-xs px-2 text-zinc-500">✕</WorkButton>
              </div>
            ))}
            <div className="flex gap-2 mt-2">
              <WorkButton type="submit" onClick={() => setRows([...rows, { campaign_type: "general", name: "", channel: "email" }])} className="text-xs px-2.5 py-1 rounded-md border border-zinc-700 text-zinc-300">+ Row</WorkButton>
              <WorkButton type="submit" onClick={planAll} disabled={busy} className="text-xs px-3 py-1.5 rounded-md bg-brand-teal text-black font-semibold disabled:opacity-50">Create all as drafts</WorkButton>
            </div>
          </div>
        )}

        {tab === "delivery" && (
          <div className={card}>
            <div className="text-xs font-semibold mb-1">Send &amp; delivery</div>
            <div className="text-xs text-zinc-500 mb-2">
              Delivery is real and per-recipient — it routes through the provider seam. With no live provider connected it&apos;s honestly simulated; connect one under Administration ▸ Connections to send for real.
            </div>
            {data.recent_campaigns.map((c) => {
              const s = stats[c.id];
              return (
                <div key={c.id} className="py-1 border-b border-zinc-800/50">
                  <div className="flex items-center gap-2 text-xs">
                    <div className="flex-1 truncate">{c.name}</div>
                    <div className="text-zinc-500 w-16 truncate">{c.channel}</div>
                    <WorkButton type="submit" onClick={() => loadStats(c.id)} className="text-xs px-2 py-0.5 rounded bg-zinc-800 text-zinc-300">Stats</WorkButton>
                    {canManage && <WorkButton type="submit" onClick={() => send(c.id)} disabled={busy} className="text-xs px-2 py-0.5 rounded bg-brand-teal text-black font-semibold disabled:opacity-50">Send</WorkButton>}
                  </div>
                  {s && (
                    <div className="text-xs text-zinc-500 mt-0.5">
                      {s.mode} · {s.delivered} delivered · {s.opened} opened · {s.clicked} clicked
                      {s.total_sends === 0 ? " · not sent yet" : ` · open ${(s.open_rate * 100).toFixed(0)}%`}
                    </div>
                  )}
                </div>
              );
            })}
            {data.recent_campaigns.length === 0 && <div className="text-xs text-zinc-500">No campaigns yet.</div>}
          </div>
        )}
      </div>
    </div>
  );
}

export default CampaignSchedulerBoard;
