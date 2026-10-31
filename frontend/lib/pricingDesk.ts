// Inventory department's "Pricing" item -- the pricing desk (Inventory
// rebuild, third slice). Backend: core/pricing_desk.py / _api.py. Market
// Pricing, Competitor Comparisons, and Age-Based Adjustments are all
// SIMULATED per Sam's direct instruction (2026-07-17: "when a lack of data
// is a problem, lets simply make up simulated data to accommodate it") --
// every simulated figure carries basis: "simulated_market_data" plus a
// disclaimer string, surfaced as-is in the UI rather than hidden. Applying a
// recommendation is a real, bidirectional Vehicle.Price mutation
// (core/inventory_aging.py's new set_price(), a sibling to the existing
// reduction-only reduce_price()).

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type PricePosition = "below_market" | "at_market" | "above_market";

export type MarketPricing = {
  vehicle_id: string;
  current_price: number | null;
  market_avg_price: number | null;
  price_position: PricePosition | null;
  market_days_supply: number;
  basis: string;
  disclaimer: string;
};

export type CompetitorComparison = {
  dealer_name: string;
  price: number;
  mileage: number;
  distance_miles: number;
};

export type CompetitorComparisons = {
  vehicle_id: string;
  comparisons: CompetitorComparison[];
  basis: string;
  disclaimer: string;
};

export type AgeBasedAdjustment = {
  vehicle_id: string;
  estimated_listing_age_days: number;
  age_band: string;
  suggested_adjustment_pct: number;
  current_price: number | null;
  suggested_price: number | null;
  basis: string;
  disclaimer: string;
};

export type PricingRecommendation = {
  vehicle_id: string;
  current_price: number | null;
  recommended_price: number | null;
  margin_floor: number | null;
  margin_floor_applied: boolean;
  basis: string;
  disclaimer: string;
};

export type VehicleBrief = {
  vehicle_id: string;
  vin: string | null;
  stock_number: string | null;
  year: string | null;
  make: string | null;
  model: string | null;
  price: number | null;
  cost: number | null;
  margin_pct: number | null;
  price_band: string;
  price_history_count: number;
};

export type PricingView = {
  vehicle: VehicleBrief;
  market_pricing: MarketPricing;
  competitor_comparisons: CompetitorComparisons;
  age_based_adjustment: AgeBasedAdjustment;
  recommendation: PricingRecommendation;
};

export type PricingQueueEntry = VehicleBrief & { recommendation: PricingRecommendation };

export type PricingQueue = { count: number; vehicles: PricingQueueEntry[] };

export type PriceHistoryEntry = {
  old_price: number;
  new_price: number;
  reason: string;
  updated_by: string;
  updated_at: string;
};

export type ApplyPriceResult = { vehicle: VehicleBrief; history: PriceHistoryEntry[] };

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

function get<T>(path: string): Promise<T> {
  return fetch(`${API_BASE}${path}`, { headers: { ...authHeaders() } }).then(handle<T>);
}

function post<T>(path: string, body: unknown): Promise<T> {
  return fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(body),
  }).then(handle<T>);
}

export function getPricingQueue(limit = 25): Promise<PricingQueue> {
  return get(`/pricing-desk/queue?limit=${limit}`);
}

export function getPricingView(vehicleId: string): Promise<PricingView> {
  return get(`/pricing-desk/${encodeURIComponent(vehicleId)}`);
}

export function getMarketPricing(vehicleId: string): Promise<MarketPricing> {
  return get(`/pricing-desk/${encodeURIComponent(vehicleId)}/market`);
}

export function getCompetitorComparisons(vehicleId: string): Promise<CompetitorComparisons> {
  return get(`/pricing-desk/${encodeURIComponent(vehicleId)}/competitors`);
}

export function getAgeBasedAdjustment(vehicleId: string): Promise<AgeBasedAdjustment> {
  return get(`/pricing-desk/${encodeURIComponent(vehicleId)}/age-adjustment`);
}

export function getPricingRecommendation(vehicleId: string): Promise<PricingRecommendation> {
  return get(`/pricing-desk/${encodeURIComponent(vehicleId)}/recommendation`);
}

export function applyPriceRecommendation(vehicleId: string, newPrice: number, reason = ""): Promise<ApplyPriceResult> {
  return post(`/pricing-desk/${encodeURIComponent(vehicleId)}/apply-price`, { new_price: newPrice, reason });
}
