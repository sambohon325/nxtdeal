// Inventory Aging Management (session 106 follow-up #4) -- backs Operations'
// own "Inventory" Top Menu item (distinct from Sales' own "Inventory" item,
// lib/inventorySales.ts -- a sales-facing locator/hold/compare tool, not a
// pricing-desk action layer). Backend: core/inventory_aging.py / _api.py.
//
// Price banding is the honest HEURISTIC proxy for true day-based aging --
// Vehicle has no acquisition-date field anywhere in this codebase (same
// finding sessions 63/85/106 already made). Actions: Price Reduction (a real
// mutation, new capability), Wholesale/Manager/Auction review (create a real
// OperationsTask, reusing lib/operationsTasks.ts's backing engine), Marketing
// Campaign tie-in (creates a real draft inventory_ads Campaign).

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type PriceBand = "under_15k" | "15k_25k" | "25k_40k" | "40k_plus";

export type AgingVehicleBrief = {
  vehicle_id: string;
  vin: string | null;
  stock_number: string | null;
  year: string | null;
  make: string | null;
  model: string | null;
  price: number;
  cost: number | null;
  margin_pct: number | null;
  price_band: PriceBand;
  price_history_count: number;
};

export type AgingBoard = {
  unsold_count: number;
  by_price_band: Record<PriceBand, AgingVehicleBrief[]>;
  note: string;
};

export type PriceHistoryEntry = {
  old_price: number;
  new_price: number;
  reason: string;
  updated_by: string;
  updated_at: string;
};

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

export async function getAgingBoard(): Promise<AgingBoard> {
  const res = await fetch(`${API_BASE}/inventory-aging/board`, { headers: { ...authHeaders() } });
  return handle(res);
}

export type VehicleAgingBrief = {
  vehicle: AgingVehicleBrief;
  price_history: PriceHistoryEntry[];
  note: string;
};

// Single-vehicle aging lookup -- added for Inventory's own Aging Action
// Center tab (InventoryWorkspaceBoard.tsx's Vehicle Detail modal), distinct
// from Operations' full-board InventoryAgingBoard.tsx above.
export async function getVehicleAgingBrief(vehicleId: string): Promise<VehicleAgingBrief> {
  const res = await fetch(`${API_BASE}/inventory-aging/${encodeURIComponent(vehicleId)}`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function reduceVehiclePrice(vehicleId: string, newPrice: number, reason = ""): Promise<{ vehicle: AgingVehicleBrief; history: PriceHistoryEntry[] }> {
  const res = await fetch(`${API_BASE}/inventory-aging/${encodeURIComponent(vehicleId)}/reduce-price`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ new_price: newPrice, reason }),
  });
  return handle(res);
}

export async function requestWholesaleReview(vehicleId: string, notes = ""): Promise<{ id: string }> {
  const res = await fetch(`${API_BASE}/inventory-aging/${encodeURIComponent(vehicleId)}/wholesale-review`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ notes }),
  });
  return handle(res);
}

export async function requestManagerReview(vehicleId: string, notes = ""): Promise<{ id: string }> {
  const res = await fetch(`${API_BASE}/inventory-aging/${encodeURIComponent(vehicleId)}/manager-review`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ notes }),
  });
  return handle(res);
}

export async function requestAuctionAssignment(vehicleId: string, notes = ""): Promise<{ id: string }> {
  const res = await fetch(`${API_BASE}/inventory-aging/${encodeURIComponent(vehicleId)}/auction-assignment`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ notes }),
  });
  return handle(res);
}

export async function createMarketingTieIn(vehicleId: string): Promise<{ campaign: { id: string }; task: { id: string } }> {
  const res = await fetch(`${API_BASE}/inventory-aging/${encodeURIComponent(vehicleId)}/marketing-tie-in`, {
    method: "POST",
    headers: { ...authHeaders() },
  });
  return handle(res);
}
