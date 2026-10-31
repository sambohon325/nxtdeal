// Track B provider-connections client (2026-07-25): integration status + credential store.
// Talks to backend/api/routers/connections.py (/connections). Secrets are masked by the
// backend on read; configuring a credential can flip a capability live.
import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

export type ProviderStatus = {
  capability: string;
  name: string;
  description: string;
  recommended_provider: string;
  consumed_by: string[];
  mode: "live" | "simulated";
  scope: "dealer" | "personal";
  layer: string;
  configured_provider: string | null;
  note: string | null;
};

export type StoredCredential = {
  id: string;
  capability: string;
  provider: string;
  config: Record<string, string>;
  secrets: Record<string, string>;
  has_builder: boolean;
  live: boolean;
  configured_by: string | null;
  updated_at: string | null;
};

export type ProviderSlot = { provider: string; has_builder: boolean };

export type ConnectionsView = {
  status: {
    providers: ProviderStatus[];
    live_count: number;
    simulated_count: number;
    by_layer?: { dealer: string[]; personal: string[] };
    disclaimer: string;
  };
  credentials: StoredCredential[];
  slots: Record<string, ProviderSlot[]>;
};

export async function getConnections(): Promise<ConnectionsView> {
  const res = await fetch(`${API_BASE}/connections`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function configureCredential(
  capability: string,
  provider: string,
  config: Record<string, string>,
  secrets: Record<string, string>
): Promise<{ capability: string; provider: string; live: boolean; has_builder: boolean; note: string }> {
  const res = await fetch(`${API_BASE}/connections/${encodeURIComponent(capability)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ provider, config, secrets }),
  });
  return handle(res);
}

export async function removeCredential(capability: string): Promise<{ ok: boolean; capability: string; live: boolean }> {
  const res = await fetch(`${API_BASE}/connections/${encodeURIComponent(capability)}`, {
    method: "DELETE",
    headers: { ...authHeaders() },
  });
  return handle(res);
}
