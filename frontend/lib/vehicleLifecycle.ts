// Vehicle Lifecycle Management (session 106 follow-up) -- the flagship build of
// Operations' rebuild. Backend: core/vehicle_lifecycle.py / _api.py. Sam's own
// framing: "Sales should manage the customer lifecycle. Operations should manage
// the vehicle lifecycle... This should be one of the largest operational modules."
//
// Internal cross-department messaging about a specific vehicle reuses the
// existing generic FieldNote mechanism (POST/GET /notes, core/field_notes.py) with
// category="vehicle_message" and linked_entity_id=the Vehicle's id -- no new
// backend route needed for that part.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type LifecycleStage =
  | "Acquired" | "In Transit" | "Received" | "Inspection" | "Recon"
  | "Photo" | "Merchandising" | "Front Line Ready" | "Sold" | "Delivered";

export type ReconItem = "inspection" | "oil_change" | "tires" | "body_work" | "photos";
export type VendorType = "body_shop" | "detail" | "paint" | "glass" | "other";
export type VendorStatus = "assigned" | "in_progress" | "complete";

export type CostField = "acquisition_cost" | "transport_cost" | "recon_cost" | "floorplan_interest" | "marketing_cost";
export type OwnershipRole = "buyer" | "inventory_manager" | "recon_manager" | "sales_manager";

export type LifecycleCatalog = {
  stages: LifecycleStage[];
  recon_items: ReconItem[];
  vendor_types: VendorType[];
  vendor_statuses: VendorStatus[];
  cost_fields: CostField[];
  ownership_roles: OwnershipRole[];
};

export type ReconChecklistEntry = {
  complete: boolean;
  notes: string;
  updated_by: string | null;
  updated_at: string | null;
};

export type VendorAssignment = {
  id: string;
  vendor_type: VendorType;
  vendor_name: string;
  status: VendorStatus;
  notes: string;
  assigned_by: string;
  assigned_at: string;
  updated_by: string | null;
  updated_at: string | null;
  completed_at: string | null;
};

export type AcquisitionData = {
  cost: string | number | null;
  lot: string | null;
  condition: string | null;
  auction_data: {
    auction_house: string | null;
    bid_amount: number | null;
    purchase_date: string | null;
    carrier: string | null;
    transport_status: string | null;
  } | null;
  not_yet_tracked?: string;
};

export type VehicleLifecycle = {
  vehicle_id: string;
  vin: string | null;
  stock_number: string | null;
  year: string | null;
  make: string | null;
  model: string | null;
  trim: string | null;
  color: string | null;
  mileage: string | null;
  price: string | number | null;
  date_sold: string | null;
  lifecycle_status: LifecycleStage;
  lifecycle_status_is_default: boolean;
  status_history: { status: string; at: string; by: string }[];
  recon_checklist: Record<ReconItem, ReconChecklistEntry>;
  vendor_assignments: VendorAssignment[];
  acquisition: AcquisitionData;
};

export type LifecycleBoard = Record<string, { vehicle_id: string; vin: string | null; stock_number: string | null; year: string | null; make: string | null; model: string | null; price: string | number | null }[]>;

// Inventory department's Master Vehicle Workspace (Inventory rebuild, first
// slice -- Cost Breakdown, Ownership, Activity Feed on top of the same
// Vehicle lifecycle data above). Backend: core/vehicle_lifecycle.py's
// get_cost_breakdown/assign_ownership/get_vehicle_activity_feed/
// get_vehicle_workspace + core/vehicle_lifecycle_api.py's ACL wrappers.

export type CostBreakdown = {
  vehicle_id: string;
  breakdown: Record<CostField, number | string>;
  total_investment: number | null;
  acquisition_cost_is_default: boolean;
  updated_by: string | null;
  updated_at: string | null;
};

export type Ownership = {
  vehicle_id: string;
  assignments: Record<OwnershipRole, string | null>;
  updated_by: string | null;
  updated_at: string | null;
};

export type ActivityEvent = {
  type: string;
  label: string;
  at: string;
  by: string | null;
  notes: string | null;
};

export type ActivityFeed = {
  vehicle_id: string;
  count: number;
  events: ActivityEvent[];
};

export type VehicleWorkspace = VehicleLifecycle & {
  cost_breakdown: CostBreakdown;
  ownership: Ownership;
  activity_feed: ActivityFeed;
};

export type VehicleMessage = {
  id: string;
  category: string;
  body: string;
  created_by: string;
  created_at: string;
};

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

export async function getLifecycleCatalog(): Promise<LifecycleCatalog> {
  const res = await fetch(`${API_BASE}/vehicle-lifecycle/catalog`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function getLifecycleBoard(stage?: LifecycleStage): Promise<LifecycleBoard> {
  const params = stage ? `?stage=${encodeURIComponent(stage)}` : "";
  const res = await fetch(`${API_BASE}/vehicle-lifecycle/board${params}`, { headers: { ...authHeaders() } });
  return handle(res);
}

// Phase 6: reconditioning cycle-time + SLA analytics.
export type ReconMetrics = {
  vehicles_tracked: number;
  in_stage: Record<string, number>;
  avg_days_in_stage: Record<string, number | null>;
  avg_cycle_time_days: number | null;
  front_line_ready_count: number;
  sla_breaching_count: number;
  stage_sla_days: Record<string, number>;
};

export type ReconSlaAlert = {
  vehicle_id: string;
  vehicle: string;
  stage: string;
  days_in_stage: number;
  sla_days: number;
  days_over: number;
};

export async function getReconMetrics(): Promise<ReconMetrics> {
  const res = await fetch(`${API_BASE}/vehicle-lifecycle/recon-metrics`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function getReconSlaAlerts(): Promise<{ count: number; alerts: ReconSlaAlert[] }> {
  const res = await fetch(`${API_BASE}/vehicle-lifecycle/recon-alerts`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function getVehicleLifecycle(vehicleId: string): Promise<VehicleLifecycle> {
  const res = await fetch(`${API_BASE}/vehicle-lifecycle/${encodeURIComponent(vehicleId)}`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function updateLifecycleStatus(vehicleId: string, newStatus: LifecycleStage): Promise<VehicleLifecycle> {
  const res = await fetch(`${API_BASE}/vehicle-lifecycle/${encodeURIComponent(vehicleId)}/status`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ new_status: newStatus }),
  });
  return handle(res);
}

export async function updateReconItem(vehicleId: string, item: ReconItem, complete: boolean, notes = ""): Promise<VehicleLifecycle> {
  const res = await fetch(`${API_BASE}/vehicle-lifecycle/${encodeURIComponent(vehicleId)}/recon`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ item, complete, notes }),
  });
  return handle(res);
}

export async function assignVendor(vehicleId: string, vendorType: VendorType, vendorName: string, notes = ""): Promise<VehicleLifecycle> {
  const res = await fetch(`${API_BASE}/vehicle-lifecycle/${encodeURIComponent(vehicleId)}/vendor`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ vendor_type: vendorType, vendor_name: vendorName, notes }),
  });
  return handle(res);
}

export async function updateVendorStatus(vehicleId: string, assignmentId: string, newStatus: VendorStatus): Promise<VehicleLifecycle> {
  const res = await fetch(`${API_BASE}/vehicle-lifecycle/${encodeURIComponent(vehicleId)}/vendor/${encodeURIComponent(assignmentId)}/status`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ new_status: newStatus }),
  });
  return handle(res);
}

export async function getVehicleMessages(vehicleId: string): Promise<VehicleMessage[]> {
  const res = await fetch(`${API_BASE}/notes?linked_entity_id=${encodeURIComponent(vehicleId)}`, { headers: { ...authHeaders() } });
  const data = await handle<{ notes: VehicleMessage[] }>(res);
  return (data.notes || []).filter((n) => n.category === "vehicle_message");
}

export async function sendVehicleMessage(vehicleId: string, body: string): Promise<VehicleMessage> {
  const res = await fetch(`${API_BASE}/notes`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ department: "Operations", category: "vehicle_message", body, linked_entity_id: vehicleId }),
  });
  return handle(res);
}

export async function getVehicleWorkspace(vehicleId: string): Promise<VehicleWorkspace> {
  const res = await fetch(`${API_BASE}/vehicle-lifecycle/${encodeURIComponent(vehicleId)}/workspace`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function getCostBreakdown(vehicleId: string): Promise<CostBreakdown> {
  const res = await fetch(`${API_BASE}/vehicle-lifecycle/${encodeURIComponent(vehicleId)}/cost-breakdown`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function updateCostBreakdown(vehicleId: string, fields: Partial<Record<CostField, number>>): Promise<CostBreakdown> {
  const res = await fetch(`${API_BASE}/vehicle-lifecycle/${encodeURIComponent(vehicleId)}/cost-breakdown`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(fields),
  });
  return handle(res);
}

export async function getOwnership(vehicleId: string): Promise<Ownership> {
  const res = await fetch(`${API_BASE}/vehicle-lifecycle/${encodeURIComponent(vehicleId)}/ownership`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function assignOwnership(vehicleId: string, roles: Partial<Record<OwnershipRole, string>>): Promise<Ownership> {
  const res = await fetch(`${API_BASE}/vehicle-lifecycle/${encodeURIComponent(vehicleId)}/ownership`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(roles),
  });
  return handle(res);
}

export async function getVehicleActivityFeed(vehicleId: string): Promise<ActivityFeed> {
  const res = await fetch(`${API_BASE}/vehicle-lifecycle/${encodeURIComponent(vehicleId)}/activity`, { headers: { ...authHeaders() } });
  return handle(res);
}
