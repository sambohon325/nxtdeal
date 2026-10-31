// core/customer_360.py's client (Marketing Growth Platform kickoff, 2026-07-17) --
// "One record. One timeline." A merged Customer 360 pulling Lead History/Vehicle
// Ownership/Trade Equity/Service History/Finance History/Communication (Email/SMS/
// Call/Video)/Chat/Event Attendance/Campaign Activity/Purchase History into one real
// chronological timeline. Routes live at /customer-360/*.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type TimelineEntry = {
  type: string;
  summary: string;
  timestamp: string;
  actor?: string;
  details?: Record<string, unknown>;
};

export type Customer360 = {
  customer: { id: string; entity_type: string; attributes: Record<string, unknown> };
  related_entities: unknown;
  lead_history: {
    origin_leads: { count: number; leads: { id: string; source: string; pipeline_state: string; created_at: string }[] };
    re_engagement_leads: { count: number; leads: { id: string; source: string; pipeline_state: string; created_at: string }[] };
  };
  purchase_history: { count: number; deals: { id: string; status: string; vehicle_id: string; funded_at: string | null }[] };
  vehicles_owned: { count: number; vehicles: { id: string; vin: string; year: string; make: string; model: string }[] };
  service_history: { count: number; records: { id: string; service_date: string; description: string; technician: string }[] };
  finance_contracts: { count: number; contracts: { id: string; contract_date: string; term_months: string; lender_id: string | null }[] };
  trade_equity: { count: number; basis: string; signals: { id: string; status: string; headline: string; vehicle_id: string | null; created_at: string }[] };
  communication_activity: { count: number; by_channel: Record<string, number>; recent: { id: string; category: string; body: string; created_by: string; created_at: string }[] };
  chat_activity: { count: number; sessions: { id: string; website_id: string; status: string; created_at: string }[]; not_yet_tracked: string };
  event_attendance: { count: number; rsvps: { id: string; event_id: string; status: string; attended: boolean; created_at: string }[] };
  campaign_activity: { count: number; campaigns: { id: string; name: string; campaign_type: string; channel: string; status: string; activated_at: string | null }[]; not_yet_tracked: string };
  credit_applications: {
    count: number;
    applications: { id: string; status: string; linked_deal_id: string | null; requested_amount: number | null; decision: string | null; score_band: string | null; estimated_apr: number | null; created_at: string }[];
  };
  trade_ins: {
    count: number;
    trades: { deal_id: string; deal_status: string | null; vin: string | null; year: string | number | null; make: string | null; model: string | null; acv: number | null; market_value_estimate: number | null; approved: boolean | null; appraised_by: string | null; appraised_at: string | null }[];
  };
  website_activity?: { visits: { purl_id: string; offer_type: string | null; visited_at: string }[]; count?: number };
  timeline: TimelineEntry[];
  not_yet_tracked: Record<string, string>;
  error?: string;
};

export async function getCustomer360(customerId: string): Promise<Customer360> {
  const res = await fetch(`${API_BASE}/customer-360/${encodeURIComponent(customerId)}`, {
    headers: { ...authHeaders() },
  });
  const data = await res.json();
  if (!res.ok || (data && typeof data === "object" && "error" in data && !("customer" in data))) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as Customer360;
}

export type CustomerSearchResult = { id: string; entity_type: string; name?: string };

