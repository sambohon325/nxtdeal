"use client";
import Link from "next/link";
import { type AppDef, type AppScreen, accentOf } from "@/lib/apps/registry";
import { AppIcon } from "../AppIcon";

// Historical screen entry retained for existing clients. Connections belong to
// the independent MySales account, never to this tenant staff session.
export function MySalesAiConfig({ app }: { app: AppDef; screen: AppScreen }) {
  const accent = accentOf(app);
  return (
    <section className="space-y-4 rounded-2xl border border-white/10 bg-white/[0.05] p-5 backdrop-blur-sm">
      <AppIcon name="settings" tile={false} className={`h-7 w-7 ${accent.text}`} />
      <h2 className="text-xl text-white">AI Setup</h2>
      <p className="text-sm text-slate-300">
        Connect an assistant to your personal MySales account. Review its
        permissions, see activity and disconnect whenever you choose.
      </p>
      <p className="text-sm text-slate-400">
        A saved provider key hint is not a live connection. No API key is needed
        here, and your dealership staff session is not shared.
      </p>
      <Link
        className={`inline-block rounded-full ${accent.bg} px-5 py-2.5 text-sm font-semibold text-[var(--app-accent-text)]`}
        href="/apps/mysales#coach"
      >
        Open Conversations AI →
      </Link>
    </section>
  );
}
