// Inventory department's "Inventory" Top Menu item -- the Master Vehicle
// Workspace (Inventory rebuild, first slice, Sam picked this over Acquisitions/
// Pricing/Overview). Backend: core/inventory_menu.py's inventory(role, query),
// reached via the same generic GET /menu/data route every other bespoke board
// uses (menuData() helper below, same pattern as lib/customers360.ts). The
// per-vehicle detail data (lifecycle/cost breakdown/ownership/activity feed) is
// the real core/vehicle_lifecycle.py engine, surfaced here through
// inventory_menu.py's VEH- branch so the plain chat/menu path and this
// dedicated board agree -- see that module's docstring.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type InventoryListItem = {
  id: string;
  vin: string | null;
  stock_number: string | null;
  year: string | number | null;
  make: string | null;
  model: string | null;
  condition: string | null;
  lot: string | null;
  price: string | number | null;
  photo_url?: string | null;
  mileage?: string | number | null;
};

// Phase 2/3: one normalized vehicle shape + a normalizer so every app inventory surface
// (list, grid, showroom) renders the same fields — including the real primary photo — from
// either the default-view list items (flat lowercase keys) or search hits (capitalized
// attributes). One place to map, so a fix (like photos) propagates everywhere.
export type NormalizedVehicle = {
  id: string;
  title: string;         // "2022 Ford F-150"
  subtitle: string;      // "45,000 mi · Used · Stock #..."
  price: number | null;
  photoUrl: string | null;
  vin: string | null;
};

function _num(v: unknown): number | null {
  if (v === null || v === undefined || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function _str(v: unknown): string {
  return v === null || v === undefined ? "" : String(v);
}

export function normalizeListItem(v: InventoryListItem): NormalizedVehicle {
  const mileage = _num(v.mileage);
  const subtitleParts = [
    mileage !== null ? `${mileage.toLocaleString()} mi` : "",
    _str(v.condition),
    v.stock_number ? `Stock #${v.stock_number}` : "",
  ].filter(Boolean);
  return {
    id: v.id,
    title: [v.year, v.make, v.model].filter(Boolean).join(" ") || v.vin || v.id,
    subtitle: subtitleParts.join(" · "),
    price: _num(v.price),
    photoUrl: v.photo_url ?? null,
    vin: v.vin ?? null,
  };
}

export function normalizeSearchHit(hit: { id: string; attributes: Record<string, unknown>; photo_url?: string | null }): NormalizedVehicle {
  const a = hit.attributes || {};
  const mileage = _num(a.Mileage ?? a.mileage);
  const subtitleParts = [
    mileage !== null ? `${mileage.toLocaleString()} mi` : "",
    _str(a.Condition ?? a.condition),
    a.StockNumber ? `Stock #${a.StockNumber}` : "",
  ].filter(Boolean);
  return {
    id: hit.id,
    title: [a.Year ?? a.year, a.Make ?? a.make, a.Model ?? a.model].filter(Boolean).join(" ") || _str(a.VIN ?? a.vin) || hit.id,
    subtitle: subtitleParts.join(" · "),
    price: _num(a.Price ?? a.price),
    photoUrl: (hit.photo_url as string | null | undefined) ?? (a.photo_url as string | null | undefined) ?? null,
    vin: (a.VIN ?? a.vin ?? null) as string | null,
  };
}

export type InventorySummary = {
  default_view: "unsold_inventory";
  count: number;
  vehicles: InventoryListItem[];
};

export type InventorySearchResults = {
  query: string;
  count: number;
  results: { id: string; entity_type: string; attributes: Record<string, unknown>; photo_url?: string | null }[];
};

export type VehicleDetail = {
  vehicle: { id: string; entity_type: string; attributes: Record<string, unknown> };
  related_entities: Record<string, unknown>[];
  vehicle_profile: {
    cost_basis: string | number | null;
    current_price: string | number | null;
    margin: number | null;
    has_photos: boolean;
  };
  lifecycle: {
    lifecycle_status: string;
    status_history: { status: string; at: string; by: string }[];
    recon_checklist: Record<string, { complete: boolean; notes: string; updated_by: string | null; updated_at: string | null }>;
    vendor_assignments: {
      id: string; vendor_type: string; vendor_name: string; status: string; notes: string;
      assigned_by: string; assigned_at: string; updated_by: string | null; updated_at: string | null; completed_at: string | null;
    }[];
  } | null;
  cost_breakdown: {
    vehicle_id: string;
    breakdown: Record<string, number | string>;
    total_investment: number | null;
    acquisition_cost_is_default: boolean;
    updated_by: string | null;
    updated_at: string | null;
  } | null;
  ownership: {
    vehicle_id: string;
    assignments: Record<string, string | null>;
    updated_by: string | null;
    updated_at: string | null;
  } | null;
  activity_feed: {
    vehicle_id: string;
    count: number;
    events: { type: string; label: string; at: string; by: string | null; notes: string | null }[];
  } | null;
  not_yet_tracked: Record<string, string>;
};

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

function menuData<T>(query?: string): Promise<T> {
  const params = new URLSearchParams({ department: "Inventory", item_key: "inventory" });
  if (query) params.set("query", query);
  return fetch(`${API_BASE}/menu/data?${params.toString()}`, { headers: { ...authHeaders() } }).then(handle<T>);
}

export function getInventorySummary(): Promise<InventorySummary> {
  return menuData<InventorySummary>();
}

export function searchInventory(query: string): Promise<InventorySearchResults> {
  return menuData<InventorySearchResults>(query);
}

export function getVehicleDetail(vehicleId: string): Promise<VehicleDetail> {
  return menuData<VehicleDetail>(vehicleId);
}
