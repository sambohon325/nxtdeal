"use client";

// DigitalRetailBoard — the Digital Retail KPI dashboard (DR-8, 2026-07-24). Sam's Reporting
// spec: digital leads/deals/deliveries/closings/gross, AI performance, and the workflow
// drop-off funnel. A read-only roll-up over everything DR-1..7 record (core/
// digital_retail_analytics.py) — "digital" means self-service (the customer drove it via the
// Verify portal), and gross is computed from real Vehicle Cost/Price on funded digital deals.
// Same styling vocabulary (RIBBON palette, theme-aware tc()) as the other DR boards.

import { PRODUCT_ACCENT_COLORS } from "@/lib/productTheme";
import { useEffect, useState } from "react";
import { fetchDigitalRetailDashboard, type DigitalRetailDashboard } from "@/lib/digitalRetail";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const RIBBON = PRODUCT_ACCENT_COLORS;

function money(n: number): string {
  return `$${Math.round(n).toLocaleString()}`;
}

function cap(s: string): string {
  return s ? s.charAt(0).toUpperCase() + s.slice(1).replace(/_/g, " ") : s;
}

function Tile({ theme, value, label, accent }: { theme: Theme; value: number | string; label: string; accent: string }) {
  return (
    <div
      className={`rounded-lg border p-3 ${tc(theme, "border-white/10 bg-white/[0.03]", "border-black/10 bg-black/[0.02]")}`}
      style={{ borderLeft: `3px solid ${accent}` }}
    >
      <div className={`text-2xl font-semibold ${tc(theme, "text-white", "text-gray-900")}`}>{value}</div>
      <div className={`mt-1 text-xs font-brand uppercase tracking-wide ${tc(theme, "text-gray-400", "text-gray-500")}`}>
        {label}
      </div>
    </div>
  );
}

export function DigitalRetailBoard({ theme, hideHeading=false }: { theme: Theme; hideHeading?:boolean }) {
  const [data, setData] = useState<DigitalRetailDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    fetchDigitalRetailDashboard()
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(e instanceof Error ? e.message : "Unable to load the Digital Retail dashboard."))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, []);

  const cardBase = tc(theme, "border-white/10 bg-white/[0.03]", "border-black/10 bg-white");
  const subtle = tc(theme, "text-gray-400", "text-gray-500");
  const heading = tc(theme, "text-white", "text-gray-900");

  return (
    <div className="space-y-5">
      <div>
        {!hideHeading && <h2 className={`text-xl font-semibold ${heading}`}>Digital Retail</h2>}
        <p className={`mt-1 text-sm ${subtle}`}>
          How the self-service purchase journey is performing — deals the customer drove
          themselves through NXTDeal, from verification to delivery. Gross is computed from real
          vehicle cost on funded digital deals; nothing is fabricated.
        </p>
      </div>

      {loading ? (
        <div className={`text-sm ${subtle}`}>Loading the Digital Retail dashboard…</div>
      ) : error ? (
        <div className="rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-400">{error}</div>
      ) : data ? (
        <>
          {/* Headline KPIs */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            <Tile theme={theme} value={data.kpis.verifications} label="Verifications" accent={RIBBON[0]} />
            <Tile theme={theme} value={data.kpis.digital_deals} label="Digital Deals" accent={RIBBON[1]} />
            <Tile theme={theme} value={data.kpis.digital_closings} label="Digital Closings" accent={RIBBON[3]} />
            <Tile theme={theme} value={money(data.kpis.digital_gross)} label="Digital Gross" accent={RIBBON[2]} />
            <Tile theme={theme} value={data.kpis.digital_deliveries} label="Digital Deliveries" accent={RIBBON[1]} />
            <Tile theme={theme} value={data.negotiations.total_sessions} label="Negotiations" accent={RIBBON[0]} />
          </div>

          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            {/* Journey funnel / drop-off */}
            <div className={`rounded-lg border p-4 ${cardBase}`}>
              <h3 className={`mb-3 text-sm font-semibold ${heading}`}>Self-service journey — drop-off</h3>
              <div className="space-y-2">
                {data.funnel.stages.map((s, i) => {
                  const max = data.funnel.stages[0]?.count || 1;
                  const pct = max > 0 ? Math.round((s.count / max) * 100) : 0;
                  return (
                    <div key={s.stage}>
                      <div className="flex items-center justify-between text-xs">
                        <span className={subtle}>{s.label}</span>
                        <span className={heading}>
                          {s.count}
                          {s.conversion_from_prev != null && (
                            <span className={subtle}> · {Math.round(s.conversion_from_prev * 100)}%</span>
                          )}
                          {s.dropped_from_prev > 0 && (
                            <span className="text-red-400"> · −{s.dropped_from_prev}</span>
                          )}
                        </span>
                      </div>
                      <div className={`mt-1 h-2 overflow-hidden rounded-full ${tc(theme, "bg-white/10", "bg-black/10")}`}>
                        <div className="h-full rounded-full" style={{ width: `${pct}%`, backgroundColor: RIBBON[i % RIBBON.length] }} />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* AI performance */}
            <div className={`rounded-lg border p-4 ${cardBase}`}>
              <h3 className={`mb-3 text-sm font-semibold ${heading}`}>AI performance</h3>
              <div className="grid grid-cols-2 gap-3">
                <Tile theme={theme} value={data.ai_performance.deals_assisted} label="Deals Assisted" accent={RIBBON[0]} />
                <Tile theme={theme} value={data.ai_performance.deals_negotiated} label="Deals Negotiated" accent={RIBBON[1]} />
                <Tile theme={theme} value={data.ai_performance.deals_closed} label="Deals Closed" accent={RIBBON[3]} />
                <Tile theme={theme} value={money(data.ai_performance.revenue_influenced)} label="Revenue Influenced" accent={RIBBON[2]} />
              </div>
              <div className={`mt-3 text-xs ${subtle}`}>
                AI workforce: {data.ai_performance.workforce.active_workers} active ·{" "}
                {data.ai_performance.workforce.actions_executed} executed ·{" "}
                {data.ai_performance.workforce.actions_drafted} drafted
              </div>
            </div>
          </div>

          {/* Verification tiers + deliveries breakdown */}
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            <div className={`rounded-lg border p-4 ${cardBase}`}>
              <h3 className={`mb-3 text-sm font-semibold ${heading}`}>Verification tiers</h3>
              <div className="space-y-1.5">
                {Object.entries(data.verifications.by_tier).map(([tier, n]) => (
                  <div key={tier} className="flex items-center justify-between text-xs">
                    <span className={subtle}>{cap(tier)}</span>
                    <span className={heading}>{n}</span>
                  </div>
                ))}
              </div>
            </div>
            <div className={`rounded-lg border p-4 ${cardBase}`}>
              <h3 className={`mb-3 text-sm font-semibold ${heading}`}>Deliveries &amp; trials</h3>
              <div className="space-y-1.5 text-xs">
                {Object.entries(data.deliveries.by_mode).map(([mode, n]) => (
                  <div key={mode} className="flex items-center justify-between">
                    <span className={subtle}>{cap(mode)}</span>
                    <span className={heading}>{n}</span>
                  </div>
                ))}
                <div className="flex items-center justify-between">
                  <span className={subtle}>Home deliveries without a driver</span>
                  <span className={data.deliveries.home_deliveries_without_driver > 0 ? "text-red-400" : heading}>
                    {data.deliveries.home_deliveries_without_driver}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className={subtle}>Try-before-you-buy out now</span>
                  <span className={heading}>{data.try_before_you_buy.currently_out}</span>
                </div>
              </div>
            </div>
          </div>

          <p className={`text-xs ${subtle}`}>{data.note}</p>
        </>
      ) : null}
    </div>
  );
}
