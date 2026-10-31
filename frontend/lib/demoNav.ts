// Demo navigation bridge (2026-07-24, Phase 2) — lets the AI Demo Host (components/demo/
// DemoOverlay, mounted globally) drive the workspace's INTERNAL nav, which is state-driven
// (selectedAgent department + dashboard artifacts), not URL-driven. The host writes a nav
// intent here; app/workspace subscribes and applies it (switch department, optionally open a
// dashboard). A module store + useSyncExternalStore, matching lib/commsStore/demoSession.

import { useSyncExternalStore } from "react";

export const DEMO_DEPARTMENTS = ["Operations", "Sales", "Marketing", "Inventory", "Service", "Finance"] as const;
export type DemoDepartment = (typeof DEMO_DEPARTMENTS)[number];

export type DemoNavIntent = {
  department?: DemoDepartment;
  dashboard?: string; // optional backend dashboard key to open as an artifact
  label?: string; // what the host said it's showing (for narration)
  nonce: number; // bumps every request so identical intents still re-fire
};

let current: DemoNavIntent | null = null;
let counter = 0;
const listeners = new Set<() => void>();

export function requestDemoNav(partial: Omit<DemoNavIntent, "nonce">) {
  counter += 1;
  current = { ...partial, nonce: counter };
  listeners.forEach((l) => l());
}

function subscribe(cb: () => void) {
  listeners.add(cb);
  return () => listeners.delete(cb);
}

export function getDemoNavIntent(): DemoNavIntent | null {
  return current;
}

export function useDemoNavIntent(): DemoNavIntent | null {
  return useSyncExternalStore(subscribe, getDemoNavIntent, () => null);
}

// Keyword → department. Ordered most-specific first so overlapping terms (e.g. "deal"
// vs "funding") resolve to the right place. Used for both tour steps and free-text
// questions, so a picked step OR a typed question navigates the workspace.
const RESOLUTION: { dept: DemoDepartment; keywords: string[] }[] = [
  { dept: "Finance", keywords: ["collection", "payment", "portfolio", "servicing", "recovery", "gps", "starter interrupt", "repossession", "f&i", "fi menu", "funding", "lender", "compliance", "credit", "bhph", "finance"] },
  { dept: "Service", keywords: ["repair order", "ro board", " ro", "dvi", "shop control", "technician", "retention", "parts", "fixed ops", "inspection", "advisor", "service"] },
  { dept: "Marketing", keywords: ["crm", "email", "sms", "website", "campaign", "event", "advertis", "audience", "landing page", "ads", "marketing"] },
  { dept: "Inventory", keywords: ["inventory", "stock", "vehicle", "lot", "vin", "appraisal", "recon"] },
  { dept: "Sales", keywords: ["lead", "bdc", "pipeline", "coaching", "coach", "sales agent", "showroom", "follow-up", "follow up", "my day", "desking", "digital retail", "up ", "ups", "sell", "sales"] },
  { dept: "Operations", keywords: ["readiness", "network", "forecast", "profit", "opportunit", "workforce", "benchmark", "store performance", "multi-store", "operations", "overview"] },
];

export function resolveDepartment(text: string): DemoDepartment | null {
  const t = ` ${(text || "").toLowerCase()} `;
  for (const { dept, keywords } of RESOLUTION) {
    if (keywords.some((k) => t.includes(k))) return dept;
  }
  return null;
}
