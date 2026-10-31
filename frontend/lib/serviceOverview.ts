// Service's "Overview" item, second slice of Service's rebuild (session 111
// follow-up). Backend: core/service_overview.py / _api.py, GET /service/my-day
// (same "My Day" composition pattern as lib/salesOverview.ts). Command Center
// + Today's Risks only render for a manager-tier caller (is_manager_view) --
// same convention SalesOverviewBoard.tsx already established.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";
import type { RoBrief } from "@/lib/repairOrders";

export type RoBucket = { count: number; repair_orders: RoBrief[]; note?: string };

export type CommandCenter = {
  open_ros: RoBucket;
  returned_unfinished?: RoBucket;
  waiting_approval: RoBucket;
  waiting_parts: RoBucket;
  waiting_technician: RoBucket;
  waiting_delivery: RoBucket;
  comebacks: RoBucket;
  note: string;
};

export type TodaysRisks = {
  customers_waiting: RoBucket;
  jobs_behind_schedule: RoBucket & { note: string };
  techs_overloaded: { count: number; technicians: { technician_id: string; hours_booked_today: number; assumed_capacity_hours: number }[]; note: string };
  parts_delayed: RoBucket;
  promised_today_not_started: { count: null; not_yet_tracked: string };
};

export type AdvisorDashboard = {
  advisor: { id: string; name: string | null };
  my_appointments: { today_count: number; this_week_count: number };
  my_waiting_customers: RoBucket;
  my_returned_unfinished?: RoBucket;
  my_pending_approvals: RoBucket;
  my_vehicles_ready: RoBucket;
};

export type ServiceMyDay = {
  advisor_dashboard: AdvisorDashboard;
  is_manager_view: boolean;
  command_center?: CommandCenter;
  todays_risks?: TodaysRisks;
};

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

export async function getServiceMyDay(): Promise<ServiceMyDay> {
  const res = await fetch(`${API_BASE}/service/my-day`, { headers: { ...authHeaders() } });
  return handle(res);
}
