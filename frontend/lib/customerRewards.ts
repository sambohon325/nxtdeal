import { API_BASE } from "@/lib/api";
let csrf = "";
const pendingRequests = new Map<string,string>();

export async function customerRewards<T>(path = "", body?: unknown): Promise<T> {
  let fingerprint: string | undefined;
  if (body && typeof body === "object" && "request_key" in body) {
    const values = { ...body } as Record<string,unknown>;
    delete values.request_key;
    fingerprint = path + JSON.stringify(values);
    const key = pendingRequests.get(fingerprint) || String((body as {request_key:string}).request_key);
    pendingRequests.set(fingerprint,key);
    body = {...values,request_key:key};
  }
  const response = await fetch(`${API_BASE}/customer/loyalty${path}`, {
    method: body === undefined ? "GET" : "POST",
    credentials: "include",
    cache: "no-store",
    headers: { "Content-Type": "application/json", ...(csrf ? { "X-Loyalty-CSRF": csrf } : {}) },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await response.json();
  if (fingerprint && response.status < 500) pendingRequests.delete(fingerprint);
  if (!response.ok || data.error) {
    if (response.status === 401) window.dispatchEvent(new Event("rewards-session-expired"));
    throw new Error(typeof data.detail === "string" ? data.detail : data.error || "Unable to load rewards.");
  }
  if (typeof data.csrf === "string") csrf = data.csrf;
  if (data.signed_out) { csrf = ""; pendingRequests.clear(); }
  return data;
}
