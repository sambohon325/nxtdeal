// Administration's "Data Management" item (Administration Control Center
// rebuild, continued). Backend: core/data_backup.py / _api.py -- real
// per-entity-type CSV export and a real graph.json backup/restore action.
// ADMIN/OPERATIONS for everything except restore, which is ADMIN-only (the
// single most consequential real action in this whole rebuild -- overwrites
// the live graph.json and reloads it in-process).

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type DataBackup = {
  id: string;
  filename: string;
  path: string;
  size_bytes: number;
  label: string;
  created_by: string;
  created_at: string;
  restored_at: string | null;
  restored_by: string | null;
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

function post<T>(path: string, body?: unknown): Promise<T> {
  return fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: body ? JSON.stringify(body) : undefined,
  }).then(handle<T>);
}

export function getExportableTypes(): Promise<{ entity_types: Record<string, number> }> {
  return get("/data-management/exportable-types");
}

// The export route requires a real Authorization header, which a plain
// `<a href download>` can't attach -- fetch as a blob and trigger the
// download client-side instead. No prior precedent for a file download
// exists anywhere else in this codebase (checked before writing this), so
// this is a fresh, minimal pattern rather than a copy of an established one.
export async function downloadEntityTypeExport(entityType: string): Promise<void> {
  const response = await fetch(`${API_BASE}/data-management/export/${entityType}`, {
    headers: { ...authHeaders() },
  });

  const contentType = response.headers.get("content-type") || "";

  if (!response.ok || contentType.includes("application/json")) {
    const data = await response.json().catch(() => null);
    throw new Error((data && (data as { error?: string }).error) || "Unable to export this entity type.");
  }

  const blob = await response.blob();
  const disposition = response.headers.get("content-disposition") || "";
  const match = disposition.match(/filename="?([^"]+)"?/);
  const filename = match ? match[1] : `${entityType}_export.csv`;

  const url = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.URL.revokeObjectURL(url);
}

export function createBackup(label = ""): Promise<DataBackup> {
  return post("/data-management/backups", { label });
}

export function listBackups(): Promise<{ backups: DataBackup[] }> {
  return get("/data-management/backups");
}

export function restoreBackup(backupId: string): Promise<DataBackup | { warning: string }> {
  return post(`/data-management/backups/${backupId}/restore`);
}
