"use client";

import type { AppDef, AppScreen } from "@/lib/apps/registry";

// Informational customer screens must not present roadmap features as available.
export function CustomerUnavailable({ screen }: { app: AppDef; screen: AppScreen }) {
  return (
    <section className="space-y-4">
      <h2 className="text-xl font-bold text-white">{screen.heading}</h2>
      <div role="status" className="rounded-2xl border border-white/10 bg-white/[0.05] p-4">
        <p className="text-sm text-zinc-300">{screen.intro}</p>
        <p className="mt-2 text-sm text-zinc-400">Please contact the dealership for assistance.</p>
      </div>
    </section>
  );
}
