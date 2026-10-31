"use client";

import type { ReactNode } from "react";

// Public identity providers and session lifetime controls are not ready. Keep
// protected children unmounted, including for tokens from the former simulation.
// The API independently enforces the same boundary; this is only the UI state.
export function CustomerVerifyGate({ what }: { what: string; children: ReactNode }) {
  return (
    <section role="status" className="rounded-2xl border border-white/10 bg-white/[0.05] p-4 backdrop-blur-sm">
      <h3 className="text-sm font-semibold text-white">Customer access is coming soon</h3>
      <p className="mt-2 text-sm text-zinc-400">
        Secure customer verification is not available yet. Please contact your dealership for help with {what}.
      </p>
    </section>
  );
}
