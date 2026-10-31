// Marketing's "Analytics" Top Menu item (session 113 follow-up) -- the
// Attribution Engine + Marketing ROI Dashboard + Vehicle Attribution capstone.
// Backend: core/marketing_attribution.py / core/marketing_attribution_api.py.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type ChannelMixRow = {
  source: string;
  lead_count: number;
  sold_count: number;
  revenue: number;
  funded_deals_count: number;
  conversion_rate: number;
  revenue_per_lead: number;
};

export type ChannelMix = {
  basis: string;
  disclaimer: string;
  channels: ChannelMixRow[];
  total_leads: number;
  total_revenue: number;
};

export type CampaignRoiRow = {
  campaign_id: string;
  name: string;
  campaign_type: string;
  channel: string;
  revenue: number;
  funded_deals_count: number;
  leads_sold_count: number;
};

export type PurlRoiRow = {
  purl_id: string;
  revenue: number;
  visits: number;
  lead_generated: boolean;
};

export type MarketingRoiDashboard = {
  channel_mix: ChannelMix;
  campaign_roi: {
    basis: string;
    disclaimer: string;
    total_revenue: number;
    campaigns: CampaignRoiRow[];
  };
  purl_roi: {
    basis: string;
    disclaimer: string;
    total_revenue: number;
    purls: PurlRoiRow[];
  };
};

export type VehicleAttributionRow = {
  make: string;
  model: string;
  campaign_mentions: number;
  social_mentions: number;
  funded_deals_count: number;
  gross_revenue: number;
  marketed: boolean;
};

export type VehicleAttribution = {
  basis: string;
  disclaimer: string;
  rows: VehicleAttributionRow[];
  marketed_and_sold_count: number;
  marketed_not_sold_count: number;
  sold_not_marketed_count: number;
};

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

export async function fetchChannelMix(): Promise<ChannelMix> {
  const res = await fetch(`${API_BASE}/marketing-attribution/channel-mix`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function fetchMarketingRoiDashboard(): Promise<MarketingRoiDashboard> {
  const res = await fetch(`${API_BASE}/marketing-attribution/roi-dashboard`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function fetchVehicleAttribution(): Promise<VehicleAttribution> {
  const res = await fetch(`${API_BASE}/marketing-attribution/vehicle-attribution`, { headers: { ...authHeaders() } });
  return handle(res);
}
