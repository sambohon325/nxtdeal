// Prospects / Lead Record (backend: core/lead_record.py, core/lead_tasks.py,
// core/lead_conversion.py, core/field_notes.py -- session 92 follow-up). Sam's Sales
// sub-menu spec: "Customer Profile, Activity Timeline, Communication Hub (Call/Text/
// Email/Video, all logged automatically), Task Management, Customer Notes, Next Best
// Action."

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type CommunicationCategory = "call" | "text" | "email" | "video";
export type NoteCategory = "objection" | "family" | "competitor" | "payment_goal" | "general";

export type FieldNoteBrief = {
  id: string;
  category: string;
  body: string;
  created_by: string;
  created_at: string;
};

export type LeadTaskType = "call" | "send_pricing" | "schedule_appraisal" | "follow_up_after_demo" | "custom";

export type LeadTaskBrief = {
  id: string;
  task_type: LeadTaskType;
  description: string;
  due_at: string | null;
  completed: boolean;
  completed_at: string | null;
  assigned_to: string;
};

export type TimelineEntry = {
  type: string;
  summary: string;
  actor: string | null;
  timestamp: string | null;
  details: Record<string, unknown>;
};

export type NextBestAction = {
  action: string;
  reason: string;
  basis?: string;
};

export type LeadRecord = {
  lead: { id: string; entity_type: string; attributes: Record<string, unknown> };
  related_entities: Record<string, unknown>[];
  communications: FieldNoteBrief[];
  notes: FieldNoteBrief[];
  tasks: LeadTaskBrief[];
  open_task_count: number;
  overdue_task_count: number;
  timeline: TimelineEntry[];
  next_best_action: NextBestAction;
  not_yet_tracked: Record<string, string>;
};

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

export async function getLeadRecord(leadId: string): Promise<LeadRecord> {
  const res = await fetch(`${API_BASE}/leads/${encodeURIComponent(leadId)}/record`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function logLeadActivity(leadId: string, category: CommunicationCategory, body: string): Promise<FieldNoteBrief> {
  const res = await fetch(`${API_BASE}/leads/${encodeURIComponent(leadId)}/log`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ department: "Sales", category, body, linked_entity_id: leadId }),
  });
  return handle(res);
}

export async function addLeadNote(leadId: string, category: NoteCategory, body: string): Promise<FieldNoteBrief> {
  const res = await fetch(`${API_BASE}/leads/${encodeURIComponent(leadId)}/notes`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ department: "Sales", category, body, linked_entity_id: leadId }),
  });
  return handle(res);
}

export async function createLeadTask(leadId: string, input: { task_type: LeadTaskType; description?: string; due_at?: string | null; assigned_to?: string | null }): Promise<LeadTaskBrief> {
  const res = await fetch(`${API_BASE}/leads/${encodeURIComponent(leadId)}/tasks`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(input),
  });
  return handle(res);
}

export async function completeLeadTask(taskId: string): Promise<LeadTaskBrief> {
  const res = await fetch(`${API_BASE}/tasks/${encodeURIComponent(taskId)}/complete`, {
    method: "POST",
    headers: { ...authHeaders() },
  });
  return handle(res);
}

export async function convertLeadToCustomer(leadId: string): Promise<{ id: string; [key: string]: unknown }> {
  const res = await fetch(`${API_BASE}/leads/${encodeURIComponent(leadId)}/convert`, {
    method: "POST",
    headers: { ...authHeaders() },
  });
  return handle(res);
}

// --- Prospects summary + search ---

export type ProspectsSummary = {
  total_leads?: number;
  by_source_bucket?: Record<string, number>;
  lost_opportunities?: { count: number };
  unsold_showroom_traffic?: { count: number };
  needing_assignment?: { count: number };
  equity_customers?: unknown;
  not_yet_tracked?: Record<string, string>;
  [key: string]: unknown;
};

export async function getProspectsSummary(): Promise<ProspectsSummary> {
  const params = new URLSearchParams({ department: "Sales", item_key: "prospects" });
  const res = await fetch(`${API_BASE}/menu/data?${params.toString()}`, { headers: { ...authHeaders() } });
  return handle(res);
}

export type LeadSearchResult = { id: string; entity_type: string; attributes: Record<string, unknown> };

export async function searchLeads(query: string): Promise<LeadSearchResult[]> {
  if (!query.trim()) return [];
  const res = await fetch(`${API_BASE}/search?q=${encodeURIComponent(query)}`, { headers: { ...authHeaders() } });
  const results = await handle<LeadSearchResult[]>(res);
  return results.filter((r) => r.entity_type === "Lead").slice(0, 20);
}
