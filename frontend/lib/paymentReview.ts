import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type PaymentReview = {
  read_only: true;
  reconciled: false;
  scanned_payments: number;
  flagged_payments: number;
  flagged_approved_receipt_total: string;
  notice: string;
  offset: number;
  limit: number;
  has_more: boolean;
  records: {
    payment_id: string;
    loan_id: string | null;
    amount: string | null;
    approved: boolean;
    posted: boolean;
    reasons: string[];
  }[];
};

export async function getPaymentReview(offset: number, signal?: AbortSignal): Promise<PaymentReview> {
  const response = await fetch(`${API_BASE}/compliance/payment-review?offset=${offset}&limit=25`, {
    headers: authHeaders(), cache: "no-store", signal,
  }).catch(error => {
    if (error instanceof TypeError) throw new Error("Unable to connect to payment review. Check your connection and try again.");
    throw error;
  });
  const data = await response.json();
  if (!response.ok || data?.error) throw new Error(data?.error || "Unable to load payment review.");
  if (data?.read_only !== true || data?.reconciled !== false || !Array.isArray(data?.records)) {
    throw new Error("Payment review is unavailable on this server.");
  }
  return data;
}

export const paymentReviewReasons: Record<string, string> = {
  simulated_payment: "Simulated payment result",
  legacy_cash_provenance: "Older cash receipt needs supporting evidence",
  unreviewed_payment_basis: "Payment source needs review",
  inconsistent_cash_provenance: "Cash receipt source does not match its label",
  missing_finance_contract: "Linked loan is missing",
  invalid_amount: "Amount is missing or invalid",
  unreviewed_payment_status: "Payment status needs review",
};
