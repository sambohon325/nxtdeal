// core/smart_audiences.py's client (Marketing Growth Platform kickoff, 2026-07-17) --
// the no-code Visual Segment Builder ("Vehicle = Truck AND Mileage > 75,000 AND
// Positive Equity") plus a preset library of named Smart Audiences (Truck Owners, No
// Service In N Months, Warranty Expiring, Lease Ending In N Days, Positive Equity,
// Subprime Customers, BHPH Customers, Potential Refinance Customers). Routes live at
// /smart-audiences/*.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type AudienceField = { key: string; label: string; type: string; entity: string };

export type AudiencePreset = { key: string; name: string; basis: string; params: { key: string; label: string; type: string; default: unknown }[] };

export type AudienceCondition = { field: string; operator: string; value: string | number };

export type AudienceMember = { id: string; name: string; email?: string | null; phone?: string | null };

export type SavedAudience = {
  id: string;
  name: string;
  description: string;
  preset_key: string | null;
  conditions: AudienceCondition[];
  created_by: string;
  created_at: string;
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

function post<T>(path: string, body?: unknown): Promise<T> {
  return fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  }).then(handle<T>);
}

function del<T>(path: string): Promise<T> {
  return fetch(`${API_BASE}${path}`, { method: "DELETE", headers: { ...authHeaders() } }).then(handle<T>);
}

export function getAudienceFields(): Promise<{ fields: AudienceField[]; operators: string[] }> {
  return get(`/smart-audiences/fields`);
}

export function listAudiencePresets(): Promise<{ presets: AudiencePreset[] }> {
  return get(`/smart-audiences/presets`);
}

export function previewAudiencePreset(presetKey: string, params: Record<string, unknown>): Promise<{ preset: string; name: string; basis: string; count: number; sample: AudienceMember[] }> {
  return post(`/smart-audiences/presets/${encodeURIComponent(presetKey)}/preview`, { params });
}

export function previewAudienceConditions(conditions: AudienceCondition[]): Promise<{ count: number; sample: AudienceMember[] }> {
  return post(`/smart-audiences/preview`, { conditions });
}

export function listSavedAudiences(): Promise<{ audiences: SavedAudience[] }> {
  return get(`/smart-audiences`);
}

export function createSmartAudience(input: { name: string; conditions?: AudienceCondition[]; preset_key?: string | null; preset_params?: Record<string, unknown>; description?: string }): Promise<SavedAudience> {
  return post(`/smart-audiences`, input);
}

export function deleteSmartAudience(audienceId: string): Promise<{ deleted: string }> {
  return del(`/smart-audiences/${encodeURIComponent(audienceId)}`);
}

export function evaluateSmartAudience(audienceId: string): Promise<{ audience: string; name: string; basis: string; count: number; members: AudienceMember[]; member_ids: string[] }> {
  return get(`/smart-audiences/${encodeURIComponent(audienceId)}/evaluate`);
}
