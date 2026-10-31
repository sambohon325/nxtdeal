// Demo Drive (session 102 follow-up) -- a real test-drive log: which prospect drove
// which vehicle, with which salesperson, license verification, out/in odometer, and an
// out -> returned lifecycle. Backend: core/demo_drive.py / demo_drive_api.py.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type DemoDriveStatus = "out" | "returned" | "cancelled";
export type InterestLevel = "hot" | "warm" | "cold";

export type DemoDrive = {
  id: string;
  linked_entity_id: string;
  linked_entity_type: string;
  driver_label: string;
  vehicle_id: string;
  vehicle_label: string;
  salesperson_id: string;
  salesperson_name: string | null;
  license_number: string;
  license_verified: boolean;
  status: DemoDriveStatus;
  odometer_out: number | null;
  odometer_in: number | null;
  miles_driven: number | null;
  start_at: string | null;
  end_at: string | null;
  duration_minutes: number | null;
  interest_level: InterestLevel | null;
  notes: string;
  feedback: string;
};

export type DemoDriveStats = {
  total: number;
  active: number;
  returned: number;
  cancelled: number;
  license_verified_pct: number | null;
  avg_duration_minutes: number | null;
  avg_miles_driven: number | null;
};

export type DemoDriveDashboard = {
  active: DemoDrive[];
  stats: DemoDriveStats;
};

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

export async function getDemoDriveDashboard(): Promise<DemoDriveDashboard> {
  const res = await fetch(`${API_BASE}/demo-drives/dashboard`, { headers: { ...authHeaders() } });
  return handle(res);
}

// Session 102 follow-up -- real history for the Interest & Follow-Up tab (returned
// drives with their interest_level/feedback). Route already existed (GET
// /demo-drives?status=), just never had a client wrapper.
export async function listDemoDrives(status?: DemoDriveStatus): Promise<DemoDrive[]> {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  const res = await fetch(`${API_BASE}/demo-drives?${params.toString()}`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function startDemoDrive(input: {
  linked_entity_id: string;
  vehicle_id: string;
  salesperson_id: string;
  license_number?: string;
  license_verified: boolean;
  odometer_out?: number | null;
  notes?: string;
}): Promise<DemoDrive> {
  const res = await fetch(`${API_BASE}/demo-drives`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(input),
  });
  return handle(res);
}

export async function returnDemoDrive(
  demoId: string,
  input: { odometer_in?: number | null; interest_level?: InterestLevel | null; feedback?: string },
): Promise<DemoDrive> {
  const res = await fetch(`${API_BASE}/demo-drives/${encodeURIComponent(demoId)}/return`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(input),
  });
  return handle(res);
}

export async function cancelDemoDrive(demoId: string): Promise<DemoDrive> {
  const res = await fetch(`${API_BASE}/demo-drives/${encodeURIComponent(demoId)}/cancel`, {
    method: "POST",
    headers: { ...authHeaders() },
  });
  return handle(res);
}
