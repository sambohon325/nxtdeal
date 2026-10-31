// Accessories Accelerator -- core/accessories.py's graph-native accessory
// upsell motion (Vehicle Sold -> Recommend -> Install -> Track Revenue), stored
// directly as attributes on the Customer entity (accessory_sales list +
// accessory_revenue_total rollup), the same "own lifecycle state on the
// customer" convention core/customer_journey.py established. Backed by 6
// dedicated /accessories/* routes (api/routers/accessories.py), not the generic
// /menu/data dispatch -- same "bespoke board bypasses /menu/data for its own
// extra views" precedent lib/customerJourney.ts and every other rebuild in this
// codebase established.
// Mirrors lib/customerJourney.ts's client pattern exactly (API_BASE + authHeaders
// + a shared handle<T> helper, one thin function per route).

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

// The six real accessory categories -- must stay in step with
// core/accessories.py's CATEGORIES list (order is load-bearing for the
// overview's revenue_by_category seeding).
export const ACCESSORY_CATEGORIES = [
  "truck_accessories",
  "protection_packages",
  "oem_accessories",
  "lift_kits",
  "wheels",
  "tint",
] as const;
export type AccessoryCategory = (typeof ACCESSORY_CATEGORIES)[number];

// One catalog item (id / category / name / price) -- mirrors ACCESSORY_CATALOG
// entries in core/accessories.py.
export type CatalogItem = {
  id: string;
  category: string;
  name: string;
  price: number;
};

export type AccessoriesCatalog = {
  categories: string[];
  items: CatalogItem[];
  basis: string;
  disclaimer: string;
};

export type AccessoriesOverview = {
  total_accessory_revenue: number;
  revenue_by_category: Record<string, number>;
  total_sales: number;
  installed_count: number;
  pending_count: number;
  customers_with_accessory_sale: number;
  total_customers: number;
  attach_rate_estimate: number;
  attach_rate_basis: string;
  attach_rate_disclaimer: string;
};

// One rule-based recommendation (top unpurchased item per category).
export type RecommendationItem = {
  category: string;
  item_id: string;
  name: string;
  price: number;
  reason: string;
};

export type Recommendation = {
  customer_id: string;
  name: string | null;
  recommendations: RecommendationItem[];
  basis: string;
  disclaimer: string;
};

// One priced line item on a sale.
export type SaleLineItem = {
  item_id: string;
  category: string;
  name: string;
  price: number;
};

// A recorded accessory sale (the "sale brief" create/install return).
export type AccessorySale = {
  sale_id: string;
  customer_id: string;
  line_items: SaleLineItem[];
  total_revenue: number;
  installed: boolean;
  installed_at: string | null;
  created_at: string;
};

// The AI accessory pitch -- pitch / highlighted_items / suggested_bundle_note
// plus an ai_generated flag, with honest disabled/fallback fields on the
// non-AI path (matches core/accessories.py's fallback_accessory_pitch()).
export type AccessoryPitch = {
  pitch: string;
  highlighted_items: string[];
  suggested_bundle_note: string;
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

export function getCatalog(category?: string): Promise<AccessoriesCatalog> {
  const query = category ? `?category=${encodeURIComponent(category)}` : "";
  return fetch(`${API_BASE}/accessories/catalog${query}`, {
    headers: { ...authHeaders() },
  }).then(handle<AccessoriesCatalog>);
}

export function getAccessoriesOverview(): Promise<AccessoriesOverview> {
  return fetch(`${API_BASE}/accessories/overview`, {
    headers: { ...authHeaders() },
  }).then(handle<AccessoriesOverview>);
}

export function getRecommendations(customerId: string): Promise<Recommendation> {
  return fetch(`${API_BASE}/accessories/customer/${encodeURIComponent(customerId)}/recommendations`, {
    headers: { ...authHeaders() },
  }).then(handle<Recommendation>);
}

export function createSale(customerId: string, itemIds: string[]): Promise<AccessorySale> {
  return fetch(`${API_BASE}/accessories/customer/${encodeURIComponent(customerId)}/sale`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ item_ids: itemIds }),
  }).then(handle<AccessorySale>);
}

export function markInstalled(customerId: string, saleId: string): Promise<AccessorySale> {
  return fetch(
    `${API_BASE}/accessories/customer/${encodeURIComponent(customerId)}/sale/${encodeURIComponent(saleId)}/install`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
    }
  ).then(handle<AccessorySale>);
}

export function generatePitch(customerId: string): Promise<AccessoryPitch> {
  return fetch(`${API_BASE}/accessories/customer/${encodeURIComponent(customerId)}/pitch`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
  }).then(handle<AccessoryPitch>);
}
