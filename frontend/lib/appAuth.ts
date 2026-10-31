import { canonicalApiUrl } from "./canonicalApiUrl";

// NXTDeal App Suite auth (2026-07-24, multi-tenant routing added 2026-07-24).
//
// Staff apps in the suite log in with a dealership ID + username + password, matching how a rep
// or advisor thinks about signing in on their phone.
//
// TWO deployment shapes share this code:
//   • Single-tenant — the suite served under a dealer's own subdomain (dealer1.dealeros.xyz/apps).
//     NEXT_PUBLIC_API_URL is baked in, so the dealership ID is captured for UX only and login goes
//     straight to that one backend. This is the original behavior, unchanged.
//   • Multi-tenant — the shared app host apps.dealeros.xyz (NEXT_PUBLIC_DEPLOYMENT_MODE=apps),
//     which serves every dealer from one build. Here the dealership ID actually ROUTES the login:
//     we ask the Hub's public resolver where that dealer's backend lives, store that origin as the
//     per-tenant API override (lib/api.ts), authenticate against it, then hard-reload so every
//     typed client picks up the tenant. See docs/DEPLOYMENT.md "The shared app suite".
//
// App identity metadata has its own key, but appLogin mirrors staff credentials
// into the main workspace session (lib/auth.ts). Both views share that identity;
// replacement or sign-out must invalidate both, including other open tabs.

import { API_BASE, setTenantApiBase, clearTenantApiBase } from "@/lib/api";
import { HUB_API_BASE } from "@/lib/hubApi";
import { saveSession, clearSession, getSession } from "@/lib/auth";

// The shared apps host resolves the tenant at login; a dealer subdomain does not.
export const MULTI_TENANT_APPS = process.env.NEXT_PUBLIC_DEPLOYMENT_MODE === "apps";

export type AppSession = {
  token: string;
  employeeId: string;
  dealershipId: string;
  role: string;
  allowedDashboards?: string[];
  // Multi-tenant only: the resolved dealer API origin + display name for this session.
  apiBaseUrl?: string;
  dealershipName?: string;
};

const STORAGE_KEY = "dealeros_app_session";

// Storage events come from other tabs. Every typed client captures API_BASE at
// module load, so a tenant or identity change must discard the old view and reload.
// Observe the mirrored staff session too: back-office sign-out uses that key.
export function subscribeAppSessionChange(onChange: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  const keys = new Set([STORAGE_KEY, "dealeros_session", "dealeros_tenant_api"]);
  const changed = (event: StorageEvent) => {
    if (event.storageArea !== window.localStorage) return;
    if (event.key !== null && !keys.has(event.key)) return;
    if (event.key !== null && event.oldValue === event.newValue) return;
    onChange();
  };
  window.addEventListener("storage", changed);
  return () => window.removeEventListener("storage", changed);
}

export function saveAppSession(session: AppSession) {
  if (typeof window === "undefined") return;
  localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
}

export function getAppSession(): AppSession | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(STORAGE_KEY);
  if (!raw) return null;
  try {
    const session = JSON.parse(raw) as AppSession;
    const mirrored = getSession();
    // Screens use the mirrored staff token. Never pair an old app identity with
    // a different back-office login (or keep it signed in after that logout).
    if (!session?.token || !session.employeeId || !mirrored
        || mirrored.token !== session.token || mirrored.employeeId !== session.employeeId) return null;
    return session;
  } catch {
    return null;
  }
}

export function clearAppSession() {
  if (typeof window === "undefined") return;
  localStorage.removeItem(STORAGE_KEY);
}

// Sign out of an app: clear the app session, the back-office session that appLogin mirrored,
// and (multi-tenant) the per-tenant API override so the next sign-in re-resolves cleanly.
export function appSignOut() {
  clearAppSession();
  clearSession();
  clearTenantApiBase();
}

export function appAuthHeaders(): Record<string, string> {
  const session = getAppSession();
  return session ? { Authorization: `Bearer ${session.token}` } : {};
}

type ResolvedTenant = { apiBaseUrl: string; name: string; dealerId: string };

// Ask the Hub's public resolver where a dealership's backend lives. Only used on the shared
// apps host. Returns the dealer's API origin or a friendly error.
async function resolveTenant(
  dealershipId: string,
): Promise<{ ok: true; tenant: ResolvedTenant } | { ok: false; error: string }> {
  const id = dealershipId.trim();
  if (!id) return { ok: false, error: "Enter your dealership ID." };
  try {
    const res = await fetch(`${HUB_API_BASE}/hub/public/resolve/${encodeURIComponent(id)}`);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      // FastAPI HTTPException → { detail }; be tolerant of { error } too.
      const msg = (data && (data.detail || data.error)) || `We couldn't find dealership "${id}".`;
      return { ok: false, error: String(msg) };
    }
    if (!data || !data.api_base_url) {
      return { ok: false, error: `Dealership "${id}" isn't available online yet.` };
    }
    return {
      ok: true,
      tenant: {
        apiBaseUrl: canonicalApiUrl(String(data.api_base_url)),
        name: String(data.name ?? id),
        dealerId: String(data.dealer_id ?? id),
      },
    };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : "Couldn't reach the dealership directory." };
  }
}

type LoginResult =
  | { ok: true; session: AppSession; reload: boolean }
  | { ok: false; error: string };

// Sign in against the real backend. Username maps to employee_id (the backend's identifier).
// On the shared apps host, the dealership ID is first resolved to a tenant backend and login
// runs against THAT origin; `reload` comes back true so the caller hard-reloads to let API_BASE
// re-read the tenant override. On a dealer subdomain, login uses the baked-in API_BASE and
// `reload` is false. The backend returns {error} with a 200 on failure (its convention — see
// lib/auth.ts isAuthError), so we detect that in the body.
export async function appLogin(
  dealershipId: string,
  username: string,
  password: string,
): Promise<LoginResult> {
  try {
    // Pick the backend to authenticate against.
    let apiBase = API_BASE;
    let tenant: ResolvedTenant | null = null;
    if (MULTI_TENANT_APPS) {
      const resolved = await resolveTenant(dealershipId);
      if (!resolved.ok) return { ok: false, error: resolved.error };
      tenant = resolved.tenant;
      apiBase = tenant.apiBaseUrl;
    }

    const res = await fetch(`${apiBase}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ employee_id: username, password }),
    });
    const data = await res.json().catch(() => ({}));

    if (data && typeof data === "object" && "error" in data) {
      return { ok: false, error: String((data as { error: unknown }).error) };
    }
    if (!res.ok || !data || typeof data !== "object"
        || typeof data.token !== "string" || !data.token.trim()) {
      return { ok: false, error: "Unexpected response from server." };
    }

    const d = data as { token: string; employee_id?: string; role?: string; allowed_dashboards?: string[] };
    const session: AppSession = {
      token: d.token,
      employeeId: d.employee_id ?? username,
      dealershipId: dealershipId.trim(),
      role: d.role ?? "",
      allowedDashboards: d.allowed_dashboards ?? [],
      apiBaseUrl: tenant?.apiBaseUrl,
      dealershipName: tenant?.name,
    };
    // Commit routing only after successful authentication. A pending or failed
    // login must never send an existing tab's credentials to another tenant.
    if (tenant) setTenantApiBase(tenant.apiBaseUrl);
    saveAppSession(session);
    // Also populate the back-office session shape (same token from /auth/login) so the
    // existing typed API clients (lib/*.ts, which read authHeaders() → dealeros_session)
    // work unchanged inside the apps — that's what lets a screen call getMyDay(),
    // getRoBoard(), listAppointments(), etc. without a parallel client layer. On a phone
    // this is the only session anyway; appSignOut() clears both.
    saveSession({
      token: session.token,
      employeeId: session.employeeId,
      role: session.role,
      allowedDashboards: session.allowedDashboards ?? [],
      apiBaseUrl: apiBase,
    });
    return { ok: true, session, reload: MULTI_TENANT_APPS };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : "Network error." };
  }
}
