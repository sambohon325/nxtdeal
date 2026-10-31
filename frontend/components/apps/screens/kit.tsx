"use client";

// Shared kit for wired app screens (2026-07-24).
//
// The suite's screens started as static shells (AppScreenView). A "wired" screen fetches live
// NXTDeal data and renders it in the same mobile card language. Failed requests display an
// explicit unavailable state instead of replacing a working screen with a feature mockup.

import { useEffect, useState, type ReactNode } from "react";
import { type AppDef, type AppScreen, accentOf } from "@/lib/apps/registry";

// Minimal async state hook. Re-runs when `deps` change.
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[] = []): {
  loading: boolean;
  error: string | null;
  data: T | null;
  reload: () => void;
} {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<T | null>(null);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    fn()
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(e instanceof Error ? e.message : "Couldn't load."))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce]);

  return { loading, error, data, reload: () => setNonce((n) => n + 1) };
}

export function CustomerLoadError({ subject, onRetry }: { subject: string; onRetry: () => void }) {
  return (
    <div role="alert" className="rounded-xl border border-white/10 bg-white/[0.05] p-4 text-center">
      <p className="text-sm text-zinc-200">We couldn&apos;t load {subject}.</p>
      <p className="mt-1 text-xs text-zinc-400">Check your connection and try again. If this continues, contact the dealership.</p>
      <button type="button" onClick={onRetry} className="mt-3 min-h-11 rounded-lg border border-white/20 px-4 py-2 text-sm text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400">Try again</button>
    </div>
  );
}

// Standard wired-screen frame: heading, request state, then live children.
export function WiredScreen({
  app,
  screen,
  loading,
  error,
  children,
  empty,
  onRetry,
}: {
  app: AppDef;
  screen: AppScreen;
  loading: boolean;
  error: string | null;
  children: ReactNode;
  empty?: boolean;
  onRetry?: () => void;
}) {
  const accent = accentOf(app);

  if (loading) {
    return (
      <div className="space-y-4">
        <Header app={app} screen={screen} />
        <div className="flex items-center justify-center py-16">
          <div className={`h-6 w-6 animate-spin rounded-full border-2 border-white/15 ${accent.text} border-t-current`} />
        </div>
      </div>
    );
  }

  if (error || empty) {
    return (
      <div className="space-y-3">
        <Header app={app} screen={screen} />
        <div role={error ? "alert" : "status"} className="rounded-xl border border-white/10 bg-white/[0.05] p-4">
          <p className="text-sm text-zinc-200">
            {error ? "We couldn't load this screen's data." : "No data is available for this screen yet."}
          </p>
          <p className="mt-1 text-xs text-zinc-400">
            {error ? "Check your connection and sign-in, then try again." : "Nothing has been returned by the connected service."}
          </p>
          {onRetry && <button type="button" onClick={onRetry} className="mt-3 rounded-lg border border-white/20 px-3 py-2 text-sm text-white">Try again</button>}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <Header app={app} screen={screen} />
      {children}
    </div>
  );
}

function Header({ app, screen }: { app: AppDef; screen: AppScreen }) {
  return (
    <div>
      <h2 className="text-xl font-bold text-white">{screen.heading}</h2>
      <p className="mt-0.5 text-sm text-zinc-400">{screen.intro}</p>
    </div>
  );
}

// A grid of KPI stat tiles.
export function StatGrid({ app, stats }: { app: AppDef; stats: { label: string; value: ReactNode; hint?: string }[] }) {
  const accent = accentOf(app);
  return (
    <div className="grid grid-cols-2 gap-2.5 md:grid-cols-4">
      {stats.map((s) => (
        <div key={s.label} className="rounded-2xl border border-white/10 bg-white/[0.05] p-3 backdrop-blur-sm">
          <div className={`text-2xl font-bold ${accent.text}`}>{s.value}</div>
          <div className="mt-0.5 text-[11px] font-medium text-zinc-300">{s.label}</div>
          {s.hint && <div className="text-[10px] text-zinc-500">{s.hint}</div>}
        </div>
      ))}
    </div>
  );
}

// A titled card wrapping a list of rows.
export function ListCard({ title, count, children }: { title: string; count?: number; children: ReactNode }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.05] p-4 backdrop-blur-sm">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-white">{title}</h3>
        {typeof count === "number" && (
          <span className="rounded-full bg-white/10 px-2 py-0.5 text-[10px] font-medium text-zinc-300">{count}</span>
        )}
      </div>
      <div className="space-y-2">{children}</div>
    </div>
  );
}

// A single list row: primary text, optional secondary, optional right-aligned meta/badge.
export function Row({
  primary,
  secondary,
  meta,
  onClick,
}: {
  primary: ReactNode;
  secondary?: ReactNode;
  meta?: ReactNode;
  onClick?: () => void;
}) {
  return (
    <div
      onClick={onClick}
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={onClick ? (event) => {
        if (event.target === event.currentTarget && (event.key === "Enter" || event.key === " ")) {
          event.preventDefault();
          onClick();
        }
      } : undefined}
      className={`flex items-center justify-between gap-3 rounded-lg border border-white/5 px-3 py-2 ${
        onClick ? "cursor-pointer hover:bg-white/5 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white" : ""
      }`}
    >
      <div className="min-w-0">
        <div className="truncate text-sm text-zinc-100">{primary}</div>
        {secondary && <div className="truncate text-[11px] text-zinc-500">{secondary}</div>}
      </div>
      {meta && <div className="shrink-0 text-right text-[11px] text-zinc-400">{meta}</div>}
    </div>
  );
}

export function EmptyNote({ children }: { children: ReactNode }) {
  return <p className="px-1 py-2 text-xs text-zinc-500">{children}</p>;
}

export function Badge({ app, children }: { app: AppDef; children: ReactNode }) {
  const accent = accentOf(app);
  return (
    <span className={`${accent.soft} ${accent.softText} rounded-full px-2 py-0.5 text-[10px] font-medium`}>
      {children}
    </span>
  );
}
