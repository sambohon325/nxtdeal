// Administration's "Vendors" item (Administration Control Center rebuild,
// continued). Backend: core/vendor_management.py / _api.py. Real Vendor
// entities -- name/category/contact info/monthly cost/contract dates/
// auto-renew/notes/status. ADMIN/OPERATIONS-only throughout.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type VendorCategory = "software" | "parts_supplier" | "service_provider" | "marketing" | "other";
export type VendorStatus = "active" | "inactive" | "under_review";

export type Vendor = {
  id: string;
  name: string;
  category: VendorCategory;
  status: VendorStatus;
  contact_name: string;
  contact_email: string;
  contact_phone: string;
  monthly_cost: number | null;
  contract_start_date: string | null;
  contract_end_date: string | null;
  auto_renew: boolean;
  notes: string;
  created_by: string;
  created_at: string;
  updated_at: string;
  updated_by?: string;
  days_to_renewal: number | null;
};

export type VendorDashboard = {
  total_vendors: number;
  active_vendors: number;
  total_monthly_cost: number;
  upcoming_renewals: Vendor[];
  by_category: Record<string, { count: number; monthly_cost: number }>;
  vendors: Vendor[];
  not_yet_tracked: Record<string, string>;
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

function post<T>(path: string, body?: unknown, method: "POST" | "PUT" = "POST"): Promise<T> {
  return fetch(`${API_BASE}${path}`, {
    method,
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: body ? JSON.stringify(body) : undefined,
  }).then(handle<T>);
}

export function getVendorDashboard(): Promise<VendorDashboard> {
  return get("/vendors/dashboard");
}

export function listVendors(opts?: { category?: string; status?: string }): Promise<{ vendors: Vendor[] }> {
  const params = new URLSearchParams();
  if (opts?.category) params.set("category", opts.category);
  if (opts?.status) params.set("status", opts.status);
  const qs = params.toString();
  return get(`/vendors${qs ? `?${qs}` : ""}`);
}

export function getVendor(vendorId: string): Promise<Vendor> {
  return get(`/vendors/${vendorId}`);
}

export function createVendor(fields: {
  name: string;
  category: VendorCategory;
  contact_name?: string;
  contact_email?: string;
  contact_phone?: string;
  monthly_cost?: number;
  contract_start_date?: string;
  contract_end_date?: string;
  auto_renew?: boolean;
  notes?: string;
}): Promise<Vendor> {
  return post("/vendors", fields);
}

export function updateVendor(vendorId: string, fields: Partial<Vendor>): Promise<Vendor> {
  return post(`/vendors/${vendorId}`, fields, "PUT");
}

export function setVendorStatus(vendorId: string, status: VendorStatus): Promise<Vendor> {
  return post(`/vendors/${vendorId}/status`, { status });
}
