"use client";
import { WorkButton, WorkInput } from "./WorkspaceUi";
import { WorkField } from "./WorkField";

// Administration → "Modules & Plan" (Freemium Platform roadmap, Phase 5, 2026-08-03). The
// in-product surface for the tenant-side Foundation-plus-Modules entitlement layer the running
// product actually enforces (core/entitlements.py). ADMIN/OPERATIONS. Shows Foundation + every paid
// Module with its active state and level, lets an admin switch the whole dealer between the
// full-build "reference" profile and Tier-0 "foundation", add/adjust an individual Module, and set
// the Foundation usage caps. Mutates via the dedicated /entitlements/* routes.

import { useEffect, useState } from "react";
import {
  getEntitlements,
  getEntitlementCatalog,
  setEntitlementProfile,
  setEntitlementModule,
  setEntitlementCap,
  type EntitlementRecord,
  type EntitlementCatalog,
} from "@/lib/entitlements";

type Theme = "dark" | "light";
function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const LEVELS = ["professional", "enterprise"] as const;

export function AddModulesBoard({ theme = "dark" }: { theme?: Theme }) {
  const [rec, setRec] = useState<EntitlementRecord | null>(null);
  const [catalog, setCatalog] = useState<EntitlementCatalog | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  async function load() {
    try {
      const [r, c] = await Promise.all([getEntitlements(), getEntitlementCatalog()]);
      setRec(r);
      setCatalog(c);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't load entitlements.");
    }
  }
  useEffect(() => {
    load();
  }, []);

  async function guard(key: string, fn: () => Promise<EntitlementRecord>) {
    setBusy(key);
    setError(null);
    try {
      setRec(await fn());
    } catch (e) {
      setError(e instanceof Error ? e.message : "That change didn't take.");
    } finally {
      setBusy(null);
    }
  }

  if (error && !rec) return <div className="rounded-lg bg-red-500/10 px-4 py-3 text-sm text-red-400">{error}</div>;
  if (!rec || !catalog) return <div className="py-10 text-center text-sm text-zinc-500">Loading modules…</div>;

  const card = tc(theme, "rounded-xl border border-white/10 bg-white/[0.03] p-4", "rounded-xl border border-zinc-200 bg-white p-4");
  const sub = tc(theme, "text-zinc-400", "text-zinc-500");

  return (
    <div className="space-y-5">
      {error && <div className="rounded-lg bg-red-500/10 px-4 py-2 text-sm text-red-400">{error}</div>}

      {/* Profile switch */}
      <div className={card}>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-sm font-semibold">Plan profile</div>
            <div className={`text-xs ${sub}`}>
              Current: <span className="font-medium capitalize">{rec.profile}</span> ·{" "}
              {rec.active_modules.length - 1} of {catalog.paid_modules.length} paid Modules active
            </div>
          </div>
          <div className="flex gap-2">
            <WorkButton type="submit"
              onClick={() => guard("profile:reference", () => setEntitlementProfile("reference"))}
              disabled={!!busy}
              className={`rounded-lg px-3 py-1.5 text-xs font-semibold ${rec.profile === "reference" ? "bg-emerald-600 text-white" : tc(theme, "bg-white/10 text-zinc-200", "bg-zinc-100 text-zinc-700")}`}
            >
              Full build (reference)
            </WorkButton>
            <WorkButton type="submit"
              onClick={() => guard("profile:foundation", () => setEntitlementProfile("foundation"))}
              disabled={!!busy}
              className={`rounded-lg px-3 py-1.5 text-xs font-semibold ${rec.profile === "foundation" ? "bg-emerald-600 text-white" : tc(theme, "bg-white/10 text-zinc-200", "bg-zinc-100 text-zinc-700")}`}
            >
              Foundation only (Tier 0)
            </WorkButton>
          </div>
        </div>
      </div>

      {/* Foundation (always on) */}
      <div className={card}>
        <div className="flex items-center gap-2">
          <span className="rounded-full bg-emerald-500/15 px-2 py-0.5 text-xs font-semibold text-emerald-400">FREE · ALWAYS ON</span>
          <span className="text-sm font-semibold">{catalog.modules[catalog.foundation_key].name}</span>
        </div>
        <div className={`mt-1 text-xs ${sub}`}>{catalog.modules[catalog.foundation_key].tagline}</div>
      </div>

      {/* Paid modules */}
      <div className="grid gap-3 md:grid-cols-2">
        {catalog.paid_modules.map((key) => {
          const mod = catalog.modules[key];
          const state = rec.modules[key] ?? { enabled: false, level: "professional" };
          const on = state.enabled;
          return (
            <div key={key} className={card}>
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="text-sm font-semibold">{mod.name}</div>
                  <div className={`text-xs ${sub}`}>{mod.tagline}</div>
                </div>
                <span
                  className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-semibold ${on ? "bg-emerald-500/15 text-emerald-400" : tc(theme, "bg-white/10 text-zinc-400", "bg-zinc-100 text-zinc-500")}`}
                >
                  {on ? `ON · ${state.level}` : "LOCKED"}
                </span>
              </div>

              <div className="mt-3 flex items-center gap-2">
                <WorkButton type="submit"
                  onClick={() => guard(`mod:${key}`, () => setEntitlementModule(key, !on, state.level))}
                  disabled={!!busy}
                  className={`rounded-lg px-3 py-1.5 text-xs font-semibold ${on ? tc(theme, "bg-white/10 text-zinc-200", "bg-zinc-100 text-zinc-700") : "bg-emerald-600 text-white"}`}
                >
                  {busy === `mod:${key}` ? "…" : on ? "Turn off" : "Add Module"}
                </WorkButton>
                {on && (
                  <div className="flex gap-1">
                    {LEVELS.map((lvl) => (
                      <WorkButton type="submit"
                        key={lvl}
                        onClick={() => guard(`mod:${key}:${lvl}`, () => setEntitlementModule(key, true, lvl))}
                        disabled={!!busy}
                        className={`rounded-md px-2 py-1 text-xs font-medium capitalize ${state.level === lvl ? "bg-brand-blue text-white" : tc(theme, "bg-white/5 text-zinc-400", "bg-zinc-50 text-zinc-500")}`}
                      >
                        {lvl}
                      </WorkButton>
                    ))}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Foundation usage caps */}
      <div className={card}>
        <div className="text-sm font-semibold">Foundation usage caps</div>
        <div className={`mb-2 text-xs ${sub}`}>Starting points, tunable per dealer. Blank = unlimited.</div>
        <div className="grid gap-2 sm:grid-cols-2">
          {Object.entries(catalog.usage_caps).map(([cap, spec]) => (
            <CapRow
              key={cap}
              theme={theme}
              label={spec.name}
              unit={spec.unit}
              value={rec.caps[cap] ?? null}
              busy={busy === `cap:${cap}`}
              onSave={(v) => guard(`cap:${cap}`, () => setEntitlementCap(cap, v))}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

function CapRow({
  theme,
  label,
  unit,
  value,
  busy,
  onSave,
}: {
  theme: Theme;
  label: string;
  unit: string;
  value: number | null;
  busy: boolean;
  onSave: (v: number | null) => void;
}) {
  const [draft, setDraft] = useState<string>(value === null ? "" : String(value));
  useEffect(() => {
    setDraft(value === null ? "" : String(value));
  }, [value]);
  return (
    <div className={tc(theme, "flex items-center justify-between gap-2 rounded-lg border border-white/5 px-3 py-2", "flex items-center justify-between gap-2 rounded-lg border border-zinc-100 px-3 py-2")}>
      <div className="min-w-0">
        <div className="truncate text-xs font-medium">{label}</div>
        <div className="text-xs text-zinc-500">{unit}</div>
      </div>
      <div className="flex items-center gap-1">
        <WorkField label="Limit"><WorkInput
          value={draft}
          onChange={(e) => setDraft(e.target.value.replace(/[^0-9]/g, ""))}
          placeholder="∞"
          className={tc(theme, "w-16 rounded-md border border-white/10 bg-black/20 px-2 py-1 text-right text-xs text-white outline-none", "w-16 rounded-md border border-zinc-200 bg-white px-2 py-1 text-right text-xs outline-none")}
        /></WorkField>
        <WorkButton type="submit" variant="primary"
          onClick={() => onSave(draft === "" ? null : Number(draft))}
          disabled={busy}
          className="rounded-md bg-brand-blue px-2 py-1 text-xs font-semibold text-white disabled:opacity-50"
        >
          {busy ? "…" : "Set"}
        </WorkButton>
      </div>
    </div>
  );
}
