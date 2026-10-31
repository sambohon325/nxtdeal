"use client";
import { WorkButton } from "./WorkspaceUi";
import {RecordCollection} from "./RecordCollection";

// Readiness' "Forecasts" item (2026-07-19), item #5 of Sam's 10-item proposed
// structure -- enriched from a generic tomorrow/week/month/quarter-per-department
// view into Sam's own "predictive analytics engine" framing: Sales (Units/Gross/
// Closing Ratio/Revenue), Service (Labor Sales/Parts Sales/RO Count/Capacity),
// Inventory (Units Likely To Sell/Age, Wholesale Candidates), Finance (Funding/
// Collections/Delinquencies/Portfolio Performance). Also closes the separately-named
// "Readiness Timeline" capstone (Last 7/30/90 Days, Year To Date, "to spot trends").
// core/readiness_forecasts.py is a pure composition layer -- every figure here is
// real, a real simple linear run-rate projection (labeled as such, never oversold as
// a sophisticated model), or a real transparent rules-engine composition of already-
// real/simulated signals. No fabricated number appears anywhere.
import { useEffect, useState } from "react";
import {
  getForecastsOverview,
  getReadinessTimelineOverview,
  type ForecastsOverview,
  type ReadinessTimelineOverview,
  type Basis,
  type HorizonPrediction,
  type LinearProjectionField,
  type InventoryVehicleSignal,
} from "@/lib/readinessForecasts";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const RIBBON: Record<string, string> = {
  sales: "#2B68AB",
  service: "#3FBCC4",
  inventory: "#FBCF09",
  finance: "#EE3C25",
};

function fmtNum(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number") {
    return Number.isInteger(value) ? value.toLocaleString() : value.toFixed(2);
  }
  return String(value);
}

function fmtMoney(value: unknown): string {
  if (value === null || value === undefined || typeof value !== "number") return "—";
  return `$${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function BasisBadge({ basis }: { basis?: Basis }) {
  if (!basis) return null;
  const map: Record<string, { label: string; cls: string }> = {
    real: { label: "real", cls: "bg-emerald-950/40 text-emerald-300" },
    actual: { label: "real (actual)", cls: "bg-emerald-950/40 text-emerald-300" },
    ledger: { label: "real ledger", cls: "bg-emerald-950/40 text-emerald-300" },
    ledger_or_industry_estimate: { label: "ledger / est.", cls: "bg-sky-950/40 text-sky-300" },
    real_linear_projection: { label: "linear projection", cls: "bg-sky-950/40 text-sky-300" },
    heuristic: { label: "heuristic", cls: "bg-amber-950/40 text-amber-300" },
    heuristic_rules: { label: "rules engine", cls: "bg-amber-950/40 text-amber-300" },
    simulated_payment_status: { label: "simulated", cls: "bg-purple-950/40 text-purple-300" },
    blended: { label: "blended", cls: "bg-sky-950/40 text-sky-300" },
    industry_estimate: { label: "industry est.", cls: "bg-zinc-800 text-zinc-400" },
  };
  const entry = map[basis] ?? { label: basis, cls: "bg-zinc-800 text-zinc-400" };
  return <span className={`ml-1.5 px-1.5 py-0.5 rounded text-xs uppercase tracking-wide ${entry.cls}`}>{entry.label}</span>;
}

function NoAccessNote({ theme }: { theme: Theme }) {
  return <div className={tc(theme, "text-xs text-zinc-600 italic", "text-xs text-zinc-400 italic")}>No access with your current role.</div>;
}

function Tile({ theme, label, value, basis, sub }: { theme: Theme; label: string; value: string; basis?: Basis; sub?: string }) {
  return (
    <div className={tc(theme, "rounded border border-zinc-800 bg-zinc-900/60 px-3 py-2", "rounded border border-zinc-200 bg-zinc-50 px-3 py-2")}>
      <div className="flex items-center flex-wrap">
        <span className="text-xs uppercase tracking-wide text-zinc-500">{label}</span>
        <BasisBadge basis={basis} />
      </div>
      <div className="text-lg font-semibold mt-0.5">{value}</div>
      {sub && <div className="text-xs text-zinc-500 mt-0.5">{sub}</div>}
    </div>
  );
}

function SectionCard({ theme, title, color, children }: { theme: Theme; title: string; color: string; children: React.ReactNode }) {
  return (
    <div className={tc(theme, "relative overflow-hidden rounded-lg border border-zinc-800 bg-brand-charcoal p-4", "relative overflow-hidden rounded-lg border border-zinc-200 bg-white p-4")}>
      <span className="absolute left-0 top-0 bottom-0 w-1.5" style={{ background: color }} />
      <div className="pl-2">
        <div className="text-sm font-brand font-semibold mb-3">{title}</div>
        <div className="grid grid-cols-2 gap-2">{children}</div>
      </div>
    </div>
  );
}

function HorizonRow({ theme, forecasts }: { theme: Theme; forecasts?: HorizonPrediction[] }) {
  if (!forecasts || forecasts.length === 0) return <div className="text-xs text-zinc-500">No forecast available.</div>;
  return (
    <div className="grid grid-cols-4 gap-1.5">
      {forecasts.map((f) => (
        <div key={f.horizon} className={tc(theme, "rounded border border-zinc-800 bg-zinc-950/60 px-2 py-1.5 text-center", "rounded border border-zinc-200 bg-white px-2 py-1.5 text-center")}>
          <div className="text-xs uppercase tracking-wide text-zinc-500 capitalize">{f.horizon}</div>
          <div className="text-sm font-semibold">{fmtNum(f.predicted_value)}</div>
          <div className="text-xs text-zinc-600">{f.unit}</div>
          <BasisBadge basis={f.basis} />
        </div>
      ))}
    </div>
  );
}

function ProjectionTile({ theme, label, field }: { theme: Theme; label: string; field?: LinearProjectionField | { basis: string; note: string } }) {
  if (!field) return <Tile theme={theme} label={label} value="—" />;
  const proj = field as LinearProjectionField;
  if (typeof proj.projected_month_total !== "number") {
    return <Tile theme={theme} label={label} value="—" basis={field.basis as Basis} sub={field.note} />;
  }
  const toDate = proj.month_to_date ?? proj.actual_to_date;
  return (
    <Tile
      theme={theme}
      label={label}
      value={fmtMoney(proj.projected_month_total)}
      basis={field.basis as Basis}
      sub={`${fmtMoney(toDate)} so far · day ${proj.days_elapsed}/${proj.days_in_month}`}
    />
  );
}

function VehicleList({ theme, vehicles }: { theme: Theme; vehicles: InventoryVehicleSignal[] }) {
  if (vehicles.length === 0) return <div className="text-xs text-zinc-500">None.</div>;
  return (
    <div className="max-h-32 overflow-y-auto space-y-1 mt-1">
      <RecordCollection>{vehicles.map((v) => (
        <div key={v.vehicle_id} className={tc(theme, "flex items-center justify-between text-xs text-zinc-400 border-b border-zinc-800 pb-0.5", "flex items-center justify-between text-xs text-zinc-600 border-b border-zinc-200 pb-0.5")}>
          <span>
            {v.year} {v.make} {v.model} — {v.stock_number ?? v.vehicle_id}
          </span>
          <span className="text-zinc-500">
            {v.age_band} · {v.margin_pct !== null && v.margin_pct !== undefined ? `${(v.margin_pct * 100).toFixed(1)}%` : "—"}
          </span>
        </div>
      ))}</RecordCollection>
    </div>
  );
}

const TREND_ARROW: Record<string, { icon: string; cls: string }> = {
  up: { icon: "▲", cls: "text-emerald-400" },
  down: { icon: "▼", cls: "text-red-400" },
  flat: { icon: "▬", cls: "text-zinc-500" },
};

function TimelineCard({ theme, department, trend }: { theme: Theme; department: string; trend: ReadinessTimelineOverview["departments"][string] }) {
  const color = RIBBON[department] ?? "#7C5CBF";
  if (!trend || trend.error) {
    return (
      <div className={tc(theme, "relative overflow-hidden rounded-lg border border-zinc-800 bg-brand-charcoal p-4", "relative overflow-hidden rounded-lg border border-zinc-200 bg-white p-4")}>
        <span className="absolute left-0 top-0 bottom-0 w-1.5" style={{ background: color }} />
        <div className="pl-2 text-sm font-brand font-semibold capitalize">{department}</div>
        <div className="pl-2 text-xs text-zinc-500 mt-1">{trend?.error ?? "No data."}</div>
      </div>
    );
  }
  const arrow = TREND_ARROW[trend.trend_direction] ?? TREND_ARROW.flat;
  const windows = [
    { key: "last_7_days", w: trend.windows.last_7_days },
    { key: "last_30_days", w: trend.windows.last_30_days },
    { key: "last_90_days", w: trend.windows.last_90_days },
    { key: "year_to_date", w: trend.windows.year_to_date },
  ];
  return (
    <div className={tc(theme, "relative overflow-hidden rounded-lg border border-zinc-800 bg-brand-charcoal p-4", "relative overflow-hidden rounded-lg border border-zinc-200 bg-white p-4")}>
      <span className="absolute left-0 top-0 bottom-0 w-1.5" style={{ background: color }} />
      <div className="pl-2">
        <div className="flex items-center justify-between">
          <div className="text-sm font-brand font-semibold capitalize">{department}</div>
          <div className={`text-lg font-bold ${arrow.cls}`}>{arrow.icon} {trend.trend_direction}</div>
        </div>
        <div className="text-xs text-zinc-500 mt-0.5">{trend.metric} ({trend.unit})</div>
        <div className="grid grid-cols-4 gap-1.5 mt-3">
          {windows.map(({ key, w }) => (
            <div key={key} className={tc(theme, "rounded border border-zinc-800 bg-zinc-900/60 px-2 py-1.5 text-center", "rounded border border-zinc-200 bg-zinc-50 px-2 py-1.5 text-center")}>
              <div className="text-xs uppercase tracking-wide text-zinc-500">{w.label}</div>
              <div className="text-sm font-semibold">{fmtNum(w.value)}</div>
              <div className="text-xs text-zinc-600">{w.daily_rate}/day</div>
            </div>
          ))}
        </div>
        <div className="text-xs text-zinc-600 mt-2">{trend.trend_basis}</div>
      </div>
    </div>
  );
}

export function ReadinessForecastsBoard({ theme, horizon }: { theme: Theme; horizon?:string }) {
  const [tab, setTab] = useState<"forecasts" | "timeline">("forecasts");
  const [data, setData] = useState<ForecastsOverview | null>(null);
  const [timeline, setTimeline] = useState<ReadinessTimelineOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  function refresh() {
    setLoading(true);
    setError(null);
    Promise.all([getForecastsOverview(), getReadinessTimelineOverview()])
      .then(([f, t]) => {
        setData(f);
        setTimeline(t);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Unable to load Forecasts data."))
      .finally(() => setLoading(false));
  }

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => refresh(), []);

  const sales = data?.sales;
  const service = data?.service;
  const inventory = data?.inventory;
  const finance = data?.finance;

  const financeCollectionsOk = finance && !("error" in (finance.collections ?? {}));
  const financePortfolioOk = finance && !("error" in (finance.portfolio_performance ?? {}));

  return (
    <div className={tc(theme, "flex-1 flex flex-col min-h-0 bg-brand-ink text-white overflow-y-auto", "flex-1 flex flex-col min-h-0 bg-white text-black overflow-y-auto")}>
      <div className={tc(theme, "px-4 py-3 border-b border-zinc-800", "px-4 py-3 border-b border-zinc-200")}>
        <div className="flex items-center justify-between">
          <div>
            <div className="text-sm font-brand font-semibold">Forecasts</div>
            <div className="text-xs text-zinc-500 mt-0.5">
              The predictive analytics engine -- real ledger forecasts, real simple linear run-rate projections
              (clearly labeled, not a sophisticated model), and a real transparent rules engine for Inventory. Plus
              the Readiness Timeline capstone -- real trailing-window trends to spot momentum.
            </div>
          </div>
          <div className="flex gap-1.5">
            <WorkButton data-work-view aria-pressed={tab === "forecasts"} type="submit"
              onClick={() => setTab("forecasts")}
              className={`text-xs px-3 py-1.5 rounded font-medium ${tab === "forecasts" ? "bg-zinc-200 text-black" : tc(theme, "bg-zinc-800 text-zinc-300", "bg-zinc-100 text-zinc-600")}`}
            >
              Forecasts
            </WorkButton>
            <WorkButton data-work-view aria-pressed={tab === "timeline"} type="submit"
              onClick={() => setTab("timeline")}
              className={`text-xs px-3 py-1.5 rounded font-medium ${tab === "timeline" ? "bg-zinc-200 text-black" : tc(theme, "bg-zinc-800 text-zinc-300", "bg-zinc-100 text-zinc-600")}`}
            >
              Readiness Timeline
            </WorkButton>
          </div>
        </div>
      </div>

      {error && <div className="mx-4 mt-2 text-xs text-red-400">{error}</div>}

      <div className="flex-1 p-4 space-y-4">
        {loading ? (
          <div className="text-sm text-zinc-500">Loading…</div>
        ) : tab === "forecasts" ? (
          <>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
              <SectionCard theme={theme} title="Sales Forecast" color={RIBBON.sales}>
                <div className="col-span-2">
                  <div className="text-xs uppercase tracking-wide text-zinc-500 mb-1">Units (by horizon)</div>
                  <HorizonRow theme={theme} forecasts={sales?.units.forecast_by_horizon?.filter(f=>!horizon||f.horizon===horizon)} />
                </div>
                <ProjectionTile theme={theme} label="Gross (projected)" field={sales?.gross} />
                <ProjectionTile theme={theme} label="Revenue (projected)" field={sales?.revenue} />
                <div className="col-span-2">
                  <Tile
                    theme={theme}
                    label="Closing Ratio (current baseline)"
                    value={sales?.closing_ratio.value !== null && sales?.closing_ratio.value !== undefined ? `${sales.closing_ratio.value}%` : "—"}
                    basis={sales?.closing_ratio.basis}
                    sub={sales?.closing_ratio.note}
                  />
                </div>
              </SectionCard>

              <SectionCard theme={theme} title="Service Forecast" color={RIBBON.service}>
                <ProjectionTile theme={theme} label="Labor Sales (projected)" field={service?.labor_sales} />
                <ProjectionTile theme={theme} label="Parts Sales (projected)" field={service?.parts_sales} />
                <div className="col-span-2">
                  <div className="text-xs uppercase tracking-wide text-zinc-500 mb-1">RO Count (by horizon)</div>
                  <HorizonRow theme={theme} forecasts={service?.ro_count.forecast_by_horizon?.filter(f=>!horizon||f.horizon===horizon)} />
                </div>
                <div className="col-span-2">
                  <Tile
                    theme={theme}
                    label="Capacity (current constraint)"
                    value={service?.capacity?.avg_utilization_pct_today !== undefined ? `${fmtNum(service.capacity.avg_utilization_pct_today)}%` : "—"}
                    basis={service?.capacity?.basis as Basis}
                    sub={typeof service?.capacity?.note === "string" ? service.capacity.note : undefined}
                  />
                </div>
              </SectionCard>

              <SectionCard theme={theme} title="Inventory Forecast" color={RIBBON.inventory}>
                <div className="col-span-2">
                  <Tile
                    theme={theme}
                    label="Units Likely To Sell"
                    value={String(inventory?.units_likely_to_sell.count ?? "—")}
                    basis={inventory?.units_likely_to_sell.basis}
                    sub={inventory?.units_likely_to_sell.note}
                  />
                  {inventory && <VehicleList theme={theme} vehicles={inventory.units_likely_to_sell.vehicles} />}
                </div>
                <div className="col-span-2">
                  <Tile
                    theme={theme}
                    label="Units Likely To Age"
                    value={String(inventory?.units_likely_to_age.count ?? "—")}
                    basis={inventory?.units_likely_to_age.basis}
                    sub={inventory?.units_likely_to_age.note}
                  />
                  {inventory && <VehicleList theme={theme} vehicles={inventory.units_likely_to_age.vehicles} />}
                </div>
                <div className="col-span-2">
                  <Tile
                    theme={theme}
                    label="Wholesale Candidates"
                    value={String(inventory?.wholesale_candidates?.count ?? inventory?.wholesale_candidates?.error ?? "—")}
                    basis="real"
                    sub={typeof inventory?.wholesale_candidates?.note === "string" ? inventory.wholesale_candidates.note : undefined}
                  />
                </div>
              </SectionCard>

              <SectionCard theme={theme} title="Finance Forecast" color={RIBBON.finance}>
                <div className="col-span-2">
                  <div className="text-xs uppercase tracking-wide text-zinc-500 mb-1">Funding (by horizon)</div>
                  <HorizonRow theme={theme} forecasts={finance?.funding.forecast_by_horizon?.filter(f=>!horizon||f.horizon===horizon)} />
                </div>
                {financeCollectionsOk ? (
                  <Tile
                    theme={theme}
                    label="Collections Queue"
                    value={String((finance?.collections as Record<string, unknown>)?.total_in_queue ?? "—")}
                    basis="real"
                    sub={`Recovery risk: ${(finance?.collections as Record<string, unknown>)?.recovery_risk_count ?? "—"}`}
                  />
                ) : (
                  <div>
                    <div className="text-xs uppercase tracking-wide text-zinc-500">Collections</div>
                    <NoAccessNote theme={theme} />
                  </div>
                )}
                {financePortfolioOk ? (
                  <Tile
                    theme={theme}
                    label="Portfolio Performance"
                    value={fmtMoney((finance?.portfolio_performance as Record<string, unknown>)?.total_outstanding_balance)}
                    basis={(finance?.portfolio_performance as Record<string, unknown>)?.basis as Basis}
                    sub={`${(finance?.portfolio_performance as Record<string, unknown>)?.active_loans ?? "—"} active loans`}
                  />
                ) : (
                  <div>
                    <div className="text-xs uppercase tracking-wide text-zinc-500">Portfolio Performance</div>
                    <NoAccessNote theme={theme} />
                  </div>
                )}
                {financePortfolioOk && (
                  <div className="col-span-2 text-xs text-zinc-600">
                    Delinquency buckets: {JSON.stringify((finance?.delinquencies as Record<string, unknown>)?.delinquency_buckets ?? {})}
                  </div>
                )}
              </SectionCard>
            </div>

            {data?.not_yet_tracked && Object.keys(data.not_yet_tracked).length > 0 && (
              <div className={tc(theme, "text-xs text-zinc-500 bg-zinc-900/60 border border-zinc-800 rounded px-3 py-2", "text-xs text-zinc-600 bg-zinc-50 border border-zinc-200 rounded px-3 py-2")}>
                {Object.entries(data.not_yet_tracked).map(([k, v]) => (
                  <div key={k}>
                    <span className="font-semibold">{k}:</span> {v}
                  </div>
                ))}
              </div>
            )}
          </>
        ) : (
          <>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
              {timeline &&
                Object.entries(timeline.departments).map(([dept, trend]) => (
                  <TimelineCard key={dept} theme={theme} department={dept} trend={trend} />
                ))}
            </div>
            {timeline?.not_yet_tracked && Object.keys(timeline.not_yet_tracked).length > 0 && (
              <div className={tc(theme, "text-xs text-zinc-500 bg-zinc-900/60 border border-zinc-800 rounded px-3 py-2", "text-xs text-zinc-600 bg-zinc-50 border border-zinc-200 rounded px-3 py-2")}>
                {Object.entries(timeline.not_yet_tracked).map(([k, v]) => (
                  <div key={k}>
                    <span className="font-semibold">{k}:</span> {v}
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
