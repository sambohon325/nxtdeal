"use client";

// Shared "Inventory" screen for Sales Pro & Sales — live lot off
// GET /menu/data?department=Inventory&item_key=inventory (core/inventory_menu.py), with a
// client-side search box that hits the same endpoint's query branch.

import { useState } from "react";
import { type AppDef, type AppScreen, accentOf } from "@/lib/apps/registry";
import {
  getInventorySummary,
  searchInventory,
  normalizeListItem,
  normalizeSearchHit,
  type InventorySummary,
  type InventorySearchResults,
} from "@/lib/inventoryWorkspace";
import { useAsync, WiredScreen, ListCard, EmptyNote } from "./kit";
import { VehicleRow } from "@/components/apps/VehicleCard";

export function InventoryScreen({ app, screen }: { app: AppDef; screen: AppScreen }) {
  const accent = accentOf(app);
  const [term, setTerm] = useState("");
  const [query, setQuery] = useState("");
  const [visibleCount, setVisibleCount] = useState(30);

  const summary = useAsync<InventorySummary>(() => getInventorySummary(), []);
  const search = useAsync<InventorySearchResults>(
    () => (query ? searchInventory(query) : Promise.resolve({ query: "", count: 0, results: [] })),
    [query],
  );

  const active = query ? search : summary;

  // One shared normalizer + card (Phase 3), now with real thumbnails (Phase 2).
  const vehicles = (summary.data?.vehicles ?? []).map(normalizeListItem);
  const results = query ? (search.data?.results ?? []).map(normalizeSearchHit) : [];

  return (
    <WiredScreen app={app} screen={screen} loading={active.loading} error={active.error} empty={!active.data} onRetry={active.reload}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          setQuery(term.trim());
          setVisibleCount(30);
          if (term.trim() === query && query) search.reload();
        }}
        className="flex gap-2"
      >
        <input
          aria-label="Search inventory"
          value={term}
          onChange={(e) => setTerm(e.target.value)}
          placeholder="Search make, model, VIN, stock #"
          className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white placeholder-zinc-500"
        />
        <button className={`${accent.bg} rounded-lg px-3 text-sm font-semibold text-white`}>Go</button>
      </form>

      {query ? (
        <ListCard title={`Results for “${query}”`} count={results.length}>
          {results.slice(0, visibleCount).map((v) => (
            <VehicleRow key={v.id} v={v} />
          ))}
          {results.length === 0 && !search.loading && <EmptyNote>No matches. Clear the search to see the lot.</EmptyNote>}
          <button onClick={() => { setTerm(""); setQuery(""); setVisibleCount(30); }} className="pt-1 text-[11px] text-zinc-400 underline">
            Clear search
          </button>
        </ListCard>
      ) : (
        <ListCard title="Unsold inventory" count={vehicles.length}>
          {vehicles.slice(0, visibleCount).map((v) => (
            <VehicleRow key={v.id} v={v} />
          ))}
          {vehicles.length === 0 && <EmptyNote>No unsold units on the lot right now.</EmptyNote>}
        </ListCard>
      )}
      {(query ? results.length : vehicles.length) > visibleCount && (
        <button type="button" onClick={() => setVisibleCount((count) => count + 30)} className="min-h-11 w-full rounded-lg border border-white/20 px-4 py-2 text-sm text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400">
          Show more vehicles ({Math.min(visibleCount, query ? results.length : vehicles.length)} of {query ? results.length : vehicles.length} shown)
        </button>
      )}
    </WiredScreen>
  );
}
