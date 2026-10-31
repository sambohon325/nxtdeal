"use client";

// LockedModuleScreen — the App Suite's locked-state UI for a screen whose paid Module isn't
// active (Freemium Platform roadmap, Phase 1 gate; the richer Add-Modules flow is Phase 5).
// Shown in place of a wired screen when lib/entitlements' requiredModuleFor() names a Module the
// dealer isn't entitled to. Under the default "reference" profile no screen reaches this.

import { type AppDef, type AppScreen } from "@/lib/apps/registry";
import { MODULE_LABELS } from "@/lib/entitlements";
import { accentOf } from "@/lib/apps/registry";

export function LockedModuleScreen({
  app,
  screen,
  requiredModule,
}: {
  app: AppDef;
  screen: AppScreen;
  requiredModule: string;
}) {
  const accent = accentOf(app);
  const mod = MODULE_LABELS[requiredModule] ?? { name: "a paid Module", tagline: "" };

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-xl font-bold text-white">{screen.heading}</h2>
        <p className="mt-0.5 text-sm text-zinc-400">{screen.intro}</p>
      </div>

      <div className="rounded-2xl border border-white/10 bg-white/[0.05] p-6 text-center backdrop-blur-sm">
        <div className={`mx-auto flex h-12 w-12 items-center justify-center rounded-full ${accent.soft}`}>
          <svg viewBox="0 0 24 24" fill="none" className={`h-6 w-6 ${accent.text}`} aria-hidden>
            <path
              d="M7 11V8a5 5 0 0 1 10 0v3m-11 0h12a1 1 0 0 1 1 1v7a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1v-7a1 1 0 0 1 1-1Z"
              stroke="currentColor"
              strokeWidth="1.6"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </div>
        <div className="mt-3 text-sm font-semibold text-white">{mod.name} required</div>
        <p className="mx-auto mt-1 max-w-xs text-[12px] text-zinc-400">
          {screen.label} is part of the {mod.name}. {mod.tagline}
        </p>
        <p className="mx-auto mt-3 max-w-xs text-[11px] text-zinc-500">
          Your dealership is on NXTDeal Foundation. Add the {mod.name} to unlock this — no
          migration, your data is already here.
        </p>
        <button
          type="button"
          className={`mt-4 rounded-lg ${accent.soft} ${accent.softText} px-4 py-2 text-[12px] font-semibold`}
          onClick={() => {
            // Phase 5 wires the real self-serve Add-Modules flow here. For now, surface intent.
            if (typeof window !== "undefined") {
              window.dispatchEvent(new CustomEvent("dealeros:add-module", { detail: { module: requiredModule } }));
            }
          }}
        >
          Add {mod.name}
        </button>
      </div>
    </div>
  );
}
