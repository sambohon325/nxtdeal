"use client";

// Shared vehicle card for every app inventory surface (App Suite roadmap Phase 2 + 3).
// One component renders the real primary photo (with a clean branded placeholder when a
// vehicle has none on file) in either a grid tile or a list row. Consolidating the card +
// the photo handling here means a single fix — like closing the photo gap — propagates to
// Showroom, My Garage, MySales, and Sales at once instead of three copies drifting apart.

import { type NormalizedVehicle } from "@/lib/inventoryWorkspace";

function money(v: number | null): string {
  return v === null ? "Call for price" : `$${Math.round(v).toLocaleString()}`;
}

function Photo({ url, className }: { url: string | null; className: string }) {
  if (url) {
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={url} alt="" className={`${className} object-cover`} />;
  }
  return (
    <div className={`${className} flex items-center justify-center bg-gradient-to-br from-white/[0.08] to-white/[0.02]`}>
      <svg viewBox="0 0 24 24" className="h-8 w-8 text-white/25" fill="none" stroke="currentColor" strokeWidth="1.5">
        <path d="M3 13l2-5a2 2 0 0 1 1.9-1.3h10.2A2 2 0 0 1 19 8l2 5m-18 0v4m18-4v4M3 13h18M6 17h.01M18 17h.01" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </div>
  );
}

// Grid tile — used by the Showroom / My Garage browse grid.
export function VehicleTile({ v, onClick, cta }: { v: NormalizedVehicle; onClick?: () => void; cta?: string }) {
  const Container = onClick ? "button" : "div";
  return (
    <Container
      onClick={onClick}
      className="group flex flex-col overflow-hidden rounded-2xl border border-white/10 bg-white/[0.05] text-left backdrop-blur-sm"
    >
      <Photo url={v.photoUrl} className="h-28 w-full" />
      <div className="p-3">
        <div className="truncate text-sm font-semibold text-white">{v.title}</div>
        {v.subtitle && <div className="truncate text-[11px] text-zinc-500">{v.subtitle}</div>}
        <div className="mt-1 flex items-center justify-between">
          <span className="text-sm font-bold text-white">{money(v.price)}</span>
          {cta && onClick && <span className="text-[11px] text-zinc-400 group-hover:text-white">{cta} →</span>}
        </div>
      </div>
    </Container>
  );
}

// List row with a thumbnail — used by the MySales / Sales inventory list.
export function VehicleRow({ v, onClick }: { v: NormalizedVehicle; onClick?: () => void }) {
  const Container = onClick ? "button" : "div";
  return (
    <Container
      onClick={onClick}
      className={`flex w-full items-center gap-3 rounded-lg border border-white/5 px-2 py-2 text-left ${onClick ? "hover:bg-white/5" : ""}`}
    >
      <Photo url={v.photoUrl} className="h-12 w-16 shrink-0 rounded-md" />
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm text-zinc-100">{v.title}</div>
        {v.subtitle && <div className="truncate text-[11px] text-zinc-500">{v.subtitle}</div>}
      </div>
      <div className="shrink-0 text-sm font-semibold text-white">{money(v.price)}</div>
    </Container>
  );
}
