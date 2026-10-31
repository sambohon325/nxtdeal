import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type CrmFilters = { kind: "Lead" | "Customer"; q: string; owner: string; stage: string; source: string; overdue: boolean; sort: "name" | "newest" | "oldest" | "overdue" };
export type CrmRow = { id: string; kind: string; name: string; email: string; phone: string; owner_id: string; owner_name: string; stage: string; source: string; created_at: string | null; stage_since: string | null; last_contact: string | null; vin: string; vehicles: {id: string; label: string; vin: string}[]; open_tasks: number; overdue_tasks: number };
export type CrmRecords = { records: CrmRow[]; total: number; offset: number; stage_counts: Record<string,number>; states: string[]; transitions: Record<string,string[]>; owners: {id: string; name: string}[]; sources: string[]; intake_sources: string[]; observed_at: string };
export type CrmView = CrmFilters & { id: string; name: string; layout: "table" | "board" };
export const defaultFilters: CrmFilters = {kind: "Lead", q: "", owner: "", stage: "", source: "", overdue: false, sort: "newest"};
export async function crmRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {...init, headers: {"Content-Type": "application/json", ...authHeaders(), ...init?.headers}});
  const data = await response.json();
  if (!response.ok || data?.error) throw new Error(data?.detail || data?.error || "CRM request failed");
  return data;
}
export function fetchCrmRecords(filters: CrmFilters, offset: number) {
  return crmRequest<CrmRecords>(`/sales/crm/records?${new URLSearchParams({...filters, overdue: String(filters.overdue), offset: String(offset), limit: "50"})}`);
}
export const stageLabel = (value: string) => ({NEW:"New inquiry",CONTACTED:"Contacted",APPOINTMENT_SET:"Appointment set",VISITED:"Showroom visit",PROPOSAL:"Proposal",NEGOTIATION:"Negotiation",SOLD:"Sold",LOST:"Lost",UNTRACKED:"Untracked",CUSTOMER:"Customer"}[value] || value);
