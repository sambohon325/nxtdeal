// Inventory's new "Syndication" Top Menu item (2026-07-19) -- closes the
// "Inventory Syndication" item from Sam's own six-pillar spec. A composition
// over two already-real engines: core/merchandising.py's per-vehicle
// SIMULATED feed-sync status, rolled up dealership-wide (core/
// inventory_syndication.py), plus real cross-platform lead/revenue
// performance reusing core/marketing_attribution.py's Lead.Source channel
// mix, filtered to genuine syndication platforms.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type VehicleBrief = {
  vehicle_id: string;
  vin: string | null;
  stock_number: string | null;
  year: string | null;
  make: string | null;
  model: string | null;
  price: number | null;
};

export type FeedPlatformStatus = {
  platform: string;
  synced: number;
  pending: number;
  error: number;
  error_vehicles: VehicleBrief[];
};

export type ListingCompletenessRiskVehicle = VehicleBrief & {
  has_photos: boolean;
  has_description: boolean;
};

export type FeedHealthRollup = {
  total_unsold: number;
  platforms: FeedPlatformStatus[];
  listing_completeness_risk: {
    count: number;
    vehicles: ListingCompletenessRiskVehicle[];
    note: string;
  };
  basis: string;
  disclaimer: string;
  error?: string;
};

export type PlatformPerformanceRow = {
  platform: string;
  lead_source: string;
  lead_count: number;
  sold_count: number;
  revenue: number;
  funded_deals_count: number;
  conversion_rate: number;
  revenue_per_lead: number;
};

export type LeadOnlyChannel = {
  source: string;
  lead_count: number;
  sold_count: number;
  revenue: number;
  funded_deals_count: number;
  conversion_rate: number;
  revenue_per_lead: number;
};

export type SyndicationLeadPerformance = {
  platform_performance: PlatformPerformanceRow[];
  total_syndication_revenue: number;
  total_syndication_leads: number;
  feed_only_platforms: string[];
  lead_only_channels: LeadOnlyChannel[];
  basis: string;
  disclaimer: string;
  error?: string;
};

export type SyndicationOverview = {
  total_unsold_vehicles: number;
  total_listing_errors: number;
  total_listing_pending: number;
  listing_completeness_risk_count: number;
  total_syndication_revenue: number;
  total_syndication_leads: number;
  feed_health: FeedHealthRollup;
  lead_performance: SyndicationLeadPerformance;
  error?: string;
};

export type RepublishResult = {
  platform: string;
  republished_count: number;
  republished_vehicle_ids: string[];
  basis: string;
  disclaimer: string;
  error?: string;
};

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data && (data as { error?: string }).error)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

function get<T>(path: string): Promise<T> {
  return fetch(`${API_BASE}${path}`, { headers: { ...authHeaders() } }).then(handle<T>);
}

function post<T>(path: string, body?: Record<string, unknown>): Promise<T> {
  return fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(body ?? {}),
  }).then(handle<T>);
}

export function getSyndicationCatalog(): Promise<{ feed_platforms: string[] }> {
  return get("/inventory-syndication/catalog");
}

export function getSyndicationOverview(): Promise<SyndicationOverview> {
  return get("/inventory-syndication/overview");
}

export function getFeedHealthRollup(): Promise<FeedHealthRollup> {
  return get("/inventory-syndication/feed-health");
}

export function getSyndicationLeadPerformance(): Promise<SyndicationLeadPerformance> {
  return get("/inventory-syndication/lead-performance");
}

export function republishPlatform(platform: string): Promise<RepublishResult> {
  return post("/inventory-syndication/republish", { platform });
}
