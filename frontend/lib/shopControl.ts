// Service's "Shop Control" item, third slice of Service's rebuild -- Sam's
// framing: "the operational heart of the shop." Backend: core/shop_control.py
// / _api.py. The Shop Workflow Board itself isn't duplicated here -- it's the
// same real board lib/repairOrders.ts's getRoBoard() already provides; this
// covers Technician Dispatch (real drag-and-drop reassignment, via
// assignTechnician below), Technician Utilization, Stalled RO Detection, and
// Shop Bottlenecks.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";
import type { RoBrief } from "@/lib/repairOrders";

export type DispatchBoard = {
  technicians: Record<string, { name: string | null; repair_orders: RoBrief[] }>;
  unassigned: RoBrief[];
};

export type TechnicianUtilizationEntry = {
  technician_id: string;
  name: string | null;
  ro_count: number;
  hours_booked: number;
  assumed_capacity_hours: number;
  utilization_pct: number;
  overloaded: boolean;
};

export type TechnicianUtilization = {
  date: string;
  technicians: TechnicianUtilizationEntry[];
  note: string;
};

export type StalledRo = RoBrief & { hours_open: number };

export type StalledRos = {
  count: number;
  repair_orders: StalledRo[];
  hours_threshold: number;
};

export type Bottlenecks = {
  parts_delays: { count: number; repair_orders: RoBrief[] };
  approval_delays: { count: number; repair_orders: (RoBrief & { hours_open: number })[]; note: string };
  technician_delays: StalledRos;
};

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

export async function getDispatchBoard(): Promise<DispatchBoard> {
  const res = await fetch(`${API_BASE}/shop-control/dispatch-board`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function getTechnicianUtilization(date?: string): Promise<TechnicianUtilization> {
  const params = date ? `?date=${encodeURIComponent(date)}` : "";
  const res = await fetch(`${API_BASE}/shop-control/utilization${params}`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function getStalledRos(): Promise<StalledRos> {
  const res = await fetch(`${API_BASE}/shop-control/stalled`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function getBottlenecks(): Promise<Bottlenecks> {
  const res = await fetch(`${API_BASE}/shop-control/bottlenecks`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function assignTechnician(roId: string, technicianId: string | null) {
  const res = await fetch(`${API_BASE}/repair-orders/${encodeURIComponent(roId)}/assign-technician`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ technician_id: technicianId }),
  });
  return handle(res);
}
