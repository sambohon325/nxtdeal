// lib/commsStore.ts — a tiny global store so ANY dashboard can open the Communications
// call/text workspace (2026-07-24). NXTDeal has no global store convention (useMenuDash is a
// per-page useState hook), so this is a minimal module-level store exposed through
// useSyncExternalStore: a board's "Call"/"Text" button calls startCommsSession(...) and the
// single workspace modal (mounted once in CommunicationsPanel) opens with the customer preloaded.
// This is the cross-cutting wiring the CustomerCommsPanel workspace was built to be reused by.

import { useSyncExternalStore } from "react";

export type CommsSession = {
  mode: "call" | "text";
  customerId?: string;
  number?: string;
  name?: string;
};

let current: CommsSession | null = null;
const listeners = new Set<() => void>();

function emit() {
  listeners.forEach((l) => l());
}

export function startCommsSession(session: CommsSession) {
  current = session;
  emit();
}

export function closeCommsSession() {
  current = null;
  emit();
}

function subscribe(cb: () => void) {
  listeners.add(cb);
  return () => {
    listeners.delete(cb);
  };
}

function getSnapshot() {
  return current;
}

export function useCommsSession(): CommsSession | null {
  // getServerSnapshot returns null — the workspace is client-only (auth + fetch on open).
  return useSyncExternalStore(subscribe, getSnapshot, () => null);
}

// ---------------------------------------------------------------------------------------------
// AI coaching preferences (2026-07-24, Sam: reps "need AI coaching built in that they can
// control"). A per-rep, localStorage-backed toggle + style the call/text workspace respects.
// ---------------------------------------------------------------------------------------------

export type CoachingStyle = "supportive" | "direct" | "aggressive";
export type CoachingPrefs = { enabled: boolean; style: CoachingStyle };

const COACH_KEY = "dealeros_coaching_prefs";
const DEFAULT_COACH: CoachingPrefs = { enabled: true, style: "supportive" };

function loadCoach(): CoachingPrefs {
  if (typeof window === "undefined") return DEFAULT_COACH;
  try {
    const raw = window.localStorage.getItem(COACH_KEY);
    return raw ? { ...DEFAULT_COACH, ...JSON.parse(raw) } : DEFAULT_COACH;
  } catch {
    return DEFAULT_COACH;
  }
}

let coach: CoachingPrefs = typeof window === "undefined" ? DEFAULT_COACH : loadCoach();
const coachListeners = new Set<() => void>();

export function getCoachingPrefs(): CoachingPrefs {
  return coach;
}

export function setCoachingPrefs(patch: Partial<CoachingPrefs>) {
  coach = { ...coach, ...patch };
  if (typeof window !== "undefined") {
    try {
      window.localStorage.setItem(COACH_KEY, JSON.stringify(coach));
    } catch {
      /* ignore */
    }
  }
  coachListeners.forEach((l) => l());
}

export function useCoachingPrefs(): CoachingPrefs {
  return useSyncExternalStore(
    (cb) => {
      coachListeners.add(cb);
      return () => coachListeners.delete(cb);
    },
    () => coach,
    () => DEFAULT_COACH,
  );
}
