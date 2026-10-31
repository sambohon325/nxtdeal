"use client";

import Link from "next/link";
import { type AppDef, type AppScreen } from "@/lib/apps/registry";

// An unwired screen must not look like a working queue or expose implementation names.
export function AppScreenView({ app, screen }: { app: AppDef; screen: AppScreen }) {
  return (
    <section className="space-y-4">
      <h2 className="text-2xl font-semibold text-white">{screen.heading}</h2>
      <div role="status" className="rounded-xl border border-white/20 bg-white/5 p-5">
        <h3 className="text-lg font-semibold text-white">This task is not available here yet</h3>
        <p className="mt-2 max-w-xl text-base leading-7 text-slate-300">
          {app.requiresStaffLogin
            ? "Use your dealership's existing process for this task. This screen does not contain live records or save changes."
            : "Please contact your dealership for help with this task. This screen does not submit a request."}
        </p>
        <Link href="/apps" className="mt-4 inline-flex min-h-11 items-center rounded-lg border border-white/10 px-4 text-sm text-[var(--app-accent)] focus-visible:outline-2 focus-visible:outline-sky-300">Choose another workspace</Link>
      </div>
    </section>
  );
}