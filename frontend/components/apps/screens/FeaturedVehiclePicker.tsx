"use client";

import { useEffect, useState } from "react";
import { getInventorySummary, normalizeListItem, type NormalizedVehicle } from "@/lib/inventoryWorkspace";

export function FeaturedVehiclePicker({ selected, onChange, disabled }: {
  selected: string[]; onChange: (ids: string[]) => void; disabled: boolean;
}) {
  const [vehicles, setVehicles] = useState<NormalizedVehicle[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [retry, setRetry] = useState(0);
  const [query, setQuery] = useState("");
  useEffect(() => {
    let alive = true;
    setLoading(true); setError(false);
    getInventorySummary().then(data => { if (alive) setVehicles(data.vehicles.map(normalizeListItem)); })
      .catch(() => { if (alive) setError(true); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [retry]);
  const term = query.trim().toLowerCase();
  const matches = vehicles.filter(v => `${v.title} ${v.subtitle} ${v.vin || ""}`.toLowerCase().includes(term));
  return <fieldset disabled={disabled} className="space-y-3 rounded-lg border border-white/15 p-3">
    <legend className="px-1 text-sm">Featured vehicles ({selected.length}/24)</legend>
    <p className="text-xs text-zinc-400">Choose current inventory, then save your page. Sold or removed vehicles are omitted from the public page automatically.</p>
    {selected.length > 0 && <ul className="space-y-1">{selected.map(id => <li key={id} className="flex items-center justify-between gap-2 text-sm">
      <span>{vehicles.find(v => v.id === id)?.title || `Saved selection ${id}`}</span>
      <button type="button" aria-label={`Remove ${vehicles.find(v => v.id === id)?.title || id}`} onClick={() => onChange(selected.filter(value => value !== id))} className="text-[var(--app-accent)]">Remove</button>
    </li>)}</ul>}
    {loading ? <p role="status">Loading inventory…</p> : error ? <div><p role="alert">Inventory could not be loaded. Your saved selections are unchanged.</p><button type="button" onClick={() => setRetry(v => v + 1)} className="text-[var(--app-accent)]">Retry inventory</button></div> : <>
      <label className="block text-sm">Find featured vehicles<input value={query} onChange={e => setQuery(e.target.value)}            className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-white" /></label>
      <div className="max-h-64 space-y-2 overflow-y-auto">{matches.map(v => <label key={v.id} className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={selected.includes(v.id)} disabled={!selected.includes(v.id) && selected.length >= 24}
          onChange={e => onChange(e.target.checked ? [...new Set([...selected, v.id])].slice(0, 24) : selected.filter(id => id !== v.id))} />
        <span>{v.title} · {v.subtitle || v.id}</span>
      </label>)}</div>
      {!matches.length && <p role="status">No matching unsold vehicles.</p>}
    </>}
  </fieldset>;
}
