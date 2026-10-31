// Digital Vehicle Inspection (DVI) -- the first of Sam's "completely
// missing" Service features. Real additive DVI state on the same
// ServiceRecord the RO Workflow Engine manages, tied to that engine's
// existing "Inspection" stage. The real tie-in: flagged (yellow/red)
// findings can be converted directly into real Concerns via
// createConcernsFromInspection, feeding straight into the RO's existing
// Concerns -> Estimate -> Customer Approval pipeline. Backend:
// core/vehicle_inspection.py / _api.py.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type InspectionStatus = "not_inspected" | "green" | "yellow" | "red";

export type DviCategory = { label: string; items: string[] };

export type DviCatalog = {
  categories: Record<string, DviCategory>;
  statuses: InspectionStatus[];
};

export type InspectionItem = {
  category: string;
  item: string;
  status: InspectionStatus;
  notes: string;
  photo_urls: string[];
  video_urls?: string[];
  concern_created: boolean;
  updated_by: string | null;
  updated_at: string | null;
};

export type Inspection = {
  ro_id: string;
  status: "not_started" | "in_progress" | "completed";
  started_by: string | null;
  started_at: string | null;
  completed_by: string | null;
  completed_at: string | null;
  summary: Record<InspectionStatus, number>;
  items: Record<string, InspectionItem>;
};

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

export async function getDviCatalog(): Promise<DviCatalog> {
  const res = await fetch(`${API_BASE}/dvi/catalog`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function getInspection(roId: string): Promise<Inspection> {
  const res = await fetch(`${API_BASE}/repair-orders/${encodeURIComponent(roId)}/inspection`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function startInspection(roId: string): Promise<Inspection> {
  const res = await fetch(`${API_BASE}/repair-orders/${encodeURIComponent(roId)}/inspection/start`, {
    method: "POST",
    headers: { ...authHeaders() },
  });
  return handle(res);
}

export async function updateInspectionItem(roId: string, itemKey: string, status: InspectionStatus, notes: string): Promise<Inspection> {
  const res = await fetch(`${API_BASE}/repair-orders/${encodeURIComponent(roId)}/inspection/item`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ item_key: itemKey, status, notes }),
  });
  return handle(res);
}

export async function attachInspectionPhoto(roId: string, itemKey: string, imageUrl: string, mediaType:"photo"|"video"="photo"): Promise<Inspection> {
  const res = await fetch(`${API_BASE}/repair-orders/${encodeURIComponent(roId)}/inspection/photo`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ item_key: itemKey, image_url: imageUrl, media_type:mediaType }),
  });
  return handle(res);
}

export async function completeInspection(roId: string): Promise<Inspection> {
  const res = await fetch(`${API_BASE}/repair-orders/${encodeURIComponent(roId)}/inspection/complete`, {
    method: "POST",
    headers: { ...authHeaders() },
  });
  return handle(res);
}

export async function createConcernsFromInspection(roId: string, itemKeys: string[]) {
  const res = await fetch(`${API_BASE}/repair-orders/${encodeURIComponent(roId)}/inspection/create-concerns`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ item_keys: itemKeys }),
  });
  return handle(res);
}

// Cross-RO Vehicle Inspection History (2026-07-19) -- closes Sam's "Digital
// Inspections' remaining asks" gap. Real, read-only composition across every
// completed/in-progress DVI recorded against this vehicle's VIN, plus a real
// "recurring findings" signal (same item flagged yellow/red in 2+ visits).

export type InspectionHistoryFlaggedItem = {
  item_key: string;
  category: string;
  item: string;
  status: InspectionStatus;
  notes: string;
};

export type InspectionHistoryEntry = {
  ro_id: string;
  service_date: string | null;
  dvi_status: "in_progress" | "completed";
  completed_at: string | null;
  summary: Record<InspectionStatus, number>;
  flagged_items: InspectionHistoryFlaggedItem[];
};

export type RecurringFinding = {
  category: string;
  item: string;
  label: string;
  occurrences: number;
};

export type InspectionHistory = {
  vehicle_id: string | null;
  vin: string | null;
  inspection_count: number;
  inspections: InspectionHistoryEntry[];
  recurring_findings: RecurringFinding[];
  note: string;
  error?: string;
};

export async function getVehicleInspectionHistory(vehicleIdOrVin: string): Promise<InspectionHistory> {
  const res = await fetch(`${API_BASE}/vehicle-inspection-history/${encodeURIComponent(vehicleIdOrVin)}`, {
    headers: { ...authHeaders() },
  });
  return handle(res);
}
