// lib/apps/appTheme.ts — the NXTDeal app-suite theme (2026-07-24, Sam's spec).
//
// Every app now shares ONE NXTDeal look (dark brand chrome, brand font, angled accents) instead
// of a random per-app color. The single thing a dealership customizes — within our framework — is
// the brand: an accent color, their name, and a logo. That customization flows through the whole
// suite via one CSS variable (`--app-accent`, set on the shell root) so no screen needs per-dealer
// code: accent classes read the variable, arbitrary dealer colors just work.
//
// Persisted to localStorage (per browser) for now; a future slice can load/save it per dealership
// from the backend. Exposed through a tiny useSyncExternalStore store, same pattern as commsStore.

import { useSyncExternalStore } from "react";

export type AppTheme = {
  dealershipName: string;
  logoUrl: string | null;
  accent: string; // any CSS color; dealers pick their brand color
  accentText: string; // readable text color on the accent (#fff / #111)
};

// NXTDeal defaults — brand blue primary, white text on it.
export const DEFAULT_THEME: AppTheme = {
  dealershipName: "NXTDeal",
  logoUrl: null,
  accent: "#2b68ab",
  accentText: "#ffffff",
};

const KEY = "dealeros_app_theme";

function load(): AppTheme {
  if (typeof window === "undefined") return DEFAULT_THEME;
  try {
    const raw = window.localStorage.getItem(KEY);
    return raw ? { ...DEFAULT_THEME, ...JSON.parse(raw) } : DEFAULT_THEME;
  } catch {
    return DEFAULT_THEME;
  }
}

// Hydrate from localStorage as soon as this module loads on the client, so the first client render
// already has the dealer's theme (the app routes are client components).
let current: AppTheme = typeof window === "undefined" ? DEFAULT_THEME : load();

const listeners = new Set<() => void>();
function emit() {
  listeners.forEach((l) => l());
}

export function getAppTheme(): AppTheme {
  return current;
}

export function setAppTheme(patch: Partial<AppTheme>) {
  current = { ...current, ...patch };
  if (typeof window !== "undefined") {
    try {
      window.localStorage.setItem(KEY, JSON.stringify(current));
    } catch {
      /* ignore quota / privacy-mode failures */
    }
  }
  emit();
}

export function resetAppTheme() {
  current = { ...DEFAULT_THEME };
  if (typeof window !== "undefined") {
    try {
      window.localStorage.removeItem(KEY);
    } catch {
      /* ignore */
    }
  }
  emit();
}

function subscribe(cb: () => void) {
  listeners.add(cb);
  return () => {
    listeners.delete(cb);
  };
}

export function useAppTheme(): AppTheme {
  return useSyncExternalStore(subscribe, () => current, () => DEFAULT_THEME);
}

// The style object to spread onto the shell root so descendants can use `var(--app-accent)`.
export function accentVars(theme: AppTheme): React.CSSProperties {
  return {
    ["--app-accent" as string]: theme.accent,
    ["--app-accent-text" as string]: theme.accentText,
  } as React.CSSProperties;
}
