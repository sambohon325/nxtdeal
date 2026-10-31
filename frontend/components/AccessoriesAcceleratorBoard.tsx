"use client";
import { WorkButton, WorkInput , WorkStat} from "./WorkspaceUi";
import { WorkField } from "./WorkField";

// Accessories Accelerator board -- a staff-facing visualizer + control surface
// over core/accessories.py's graph-native accessory upsell motion (Vehicle Sold
// -> Recommend -> Install -> Track Revenue), stored directly as attributes on
// the Customer entity. Three sections: program overview KPIs (estimated attach
// rate, total revenue, revenue-by-category, installed vs pending), the fixed
// accessory catalog grouped by category, and a per-customer panel that pulls
// rule-based recommendations, records a sale from selected items, marks it
// installed, and drafts an AI upsell pitch (with an honest disabled/fallback
// path). Read/act through lib/accessories.ts -- same shape and styling
// vocabulary as OperationsCustomerJourneyBoard.tsx (RIBBON palette, theme-aware
// classes).
import { PRODUCT_ACCENT_COLORS } from "@/lib/productTheme";
import { useEffect, useMemo, useState } from "react";
import {
  getCatalog,
  getAccessoriesOverview,
  getRecommendations,
  createSale,
  markInstalled,
  generatePitch,
  ACCESSORY_CATEGORIES,
  type CatalogItem,
  type AccessoriesCatalog,
  type AccessoriesOverview,
  type Recommendation,
  type AccessorySale,
  type AccessoryPitch,
} from "@/lib/accessories";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const RIBBON = PRODUCT_ACCENT_COLORS;

// A readable Title-Case label + a ribbon-derived accent color per category.
// Colors cycle the RIBBON palette so the board reads as one branded system.
const CATEGORY_LABEL: Record<string, string> = {
  truck_accessories: "Truck Accessories",
  protection_packages: "Protection Packages",
  oem_accessories: "OEM Accessories",
  lift_kits: "Lift Kits",
  wheels: "Wheels",
  tint: "Tint",
};

const CATEGORY_COLOR: Record<string, string> = {
  truck_accessories: RIBBON[0],
  protection_packages: RIBBON[1],
  oem_accessories: RIBBON[2],
  lift_kits: RIBBON[3],
  wheels: RIBBON[0],
  tint: RIBBON[1],
};

function categoryLabel(category: string | null | undefined): string {
  if (!category) return "—";
  return CATEGORY_LABEL[category] ?? category;
}

function money(value: number | null | undefined): string {
  const n = typeof value === "number" ? value : 0;
  return n.toLocaleString([], { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function pct(value: number | null | undefined): string {
  const n = typeof value === "number" ? value : 0;
  return `${(n * 100).toFixed(1)}%`;
}

function fmt(ts: string | null | undefined): string {
  if (!ts) return "—";
  try {
    return new Date(ts).toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  } catch {
    return ts;
  }
}

function Kpi({ theme, label, value, color }: { theme: Theme; label: string; value: string; color: string }) { return <WorkStat label={label} value={value}/>; }

// One horizontal revenue-by-category bar, scaled against the busiest category so
// the mix reads at a glance -- the "accelerator" idea from the slice brief.
function CategoryRevenueBar({
  theme,
  category,
  revenue,
  maxRevenue,
}: {
  theme: Theme;
  category: string;
  revenue: number;
  maxRevenue: number;
}) {
  const color = CATEGORY_COLOR[category] ?? RIBBON[0];
  const share = maxRevenue > 0 ? revenue / maxRevenue : 0;
  return (
    <div className="flex items-center gap-2">
      <div className="w-32 text-xs font-brand uppercase tracking-wide text-zinc-500 truncate">{CATEGORY_LABEL[category] ?? category}</div>
      <div className={tc(theme, "flex-1 h-4 rounded bg-black/30 overflow-hidden", "flex-1 h-4 rounded bg-zinc-200 overflow-hidden")}>
        <div className="h-full rounded" style={{ width: `${Math.max(share * 100, revenue > 0 ? 4 : 0)}%`, background: color }} />
      </div>
      <div className="w-24 text-right text-xs text-zinc-400 tabular-nums">{money(revenue)}</div>
    </div>
  );
}

function PitchCard({ theme, pitch }: { theme: Theme; pitch: AccessoryPitch }) {
  return (
    <div className={tc(theme, "rounded-md border border-zinc-700 bg-black/20 p-3", "rounded-md border border-zinc-300 bg-white p-3")}>
      <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1">
        🤖 AI Pitch {pitch.ai_generated ? "" : pitch.disabled ? "(disabled — fallback)" : "(fallback)"}
      </div>
      <div className="text-sm text-zinc-200">{pitch.pitch || "—"}</div>
      {pitch.highlighted_items.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mt-2">
          {pitch.highlighted_items.map((item, i) => (
            <span
              key={i}
              className={tc(theme, "text-xs px-2 py-0.5 rounded-full bg-zinc-200/10 text-zinc-300", "text-xs px-2 py-0.5 rounded-full bg-zinc-200 text-zinc-700")}
            >
              {item}
            </span>
          ))}
        </div>
      )}
      {pitch.suggested_bundle_note && (
        <div className="text-xs text-zinc-400 mt-2">
          <span className="font-brand uppercase tracking-wide text-zinc-600 mr-1">Bundle</span>
          {pitch.suggested_bundle_note}
        </div>
      )}
      {pitch.fallback_reason && (
        <div className="text-xs text-zinc-600 mt-2 italic">Fallback reason: {pitch.fallback_reason}</div>
      )}
    </div>
  );
}

export function AccessoriesAcceleratorBoard({ theme }: { theme: Theme }) {
  const [overview, setOverview] = useState<AccessoriesOverview | null>(null);
  const [catalog, setCatalog] = useState<AccessoriesCatalog | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Per-customer panel state -- distinct from the overview/catalog above.
  const [lookupId, setLookupId] = useState("");
  const [rec, setRec] = useState<Recommendation | null>(null);
  const [recLoading, setRecLoading] = useState(false);
  const [customerError, setCustomerError] = useState<string | null>(null);

  // Items the user has ticked to build a sale from (item ids).
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [saleBusy, setSaleBusy] = useState(false);
  const [sale, setSale] = useState<AccessorySale | null>(null);

  const [pitch, setPitch] = useState<AccessoryPitch | null>(null);
  const [pitchBusy, setPitchBusy] = useState(false);

  function refresh() {
    setLoading(true);
    setError(null);
    Promise.all([getAccessoriesOverview(), getCatalog()])
      .then(([ov, cat]) => {
        setOverview(ov);
        setCatalog(cat);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Unable to load the Accessories Accelerator overview."))
      .finally(() => setLoading(false));
  }

  useEffect(refresh, []);

  // Catalog items grouped by category, in the load-bearing CATEGORIES order.
  const catalogByCategory = useMemo(() => {
    const groups: Record<string, CatalogItem[]> = {};
    const items = catalog?.items ?? [];
    for (const item of items) {
      const list = groups[item.category] ?? [];
      list.push(item);
      groups[item.category] = list;
    }
    return groups;
  }, [catalog]);

  const maxCategoryRevenue = useMemo(() => {
    const byCat = overview?.revenue_by_category ?? {};
    return ACCESSORY_CATEGORIES.map((c) => byCat[c] ?? 0).reduce((a, b) => Math.max(a, b), 0);
  }, [overview]);

  const selectedIds = useMemo(() => Object.keys(selected).filter((id) => selected[id]), [selected]);

  function toggleSelected(itemId: string) {
    setSelected((prev) => ({ ...prev, [itemId]: !prev[itemId] }));
  }

  function loadRecommendations(customerId: string) {
    const id = customerId.trim();
    if (!id) {
      setCustomerError("Enter a customer id to look up.");
      return;
    }
    setRecLoading(true);
    setCustomerError(null);
    setSale(null);
    setPitch(null);
    getRecommendations(id)
      .then(setRec)
      .catch((e) => {
        setRec(null);
        setCustomerError(e instanceof Error ? e.message : "Unable to load recommendations for this customer.");
      })
      .finally(() => setRecLoading(false));
  }

  async function handleCreateSale() {
    const id = lookupId.trim();
    if (!id) {
      setCustomerError("Enter a customer id first.");
      return;
    }
    if (selectedIds.length === 0) {
      setCustomerError("Select at least one accessory to record a sale.");
      return;
    }
    setSaleBusy(true);
    setCustomerError(null);
    try {
      const created = await createSale(id, selectedIds);
      setSale(created);
      setSelected({});
      refresh();
    } catch (e) {
      setCustomerError(e instanceof Error ? e.message : "Unable to record this accessory sale.");
    } finally {
      setSaleBusy(false);
    }
  }

  async function handleMarkInstalled() {
    if (!sale) return;
    setSaleBusy(true);
    setCustomerError(null);
    try {
      const updated = await markInstalled(sale.customer_id, sale.sale_id);
      setSale(updated);
      refresh();
    } catch (e) {
      setCustomerError(e instanceof Error ? e.message : "Unable to mark this sale installed.");
    } finally {
      setSaleBusy(false);
    }
  }

  async function handlePitch() {
    const id = lookupId.trim();
    if (!id) {
      setCustomerError("Enter a customer id first.");
      return;
    }
    setPitchBusy(true);
    setCustomerError(null);
    try {
      const result = await generatePitch(id);
      setPitch(result);
    } catch (e) {
      setCustomerError(e instanceof Error ? e.message : "Unable to generate an accessory pitch.");
    } finally {
      setPitchBusy(false);
    }
  }

  const byCat = overview?.revenue_by_category ?? {};

  return (
    <div className={tc(theme, "flex-1 flex flex-col min-h-0 bg-brand-ink text-white overflow-y-auto", "flex-1 flex flex-col min-h-0 bg-white text-black overflow-y-auto")}>
      {/* Program overview */}
      <div className={tc(theme, "p-4 border-b border-zinc-800", "p-4 border-b border-zinc-200")}>
        <div className="flex items-center justify-between gap-2">
          <div className="text-sm font-brand uppercase tracking-wide text-zinc-400">🚀 Accessories Accelerator</div>
          <WorkButton type="submit" onClick={refresh} className="text-xs px-2.5 py-1 rounded-full bg-zinc-200/10 text-zinc-400 hover:text-white">
            ↻ Refresh
          </WorkButton>
        </div>
        {loading && <div className="text-sm text-zinc-500 mt-2">Loading…</div>}
        {error && <div className="text-sm text-red-400 mt-2">{error}</div>}
      </div>

      {/* Overview KPIs */}
      <div className={tc(theme, "grid grid-cols-4 gap-3 p-4 border-b border-zinc-800", "grid grid-cols-4 gap-3 p-4 border-b border-zinc-200")}>
        <Kpi theme={theme} label="Est. Attach Rate" value={pct(overview?.attach_rate_estimate)} color={RIBBON[0]} />
        <Kpi theme={theme} label="Total Revenue" value={money(overview?.total_accessory_revenue)} color={RIBBON[1]} />
        <Kpi theme={theme} label="Installed" value={String(overview?.installed_count ?? 0)} color={RIBBON[2]} />
        <Kpi theme={theme} label="Pending Install" value={String(overview?.pending_count ?? 0)} color={RIBBON[3]} />
      </div>

      {/* Revenue by category */}
      <div className={tc(theme, "p-4 border-b border-zinc-800 space-y-2", "p-4 border-b border-zinc-200 space-y-2")}>
        <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1">Revenue by Category</div>
        {ACCESSORY_CATEGORIES.map((category) => (
          <CategoryRevenueBar
            key={category}
            theme={theme}
            category={category}
            revenue={byCat[category] ?? 0}
            maxRevenue={maxCategoryRevenue}
          />
        ))}
        {overview?.attach_rate_disclaimer && (
          <div className="text-xs text-zinc-600 mt-2 italic">{overview.attach_rate_disclaimer}</div>
        )}
      </div>

      {/* Accessory catalog grouped by category */}
      <div className={tc(theme, "p-4 border-b border-zinc-800 space-y-4", "p-4 border-b border-zinc-200 space-y-4")}>
        <div className="text-sm font-brand uppercase tracking-wide text-zinc-400">🛠️ Accessory Catalog</div>
        {ACCESSORY_CATEGORIES.map((category) => {
          const items = catalogByCategory[category] ?? [];
          if (items.length === 0) return null;
          return (
            <div key={category}>
              <div className="text-xs font-brand uppercase tracking-wide mb-1.5" style={{ color: CATEGORY_COLOR[category] ?? RIBBON[0] }}>
                {CATEGORY_LABEL[category] ?? category}
              </div>
              <div className="grid grid-cols-2 gap-2">
                {items.map((item) => (
                  <div
                    key={item.id}
                    className={tc(theme, "rounded-md border border-zinc-800 bg-brand-charcoal px-3 py-2 flex items-center justify-between gap-2", "rounded-md border border-zinc-200 bg-zinc-50 px-3 py-2 flex items-center justify-between gap-2")}
                  >
                    <div className="min-w-0">
                      <div className="text-xs text-zinc-200 truncate">{item.name}</div>
                      <div className="text-xs text-zinc-500">{item.id}</div>
                    </div>
                    <div className="text-xs font-semibold text-zinc-300 tabular-nums whitespace-nowrap">{money(item.price)}</div>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
        {catalog?.disclaimer && <div className="text-xs text-zinc-600 italic">{catalog.disclaimer}</div>}
      </div>

      {/* Per-customer panel */}
      <div className="p-4 space-y-3">
        <div className="text-sm font-brand uppercase tracking-wide text-zinc-400">👤 Per-Customer Accessories</div>

        <div className="flex items-center gap-2">
          <WorkField label="Record ID"><WorkInput
            value={lookupId}
            onChange={(e) => setLookupId(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") loadRecommendations(lookupId);
            }}
            placeholder="Customer id (e.g. CUST-00123)"
            className={tc(
              theme,
              "flex-1 text-xs rounded border border-zinc-700 bg-black/30 px-2 py-1.5 text-white",
              "flex-1 text-xs rounded border border-zinc-300 bg-white px-2 py-1.5 text-black"
            )}
          /></WorkField>
          <WorkButton type="submit"
            onClick={() => loadRecommendations(lookupId)}
            disabled={recLoading}
            className="text-xs px-3 py-1.5 rounded-full bg-zinc-200 text-black font-medium disabled:opacity-50 whitespace-nowrap"
          >
            {recLoading ? "Loading…" : "Recommend"}
          </WorkButton>
          <WorkButton type="submit"
            onClick={handlePitch}
            disabled={pitchBusy}
            className="text-xs px-3 py-1.5 rounded-full bg-zinc-200/10 text-zinc-400 hover:text-white disabled:opacity-50 whitespace-nowrap"
          >
            {pitchBusy ? "Generating…" : "✨ Get AI Pitch"}
          </WorkButton>
        </div>

        {customerError && <div className="text-sm text-red-400">{customerError}</div>}

        {pitch && <PitchCard theme={theme} pitch={pitch} />}

        {rec && (
          <div className={tc(theme, "rounded-lg border border-zinc-800 bg-brand-charcoal p-3 space-y-3", "rounded-lg border border-zinc-200 bg-zinc-50 p-3 space-y-3")}>
            <div className="flex items-center justify-between gap-2">
              <div className="min-w-0">
                <div className="text-sm font-medium text-zinc-200 truncate">{rec.name ?? rec.customer_id}</div>
                <div className="text-xs text-zinc-500">{rec.customer_id}</div>
              </div>
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500">
                {selectedIds.length} selected
              </div>
            </div>

            {/* Recommendations -- tick items to build a sale from */}
            {rec.recommendations.length === 0 ? (
              <div className="text-xs text-zinc-500">No recommendations — this customer already owns an item in every category.</div>
            ) : (
              <div className="space-y-1.5">
                {rec.recommendations.map((item) => (
                  <label
                    key={item.item_id}
                    className={tc(theme, "flex items-center gap-2 rounded-md border border-zinc-800 bg-black/20 px-2.5 py-1.5 cursor-pointer", "flex items-center gap-2 rounded-md border border-zinc-200 bg-white px-2.5 py-1.5 cursor-pointer")}
                  >
                    <WorkInput
                      type="checkbox"
                      checked={!!selected[item.item_id]}
                      onChange={() => toggleSelected(item.item_id)}
                    />
                    <span
                      className="h-2 w-2 rounded-full flex-shrink-0"
                      style={{ background: CATEGORY_COLOR[item.category] ?? "#9CA3AF" }}
                    />
                    <div className="min-w-0 flex-1">
                      <div className="text-xs text-zinc-200 truncate">{item.name}</div>
                      <div className="text-xs text-zinc-500">{categoryLabel(item.category)}</div>
                    </div>
                    <div className="text-xs font-semibold text-zinc-300 tabular-nums whitespace-nowrap">{money(item.price)}</div>
                  </label>
                ))}
              </div>
            )}

            <div className="flex flex-wrap items-center gap-2">
              <WorkButton type="submit"
                onClick={handleCreateSale}
                disabled={saleBusy || selectedIds.length === 0}
                className="text-xs px-3 py-1.5 rounded-full bg-zinc-200 text-black font-medium disabled:opacity-50"
              >
                {saleBusy ? "…" : "＋ Record Sale"}
              </WorkButton>
            </div>

            {/* Recorded sale -- with mark-installed action */}
            {sale && (
              <div className={tc(theme, "rounded-md border border-zinc-700 bg-black/20 p-3", "rounded-md border border-zinc-300 bg-white p-3")}>
                <div className="flex items-center justify-between gap-2">
                  <div className="min-w-0">
                    <div className="text-xs font-medium text-zinc-200 truncate">{sale.sale_id}</div>
                    <div className="text-xs text-zinc-500">
                      {sale.installed ? `Installed ${fmt(sale.installed_at)}` : `Created ${fmt(sale.created_at)}`}
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-sm font-semibold text-zinc-200 tabular-nums">{money(sale.total_revenue)}</div>
                    <div className="text-xs font-brand uppercase tracking-wide" style={{ color: sale.installed ? RIBBON[1] : RIBBON[2] }}>
                      {sale.installed ? "Installed" : "Pending"}
                    </div>
                  </div>
                </div>
                <div className="mt-2 space-y-1">
                  {sale.line_items.map((line, i) => (
                    <div key={i} className="flex items-center justify-between gap-2 text-xs">
                      <span className="text-zinc-400 truncate">{line.name}</span>
                      <span className="text-zinc-500 tabular-nums whitespace-nowrap">{money(line.price)}</span>
                    </div>
                  ))}
                </div>
                {!sale.installed && (
                  <WorkButton type="submit"
                    onClick={handleMarkInstalled}
                    disabled={saleBusy}
                    className="mt-2 text-xs px-3 py-1.5 rounded-full bg-zinc-200/10 text-zinc-400 hover:text-white disabled:opacity-50"
                  >
                    {saleBusy ? "…" : "✓ Mark Installed"}
                  </WorkButton>
                )}
              </div>
            )}

            {rec.disclaimer && <div className="text-xs text-zinc-600 italic">{rec.disclaimer}</div>}
          </div>
        )}
      </div>
    </div>
  );
}
