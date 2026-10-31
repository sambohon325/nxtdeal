// Operations' "Documents" item (session 106 follow-up #6) -- Deal Jacket
// Workflow, Title Processing workflow, Compliance Packets, Digital
// Approvals. Backend: core/document_workflows.py / _api.py.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type DocEntityType = "Deal" | "Vehicle" | "Customer";
export type ApprovalStatus = "pending" | "approved" | "rejected";

export type DocumentBrief = {
  id: string;
  document_type: string;
  file_name: string | null;
  uploaded_by: string | null;
  created_at: string | null;
  approval_status: ApprovalStatus;
};

export type CompletenessCheck = {
  entity_id: string;
  entity_type: DocEntityType;
  required_types: string[];
  documents: DocumentBrief[];
  missing_types: string[];
  is_complete: boolean;
};

export type PendingApprovals = {
  count: number;
  documents: DocumentBrief[];
};

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

export async function getDealJacketStatus(dealId: string): Promise<CompletenessCheck> {
  const res = await fetch(`${API_BASE}/document-workflows/deal-jacket/${encodeURIComponent(dealId)}`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function getTitleStatus(vehicleId: string): Promise<CompletenessCheck> {
  const res = await fetch(`${API_BASE}/document-workflows/title/${encodeURIComponent(vehicleId)}`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function getDocumentPacket(entityType: DocEntityType, entityId: string): Promise<CompletenessCheck> {
  const res = await fetch(`${API_BASE}/document-workflows/packet/${encodeURIComponent(entityType)}/${encodeURIComponent(entityId)}`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function requestDocument(entityType: DocEntityType, entityId: string, documentType: string, notes = ""): Promise<{ id: string }> {
  const res = await fetch(`${API_BASE}/document-workflows/request`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ entity_type: entityType, entity_id: entityId, document_type: documentType, notes }),
  });
  return handle(res);
}

export async function getPendingApprovals(): Promise<PendingApprovals> {
  const res = await fetch(`${API_BASE}/document-workflows/pending-approvals`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function approveDocument(documentId: string, notes = ""): Promise<DocumentBrief> {
  const res = await fetch(`${API_BASE}/document-workflows/${encodeURIComponent(documentId)}/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ notes }),
  });
  return handle(res);
}

export async function rejectDocument(documentId: string, reason: string): Promise<DocumentBrief> {
  const res = await fetch(`${API_BASE}/document-workflows/${encodeURIComponent(documentId)}/reject`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ reason }),
  });
  return handle(res);
}
