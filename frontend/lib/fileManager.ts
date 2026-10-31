// Bumper-parity File Manager / DAM client (2026-07-25). Talks to
// backend/api/routers/content_library.py (/files/*).
import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

export type MediaType = "image" | "video" | "audio" | "document" | "other";

export type FileAsset = {
  id: string;
  name: string;
  media_type: MediaType;
  url: string;
  category: string;
  tags: string[];
  size_bytes: number | null;
  content_type: string | null;
  description: string;
  uploaded_by: string;
  created_at: string;
};

export type StorageSummary = {
  total: number;
  by_media_type: Record<string, { count: number; bytes: number }>;
};

export async function getStorageSummary(): Promise<StorageSummary> {
  const res = await fetch(`${API_BASE}/files/summary`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function listFileCategories(): Promise<{ categories: { category: string; count: number }[] }> {
  const res = await fetch(`${API_BASE}/files/categories`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function listFiles(opts?: { media_type?: string; category?: string; query?: string }): Promise<{ files: FileAsset[] }> {
  const qs = new URLSearchParams();
  if (opts?.media_type) qs.set("media_type", opts.media_type);
  if (opts?.category) qs.set("category", opts.category);
  if (opts?.query) qs.set("query", opts.query);
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  const res = await fetch(`${API_BASE}/files${suffix}`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function addFile(input: {
  name: string;
  media_type: MediaType;
  url: string;
  category?: string;
  tags?: string[];
  size_bytes?: number | null;
  content_type?: string | null;
  description?: string;
}): Promise<FileAsset> {
  const res = await fetch(`${API_BASE}/files`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(input),
  });
  return handle(res);
}

export async function removeFile(fileId: string) {
  const res = await fetch(`${API_BASE}/files/${encodeURIComponent(fileId)}`, {
    method: "DELETE",
    headers: { ...authHeaders() },
  });
  return handle<{ removed: string }>(res);
}
