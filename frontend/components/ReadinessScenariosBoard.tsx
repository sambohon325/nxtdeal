"use client";
import { WorkButton, WorkInput, WorkSelect , WorkStat} from "./WorkspaceUi";

// Readiness reframe -- Scenarios / What-If Modeling (2026-07-19), item #6 of
// Sam's 10-item proposed structure. Sam's own words: "one of NXTDeal' most
// powerful features." Backend: core/readiness_scenarios.py / _api.py -- every
// projection here is a transparent FORMULA over this dealership's own real
// current-data ratios (real close rate, real avg gross per sale, real
// per-technician revenue, real observed portfolio yield/delinquency rate),
// never an invented multiplier. This board always shows the real ratios used
// (and any editable ASSUMPTION input, clearly flagged) right alongside the
// projected output, so the math is auditable, not a black box.
import { useEffect, useState } from "react";
import {
  getScenarioCatalog,
  runMarketingLeadVolumeScenario,
  runInventoryPricingScenario,
  runStaffingScenario,
  runFinancePortfolioScenario,
  type ScenarioCatalog,
  type MarketingLeadVolumeResult,
  type InventoryPricingResult,
  type StaffingResult,
  type FinancePortfolioResult,
} from "@/lib/readinessScenarios";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const SCENARIO_COLORS: Record<string, string> = {
  marketing_lead_volume: "#FBCF09",
  inventory_pricing: "#7C5CBF",
  staffing: "#3FBCC4",
  finance_portfolio: "#EE3C25",
};

function fmtNum(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toLocaleString(undefined, { maximumFractionDigits: digits });
}

function fmtCurrency(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `$${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}

function fmtPct(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}%`;
}

function Kpi({ theme, label, value, color }: { theme: Theme; label: string; value: string; color: string }) { return <WorkStat label={label} value={value}/>; }

function Btn({ onClick, children, disabled, tone }: { onClick: () => void; children: React.ReactNode; disabled?: boolean; tone?: "primary" | "danger" }) {
  return (
    <WorkButton type="submit"
      onClick={onClick}
      disabled={disabled}
      className={`text-xs px-3 py-1.5 rounded font-medium disabled:opacity-40 ${
        tone === "danger" ? "bg-red-900/60 text-red-200 hover:bg-red-900" : tone === "primary" ? "bg-zinc-200 text-black hover:bg-white" : "bg-zinc-800 text-zinc-300 hover:bg-zinc-700"
      }`}
    >
      {children}
    </WorkButton>
  );
}

function Field({ theme, label, value, onChange, placeholder, type = "number" }: { theme: Theme; label: string; value: string; onChange: (v: string) => void; placeholder?: string; type?: string }) {
  return (
    <label className="flex flex-col gap-1 text-xs text-zinc-500">
      {label}
      <WorkInput
        type={type}
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        className={tc(
          theme,
          "rounded border border-zinc-700 bg-black/30 px-2 py-1.5 text-sm text-white placeholder:text-zinc-600",
          "rounded border border-zinc-300 bg-white px-2 py-1.5 text-sm text-black placeholder:text-zinc-400"
        )}
      />
    </label>
  );
}

function RatioRow({ label, value, basis }: { label: string; value: React.ReactNode; basis?: string }) {
  return (
    <div className="flex items-start justify-between gap-3 py-1 border-b border-zinc-800/50 last:border-0">
      <div className="min-w-0">
        <div className="text-xs text-zinc-300">{label}</div>
        {basis && <div className="text-xs text-zinc-600 mt-0.5">{basis}</div>}
      </div>
      <div className="text-sm font-semibold whitespace-nowrap">{value}</div>
    </div>
  );
}

function AssumptionBadge() {
  return (
    <span className="inline-block rounded bg-amber-900/50 text-amber-300 text-xs font-semibold px-1.5 py-0.5 uppercase tracking-wide">
      Assumption, editable
    </span>
  );
}

function SectionCard({ theme, title, children }: { theme: Theme; title: string; children: React.ReactNode }) {
  return (
    <div className={tc(theme, "rounded-lg border border-zinc-800 bg-black/20 p-3", "rounded-lg border border-zinc-200 bg-zinc-50 p-3")}>
      <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">{title}</div>
      {children}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Marketing / Lead Volume
// ---------------------------------------------------------------------------

function MarketingScenarioForm({ theme }: { theme: Theme }) {
  const [additionalLeads, setAdditionalLeads] = useState("");
  const [additionalSpend, setAdditionalSpend] = useState("");
  const [assumedCost, setAssumedCost] = useState("45");
  const [result, setResult] = useState<MarketingLeadVolumeResult | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setRunning(true);
    setError(null);
    try {
      const leads = additionalLeads.trim() ? Number(additionalLeads) : null;
      const spend = additionalSpend.trim() ? Number(additionalSpend) : null;
      const cost = assumedCost.trim() ? Number(assumedCost) : null;
      const r = await runMarketingLeadVolumeScenario({
        additional_leads: leads,
        additional_ad_spend: leads === null ? spend : null,
        assumed_cost_per_lead: cost,
      });
      setResult(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to run scenario.");
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="space-y-3">
      <div className="text-xs text-zinc-500">
        Supply either Additional Leads directly (a 100% real chain), or Additional Ad Spend with an editable assumed
        cost-per-lead -- no real spend-to-lead ratio exists anywhere in this codebase yet, so that conversion is
        always an assumption you can change, never a computed fact.
      </div>
      <div className="grid grid-cols-3 gap-3">
        <Field theme={theme} label="Additional Leads" value={additionalLeads} onChange={setAdditionalLeads} placeholder="e.g. 100" />
        <Field theme={theme} label="OR Additional Ad Spend ($)" value={additionalSpend} onChange={setAdditionalSpend} placeholder="e.g. 5000" />
        <div className="flex flex-col gap-1">
          <Field theme={theme} label="Assumed Cost Per Lead ($)" value={assumedCost} onChange={setAssumedCost} />
          <AssumptionBadge />
        </div>
      </div>
      <Btn onClick={run} disabled={running} tone="primary">{running ? "Running…" : "Run Scenario"}</Btn>
      {error && <div className="text-xs text-red-400">{error}</div>}

      {result && (
        <div className="grid grid-cols-2 gap-3 pt-2">
          <SectionCard theme={theme} title={`Real Data Used (${result.input_path === "direct_lead_volume" ? "direct lead volume" : "derived from spend, via assumption"})`}>
            <RatioRow label="Close Rate" value={fmtPct(result.real_ratios_used.close_rate_pct)} basis={result.real_ratios_used.close_rate_basis} />
            <RatioRow label="Funded Deals" value={fmtNum(result.real_ratios_used.funded_deals_count, 0)} />
            <RatioRow label="Gross Profit (Funded Deals, Total)" value={fmtCurrency(result.real_ratios_used.gross_profit_funded_deals_total)} />
            <RatioRow label="Avg Gross Per Sale" value={fmtCurrency(result.real_ratios_used.avg_gross_per_sale)} basis={result.real_ratios_used.avg_gross_per_sale_basis} />
            {result.assumption_used && (
              <div className="mt-2 pt-2 border-t border-amber-900/40">
                <AssumptionBadge />
                <div className="text-xs text-amber-300 mt-1">${result.assumption_used.assumed_cost_per_lead}/lead assumed — {result.assumption_used.note}</div>
              </div>
            )}
          </SectionCard>
          <SectionCard theme={theme} title="Projected Output">
            <RatioRow label="Additional Leads" value={fmtNum(result.projection.additional_leads)} />
            <RatioRow label="Projected Additional Sales" value={fmtNum(result.projection.projected_additional_sales)} />
            <RatioRow label="Projected Additional Gross Profit" value={fmtCurrency(result.projection.projected_additional_gross_profit)} />
            <div className="text-xs text-zinc-600 mt-2">{result.projection.formula}</div>
          </SectionCard>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Inventory Pricing
// ---------------------------------------------------------------------------

function InventoryScenarioForm({ theme, priceBands }: { theme: Theme; priceBands: string[] }) {
  const [reduction, setReduction] = useState("500");
  const [band, setBand] = useState("all");
  const [result, setResult] = useState<InventoryPricingResult | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setRunning(true);
    setError(null);
    try {
      const r = await runInventoryPricingScenario({ price_reduction_amount: Number(reduction), price_band: band });
      setResult(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to run scenario.");
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="space-y-3">
      <div className="text-xs text-zinc-500">
        Vehicle has no acquisition-date field anywhere in this codebase, so no real day-based aging or
        price-elasticity/days-to-sell correlation exists to compute a &quot;days supply reduced&quot; figure from.
        Instead, this mechanically recomputes each real unsold vehicle&apos;s price band and real 3%-over-cost margin
        floor at the reduced price -- a real, traceable band-shift count, not a fabricated elasticity claim.
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Field theme={theme} label="Price Reduction ($)" value={reduction} onChange={setReduction} />
        <label className="flex flex-col gap-1 text-xs text-zinc-500">
          Price Band (optional filter)
          <WorkSelect
            value={band}
            onChange={(e) => setBand(e.target.value)}
            className={tc(theme, "rounded border border-zinc-700 bg-black/30 px-2 py-1.5 text-sm text-white", "rounded border border-zinc-300 bg-white px-2 py-1.5 text-sm text-black")}
          >
            <option value="all">All Bands</option>
            {priceBands.map((b) => (
              <option key={b} value={b}>{b}</option>
            ))}
          </WorkSelect>
        </label>
      </div>
      <Btn onClick={run} disabled={running} tone="primary">{running ? "Running…" : "Run Scenario"}</Btn>
      {error && <div className="text-xs text-red-400">{error}</div>}

      {result && (
        <div className="grid grid-cols-2 gap-3 pt-2">
          <SectionCard theme={theme} title="Real Data Used">
            <RatioRow label="Vehicles Evaluated" value={fmtNum(result.real_ratios_used.vehicles_evaluated, 0)} />
            <RatioRow label="Margin Floor" value="Cost × 1.03" basis={result.real_ratios_used.margin_floor_basis} />
            <RatioRow label="Price Bands" value="—" basis={result.real_ratios_used.price_band_basis} />
            <div className="mt-2 pt-2 border-t border-zinc-800">
              <div className="text-xs text-zinc-500 mb-1">Band Distribution Before → After</div>
              {Object.keys(result.projection.band_distribution_before).map((k) => (
                <RatioRow key={k} label={k} value={`${result.projection.band_distribution_before[k]} → ${result.projection.band_distribution_after[k]}`} />
              ))}
            </div>
          </SectionCard>
          <SectionCard theme={theme} title="Projected Output">
            <RatioRow label="Would Shift Price Band" value={fmtNum(result.projection.vehicles_would_shift_band, 0)} />
            <RatioRow label="Blocked by Margin Floor" value={fmtNum(result.projection.vehicles_blocked_by_margin_floor, 0)} />
            <RatioRow label="Unknown Cost (excluded)" value={fmtNum(result.projection.vehicles_unknown_cost, 0)} />
            <RatioRow label="Total Margin $ Given Up" value={fmtCurrency(result.projection.total_margin_dollars_given_up)} />
            <div className="text-xs text-zinc-600 mt-2">{result.projection.formula}</div>
            <div className="text-xs text-amber-400 mt-2">{result.not_yet_tracked.days_supply_reduction}</div>
          </SectionCard>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Staffing
// ---------------------------------------------------------------------------

function StaffingScenarioForm({ theme }: { theme: Theme }) {
  const [additional, setAdditional] = useState("2");
  const [result, setResult] = useState<StaffingResult | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setRunning(true);
    setError(null);
    try {
      const r = await runStaffingScenario({ additional_technicians: Number(additional) });
      setResult(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to run scenario.");
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="space-y-3">
      <div className="text-xs text-zinc-500">
        Uses this dealership&apos;s own real current technician headcount and real all-time per-technician revenue
        (Cost − PartsCost across every ServiceRecord), divided by the real number of elapsed months in this
        dealership&apos;s own data -- no assumed workdays/month or invented capacity-dollar constant.
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Field theme={theme} label="Additional Technicians" value={additional} onChange={setAdditional} />
      </div>
      <Btn onClick={run} disabled={running} tone="primary">{running ? "Running…" : "Run Scenario"}</Btn>
      {error && <div className="text-xs text-red-400">{error}</div>}

      {result && (
        <div className="grid grid-cols-2 gap-3 pt-2">
          <SectionCard theme={theme} title="Real Data Used">
            <RatioRow label="Current Technician Count" value={fmtNum(result.real_ratios_used.current_technician_count, 0)} basis={result.real_ratios_used.current_technician_count_basis} />
            <RatioRow label="Total Revenue (All Time)" value={fmtCurrency(result.real_ratios_used.total_revenue_all_time)} basis={result.real_ratios_used.total_revenue_basis} />
            <RatioRow label="Months of Data" value={fmtNum(result.real_ratios_used.months_of_data, 0)} basis={result.real_ratios_used.months_of_data_basis} />
            <RatioRow label="Avg Revenue / Tech (All Time)" value={fmtCurrency(result.real_ratios_used.avg_revenue_per_technician_all_time)} />
            <RatioRow label="Avg Monthly Revenue / Tech" value={fmtCurrency(result.real_ratios_used.avg_monthly_revenue_per_technician)} />
          </SectionCard>
          <SectionCard theme={theme} title="Projected Output">
            <RatioRow label="Capacity Increase" value={fmtPct(result.projection.capacity_increase_pct)} />
            <RatioRow label="Projected Monthly Labor Increase" value={fmtCurrency(result.projection.projected_monthly_labor_increase)} />
            <div className="text-xs text-zinc-600 mt-2">{result.projection.formula}</div>
          </SectionCard>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Finance Portfolio
// ---------------------------------------------------------------------------

function FinanceScenarioForm({ theme }: { theme: Theme }) {
  const [growthPct, setGrowthPct] = useState("10");
  const [result, setResult] = useState<FinancePortfolioResult | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setRunning(true);
    setError(null);
    try {
      const r = await runFinancePortfolioScenario({ portfolio_growth_pct: Number(growthPct) });
      setResult(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to run scenario.");
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="space-y-3">
      <div className="text-xs text-zinc-500">
        Uses this dealership&apos;s own real schedule-implied outstanding balance, real cash-basis interest income
        recognized (from actually-recorded Payments), and a delinquency rate aggregated from the SIMULATED per-loan
        delinquency layer (core/loan_servicing.py) -- every figure below scaled proportionally. ADMIN/OPERATIONS/
        FINANCE-only underlying data; other roles will see an honest access-denied note instead.
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Field theme={theme} label="Portfolio Growth (%)" value={growthPct} onChange={setGrowthPct} />
      </div>
      <Btn onClick={run} disabled={running} tone="primary">{running ? "Running…" : "Run Scenario"}</Btn>
      {error && <div className="text-xs text-red-400">{error}</div>}

      {result && result.error && (
        <div className="text-xs text-amber-400 pt-2">{result.error} — {result.note}</div>
      )}

      {result && result.real_ratios_used && result.projection && (
        <div className="grid grid-cols-2 gap-3 pt-2">
          <SectionCard theme={theme} title="Real Data Used">
            <RatioRow label="Current Outstanding Balance" value={fmtCurrency(result.real_ratios_used.current_total_outstanding_balance)} basis={result.real_ratios_used.current_total_outstanding_basis} />
            <RatioRow label="Current Total Loans" value={fmtNum(result.real_ratios_used.current_total_loans, 0)} />
            <RatioRow label="Current Delinquency Rate" value={fmtPct(result.real_ratios_used.current_delinquency_rate_pct)} basis={result.real_ratios_used.current_delinquency_rate_basis} />
            <RatioRow label="Interest Income Recognized" value={fmtCurrency(result.real_ratios_used.interest_income_recognized)} basis={result.real_ratios_used.interest_income_basis} />
            <RatioRow label="Observed Yield" value={fmtPct(result.real_ratios_used.observed_yield_pct)} basis={result.real_ratios_used.observed_yield_basis} />
          </SectionCard>
          <SectionCard theme={theme} title="Projected Output">
            <RatioRow label="Additional Outstanding Balance" value={fmtCurrency(result.projection.projected_additional_outstanding_balance)} />
            <RatioRow label="Additional Interest Income" value={fmtCurrency(result.projection.projected_additional_interest_income)} />
            <RatioRow label="Additional Loans" value={fmtNum(result.projection.projected_additional_loans)} />
            <RatioRow label="Additional Delinquent Loans" value={fmtNum(result.projection.projected_additional_delinquent_loans)} />
            <div className="text-xs text-zinc-600 mt-2">{result.projection.formula}</div>
          </SectionCard>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Board
// ---------------------------------------------------------------------------

export function ReadinessScenariosBoard({ theme }: { theme: Theme }) {
  const [catalog, setCatalog] = useState<ScenarioCatalog | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [active, setActive] = useState<string>("marketing_lead_volume");

  useEffect(() => {
    getScenarioCatalog()
      .then(setCatalog)
      .catch((e) => setError(e instanceof Error ? e.message : "Unable to load Scenarios catalog."))
      .finally(() => setLoading(false));
  }, []);

  const priceBandInput = catalog?.scenario_types.find((s) => s.key === "inventory_pricing")?.inputs.find((i) => i.key === "price_band");
  const priceBands = (priceBandInput?.options ?? []).filter((b) => b !== "all");

  const tabs = catalog?.scenario_types ?? [];

  return (
    <div className={tc(theme, "flex-1 flex flex-col min-h-0 bg-brand-ink text-white overflow-y-auto", "flex-1 flex flex-col min-h-0 bg-white text-black overflow-y-auto")}>
      <div className={tc(theme, "px-4 py-3 border-b border-zinc-800", "px-4 py-3 border-b border-zinc-200")}>
        <div className="text-sm font-brand font-semibold">Scenarios -- What-If Modeling</div>
        <div className="text-xs text-zinc-500 mt-0.5">
          Real, transparent, formula-based projections over this dealership&apos;s own real current-data ratios --
          never an invented multiplier. Every result shows exactly which real inputs and ratios were used.
        </div>
      </div>

      {error && <div className="mx-4 mt-2 text-xs text-red-400">{error}</div>}

      <div className="flex-1 p-4 space-y-4">
        {loading ? (
          <div className="text-sm text-zinc-500">Loading…</div>
        ) : (
          <>
            <div className="grid grid-cols-4 gap-3">
              {tabs.map((t) => (
                <Kpi key={t.key} theme={theme} label={t.label} value=" " color={SCENARIO_COLORS[t.key] ?? "#7C5CBF"} />
              ))}
            </div>

            <div className="flex gap-2 flex-wrap">
              {tabs.map((t) => (
                <WorkButton aria-pressed={active === t.key} type="submit"
                  key={t.key}
                  onClick={() => setActive(t.key)}
                  className={`text-xs px-3 py-1.5 rounded font-medium ${
                    active === t.key ? "bg-zinc-200 text-black" : "bg-zinc-800 text-zinc-300 hover:bg-zinc-700"
                  }`}
                >
                  {t.label}
                </WorkButton>
              ))}
            </div>

            {tabs.find((t) => t.key === active) && (
              <div className="text-xs text-zinc-500">{tabs.find((t) => t.key === active)!.description}</div>
            )}

            <div className={tc(theme, "rounded-lg border border-zinc-800 bg-black/10 p-4", "rounded-lg border border-zinc-200 bg-white p-4")}>
              {active === "marketing_lead_volume" && <MarketingScenarioForm theme={theme} />}
              {active === "inventory_pricing" && <InventoryScenarioForm theme={theme} priceBands={priceBands} />}
              {active === "staffing" && <StaffingScenarioForm theme={theme} />}
              {active === "finance_portfolio" && <FinanceScenarioForm theme={theme} />}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
