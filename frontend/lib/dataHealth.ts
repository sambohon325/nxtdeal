// Readiness' "Data Health" Top Menu item, GREATLY EXPANDED -- Sam: "This is what
// the current screen appears focused on. I'd keep it but greatly expand it."
// Backend: core/data_health.py / _api.py. ADMIN/OPERATIONS-only, matching this
// item's own historical gate (core/data_connections_api.py's CONNECTION_ROLES).

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type ConnectionRecord = {
  id?: string;
  name?: string;
  connection_type?: string;
  department?: string;
  status?: string;
  last_synced_at?: string | null;
  last_test_at?: string | null;
  error_message?: string | null;
};

export type IntegrationMonitoring = {
  total_connections: number;
  by_sam_category: Record<string, ConnectionRecord[]>;
  by_connection_type: Record<string, number>;
  category_mapping_note: string;
  accounting_connections_note: string;
  accounting_connections_count: number;
};

export type FieldGap = {
  field: string;
  missing_count: number;
  total_count: number;
  missing_pct: number | null;
  sample_ids: string[];
};

export type DataCompleteness = {
  missing_vin_data: { vehicles: FieldGap; repair_orders: FieldGap; finance_contracts: FieldGap };
  missing_customer_data: { email: FieldGap; phone: FieldGap; first_name: FieldGap; last_name: FieldGap };
  missing_ro_data: { technician: FieldGap; description: FieldGap; service_date: FieldGap; customer_id: FieldGap };
  missing_contract_data: { apr: FieldGap; amount_financed: FieldGap; lender_name: FieldGap; term_months: FieldGap };
  note: string;
};

export type DuplicateGroup = {
  key: string;
  count: number;
  members: { id: string; label: string }[];
};

export type DataAccuracy = {
  duplicate_customers: {
    duplicate_groups_by_email: DuplicateGroup[];
    duplicate_groups_by_phone: DuplicateGroup[];
    total_customers_affected: number;
    note: string;
  };
  duplicate_vehicles: {
    duplicate_groups_by_vin: DuplicateGroup[];
    total_vehicles_affected: number;
    note: string;
  };
  pricing_discrepancies: {
    checked: boolean;
    count: number | null;
    note: string;
  };
  inventory_mismatches: {
    sold_without_purchase_relationship: number;
    discrepancies: Record<string, unknown>[];
    note: string;
    source: string;
  };
};

export type PendingBucket = { count: number | null; items?: unknown[]; error?: string };

export type DataFreshness = {
  last_sync: {
    connections: ConnectionRecord[];
    never_synced_count: number;
  };
  records_updated_last_24h: {
    since: string;
    by_entity_type: { deals: number; vehicles: number; repair_orders: number };
    total: number;
    not_yet_tracked: Record<string, string>;
  };
  pending_changes: {
    campaigns: PendingBucket;
    assets: PendingBucket;
    websites: PendingBucket;
    financing: PendingBucket;
  };
};

export type DataHealthOverview = {
  integration_monitoring: IntegrationMonitoring;
  data_completeness: DataCompleteness;
  data_accuracy: DataAccuracy;
  data_freshness: DataFreshness;
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

export function getDataHealthOverview(): Promise<DataHealthOverview> {
  return get("/data-health/overview");
}
