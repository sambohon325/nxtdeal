// NXTDeal VIN Intelligence, Phase 1 (Core VIN Decoder) -- backs Inventory's
// own Master Vehicle Workspace (InventoryWorkspaceBoard.tsx's Vehicle Detail
// modal). Backend: core/vin_decoder.py / vin_decoder_api.py.
//
// Two real, honestly distinct data sources, never blurred together: offline,
// standards-based decode (VIN format/check-digit/WMI/model-year -- real,
// deterministic, per FMVSS 115 / ISO 3779) and a live NHTSA vPIC lookup
// (Model/Trim/Engine/Transmission/Drive Type/Fuel Type/Body Style -- real,
// wired code, but this sandbox has confirmed zero outbound network access,
// so `live` will be null and `live_error`/`gap_note` will explain why until
// this runs in a deployment with real outbound access).

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type VinDecodeOffline = {
  vin: string;
  valid_format: boolean;
  format_error: string | null;
  check_digit_valid: boolean | null;
  expected_check_digit: string | null;
  wmi: string | null;
  wmi_recognized: boolean;
  manufacturer: string | null;
  country_of_origin: string | null;
  vehicle_type_hint: string | null;
  model_year: number | null;
  model_year_candidates: number[];
  model_year_basis: string | null;
  plant_code: string | null;
  serial_number: string | null;
};

export type VinDecodeLive = {
  success: true;
  source: "nhtsa_vpic_live";
  make: string | null;
  model: string | null;
  model_year: string | null;
  trim: string | null;
  body_style: string | null;
  vehicle_type: string | null;
  engine_cylinders: string | null;
  engine_displacement_l: string | null;
  fuel_type: string | null;
  drive_type: string | null;
  transmission: string | null;
  doors: string | null;
  plant_country: string | null;
  manufacturer_name: string | null;
  raw: Record<string, unknown>;
};

export type VinDecodeResolved = {
  year: number | string | null;
  make: string | null;
  model: string | null;
  trim: string | null;
  engine: string | null;
  transmission: string | null;
  drive_type: string | null;
  fuel_type: string | null;
  body_style: string | null;
};

export type VinDecodeBasis = Record<keyof VinDecodeResolved, "nhtsa_vpic_live" | "iso_3779_offline" | "wmi_offline" | "unavailable">;

export type VinDecodeResult = {
  vin: string;
  valid_format: boolean;
  format_error: string | null;
  check_digit_valid: boolean | null;
  expected_check_digit: string | null;
  offline: VinDecodeOffline;
  live: VinDecodeLive | null;
  live_error: string | null;
  resolved: VinDecodeResolved;
  basis: VinDecodeBasis;
  gaps: string[];
  gap_note: string | null;
};

export type VinDecodeAppliedRecord = {
  decoded_at: string;
  decoded_by: string;
  check_digit_valid: boolean | null;
  resolved: VinDecodeResolved;
  basis: VinDecodeBasis;
  gaps: string[];
  live_error: string | null;
  backfilled_fields: string[];
};

export type VinDecodeApplyResult = {
  vehicle_id: string;
  decode: VinDecodeResult;
  applied: VinDecodeAppliedRecord;
};

export type VehicleVinDecodeResponse = {
  vehicle_id: string;
  vin_decode: VinDecodeAppliedRecord | null;
  note?: string;
};

export type VinBulkApplyResultRow =
  | { vehicle_id: string; error: string }
  | { vehicle_id: string; backfilled_fields: string[]; check_digit_valid: boolean | null };

export type VinBulkApplyResult = {
  attempted: number;
  succeeded: number;
  results: VinBulkApplyResultRow[];
  note: string;
};

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

export async function decodeVin(vin: string, attemptLive = true): Promise<VinDecodeResult> {
  const res = await fetch(`${API_BASE}/vin-decoder/decode`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ vin, attempt_live: attemptLive }),
  });
  return handle(res);
}

export async function getVehicleVinDecode(vehicleId: string): Promise<VehicleVinDecodeResponse> {
  const res = await fetch(`${API_BASE}/vin-decoder/vehicle/${encodeURIComponent(vehicleId)}`, {
    headers: { ...authHeaders() },
  });
  return handle(res);
}

export async function applyVinDecodeToVehicle(vehicleId: string, attemptLive = true): Promise<VinDecodeApplyResult> {
  const res = await fetch(`${API_BASE}/vin-decoder/vehicle/${encodeURIComponent(vehicleId)}/apply`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ attempt_live: attemptLive }),
  });
  return handle(res);
}

export async function bulkApplyVinDecode(
  vehicleIds?: string[],
  attemptLive = true,
  limit = 100
): Promise<VinBulkApplyResult> {
  const res = await fetch(`${API_BASE}/vin-decoder/bulk-apply`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ vehicle_ids: vehicleIds ?? null, attempt_live: attemptLive, limit }),
  });
  return handle(res);
}

// --- VIN Lookup widget (NXTDeal VIN Intelligence, Phase 3) -----------------------
//
// Backs the global floating "VIN" widget (VinLookupWidget.tsx) -- reachable from
// anywhere in the app, not scoped to Inventory's own Master Vehicle Workspace.
// Reuses decodeVin() above for the actual decode (no second decode engine) and the
// same generic GET /search endpoint every other domain's "does this already exist"
// check already uses (deals.ts's searchCustomers, leadRecord.ts's searchLeads) --
// no VIN-specific search route was built, since this one already does the job.

export type VinInventoryMatch = {
  id: string;
  entity_type: string;
  attributes: Record<string, unknown>;
};

export async function searchVehicleByVin(vin: string): Promise<VinInventoryMatch[]> {
  const trimmed = vin.trim();
  if (!trimmed) return [];
  const res = await fetch(`${API_BASE}/search?q=${encodeURIComponent(trimmed)}`, {
    headers: { ...authHeaders() },
  });
  const results = await handle<VinInventoryMatch[]>(res);
  return results.filter((r) => r.entity_type === "Vehicle");
}
