"use client";

// VehicleShowroom — the tablet showroom browse (2026-07-24, Sam: the Showroom app is "a tablet
// optimized showroom style app... a receptionist can hand off to a customer that doesn't want to
// deal with a sales rep"). A big, glossy, responsive grid of the dealership's live inventory the
// customer can browse and search on their own. The interest action currently explains that
// online buying is unavailable. Runs on the dealership's logged-in tablet, so it reads live inventory
// through the authed inventory endpoint; reports unavailable data if there is no session.

import { useState } from "react";
import { type AppDef, type AppScreen } from "@/lib/apps/registry";
import {
  getInventorySummary,
  searchInventory,
  normalizeListItem,
  normalizeSearchHit,
  type InventorySummary,
  type InventorySearchResults,
  type NormalizedVehicle,
} from "@/lib/inventoryWorkspace";
import { useAsync, WiredScreen } from "./kit";
import { VehicleTile } from "@/components/apps/VehicleCard";
import { DigitalRetailFlow } from "@/components/DigitalRetailFlow";

export function VehicleShowroom({ app, screen }: { app: AppDef; screen: AppScreen }) {
  const [term, setTerm] = useState("");
  const [query, setQuery] = useState("");
  const [visibleCount, setVisibleCount] = useState(60);
  const [dealOpen, setDealOpen] = useState(false);
  const [picked, setPicked] = useState<NormalizedVehicle | null>(null);

  const summary = useAsync<InventorySummary>(() => getInventorySummary(), []);
  const search = useAsync<InventorySearchResults>(
    () => (query ? searchInventory(query) : Promise.resolve({ query: "", count: 0, results: [] })),
    [query],
  );

  const active = query ? search : summary;

  // One shared normalizer for both the default list and search hits (Phase 3).
  const vehicles: NormalizedVehicle[] = query
    ? (search.data?.results ?? []).map(normalizeSearchHit)
    : (summary.data?.vehicles ?? []).map(normalizeListItem);

  return (
    <WiredScreen app={app} screen={screen} loading={active.loading} error={active.error} empty={!active.data} onRetry={active.reload}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          setQuery(term.trim());
          setVisibleCount(60);
          if (term.trim() === query && query) search.reload();
        }}
        className="flex gap-2"
      >
        <input
          aria-label="Search vehicles"
          value={term}
          onChange={(e) => setTerm(e.target.value)}
          placeholder="Search make, model, price…"
          className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white placeholder-zinc-500 focus:border-[var(--app-accent)] focus:outline-none"
        />
        <button className="rounded-full bg-[var(--app-accent)] px-4 text-sm font-semibold text-[var(--app-accent-text)]">Search</button>
        {query && (
          <button type="button" onClick={() => { setTerm(""); setQuery(""); setVisibleCount(60); }} className="rounded-lg border border-white/10 px-3 text-sm text-zinc-400">
            Clear
          </button>
        )}
      </form>

      <div className="text-[11px] uppercase tracking-wide text-zinc-500">
        {query ? `Results for “${query}”` : "In stock now"} · {vehicles.length}
      </div>

      {vehicles.length === 0 ? (
        <p className="py-8 text-center text-sm text-zinc-500">No vehicles to show right now.</p>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {vehicles.slice(0, visibleCount).map((v) => (
            <VehicleTile key={v.id} v={v} cta="I'm interested" onClick={() => { setPicked(v); setDealOpen(true); }} />
          ))}
        </div>
      )}

      {vehicles.length > visibleCount && (
        <button type="button" onClick={() => setVisibleCount((count) => count + 60)} className="min-h-11 w-full rounded-lg border border-white/20 px-4 py-2 text-sm text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400">
          Show more vehicles ({visibleCount} of {vehicles.length} shown)
        </button>
      )}

      {/* Interest currently opens an availability notice; it does not create a deal. */}
      <DigitalRetailFlow open={dealOpen} onClose={() => { setDealOpen(false); setPicked(null); }} />
      {picked && dealOpen && (
        <div className="pointer-events-none fixed left-1/2 top-4 z-[60] -translate-x-1/2 rounded-full bg-black/70 px-4 py-1.5 text-xs text-white">
          Selected: {picked.title} · No deal has been created. Please contact the dealership.
        </div>
      )}
    </WiredScreen>
  );
}
