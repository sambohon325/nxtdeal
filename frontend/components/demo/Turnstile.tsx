"use client";

// Cloudflare Turnstile widget (2026-07-25) — the demo lead form's bot check. Renders only when a
// site key is configured (NEXT_PUBLIC_TURNSTILE_SITE_KEY on the demo frontend); otherwise it
// renders nothing and reports no token, and the Hub skips verification when its secret is unset —
// so the form works during setup and starts enforcing once both keys are in place.

import { useEffect, useRef } from "react";

const SITE_KEY = process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY;
const SCRIPT_SRC = "https://challenges.cloudflare.com/turnstile/v0/api.js";

// Minimal typing for the global the script installs.
type TurnstileApi = {
  render: (el: HTMLElement, opts: { sitekey: string; callback: (t: string) => void; "expired-callback"?: () => void; theme?: string }) => string;
  remove?: (id: string) => void;
};
declare global {
  interface Window {
    turnstile?: TurnstileApi;
  }
}

function ensureScript(): Promise<void> {
  return new Promise((resolve) => {
    if (typeof window === "undefined") return resolve();
    if (window.turnstile) return resolve();
    const existing = document.querySelector(`script[src="${SCRIPT_SRC}"]`);
    if (existing) {
      existing.addEventListener("load", () => resolve());
      return;
    }
    const s = document.createElement("script");
    s.src = SCRIPT_SRC;
    s.async = true;
    s.defer = true;
    s.onload = () => resolve();
    document.head.appendChild(s);
  });
}

export function isTurnstileConfigured() {
  return !!SITE_KEY;
}

export function Turnstile({ onToken }: { onToken: (token: string) => void }) {
  const ref = useRef<HTMLDivElement | null>(null);
  const widgetId = useRef<string | null>(null);

  useEffect(() => {
    if (!SITE_KEY) return;
    let cancelled = false;
    ensureScript().then(() => {
      if (cancelled || !ref.current || !window.turnstile) return;
      // Guard against a double render (React strict mode).
      if (widgetId.current) return;
      widgetId.current = window.turnstile.render(ref.current, {
        sitekey: SITE_KEY,
        theme: "dark",
        callback: (t) => onToken(t),
        "expired-callback": () => onToken(""),
      });
    });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!SITE_KEY) return null;
  return <div ref={ref} className="mt-1" />;
}
