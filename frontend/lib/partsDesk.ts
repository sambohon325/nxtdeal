// Service department's "Parts" item, fifth slice of Service's rebuild -- a
// real department-wide Parts Request Queue (previously only visible one RO
// at a time), Special Order Tracking (vendor/ETA, genuinely new), and
// Inventory Recommendations (REAL, computed off real PartSale velocity vs.
// real Part.QuantityOnHand -- no fabrication). Backend: core/parts_desk.py /
// _api.py.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type PartRequestEntry = {
  id: string;
  description: string;
  status: string;
  requested_by: string | null;
  requested_at: string | null;
  updated_by: string | null;
  updated_at: string | null;
  is_special_order?: boolean;
  vendor?: string | null;
  eta?: string | null;
  ro_id: string;
  service_number: string | null;
  ro_description: string | null;
  ro_stage: string;
  customer_name: string | null;
  vehicle: string | null;
};

export type PartsRequestQueue = {
  count: number;
  by_status: Record<string, number>;
  requests: PartRequestEntry[];
};

export type SpecialOrderEntry = PartRequestEntry & {
  days_until_eta: number | null;
  overdue: boolean;
};

export type SpecialOrders = {
  count: number;
  overdue_count: number;
  special_orders: SpecialOrderEntry[];
};

export type InventoryRecommendation = {
  part_id: string;
  part_number: string;
  description: string | null;
  category: string | null;
  quantity_on_hand: number;
  total_units_sold: number;
  velocity_per_day: number;
  days_of_supply: number | null;
  recommendation: string;
};

export type InventoryRecommendations = {
  count: number;
  recommendations: InventoryRecommendation[];
  not_yet_tracked: Record<string, string>;
};

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

export async function getPartsRequestQueue(status?: string): Promise<PartsRequestQueue> {
  const params = status ? `?status=${encodeURIComponent(status)}` : "";
  const res = await fetch(`${API_BASE}/parts-desk/queue${params}`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function getSpecialOrders(): Promise<SpecialOrders> {
  const res = await fetch(`${API_BASE}/parts-desk/special-orders`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function getInventoryRecommendations(): Promise<InventoryRecommendations> {
  const res = await fetch(`${API_BASE}/parts-desk/recommendations`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function markSpecialOrder(roId: string, requestId: string, vendor: string, eta: string) {
  const res = await fetch(`${API_BASE}/repair-orders/${encodeURIComponent(roId)}/mark-special-order`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ request_id: requestId, vendor, eta }),
  });
  return handle(res);
}
