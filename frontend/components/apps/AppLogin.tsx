"use client";

// AppLogin — the dealership sign-in screen for staff apps in the suite (2026-07-24).
//
// Collects dealership ID + username + password. On the shared apps host (apps.dealeros.xyz,
// MULTI_TENANT_APPS) the dealership ID ROUTES the login to that dealer's backend, so on success
// we hard-reload to let API_BASE pick up the resolved tenant (see lib/appAuth.ts). Rendered
// inside the same frame as the app it guards so sign-in feels like part of the app.

import { useId, useState } from "react";
import Link from "next/link";
import { type AppDef } from "@/lib/apps/registry";
import { appLogin, MULTI_TENANT_APPS } from "@/lib/appAuth";
import { useAppTheme, accentVars } from "@/lib/apps/appTheme";
import { AngledGlow, BrandRibbon } from "@/components/BrandAngles";

export function AppLogin({ app, onSignedIn }: { app: AppDef; onSignedIn: () => void }) {
  const theme = useAppTheme();
  const fieldId = useId();
  const [dealershipId, setDealershipId] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const res = await appLogin(dealershipId, username, password);
    if (res.ok) {
      // Multi-tenant: a per-tenant API override was just set; hard-reload so every client
      // re-reads it. Keep `busy` true through the reload so the button doesn't flash back.
      if (res.reload) {
        window.location.reload();
        return;
      }
      setBusy(false);
      onSignedIn();
    } else {
      setBusy(false);
      setError(res.error);
    }
  }

  const input =
    "w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white placeholder-zinc-500 focus:outline-none focus:border-[var(--app-accent)]";

  return (
    <div
      className="relative flex min-h-screen w-full items-center justify-center overflow-hidden bg-[#111113] p-4 font-brand"
      style={accentVars(theme)}
    >
      <AngledGlow color="blue" className="absolute -left-40 top-0 h-full w-[420px]" />
      <div
        aria-hidden
        className="pointer-events-none absolute -right-40 top-0 h-full w-[420px]"
        style={{ background: "var(--app-accent)", transform: "skewX(-27deg)", filter: "blur(48px)", opacity: 0.14 }}
      />

      <div className="relative z-10 flex w-full max-w-md flex-col overflow-hidden rounded-2xl border border-white/10 bg-[#141416]/85 text-white shadow-2xl backdrop-blur-md">
        <div className="bg-[var(--app-accent)] px-6 pb-8 pt-8 text-[var(--app-accent-text)]">
          <Link href="/apps" className="text-xs opacity-80 transition hover:opacity-100">‹ All apps</Link>
          <div className="mt-5 flex items-center gap-3">
            {theme.logoUrl ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={theme.logoUrl} alt="" className="h-12 w-12 rounded-lg bg-white/15 object-contain" />
            ) : (
              <span className="text-4xl leading-none">{app.icon}</span>
            )}
            <div>
              <div className="text-[10px] uppercase tracking-wider opacity-70">{theme.dealershipName}</div>
              <h1 className="text-2xl font-bold leading-tight">{app.name}</h1>
              <p className="text-sm opacity-80">{app.tagline}</p>
            </div>
          </div>
        </div>
        <BrandRibbon height={3} />

        <form onSubmit={submit} aria-busy={busy} className="flex-1 space-y-4 px-6 pb-6 pt-6">
          <div>
            <label htmlFor={`${fieldId}-dealership`} className="mb-1 block text-xs font-medium text-zinc-400">Dealership ID</label>
            <input
              className={input}
              placeholder={MULTI_TENANT_APPS ? "e.g. dealer1" : "e.g. your-dealership"}
              id={`${fieldId}-dealership`}
              name="dealership"
              value={dealershipId}
              onChange={(e) => setDealershipId(e.target.value)}
              autoCapitalize="none"
            />
            {MULTI_TENANT_APPS && (
              <p className="mt-1 text-[10px] text-zinc-500">
                Your store&apos;s ID connects this app to your dealership.
              </p>
            )}
          </div>
          <div>
            <label htmlFor={`${fieldId}-username`} className="mb-1 block text-xs font-medium text-zinc-400">Username</label>
            <input
              className={input}
              placeholder="Your employee username"
              id={`${fieldId}-username`}
              name="username"
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoCapitalize="none"
            />
          </div>
          <div>
            <label htmlFor={`${fieldId}-password`} className="mb-1 block text-xs font-medium text-zinc-400">Password</label>
            <input
              className={input}
              type="password"
              placeholder="••••••••"
              id={`${fieldId}-password`}
              name="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>

          {error && (
            <div role="alert" className="rounded-lg bg-red-500/10 p-2.5 text-xs text-red-400">{error}</div>
          )}

          <button
            type="submit"
            disabled={busy || !dealershipId || !username || !password}
            className="w-full rounded-full bg-[var(--app-accent)] py-3 text-sm font-semibold text-[var(--app-accent-text)] disabled:opacity-50"
          >
            {busy ? "Signing in…" : "Sign in"}
          </button>

          <p className="pt-2 text-center text-[11px] text-zinc-500">
            Signs in to your NXTDeal account and syncs to your dealership.
          </p>
        </form>
      </div>
    </div>
  );
}
