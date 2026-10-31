// Inventory department's "Lot Management" item -- physical inventory
// control (Inventory rebuild, fifth slice). Backend: core/lot_control.py /
// _api.py. Unlike Pricing/Acquisitions (SIMULATED, since real market data
// genuinely doesn't exist), Lot Map/Key Management/Damage Reports/Showroom
// Assignments are all REAL features here -- internal tracking capabilities
// this codebase simply hadn't built yet, not external data gaps.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type KeyStatusValue = "on_lot" | "checked_out" | "missing";
export type DamageSeverity = "minor" | "moderate" | "severe";
export type DamageStatus = "open" | "in_repair" | "resolved";

export type VehicleBrief = {
  vehicle_id: string;
  vin: string | null;
  stock_number: string | null;
  year: string | null;
  make: string | null;
  model: string | null;
  lot: string | null;
};

export type LotPosition = {
  row: string | null;
  space: string | null;
  section: string | null;
  notes: string;
  updated_by: string;
  updated_at: string;
} | null;

export type LotMapEntry = VehicleBrief & { lot_position: LotPosition };

export type LotMap = {
  by_lot: Record<string, LotMapEntry[]>;
  total_unsold: number;
  positioned_count: number;
  unpositioned_count: number;
};

export type KeyStatus = {
  status: KeyStatusValue;
  holder: string | null;
  checked_out_at?: string;
  checked_in_at?: string;
  reported_at?: string;
};

export type KeyLogEntry = {
  action: string;
  holder?: string | null;
  notes: string;
  updated_by: string;
  at: string;
};

export type KeyBoard = {
  checked_out: (VehicleBrief & { key_status: KeyStatus })[];
  missing: (VehicleBrief & { key_status: KeyStatus })[];
  on_lot_count: number;
};

export type DamageReport = {
  id: string;
  vehicle_id: string;
  severity: DamageSeverity;
  description: string;
  estimated_cost: number | null;
  status: DamageStatus;
  reported_by: string;
  reported_at: string;
  updated_by: string | null;
  updated_at: string | null;
  resolved_by: string | null;
  resolved_at: string | null;
  resolution_notes: string;
};

export type ShowroomAssignment = {
  assigned: boolean;
  assigned_by?: string;
  assigned_at?: string;
  removed_by?: string;
  removed_at?: string;
  notes?: string;
} | null;

export type ShowroomBoard = {
  count: number;
  vehicles: (VehicleBrief & { showroom_assignment: ShowroomAssignment })[];
};

export type ScanLogEntry = { scanned_by: string; location_note: string; at: string };

export type LotControlView = {
  vehicle: VehicleBrief;
  lot_position: LotPosition;
  key_status: KeyStatus;
  key_log: KeyLogEntry[];
  damage_reports: DamageReport[];
  showroom_assignment: ShowroomAssignment;
  scan_log: ScanLogEntry[];
};

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

export function getLotMap(): Promise<LotMap> {
  return get("/lot-control/map");
}

export function getKeyBoard(): Promise<KeyBoard> {
  return get("/lot-control/keys/board");
}

export function getShowroomBoard(): Promise<ShowroomBoard> {
  return get("/lot-control/showroom/board");
}

export function listDamageReports(vehicleId?: string, status?: DamageStatus): Promise<{ count: number; reports: DamageReport[] }> {
  const params = new URLSearchParams();
  if (vehicleId) params.set("vehicle_id", vehicleId);
  if (status) params.set("status", status);
  const qs = params.toString();
  return get(`/lot-control/damage-reports${qs ? `?${qs}` : ""}`);
}

export function updateDamageStatus(reportId: string, newStatus: DamageStatus, resolutionNotes = ""): Promise<DamageReport> {
  return post(`/lot-control/damage-reports/${encodeURIComponent(reportId)}/status`, { new_status: newStatus, resolution_notes: resolutionNotes });
}

export function getLotControlView(vehicleId: string): Promise<LotControlView> {
  return get(`/lot-control/${encodeURIComponent(vehicleId)}`);
}

export function setLotPosition(vehicleId: string, row?: string, space?: string, section?: string, notes = ""): Promise<{ vehicle_id: string; lot_position: LotPosition }> {
  return post(`/lot-control/${encodeURIComponent(vehicleId)}/position`, { row, space, section, notes });
}

export function checkoutKey(vehicleId: string, holder: string, notes = ""): Promise<{ vehicle_id: string; key_status: KeyStatus; log: KeyLogEntry[] }> {
  return post(`/lot-control/${encodeURIComponent(vehicleId)}/key/checkout`, { holder, notes });
}

export function checkinKey(vehicleId: string, notes = ""): Promise<{ vehicle_id: string; key_status: KeyStatus; log: KeyLogEntry[] }> {
  return post(`/lot-control/${encodeURIComponent(vehicleId)}/key/checkin`, { notes });
}

export function reportKeyMissing(vehicleId: string, notes = ""): Promise<{ vehicle_id: string; key_status: KeyStatus; log: KeyLogEntry[] }> {
  return post(`/lot-control/${encodeURIComponent(vehicleId)}/key/missing`, { notes });
}

export function reportDamage(vehicleId: string, severity: DamageSeverity, description: string, estimatedCost?: number): Promise<DamageReport> {
  return post(`/lot-control/${encodeURIComponent(vehicleId)}/damage-reports`, { severity, description, estimated_cost: estimatedCost });
}

export function assignShowroom(vehicleId: string, notes = ""): Promise<{ vehicle_id: string; showroom_assignment: ShowroomAssignment }> {
  return post(`/lot-control/${encodeURIComponent(vehicleId)}/showroom`, { notes });
}

export function removeShowroomAssignment(vehicleId: string): Promise<{ vehicle_id: string; showroom_assignment: ShowroomAssignment }> {
  return post(`/lot-control/${encodeURIComponent(vehicleId)}/showroom/remove`, {});
}

export function logScan(vehicleId: string, locationNote = ""): Promise<{ vehicle_id: string; scan_log: ScanLogEntry[] }> {
  return post(`/lot-control/${encodeURIComponent(vehicleId)}/scan`, { location_note: locationNote });
}
