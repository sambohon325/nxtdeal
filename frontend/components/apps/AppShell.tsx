"use client";

import { AppIcon } from "@/components/apps/AppIcon";

// AppShell — the NXTDeal-themed frame every suite app renders inside (2026-07-24 theme v2).
//
// Matches the main NXTDeal app: dark #111 background, ambient ANGLED GLOWS (blue + the dealer's
// accent), the 4-color brand ribbon, glassy chrome (translucent + backdrop-blur), the brand font,
// and angled accents. Fully responsive / full-bleed 16:9 — it fills a monitor in landscape (rail +
// wide workspace), fits a tablet, and collapses to a tall single column with a bottom tab bar on a
// phone — no more fixed tall-tablet column. The dealer's accent flows through via `--app-accent`.

import { useState, type ReactNode } from "react";
import Link from "next/link";
import { type AppDef } from "@/lib/apps/registry";
import { useAppTheme, accentVars } from "@/lib/apps/appTheme";
import { StaffProgress } from "@/components/apps/StaffProgress";
import { AppSettings } from "@/components/apps/AppSettings";
import { CommsWorkspaceMount } from "@/components/CustomerCommsPanel";
import { AngledGlow, BrandRibbon, angledClip } from "@/components/BrandAngles";

export function AppShell({
  app,
  children,
  activeTab,
  onTabChange,
  onSignOut,
  subtitle,
}: {
  app: AppDef;
  children: ReactNode;
  activeTab: string;
  onTabChange: (key: string) => void;
  onSignOut?: () => void;
  subtitle?: string;
}) {
  const theme = useAppTheme();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [progressOpen, setProgressOpen] = useState(false);

  return (
    <div
      className="nxt-suite nxt-workflow relative flex h-[100dvh] w-full flex-col overflow-hidden font-brand text-white"
      style={accentVars(theme)}
    >
      <a href="#workspace-content" onClick={event => { event.preventDefault(); document.getElementById("workspace-content")?.focus(); }} className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-lg focus:bg-white focus:p-3 focus:text-black">Skip to workspace content</a>
      {/* Ambient angled glows — blue on the left, the dealer's accent on the right (NXTDeal's
          styleguide background treatment). Purely decorative; glass surfaces let them show through. */}
      <AngledGlow color="blue" className="absolute -left-40 top-0 h-full w-[420px]" />
      <div
        aria-hidden
        className="pointer-events-none absolute -right-40 top-0 h-full w-[420px]"
        style={{ background: "var(--app-accent)", borderRadius: "50%", filter: "blur(100px)", opacity: 0.035 }}
      />

      {/* top chrome — dark glass, matching the main app's header (not a big colored bar) */}
      <header className="relative z-10 shrink-0 border-b border-white/10 bg-[#061019]/85 backdrop-blur-md">
        <div className="flex items-center justify-between px-4 py-2.5 md:px-6">
          <div className="flex min-w-0 items-center gap-3">
            <Link href="/apps" className="shrink-0 text-xs text-zinc-400 transition hover:text-white">‹ Workspaces</Link>
            <div className="flex min-w-0 items-center gap-2.5">
              <div
                className="flex h-9 w-9 shrink-0 items-center justify-center text-lg text-[var(--app-accent-text)]"
                style={angledClip(6)}
              >
                {theme.logoUrl ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={theme.logoUrl} alt="" className="h-full w-full object-contain" />
                ) : (
                  <AppIcon name={app.icon} className="h-10 w-10" />
                )}
              </div>
              <div className="min-w-0">
                <div className="truncate text-[10px] uppercase tracking-wider text-zinc-500">{theme.dealershipName}</div>
                <div className="flex items-baseline gap-2">
                  <h1 className="truncate text-sm font-bold leading-tight">{app.name}</h1>
                  <span className="hidden truncate text-[11px] text-zinc-500 sm:inline">{subtitle ?? app.tagline}</span>
                </div>
              </div>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-3">

            {app.requiresStaffLogin && app.audience === "staff" && <button aria-expanded={progressOpen} onClick={() => setProgressOpen(!progressOpen)} className="text-xs text-zinc-300">{progressOpen ? "Back to app" : "Progress"}</button>}
            <button onClick={() => setSettingsOpen(true)} className="text-sm text-zinc-400 transition hover:text-white" title="Appearance" aria-label="Appearance"><AppIcon name="settings" tile={false} className="h-5 w-5" /></button>
            {onSignOut && (
              <button onClick={onSignOut} className="text-xs text-zinc-400 transition hover:text-white">Sign out</button>
            )}
          </div>
        </div>
        {/* the NXTDeal 4-color angled brand ribbon */}
        <BrandRibbon height={3} />
      </header>

      {/* body: glass left rail (tablet/desktop) + content */}
      <div className="relative z-10 flex min-h-0 flex-1">
        <nav aria-label="Workspace tasks" className="hidden w-64 shrink-0 flex-col gap-1 overflow-y-auto border-r border-white/10 bg-[#061019]/50 p-2.5 backdrop-blur-md md:flex">
          {app.screens.map((s) => {
            const active = !progressOpen && s.key === activeTab;
            return (
              <button
                key={s.key}
                aria-current={!progressOpen && s.key === activeTab ? "page" : undefined}
                onClick={() => { setProgressOpen(false); onTabChange(s.key); }}
                className={`group relative flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition ${
                  active ? "bg-white/[0.07] font-semibold text-white" : "text-zinc-400 hover:bg-white/[0.04] hover:text-white"
                }`}
              >
                {active && <span className="absolute left-0 top-1/2 h-5 w-1 -translate-y-1/2 rounded-r bg-[var(--app-accent)]" />}
                <span
                  className={`flex h-8 w-8 items-center justify-center text-base transition ${
                    active ? "bg-[color-mix(in_srgb,var(--app-accent)_22%,transparent)] text-white" : "bg-white/[0.04] text-zinc-400 group-hover:text-white"
                  }`}
                  style={angledClip(4)}
                >
                  <AppIcon name={s.icon} tile={false} className="h-5 w-5" />
                </span>
                <span className="text-left leading-5">{s.label}</span>
              </button>
            );
          })}
        </nav>

        <main id="workspace-content" tabIndex={-1} className="min-h-0 min-w-0 flex-1 overflow-y-auto focus:outline-none">
          <div className="mx-auto w-full max-w-6xl px-4 py-5 pb-24 md:px-8 md:pb-8">{progressOpen && app.requiresStaffLogin && app.audience === "staff" ? <StaffProgress /> : children}</div>
        </main>
      </div>

      <nav aria-label="Mobile workspace tasks" className="relative z-10 shrink-0 border-t border-white/15 bg-[#102331] px-4 py-3 pb-[max(12px,env(safe-area-inset-bottom))] md:hidden">
        <label htmlFor="mobile-task" className="mb-1 block text-xs font-semibold text-slate-300">Go to a task</label>
        <select id="mobile-task" value={progressOpen ? "" : activeTab} onChange={event => { setProgressOpen(false); onTabChange(event.target.value); }} className="min-h-12 w-full rounded-lg border border-white/15 bg-white/5 px-3 text-base text-white">
          {progressOpen && <option value="" disabled>Staff progress</option>}
          {app.screens.map(screen => <option key={screen.key} value={screen.key}>{screen.label}</option>)}
        </select>
      </nav>
      {settingsOpen && <AppSettings onClose={() => setSettingsOpen(false)} />}
      <CommsWorkspaceMount />
    </div>
  );
}
