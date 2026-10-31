// Customer-Facing Approval Center -- the second of Sam's "completely
// missing" Service features. A real, unguessable shareable link per RO
// estimate that lets the customer approve/decline it themselves, with no
// staff member recording the decision on their behalf. Staff-side actions
// (generate/view status/revoke) are authenticated, ACL-gated calls, same as
// every other RO Workflow Engine action. The public view/decision calls are
// genuinely unauthenticated -- no authHeaders() at all, matching the
// /public/websites/* convention lib/websites.ts already established.
// Backend: core/approval_center.py / _api.py.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type ApprovalLinkStatus = {
  ro_id: string;
  exists: boolean;
  token?: string;
  created_by?: string;
  created_at?: string;
  revoked?: boolean;
  revoked_by?: string;
  revoked_at?: string;
  path?: string;
};

export type PublicApprovalConcern = { description: string };

export type PublicApprovalFinding = {
  category: string;
  item: string;
  status: "yellow" | "red";
  notes: string;
};

export type PublicApprovalEstimate = {
  amount: number | null;
  sent_at: string | null;
  approved: boolean | null;
  decided_at: string | null;
  decline_reason: string | null;
  decided_by_customer: boolean;
};

export type PublicApprovalView = {
  revoked: boolean;
  service_number: string;
  description: string;
  customer_name: string | null;
  vehicle: string | null;
  open_concerns: PublicApprovalConcern[];
  flagged_inspection_findings: PublicApprovalFinding[];
  estimate: PublicApprovalEstimate;
};

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

// ---- Staff-side (authenticated) ----

export async function generateApprovalLink(roId: string): Promise<ApprovalLinkStatus> {
  const res = await fetch(`${API_BASE}/repair-orders/${encodeURIComponent(roId)}/approval-link`, {
    method: "POST",
    headers: { ...authHeaders() },
  });
  return handle(res);
}

export async function getApprovalLinkStatus(roId: string): Promise<ApprovalLinkStatus> {
  const res = await fetch(`${API_BASE}/repair-orders/${encodeURIComponent(roId)}/approval-link`, {
    headers: { ...authHeaders() },
  });
  return handle(res);
}

export async function revokeApprovalLink(roId: string): Promise<{ ro_id: string; revoked: boolean }> {
  const res = await fetch(`${API_BASE}/repair-orders/${encodeURIComponent(roId)}/approval-link/revoke`, {
    method: "POST",
    headers: { ...authHeaders() },
  });
  return handle(res);
}

// ---- Public (unauthenticated) ----

export async function publicGetApprovalView(token: string): Promise<PublicApprovalView> {
  const res = await fetch(`${API_BASE}/public/approve/${encodeURIComponent(token)}`);
  return handle(res);
}

export async function publicRecordApprovalDecision(
  token: string,
  approved: boolean,
  declineReason?: string
): Promise<PublicApprovalView> {
  const res = await fetch(`${API_BASE}/public/approve/${encodeURIComponent(token)}/decision`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ approved, decline_reason: declineReason ?? "" }),
  });
  return handle(res);
}
