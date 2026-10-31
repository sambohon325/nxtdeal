// lib/publicRetail.ts — PUBLIC (unauthenticated) client for the customer-facing Digital Retail
// backend: the /public/verify/* and /public/retail/* routes (backend core/dealeros_verify.py +
// core/digital_retail.py). These are token-driven — the verification session_token returned by
// /public/verify/start is the customer's only credential — so NO Authorization header is sent
// (unlike every staff lib/*.ts client). Used by the public site widgets (DigitalRetailFlow).

import { API_BASE } from "@/lib/api";

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (
    !response.ok ||
    (data && typeof data === "object" && "error" in data && (data as { error?: string }).error)
  ) {
    throw new Error((data && (data as { error?: string }).error) || "Something went wrong.");
  }
  return data as T;
}

function postPublic<T>(path: string, body: unknown): Promise<T> {
  return fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  }).then(handle<T>);
}

function getPublic<T>(path: string): Promise<T> {
  return fetch(`${API_BASE}${path}`, { headers: { "Content-Type": "application/json" } }).then(handle<T>);
}

// ---- Verify (the trust ladder) ----

export type VerifyTier = "anonymous" | "verified_human" | "identity_verified" | "credit_verified";

export type VerificationView = {
  id: string;
  tier: VerifyTier;
  tier_label: string;
  email: string | null;
  email_verified: boolean;
  phone: string | null;
  phone_verified: boolean;
  identity_verified: boolean;
  credit_verified: boolean;
  capabilities: string[];
  next_tier: { tier: string; label: string; needs: string[] } | null;
};

export type StartVerification = { verification: VerificationView; session_token: string };
export type CodeRequest = { channel: string; sent_to: string; expires_at: string; simulated: boolean; dev_code: string; disclaimer: string };

export function publicStartVerification(email?: string, phone?: string): Promise<StartVerification> {
  return postPublic("/public/verify/start", { email, phone });
}

export function publicGetVerification(token: string): Promise<VerificationView> {
  return getPublic(`/public/verify/${encodeURIComponent(token)}`);
}

export function publicRequestCode(token: string, channel: "email" | "sms"): Promise<CodeRequest> {
  return postPublic(`/public/verify/${encodeURIComponent(token)}/request-code`, { channel });
}

export function publicConfirmCode(token: string, channel: "email" | "sms", code: string): Promise<{ verification: VerificationView }> {
  return postPublic(`/public/verify/${encodeURIComponent(token)}/confirm-code`, { channel, code });
}

export function publicSetContact(token: string, email?: string, phone?: string): Promise<{ verification: VerificationView }> {
  return postPublic(`/public/verify/${encodeURIComponent(token)}/contact`, { email, phone });
}

export function publicSubmitIdentity(token: string, licenseNumber: string, selfieProvided = true): Promise<{ verification: VerificationView; disclaimer: string }> {
  return postPublic(`/public/verify/${encodeURIComponent(token)}/identity`, {
    license_number: licenseNumber,
    selfie_provided: selfieProvided,
  });
}

// ---- Retail (self-service deal) — used once a session is Identity Verified ----

export type RetailDeal = {
  id: string;
  status: string;
  vehicle_id: string;
  scenarios: Record<string, unknown>[];
  trade_in: Record<string, unknown> | null;
  financing_status: string | null;
};

export function publicStartDeal(token: string, vehicleId: string): Promise<{ deal: RetailDeal }> {
  return postPublic("/public/retail/deals", { token, vehicle_id: vehicleId });
}

export function publicGetDealRoom(token: string, dealId: string): Promise<Record<string, unknown>> {
  return getPublic(`/public/retail/deals/${encodeURIComponent(dealId)}?token=${encodeURIComponent(token)}`);
}
