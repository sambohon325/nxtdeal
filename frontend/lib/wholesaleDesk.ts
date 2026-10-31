// Inventory department's "Wholesale" item -- the disposition center
// (Inventory rebuild, seventh slice). Backend: core/wholesale_desk.py /
// _api.py. Open Offers, Sold Wholesale Units, and Fund Collection are all
// REAL features (internal tracking capabilities nobody had built), same
// call Lot Management/Merchandising made for their own internal gaps.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type OfferStatus = "pending" | "accepted" | "rejected" | "countered" | "withdrawn";

export type WholesaleDeskCatalog = { offer_statuses: OfferStatus[] };

export type WholesaleOffer = {
  id: string;
  vehicle_id: string;
  buyer_name: string;
  offer_amount: number;
  status: OfferStatus;
  notes: string;
  submitted_by: string;
  submitted_at: string;
  decided_by: string | null;
  decided_at: string | null;
  counter_amount: number | null;
};

export type VehicleBrief = {
  vehicle_id: string;
  vin: string | null;
  stock_number: string | null;
  year: string | null;
  make: string | null;
  model: string | null;
  price: number | null;
  cost: number | null;
};

export type FundsCollected = { amount: number; method: string; notes: string; collected_by: string; collected_at: string };

export type WholesaleSale = {
  buyer_name: string;
  sale_price: number;
  sold_by: string;
  sold_at: string;
  offer_id: string | null;
  notes: string;
  funds_collected: FundsCollected | null;
};

export type SoldWholesaleEntry = VehicleBrief & { wholesale_sale: WholesaleSale };

export type SoldWholesaleUnits = { count: number; vehicles: SoldWholesaleEntry[] };

export type FundCollectionStatus = {
  awaiting_collection: { count: number; total_amount: number; vehicles: SoldWholesaleEntry[] };
  collected: { count: number; total_amount: number; vehicles: SoldWholesaleEntry[] };
};

export type WholesaleDeskSummary = {
  open_offers: { count: number; offers: WholesaleOffer[] };
  sold_wholesale_units: SoldWholesaleUnits;
  fund_collection: FundCollectionStatus;
};

export type WholesaleCandidate = {
  vehicle_id: string;
  vin: string | null;
  stock_number: string | null;
  year: string | null;
  make: string | null;
  model: string | null;
  lot: string | null;
  price: number | null;
  cost: number | null;
  margin: number | null;
  margin_pct: number | null;
};

export type WholesaleCandidatesResponse = {
  wholesale_candidates: { count: number; candidates: WholesaleCandidate[] };
  auction_queue: { count: number; candidates: WholesaleCandidate[] };
  title_status: {
    candidates_with_title_on_file: number;
    candidates_missing_title: number;
    missing_title_vehicle_ids: string[];
  };
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

export function getWholesaleDeskCatalog(): Promise<WholesaleDeskCatalog> {
  return get("/wholesale-desk/catalog");
}

export function getWholesaleCandidates(): Promise<WholesaleCandidatesResponse> {
  const params = new URLSearchParams({ department: "Inventory", item_key: "wholesale" });
  return fetch(`${API_BASE}/menu/data?${params.toString()}`, { headers: { ...authHeaders() } }).then(handle<WholesaleCandidatesResponse>);
}

export function getWholesaleDeskSummary(): Promise<WholesaleDeskSummary> {
  return get("/wholesale-desk/summary");
}

export function listOffers(vehicleId?: string, status?: OfferStatus): Promise<{ count: number; offers: WholesaleOffer[] }> {
  const params = new URLSearchParams();
  if (vehicleId) params.set("vehicle_id", vehicleId);
  if (status) params.set("status", status);
  const qs = params.toString();
  return get(`/wholesale-desk/offers${qs ? `?${qs}` : ""}`);
}

export function submitOffer(vehicleId: string, buyerName: string, offerAmount: number, notes = ""): Promise<WholesaleOffer> {
  return post(`/wholesale-desk/offers/${encodeURIComponent(vehicleId)}`, { buyer_name: buyerName, offer_amount: offerAmount, notes });
}

export function acceptOffer(offerId: string): Promise<WholesaleOffer> {
  return post(`/wholesale-desk/offers/${encodeURIComponent(offerId)}/accept`, {});
}

export function rejectOffer(offerId: string, notes = ""): Promise<WholesaleOffer> {
  return post(`/wholesale-desk/offers/${encodeURIComponent(offerId)}/reject`, { notes });
}

export function counterOffer(offerId: string, counterAmount: number): Promise<WholesaleOffer> {
  return post(`/wholesale-desk/offers/${encodeURIComponent(offerId)}/counter`, { counter_amount: counterAmount });
}

export function withdrawOffer(offerId: string): Promise<WholesaleOffer> {
  return post(`/wholesale-desk/offers/${encodeURIComponent(offerId)}/withdraw`, {});
}

export function getSoldWholesaleUnits(limit = 50): Promise<SoldWholesaleUnits> {
  return get(`/wholesale-desk/sold?limit=${limit}`);
}

export function markWholesaleSold(vehicleId: string, buyerName: string, salePrice: number, offerId?: string, notes = ""): Promise<{ vehicle_id: string; wholesale_sale: WholesaleSale }> {
  return post(`/wholesale-desk/sold/${encodeURIComponent(vehicleId)}`, { buyer_name: buyerName, sale_price: salePrice, offer_id: offerId, notes });
}

export function getFundCollectionStatus(): Promise<FundCollectionStatus> {
  return get("/wholesale-desk/funds");
}

export function recordFundsCollected(vehicleId: string, amount: number, method = "", notes = ""): Promise<{ vehicle_id: string; wholesale_sale: WholesaleSale }> {
  return post(`/wholesale-desk/funds/${encodeURIComponent(vehicleId)}`, { amount, method, notes });
}
