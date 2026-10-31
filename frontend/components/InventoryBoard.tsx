"use client";
import { WorkInput, WorkButton , WorkStat, WorkOverlay} from "./WorkspaceUi";
import {CollectionPagination} from "./CollectionPagination";
import {RecordCollection} from "./RecordCollection";
import {RecordTable} from "./RecordTable";
import { WorkField } from "./WorkField";

// Sales' "Inventory" item (session 99 follow-up) -- the last of Sam's original
// 8 Sales submenus. A sales-facing vehicle browser/locator (not an inventory
// management view -- that's the Inventory department's own Dash), real
// payment-based search (an honest ESTIMATE, not a credit-approved quote), a real
// Reservation/Hold mechanism so two reps don't both walk a customer up to the same
// unsold car, and a side-by-side Comparison Tool (2-4 vehicles).
import { PRODUCT_ACCENT_COLORS } from "@/lib/productTheme";
import { useEffect, useState } from "react";
import {
  getInventory,
  placeHold,
  releaseHold,
  listActiveHolds,
  compareVehicles,
  type InventoryResult,
  type VehicleBrief,
  type CompareResult,
} from "@/lib/inventorySales";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const RIBBON = PRODUCT_ACCENT_COLORS;

function fmtMoney(v: number | string | null | undefined): string {
  const n = typeof v === "string" ? parseFloat(v) : v;
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return `$${n.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

function fmtDate(ts: string | null | undefined): string {
  if (!ts) return "—";
  try {
    return new Date(ts).toLocaleString();
  } catch {
    return ts;
  }
}

function isBrowse(r: InventoryResult): r is Extract<InventoryResult, { available_count: number }> {
  return "available_count" in r;
}

function Kpi({ theme, label, value, color }: { theme: Theme; label: string; value: number | string; color: string }) { return <WorkStat label={label} value={value}/>; }

function VehicleCard({
  theme,
  v,
  selected,
  onToggleSelect,
  onPlaceHold,
  onReleaseHold,
  busy,
  onPrepare,
}: {
  theme: Theme;
  v: VehicleBrief;
  selected: boolean;
  onToggleSelect: () => void;
  onPlaceHold: () => void;
  onReleaseHold: () => void;
  busy: boolean;
  onPrepare?:()=>void;
}) {
  return (
    <div
      className={tc(
        theme,
        `rounded-lg border p-2.5 ${selected ? "border-brand-blue bg-brand-blue/10" : "border-black/20 bg-brand-charcoal"}`,
        `rounded-lg border p-2.5 ${selected ? "border-brand-blue bg-brand-blue/10" : "border-zinc-200 bg-zinc-50"}`
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <label className="flex items-start gap-2 min-w-0 cursor-pointer">
          <WorkInput type="checkbox" checked={selected} onChange={onToggleSelect} className="mt-0.5" />
          <div className="min-w-0">
            <div className="text-xs font-medium truncate">
              {v.year} {v.make} {v.model} {v.trim || ""}
            </div>
            <div className="text-xs text-zinc-500 mt-0.5">{v.vin}</div>
          </div>
        </label>
        <div className="text-xs font-semibold shrink-0">{fmtMoney(v.price)}</div>
      </div>

      <div className="flex items-center justify-between gap-2 mt-2">
        {v.on_hold ? (
          <span className="text-xs px-2 py-0.5 rounded-md bg-amber-950/40 border border-amber-900 text-amber-300">
            On hold · {v.held_by} · until {fmtDate(v.hold_expires_at)}
          </span>
        ) : (
          <span className="text-xs text-zinc-600">Available</span>
        )}

        {v.on_hold ? (
          <WorkButton type="submit"
            onClick={onReleaseHold}
            disabled={busy}
            className="text-xs px-2 py-1 rounded-md bg-zinc-200 text-black font-medium transition disabled:opacity-50"
          >
            Release
          </WorkButton>
        ) : (
          <WorkButton type="submit"
            onClick={onPlaceHold}
            disabled={busy}
            className="text-xs px-2 py-1 rounded-md bg-zinc-200 text-black font-medium transition disabled:opacity-50"
          >
            Place Hold
          </WorkButton>
        )}
      </div>
      {onPrepare&&<WorkButton type="submit" className="mt-3 w-full rounded border border-blue-400/40 p-2 text-sm" onClick={onPrepare}>Prepare a deal with this vehicle →</WorkButton>}
    </div>
  );
}

function CompareModal({ theme, result, onClose, inline = false }: { theme: Theme; result: CompareResult; onClose: () => void; inline?:boolean }) {
  const fields = ["Year", "Make", "Model", "Trim", "VIN", "Price", "Mileage", "Color"];

  return (
    <WorkOverlay data-department-work="" className={inline ? "workspace-inline-editor" : "fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-6"} onClick={inline ? undefined : onClose}>
      <div
        className={inline ? "workspace-editor-surface p-5 overflow-x-auto" : tc(theme, "w-full max-w-4xl max-h-[85vh] overflow-y-auto rounded-xl border border-zinc-800 bg-brand-ink p-5", "w-full max-w-4xl max-h-[85vh] overflow-y-auto rounded-xl border border-zinc-200 bg-white p-5")}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-3">
          <div className="text-sm font-brand uppercase tracking-wide">Vehicle Comparison</div>
          <WorkButton type="submit" onClick={onClose} className="text-xs px-2.5 py-1 rounded-md bg-zinc-200 text-black font-medium transition">
            Close
          </WorkButton>
        </div>

        {result.errors.length > 0 && (
          <div className="text-xs text-red-400 mb-2">
            {result.errors.map((e) => `${e.id}: ${e.error}`).join(" · ")}
          </div>
        )}

        <div className="overflow-x-auto">
          <RecordTable className="w-full text-xs border-collapse">
            <thead>
              <tr>
                <th className="text-left p-2 text-zinc-500 font-medium">Field</th>
                {result.vehicles.map((v) => (
                  <th key={v.id} className="text-left p-2 font-medium">
                    {v.id}
                    {v.on_hold && <div className="text-xs text-amber-400 font-normal">On hold · {v.held_by}</div>}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {fields.map((f) => (
                <tr key={f} className={tc(theme, "border-t border-zinc-800", "border-t border-zinc-200")}>
                  <td className="p-2 text-zinc-500">{f}</td>
                  {result.vehicles.map((v) => (
                    <td key={v.id} className="p-2">
                      {f === "Price" ? fmtMoney(v.attributes[f] as number) : String(v.attributes[f] ?? "—")}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </RecordTable>
        </div>
      </div>
    </WorkOverlay>
  );
}

export function InventoryBoard({ theme, onPrepare, inline = false }: { theme: Theme; inline?:boolean; onPrepare?:(vehicle:VehicleBrief)=>void }) {
  const [page,setPage]=useState(0);
  const [result, setResult] = useState<InventoryResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [compareResult, setCompareResult] = useState<CompareResult | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function refresh(query?: string) {
    setLoading(true);
    getInventory(query)
      .then((r) => {
        setResult(r);
        setError(null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load inventory"))
      .finally(() => setLoading(false));
  }

  useEffect(() => refresh(), []);

  function vehiclesFromResult(r: InventoryResult | null): VehicleBrief[] {
    if (!r) return [];
    if ("vehicles" in r) return r.vehicles as VehicleBrief[];
    return [];
  }

  const vehicles = vehiclesFromResult(result);
  useEffect(()=>setPage(0),[result]);
  const pages=Math.max(1,Math.ceil(vehicles.length/25));const current=Math.min(page,pages-1);

  function toggleSelect(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        if (next.size >= 4) return prev;
        next.add(id);
      }
      return next;
    });
  }

  async function handlePlaceHold(vehicleId: string) {
    setBusyId(vehicleId);
    try {
      await placeHold({ vehicle_id: vehicleId, duration_hours: 24 });
      refresh(search);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to place hold");
    } finally {
      setBusyId(null);
    }
  }

  async function handleReleaseHold(vehicleId: string) {
    const held = vehicles.find((v) => v.id === vehicleId);
    setBusyId(vehicleId);
    try {
      // A vehicle brief carries hold status but not the hold's own id (it's a
      // separate entity) -- releasing means finding that vehicle's current active
      // hold record first.
      const active = await listActiveHolds();
      const match = active.find((h) => h.vehicle_id === vehicleId && h.status === "active");
      if (match) {
        await releaseHold(match.id);
        refresh(search);
      } else if (held) {
        setError("Could not find the active hold record for this vehicle.");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to release hold");
    } finally {
      setBusyId(null);
    }
  }

  async function handleCompare() {
    if (selected.size < 2) return;
    try {
      const r = await compareVehicles(Array.from(selected));
      setCompareResult(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to compare vehicles");
    }
  }

  const onHoldCount = vehicles.filter((v) => v.on_hold).length;
  const recentlySold = result && isBrowse(result) ? result.recently_sold : [];
  const availableCount = result && isBrowse(result) ? result.available_count : vehicles.length;

  if(inline && compareResult)return <CompareModal inline theme={theme} result={compareResult} onClose={()=>setCompareResult(null)}/>;
  return (
    <div className={tc(theme, "flex-1 flex flex-col min-h-0 bg-brand-ink text-white", "flex-1 flex flex-col min-h-0 bg-white text-black")}>
      <div className={tc(theme, "grid grid-cols-4 gap-3 p-4 border-b border-zinc-800", "grid grid-cols-4 gap-3 p-4 border-b border-zinc-200")}>
        <Kpi theme={theme} label="Available" value={availableCount} color={RIBBON[0]} />
        <Kpi theme={theme} label="On Hold" value={onHoldCount} color={RIBBON[1]} />
        <Kpi theme={theme} label="Recently Sold" value={recentlySold.length} color={RIBBON[2]} />
        <Kpi theme={theme} label="Selected to Compare" value={selected.size} color={RIBBON[3]} />
      </div>

      <div className={tc(theme, "border-b border-zinc-800 px-4 py-2.5 flex items-center gap-2", "border-b border-zinc-200 px-4 py-2.5 flex items-center gap-2")}>
        <WorkField label="Search make/model, or type a target monthly payment"><WorkInput
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && refresh(search)}
          placeholder="Search make/model, or type a target monthly payment (e.g. 400)"
          className={tc(
            theme,
            "flex-1 text-xs rounded-md border border-zinc-700 bg-brand-charcoal px-2.5 py-1.5 text-white placeholder:text-zinc-600",
            "flex-1 text-xs rounded-md border border-zinc-300 bg-white px-2.5 py-1.5 text-black placeholder:text-zinc-400"
          )}
        /></WorkField>
        <WorkButton type="submit" onClick={() => refresh(search)} className="text-xs px-3 py-1.5 rounded-md bg-zinc-200 text-black font-medium transition">
          Search
        </WorkButton>
        {search && (
          <WorkButton type="submit"
            onClick={() => {
              setSearch("");
              refresh();
            }}
            className={tc(theme, "text-xs px-2.5 py-1.5 rounded-md text-zinc-400 hover:text-white transition", "text-xs px-2.5 py-1.5 rounded-md text-zinc-500 hover:text-black transition")}
          >
            Clear
          </WorkButton>
        )}
        {selected.size >= 2 && (
          <WorkButton type="submit" variant="primary" onClick={handleCompare} className="text-xs px-3 py-1.5 rounded-md bg-brand-blue text-white font-medium transition">
            Compare ({selected.size})
          </WorkButton>
        )}
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {error && <div className="text-xs text-red-400">{error}</div>}

        {result && !isBrowse(result) && "note" in result && (
          <div className={tc(theme, "text-xs text-zinc-400 rounded-md border border-zinc-800 bg-brand-charcoal p-2.5", "text-xs text-zinc-500 rounded-md border border-zinc-200 bg-zinc-50 p-2.5")}>
            {result.mode === "payment_based_search"
              ? `Est. max price ${fmtMoney(result.estimated_max_price)} at $${result.target_monthly_payment}/mo (${result.assumptions.term_months}mo, ${(result.assumptions.apr * 100).toFixed(1)}% APR). ${result.note}`
              : null}
          </div>
        )}

        {loading ? (
          <div className="text-sm text-zinc-500">Loading…</div>
        ) : vehicles.length === 0 ? (
          <div className="text-xs text-zinc-600">No matching vehicles.</div>
        ) : (
          <div className="grid grid-cols-2 gap-2">
            {vehicles.slice(current*25,current*25+25).map((v) => (
              <VehicleCard
                key={v.id}
                theme={theme}
                v={v}
                selected={selected.has(v.id)}
                onToggleSelect={() => toggleSelect(v.id)}
                onPlaceHold={() => handlePlaceHold(v.id)}
                onReleaseHold={() => handleReleaseHold(v.id)}
                onPrepare={onPrepare ? ()=>onPrepare(v) : undefined}
                busy={busyId === v.id}
              />
            ))}
          </div>
        )}

        <CollectionPagination label="Vehicles" total={vehicles.length} page={current} pageSize={25} onPageChange={setPage} busy={loading}/>
        {recentlySold.length > 0 && (
          <div>
            <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1.5">Recently Sold</div>
            <div className="grid grid-cols-3 gap-2">
              <RecordCollection>{recentlySold.map((v) => (
                <div key={v.id} className={tc(theme, "rounded-lg border border-black/20 bg-brand-charcoal p-2 text-xs", "rounded-lg border border-zinc-200 bg-zinc-50 p-2 text-xs")}>
                  <div className="font-medium">{v.vin}</div>
                  <div className="text-zinc-500">{fmtDate(v.date_sold)}</div>
                </div>
              ))}</RecordCollection>
            </div>
          </div>
        )}
      </div>

      {compareResult && <CompareModal theme={theme} result={compareResult} onClose={() => setCompareResult(null)} />}
    </div>
  );
}
