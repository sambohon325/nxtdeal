// Sales Overview -- My Tasks Widget, Action Center, Daily Sales Dashboard, Sales
// Manager Dashboard (backend: core/sales_overview.py, session 94 follow-up). Renders
// ABOVE the existing generic Overview KPI board, not in place of it -- see
// components/SalesOverviewBoard.tsx.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";
import type { TurnOver, ToStats } from "@/lib/managerTo";

export type ActionItem = {
  id: string;
  name: string;
  phone: string | null;
  email: string | null;
  source: string | null;
  pipeline_state: string | null;
  last_contact: string | null;
  overdue_task_count: number;
  available_actions: string[];
};

export type MyTasks = {
  leads_requiring_contact_today: { count: number; items: ActionItem[] };
  missing_follow_ups: { count: number; items: ActionItem[] };
  unsold_showroom_visits: { count: number; items: ActionItem[] };
  action_center: { count: number; items: ActionItem[] };
  not_yet_tracked: Record<string, string>;
};

export type DailyDashboard = {
  todays_leads: { count: number };
  todays_shows: { count: number };
  write_ups_today: { count: number };
  deliveries_today: { count: number };
  not_yet_tracked: Record<string, string>;
};

export type ManagerDashboard = {
  unworked_leads: { count: number };
  overdue_follow_ups: { count: number };
  deals_stuck_in_fi: { count: number; deals: { id: string; customer_id: string | null; vehicle_id: string | null; financing_type: string | null; lender_id: string | null; financing_status: string | null }[] };
  trades_awaiting_appraisal: { count: number; deals: { id: string; customer_id: string | null; vehicle_id: string | null }[] };
  open_to_requests: { count: number; requests: TurnOver[]; stats: ToStats };
  not_yet_tracked: Record<string, string>;
};

export type MyDay = {
  my_tasks: MyTasks;
  daily_dashboard: DailyDashboard;
  is_manager_view: boolean;
  manager_dashboard?: ManagerDashboard;
};

export type SalesEmployeeBrief = { id: string; name: string; title: string | null };

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

export async function getMyDay(): Promise<MyDay> {
  const res = await fetch(`${API_BASE}/sales/my-day`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function getSalesEmployees(): Promise<SalesEmployeeBrief[]> {
  const res = await fetch(`${API_BASE}/sales/employees`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function transferLead(leadId: string, newEmployeeId: string): Promise<{ lead_id: string; transferred_from: string; transferred_to: string }> {
  const res = await fetch(`${API_BASE}/leads/${encodeURIComponent(leadId)}/transfer`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ new_employee_id: newEmployeeId }),
  });
  return handle(res);
}
