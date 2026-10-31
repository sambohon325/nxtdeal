// Tiny bridge so the globally-mounted DemoOverlay (root layout) can know "what's on screen" in the
// workspace (2026-07-25). The workspace publishes a short human-readable summary of the current
// department + open artifact whenever they change; the Demo Host reads it at question time and
// includes it so answers reference what the visitor is actually looking at. Same spirit as
// lib/demoNav.ts — a module-level store, no context/provider needed.

let current: string | null = null;

export function setDemoScreen(summary: string | null) {
  current = summary && summary.trim() ? summary.trim() : null;
}

export function getDemoScreen(): string | null {
  return current;
}
