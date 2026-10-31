import { canonicalApiUrl } from "./canonicalApiUrl";

// Shared API base URL for talking to backend/api/app.py (the real graph-native backend —
// see CLAUDE.md, backend/main.py was retired 2026-07-13 once this was live-verified).
//
// Precedence (evaluated once at module load):
//   1. A client-stored TENANT OVERRIDE (localStorage "dealeros_tenant_api"), if present.
//   2. The build-time NEXT_PUBLIC_API_URL.
//   3. The local dev server.
//
// The override exists for the shared app suite host (apps.dealeros.xyz), which serves
// EVERY dealer from one build and therefore can't bake in a single NEXT_PUBLIC_API_URL.
// There the tenant is resolved per login (see lib/appAuth.ts): the resolved dealer API
// origin is written to the override, then the page hard-reloads so this module re-reads it
// and every typed client (which all interpolate API_BASE) talks to the right tenant. On a
// single-tenant dealer subdomain the override is never set, so this is exactly
// NEXT_PUBLIC_API_URL as before — zero behavior change.

const TENANT_API_KEY = "dealeros_tenant_api";

function resolveApiBase(): string {
  if (typeof window !== "undefined") {
    let override: string | null = null;
    try {
      override = window.localStorage.getItem(TENANT_API_KEY);
    } catch {
      /* localStorage unavailable — fall through to the build-time default */
    }
    if (override) return canonicalApiUrl(override);
  }
  return canonicalApiUrl(process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000");
}

export const API_BASE = resolveApiBase();

// Set/clear the per-tenant API override. Changing it only takes effect on the next module
// load, so callers set it and then hard-reload (window.location.reload()) into the app.
export function setTenantApiBase(url: string) {
  if (typeof window === "undefined") return;
  const canonical = canonicalApiUrl(url);
  try {
    window.localStorage.setItem(TENANT_API_KEY, canonical);
  } catch {
    /* ignore */
  }
}

export function clearTenantApiBase() {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(TENANT_API_KEY);
  } catch {
    /* ignore */
  }
}

export function getTenantApiBase(): string | null {
  if (typeof window === "undefined") return null;
  try {
    const value = window.localStorage.getItem(TENANT_API_KEY);
    return value ? canonicalApiUrl(value) : null;
  } catch {
    return null;
  }
}
