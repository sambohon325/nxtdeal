// Sales' "Communications" item -- a real unified inbox aggregating the Communication
// Hub log (call/text/email/video FieldNotes, built for Prospects session 92) across
// every lead, plus the real follow-up cadence queue and marketing-compliance alerts
// (session 98 follow-up, backend: core/sales_menu.py's communications()).

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";
import type { CommunicationCategory } from "@/lib/leadRecord";

export type InboxItem = {
  id: string;
  category: CommunicationCategory;
  body: string;
  linked_entity_id: string | null;
  linked_entity_name: string | null;
  created_by: string;
  created_at: string;
};

export type FollowUpItem = {
  lead_id: string;
  current_state: string | null;
  days_in_state: number;
  name: string | null;
};

export type ComplianceAlert = {
  id: string;
  law?: string;
  citation?: string;
  description?: string;
  category?: string;
  [key: string]: unknown;
};

export type CommunicationsSummary = {
  unified_inbox: { total: number; by_channel: Record<string, number>; items: InboxItem[] };
  follow_up_cadence_queue: { count: number; items: FollowUpItem[] };
  compliance_logs: { count: number; alerts: ComplianceAlert[] };
  not_yet_tracked: Record<string, string>;
};

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

export async function getCommunicationsSummary(): Promise<CommunicationsSummary> {
  const params = new URLSearchParams({ department: "Sales", item_key: "communications" });
  const res = await fetch(`${API_BASE}/menu/data?${params.toString()}`, { headers: { ...authHeaders() } });
  return handle(res);
}
