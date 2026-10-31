"use client";

// Customer purchase entry remains informational until secure verification is ready.

import { useState } from "react";
import { type AppDef, type AppScreen, accentOf } from "@/lib/apps/registry";
import { DigitalRetailFlow } from "@/components/DigitalRetailFlow";

export function ShowroomDeal({ app, screen }: { app: AppDef; screen: AppScreen }) {
  const accent = accentOf(app);
  const [open, setOpen] = useState(false);

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-xl font-bold text-white">{screen.heading}</h2>
        <p className="mt-0.5 text-sm text-zinc-500">{screen.intro}</p>
      </div>

      <div className={`${accent.soft} rounded-2xl border border-white/10 p-4`}>
        <h3 className="text-sm font-semibold text-white">Online buying is coming soon</h3>
        <p className="mt-1 text-xs text-zinc-300">
          Please contact the dealership to start your purchase. Secure online customer access is not available yet.
        </p>
        <button
          onClick={() => setOpen(true)}
          className={`${accent.bg} mt-3 w-full rounded-full py-2.5 text-sm font-semibold text-[var(--app-accent-text)]`}
        >
          View availability
        </button>
      </div>

      <DigitalRetailFlow open={open} onClose={() => setOpen(false)} />
    </div>
  );
}
