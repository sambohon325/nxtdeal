// Bumper-parity Bulk Import client (2026-07-25): analyze (parse + suggest column mapping),
// preview (non-destructive plan), commit. Talks to backend/core/bulk_import_api.py via the
// /imports/* routes.
import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

export type ImportTarget = { target_type: string; fields: string[] };

export type AnalyzeResult = {
  headers: string[];
  row_count: number;
  suggested_mapping: Record<string, string>;
  target_fields: string[];
  sample_rows: Record<string, string>[];
};

export type ImportVerdict = {
  index: number;
  status: "create" | "duplicate" | "error";
  errors?: string[];
  duplicate_of?: { match: string; on: string };
  record: Record<string, string>;
};

export type PreviewResult = {
  target_type: string;
  total: number;
  will_create: number;
  duplicates: number;
  errors: number;
  verdicts: ImportVerdict[];
};

export type CommitResult = {
  target_type: string;
  created: string[];
  created_count: number;
  skipped: { index: number; duplicate_of: { match: string; on: string } }[];
  skipped_count: number;
  errors: { index: number; errors: string[] }[];
  error_count: number;
};

export async function listImportTargets(): Promise<{ targets: ImportTarget[] }> {
  const res = await fetch(`${API_BASE}/imports/targets`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function analyzeCsv(csvText: string, targetType: string): Promise<AnalyzeResult> {
  const res = await fetch(`${API_BASE}/imports/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ csv_text: csvText, target_type: targetType }),
  });
  return handle(res);
}

export async function previewImport(
  csvText: string,
  mapping: Record<string, string>,
  targetType: string,
  dedupe = true
): Promise<PreviewResult> {
  const res = await fetch(`${API_BASE}/imports/preview`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ csv_text: csvText, mapping, target_type: targetType, dedupe }),
  });
  return handle(res);
}

export async function commitImport(
  csvText: string,
  mapping: Record<string, string>,
  targetType: string,
  dedupe = true
): Promise<CommitResult> {
  const res = await fetch(`${API_BASE}/imports/commit`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ csv_text: csvText, mapping, target_type: targetType, dedupe }),
  });
  return handle(res);
}
