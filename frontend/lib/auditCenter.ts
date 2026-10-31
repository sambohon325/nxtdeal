// Administration's "Audit Center" item (Administration Control Center
// rebuild, final slice). Backend: core/audit_center.py / _api.py -- a real
// investigative workspace over the audit log every ~20+ modules across this
// codebase already write to (core/audit.py's `audit_log` singleton),
// distinct from the thin slices "Security"/"Systems"/"Governance" already
// surface: real filtering/search, a real per-actor activity summary, and a
// real, transparent RULES-based suspicious-activity flag list. No ML/AI
// anomaly detection anywhere in this module or its backend.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type AuditEvent = {
  id: string;
  event_type: string;
  category: string;
  entity_id: string | null;
  actor: string;
  summary: string;
  details: Record<string, unknown>;
  timestamp: string;
};

export type EventCatalog = {
  categories: Record<string, string[]>;
  total_event_types: number;
};

export type SearchResult = {
  total_matches: number;
  returned: number;
  events: AuditEvent[];
};

export type ActorBucket = {
  actor: string;
  total: number;
  by_event_type: Record<string, number>;
  first_seen: string;
  last_seen: string;
};

export type ActorActivity = {
  total_actors: number;
  actors: ActorBucket[];
};

export type ActorTimeline = {
  actor: string;
  total_events: number;
  events: AuditEvent[];
};

export type SuspiciousFlag = {
  flag_type: string;
  severity: "high" | "medium" | "low";
  entity_id: string | null;
  basis: string;
  detail: string;
};

export type SuspiciousActivity = {
  total_flags: number;
  by_severity: Record<string, number>;
  flags: SuspiciousFlag[];
  not_yet_tracked: Record<string, string>;
};

export type AuditCenterOverview = {
  total_events: number;
  by_type: Record<string, number>;
  recent: AuditEvent[];
  event_catalog: EventCatalog;
  top_actors: ActorActivity;
  suspicious_activity_summary: { total_flags: number; by_severity: Record<string, number> };
};

export type SearchFilters = {
  entityId?: string;
  actor?: string;
  eventType?: string;
  category?: string;
  dateFrom?: string;
  dateTo?: string;
  query?: string;
  limit?: number;
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

function buildQuery(filters?: SearchFilters): string {
  if (!filters) return "";
  const params = new URLSearchParams();
  if (filters.entityId) params.set("entity_id", filters.entityId);
  if (filters.actor) params.set("actor", filters.actor);
  if (filters.eventType) params.set("event_type", filters.eventType);
  if (filters.category) params.set("category", filters.category);
  if (filters.dateFrom) params.set("date_from", filters.dateFrom);
  if (filters.dateTo) params.set("date_to", filters.dateTo);
  if (filters.query) params.set("query", filters.query);
  if (filters.limit) params.set("limit", String(filters.limit));
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

export function getAuditCenterOverview(): Promise<AuditCenterOverview> {
  return get("/audit-center/overview");
}

export function getEventCatalog(): Promise<EventCatalog> {
  return get("/audit-center/event-catalog");
}

export function searchAuditLog(filters?: SearchFilters): Promise<SearchResult> {
  return get(`/audit-center/search${buildQuery(filters)}`);
}

export function getActorActivity(limit = 50): Promise<ActorActivity> {
  return get(`/audit-center/actor-activity?limit=${limit}`);
}

export function getActorTimeline(actor: string, limit = 100): Promise<ActorTimeline> {
  return get(`/audit-center/actors/${encodeURIComponent(actor)}?limit=${limit}`);
}

export function getSuspiciousActivity(offHoursLookbackDays = 7): Promise<SuspiciousActivity> {
  return get(`/audit-center/suspicious-activity?off_hours_lookback_days=${offHoursLookbackDays}`);
}

// Same blob-download pattern lib/dataManagement.ts's downloadEntityTypeExport()
// already established -- the export route requires a real Authorization header,
// which a plain `<a href download>` can't attach.
export async function downloadAuditExport(filters?: SearchFilters): Promise<void> {
  const response = await fetch(`${API_BASE}/audit-center/export${buildQuery(filters)}`, {
    headers: { ...authHeaders() },
  });

  const contentType = response.headers.get("content-type") || "";

  if (!response.ok || contentType.includes("application/json")) {
    const data = await response.json().catch(() => null);
    throw new Error((data && (data as { error?: string }).error) || "Unable to export audit events.");
  }

  const blob = await response.blob();
  const disposition = response.headers.get("content-disposition") || "";
  const match = disposition.match(/filename="?([^"]+)"?/);
  const filename = match ? match[1] : "audit_log_export.csv";

  const url = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.URL.revokeObjectURL(url);
}
