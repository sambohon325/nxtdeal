// Service department's "Customers" item, fourth slice of Service's rebuild --
// Sam's framing: "Service should be relationship-driven." Customer 360
// (Vehicles Owned/Service History/Warranty/Recall/Declined Services),
// Retention metrics, Lost Customer Recovery, and Declined Services. Backend:
// core/service_customers.py / _api.py.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type VehicleBrief = {
  id: string;
  vin: string;
  year: string;
  make: string;
  model: string;
  warranty_status: { status: string; condition: string | null; note: string };
  recall_status: { open_recalls: { id: string; recall_number: string; description: string; campaign_type: string }[]; count: number };
};

export type ServiceHistoryRecord = {
  id: string;
  service_date: string | null;
  description: string | null;
  cost: string | number | null;
  pay_type: string | null;
  ro_stage: string;
};

export type DeclinedServiceRecord = {
  ro_id: string;
  description: string | null;
  amount: number | null;
  decline_reason: string | null;
  declined_at: string | null;
};

export type RetentionMetrics = {
  last_visit: string | null;
  first_visit: string | null;
  visit_count: number;
  average_spend: number | null;
  visits_per_year: number | null;
};

export type CustomerServiceProfile = {
  customer: { id: string; name: string; email: string | null; phone: string | null };
  vehicles_owned: { count: number; vehicles: VehicleBrief[] };
  service_history: { count: number; records: ServiceHistoryRecord[] };
  declined_services: { count: number; records: DeclinedServiceRecord[] };
  retention: RetentionMetrics;
};

export type LostCustomer = {
  customer_id: string;
  name: string;
  phone: string | null;
  last_visit: string;
  days_since_last_visit: number;
  total_visits: number;
};

export type LostCustomerRecovery = {
  count: number;
  customers: LostCustomer[];
  not_yet_tracked: Record<string, string>;
};

export type DeclinedServiceEntry = {
  ro_id: string;
  customer_id: string | null;
  customer_name: string | null;
  vehicle: string | null;
  description: string | null;
  amount: number | null;
  decline_reason: string | null;
  days_since_declined: number | null;
};

export type DeclinedServices = {
  count: number;
  total_value: number;
  records: DeclinedServiceEntry[];
};

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

export async function getCustomer360(customerId: string): Promise<CustomerServiceProfile> {
  const res = await fetch(`${API_BASE}/service-customers/${encodeURIComponent(customerId)}`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function getRetentionMetrics(customerId: string): Promise<RetentionMetrics> {
  const res = await fetch(`${API_BASE}/service-customers/${encodeURIComponent(customerId)}/retention`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function getLostCustomerRecovery(): Promise<LostCustomerRecovery> {
  const res = await fetch(`${API_BASE}/service-customers/lost-customer-recovery`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function getDeclinedServices(): Promise<DeclinedServices> {
  const res = await fetch(`${API_BASE}/service-customers/declined-services`, { headers: { ...authHeaders() } });
  return handle(res);
}
