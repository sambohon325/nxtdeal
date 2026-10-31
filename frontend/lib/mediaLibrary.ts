// Shared media library client (2026-07-23) -- the dealership-wide image asset library
// (OEM approved images, logos, dealership branding, and live inventory photos merged
// in) reachable from every marketing tool. Talks to backend/api/routers/media_library.py's
// /media-library/* routes. Mirrors lib/accessories.ts's client shape (API_BASE +
// authHeaders + a shared handle<T> helper, one thin call per route).

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type MediaImage = {
  id: string;
  url: string;
  name: string;
  category: string;
  tags: string[];
  scope: "library" | "inventory";
  vehicle_id?: string;
  vehicle?: string;
  uploaded_by: string | null;
  created_at: string | null;
  removable: boolean;
};

export type MediaCategory = {
  key: string;
  label: string;
  count: number;
};

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (
    !response.ok ||
    (data && typeof data === "object" && "error" in data && (data as { error?: string }).error)
  ) {
    throw new Error(
      (data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend."
    );
  }
  return data as T;
}

export function listMediaCategories(): Promise<{ categories: MediaCategory[] }> {
  return fetch(`${API_BASE}/media-library/categories`, { headers: { ...authHeaders() } }).then(
    handle<{ categories: MediaCategory[] }>
  );
}

export function listMedia(category?: string, query?: string): Promise<{ images: MediaImage[] }> {
  const params = new URLSearchParams();
  if (category) params.set("category", category);
  if (query) params.set("q", query);
  const qs = params.toString();
  return fetch(`${API_BASE}/media-library${qs ? `?${qs}` : ""}`, {
    headers: { ...authHeaders() },
  }).then(handle<{ images: MediaImage[] }>);
}

export function addMedia(
  url: string,
  name: string,
  category: string,
  tags: string[] = []
): Promise<{ image: MediaImage }> {
  return fetch(`${API_BASE}/media-library`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ url, name, category, tags }),
  }).then(handle<{ image: MediaImage }>);
}

export function removeMedia(imageId: string): Promise<{ removed: string }> {
  return fetch(`${API_BASE}/media-library/${encodeURIComponent(imageId)}`, {
    method: "DELETE",
    headers: { "Content-Type": "application/json", ...authHeaders() },
  }).then(handle<{ removed: string }>);
}


/** Managed artwork paths stay tenant-relative in saved website content. */
export function mediaImageUrl(url: string): string {
  return /^\/public\/media-library\/[0-9a-f]{32}\.png$/.test(url) ? `${API_BASE}${url}` : url;
}

export function uploadMedia(file: File, name: string, category: string): Promise<{ image: MediaImage }> {
  const body = new FormData();
  body.append("file", file);
  body.append("name", name);
  body.append("category", category);
  return fetch(`${API_BASE}/media-library/upload`, { method: "POST", headers: { ...authHeaders() }, body }).then(handle<{ image: MediaImage }>);
}
