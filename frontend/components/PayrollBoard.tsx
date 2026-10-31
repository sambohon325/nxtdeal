"use client";
import { WorkButton, WorkInput, WorkSelect } from "./WorkspaceUi";
import { WorkField } from "./WorkField";

// Payroll board (Phase 5, 2026-07-25): a self-service time clock for everyone, plus
// pay-plan setup, payroll runs, and pay statements for Admin/Operations. Backed by
// lib/payroll.ts (backend/api/routers/payroll.py). Withholding is a simplified flat-rate
// model — statements are marked as such.
import { useEffect, useState } from "react";
import { getSession } from "@/lib/auth";
import {
  getClockStatus,
  clockIn,
  clockOut,
  setPayPlan,
  runPayroll,
  listPayrollRuns,
  listPayStatements,
  type TimeEntry,
  type PayrollRun,
  type PayStatement,
} from "@/lib/payroll";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

function money(v: number): string {
  return `$${v.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}

export function PayrollBoard({ theme }: { theme: Theme }) {
  const session = getSession();
  const isAdmin = session?.role === "ADMIN" || session?.role === "OPERATIONS";

  const [open, setOpen] = useState<TimeEntry | null>(null);
  const [runs, setRuns] = useState<PayrollRun[]>([]);
  const [statements, setStatements] = useState<PayStatement[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [flash, setFlash] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // pay plan form
  const [planEmp, setPlanEmp] = useState("");
  const [planType, setPlanType] = useState("hourly");
  const [hourly, setHourly] = useState("");
  const [salary, setSalary] = useState("");
  const [perDeal, setPerDeal] = useState("");
  const [pctGross, setPctGross] = useState("");
  const [state, setState] = useState("TX");

  // run form
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");

  const card = tc(theme, "rounded-md border border-zinc-800 bg-zinc-900/60 p-3", "rounded-md border border-zinc-200 bg-white p-3");
  const input = tc(theme, "rounded-md bg-zinc-950 border border-zinc-800 px-2 py-1.5 text-[12px]", "rounded-md bg-white border border-zinc-300 px-2 py-1.5 text-[12px]");

  function refresh() {
    getClockStatus().then((s) => setOpen(s.open_entry)).catch(() => {});
    listPayStatements().then((s) => setStatements(s.statements)).catch(() => {});
    if (isAdmin) listPayrollRuns().then((r) => setRuns(r.runs)).catch(() => {});
  }

  useEffect(refresh, []);

  async function punch(inOut: "in" | "out") {
    setBusy(true); setError(null);
    try {
      await (inOut === "in" ? clockIn() : clockOut());
      refresh();
    } catch (e) { setError(e instanceof Error ? e.message : "Clock error."); } finally { setBusy(false); }
  }

  async function savePlan() {
    setBusy(true); setError(null); setFlash(null);
    try {
      await setPayPlan(planEmp, {
        plan_type: planType,
        hourly_rate: Number(hourly) || 0,
        annual_salary: Number(salary) || 0,
        per_deal_commission: Number(perDeal) || 0,
        pct_front_gross: Number(pctGross) || 0,
        state,
      });
      setFlash(`Pay plan saved for ${planEmp}.`);
    } catch (e) { setError(e instanceof Error ? e.message : "Couldn't save plan."); } finally { setBusy(false); }
  }

  async function doRun() {
    setBusy(true); setError(null); setFlash(null);
    try {
      const r = await runPayroll(start, end);
      setFlash(`Payroll run complete: ${r.statement_count} paycheck(s), ${money(r.total_net)} net.`);
      refresh();
    } catch (e) { setError(e instanceof Error ? e.message : "Couldn't run payroll."); } finally { setBusy(false); }
  }

  return (
    <div className="flex-1 min-h-0 flex flex-col overflow-y-auto">
      <div className="px-3 pt-3 shrink-0">
        <div className="text-base font-brand">Payroll</div>
        <div className="text-xs text-zinc-500">Clock in and out, run payroll, and view paychecks. Tax withholding is a simplified flat-rate model.</div>
      </div>

      {error && <div className="mx-3 mt-2 rounded-md bg-red-500/10 border border-red-500/30 px-3 py-2 text-xs text-red-400">{error}</div>}
      {flash && <div className="mx-3 mt-2 rounded-md bg-brand-teal/15 border border-brand-teal/40 px-3 py-2 text-xs text-brand-teal">{flash}</div>}

      <div className="p-3 space-y-3">
        {/* time clock */}
        <div className={card + " flex items-center gap-3"}>
          <div className="text-xs font-semibold">Time Clock</div>
          {open ? (
            <>
              <span className="text-xs text-brand-teal">Clocked in since {new Date(open.clock_in_at).toLocaleTimeString()}</span>
              <WorkButton type="submit" onClick={() => punch("out")} disabled={busy} className="ml-auto text-xs px-3 py-1.5 rounded-md bg-zinc-700 text-white disabled:opacity-50">Clock out</WorkButton>
            </>
          ) : (
            <>
              <span className="text-xs text-zinc-500">Not clocked in</span>
              <WorkButton type="submit" onClick={() => punch("in")} disabled={busy} className="ml-auto text-xs px-3 py-1.5 rounded-md bg-brand-teal text-black font-semibold disabled:opacity-50">Clock in</WorkButton>
            </>
          )}
        </div>

        {isAdmin && (
          <div className={card}>
            <div className="text-xs font-semibold mb-2">Set a pay plan</div>
            <div className="flex flex-wrap gap-2 items-center">
              <WorkField label="Employee ID"><WorkInput className={input} placeholder="Employee ID" value={planEmp} onChange={(e) => setPlanEmp(e.target.value)} /></WorkField>
              <WorkField label="Plan Type"><WorkSelect className={input} value={planType} onChange={(e) => setPlanType(e.target.value)}>
                <option value="hourly">Hourly</option>
                <option value="salary">Salary</option>
                <option value="commission">Commission</option>
                <option value="hybrid">Hybrid</option>
              </WorkSelect></WorkField>
              {(planType === "hourly" || planType === "hybrid") && <WorkField label="$/hr"><WorkInput className={input + " w-24"} placeholder="$/hr" value={hourly} onChange={(e) => setHourly(e.target.value)} /></WorkField>}
              {(planType === "salary" || planType === "hybrid") && <WorkField label="Annual $"><WorkInput className={input + " w-28"} placeholder="Annual $" value={salary} onChange={(e) => setSalary(e.target.value)} /></WorkField>}
              {(planType === "commission" || planType === "hybrid") && <WorkField label="$/deal"><WorkInput className={input + " w-28"} placeholder="$/deal" value={perDeal} onChange={(e) => setPerDeal(e.target.value)} /></WorkField>}
              {(planType === "commission" || planType === "hybrid") && <WorkField label="% front gross (0.25)"><WorkInput className={input + " w-28"} placeholder="% front gross (0.25)" value={pctGross} onChange={(e) => setPctGross(e.target.value)} /></WorkField>}
              <WorkField label="State"><WorkInput className={input + " w-16"} placeholder="State" value={state} onChange={(e) => setState(e.target.value.toUpperCase())} /></WorkField>
              <WorkButton type="submit" onClick={savePlan} disabled={busy || !planEmp} className="text-xs px-3 py-1.5 rounded-md bg-zinc-700 text-white disabled:opacity-50">Save plan</WorkButton>
            </div>
          </div>
        )}

        {isAdmin && (
          <div className={card}>
            <div className="text-xs font-semibold mb-2">Run payroll</div>
            <div className="flex gap-2 items-center">
              <label className="text-xs text-zinc-500">Period</label>
              <WorkInput aria-label="Period" type="date" className={input} value={start} onChange={(e) => setStart(e.target.value)} />
              <span className="text-zinc-600">→</span>
              <WorkInput aria-label="Period" type="date" className={input} value={end} onChange={(e) => setEnd(e.target.value)} />
              <WorkButton type="submit" onClick={doRun} disabled={busy || !start || !end} className="text-xs px-3 py-1.5 rounded-md bg-brand-teal text-black font-semibold disabled:opacity-50">Run payroll</WorkButton>
            </div>
            {runs.length > 0 && (
              <div className="mt-2 space-y-0.5">
                {runs.map((r) => (
                  <div key={r.id} className="text-xs text-zinc-500">
                    {r.period_start} → {r.period_end}: {r.statement_count} paychecks · {money(r.total_gross)} gross · {money(r.total_net)} net
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        <div className={card}>
          <div className="text-xs font-semibold mb-2">{isAdmin ? "Recent pay statements" : "My pay statements"}</div>
          {statements.length === 0 && <div className="text-xs text-zinc-500">No statements yet.</div>}
          {statements.map((s) => (
            <div key={s.id} className="text-xs py-1 border-b border-zinc-800/50">
              <div className="flex items-center gap-2">
                <span className="flex-1 truncate">{s.employee_name}</span>
                <span className="text-zinc-500">{s.period_start} → {s.period_end}</span>
                <span className="font-semibold text-brand-teal">{money(s.net_pay)}</span>
              </div>
              <div className="text-xs text-zinc-500">
                gross {money(s.gross_pay)} · tax {money(s.taxes.total)} ({s.state}) · {s.plan_type}
                {s.hours ? ` · ${s.hours}h` : ""}{s.earnings.commission ? ` · comm ${money(s.earnings.commission)}` : ""}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export default PayrollBoard;
