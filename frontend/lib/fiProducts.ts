// F&I Workflow (session 105 follow-up) -- the seventh of Sam's ~10 "completely
// missing" dealership workflows: the actual F&I menu -- presenting protection
// products (VSC, GAP, Tire & Wheel, Paint & Fabric, Key Replacement, Prepaid
// Maintenance) on a deal, tracking accept/decline, and real cross-deal product
// penetration. Backend: core/fi_products.py / fi_products_api.py.
//
// Deliberately distinct from the eSignature workflow (contract signing) and the
// "F&I Handoff" tab under sales.fi_turnover (the process handoff from sales to F&I) --
// this is the menu-selling step itself.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type FIProductCategory = "protection" | "maintenance";

export type FIProductCatalogEntry = {
  key: string;
  name: string;
  category: FIProductCategory;
  description: string;
  default_cost: number;
  default_price: number;
};

export type FIProductStatus = "presented" | "accepted" | "declined";

export type FIProductEntry = {
  product_key: string;
  name: string;
  category: FIProductCategory;
  cost: number;
  price: number;
  status: FIProductStatus;
  presented_by: string;
  presented_at: string;
  decided_at: string | null;
  declined_reason: string | null;
};

export type FIMenuTotals = {
  presented: number;
  pending: number;
  accepted: number;
  declined: number;
  total_price_accepted: number;
  total_cost_accepted: number;
  total_gross_accepted: number;
};

export type FIMenu = {
  deal_id: string;
  deal_status: string;
  products: FIProductEntry[];
  totals: FIMenuTotals;
};

export type CustomerBrief = { id: string; name: string } | null;
export type VehicleBrief = { id: string; description: string } | null;

export type DealBrief = {
  id: string;
  status: string;
  customer: CustomerBrief;
  vehicle: VehicleBrief;
  updated_at: string | null;
};

export type ProductPenetrationEntry = {
  product_key: string;
  name: string;
  category: FIProductCategory;
  presented: number;
  accepted: number;
  declined: number;
  penetration_pct: number | null;
  total_gross: number;
};

export type ProductPenetrationStats = {
  deals_with_fi_menu: number;
  products_per_deal_avg: number | null;
  total_accepted_gross: number;
  by_product: ProductPenetrationEntry[];
};

export type FIProductsDashboard = {
  catalog: FIProductCatalogEntry[];
  queue: DealBrief[];
  penetration: ProductPenetrationStats;
};

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

export async function getFIProductCatalog(): Promise<FIProductCatalogEntry[]> {
  const res = await fetch(`${API_BASE}/fi-products/catalog`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function getFIProductsDashboard(): Promise<FIProductsDashboard> {
  const res = await fetch(`${API_BASE}/fi-products/dashboard`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function getProductPenetrationStats(): Promise<ProductPenetrationStats> {
  const res = await fetch(`${API_BASE}/fi-products/penetration`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function listDealsNeedingFIMenu(limit = 25): Promise<DealBrief[]> {
  const res = await fetch(`${API_BASE}/fi-products/queue?limit=${limit}`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function getFIMenu(dealId: string): Promise<FIMenu> {
  const res = await fetch(`${API_BASE}/fi-products/${encodeURIComponent(dealId)}`, { headers: { ...authHeaders() } });
  return handle(res);
}

// Phase 4: personalized F&I menu recommendation for a deal.
export type FIRecommendation = {
  product_key: string;
  name: string;
  category: string;
  price: number;
  fit_score: number;
  recommended: boolean;
  reasons: string[];
  already_on_menu: boolean;
};

export type FIRecommendationResult = {
  deal_id: string;
  signals: Record<string, number | null>;
  recommendations: FIRecommendation[];
  recommended_keys: string[];
  basis: string;
};

export async function recommendFIProducts(dealId: string): Promise<FIRecommendationResult> {
  const res = await fetch(`${API_BASE}/fi-products/${encodeURIComponent(dealId)}/recommend`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function presentFIProducts(dealId: string, productKeys: string[]): Promise<FIMenu> {
  const res = await fetch(`${API_BASE}/fi-products/${encodeURIComponent(dealId)}/present`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ product_keys: productKeys }),
  });
  return handle(res);
}

export async function updateFIProductPricing(
  dealId: string,
  productKey: string,
  input: { cost?: number; price?: number },
): Promise<FIMenu> {
  const res = await fetch(`${API_BASE}/fi-products/${encodeURIComponent(dealId)}/${encodeURIComponent(productKey)}/pricing`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(input),
  });
  return handle(res);
}

export async function decideFIProduct(
  dealId: string,
  productKey: string,
  decision: "accepted" | "declined",
  declinedReason?: string,
): Promise<FIMenu> {
  const res = await fetch(`${API_BASE}/fi-products/${encodeURIComponent(dealId)}/${encodeURIComponent(productKey)}/decide`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ decision, declined_reason: declinedReason }),
  });
  return handle(res);
}
