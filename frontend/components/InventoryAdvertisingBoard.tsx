"use client";
import { WorkButton, WorkInput, WorkSelect , WorkStat} from "./WorkspaceUi";
import { WorkField } from "./WorkField";

// Marketing's "Inventory Advertising" board -- a staff-facing surface over
// core/inventory_advertising.py's inventory-driven auto ad campaigns. Given the
// real Vehicle inventory already in the graph, it AUTO-generates ready-to-edit
// campaign specs (headline / body / target_audience / suggested_daily_budget)
// across five channels (meta / google / retargeting / price_drop / aged_inventory)
// and a real, kill-switched AI ad-copy draft with an honest non-AI fallback.
//
// HONEST disclosure: which vehicles qualify is REAL and the spec is a real persisted
// record, but the ad-PLATFORM output (estimated reach) is SIMULATED -- no real
// Meta/Google Ads API is connected. Surfaced honestly via a standing disclaimer.
//
// Sections: overview KPIs (campaigns by channel + estimated reach), the campaigns
// list, price-drop and aged-inventory quick lists, and a per-vehicle panel that can
// generate a campaign spec and pull AI ad copy. Read/act through
// lib/inventoryAdvertising.ts -- same shape and styling vocabulary as
// OperationsCustomerJourneyBoard.tsx (RIBBON palette, theme-aware classes).
import { PRODUCT_ACCENT_COLORS } from "@/lib/productTheme";
import { useEffect, useState } from "react";
import {
  getAdvertisingOverview,
  listCampaigns,
  generateCampaign,
  getPriceDrops,
  getAged,
  generateAdCopy,
  AD_CHANNELS,
  type AdvertisingOverview,
  type Campaign,
  type AdCopy,
  type AdChannel,
} from "@/lib/inventoryAdvertising";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const RIBBON = PRODUCT_ACCENT_COLORS;

// A readable Title-Case label + a ribbon-derived accent color per channel. Colors
// cycle the RIBBON palette so the board reads as one branded system.
const CHANNEL_LABEL: Record<string, string> = {
  meta: "Meta",
  google: "Google",
  retargeting: "Retargeting",
  price_drop: "Price Drop",
  aged_inventory: "Aged Inventory",
};

const CHANNEL_COLOR: Record<string, string> = {
  meta: RIBBON[0],
  google: RIBBON[1],
  retargeting: RIBBON[2],
  price_drop: RIBBON[3],
  aged_inventory: RIBBON[0],
};

function channelLabel(channel: string | null | undefined): string {
  if (!channel) return "—";
  return CHANNEL_LABEL[channel] ?? channel;
}

function fmt(ts: string | null | undefined): string {
  if (!ts) return "—";
  try {
    return new Date(ts).toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  } catch {
    return ts;
  }
}

function money(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  try {
    return `$${Math.round(value).toLocaleString()}`;
  } catch {
    return String(value);
  }
}

function Kpi({ theme, label, value, color }: { theme: Theme; label: string; value: string; color: string }) { return <WorkStat label={label} value={value}/>; }

// A standing honest disclaimer that the ad-platform output is SIMULATED. Prefers the
// backend's own disclaimer text when present, with a self-contained fallback.
function SimulatedDisclaimer({ theme, text }: { theme: Theme; text?: string | null }) {
  return (
    <div className={tc(theme, "rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2", "rounded-md border border-amber-400/50 bg-amber-50 px-3 py-2")}>
      <div className="text-xs font-brand uppercase tracking-wide text-amber-500 mb-0.5">⚠ Simulated Ad Output</div>
      <div className="text-xs text-zinc-400">
        {text ||
          "SIMULATED -- no real Meta Ads / Google Ads API is connected in this environment. These are generated, ready-to-edit campaign specs and a deterministically-seeded estimated-reach figure, never a launched, spending, or delivered ad."}
      </div>
    </div>
  );
}

function CampaignRow({ theme, campaign }: { theme: Theme; campaign: Campaign }) {
  const color = CHANNEL_COLOR[campaign.channel ?? ""] ?? RIBBON[0];
  return (
    <div className={tc(theme, "rounded-md border border-zinc-800 bg-brand-charcoal p-3", "rounded-md border border-zinc-200 bg-zinc-50 p-3")}>
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <div className="text-sm font-medium text-zinc-200 truncate">{campaign.vehicle_label ?? campaign.vehicle_id ?? campaign.id}</div>
          <div className="text-xs text-zinc-500">
            {campaign.vehicle_id ?? "—"}
            <span className="text-zinc-600 ml-2">{fmt(campaign.created_at)}</span>
          </div>
        </div>
        <span className="text-xs font-brand uppercase tracking-wide px-2 py-0.5 rounded-full flex-shrink-0" style={{ background: `${color}22`, color }}>
          {channelLabel(campaign.channel)}
        </span>
      </div>
      {campaign.headline && <div className="text-xs font-medium text-zinc-300 mt-2">{campaign.headline}</div>}
      {campaign.body && <div className="text-xs text-zinc-500 mt-1 break-words">{campaign.body}</div>}
      <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2">
        <div className="text-xs text-zinc-500">
          <span className="font-brand uppercase tracking-wide text-zinc-600 mr-1">Price</span>
          {money(campaign.price)}
        </div>
        <div className="text-xs text-zinc-500">
          <span className="font-brand uppercase tracking-wide text-zinc-600 mr-1">Daily Budget</span>
          {money(campaign.suggested_daily_budget)}
        </div>
        {campaign.age_days !== null && campaign.age_days !== undefined && (
          <div className="text-xs text-zinc-500">
            <span className="font-brand uppercase tracking-wide text-zinc-600 mr-1">Age</span>
            {campaign.age_days}d{campaign.age_is_estimated ? " (est.)" : ""}
          </div>
        )}
        {campaign.price_drop_from !== null && campaign.price_drop_from !== undefined && (
          <div className="text-xs text-zinc-500">
            <span className="font-brand uppercase tracking-wide text-zinc-600 mr-1">Was</span>
            {money(campaign.price_drop_from)}
          </div>
        )}
      </div>
      {campaign.target_audience && (
        <div className="text-xs text-zinc-600 mt-2 italic break-words">🎯 {campaign.target_audience}</div>
      )}
    </div>
  );
}

function AdCopyCard({ theme, copy }: { theme: Theme; copy: AdCopy }) {
  return (
    <div className={tc(theme, "rounded-md border border-zinc-700 bg-black/20 p-3", "rounded-md border border-zinc-300 bg-white p-3")}>
      <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1">
        🤖 AI Ad Copy {copy.ai_generated ? "" : copy.disabled ? "(disabled — fallback)" : "(fallback)"}
      </div>
      <div className="text-sm font-medium text-zinc-200">{copy.headline || "—"}</div>
      {copy.body && <div className="text-xs text-zinc-400 mt-1 break-words">{copy.body}</div>}
      {copy.target_audience && (
        <div className="text-xs text-zinc-500 mt-2">
          <span className="font-brand uppercase tracking-wide text-zinc-600 mr-1">Audience</span>
          {copy.target_audience}
        </div>
      )}
      {copy.disclaimer && <div className="text-xs text-zinc-600 mt-2 italic">{copy.disclaimer}</div>}
      {copy.fallback_reason && (
        <div className="text-xs text-zinc-600 mt-2 italic">Fallback reason: {copy.fallback_reason}</div>
      )}
    </div>
  );
}

export function InventoryAdvertisingBoard({ theme }: { theme: Theme }) {
  const [overview, setOverview] = useState<AdvertisingOverview | null>(null);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Price-drop and aged-inventory quick lists -- each button builds+returns the
  // matching campaigns for qualifying real vehicles.
  const [priceDrops, setPriceDrops] = useState<Campaign[] | null>(null);
  const [priceDropsBusy, setPriceDropsBusy] = useState(false);
  const [aged, setAged] = useState<Campaign[] | null>(null);
  const [agedBusy, setAgedBusy] = useState(false);
  const [agedThreshold, setAgedThreshold] = useState("60");
  const [listError, setListError] = useState<string | null>(null);

  // Per-vehicle panel state.
  const [vehicleId, setVehicleId] = useState("");
  const [channel, setChannel] = useState<AdChannel>(AD_CHANNELS[0]);
  const [spec, setSpec] = useState<Campaign | null>(null);
  const [specBusy, setSpecBusy] = useState(false);
  const [adCopy, setAdCopy] = useState<AdCopy | null>(null);
  const [copyBusy, setCopyBusy] = useState(false);
  const [panelError, setPanelError] = useState<string | null>(null);

  function refresh() {
    setLoading(true);
    setError(null);
    Promise.all([getAdvertisingOverview(), listCampaigns()])
      .then(([ov, list]) => {
        setOverview(ov);
        setCampaigns(list);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Unable to load the Inventory Advertising overview."))
      .finally(() => setLoading(false));
  }

  useEffect(refresh, []);

  function handlePriceDrops() {
    setPriceDropsBusy(true);
    setListError(null);
    getPriceDrops()
      .then((built) => {
        setPriceDrops(built);
        refresh();
      })
      .catch((e) => setListError(e instanceof Error ? e.message : "Unable to build price-drop campaigns."))
      .finally(() => setPriceDropsBusy(false));
  }

  function handleAged() {
    setAgedBusy(true);
    setListError(null);
    const parsed = parseInt(agedThreshold, 10);
    const threshold = Number.isFinite(parsed) ? parsed : undefined;
    getAged(threshold)
      .then((built) => {
        setAged(built);
        refresh();
      })
      .catch((e) => setListError(e instanceof Error ? e.message : "Unable to build aged-inventory campaigns."))
      .finally(() => setAgedBusy(false));
  }

  function handleGenerateSpec() {
    const id = vehicleId.trim();
    if (!id) {
      setPanelError("Enter a vehicle id to generate a campaign.");
      return;
    }
    setSpecBusy(true);
    setPanelError(null);
    setAdCopy(null);
    generateCampaign(id, channel)
      .then((built) => {
        setSpec(built);
        refresh();
      })
      .catch((e) => {
        setSpec(null);
        setPanelError(e instanceof Error ? e.message : "Unable to generate this campaign.");
      })
      .finally(() => setSpecBusy(false));
  }

  function handleGenerateAdCopy() {
    const id = vehicleId.trim();
    if (!id) {
      setPanelError("Enter a vehicle id to generate ad copy.");
      return;
    }
    setCopyBusy(true);
    setPanelError(null);
    generateAdCopy(id, channel)
      .then(setAdCopy)
      .catch((e) => setPanelError(e instanceof Error ? e.message : "Unable to generate ad copy."))
      .finally(() => setCopyBusy(false));
  }

  const byChannel = overview?.campaigns_by_channel ?? {};

  return (
    <div className={tc(theme, "flex-1 flex flex-col min-h-0 bg-brand-ink text-white overflow-y-auto", "flex-1 flex flex-col min-h-0 bg-white text-black overflow-y-auto")}>
      {/* Header + standing simulated disclaimer */}
      <div className={tc(theme, "p-4 border-b border-zinc-800 space-y-3", "p-4 border-b border-zinc-200 space-y-3")}>
        <div className="flex items-center justify-between gap-2">
          <div className="text-sm font-brand uppercase tracking-wide text-zinc-400">📣 Inventory Advertising Engine</div>
          <WorkButton type="submit" onClick={refresh} className="text-xs px-2.5 py-1 rounded-full bg-zinc-200/10 text-zinc-400 hover:text-white">
            ↻ Refresh
          </WorkButton>
        </div>
        <SimulatedDisclaimer theme={theme} text={overview?.disclaimer} />
        {loading && <div className="text-sm text-zinc-500">Loading…</div>}
        {error && <div className="text-sm text-red-400">{error}</div>}
      </div>

      {/* Overview KPIs */}
      <div className={tc(theme, "grid grid-cols-4 gap-3 p-4 border-b border-zinc-800", "grid grid-cols-4 gap-3 p-4 border-b border-zinc-200")}>
        <Kpi theme={theme} label="Total Campaigns" value={String(overview?.total_campaigns ?? 0)} color={RIBBON[0]} />
        <Kpi theme={theme} label="Channels" value={String(overview?.channels?.length ?? AD_CHANNELS.length)} color={RIBBON[1]} />
        <Kpi theme={theme} label="Est. Daily Reach (sim.)" value={(overview?.estimated_total_daily_reach ?? 0).toLocaleString()} color={RIBBON[2]} />
        <Kpi theme={theme} label="Price-Drop Campaigns" value={String(byChannel["price_drop"] ?? 0)} color={RIBBON[3]} />
      </div>

      {/* Campaigns-by-channel breakdown */}
      <div className={tc(theme, "grid grid-cols-5 gap-2 px-4 py-3 border-b border-zinc-800", "grid grid-cols-5 gap-2 px-4 py-3 border-b border-zinc-200")}>
        {AD_CHANNELS.map((c) => (
          <div
            key={c}
            className={tc(theme, "rounded-md border border-zinc-800 bg-brand-charcoal px-3 py-2", "rounded-md border border-zinc-200 bg-zinc-50 px-3 py-2")}
          >
            <div className="text-lg font-semibold" style={{ color: CHANNEL_COLOR[c] ?? RIBBON[0] }}>
              {byChannel[c] ?? 0}
            </div>
            <div className="text-xs font-brand uppercase tracking-wide text-zinc-500">{CHANNEL_LABEL[c] ?? c}</div>
          </div>
        ))}
      </div>

      {/* Price-drop + aged-inventory quick lists */}
      <div className={tc(theme, "p-4 border-b border-zinc-800 space-y-3", "p-4 border-b border-zinc-200 space-y-3")}>
        <div className="text-sm font-brand uppercase tracking-wide text-zinc-400">⚡ Quick Campaigns</div>
        {listError && <div className="text-sm text-red-400">{listError}</div>}
        <div className="grid grid-cols-2 gap-3">
          {/* Price drops */}
          <div className="space-y-2">
            <WorkButton type="submit"
              onClick={handlePriceDrops}
              disabled={priceDropsBusy}
              className="text-xs px-3 py-1.5 rounded-full bg-zinc-200 text-black font-medium disabled:opacity-50"
            >
              {priceDropsBusy ? "Building…" : "💲 Build Price-Drop Campaigns"}
            </WorkButton>
            {priceDrops !== null && (
              <div className="space-y-2">
                {priceDrops.length === 0 ? (
                  <div className="text-xs text-zinc-500">No unsold vehicles with a recorded price drop.</div>
                ) : (
                  priceDrops.map((c) => <CampaignRow key={c.id} theme={theme} campaign={c} />)
                )}
              </div>
            )}
          </div>

          {/* Aged inventory */}
          <div className="space-y-2">
            <div className="flex items-center gap-1.5">
              <WorkButton type="submit"
                onClick={handleAged}
                disabled={agedBusy}
                className="text-xs px-3 py-1.5 rounded-full bg-zinc-200 text-black font-medium disabled:opacity-50 whitespace-nowrap"
              >
                {agedBusy ? "Building…" : "⏳ Build Aged-Inventory"}
              </WorkButton>
              <WorkField label="Aged Threshold"><WorkInput
                value={agedThreshold}
                onChange={(e) => setAgedThreshold(e.target.value)}
                placeholder="60"
                inputMode="numeric"
                className={tc(
                  theme,
                  "w-16 text-xs rounded border border-zinc-700 bg-black/30 px-2 py-1.5 text-white",
                  "w-16 text-xs rounded border border-zinc-300 bg-white px-2 py-1.5 text-black"
                )}
              /></WorkField>
              <span className="text-xs text-zinc-500">days</span>
            </div>
            {aged !== null && (
              <div className="space-y-2">
                {aged.length === 0 ? (
                  <div className="text-xs text-zinc-500">No unsold vehicles past that age threshold.</div>
                ) : (
                  aged.map((c) => <CampaignRow key={c.id} theme={theme} campaign={c} />)
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Per-vehicle panel */}
      <div className={tc(theme, "p-4 border-b border-zinc-800 space-y-3", "p-4 border-b border-zinc-200 space-y-3")}>
        <div className="text-sm font-brand uppercase tracking-wide text-zinc-400">🚗 Per-Vehicle Campaign</div>

        <div className="flex flex-wrap items-center gap-2">
          <WorkField label="Vehicle id"><WorkInput
            value={vehicleId}
            onChange={(e) => setVehicleId(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleGenerateSpec();
            }}
            placeholder="Vehicle id (e.g. VEH-00123)"
            className={tc(
              theme,
              "flex-1 min-w-[180px] text-xs rounded border border-zinc-700 bg-black/30 px-2 py-1.5 text-white",
              "flex-1 min-w-[180px] text-xs rounded border border-zinc-300 bg-white px-2 py-1.5 text-black"
            )}
          /></WorkField>
          <WorkField label="Channel"><WorkSelect
            value={channel}
            onChange={(e) => setChannel(e.target.value as AdChannel)}
            className={tc(
              theme,
              "text-xs rounded border border-zinc-700 bg-black/30 px-2 py-1.5 text-white",
              "text-xs rounded border border-zinc-300 bg-white px-2 py-1.5 text-black"
            )}
          >
            {AD_CHANNELS.map((c) => (
              <option key={c} value={c}>
                {CHANNEL_LABEL[c] ?? c}
              </option>
            ))}
          </WorkSelect></WorkField>
          <WorkButton type="submit"
            onClick={handleGenerateSpec}
            disabled={specBusy}
            className="text-xs px-3 py-1.5 rounded-full bg-zinc-200 text-black font-medium disabled:opacity-50 whitespace-nowrap"
          >
            {specBusy ? "Generating…" : "Generate Campaign Spec"}
          </WorkButton>
          <WorkButton type="submit"
            onClick={handleGenerateAdCopy}
            disabled={copyBusy}
            className="text-xs px-3 py-1.5 rounded-full bg-zinc-200/10 text-zinc-400 hover:text-white disabled:opacity-50 whitespace-nowrap"
          >
            {copyBusy ? "Generating…" : "✨ Generate AI Ad Copy"}
          </WorkButton>
        </div>

        {panelError && <div className="text-sm text-red-400">{panelError}</div>}

        {spec && <CampaignRow theme={theme} campaign={spec} />}
        {adCopy && <AdCopyCard theme={theme} copy={adCopy} />}
      </div>

      {/* All campaigns list */}
      <div className={tc(theme, "p-4 space-y-3", "p-4 space-y-3")}>
        <div className="text-sm font-brand uppercase tracking-wide text-zinc-400">📋 All Campaigns</div>
        {!loading && campaigns.length === 0 ? (
          <div className="text-xs text-zinc-500">No inventory ad campaigns built yet.</div>
        ) : (
          <div className="space-y-2">
            {campaigns.map((c) => (
              <CampaignRow key={c.id} theme={theme} campaign={c} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
