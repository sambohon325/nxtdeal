// Demo session store (2026-07-24) — the client half of the AI Demo Platform. When a prospect
// starts a demo (app/demo), we keep the demo context here AND dual-write the normal
// `dealeros_session` (lib/auth) with the persona's token, so every existing authed workspace
// client (authHeaders → dealeros_session) works against the seeded demo data with no changes.
// The demo backend tenant (DEALEROS_DEMO) can't persist, so this is a pure read/interact sandbox.
//
// A module-level store + useSyncExternalStore, matching lib/commsStore's pattern.

import { saveSession, clearSession } from "@/lib/auth";

export type DemoPersona = { key: string; label: string; focus: string[]; entry: string };
export type DemoScenario = { key: string; label: string; steps: string[] };
export type DemoMode = "guided" | "explore" | "power";

export type DemoSession = {
  token: string;
  sessionId: string;
  persona: DemoPersona;
  role: string;
  allowed_dashboards?: string[];
  mode: DemoMode;
  scenarios: DemoScenario[];
  watermark: { label: string; session_id: string; started_at: string };
};

const STORAGE_KEY = "dealeros_demo_session";

let current: DemoSession | null = null;
const listeners = new Set<() => void>();

function emit() {
  listeners.forEach((l) => l());
}

function load(): DemoSession | null {
  if (typeof window === "undefined") return null;
  if (current) return current;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    current = raw ? (JSON.parse(raw) as DemoSession) : null;
  } catch {
    current = null;
  }
  return current;
}

export function startDemoSession(session: DemoSession) {
  current = session;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
  } catch {
    /* ignore */
  }
  // Dual-write the workspace session so all authed clients use the persona token.
  saveSession({
    token: session.token,
    employeeId: "DEMO",
    role: session.role,
    allowedDashboards: session.allowed_dashboards ?? [],
  });
  emit();
}

export function endDemoSession() {
  current = null;
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* ignore */
  }
  clearSession();
  emit();
}

export function getDemoSession(): DemoSession | null {
  return load();
}

export function isDemoActive(): boolean {
  return load() !== null;
}

export function setDemoMode(mode: DemoMode) {
  const s = load();
  if (!s) return;
  current = { ...s, mode };
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(current));
  } catch {
    /* ignore */
  }
  emit();
}

function subscribe(cb: () => void) {
  listeners.add(cb);
  return () => listeners.delete(cb);
}

// React hook. Imported lazily by components; kept here to co-locate the store.
import { useSyncExternalStore } from "react";
export function useDemoSession(): DemoSession | null {
  return useSyncExternalStore(subscribe, getDemoSession, () => null);
}
