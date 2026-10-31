// Operations' Overview + Action Center (session 106 follow-up #2). Backend:
// core/operations_overview.py / _api.py. Renders ABOVE the generic KPI Overview
// board (same "ABOVE, not instead of" precedent as SalesOverviewBoard, session 94).

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type DealBrief = { deal_id: string; customer_id: string | null; vehicle_id: string | null; status: string };
export type VehicleBrief = { vehicle_id: string; vin: string | null; stock_number: string | null; year?: string; make?: string; model?: string; price?: string | number };

export type ActionCenter = {
  deliveries_at_risk: { count: number; deals: DealBrief[]; note: string };
  vehicles_missing_titles: { count: number; vehicles: VehicleBrief[] };
  vehicles_awaiting_inspection: { count: number; vehicles: VehicleBrief[]; note: string };
  compliance_violations: { count: number | null; error: string | null };
  wholesale_candidates_needing_decision: { count: number; vehicles: Record<string, unknown>[]; substituted_for: string };
};

export type DepartmentHealthCheck = { area: string; status: "healthy" | "warning"; detail: string };
export type DepartmentHealth = { checks: DepartmentHealthCheck[] };

export type WorkloadArea = {
  area: string;
  headcount: number;
  employee_ids: string[];
  open_task_count: number;
  load: "low" | "moderate" | "high" | "unstaffed";
  note?: string;
};
export type WorkloadDistribution = { areas: WorkloadArea[]; methodology_note: string; reassignment_note: string };

export type OperationsOverview = {
  action_center: ActionCenter;
  department_health: DepartmentHealth;
  workload_distribution: WorkloadDistribution;
};

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

export async function getOperationsOverview(): Promise<OperationsOverview> {
  const res = await fetch(`${API_BASE}/operations/overview`, { headers: { ...authHeaders() } });
  return handle(res);
}
