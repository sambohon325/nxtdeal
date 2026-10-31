// lib/marketplace.ts — client for the NXTDeal Marketplace (2026-07-24). Talks to the
// /marketplace routes in backend/api/app.py (core/marketplace.py / marketplace_api.py): the
// full certified catalog + per-dealer install state, plus install / uninstall (ADMIN). Same
// reuse-the-shared-helpers shape every lib/*.ts client follows: API_BASE + authHeaders() + a
// local handle<T>.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type ListingState = "available" | "installed" | "connected" | "coming_soon";
export type CategorySection = "day1" | "oem" | "phase2";

export type Listing = {
  id: string;
  name: string;
  category: string;
  blurb: string;
  badge: string | null;
  phase: "day1" | "phase2";
  capability: string | null;
  state: ListingState;
  capability_live: boolean;
  installed_at: string | null;
  installed_by: string | null;
};

export type MarketplaceCategory = {
  id: string;
  name: string;
  section: CategorySection;
  icon: string;
  blurb: string;
  purpose: string[];
  capability: string | null;
  listing_count: number;
  listings: Listing[];
};

export type MarketplaceSummary = {
  total_listings: number;
  categories: number;
  available: number;
  installed: number;
  connected: number;
  coming_soon: number;
  day1_categories: number;
  oem_brands: number;
};

export type Marketplace = {
  can_manage?: boolean;
  summary: MarketplaceSummary;
  categories: MarketplaceCategory[];
  sections: { day1: string[]; oem: string[]; phase2: string[] };
  note: string;
};

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (
    !response.ok ||
    (data && typeof data === "object" && "error" in data && (data as { error?: string }).error)
  ) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

export function fetchMarketplace(): Promise<Marketplace> {
  return fetch(`${API_BASE}/marketplace`, { headers: { ...authHeaders() } }).then(handle<Marketplace>);
}

export type ListingDetail = Listing & { category_name: string; purpose: string[] };

export function fetchListing(listingId: string): Promise<ListingDetail> {
  return fetch(`${API_BASE}/marketplace/listings/${encodeURIComponent(listingId)}`, {
    headers: { ...authHeaders() },
  }).then(handle<ListingDetail>);
}

export function installListing(listingId: string): Promise<Listing> {
  return fetch(`${API_BASE}/marketplace/listings/${encodeURIComponent(listingId)}/install`, {
    method: "POST",
    headers: { ...authHeaders() },
  }).then(handle<Listing>);
}

export function uninstallListing(listingId: string): Promise<Listing> {
  return fetch(`${API_BASE}/marketplace/listings/${encodeURIComponent(listingId)}/uninstall`, {
    method: "POST",
    headers: { ...authHeaders() },
  }).then(handle<Listing>);
}
