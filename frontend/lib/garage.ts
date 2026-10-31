// My Garage client (App Suite Phase 4/7 data). PUBLIC, verify-token-scoped: a verified
// customer sees THEIR own vehicles/equity/service/messages. The token is the customer's
// NXTDeal Verify session_token, stored by CustomerVerifyGate under this same key. No auth
// header — the token is the credential (matches the /public/* convention).
import { API_BASE } from "@/lib/api";

export const GARAGE_TOKEN_KEY = "dealeros_garage_verify";

export function getGarageToken(): string | null {
  try {
    return localStorage.getItem(GARAGE_TOKEN_KEY);
  } catch {
    return null;
  }
}

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

export type GarageCustomer = { id: string; name: string };

export type GarageVehicle = Record<string, unknown> & { id?: string };

export type GarageEquity = {
  equity_amount: number | null;
  status: string;
  estimated_value: number | null;
  estimated_payoff: number | null;
  lease_maturing_soon: boolean | null;
  is_estimated: boolean;
  disclaimer: string | null;
};

export type GarageVehiclesView = {
  customer: GarageCustomer;
  vehicles: GarageVehicle[];
  vehicle_count: number;
  equity: GarageEquity;
  service_summary: { count: number; recent: Record<string, unknown>[] };
};

export type GarageServiceRecord = Record<string, unknown>;

export type GarageServiceView = {
  customer: GarageCustomer;
  count: number;
  records: GarageServiceRecord[];
  declined_services: GarageServiceRecord[];
};

export type GarageTimelineEvent = Record<string, unknown>;

export type GarageMessagesView = {
  customer: GarageCustomer;
  timeline: { entity_id?: string; event_count?: number; events: GarageTimelineEvent[] };
};

export type GarageApprovalItem = {
  ro_id: string;
  service_number: string;
  description: string | null;
  vehicle: string;
  estimate_amount: number | null;
  estimate_status: "pending" | "approved";
  paid: boolean;
  concerns: { description: string | null }[];
};

export type GarageApprovalsView = {
  customer: GarageCustomer;
  approvals: GarageApprovalItem[];
  count: number;
};

export type GarageStatusItem = {
  ro_id: string;
  service_number: string;
  description: string | null;
  vehicle: string;
  stage: string | null;
  workflow_checklist: { stage: string; status: "complete" | "current" | "pending" }[];
  technician: string | null;
  timeline: Record<string, unknown>[];
};

export type GarageStatusView = {
  customer: GarageCustomer;
  active_ros: GarageStatusItem[];
  count: number;
};

function get<T>(path: string): Promise<T> {
  const token = getGarageToken();
  return fetch(`${API_BASE}${path}${path.includes("?") ? "&" : "?"}token=${encodeURIComponent(token ?? "")}`).then(handle<T>);
}

function post<T>(path: string, body: Record<string, unknown>): Promise<T> {
  const token = getGarageToken();
  return fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token: token ?? "", ...body }),
  }).then(handle<T>);
}

export function getMyVehicles(): Promise<GarageVehiclesView> {
  return get<GarageVehiclesView>("/public/garage/vehicles");
}

export function getMyService(): Promise<GarageServiceView> {
  return get<GarageServiceView>("/public/garage/service");
}

export function getMyMessages(): Promise<GarageMessagesView> {
  return get<GarageMessagesView>("/public/garage/messages");
}

export function getMyApprovals(): Promise<GarageApprovalsView> {
  return get<GarageApprovalsView>("/public/garage/approvals");
}

export function respondToApproval(
  roId: string,
  approved: boolean,
  declineReason = "",
): Promise<{ ok: boolean; ro_id: string; approved: boolean }> {
  return post(`/public/garage/approvals/${encodeURIComponent(roId)}/respond`, {
    approved,
    decline_reason: declineReason,
  });
}

export function payMyRo(
  roId: string,
  method = "card",
): Promise<{ ok: boolean; ro_id: string; amount: number | null; mode: "live" | "simulated" }> {
  return post(`/public/garage/approvals/${encodeURIComponent(roId)}/pay`, { method });
}

export function getMyStatus(): Promise<GarageStatusView> {
  return get<GarageStatusView>("/public/garage/status");
}
