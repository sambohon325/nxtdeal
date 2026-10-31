"use client";

import { useState } from "react";
import Link from "next/link";
import { AppIcon } from "@/components/apps/AppIcon";
import { BrandLogo } from "@/components/BrandLogo";
import { APP_SUITE, type AppDef } from "@/lib/apps/registry";
import { WORKSPACES, workspaceMatches } from "@/lib/apps/workflows";
import { useAppTheme, accentVars } from "@/lib/apps/appTheme";
import { BrandRibbon } from "@/components/BrandAngles";

function WorkspaceCard({ app }: { app: AppDef }) {
  const info = WORKSPACES[app.slug];
  return (
    <article className="flex h-full flex-col rounded-2xl border border-white/15 bg-white/5 p-6">
      <div className="flex items-center gap-4">
        <AppIcon name={app.icon} className="h-12 w-12 shrink-0" />
        <div>
          <p className="text-sm text-[var(--app-accent)]">{info.role}</p>
          <h3 className="mt-1 text-xl font-semibold text-white">{app.name}</h3>
        </div>
      </div>
      <p className="mt-4 text-base leading-7 text-slate-200">{info.purpose}</p>
      {info.note && <p className="mt-3 rounded-lg border border-amber-300/25 bg-amber-300/5 p-3 text-sm leading-6 text-amber-100">{info.note}</p>}
      <div className="mt-5 flex flex-wrap gap-2">
        {app.screens.slice(0, 3).map(screen => (
          <Link key={screen.key} href={`/apps/${app.slug}#${screen.key}`} className="rounded-lg border border-white/10 px-3 py-2.5 text-sm text-slate-200 hover:bg-white/10 focus-visible:outline-2 focus-visible:outline-[var(--app-accent)]">
            {screen.label}
          </Link>
        ))}
      </div>
      <Link href={`/apps/${app.slug}`} className="mt-auto pt-6 text-base font-semibold text-[var(--app-accent)] underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-[var(--app-accent)]">
        {info.start} <span aria-hidden="true">→</span>
      </Link>
      <p className="mt-2 text-sm text-slate-400">{app.requiresStaffLogin ? "Dealership staff sign-in" : "Customer & visitor experience"}</p>
    </article>
  );
}

export default function AppSuiteLauncher() {
  const theme = useAppTheme();
  const [query, setQuery] = useState("");
  const groups = [
    { title: "Dealership team", detail: "Choose the workspace for the work you do today.", slugs: ["reception", "salesapp", "serviceops"] },
    { title: "Your personal sales workspace", detail: "Your own contacts and follow-ups, separate from dealership staff access.", slugs: ["mysales"] },
    { title: "Customers & visitors", detail: "Availability is shown below. Staff workspaces are above.", slugs: ["showroom", "mygarage", "kiosk"] },
  ];
  const visible = APP_SUITE.filter(app => workspaceMatches(app, query));
  const showDealership = query.trim().toLowerCase().split(/\s+/).every(word => "dealership operations manager inventory finance marketing administration reporting tasks".includes(word));
  return (
    <div className="nxt-suite min-h-[100dvh] bg-[#091722] font-brand text-white" style={accentVars(theme)}>
      <BrandRibbon height={3} />
      <main className="mx-auto max-w-6xl px-5 py-8 md:px-8 md:py-12">
        <header className="border-b border-white/15 pb-8">
          <div className="w-48"><BrandLogo /></div>
          <p className="mt-5 text-sm font-medium text-[var(--app-accent)]">{theme.dealershipName} · App Suite</p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight md:text-4xl">Where are you working today?</h1>
          <p className="mt-3 max-w-2xl text-base leading-7 text-slate-300">Choose your role, then go straight to the task you need. Each workspace keeps its own sign-in and access rules.</p>
          <label htmlFor="workspace-search" className="mt-6 block text-sm font-medium text-slate-200">Find a workspace or task</label>
          <input id="workspace-search" type="search" value={query} onChange={event => setQuery(event.target.value)} placeholder="Try appointments, sales, repair orders…" className="mt-2 min-h-12 w-full max-w-xl rounded-lg border border-white/10 bg-white/5 px-4 text-base text-white placeholder:text-slate-400 focus-visible:outline-2 focus-visible:outline-[var(--app-accent)]" />
        </header>
        {visible.length === 0 && !showDealership && <div role="status" className="my-8 rounded-xl border border-white/20 p-6"><h2 className="text-lg font-semibold">No matching workspace</h2><p className="mt-2 text-slate-300">Try a role such as sales or reception, or clear your search.</p><button onClick={() => setQuery("")} className="mt-4 min-h-11 rounded-lg border border-[var(--app-accent)]/50 px-4 text-[var(--app-accent)]">Show all workspaces</button></div>}
        {showDealership && <section aria-label="Full dealership workspace" className="mt-8 rounded-2xl border border-white/15 bg-white/5 p-6">
          <p className="text-sm text-[var(--app-accent)]">Operations · Inventory · Finance · Marketing · Management</p>
          <h2 className="mt-2 text-xl font-semibold">Run your department</h2>
          <p className="mt-2 max-w-2xl text-base leading-7 text-slate-200">Open the full dealership workspace for department records, approvals, reporting and administration. Available tools depend on your staff role.</p>
          <Link href="/workspace" className="mt-4 inline-flex min-h-11 items-center rounded-full bg-[var(--app-accent)] px-4 font-semibold text-[var(--app-accent-text)] focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[var(--app-accent)]">Open dealership workspace →</Link>
        </section>}
        {groups.map(group => {
          const apps = group.slugs.map(slug => visible.find(app => app.slug === slug)).filter((app): app is AppDef => !!app);
          if (!apps.length) return null;
          return <section key={group.title} className="mt-9" aria-label={group.title}>
            <h2 className="text-xl font-semibold">{group.title}</h2>
            <p className="mt-1 text-sm text-slate-300">{group.detail}</p>
            <div className="mt-4 grid gap-4 md:grid-cols-2 lg:grid-cols-3">{apps.map(app => <WorkspaceCard key={app.slug} app={app} />)}</div>
          </section>;
        })}
        <footer className="mt-12 border-t border-white/15 py-6 text-sm text-slate-400">NXTDeal · Powered by Chrono</footer>
      </main>
    </div>
  );
}