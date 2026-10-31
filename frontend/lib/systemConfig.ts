// Administration's "Organizations" + "System Configuration" items
// (Administration Control Center rebuild, continued). Backend:
// core/system_config.py / _api.py -- one real singleton settings record
// (dealership profile, locations, business hours, defaults, feature flags).
// Viewing is open to any authenticated role; editing is ADMIN/OPERATIONS-only.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type Location = { name: string; address: string; is_primary: boolean };

export type BusinessHours = Record<string, string>;

export type FeatureFlags = Record<string, boolean>;

export type SystemConfig = {
  can_manage_system?: boolean;
  id: string;
  dealership_name: string;
  dba_name: string;
  ein: string;
  address_line1: string;
  address_line2: string;
  city: string;
  state: string;
  zip_code: string;
  phone: string;
  website_url: string;
  locations: Location[];
  business_hours: BusinessHours;
  default_currency: string;
  default_timezone: string;
  feature_flags: FeatureFlags;
  updated_by: string | null;
  updated_at: string;
};

export const FEATURE_FLAG_KEYS = ["ai_assistant_enabled", "compliance_scanning_enabled", "bot_coverage_enabled"] as const;

export const WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"] as const;

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

function post<T>(path: string, body?: unknown): Promise<T> {
  return fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: body ? JSON.stringify(body) : undefined,
  }).then(handle<T>);
}

export function getSystemConfig(): Promise<SystemConfig> {
  return get("/system-config");
}

export function updateOrganizationProfile(fields: Partial<SystemConfig>): Promise<SystemConfig> {
  return post("/system-config/organization-profile", fields);
}

export function addLocation(name: string, address: string, isPrimary = false): Promise<SystemConfig> {
  return post("/system-config/locations", { name, address, is_primary: isPrimary });
}

export function removeLocation(index: number): Promise<SystemConfig> {
  return post(`/system-config/locations/${index}/remove`);
}

export function updateBusinessHours(day: string, hours: string): Promise<SystemConfig> {
  return post("/system-config/business-hours", { day, hours });
}

export function updateDefaults(fields: { default_currency?: string; default_timezone?: string }): Promise<SystemConfig> {
  return post("/system-config/defaults", fields);
}

export function setFeatureFlag(flag: string, enabled: boolean): Promise<SystemConfig> {
  return post("/system-config/feature-flags", { flag, enabled });
}

// Performance Readiness's real Goal Tracking mechanism (Readiness reframe,
// item #4) -- a flat department -> monthly numeric target stored on this
// same SystemConfig singleton. Viewing open to any role, setting/clearing
// ADMIN/OPERATIONS-only (see core/system_config_api.py).

export const GOAL_TRACKED_DEPARTMENTS = ["sales", "service", "marketing"] as const;

export type DepartmentGoals = Record<string, number>;

export type DepartmentGoalsResponse = {
  goals: DepartmentGoals;
  tracked_departments: string[];
};

export function getDepartmentGoals(): Promise<DepartmentGoalsResponse> {
  return get("/system-config/department-goals");
}

export function setDepartmentGoal(department: string, monthlyTarget: number): Promise<SystemConfig> {
  return post("/system-config/department-goals", { department, monthly_target: monthlyTarget });
}

export function clearDepartmentGoal(department: string): Promise<SystemConfig> {
  return post(`/system-config/department-goals/${encodeURIComponent(department)}/clear`);
}
