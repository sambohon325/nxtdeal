// Marketing's "PURLs" item -- the Personalized URL Platform (Marketing Growth
// Platform, session 113 follow-up). Backend: core/purls.py / _api.py. Staff
// generate/list/revoke/mail-piece/analytics calls are authenticated; the
// visitor-facing offer/visit/submit calls are genuinely public (no auth header).

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type OfferType = "current_vehicle" | "trade_equity" | "inventory_matches" | "payment_reduction" | "general";
export type PurlStatus = "active" | "revoked";

export const OFFER_TYPES: OfferType[] = ["current_vehicle", "trade_equity", "inventory_matches", "payment_reduction", "general"];

export type MailPiece = {
  piece_name: string;
  piece_type: string;
  mail_date: string | null;
  created_by: string;
  created_at: string;
};

export type Purl = {
  id: string;
  token: string;
  customer_id: string | null;
  lead_id: string | null;
  offer_type: OfferType;
  status: PurlStatus;
  created_by: string;
  created_at: string;
  visit_count: number;
  first_visited_at: string | null;
  last_visited_at: string | null;
  generated_lead_id: string | null;
  mail_piece: MailPiece | null;
};

export type PurlList = { count: number; purls: Purl[] };

export type PurlDashboard = {
  kpis: {
    total_purls: number;
    active_purls: number;
    total_visits: number;
    leads_generated: number;
    conversion_rate: number;
  };
  recent_purls: Purl[];
};

export type PurlAnalytics = {
  purl_id: string;
  visits: number;
  first_visited_at: string | null;
  last_visited_at: string | null;
  lead_generated: boolean;
  lead_id: string | null;
  correlated_since_creation: {
    basis: string;
    disclaimer: string;
    appointments_count: number;
    funded_deals_count: number;
    revenue: number;
  };
};

export type PersonBrief = { id: string; type: "customer" | "lead"; name: string; email: string | null; phone: string | null };

export type VehicleBrief = {
  id: string;
  vin: string | null;
  year: string | number | null;
  make: string | null;
  model: string | null;
  trim?: string | null;
  price?: string | number | null;
  on_hold?: boolean;
};

export type TradeEquityOffer =
  | { eligible: false; reason: string }
  | { eligible: true; basis: string; disclaimer: string; pct_term_elapsed: number; amount_financed: string | number; vin: string | null };

export type PaymentReductionOffer =
  | { eligible: false; reason: string }
  | {
      eligible: true;
      basis: string;
      disclaimer: string;
      current_monthly_payment: number;
      estimated_new_monthly_payment: number;
      estimated_savings: number;
      estimated_apr: number;
      matched_vehicle: VehicleBrief;
    };

export type PersonalizedOffer = {
  error?: string;
  revoked: boolean;
  person: PersonBrief;
  offer_type: OfferType;
  current_vehicles: { id: string; vin: string | null; year: string | number | null; make: string | null; model: string | null }[];
  trade_equity: TradeEquityOffer;
  inventory_matches: VehicleBrief[];
  payment_reduction: PaymentReductionOffer;
  already_submitted: boolean;
  generated_lead_id: string | null;
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

function post<T>(path: string, body: unknown): Promise<T> {
  return fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(body),
  }).then(handle<T>);
}

function publicGet<T>(path: string): Promise<T> {
  return fetch(`${API_BASE}${path}`).then(handle<T>);
}

function publicPost<T>(path: string, body: unknown): Promise<T> {
  return fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then(handle<T>);
}

// ---- Staff (authenticated) ----

export function generatePurl(offerType: OfferType, customerId?: string, leadId?: string, notes?: string): Promise<{ purl: Purl; public_path: string }> {
  return post(`/purls`, { offer_type: offerType, customer_id: customerId ?? null, lead_id: leadId ?? null, notes: notes ?? null });
}

export function listPurls(createdBy?: string, status?: PurlStatus): Promise<PurlList> {
  const params = new URLSearchParams();
  if (createdBy) params.set("created_by", createdBy);
  if (status) params.set("status", status);
  return get(`/purls?${params.toString()}`);
}

export function getPurlDashboard(createdBy?: string): Promise<PurlDashboard> {
  const params = new URLSearchParams();
  if (createdBy) params.set("created_by", createdBy);
  return get(`/purls/dashboard?${params.toString()}`);
}

export function revokePurl(purlId: string): Promise<{ purl: Purl }> {
  return post(`/purls/${encodeURIComponent(purlId)}/revoke`, {});
}

export function createMailPiece(purlId: string, pieceName: string, pieceType: string, mailDate?: string): Promise<{ purl: Purl }> {
  return post(`/purls/${encodeURIComponent(purlId)}/mail-piece`, { piece_name: pieceName, piece_type: pieceType, mail_date: mailDate ?? null });
}

export function getPurlAnalytics(purlId: string): Promise<PurlAnalytics> {
  return get(`/purls/${encodeURIComponent(purlId)}/analytics`);
}

export type BulkSourceType = "marketing_list" | "smart_audience";

export type BulkGenerateResult = {
  source_type: BulkSourceType;
  source_id: string;
  source_name: string | null;
  requested: number;
  created_count: number;
  skipped_count: number;
  created: Purl[];
  skipped: { id: string; reason: string }[];
};

export function bulkGeneratePurls(
  sourceType: BulkSourceType,
  sourceId: string,
  offerType: OfferType,
  notes?: string
): Promise<BulkGenerateResult> {
  return post(`/purls/bulk-generate`, { source_type: sourceType, source_id: sourceId, offer_type: offerType, notes: notes ?? null });
}

// ---- Public (unauthenticated) ----

export function publicGetPurlOffer(token: string): Promise<PersonalizedOffer> {
  return publicGet(`/public/purl/${encodeURIComponent(token)}`);
}

export function publicRecordPurlVisit(token: string, userAgent?: string): Promise<{ visit_count: number; visited_at: string }> {
  return publicPost(`/public/purl/${encodeURIComponent(token)}/visit`, { user_agent: userAgent ?? null });
}

export function publicSubmitPurlLead(token: string, notes?: string): Promise<{ lead_id: string; assigned_to: string }> {
  return publicPost(`/public/purl/${encodeURIComponent(token)}/submit`, { notes: notes ?? null });
}
