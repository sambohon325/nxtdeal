"use client";
import { WorkButton, WorkSelect, WorkInput , WorkStat} from "./WorkspaceUi";
import { WorkField } from "./WorkField";

// Readiness reframe -- Performance Readiness (2026-07-19), item #4 of Sam's
// 10-item proposed structure. Sam's own words: "This is where scores become
// useful." Goal Tracking against real pace: a real, ADMIN/OPERATIONS-settable
// monthly target per department (core/system_config.py's department_goals)
// compared against a real current-month linear pace projection AND core/
// prediction.py's own real ledger forecast (core/performance_readiness.py).
// An unset goal or missing pace/forecast data renders honestly -- never a
// fabricated 100%. The pre-existing confidence-score content (current/
// target %, variance, risk factors against the 90% go-live threshold) is a
// genuinely different concept -- data trustworthiness, not performance vs. a
// goal -- and is shown below as its own section, reused via the generic
// GET /menu/data route rather than duplicated (see lib/performanceReadiness.ts).
import { useEffect, useState } from "react";
import {
  getPerformanceReadinessOverview,
  getReadinessMenuOverview,
  type PerformanceReadinessOverview,
  type ReadinessMenuOverview,
  type DepartmentPerformanceReadiness,
} from "@/lib/performanceReadiness";
import { getDepartmentGoals, setDepartmentGoal, clearDepartmentGoal, GOAL_TRACKED_DEPARTMENTS } from "@/lib/systemConfig";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const RIBBON: Record<string, string> = { sales: "#2B68AB", service: "#3FBCC4", marketing: "#FBCF09" };

function fmtNum(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number") {
    return Number.isInteger(value) ? value.toLocaleString() : value.toFixed(2);
  }
  return String(value);
}

function fmtGoalValue(value: number | null | undefined, unit: string): string {
  if (value === null || value === undefined) return "—";
  if (unit === "$") return `$${value.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
  return `${value.toLocaleString(undefined, { maximumFractionDigits: 0 })} ${unit}`;
}

function readinessColor(pct: number | null): string {
  if (pct === null) return "text-zinc-500";
  if (pct >= 100) return "text-emerald-400";
  if (pct >= 80) return "text-amber-400";
  return "text-red-400";
}

function Kpi({ theme, label, value, color }: { theme: Theme; label: string; value: string; color: string }) { return <WorkStat label={label} value={value}/>; }

function Btn({ onClick, children, disabled, tone }: { onClick: () => void; children: React.ReactNode; disabled?: boolean; tone?: "primary" | "danger" }) {
  return (
    <WorkButton type="submit"
      onClick={onClick}
      disabled={disabled}
      className={`text-xs px-2.5 py-1 rounded font-medium disabled:opacity-40 ${
        tone === "danger" ? "bg-red-900/60 text-red-200 hover:bg-red-900" : tone === "primary" ? "bg-zinc-200 text-black hover:bg-white" : "bg-zinc-800 text-zinc-300 hover:bg-zinc-700"
      }`}
    >
      {children}
    </WorkButton>
  );
}

function DepartmentCard({ theme, dept }: { theme: Theme; dept: DepartmentPerformanceReadiness }) {
  const color = RIBBON[dept.department] ?? "#7C5CBF";
  return (
    <div className={tc(theme, "relative overflow-hidden rounded-lg border border-zinc-800 bg-brand-charcoal p-4", "relative overflow-hidden rounded-lg border border-zinc-200 bg-white p-4")}>
      <span className="absolute left-0 top-0 bottom-0 w-1.5" style={{ background: color }} />
      <div className="pl-2">
        <div className="flex items-center justify-between">
          <div className="text-sm font-brand font-semibold capitalize">{dept.department}</div>
          <div className={`text-2xl font-bold ${readinessColor(dept.readiness_pct)}`}>
            {dept.readiness_pct !== null ? `${dept.readiness_pct}%` : "—"}
          </div>
        </div>
        <div className="text-xs text-zinc-500 mt-0.5">{dept.label}</div>

        <div className="grid grid-cols-2 gap-2 mt-3">
          <div className={tc(theme, "rounded border border-zinc-800 bg-zinc-900/60 px-2.5 py-1.5", "rounded border border-zinc-200 bg-zinc-50 px-2.5 py-1.5")}>
            <div className="text-xs uppercase tracking-wide text-zinc-500">Goal</div>
            <div className="text-sm font-semibold">{dept.goal_set ? fmtGoalValue(dept.goal, dept.unit) : "Not set"}</div>
          </div>
          <div className={tc(theme, "rounded border border-zinc-800 bg-zinc-900/60 px-2.5 py-1.5", "rounded border border-zinc-200 bg-zinc-50 px-2.5 py-1.5")}>
            <div className="text-xs uppercase tracking-wide text-zinc-500">
              {dept.readiness_source === "ledger_forecast" ? "Forecast (used)" : "Current Pace"}
            </div>
            <div className="text-sm font-semibold">
              {dept.current_month_pace ? fmtGoalValue(dept.current_month_pace.projected_month_total, dept.unit) : "—"}
            </div>
            {dept.current_month_pace && (
              <div className="text-xs text-zinc-600 mt-0.5">
                {fmtNum(dept.current_month_pace.actual_to_date)} so far, day {dept.current_month_pace.days_elapsed} of{" "}
                {dept.current_month_pace.days_in_month}
              </div>
            )}
          </div>
        </div>

        {dept.ledger_forecast && (
          <div className="mt-2 text-xs text-zinc-500">
            Ledger forecast (core/prediction.py, month horizon): {fmtNum(dept.ledger_forecast.predicted_value)}{" "}
            {dept.ledger_forecast.unit} — basis <span className="uppercase">{dept.ledger_forecast.basis}</span>,{" "}
            {dept.ledger_forecast.confidence_pct}% confidence
          </div>
        )}
        {dept.department === "service" && (
          <div className="mt-2 text-xs text-zinc-600 italic">
            No ledger forecast shown -- core/prediction.py's Service metric is repair_orders (a count), not $ labor
            revenue, a real unit mismatch against this $ goal.
          </div>
        )}

        <div className={tc(theme, "mt-2 text-xs text-zinc-400", "mt-2 text-xs text-zinc-600")}>{dept.status}</div>
      </div>
    </div>
  );
}

export function PerformanceReadinessBoard({ theme }: { theme: Theme }) {
  const [data, setData] = useState<PerformanceReadinessOverview | null>(null);
  const [menuData, setMenuData] = useState<ReadinessMenuOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [goalDept, setGoalDept] = useState<string>(GOAL_TRACKED_DEPARTMENTS[0]);
  const [goalValue, setGoalValue] = useState<string>("");
  const [saving, setSaving] = useState(false);
  const [formMessage, setFormMessage] = useState<string | null>(null);

  function refresh() {
    setLoading(true);
    setError(null);
    Promise.all([getPerformanceReadinessOverview(), getReadinessMenuOverview()])
      .then(([overview, menu]) => {
        setData(overview);
        setMenuData(menu);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Unable to load Performance Readiness data."))
      .finally(() => setLoading(false));
  }

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => refresh(), []);

  async function handleSetGoal() {
    const num = Number(goalValue);
    if (!goalValue || Number.isNaN(num) || num <= 0) {
      setFormMessage("Enter a positive number.");
      return;
    }
    setSaving(true);
    setFormMessage(null);
    try {
      await setDepartmentGoal(goalDept, num);
      setFormMessage(`Goal set for ${goalDept}.`);
      setGoalValue("");
      refresh();
    } catch (e) {
      setFormMessage(e instanceof Error ? e.message : "Unable to set goal.");
    } finally {
      setSaving(false);
    }
  }

  async function handleClearGoal(department: string) {
    setSaving(true);
    setFormMessage(null);
    try {
      await clearDepartmentGoal(department);
      setFormMessage(`Goal cleared for ${department}.`);
      refresh();
    } catch (e) {
      setFormMessage(e instanceof Error ? e.message : "Unable to clear goal.");
    } finally {
      setSaving(false);
    }
  }

  const departments = data?.departments ?? [];
  const setCount = departments.filter((d) => d.goal_set).length;
  const atOrAboveCount = departments.filter((d) => d.readiness_pct !== null && d.readiness_pct >= 100).length;
  const belowCount = departments.filter((d) => d.readiness_pct !== null && d.readiness_pct < 100).length;

  return (
    <div className={tc(theme, "flex-1 flex flex-col min-h-0 bg-brand-ink text-white overflow-y-auto", "flex-1 flex flex-col min-h-0 bg-white text-black overflow-y-auto")}>
      <div className={tc(theme, "px-4 py-3 border-b border-zinc-800", "px-4 py-3 border-b border-zinc-200")}>
        <div className="text-sm font-brand font-semibold">Performance Readiness</div>
        <div className="text-xs text-zinc-500 mt-0.5">
          Goal Tracking against real pace -- a real ADMIN/OPERATIONS-settable monthly target per department compared
          against a real current-month pace projection and core/prediction.py's own ledger forecast. An unset goal
          shows honestly, never a fabricated 100%.
        </div>
      </div>

      {error && <div className="mx-4 mt-2 text-xs text-red-400">{error}</div>}

      <div className="flex-1 p-4 space-y-4">
        {loading ? (
          <div className="text-sm text-zinc-500">Loading…</div>
        ) : (
          <>
            <div className="grid grid-cols-3 gap-3">
              <Kpi theme={theme} label="Goals Set" value={`${setCount} / ${departments.length}`} color="#2B68AB" />
              <Kpi theme={theme} label="At/Above Goal" value={String(atOrAboveCount)} color="#3FBCC4" />
              <Kpi theme={theme} label="Below Goal" value={String(belowCount)} color="#EE3C25" />
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
              {departments.map((d) => (
                <DepartmentCard key={d.department} theme={theme} dept={d} />
              ))}
            </div>

            {/* Admin goal editing -- the backend itself enforces ADMIN/OPERATIONS,
                a non-admin caller here will simply see the real error below. */}
            <div className={tc(theme, "rounded-lg border border-zinc-800 bg-zinc-900/40 p-3", "rounded-lg border border-zinc-200 bg-zinc-50 p-3")}>
              <div className="text-xs font-brand font-semibold mb-2">Set / Clear a Monthly Goal (ADMIN/OPERATIONS)</div>
              <div className="flex flex-wrap items-center gap-2">
                <WorkField label="Department"><WorkSelect
                  value={goalDept}
                  onChange={(e) => setGoalDept(e.target.value)}
                  className="text-xs px-2 py-1 rounded bg-zinc-900 border border-zinc-700 text-zinc-200"
                >
                  {GOAL_TRACKED_DEPARTMENTS.map((d) => (
                    <option key={d} value={d}>
                      {d}
                    </option>
                  ))}
                </WorkSelect></WorkField>
                <WorkField label="Monthly target"><WorkInput
                  value={goalValue}
                  onChange={(e) => setGoalValue(e.target.value)}
                  placeholder="Monthly target (e.g. 120)"
                  className="text-xs px-2 py-1 rounded bg-zinc-900 border border-zinc-700 text-zinc-200 placeholder:text-zinc-600 w-48"
                /></WorkField>
                <Btn onClick={handleSetGoal} disabled={saving} tone="primary">
                  Set Goal
                </Btn>
                <Btn onClick={() => handleClearGoal(goalDept)} disabled={saving} tone="danger">
                  Clear Goal
                </Btn>
              </div>
              {formMessage && <div className="text-xs text-zinc-400 mt-2">{formMessage}</div>}
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

            {/* Pre-existing confidence-score content -- a genuinely different
                concept (data trustworthiness) from Goal Tracking above. */}
            <div className={tc(theme, "rounded-lg border border-zinc-800 bg-brand-charcoal p-4", "rounded-lg border border-zinc-200 bg-white p-4")}>
              <div className="text-sm font-brand font-semibold mb-1">Data Confidence Scores</div>
              <div className="text-xs text-zinc-500 mb-3">
                Distinct from Goal Tracking above -- whether there's enough real ledger history to trust a forecast,
                against the real 90% go-live threshold (core/prediction.py's department_readiness()).
              </div>
              {!menuData?.data_confidence_scores || menuData.data_confidence_scores.length === 0 ? (
                <div className="text-xs text-zinc-500">No confidence scores available.</div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                  {menuData.data_confidence_scores.map((s) => (
                    <div
                      key={s.department}
                      className={tc(theme, "rounded border border-zinc-800 bg-zinc-900/60 px-3 py-2", "rounded border border-zinc-200 bg-zinc-50 px-3 py-2")}
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-semibold capitalize">{s.department}</span>
                        <span className={`text-xs ${s.status === "At/Above Target" ? "text-emerald-400" : "text-amber-400"}`}>
                          {s.status}
                        </span>
                      </div>
                      <div className="text-xs text-zinc-500 mt-0.5">
                        {s.current_score_pct}% (target {s.target_score_pct}%, variance {s.variance_pct > 0 ? "+" : ""}
                        {s.variance_pct}%)
                      </div>
                      {s.risk_factors.length > 0 && (
                        <div className="text-xs text-zinc-600 mt-1">{s.risk_factors.join(" ")}</div>
                      )}
                    </div>
                  ))}
                </div>
              )}
              {menuData?.not_yet_tracked && (
                <div className="mt-2 text-xs text-zinc-600">
                  {Object.values(menuData.not_yet_tracked).join(" ")}
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
