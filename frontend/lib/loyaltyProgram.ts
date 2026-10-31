import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type Configuration = {
  id?: string; version?: number; name: string; status: string; description?: string;
  locations?: string[]; starts_at?: string; ends_at?: string; terms_version?: string;
  enrollment_enabled?: boolean; earning_enabled?: boolean; redemption_enabled?: boolean;
  hold_hours?: number; trigger?: string; calculation?: string; points?: number;
  terms?: string; discount_cents?: number; point_cost?: number; department?: string; member_limit?: number; points_cap?: number;
};
export type PointsEntry = { id: string; customer_id: string; kind: string; points: number; reason: string; source: string; actor: string; created_at: string; reference?: string };
export type Hold = { id: string; status: string; points: number; appointment_id: string; location: string; expires_at: string; reward: Configuration };
export type ProgramMember = { customer_id: string; name: string; status: string; enrolled_at: string; terms_version: string; available: number; posted: number; reserved: number; pending: number; entries: PointsEntry[]; reservations: Hold[] };
export type ProgramWorkspace = {
  program: Configuration; active_program: Configuration; rules: Configuration[]; rewards: Configuration[]; campaigns: Configuration[];
  members: ProgramMember[]; available: number; reserved: number; totals: Record<string, number>;
  activity: PointsEntry[]; events: { id: string; status: string; error?: string; created_at: string }[];
  audit: { id: string; action: string; actor: string; created_at: string }[];
  updated_at: string; permissions: { manage: boolean; adjust: boolean; fulfill: boolean };
};

const pendingRequests = new Map<string, string>();
export async function loyaltyRequest<T>(path: string, body?: unknown): Promise<T> {
  // Preserve a mutation key after an ambiguous network failure. A retry of the
  // same action must not award/adjust points twice if the first response was lost.
  let fingerprint: string | undefined;
  if (body && typeof body === "object" && "request_key" in body) {
    const values = { ...body } as Record<string, unknown>;
    delete values.request_key;
    fingerprint = path + JSON.stringify(values);
    const key = pendingRequests.get(fingerprint) || String((body as { request_key: string }).request_key);
    pendingRequests.set(fingerprint, key);
    body = { ...values, request_key: key };
  }
  const response = await fetch(`${API_BASE}/loyalty/program/${path}`, {
    method: body === undefined ? "GET" : "POST", cache: "no-store",
    headers: { ...authHeaders(), "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await response.json();
  if (fingerprint && response.status < 500) pendingRequests.delete(fingerprint);
  if (!response.ok || data.error) {
    throw new Error(typeof data.detail === "string" ? data.detail : data.error || "Unable to complete this loyalty action.");
  }
  return data as T;
}

export const requestKey = () => crypto.randomUUID();
export const memberPath = (id: string) => `members/${encodeURIComponent(id)}`;
