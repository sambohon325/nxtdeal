// Inventory department's "Acquisitions" item -- the buying center (Inventory
// rebuild, second slice). Backend: core/acquisitions.py / _api.py. A real
// AcquisitionRequest moves through Evaluate -> Price Risk -> Estimate Recon ->
// Review Market -> Approve, with a 2-step Purchase Approval chain (Inventory
// Manager -> GM/Admin). The Buy Recommendation Engine and Factory Allocations
// feed are SIMULATED per Sam's direct instruction (2026-07-17: "when a lack
// of data is a problem, lets simply make up simulated data to accommodate
// it") -- every simulated figure carries basis: "simulated_market_data" plus
// a disclaimer string, surfaced as-is in the UI rather than hidden.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type SourceType = "auction" | "trade" | "direct_purchase";
export type DirectPurchaseChannel = "we_buy_cars" | "web_lead" | "walk_in";
export type AcquisitionStage =
  | "evaluate" | "price_risk" | "estimate_recon" | "review_market" | "pending_approval"
  | "approved" | "rejected" | "purchased";

export type AcquisitionsCatalog = {
  source_types: SourceType[];
  direct_purchase_channels: DirectPurchaseChannel[];
  stages: AcquisitionStage[];
};

export type MarketSignal = {
  demand_level: "Low" | "Medium" | "High";
  avg_turn_rate_days: number;
  comparable_sales_count: number;
  basis: string;
  disclaimer: string;
};

export type BuyRecommendation = MarketSignal & {
  recommended_bid: { low: number; high: number; anchor_acv: number } | null;
};

export type ApprovalRecord = { approved_by: string; approved_at: string; notes: string };

export type MarketReview = {
  recommendation: BuyRecommendation;
  notes: string;
  reviewed_by: string;
  reviewed_at: string;
};

export type AcquisitionRequest = {
  id: string;
  source_type: SourceType;
  direct_purchase_channel: DirectPurchaseChannel | null;
  year: string | null;
  make: string | null;
  model: string | null;
  trim: string | null;
  mileage: string | null;
  vin: string | null;
  estimated_acv: number | string | null;
  stage: AcquisitionStage;
  requested_by: string;
  linked_deal_id: string | null;
  linked_auction_transaction_id: string | null;
  linked_vehicle_id: string | null;
  notes: string;
  price_risk_level: "low" | "medium" | "high" | null;
  price_risk_notes: string | null;
  recon_estimate: number | null;
  recon_notes: string | null;
  market_review: MarketReview | null;
  inventory_manager_approval: ApprovalRecord | null;
  gm_approval: ApprovalRecord | null;
  rejection_reason: string | null;
  rejected_by: string | null;
  rejected_at: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
  purchased_at: string | null;
};

export type AcquisitionsSummary = {
  total_requests: number;
  by_stage: Record<string, number>;
  by_source_type: Record<string, number>;
  pending_approval_count: number;
  awaiting_gm_signoff_count: number;
};

export type FactoryAllocation = {
  make: string;
  allocated_units: number;
  models: string[];
  allotment_month_offset: number;
  basis: string;
};

export type FactoryAllocations = { allocations: FactoryAllocation[]; disclaimer: string };

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

export function getAcquisitionsCatalog(): Promise<AcquisitionsCatalog> {
  return get("/acquisitions/catalog");
}

export function getAcquisitionsSummary(): Promise<AcquisitionsSummary> {
  return get("/acquisitions/summary");
}

export function getFactoryAllocations(): Promise<FactoryAllocations> {
  return get("/acquisitions/factory-allocations");
}

export function getBuyRecommendation(make: string, model: string, year: string, estimatedAcv?: number): Promise<BuyRecommendation> {
  const params = new URLSearchParams({ make, model, year });
  if (estimatedAcv !== undefined) params.set("estimated_acv", String(estimatedAcv));
  return get(`/acquisitions/buy-recommendation?${params.toString()}`);
}

export function listAcquisitionRequests(sourceType?: SourceType, stage?: AcquisitionStage): Promise<{ count: number; requests: AcquisitionRequest[] }> {
  const params = new URLSearchParams();
  if (sourceType) params.set("source_type", sourceType);
  if (stage) params.set("stage", stage);
  const qs = params.toString();
  return get(`/acquisitions${qs ? `?${qs}` : ""}`);
}

export function getAcquisitionRequest(id: string): Promise<AcquisitionRequest> {
  return get(`/acquisitions/${encodeURIComponent(id)}`);
}

export function createAcquisitionRequest(input: {
  source_type: SourceType;
  year?: string; make?: string; model?: string; trim?: string; mileage?: string; vin?: string;
  estimated_acv?: number;
  direct_purchase_channel?: DirectPurchaseChannel;
  linked_deal_id?: string;
  linked_auction_transaction_id?: string;
  notes?: string;
}): Promise<AcquisitionRequest> {
  return post("/acquisitions", input);
}

export function recordPriceRisk(id: string, riskLevel: "low" | "medium" | "high", notes = ""): Promise<AcquisitionRequest> {
  return post(`/acquisitions/${encodeURIComponent(id)}/price-risk`, { risk_level: riskLevel, notes });
}

export function recordReconEstimate(id: string, reconEstimate: number, notes = ""): Promise<AcquisitionRequest> {
  return post(`/acquisitions/${encodeURIComponent(id)}/recon-estimate`, { recon_estimate: reconEstimate, notes });
}

export function recordMarketReview(id: string, notes = ""): Promise<AcquisitionRequest> {
  return post(`/acquisitions/${encodeURIComponent(id)}/market-review`, { notes });
}

export function submitForApproval(id: string): Promise<AcquisitionRequest> {
  return post(`/acquisitions/${encodeURIComponent(id)}/submit-for-approval`, {});
}

export function approveByInventoryManager(id: string, notes = ""): Promise<AcquisitionRequest> {
  return post(`/acquisitions/${encodeURIComponent(id)}/approve/inventory-manager`, { notes });
}

export function approveByGm(id: string, notes = ""): Promise<AcquisitionRequest> {
  return post(`/acquisitions/${encodeURIComponent(id)}/approve/gm`, { notes });
}

export function rejectAcquisitionRequest(id: string, reason: string): Promise<AcquisitionRequest> {
  return post(`/acquisitions/${encodeURIComponent(id)}/reject`, { reason });
}

export function markPurchased(id: string, vehicleId?: string): Promise<AcquisitionRequest> {
  return post(`/acquisitions/${encodeURIComponent(id)}/mark-purchased`, { vehicle_id: vehicleId });
}
