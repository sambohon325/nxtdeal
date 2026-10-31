// DMS Deal Desk (backend: session 33, core/deals.py/deals_api.py). Routes were
// imported into api/app.py since session 33 but never had an @app.get/@app.post
// decorator wired to them -- fixed in the session-91 follow-up alongside this client,
// as part of building the Sales "Deals" submenu (Sam's Sales sub-menu spec,
// 2026-07-16): Pipeline board, Deal Worksheet, Trade Appraisal, Desking/Financing.
//
// A Deal tracks one vehicle sale: desking -> financing -> contract -> funded
// (or cancelled from desking/financing). See core/deals.py's module docstring for the
// full state machine.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type DealStatus = "desking" | "financing" | "contract" | "funded" | "cancelled";
export type FinancingStatus = "not_started" | "submitted" | "approved" | "declined" | "countered";
export type FinancingType = "in_house" | "outside_lender" | null;

export type DealScenario = {
  id: string;
  label: string;
  sale_price: number;
  down_payment: number;
  term_months: number;
  amount_financed: number;
  estimated_apr: number;
  estimated_monthly_payment: number;
};

export type TradeInAppraisal = {
  vin?: string | null;
  year?: number | string | null;
  make?: string | null;
  model?: string | null;
  trim?: string | null;
  mileage?: number | null;
  condition?: string | null;
  photos?: string[];
  recon_estimate?: number | null;
  acv?: number | null;
  market_value_estimate?: number | null;
  notes?: string | null;
  appraised_by?: string | null;
  appraised_at?: string | null;
  approved?: boolean;
  approved_by?: string | null;
  approved_at?: string | null;
};

// NXTDeal VIN Intelligence, Phase 2 -- core/deals.py's decode_trade_in_vin(),
// read-only decision support comparing a trade-in's entered VIN against its
// entered year/make. Never writes anything back to the deal -- if a real
// mismatch is found, the appraiser corrects it themselves via
// updateTradeAppraisal() above.
export type TradeInVinMismatch = {
  field: "year" | "make";
  entered: string;
  decoded: string;
  basis: string | null;
};

export type TradeInVinDecodeResult = {
  deal_id: string;
  vin: string;
  valid_format: boolean;
  format_error: string | null;
  check_digit_valid: boolean | null;
  decoded: Record<string, unknown>;
  mismatches: TradeInVinMismatch[];
  gap_note: string;
  note: string;
};

export type CustomerBrief = {
  id: string;
  name: string;
  email: string | null;
  phone: string | null;
  credit_score?: number | string | null;
};

export type VehicleBrief = {
  id: string;
  description: string;
  vin: string | null;
  trim: string | null;
  price: number | null;
  cost: number | null;
  gross: number | null;
};

export type FinancingTerms = {
  apr: number;
  term_months: number;
  amount_financed: number;
  down_payment: number;
  monthly_payment: number;
} | null;

export type DealContract = {
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
  financing_type: FinancingType;
  lender_name: string | null;
  generated_at: string;
  disclosures: string[];
} | null;

export type Deal = {
  id: string;
  customer_id: string;
  vehicle_id: string;
  trade_in: TradeInAppraisal | null;
  delivery_checklist?: DeliveryChecklist;
  status: DealStatus;
  scenarios: DealScenario[];
  selected_scenario_id: string | null;
  financing_type: FinancingType;
  lender_id: string | null;
  financing_status: FinancingStatus;
  financing_terms: FinancingTerms;
  financing_notes?: string | null;
  contract: DealContract;
  finance_contract_id: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
  funded_at: string | null;
  customer?: CustomerBrief | null;
  vehicle?: VehicleBrief | null;
};

export type Lender = { id: string; name: string };

export type DeliveryChecklistSection = "vehicle_prep" | "quality_control" | "tech_setup" | "documentation" | "csi";

export type DeliveryChecklist = Partial<Record<DeliveryChecklistSection, Record<string, unknown>>>;

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

export async function listLenders(): Promise<Lender[]> {
  const res = await fetch(`${API_BASE}/deals/lenders`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function createDeal(input: { customer_id: string; vehicle_id: string; trade_in?: Record<string, unknown> | null }): Promise<Deal> {
  const res = await fetch(`${API_BASE}/deals`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(input),
  });
  return handle(res);
}

export async function listAllDeals(status?: DealStatus): Promise<Deal[]> {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  const res = await fetch(`${API_BASE}/deals?${params.toString()}`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function listMyDeals(): Promise<Deal[]> {
  const res = await fetch(`${API_BASE}/deals/mine`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function listPendingFinancing(): Promise<Deal[]> {
  const res = await fetch(`${API_BASE}/deals/pending-financing`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function getDeal(dealId: string): Promise<Deal> {
  const res = await fetch(`${API_BASE}/deals/${encodeURIComponent(dealId)}`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function addScenario(dealId: string, input: { label?: string; sale_price: number; down_payment?: number; term_months?: number }): Promise<Deal> {
  const res = await fetch(`${API_BASE}/deals/${encodeURIComponent(dealId)}/scenarios`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(input),
  });
  return handle(res);
}

export async function removeScenario(dealId: string, scenarioId: string): Promise<Deal> {
  const res = await fetch(`${API_BASE}/deals/${encodeURIComponent(dealId)}/scenarios/${encodeURIComponent(scenarioId)}`, {
    method: "DELETE",
    headers: { ...authHeaders() },
  });
  return handle(res);
}

export async function selectScenario(dealId: string, scenarioId: string): Promise<Deal> {
  const res = await fetch(`${API_BASE}/deals/${encodeURIComponent(dealId)}/scenarios/${encodeURIComponent(scenarioId)}/select`, {
    method: "POST",
    headers: { ...authHeaders() },
  });
  return handle(res);
}

export async function updateTradeAppraisal(dealId: string, patch: Partial<TradeInAppraisal>): Promise<Deal> {
  const res = await fetch(`${API_BASE}/deals/${encodeURIComponent(dealId)}/trade-appraisal`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ patch }),
  });
  return handle(res);
}

export async function approveTradeAppraisal(dealId: string): Promise<Deal> {
  const res = await fetch(`${API_BASE}/deals/${encodeURIComponent(dealId)}/trade-appraisal/approve`, {
    method: "POST",
    headers: { ...authHeaders() },
  });
  return handle(res);
}

export async function decodeTradeInVin(dealId: string): Promise<TradeInVinDecodeResult> {
  const res = await fetch(`${API_BASE}/deals/${encodeURIComponent(dealId)}/trade-in/decode-vin`, {
    headers: { ...authHeaders() },
  });
  return handle(res);
}

export async function updateDeliveryChecklist(dealId: string, section: DeliveryChecklistSection, patch: Record<string, unknown>): Promise<Deal> {
  const res = await fetch(`${API_BASE}/deals/${encodeURIComponent(dealId)}/delivery-checklist`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ section, patch }),
  });
  return handle(res);
}

export async function chooseInHouseFinancing(dealId: string): Promise<Deal> {
  const res = await fetch(`${API_BASE}/deals/${encodeURIComponent(dealId)}/financing/in-house`, {
    method: "POST",
    headers: { ...authHeaders() },
  });
  return handle(res);
}

export async function submitToLender(dealId: string, lenderId: string): Promise<Deal> {
  const res = await fetch(`${API_BASE}/deals/${encodeURIComponent(dealId)}/financing/submit`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ lender_id: lenderId }),
  });
  return handle(res);
}

export async function recordLenderDecision(
  dealId: string,
  decision: "approved" | "declined" | "countered",
  countered_terms?: Record<string, unknown> | null,
  notes?: string | null
): Promise<Deal> {
  const res = await fetch(`${API_BASE}/deals/${encodeURIComponent(dealId)}/financing/decision`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ decision, countered_terms: countered_terms || null, notes: notes || null }),
  });
  return handle(res);
}

export async function acceptCounteredTerms(dealId: string): Promise<Deal> {
  const res = await fetch(`${API_BASE}/deals/${encodeURIComponent(dealId)}/financing/accept-countered`, {
    method: "POST",
    headers: { ...authHeaders() },
  });
  return handle(res);
}

export async function generateContract(dealId: string): Promise<Deal> {
  const res = await fetch(`${API_BASE}/deals/${encodeURIComponent(dealId)}/contract`, {
    method: "POST",
    headers: { ...authHeaders() },
  });
  return handle(res);
}

export async function fundDeal(dealId: string): Promise<Deal> {
  const res = await fetch(`${API_BASE}/deals/${encodeURIComponent(dealId)}/fund`, {
    method: "POST",
    headers: { ...authHeaders() },
  });
  return handle(res);
}

export async function cancelDeal(dealId: string): Promise<Deal> {
  const res = await fetch(`${API_BASE}/deals/${encodeURIComponent(dealId)}/cancel`, {
    method: "POST",
    headers: { ...authHeaders() },
  });
  return handle(res);
}

// --- Customer search (generic graph search, filtered client-side to Customer records) ---

export type CustomerSearchResult = { id: string; entity_type: string; attributes: Record<string, unknown> };

export async function searchCustomers(query: string): Promise<CustomerBrief[]> {
  if (!query.trim()) return [];
  const res = await fetch(`${API_BASE}/search?q=${encodeURIComponent(query)}`, { headers: { ...authHeaders() } });
  const results = await handle<CustomerSearchResult[]>(res);
  return results
    .filter((r) => r.entity_type === "Customer")
    .slice(0, 20)
    .map((r) => ({
      id: r.id,
      name: `${r.attributes.FirstName || ""} ${r.attributes.LastName || ""}`.trim() || r.id,
      email: (r.attributes.Email as string) || null,
      phone: (r.attributes.Phone as string) || null,
      credit_score: (r.attributes.CreditScore as number) ?? null,
    }));
}
