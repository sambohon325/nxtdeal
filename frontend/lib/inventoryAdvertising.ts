// Inventory Advertising Engine -- core/inventory_advertising.py's inventory-driven
// auto ad campaigns. Given a real Vehicle (or a whole class of them -- price-dropped
// units, aged units) it AUTO-generates a ready-to-edit campaign spec (headline /
// body / target_audience / suggested_daily_budget) across five channels (meta,
// google, retargeting, price_drop, aged_inventory), plus a real, isolated,
// kill-switched OpenAI ad-copy call with an honest non-AI fallback.
//
// HONEST real-vs-simulated split (backend's session-110 disclosure convention):
// which real vehicles qualify is 100% REAL and the spec is a real persisted record,
// but the ad-PLATFORM output (estimated reach, "launch") is SIMULATED -- no real
// Meta/Google Ads API is connected. Surfaced honestly via `basis`/`disclaimer`.
//
// Backed by 6 dedicated /inventory-advertising/* routes
// (api/routers/inventory_advertising.py). Mirrors lib/customerJourney.ts's client
// pattern exactly (API_BASE + authHeaders + a shared handle<T> helper, one thin
// function per route).

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

// The five real channels this engine builds for -- must stay in step with
// core/inventory_advertising.py's CHANNELS list.
export const AD_CHANNELS = [
  "meta",
  "google",
  "retargeting",
  "price_drop",
  "aged_inventory",
] as const;
export type AdChannel = (typeof AD_CHANNELS)[number];

// Live rollup from get_advertising_overview(). `campaigns_by_channel` seeds every
// channel to 0 even when empty. `estimated_total_daily_reach` is clearly SIMULATED.
export type AdvertisingOverview = {
  channels: string[];
  total_campaigns: number;
  campaigns_by_channel: Record<string, number>;
  estimated_total_daily_reach: number;
  basis: string;
  disclaimer: string;
};

// One stored InventoryAdCampaign brief (_campaign_brief). Vehicle price/label are
// resolved live off the linked Vehicle at read time, so they may be null if the
// vehicle is gone. `basis`/`disclaimer_note` carry the SIMULATED disclosure.
export type Campaign = {
  id: string;
  vehicle_id: string | null;
  vehicle_label: string | null;
  channel: string | null;
  headline: string | null;
  body: string | null;
  disclaimer: string | null;
  target_audience: string | null;
  suggested_daily_budget: number | null;
  price: number | null;
  age_days: number | null;
  age_is_estimated: boolean | null;
  price_drop_from: number | null;
  price_drop_to: number | null;
  ai_generated: boolean;
  created_at: string | null;
  basis: string;
  disclaimer_note: string;
};

// generate_ad_copy() return contract. On disabled/failure the backend returns an
// honest rule-based fallback with ai_generated=false plus either disabled=true or a
// fallback_reason, mirroring lib/customerJourney.ts's JourneyRecommendation shape.
export type AdCopy = {
  headline: string;
  body: string;
  target_audience: string;
  disclaimer: string;
  ai_generated: boolean;
  disabled?: boolean;
  fallback_reason?: string;
  error?: string;
};

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data && (data as { error?: string }).error)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

export function getAdvertisingOverview(): Promise<AdvertisingOverview> {
  return fetch(`${API_BASE}/inventory-advertising/overview`, {
    headers: { ...authHeaders() },
  }).then(handle<AdvertisingOverview>);
}

export function listCampaigns(): Promise<Campaign[]> {
  return fetch(`${API_BASE}/inventory-advertising/campaigns`, {
    headers: { ...authHeaders() },
  }).then(handle<Campaign[]>);
}

export function generateCampaign(vehicleId: string, channel: AdChannel): Promise<Campaign> {
  return fetch(
    `${API_BASE}/inventory-advertising/vehicle/${encodeURIComponent(vehicleId)}/campaign?channel=${encodeURIComponent(channel)}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
    }
  ).then(handle<Campaign>);
}

export function getPriceDrops(): Promise<Campaign[]> {
  return fetch(`${API_BASE}/inventory-advertising/price-drops`, {
    headers: { ...authHeaders() },
  }).then(handle<Campaign[]>);
}

export function getAged(daysThreshold?: number): Promise<Campaign[]> {
  const query = daysThreshold !== undefined ? `?days_threshold=${encodeURIComponent(String(daysThreshold))}` : "";
  return fetch(`${API_BASE}/inventory-advertising/aged${query}`, {
    headers: { ...authHeaders() },
  }).then(handle<Campaign[]>);
}

export function generateAdCopy(vehicleId: string, channel: AdChannel): Promise<AdCopy> {
  return fetch(
    `${API_BASE}/inventory-advertising/vehicle/${encodeURIComponent(vehicleId)}/ad-copy?channel=${encodeURIComponent(channel)}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
    }
  ).then(handle<AdCopy>);
}
