// Sales' "Inventory" item (session 99 follow-up) -- a sales-facing vehicle browser,
// payment-based search, a real Reservation/Hold mechanism (core/vehicle_holds.py),
// and a side-by-side Comparison Tool. Backend: core/sales_menu.py's inventory()/
// compare_vehicles(), core/vehicle_holds_api.py.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type VehicleBrief = {
  id: string;
  vin: string | null;
  year: number | string | null;
  make: string | null;
  model: string | null;
  trim: string | null;
  price: number | string | null;
  on_hold: boolean;
  held_by: string | null;
  hold_expires_at: string | null;
};

export type InventoryBrowse = {
  available_count: number;
  vehicles: VehicleBrief[];
  incoming: unknown;
  recently_sold: { id: string; vin: string | null; date_sold: string | null }[];
  not_yet_tracked: Record<string, string>;
};

export type PaymentSearchResult = {
  mode: "payment_based_search";
  target_monthly_payment: number;
  assumptions: { term_months: number; apr: number };
  estimated_max_price: number;
  count: number;
  vehicles: VehicleBrief[];
  note: string;
};

export type TextSearchResult = {
  mode: "text_search";
  query: string;
  count: number;
  results: (Record<string, unknown> & { id: string; on_hold?: boolean; held_by?: string | null; hold_expires_at?: string | null })[];
};

export type InventoryResult = InventoryBrowse | PaymentSearchResult | TextSearchResult;

export type VehicleHold = {
  id: string;
  vehicle_id: string;
  held_by: string;
  customer_id: string | null;
  lead_id: string | null;
  notes: string;
  status: string;
  placed_at: string;
  expires_at: string;
  released_at: string | null;
  released_by: string | null;
};

export type CompareResult = {
  count: number;
  vehicles: { id: string; attributes: Record<string, unknown>; on_hold: boolean; held_by: string | null }[];
  errors: { id: string; error: string }[];
};

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

export async function getInventory(query?: string): Promise<InventoryResult> {
  const params = new URLSearchParams({ department: "Sales", item_key: "inventory" });
  if (query && query.trim()) params.set("query", query.trim());
  const res = await fetch(`${API_BASE}/menu/data?${params.toString()}`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function placeHold(input: {
  vehicle_id: string;
  customer_id?: string | null;
  lead_id?: string | null;
  notes?: string;
  duration_hours?: number | null;
}): Promise<VehicleHold> {
  const res = await fetch(`${API_BASE}/inventory/holds`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(input),
  });
  return handle(res);
}

export async function releaseHold(holdId: string): Promise<VehicleHold> {
  const res = await fetch(`${API_BASE}/inventory/holds/${encodeURIComponent(holdId)}/release`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
  });
  return handle(res);
}

export async function listActiveHolds(): Promise<VehicleHold[]> {
  const res = await fetch(`${API_BASE}/inventory/holds`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function listMyHolds(): Promise<VehicleHold[]> {
  const res = await fetch(`${API_BASE}/inventory/holds?mine=true`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function compareVehicles(ids: string[]): Promise<CompareResult> {
  const params = new URLSearchParams({ ids: ids.join(",") });
  const res = await fetch(`${API_BASE}/sales/inventory/compare?${params.toString()}`, { headers: { ...authHeaders() } });
  return handle(res);
}
