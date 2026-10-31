// Sales' "Customers" item -- customer-centric search + a real grouped Customer 360
// (Purchase History, Service History, Finance Contracts, Vehicles Owned), plus
// Equity Mining and a Retention Center on the default view (session 95 follow-up,
// backend: core/sales_menu.py's customers(), reusing core/trigger_alerts.py's
// Timeline engine directly rather than a second signal-detection pass).

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";
import type { TriggerAlert } from "@/lib/events";

export type CustomerListItem = { id: string; name: string; email: string | null; phone: string | null };

export type CustomersSummary = {
  default_view: "recent_customers";
  customers: CustomerListItem[];
  equity_mining: { count: number; alerts: TriggerAlert[] };
  retention_center: { count: number; alerts: TriggerAlert[] };
};

export type Customer360 = {
  purchase_history: { count: number; deals: { id: string; status: string | null; vehicle_id: string | null; funded_at: string | null }[] };
  service_history: { count: number; records: { id: string; service_date: string | null; description: string | null; technician: string | null }[] };
  finance_contracts: { count: number; contracts: { id: string; contract_date: string | null; term_months: string | number | null; lender_id: string | null }[] };
  vehicles_owned: { count: number; vehicles: { id: string; vin: string | null; year: string | number | null; make: string | null; model: string | null }[] };
};

export type CustomerDetail = {
  customer: { id: string; entity_type: string; attributes: Record<string, unknown> };
  related_entities: Record<string, unknown>[];
  customer_360: Customer360;
};

export type CustomerSearchResults = { query: string; count: number; results: { id: string; entity_type: string; attributes: Record<string, unknown> }[] };

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

function menuData<T>(query?: string): Promise<T> {
  const params = new URLSearchParams({ department: "Sales", item_key: "customers" });
  if (query) params.set("query", query);
  return fetch(`${API_BASE}/menu/data?${params.toString()}`, { headers: { ...authHeaders() } }).then(handle<T>);
}

export function getCustomersSummary(): Promise<CustomersSummary> {
  return menuData<CustomersSummary>();
}

export function getCustomerDetail(custId: string): Promise<CustomerDetail> {
  return menuData<CustomerDetail>(custId);
}

export function searchCustomerRecords(query: string): Promise<CustomerSearchResults> {
  return menuData<CustomerSearchResults>(query);
}
