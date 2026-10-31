// Readiness' "Scenarios" item (Simulations Top Menu key) -- item #6 of Sam's
// 10-item proposed structure, "one of NXTDeal' most powerful features": real
// What-If Modeling. Backend: core/readiness_scenarios.py / _api.py -- every
// projection is a transparent formula over this dealership's own real
// current-data ratios (real close rate, real avg gross per sale, real
// per-technician revenue, real observed portfolio yield/delinquency rate),
// never an invented multiplier. See that module's own docstring for the full
// per-scenario real-basis trace. Viewing/running is open to every real role;
// the Finance Portfolio scenario's underlying data stays gated at its own,
// narrower ADMIN/OPERATIONS/FINANCE layer and degrades gracefully.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type ScenarioInputField = {
  key: string;
  label: string;
  type: "int" | "float" | "string";
  required: boolean;
  default?: number;
  options?: string[];
};

export type ScenarioTypeDef = {
  key: string;
  label: string;
  description: string;
  inputs: ScenarioInputField[];
  note?: string;
};

export type ScenarioCatalog = {
  scenario_types: ScenarioTypeDef[];
};

export type MarketingLeadVolumeResult = {
  scenario_type: "marketing_lead_volume";
  input_path: "direct_lead_volume" | "assumed_spend_to_lead";
  inputs: { additional_leads: number | null; additional_ad_spend: number | null };
  assumption_used: { assumed_cost_per_lead: number; note: string } | null;
  real_ratios_used: {
    close_rate_pct: number | null;
    close_rate_basis: string;
    funded_deals_count: number;
    gross_profit_funded_deals_total: number;
    avg_gross_per_sale: number | null;
    avg_gross_per_sale_basis: string;
  };
  projection: {
    additional_leads: number;
    projected_additional_sales: number | null;
    projected_additional_gross_profit: number | null;
    formula: string;
  };
};

export type InventoryPricingResult = {
  scenario_type: "inventory_pricing";
  inputs: { price_reduction_amount: number; price_band: string };
  real_ratios_used: {
    vehicles_evaluated: number;
    margin_floor_basis: string;
    price_band_basis: string;
  };
  not_yet_tracked: Record<string, string>;
  projection: {
    vehicles_evaluated: number;
    vehicles_would_shift_band: number;
    vehicles_blocked_by_margin_floor: number;
    vehicles_unknown_cost: number;
    total_margin_dollars_given_up: number;
    band_distribution_before: Record<string, number>;
    band_distribution_after: Record<string, number>;
    formula: string;
  };
};

export type StaffingResult = {
  scenario_type: "staffing";
  inputs: { additional_technicians: number };
  real_ratios_used: {
    current_technician_count: number;
    current_technician_count_basis: string;
    total_revenue_all_time: number;
    total_revenue_basis: string;
    months_of_data: number;
    months_of_data_basis: string;
    avg_revenue_per_technician_all_time: number | null;
    avg_monthly_revenue_per_technician: number | null;
  };
  projection: {
    capacity_increase_pct: number | null;
    projected_monthly_labor_increase: number | null;
    formula: string;
  };
};

export type FinancePortfolioResult = {
  scenario_type: "finance_portfolio";
  inputs: { portfolio_growth_pct: number };
  error?: string;
  note?: string;
  real_ratios_used?: {
    current_total_outstanding_balance: number;
    current_total_outstanding_basis: string;
    current_total_loans: number;
    current_delinquency_rate_pct: number | null;
    current_delinquency_rate_basis: string;
    interest_income_recognized: number;
    interest_income_basis: string;
    observed_yield_pct: number | null;
    observed_yield_basis: string;
  };
  collections_context?: Record<string, unknown>;
  projection?: {
    projected_additional_outstanding_balance: number;
    projected_additional_interest_income: number | null;
    projected_additional_loans: number;
    projected_additional_delinquent_loans: number | null;
    formula: string;
  };
};

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data && Object.keys(data).length === 1)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

function get<T>(path: string): Promise<T> {
  return fetch(`${API_BASE}${path}`, { headers: { ...authHeaders() } }).then(handle<T>);
}

function post<T>(path: string, body?: unknown): Promise<T> {
  return fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: body ? JSON.stringify(body) : undefined,
  }).then(handle<T>);
}

export function getScenarioCatalog(): Promise<ScenarioCatalog> {
  return get("/readiness-scenarios/catalog");
}

export function runMarketingLeadVolumeScenario(input: {
  additional_leads?: number | null;
  additional_ad_spend?: number | null;
  assumed_cost_per_lead?: number | null;
}): Promise<MarketingLeadVolumeResult> {
  return post("/readiness-scenarios/marketing-lead-volume", input);
}

export function runInventoryPricingScenario(input: {
  price_reduction_amount: number;
  price_band?: string | null;
}): Promise<InventoryPricingResult> {
  return post("/readiness-scenarios/inventory-pricing", input);
}

export function runStaffingScenario(input: { additional_technicians: number }): Promise<StaffingResult> {
  return post("/readiness-scenarios/staffing", input);
}

export function runFinancePortfolioScenario(input: { portfolio_growth_pct: number }): Promise<FinancePortfolioResult> {
  return post("/readiness-scenarios/finance-portfolio", input);
}
