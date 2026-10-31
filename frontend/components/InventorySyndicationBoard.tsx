"use client";
import { WorkButton , WorkStat} from "./WorkspaceUi";
import {RecordTable} from "./RecordTable";

// Inventory's new "Syndication" Top Menu item (2026-07-19) -- closes the
// "Inventory Syndication" item from Sam's own six-pillar spec. A KPI strip +
// tab board: Feed Health (a dealership-wide rollup of core/merchandising.py's
// per-vehicle SIMULATED feed-sync status, plus a real Listing Completeness
// Risk check and a bulk republish action reusing the existing per-vehicle
// mechanism) and Lead Performance (real Lead.Source-based revenue/conversion
// per syndication platform, reusing core/marketing_attribution.py's channel
// mix verbatim).
import { PRODUCT_ACCENT_COLORS } from "@/lib/productTheme";
import { useEffect, useState } from "react";
import {
  getSyndicationOverview,
  republishPlatform,
  type SyndicationOverview,
} from "@/lib/inventorySyndication";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const RIBBON = PRODUCT_ACCENT_COLORS;

function money(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return `$${v.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}

function pct(v: number | null | undefined): string {
  return v === null || v === undefined ? "—" : `${v}%`;
}

function statusColor(status: "synced" | "pending" | "error"): string {
  if (status === "synced") return "text-emerald-400";
  if (status === "pending") return "text-amber-400";
  return "text-red-400";
}

function Kpi({ theme, label, value, color }: { theme: Theme; label: string; value: string; color: string }) { return <WorkStat label={label} value={value}/>; }

export function InventorySyndicationBoard({ theme }: { theme: Theme }) {
  const [overview, setOverview] = useState<SyndicationOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<"feed_health" | "lead_performance">("feed_health");
  const [expandedPlatform, setExpandedPlatform] = useState<string | null>(null);
  const [republishing, setRepublishing] = useState<string | null>(null);
  const [republishResult, setRepublishResult] = useState<string | null>(null);

  const cardClass = tc(theme, "rounded-lg border border-black/20 bg-brand-charcoal p-3", "rounded-lg border border-zinc-200 bg-zinc-50 p-3");
  const tableHeadClass = tc(theme, "text-[10px] uppercase tracking-wide text-zinc-500 border-b border-zinc-800", "text-[10px] uppercase tracking-wide text-zinc-500 border-b border-zinc-200");
  const rowBorder = tc(theme, "border-b border-zinc-800/60", "border-b border-zinc-100");

  function refresh() {
    setLoading(true);
    setError(null);
    getSyndicationOverview()
      .then(setOverview)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load"))
      .finally(() => setLoading(false));
  }

  useEffect(refresh, []);

  function doRepublish(platform: string) {
    setRepublishing(platform);
    setRepublishResult(null);
    republishPlatform(platform)
      .then((r) => {
        setRepublishResult(`Republished ${r.republished_count} vehicle(s) to ${r.platform} (simulated -- no real syndication occurs).`);
        refresh();
      })
      .catch((e) => setRepublishResult(e instanceof Error ? e.message : "Failed to republish"))
      .finally(() => setRepublishing(null));
  }

  if (error) {
    return (
      <div className={tc(theme, "flex-1 flex items-center justify-center bg-brand-ink text-red-400 text-sm p-6", "flex-1 flex items-center justify-center bg-white text-red-600 text-sm p-6")}>
        {error}
      </div>
    );
  }

  const feedHealth = overview?.feed_health;
  const leadPerf = overview?.lead_performance;

  return (
    <div className={tc(theme, "work-inventory-board", "work-inventory-board")}>
      <div className={tc(theme, "work-inventory-stats", "work-inventory-stats")}>
        <Kpi theme={theme} label="Unsold Vehicles" value={loading ? "…" : String(overview?.total_unsold_vehicles ?? 0)} color={RIBBON[0]} />
        <Kpi theme={theme} label="Listing Errors / Pending" value={loading ? "…" : `${overview?.total_listing_errors ?? 0} / ${overview?.total_listing_pending ?? 0}`} color={RIBBON[1]} />
        <Kpi theme={theme} label="Syndication Revenue" value={loading ? "…" : money(overview?.total_syndication_revenue)} color={RIBBON[2]} />
        <Kpi theme={theme} label="Listing Completeness Risk" value={loading ? "…" : String(overview?.listing_completeness_risk_count ?? 0)} color={RIBBON[3]} />
      </div>

      <div className="px-4 py-2 border-b border-zinc-800 flex gap-2">
        {(["feed_health", "lead_performance"] as const).map((t) => (
          <WorkButton data-work-view aria-pressed={tab === t} type="submit"
            key={t}
            onClick={() => setTab(t)}
            className={`text-xs px-3 py-1.5 rounded font-medium transition ${
              tab === t
                ? "bg-brand-blue text-white"
                : tc(theme, "bg-zinc-800 text-zinc-300 hover:bg-zinc-700", "bg-zinc-100 text-zinc-600 hover:bg-zinc-200")
            }`}
          >
            {t === "feed_health" ? "Feed Health" : "Lead Performance"}
          </WorkButton>
        ))}
      </div>

      <div className="flex-1 p-4 overflow-y-auto space-y-3">
        {loading ? (
          <div className="text-xs text-zinc-500">Loading…</div>
        ) : tab === "feed_health" ? (
          <>
            <div className="text-xs px-2 py-1.5 rounded bg-amber-950/30 border border-amber-900/50 text-amber-300 inline-block">
              {feedHealth?.disclaimer}
            </div>

            {republishResult && (
              <div className="text-xs px-2 py-1.5 rounded bg-emerald-950/30 border border-emerald-900/50 text-emerald-300">
                {republishResult}
              </div>
            )}

            <div className="space-y-2">
              {feedHealth?.platforms.map((p) => (
                <div key={p.platform} className={cardClass}>
                  <div className="flex items-center justify-between">
                    <div className="font-medium text-sm">{p.platform}</div>
                    <div className="flex items-center gap-4 text-xs">
                      <span className={statusColor("synced")}>{p.synced} synced</span>
                      <span className={statusColor("pending")}>{p.pending} pending</span>
                      <span className={statusColor("error")}>{p.error} error</span>
                      <WorkButton type="submit" variant="primary"
                        onClick={() => doRepublish(p.platform)}
                        disabled={republishing === p.platform || (p.pending + p.error === 0)}
                        className="text-xs px-2.5 py-1 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-40"
                      >
                        {republishing === p.platform ? "Republishing…" : "Republish All Pending/Error"}
                      </WorkButton>
                      {p.error > 0 && (
                        <WorkButton type="submit"
                          onClick={() => setExpandedPlatform(expandedPlatform === p.platform ? null : p.platform)}
                          className="text-xs text-zinc-400 underline"
                        >
                          {expandedPlatform === p.platform ? "Hide" : "View"} errors
                        </WorkButton>
                      )}
                    </div>
                  </div>
                  {expandedPlatform === p.platform && (
                    <div className="mt-2 space-y-1">
                      {p.error_vehicles.map((v) => (
                        <div key={v.vehicle_id} className="text-xs text-zinc-400 flex justify-between">
                          <span>{v.stock_number} — {v.year} {v.make} {v.model}</span>
                          <span>{money(v.price)}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>

            <div>
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1.5 mt-3">
                Listing Completeness Risk ({feedHealth?.listing_completeness_risk.count ?? 0})
              </div>
              <div className="text-xs text-zinc-500 mb-2">{feedHealth?.listing_completeness_risk.note}</div>
              {!feedHealth?.listing_completeness_risk.vehicles.length ? (
                <div className="text-xs text-zinc-500">No synced vehicles currently missing a photo or description.</div>
              ) : (
                <RecordTable className="w-full text-xs">
                  <thead>
                    <tr className={tableHeadClass}>
                      <th className="text-left py-2 pr-3">Vehicle</th>
                      <th className="text-right py-2 pr-3">Price</th>
                      <th className="text-right py-2 pr-3">Photos</th>
                      <th className="text-right py-2">Description</th>
                    </tr>
                  </thead>
                  <tbody>
                    {feedHealth.listing_completeness_risk.vehicles.map((v) => (
                      <tr key={v.vehicle_id} className={rowBorder}>
                        <td className="py-1.5 pr-3">{v.stock_number} — {v.year} {v.make} {v.model}</td>
                        <td className="py-1.5 pr-3 text-right">{money(v.price)}</td>
                        <td className="py-1.5 pr-3 text-right text-red-400">{v.has_photos ? "✓" : "Missing"}</td>
                        <td className="py-1.5 text-right text-red-400">{v.has_description ? "✓" : "Missing"}</td>
                      </tr>
                    ))}
                  </tbody>
                </RecordTable>
              )}
            </div>
          </>
        ) : (
          <>
            <div className="text-xs px-2 py-1.5 rounded bg-amber-950/30 border border-amber-900/50 text-amber-300 inline-block">
              {leadPerf?.disclaimer}
            </div>

            <RecordTable className="w-full text-xs">
              <thead>
                <tr className={tableHeadClass}>
                  <th className="text-left py-2 pr-3">Platform</th>
                  <th className="text-left py-2 pr-3">Lead.Source</th>
                  <th className="text-right py-2 pr-3">Leads</th>
                  <th className="text-right py-2 pr-3">Sold</th>
                  <th className="text-right py-2 pr-3">Conversion</th>
                  <th className="text-right py-2 pr-3">Revenue</th>
                  <th className="text-right py-2">Rev/Lead</th>
                </tr>
              </thead>
              <tbody>
                {leadPerf?.platform_performance.map((r) => (
                  <tr key={r.platform} className={rowBorder}>
                    <td className="py-2 pr-3 font-medium">{r.platform}</td>
                    <td className="py-2 pr-3 text-zinc-500">{r.lead_source}</td>
                    <td className="py-2 pr-3 text-right">{r.lead_count}</td>
                    <td className="py-2 pr-3 text-right">{r.sold_count}</td>
                    <td className="py-2 pr-3 text-right">{pct(r.conversion_rate)}</td>
                    <td className="py-2 pr-3 text-right">{money(r.revenue)}</td>
                    <td className="py-2 text-right">{money(r.revenue_per_lead)}</td>
                  </tr>
                ))}
              </tbody>
            </RecordTable>

            {!!leadPerf?.feed_only_platforms.length && (
              <div className="text-xs text-zinc-500 mt-2">
                Feed-tracked but no matching Lead.Source: {leadPerf.feed_only_platforms.join(", ")}
              </div>
            )}

            {!!leadPerf?.lead_only_channels.length && (
              <div className="mt-3">
                <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1.5">
                  Real Lead Channels With No Feed-Sync Mechanism
                </div>
                <RecordTable className="w-full text-xs">
                  <thead>
                    <tr className={tableHeadClass}>
                      <th className="text-left py-2 pr-3">Source</th>
                      <th className="text-right py-2 pr-3">Leads</th>
                      <th className="text-right py-2 pr-3">Conversion</th>
                      <th className="text-right py-2">Revenue</th>
                    </tr>
                  </thead>
                  <tbody>
                    {leadPerf.lead_only_channels.map((c) => (
                      <tr key={c.source} className={rowBorder}>
                        <td className="py-2 pr-3 font-medium">{c.source}</td>
                        <td className="py-2 pr-3 text-right">{c.lead_count}</td>
                        <td className="py-2 pr-3 text-right">{pct(c.conversion_rate)}</td>
                        <td className="py-2 text-right">{money(c.revenue)}</td>
                      </tr>
                    ))}
                  </tbody>
                </RecordTable>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
