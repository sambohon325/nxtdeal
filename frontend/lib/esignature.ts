// eSignature (session 104 follow-up) -- the sixth of Sam's ~10 "completely missing"
// dealership workflows: a real signing envelope against a snapshot of a Deal's
// generated contract, with a real ESIGN-Act-style consent gate per signer before
// they can sign. Backend: core/esignature.py / esignature_api.py.
//
// Honest scope note (see lib/esignature.ts's component / core/esignature.py for the
// full version): there is no live e-signature platform (DocuSign/HelloSign/Adobe
// Sign) connected in this sandbox. "Sending" is a state transition, not a real
// email/SMS dispatch, and "signing" is a typed-name capture, not a cryptographic
// signature or a verified IP/device fingerprint.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type EnvelopeStatus = "draft" | "sent" | "completed" | "declined" | "voided";
export type SignerStatus = "pending" | "signed" | "declined";
export type SignerRole = "customer" | "co_signer" | "dealer_rep";

export type Signer = {
  name: string;
  role: SignerRole;
  email: string | null;
  phone: string | null;
  esign_consent: boolean;
  esign_consent_at: string | null;
  status: SignerStatus;
  signed_at: string | null;
  typed_signature: string | null;
  decline_reason: string | null;
  verification_note?: string;
};

export type ContractSnapshot = {
  deal_id: string;
  customer_id: string;
  customer_name: string;
  vehicle_id: string;
  vehicle_description: string;
  vin: string | null;
  sale_price: number;
  trade_in_value: number | null;
  down_payment: number;
  amount_financed: number;
  apr: number;
  term_months: number;
  monthly_payment: number;
  financing_type: string | null;
  lender_name: string | null;
  generated_at: string;
  disclosures: string[];
};

export type CustomerBrief = { id: string; name: string };

export type SignatureRequest = {
  id: string;
  linked_deal_id: string;
  customer: CustomerBrief | null;
  contract_snapshot: ContractSnapshot;
  status: EnvelopeStatus;
  signers: Signer[];
  created_by: string;
  created_at: string;
  sent_at: string | null;
  completed_at: string | null;
  voided_at: string | null;
  updated_at: string;
};

export type EsignatureStats = {
  total: number;
  draft: number;
  sent: number;
  completed: number;
  declined: number;
  voided: number;
  completion_rate_pct: number | null;
};

export type EsignatureDashboard = {
  recent: SignatureRequest[];
  stats: EsignatureStats;
};

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

export async function getEsignatureDashboard(): Promise<EsignatureDashboard> {
  const res = await fetch(`${API_BASE}/esignature/dashboard`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function listSignatureRequests(params?: { linked_deal_id?: string; status?: EnvelopeStatus }): Promise<SignatureRequest[]> {
  const q = new URLSearchParams();
  if (params?.linked_deal_id) q.set("linked_deal_id", params.linked_deal_id);
  if (params?.status) q.set("status", params.status);
  const res = await fetch(`${API_BASE}/esignature?${q.toString()}`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function getSignatureRequest(requestId: string): Promise<SignatureRequest> {
  const res = await fetch(`${API_BASE}/esignature/${encodeURIComponent(requestId)}`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function createSignatureRequest(input: {
  linked_deal_id: string;
  signers: { name: string; role: SignerRole; email?: string; phone?: string }[];
}): Promise<SignatureRequest> {
  const res = await fetch(`${API_BASE}/esignature`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(input),
  });
  return handle(res);
}

export async function addSigner(
  requestId: string,
  input: { name: string; role: SignerRole; email?: string; phone?: string },
): Promise<SignatureRequest> {
  const res = await fetch(`${API_BASE}/esignature/${encodeURIComponent(requestId)}/signers`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(input),
  });
  return handle(res);
}

export async function removeSigner(requestId: string, signerIndex: number): Promise<SignatureRequest> {
  const res = await fetch(`${API_BASE}/esignature/${encodeURIComponent(requestId)}/signers/${signerIndex}/remove`, {
    method: "POST",
    headers: { ...authHeaders() },
  });
  return handle(res);
}

export async function sendSignatureRequest(requestId: string): Promise<SignatureRequest> {
  const res = await fetch(`${API_BASE}/esignature/${encodeURIComponent(requestId)}/send`, {
    method: "POST",
    headers: { ...authHeaders() },
  });
  return handle(res);
}

export async function captureSignerConsent(requestId: string, signerIndex: number): Promise<SignatureRequest> {
  const res = await fetch(`${API_BASE}/esignature/${encodeURIComponent(requestId)}/signers/${signerIndex}/consent`, {
    method: "POST",
    headers: { ...authHeaders() },
  });
  return handle(res);
}

export async function signEnvelope(requestId: string, signerIndex: number, typedSignature: string): Promise<SignatureRequest> {
  const res = await fetch(`${API_BASE}/esignature/${encodeURIComponent(requestId)}/signers/${signerIndex}/sign`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ typed_signature: typedSignature }),
  });
  return handle(res);
}

export async function declineSigner(requestId: string, signerIndex: number, reason: string): Promise<SignatureRequest> {
  const res = await fetch(`${API_BASE}/esignature/${encodeURIComponent(requestId)}/signers/${signerIndex}/decline`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ reason }),
  });
  return handle(res);
}

export async function voidSignatureRequest(requestId: string): Promise<SignatureRequest> {
  const res = await fetch(`${API_BASE}/esignature/${encodeURIComponent(requestId)}/void`, {
    method: "POST",
    headers: { ...authHeaders() },
  });
  return handle(res);
}
