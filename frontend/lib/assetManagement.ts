// Finance's "Assets" item -- the sixth slice of Sam's Retail Automotive Lending
// Platform expansion (2026-07-17): Collateral / Asset Management. Real Title status
// (reusing the categorized Document vault), real Lien tracking (release gated on the
// loan being paid off), real dealer-entered Insurance/loss-payee tracking with a
// real lapsed-expiration check, and a Collateral Valuation & Loan-to-Value ratio
// blending the vehicle's real on-file Price with core/pricing_desk.py's SIMULATED
// current market value. Backend: core/asset_management.py / _api.py. Routes live at
// /collateral/*, NOT /assets/*, to avoid colliding with Marketing's own Asset
// (creative/marketing collateral) workflow.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type LienStatus = "active" | "released";

export type TitleStatus = {
  entity_id: string;
  entity_type: string;
  required_types: string[];
  documents: unknown[];
  missing_types: string[];
  is_complete: boolean;
};

export type LienInfo = {
  loan_id: string;
  lien_status: LienStatus;
  lienholder_name: string;
  lien_released_at: string | null;
  lien_released_by: string | null;
  is_stored_value: boolean;
};

export type InsuranceInfo = {
  loan_id: string;
  on_file: boolean;
  note?: string;
  carrier?: string;
  policy_number?: string;
  expiration_date?: string;
  loss_payee_confirmed?: boolean;
  is_lapsed?: boolean;
  updated_by?: string;
  updated_at?: string;
};

// NXTDeal VIN Intelligence, Phase 2 -- core/vin_decoder.py's
// check_vehicle_vin_match(), reused in-process (no separate route) by
// core/asset_management.py's get_collateral_valuation(). Read-only: never
// writes anything back to the Vehicle.
export type VinMatchMismatch = {
  field: "Year" | "Make";
  stored: string;
  decoded: string;
  basis: string | null;
};

export type VinMatchResult =
  | { vehicle_id: string; checked: false; note: string }
  | {
      vehicle_id: string;
      checked: true;
      vin: string;
      valid_format: boolean;
      format_error: string | null;
      check_digit_valid: boolean | null;
      compared_something: boolean;
      mismatches: VinMatchMismatch[];
      match: boolean;
      note: string | null;
      gap_note: string;
    };

export type CollateralValuation = {
  loan_id: string;
  vehicle_id: string;
  book_value: number | null;
  book_value_basis: string;
  market_value: number | null;
  market_value_basis: string | null;
  current_balance: number | null;
  current_balance_basis: string | null;
  loan_to_value_pct: number | null;
  vin_match: VinMatchResult | null;
  note: string;
};

export type AssetSummary = {
  loan_id: string;
  title: TitleStatus;
  lien: LienInfo;
  insurance: InsuranceInfo;
  valuation: CollateralValuation;
};

export type AssetPortfolioDashboard = {
  total_loans: number;
  total_book_value: number;
  total_market_value: number;
  total_market_value_basis: string;
  total_outstanding_balance: number;
  average_loan_to_value_pct: number | null;
  missing_title_count: number;
  lapsed_insurance_count: number;
  no_insurance_on_file_count: number;
  active_lien_count: number;
  released_lien_count: number;
  note: string;
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

export function getAssetPortfolioDashboard(): Promise<AssetPortfolioDashboard> {
  return get(`/collateral/dashboard`);
}

export function getAssetSummary(loanId: string): Promise<AssetSummary> {
  return get(`/collateral/${encodeURIComponent(loanId)}`);
}

export function getLienStatus(loanId: string): Promise<LienInfo> {
  return get(`/collateral/${encodeURIComponent(loanId)}/lien`);
}

export function updateLienholder(loanId: string, lienholderName: string): Promise<LienInfo> {
  return post(`/collateral/${encodeURIComponent(loanId)}/lien/lienholder`, { lienholder_name: lienholderName });
}

export function releaseLien(loanId: string, reason = ""): Promise<LienInfo> {
  return post(`/collateral/${encodeURIComponent(loanId)}/lien/release`, { reason });
}

export function getInsuranceStatus(loanId: string): Promise<InsuranceInfo> {
  return get(`/collateral/${encodeURIComponent(loanId)}/insurance`);
}

export function updateInsurance(loanId: string, carrier: string, policyNumber: string, expirationDate: string, lossPayeeConfirmed: boolean): Promise<InsuranceInfo> {
  return post(`/collateral/${encodeURIComponent(loanId)}/insurance`, {
    carrier,
    policy_number: policyNumber,
    expiration_date: expirationDate,
    loss_payee_confirmed: lossPayeeConfirmed,
  });
}

export function getCollateralValuation(loanId: string): Promise<CollateralValuation> {
  return get(`/collateral/${encodeURIComponent(loanId)}/valuation`);
}
