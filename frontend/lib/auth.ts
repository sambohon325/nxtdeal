// Phase 9 wrap-up: minimal client-side session handling for api/app.py's token auth
// (core/auth.py — stdlib-signed tokens, not real JWT, 12h TTL). Token lives in
// localStorage; this is a deliberate simplification (an httpOnly cookie set by the
// backend would be more XSS-resistant, but that needs the backend to own Set-Cookie,
// which is a bigger change) — fine for now, worth revisiting if NXTDeal ever needs to
// harden against XSS specifically. See BUILD_QUEUE.md Phase 9.

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { API_BASE } from "@/lib/api";
import { canonicalApiUrl } from "./canonicalApiUrl";

export type Session = {
  token: string;
  employeeId: string;
  role: string;
  isSystemAdmin?: boolean;
  // Bind the token to the dealer origin it was issued for. Older unbound local
  // sessions deliberately require sign-in again after this frontend update.
  apiBaseUrl?: string;
  // Dashboard keys this role can open (core/permissions.py's DASHBOARD_ACCESS,
  // computed server-side and returned by POST /auth/login — see BUILD_QUEUE.md's
  // "Role-aware workspace tabs" entry). Optional/defaulted to [] for sessions saved
  // before this field existed (old localStorage entries from a prior login).
  allowedDashboards?: string[];
};

const STORAGE_KEY = "dealeros_session";

// Typed clients capture API_BASE when the page loads. A different identity or
// tenant in another tab must discard the old protected view before reloading it.
export function subscribeStaffSessionChange(onChange: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  const changed = (event: StorageEvent) => {
    if (event.storageArea !== window.localStorage) return;
    if (event.key !== null && event.key !== STORAGE_KEY && event.key !== "dealeros_tenant_api") return;
    if (event.key !== null && event.oldValue === event.newValue) return;
    onChange();
  };
  window.addEventListener("storage", changed);
  return () => window.removeEventListener("storage", changed);
}

export function saveSession(session: Session) {
  if (typeof window === "undefined") return;

  localStorage.setItem(STORAGE_KEY, JSON.stringify({
    ...session,
    apiBaseUrl: canonicalApiUrl(session.apiBaseUrl ?? API_BASE),
  }));
}

export function getSession(): Session | null {
  if (typeof window === "undefined") return null;

  const raw = localStorage.getItem(STORAGE_KEY);

  if (!raw) return null;

  try {
    const session = JSON.parse(raw) as Session;
    if (!session || typeof session.token !== "string" || !session.token
        || typeof session.apiBaseUrl !== "string"
        || canonicalApiUrl(session.apiBaseUrl) !== API_BASE) return null;
    return session;
  } catch {
    return null;
  }
}

export function clearSession() {
  if (typeof window === "undefined") return;

  localStorage.removeItem(STORAGE_KEY);
}

export function authHeaders(): Record<string, string> {
  const session = getSession();

  return session
    ? { Authorization: `Bearer ${session.token}` }
    : {};
}

// api/app.py's route-protection helpers (_authenticate/_require_admin in api/app.py)
// always return a 200 with {"error": "..."} on auth failure rather than a real 401 —
// matches the rest of that API's existing convention (see login/whoami). Client code
// checks the response body for authentication or onboarding errors to detect "the session needs attention,
// send the user back to sign in" rather than trusting the HTTP status code.
export function isAuthError(data: unknown): boolean {
  if (!data || typeof data !== "object" || !("error" in data)) {
    return false;
  }

  const message = String((data as { error: unknown }).error);

  return (
    message.includes("Authorization header") ||
    message.includes("Invalid or expired token") ||
    message === "Password change required"
  );
}

// Resolve current account state before exposing a protected page. Server-side
// authorization remains authoritative for every business request.
export async function resolveStaffSession(existing: Session, signal: AbortSignal) {
  const response = await fetch(`${API_BASE}/auth/whoami`, {
    headers: { Authorization: `Bearer ${existing.token}` },
    cache: "no-store", redirect: "error", signal,
  });
  const data = await response.json();
  if (!response.ok || !data || data.error || data.employee_id !== existing.employeeId
      || typeof data.role !== "string" || typeof data.must_change_password !== "boolean"
      || !Array.isArray(data.allowed_dashboards)
      || !data.allowed_dashboards.every((value: unknown) => typeof value === "string")) {
    throw new Error("Unable to verify account access");
  }
  return { session: { ...existing, role: data.role, isSystemAdmin: data.is_system_admin === true, allowedDashboards: data.allowed_dashboards } as Session,
    mustChangePassword: data.must_change_password as boolean };
}

// Shared route guard for protected pages (/workspace, /admin, /network, /readiness).
// No verified session -> bounce to sign-in. Verified account lacks `requiredRole` ->
// bounce to /workspace rather than back to sign-in, since they ARE authenticated, just
// not authorized for this specific page (e.g. a non-ADMIN hitting /admin). Returns null
// while checking or redirecting — callers should render nothing until it resolves to a
// real Session, same pattern /workspace already used before this was extracted.
export function useRequireAuth(requiredRole?: string): Session | null {
  const router = useRouter();
  const [session, setSession] = useState<Session | null>(null);

  useEffect(() => {
    const existing = getSession();

    if (!existing) {
      router.push("/");
      return;
    }

    let invalidated = false;
    const controller = new AbortController();
    setSession(null);
    const unsubscribe = subscribeStaffSessionChange(() => {
      if (invalidated) return;
      invalidated = true;
      controller.abort();
      setSession(null);
      window.location.reload();
    });
    resolveStaffSession(existing, controller.signal).then(result => {
      if (invalidated) return;
      if (result.mustChangePassword) { router.replace("/change-password"); return; }
      if (requiredRole && result.session.role !== requiredRole) { router.replace("/workspace"); return; }
      setSession(result.session);
    }).catch(() => {
      if (!invalidated) router.replace("/");
    });
    return () => { invalidated = true; controller.abort(); unsubscribe(); };
  }, [router, requiredRole]);

  return session;
}
