"use client";
import { WorkButton } from "./WorkspaceUi";

// Readiness' new "Business Health" Top Menu item -- Sam's reframe of Readiness from
// a data-confidence screen into an executive layer above every production
// department: "is the dealership ready to achieve its goals, where are the risks."
// core/business_health.py is a pure composition layer over each department's own
// already-real KPI engines -- this board renders exactly what it returns, with a
// visible real/heuristic/simulated/gap badge on every figure so nothing here reads
// as more precise than it actually is. No blended "overall score" exists (see the
// backend module's own docstring for why) -- this board shows 5 department cards
// side by side instead of one fabricated number.
import { PRODUCT_ACCENT_COLORS } from "@/lib/productTheme";
import { useEffect, useState } from "react";
import {
  getBusinessHealthOverview,
  type BusinessHealthOverview,
  type Basis,
} from "@/lib/businessHealth";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const RIBBON = [...PRODUCT_ACCENT_COLORS, "#aab5d1"];

function fmtNum(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number") {
    return Number.isInteger(value) ? value.toLocaleString() : value.toFixed(2);
  }
  return String(value);
}

function fmtPct(value: unknown, digits = 1): string {
  if (value === null || value === undefined || typeof value !== "number") return "—";
  return `${value.toFixed(digits)}%`;
}

function fmtMoney(value: unknown): string {
  if (value === null || value === undefined || typeof value !== "number") return "—";
  return `$${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function BasisBadge({ basis }: { basis?: Basis }) {
  if (!basis) return null;
  const map: Record<string, { label: string; cls: string }> = {
    real: { label: "real", cls: "bg-emerald-950/40 text-emerald-300" },
    heuristic: { label: "heuristic", cls: "bg-amber-950/40 text-amber-300" },
    simulated_market_data: { label: "simulated", cls: "bg-purple-950/40 text-purple-300" },
    simulated_payment_status: { label: "simulated", cls: "bg-purple-950/40 text-purple-300" },
    real_first_touch_not_multi_touch: { label: "real (first-touch)", cls: "bg-emerald-950/40 text-emerald-300" },
    real_but_not_proven_causal: { label: "real (correlation)", cls: "bg-sky-950/40 text-sky-300" },
  };
  const entry = map[basis] ?? { label: basis, cls: "bg-zinc-800 text-zinc-400" };
  return <span className={`ml-1.5 px-1.5 py-0.5 rounded text-xs uppercase tracking-wide ${entry.cls}`}>{entry.label}</span>;
}

function GapBadge() {
  return <span className="ml-1.5 px-1.5 py-0.5 rounded text-xs uppercase tracking-wide bg-zinc-800 text-zinc-500">gap</span>;
}

function NoAccessNote({ theme }: { theme: Theme }) {
  return <div className={tc(theme, "text-xs text-zinc-600 italic", "text-xs text-zinc-400 italic")}>No access with your current role.</div>;
}

function Tile({
  theme,
  label,
  value,
  basis,
  sub,
}: {
  theme: Theme;
  label: string;
  value: string;
  basis?: Basis;
  sub?: string;
}) {
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

function SectionCard({
  theme,
  title,
  color,
  children,
}: {
  theme: Theme;
  title: string;
  color: string;
  children: React.ReactNode;
}) {
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

export function BusinessHealthBoard({
  theme,
  focusDepartment,
  onClearFocus,
}: {
  theme: Theme;
  // Optional drill-down: when set (e.g. "sales"), only that one department's
  // SectionCard renders instead of the full 5-card grid -- the real
  // click-to-drill-down mechanism Readiness' new Overview heatmap
  // (components/ReadinessOverviewBoard.tsx) uses, reusing this board's own
  // per-department rendering rather than building a second one.
  focusDepartment?: string | null;
  onClearFocus?: () => void;
}) {
  const [data, setData] = useState<BusinessHealthOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  function refresh() {
    setLoading(true);
    setError(null);
    getBusinessHealthOverview()
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : "Unable to load Business Health data."))
      .finally(() => setLoading(false));
  }

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => refresh(), []);

  const sales = data?.sales;
  const service = data?.service;
  const finance = data?.finance;
  const marketing = data?.marketing;
  const inventory = data?.inventory;

  const financeCollectionsOk = finance && !("error" in (finance.collections ?? {}));
  const financePortfolioOk = finance && !("error" in (finance.portfolio_quality ?? {}));
  const marketingRoiOk = marketing && !("error" in (marketing.roi ?? {}));

  return (
    <div className={tc(theme, "flex-1 flex flex-col min-h-0 bg-brand-ink text-white overflow-y-auto", "flex-1 flex flex-col min-h-0 bg-white text-black overflow-y-auto")}>
      <div className={tc(theme, "px-4 py-3 border-b border-zinc-800", "px-4 py-3 border-b border-zinc-200")}>
        <div className="flex items-center justify-between">
          <div>
            <div className="text-sm font-brand font-semibold">
              Business Health
              {focusDepartment && <span className="text-zinc-500 font-normal"> — {focusDepartment}</span>}
            </div>
            <div className="text-xs text-zinc-500 mt-0.5">
              The executive layer above every department -- real Sales/Service/Finance/Marketing/Inventory KPIs, each
              honestly labeled real, heuristic, or simulated. No single blended score is shown; see the note below.
            </div>
          </div>
          {focusDepartment && onClearFocus && (
            <WorkButton type="submit"
              onClick={onClearFocus}
              className="ml-3 shrink-0 px-2.5 py-1 rounded text-xs bg-zinc-800 text-zinc-200 hover:bg-zinc-700"
            >
              Show all departments
            </WorkButton>
          )}
        </div>
      </div>

      {error && <div className="mx-4 mt-2 text-xs text-red-400">{error}</div>}

      <div className="flex-1 p-4 space-y-3">
        {data?.overall_score_note && (
          <div className={tc(theme, "text-xs text-zinc-400 bg-zinc-900/60 border border-zinc-800 rounded px-3 py-2", "text-xs text-zinc-600 bg-zinc-50 border border-zinc-200 rounded px-3 py-2")}>
            {data.overall_score_note}
          </div>
        )}

        {loading ? (
          <div className="text-sm text-zinc-500">Loading…</div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
            {/* Sales */}
            {(!focusDepartment || focusDepartment === "sales") && (
            <SectionCard theme={theme} title="Sales Health" color={RIBBON[0]}>
              <Tile theme={theme} label="Lead Volume" value={fmtNum(sales?.lead_volume?.value)} basis={sales?.lead_volume?.basis} />
              <Tile
                theme={theme}
                label="Show Rate"
                value={sales?.show_rate?.value !== undefined && sales?.show_rate?.value !== null ? fmtPct((sales.show_rate.value as number) * 100) : "—"}
                basis={sales?.show_rate?.basis}
                sub={`${fmtNum(sales?.show_rate?.appointments_shown)} of ${fmtNum(sales?.show_rate?.appointments_scheduled)} shown`}
              />
              <Tile theme={theme} label="Close Rate" value={fmtPct(sales?.close_rate?.value)} basis={sales?.close_rate?.basis} sub={sales?.close_rate?.note} />
              <Tile theme={theme} label="Gross Profit" value={fmtMoney(sales?.gross_profit?.value)} basis={sales?.gross_profit?.basis} sub={sales?.gross_profit?.note} />
              <div className="col-span-2">
                <Tile
                  theme={theme}
                  label="Pipeline Coverage"
                  value={`${fmtNum(sales?.pipeline_coverage?.active_pipeline_count)} active opportunities`}
                  basis={sales?.pipeline_coverage?.basis}
                />
                {sales?.pipeline_coverage?.not_yet_tracked && (
                  <div className="text-xs text-zinc-600 mt-1 flex items-center">
                    Coverage ratio (vs. quota) <GapBadge />
                  </div>
                )}
              </div>
            </SectionCard>
            )}

            {/* Service */}
            {(!focusDepartment || focusDepartment === "service") && (
            <SectionCard theme={theme} title="Service Health" color={RIBBON[1]}>
              <Tile theme={theme} label="RO Volume" value={fmtNum(service?.ro_volume?.total)} basis={service?.ro_volume?.basis} sub={`${fmtNum(service?.ro_volume?.open)} open`} />
              <Tile
                theme={theme}
                label="Technician Utilization"
                value={fmtPct(service?.technician_utilization?.avg_utilization_pct_today)}
                basis={service?.technician_utilization?.basis}
                sub={`${fmtNum(service?.technician_utilization?.technician_count)} techs, ${fmtNum(service?.technician_utilization?.overloaded_technician_count)} overloaded`}
              />
              <Tile
                theme={theme}
                label="Customer Retention"
                value={service?.customer_retention?.avg_visits_per_year !== null && service?.customer_retention?.avg_visits_per_year !== undefined ? `${fmtNum(service.customer_retention.avg_visits_per_year)} visits/yr` : "—"}
                basis={service?.customer_retention?.basis}
                sub={`${fmtNum(service?.customer_retention?.lost_customers?.count)} lost customers`}
              />
              <Tile
                theme={theme}
                label="Shop Capacity"
                value={`${fmtNum(service?.shop_capacity?.open_ro_count)} open ROs`}
                basis={service?.shop_capacity?.basis as Basis}
                sub={`${fmtNum(service?.shop_capacity?.unassigned_ro_count)} unassigned`}
              />
            </SectionCard>
            )}

            {/* Finance */}
            {(!focusDepartment || focusDepartment === "finance") && (
            <SectionCard theme={theme} title="Finance Health" color={RIBBON[2]}>
              <Tile
                theme={theme}
                label="Funding Time"
                value={finance?.funding_time?.avg_days_in_transit !== null && finance?.funding_time?.avg_days_in_transit !== undefined ? `${fmtNum(finance.funding_time.avg_days_in_transit)} days` : "—"}
                basis={finance?.funding_time?.basis}
                sub={`${fmtNum(finance?.funding_time?.contracts_in_transit)} in transit`}
              />
              <div>
                <Tile theme={theme} label="Contract Accuracy" value="—" />
                <div className="text-xs text-zinc-600 mt-1 flex items-center">No validation model exists <GapBadge /></div>
              </div>
              {financeCollectionsOk ? (
                <Tile
                  theme={theme}
                  label="Collections"
                  value={`${fmtNum((finance?.collections as { total_in_queue?: number })?.total_in_queue)} in queue`}
                  basis="real"
                  sub={`${fmtNum((finance?.collections as { recovery_risk_count?: number })?.recovery_risk_count)} recovery risk`}
                />
              ) : (
                <div>
                  <div className="text-xs uppercase tracking-wide text-zinc-500 mb-1">Collections</div>
                  <NoAccessNote theme={theme} />
                </div>
              )}
              {financePortfolioOk ? (
                <Tile
                  theme={theme}
                  label="Portfolio Quality"
                  value={fmtMoney((finance?.portfolio_quality as { total_outstanding_balance?: number })?.total_outstanding_balance)}
                  basis={(finance?.portfolio_quality as { basis?: Basis })?.basis}
                  sub={`${fmtNum((finance?.portfolio_quality as { active_loans?: number })?.active_loans)} active loans`}
                />
              ) : (
                <div>
                  <div className="text-xs uppercase tracking-wide text-zinc-500 mb-1">Portfolio Quality</div>
                  <NoAccessNote theme={theme} />
                </div>
              )}
            </SectionCard>
            )}

            {/* Marketing */}
            {(!focusDepartment || focusDepartment === "marketing") && (
            <SectionCard theme={theme} title="Marketing Health" color={RIBBON[3]}>
              <Tile theme={theme} label="Lead Volume" value={fmtNum(marketing?.lead_volume?.value)} basis={marketing?.lead_volume?.basis} />
              {marketingRoiOk ? (
                <Tile
                  theme={theme}
                  label="Campaign ROI"
                  value={fmtMoney(((marketing?.roi as { campaign_roi?: { total_revenue?: number } })?.campaign_roi)?.total_revenue)}
                  basis={((marketing?.roi as { campaign_roi?: { basis?: Basis } })?.campaign_roi)?.basis}
                  sub="real correlation, not proven causal"
                />
              ) : (
                <div>
                  <div className="text-xs uppercase tracking-wide text-zinc-500 mb-1">Campaign ROI</div>
                  <NoAccessNote theme={theme} />
                </div>
              )}
              <Tile
                theme={theme}
                label="Website Traffic"
                value={`${fmtNum(marketing?.website_traffic?.total_page_views)} views`}
                basis={marketing?.website_traffic?.basis}
                sub={`${fmtNum(marketing?.website_traffic?.human_views)} human / ${fmtNum(marketing?.website_traffic?.bot_views)} bot`}
              />
              <Tile
                theme={theme}
                label="Campaign Performance"
                value={`${fmtNum((marketing?.campaign_performance as { total_campaigns?: number })?.total_campaigns)} campaigns`}
                basis="real"
              />
            </SectionCard>
            )}

            {/* Inventory */}
            {(!focusDepartment || focusDepartment === "inventory") && (
            <SectionCard theme={theme} title="Inventory Health" color={RIBBON[4]}>
              <Tile
                theme={theme}
                label="Turn Rate"
                value={(inventory?.turn_rate as { annualized_turn_rate?: number })?.annualized_turn_rate !== undefined ? `${fmtNum((inventory?.turn_rate as { annualized_turn_rate?: number })?.annualized_turn_rate)}x / yr` : "—"}
                basis={(inventory?.turn_rate as { basis?: Basis })?.basis}
              />
              <Tile
                theme={theme}
                label="Aging"
                value={(inventory?.aging as { average_days_in_stock?: number })?.average_days_in_stock !== undefined ? `${fmtNum((inventory?.aging as { average_days_in_stock?: number })?.average_days_in_stock)} avg days` : "—"}
                basis={(inventory?.aging as { basis?: Basis })?.basis}
              />
              <Tile
                theme={theme}
                label="Recon Time"
                value={fmtPct(inventory?.recon_time?.avg_checklist_completion_pct)}
                basis={inventory?.recon_time?.basis}
                sub="checklist completion, not true duration"
              />
              <Tile
                theme={theme}
                label="Days Supply"
                value={(inventory?.days_supply as { market_days_supply?: number })?.market_days_supply !== undefined ? `${fmtNum((inventory?.days_supply as { market_days_supply?: number })?.market_days_supply)} days` : "—"}
                basis={(inventory?.days_supply as { basis?: Basis })?.basis}
              />
            </SectionCard>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
