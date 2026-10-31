import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export const LOBBY_FIELDS = {
  welcome: "Welcome", lounge: "Lounge", refreshments: "Refreshments",
  transport: "Transportation", accessibility: "Accessibility", guest_wifi: "Guest Wi-Fi",
} as const;
export type LobbyContent = Partial<Record<keyof typeof LOBBY_FIELDS, string>>;
export type PublicLobby = { published: boolean; content: LobbyContent };
export type LobbySettings = PublicLobby & { updated_at: string | null; updated_by: string | null };

async function result<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || data?.error) throw new Error("Lobby information could not be confirmed.");
  if (typeof data?.published !== "boolean" || !data.content || typeof data.content !== "object" || Array.isArray(data.content)) {
    throw new Error("Invalid lobby information response.");
  }
  return data as T;
}
export function getPublicLobby(): Promise<PublicLobby> {
  return fetch(`${API_BASE}/public/lobby`, { cache: "no-store" }).then(result<PublicLobby>);
}
export function getLobbySettings(): Promise<LobbySettings> {
  return fetch(`${API_BASE}/system-config/lobby`, { headers: authHeaders(), cache: "no-store" }).then(result<LobbySettings>);
}
export function saveLobbySettings(content: LobbyContent, published: boolean): Promise<LobbySettings> {
  return fetch(`${API_BASE}/system-config/lobby`, {
    method: "PUT", headers: { ...authHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify({ content, published }),
  }).then(result<LobbySettings>);
}
