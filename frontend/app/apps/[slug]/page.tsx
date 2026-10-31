"use client";

// Dynamic app route — mounts any NXTDeal suite app by slug (2026-07-24).
//
// hub.dealeros.xyz/<slug> resolves here. The whole suite is driven off the registry, so this one
// route renders all seven apps: it resolves the app, gates staff apps behind the dealership
// login, and swaps screens from the bottom tab bar. Uses useParams (not the async params prop)
// since this is a client component that owns tab + auth state.

import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { getApp, getDevApp } from "@/lib/apps/registry";
import { getAppSession, appSignOut, subscribeAppSessionChange } from "@/lib/appAuth";
import { AppShell } from "@/components/apps/AppShell";
import { AppLogin } from "@/components/apps/AppLogin";
import { AppScreenView } from "@/components/apps/AppScreenView";
import { wiredScreen } from "@/components/apps/screens";
import { LockedModuleScreen } from "@/components/apps/screens/LockedModuleScreen";
import { getPublicEntitlements, requiredModuleFor, screenAllowed, type PublicEntitlements } from "@/lib/entitlements";

export default function AppPage() {
  const params = useParams<{ slug: string }>();
  const slug = Array.isArray(params.slug) ? params.slug[0] : params.slug;
  return <StaffAppPage />;
}

function StaffAppPage() {
  const params = useParams<{ slug: string }>();
  const router = useRouter();
  const slug = Array.isArray(params.slug) ? params.slug[0] : params.slug;
  const app = useMemo(() => (slug ? (getApp(slug) || getDevApp(slug)) : undefined), [slug]);

  const [activeTab, setActiveTab] = useState<string>("");
  const [authed, setAuthed] = useState<boolean | null>(null); // null = still resolving
  const [entitlements, setEntitlements] = useState<PublicEntitlements | null>(null);

  useEffect(() => {
    let invalidated = false;
    return subscribeAppSessionChange(() => {
      if (invalidated) return;
      invalidated = true;
      setAuthed(null);
      window.location.reload();
    });
  }, []);

  // Resolve the dealer's active Modules once (shared across every tab) so the suite can gate
  // screens whose paid Module isn't active. Fails open in the UI; the backend is the real gate.
  useEffect(() => {
    getPublicEntitlements().then(setEntitlements).catch(() => setEntitlements(null));
  }, []);

  // Tasks are bookmarkable; Back/Forward restores the task within this workspace.
  useEffect(() => {
    if (!app) return;
    const restoreTask = () => {
      const key = window.location.hash.slice(1);
      setActiveTab(app.screens.some(screen => screen.key === key) ? key : app.screens[0]?.key ?? "");
    };
    restoreTask();
    window.addEventListener("hashchange", restoreTask);
    return () => window.removeEventListener("hashchange", restoreTask);
  }, [app]);

  // Resolve auth on mount (client-only — localStorage).
  useEffect(() => {
    if (!app) return;
    if (!app.requiresStaffLogin) {
      setAuthed(true);
      return;
    }
    setAuthed(!!getAppSession());
  }, [app]);

  // Phase 6: a rep opening MySales pings the adoption signal (fire-and-forget), so the
  // Hub/Readiness function can detect rep-level buy-in as a dealership conversion signal.
  useEffect(() => {
    if (app?.slug === "mysales" && authed) {
      import("@/lib/mysalesAdoption").then((m) => m.recordMySalesActivity("open")).catch(() => {});
    }
  }, [app?.slug, authed]);

  if (!app) {
    return (
      <div className="flex min-h-screen w-full items-center justify-center bg-[#0b0b0d] p-6 text-center font-brand text-white">
        <div>
          <p className="text-sm text-zinc-400">No app found for “{slug}”.</p>
          <Link href="/apps" className="mt-3 inline-block text-sm font-medium text-[var(--app-accent)]">
            ‹ Back to all apps
          </Link>
        </div>
      </div>
    );
  }

  if (authed === null) {
    return <div role="status" className="flex min-h-screen items-center justify-center bg-[#0b0b0d] p-6 text-slate-200">Opening your workspace…</div>;
  }

  if (!authed) {
    return <AppLogin app={app} onSignedIn={() => setAuthed(true)} />;
  }

  const screen = app.screens.find((s) => s.key === activeTab) ?? app.screens[0];
  const Wired = wiredScreen(app.slug, screen.key);
  const requiredModule = requiredModuleFor(app.slug, screen.key);
  const gated = requiredModule && !screenAllowed(entitlements, requiredModule);

  return (
    <AppShell
      app={app}
      activeTab={screen.key}
      onTabChange={(key) => { setActiveTab(key); window.location.hash = key; }}
      onSignOut={
        app.requiresStaffLogin
          ? () => {
              appSignOut();
              setAuthed(false);
            }
          : undefined
      }
    >
      {gated ? (
        <LockedModuleScreen app={app} screen={screen} requiredModule={requiredModule!} />
      ) : Wired ? (
        <Wired app={app} screen={screen} />
      ) : (
        <AppScreenView app={app} screen={screen} />
      )}
    </AppShell>
  );
}
