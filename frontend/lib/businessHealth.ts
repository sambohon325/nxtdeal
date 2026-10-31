// Readiness' new "Business Health" Top Menu item -- the executive layer above
// every production department (Sales/Service/Finance/Marketing/Inventory), Sam's
// reframe of Readiness from "data confidence" to "is the dealership ready to
// achieve its goals, where are the risks." Backend: core/business_health.py /
// _api.py -- a pure composition layer reusing each department's own already-real
// KPI functions, never a new computation. Open to every real role.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type Basis = "real" | "heuristic" | "simulated_market_data" | "simulated_payment_status" | string;

export type LabeledValue = {
  value?: number | string | null;
  basis?: Basis;
  note?: string;
  [key: string]: unknown;
};

export type NotYetTracked = Record<string, string>;

export type SalesHealth = {
  lead_volume: LabeledValue;
  show_rate: LabeledValue & { appointments_scheduled?: number; appointments_shown?: number };
  close_rate: LabeledValue;
  gross_profit: LabeledValue;
  pipeline_coverage: {
    active_pipeline_count?: number | null;
    basis?: Basis;
    not_yet_tracked?: NotYetTracked;
  };
};

export type ServiceHealth = {
  ro_volume: { total?: number; open?: number; by_status?: Record<string, number>; basis?: Basis };
  technician_utilization: {
    avg_utilization_pct_today?: number;
    overloaded_technician_count?: number;
    technician_count?: number;
    basis?: Basis;
    note?: string;
  };
  customer_retention: {
    customers_with_service_history?: number;
    avg_visits_per_year?: number | null;
    lost_customers?: { count?: number };
    basis?: Basis;
  };
  shop_capacity: Record<string, unknown> & { basis?: Basis; note?: string };
};

export type FinanceHealth = {
  funding_time: { avg_days_in_transit?: number | null; contracts_in_transit?: number; basis?: Basis; note?: string };
  contract_accuracy: { not_yet_tracked?: NotYetTracked };
  collections: Record<string, unknown> & { error?: string };
  portfolio_quality: Record<string, unknown> & { error?: string };
};

export type MarketingHealth = {
  lead_volume: LabeledValue;
  roi: Record<string, unknown> & { error?: string };
  website_traffic: {
    total_page_views?: number;
    human_views?: number;
    bot_views?: number;
    site_count?: number;
    sites_with_recorded_traffic?: number;
    basis?: Basis;
    note?: string;
  };
  campaign_performance: Record<string, unknown> & { error?: string };
};

export type InventoryHealth = {
  turn_rate: Record<string, unknown> & { basis?: Basis; disclaimer?: string };
  aging: Record<string, unknown> & { basis?: Basis; disclaimer?: string };
  recon_time: {
    avg_checklist_completion_pct?: number | null;
    vehicles_fully_recon_complete?: number;
    vehicles_with_zero_recon_progress?: number;
    used_unsold_count?: number;
    basis?: Basis;
    note?: string;
  };
  days_supply: Record<string, unknown> & { basis?: Basis; disclaimer?: string };
};

export type BusinessHealthOverview = {
  sales: SalesHealth;
  service: ServiceHealth;
  finance: FinanceHealth;
  marketing: MarketingHealth;
  inventory: InventoryHealth;
  overall_score: number | null;
  overall_score_note: string;
  generated_at: string;
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

export function getBusinessHealthOverview(): Promise<BusinessHealthOverview> {
  return get("/business-health/overview");
}

export function getBusinessHealthDepartment(department: string): Promise<Record<string, unknown>> {
  return get(`/business-health/${encodeURIComponent(department)}`);
}
