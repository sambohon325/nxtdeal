import {API_BASE} from "@/lib/api";
import {authHeaders} from "@/lib/auth";

export async function request(path: string, body?: unknown) {
  const response = await fetch(`${API_BASE}/dealer-bridge${path}`, {method: body === undefined ? "GET" : "POST", headers: {...authHeaders(), "Content-Type": "application/json"}, ...(body === undefined ? {} : {body: JSON.stringify(body)})});
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Request failed. Check the input and your administrator session.");
  return data;
}
export type Profile = {id: string; id_source: string; status: string; hash: string; proposed_by: string; approved_by?: string; fields: Record<string, {source: string; transform: string}>};
export type ValueConflict = {field: string; canonical_value: string; legacy_value: string};
export type EventRow = {row_number: number; status: string; external_id?: string; source_namespace?: string; occurred_at?: string; values?: Record<string, string>; error_code?: string; effect?: string; candidate_signature?: string; candidates?: string[]; candidate_records?: {id: string; values: Record<string, string>; legacy_conflicts?: ValueConflict[]}[]; identity_review_id?: string};
