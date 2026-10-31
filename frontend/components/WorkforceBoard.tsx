"use client";
import { WorkButton, WorkInput , WorkStat} from "./WorkspaceUi";
import {RecordCollection} from "./RecordCollection";
import { WorkField } from "./WorkField";

// Operations' new "Workforce" Top Menu item (2026-07-19). Directory (real
// roster + seniority tier), Shift Scheduling, Time-Off Requests (a real
// manager-tier approval gate), a computed-live Coverage view, and a
// Performance panel reusing the real lead-workload/employee-value engines.
import { PRODUCT_ACCENT_COLORS } from "@/lib/productTheme";
import { useEffect, useMemo, useState } from "react";
import {
  getWorkforceOverview,
  getDirectory,
  listShifts,
  scheduleShift,
  completeShift,
  markNoShow,
  cancelShift,
  listTimeOff,
  requestTimeOff,
  approveTimeOff,
  denyTimeOff,
  cancelTimeOff,
  getCoverage,
  type WorkforceOverview,
  type Directory,
  type Shift,
  type TimeOffRequest,
  type Coverage,
} from "@/lib/workforce";
import { CoachingPanel } from "@/components/CoachingPanel";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const RIBBON = PRODUCT_ACCENT_COLORS;

const TIER_COLOR: Record<string, string> = {
  staff: "#3FBCC4",
  manager: "#FBCF09",
  executive: "#EE3C25",
};

function Kpi({ theme, label, value, color }: { theme: Theme; label: string; value: string; color: string }) { return <WorkStat label={label} value={value}/>; }

function Pill({ children, tone }: { children: React.ReactNode; tone?: string }) {
  return (
    <span
      className="text-xs px-2 py-0.5 rounded-full font-brand uppercase tracking-wide"
      style={{ background: tone ? `${tone}22` : "rgba(255,255,255,0.08)", color: tone ?? "#a1a1aa" }}
    >
      {children}
    </span>
  );
}

const TABS = [
  ["overview", "Overview"],
  ["directory", "Directory"],
  ["scheduling", "Scheduling"],
  ["timeoff", "Time-Off"],
  ["coaching", "Coaching"],
] as const;

export function WorkforceBoard({ theme }: { theme: Theme }) {
  const [tab, setTab] = useState<(typeof TABS)[number][0]>("overview");
  const [overview, setOverview] = useState<WorkforceOverview | null>(null);
  const [directory, setDirectory] = useState<Directory | null>(null);
  const [shifts, setShifts] = useState<Shift[]>([]);
  const [timeOff, setTimeOff] = useState<TimeOffRequest[]>([]);
  const [coverage, setCoverage] = useState<Coverage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  function refreshOverview() {
    setLoading(true);
    setError(null);
    getWorkforceOverview()
      .then(setOverview)
      .catch((e) => setError(e instanceof Error ? e.message : "Unable to load Workforce data."))
      .finally(() => setLoading(false));
  }

  useEffect(refreshOverview, []);

  useEffect(() => {
    if (tab === "directory" && !directory) {
      getDirectory().then(setDirectory).catch(() => setDirectory(null));
    }
    if (tab === "scheduling") {
      listShifts().then((r) => setShifts(r.shifts)).catch(() => setShifts([]));
    }
    if (tab === "timeoff") {
      listTimeOff().then((r) => setTimeOff(r.requests)).catch(() => setTimeOff([]));
    }
  }, [tab]); // eslint-disable-line react-hooks/exhaustive-deps

  function refreshScheduling() {
    listShifts().then((r) => setShifts(r.shifts)).catch(() => setShifts([]));
  }

  function refreshTimeOff() {
    listTimeOff().then((r) => setTimeOff(r.requests)).catch(() => setTimeOff([]));
  }

  const upcomingByDate = useMemo(() => {
    const byDate: Record<string, Shift[]> = {};
    for (const s of shifts) {
      byDate[s.shift_date] = byDate[s.shift_date] || [];
      byDate[s.shift_date].push(s);
    }
    return Object.entries(byDate).sort(([a], [b]) => a.localeCompare(b));
  }, [shifts]);

  // -- New Shift form state --
  const [newShift, setNewShift] = useState({ employee_id: "", shift_date: "", start_time: "09:00", end_time: "17:00", department: "", notes: "" });
  async function submitShift() {
    setActionError(null);
    try {
      await scheduleShift(newShift);
      setNewShift({ employee_id: "", shift_date: "", start_time: "09:00", end_time: "17:00", department: "", notes: "" });
      refreshScheduling();
      refreshOverview();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Unable to schedule shift.");
    }
  }

  // -- New Time-Off form state --
  const [newPto, setNewPto] = useState({ employee_id: "", start_date: "", end_date: "", reason: "" });
  async function submitPto() {
    setActionError(null);
    try {
      await requestTimeOff(newPto);
      setNewPto({ employee_id: "", start_date: "", end_date: "", reason: "" });
      refreshTimeOff();
      refreshOverview();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Unable to submit time-off request.");
    }
  }

  async function act(fn: () => Promise<unknown>, after: () => void) {
    setActionError(null);
    try {
      await fn();
      after();
      refreshOverview();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Action failed.");
    }
  }

  return (
    <div className={tc(theme, "flex-1 flex flex-col min-h-0 bg-brand-ink text-white overflow-y-auto", "flex-1 flex flex-col min-h-0 bg-white text-black overflow-y-auto")}>
      <div className={tc(theme, "grid grid-cols-4 gap-3 p-4 border-b border-zinc-800", "grid grid-cols-4 gap-3 p-4 border-b border-zinc-200")}>
        <Kpi theme={theme} label="Employees" value={String(overview?.directory.total ?? 0)} color={RIBBON[0]} />
        <Kpi theme={theme} label="Scheduled Today" value={String(overview?.coverage_today.scheduled_count ?? 0)} color={RIBBON[1]} />
        <Kpi theme={theme} label="Coverage Conflicts Today" value={String(overview?.coverage_today.conflict_count ?? 0)} color={RIBBON[3]} />
        <Kpi theme={theme} label="Pending Time-Off" value={String(overview?.pending_time_off_count ?? 0)} color={RIBBON[2]} />
      </div>

      <div className="flex items-center gap-1.5 px-4 py-2 border-b border-zinc-800">
        {TABS.map(([key, label]) => (
          <WorkButton data-work-view aria-pressed={tab === key} type="submit"
            key={key}
            onClick={() => setTab(key)}
            className={`text-xs px-2.5 py-1 rounded-full font-brand uppercase tracking-wide transition ${tab === key ? "bg-zinc-200 text-black font-medium" : "bg-zinc-200/10 text-zinc-400 hover:text-white"}`}
          >
            {label}
          </WorkButton>
        ))}
        <WorkButton type="submit" onClick={refreshOverview} className="ml-auto text-xs px-2.5 py-1 rounded-full bg-zinc-200/10 text-zinc-400 hover:text-white">
          ↻ Refresh
        </WorkButton>
      </div>

      {actionError && <div className="mx-4 mt-2 text-xs text-red-400">{actionError}</div>}

      <div className="flex-1 min-h-0 overflow-y-auto p-4 space-y-4">
        {loading && <div className="text-sm text-zinc-500">Loading…</div>}
        {error && <div className="text-sm text-red-400">{error}</div>}

        {!loading && !error && tab === "overview" && overview && (
          <>
            <div className={tc(theme, "rounded-lg border border-zinc-800 bg-brand-charcoal p-3", "rounded-lg border border-zinc-200 bg-zinc-50 p-3")}>
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">
                Coverage Today -- {overview.coverage_today.date}
              </div>
              {overview.coverage_today.conflicts.length > 0 && (
                <div className="mb-2">
                  <div className="text-xs text-red-400 mb-1">⚠ Conflicts (scheduled + approved time-off overlap)</div>
                  {overview.coverage_today.conflicts.map((s) => (
                    <div key={s.id} className="text-xs text-zinc-300">
                      {s.employee.name} -- {s.start_time}–{s.end_time} ({s.department})
                    </div>
                  ))}
                </div>
              )}
              <div className="text-xs text-zinc-500">
                {overview.coverage_today.scheduled.length} scheduled, {overview.coverage_today.on_approved_time_off_count} on approved time-off
              </div>
            </div>

            <div className={tc(theme, "rounded-lg border border-zinc-800 bg-brand-charcoal p-3", "rounded-lg border border-zinc-200 bg-zinc-50 p-3")}>
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Pending Time-Off Requests</div>
              {overview.pending_time_off.length === 0 && <div className="text-xs text-zinc-500">None pending.</div>}
              {overview.pending_time_off.map((r) => (
                <div key={r.id} className="flex items-center justify-between text-xs py-1 border-b border-zinc-800/60 last:border-0">
                  <span>{r.employee.name} -- {r.start_date} to {r.end_date}</span>
                  <span className="text-zinc-500">{r.reason}</span>
                </div>
              ))}
            </div>

            <div className={tc(theme, "rounded-lg border border-zinc-800 bg-brand-charcoal p-3", "rounded-lg border border-zinc-200 bg-zinc-50 p-3")}>
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Workforce Performance</div>
              <div className="text-xs text-zinc-500 mb-1">{overview.performance.lead_workload.note}</div>
              <RecordCollection>{overview.performance.lead_workload.employees.map((e) => (
                <div key={e.employee_id} className="flex items-center justify-between text-xs">
                  <span>{e.employee_id}</span>
                  <span className="text-zinc-500">{e.active_workload} active</span>
                </div>
              ))}</RecordCollection>
              {overview.performance.employee_value?.error && (
                <div className="text-xs text-zinc-600 mt-1">{String(overview.performance.employee_value.error)}</div>
              )}
              <div className="text-xs text-zinc-600 mt-2 space-y-0.5">
                {Object.values(overview.performance.not_yet_tracked).map((n, i) => (
                  <div key={i}>· {n}</div>
                ))}
              </div>
            </div>
          </>
        )}

        {!loading && tab === "directory" && directory && (
          <div className="space-y-2">
            <div className="text-xs text-zinc-500">
              {directory.total} employees -- {Object.entries(directory.by_department).map(([d, c]) => `${d}: ${c}`).join(" · ")}
            </div>
            {directory.employees.map((e) => (
              <div key={e.id} className={tc(theme, "flex items-center justify-between rounded-lg border border-zinc-800 bg-brand-charcoal p-2", "flex items-center justify-between rounded-lg border border-zinc-200 bg-zinc-50 p-2")}>
                <div>
                  <div className="text-sm font-medium">{e.name}</div>
                  <div className="text-xs text-zinc-500">{e.title} -- {e.department}</div>
                </div>
                <Pill tone={TIER_COLOR[e.tier ?? ""]}>{e.tier}</Pill>
              </div>
            ))}
          </div>
        )}

        {!loading && tab === "scheduling" && (
          <div className="space-y-4">
            <div className={tc(theme, "rounded-lg border border-zinc-800 bg-brand-charcoal p-3 space-y-2", "rounded-lg border border-zinc-200 bg-zinc-50 p-3 space-y-2")}>
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500">+ Schedule a Shift</div>
              <div className="grid grid-cols-3 gap-2">
                <WorkField label="Employee ID (EMP-...)"><WorkInput placeholder="Employee ID (EMP-...)" value={newShift.employee_id} onChange={(e) => setNewShift({ ...newShift, employee_id: e.target.value })} className="text-xs bg-transparent border border-zinc-700 rounded px-2 py-1" /></WorkField>
                <WorkField label="Shift date"><WorkInput type="date" value={newShift.shift_date} onChange={(e) => setNewShift({ ...newShift, shift_date: e.target.value })} className="text-xs bg-transparent border border-zinc-700 rounded px-2 py-1" /></WorkField>
                <WorkField label="Department"><WorkInput placeholder="Department" value={newShift.department} onChange={(e) => setNewShift({ ...newShift, department: e.target.value })} className="text-xs bg-transparent border border-zinc-700 rounded px-2 py-1" /></WorkField>
                <WorkField label="Start time"><WorkInput type="time" value={newShift.start_time} onChange={(e) => setNewShift({ ...newShift, start_time: e.target.value })} className="text-xs bg-transparent border border-zinc-700 rounded px-2 py-1" /></WorkField>
                <WorkField label="End time"><WorkInput type="time" value={newShift.end_time} onChange={(e) => setNewShift({ ...newShift, end_time: e.target.value })} className="text-xs bg-transparent border border-zinc-700 rounded px-2 py-1" /></WorkField>
                <WorkField label="Notes"><WorkInput placeholder="Notes" value={newShift.notes} onChange={(e) => setNewShift({ ...newShift, notes: e.target.value })} className="text-xs bg-transparent border border-zinc-700 rounded px-2 py-1" /></WorkField>
              </div>
              <WorkButton type="submit" onClick={submitShift} className="text-xs px-2.5 py-1 rounded-full bg-zinc-200 text-black font-medium">Schedule</WorkButton>
            </div>

            {upcomingByDate.map(([d, list]) => (
              <div key={d}>
                <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1">{d}</div>
                {list.map((s) => (
                  <div key={s.id} className={tc(theme, "flex items-center justify-between rounded-lg border border-zinc-800 bg-brand-charcoal p-2 mb-1", "flex items-center justify-between rounded-lg border border-zinc-200 bg-zinc-50 p-2 mb-1")}>
                    <div className="text-xs">
                      {s.employee.name} -- {s.start_time}–{s.end_time} ({s.department})
                      {s.notes && <div className="text-zinc-500">{s.notes}</div>}
                    </div>
                    <div className="flex items-center gap-2">
                      <Pill tone={s.status === "scheduled" ? "#3FBCC4" : s.status === "completed" ? "#22c55e" : s.status === "no_show" ? "#EE3C25" : "#71717a"}>{s.status}</Pill>
                      {s.status === "scheduled" && (
                        <>
                          <WorkButton type="submit" onClick={() => act(() => completeShift(s.id), refreshScheduling)} className="text-xs text-zinc-400 hover:text-white">✓ Complete</WorkButton>
                          <WorkButton type="submit" onClick={() => act(() => markNoShow(s.id), refreshScheduling)} className="text-xs text-zinc-400 hover:text-white">No-Show</WorkButton>
                          <WorkButton type="submit" onClick={() => act(() => cancelShift(s.id), refreshScheduling)} className="text-xs text-zinc-400 hover:text-white">Cancel</WorkButton>
                        </>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            ))}
          </div>
        )}

        {!loading && tab === "timeoff" && (
          <div className="space-y-4">
            <div className={tc(theme, "rounded-lg border border-zinc-800 bg-brand-charcoal p-3 space-y-2", "rounded-lg border border-zinc-200 bg-zinc-50 p-3 space-y-2")}>
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500">+ Request Time Off</div>
              <div className="grid grid-cols-3 gap-2">
                <WorkField label="Employee ID (EMP-...)"><WorkInput placeholder="Employee ID (EMP-...)" value={newPto.employee_id} onChange={(e) => setNewPto({ ...newPto, employee_id: e.target.value })} className="text-xs bg-transparent border border-zinc-700 rounded px-2 py-1" /></WorkField>
                <WorkField label="Start date"><WorkInput type="date" value={newPto.start_date} onChange={(e) => setNewPto({ ...newPto, start_date: e.target.value })} className="text-xs bg-transparent border border-zinc-700 rounded px-2 py-1" /></WorkField>
                <WorkField label="End date"><WorkInput type="date" value={newPto.end_date} onChange={(e) => setNewPto({ ...newPto, end_date: e.target.value })} className="text-xs bg-transparent border border-zinc-700 rounded px-2 py-1" /></WorkField>
                <WorkField label="Reason"><WorkInput placeholder="Reason" value={newPto.reason} onChange={(e) => setNewPto({ ...newPto, reason: e.target.value })} className="text-xs bg-transparent border border-zinc-700 rounded px-2 py-1 col-span-3" /></WorkField>
              </div>
              <WorkButton type="submit" onClick={submitPto} className="text-xs px-2.5 py-1 rounded-full bg-zinc-200 text-black font-medium">Submit Request</WorkButton>
            </div>

            <div className="text-xs text-zinc-500">
              Approving/denying requires the acting employee's own Title to resolve to manager-or-above.
            </div>

            {timeOff.map((r) => (
              <div key={r.id} className={tc(theme, "rounded-lg border border-zinc-800 bg-brand-charcoal p-2", "rounded-lg border border-zinc-200 bg-zinc-50 p-2")}>
                <div className="flex items-center justify-between">
                  <div className="text-sm">{r.employee.name} -- {r.start_date} to {r.end_date}</div>
                  <Pill tone={r.status === "approved" ? "#22c55e" : r.status === "denied" ? "#EE3C25" : r.status === "pending" ? "#FBCF09" : "#71717a"}>{r.status}</Pill>
                </div>
                <div className="text-xs text-zinc-500">{r.reason}</div>
                {r.decision_note && <div className="text-xs text-zinc-600">Note: {r.decision_note}</div>}
                {r.status === "pending" && (
                  <div className="flex gap-2 mt-1">
                    <WorkButton type="submit" onClick={() => act(() => approveTimeOff(r.id), refreshTimeOff)} className="text-xs text-zinc-400 hover:text-white">✓ Approve</WorkButton>
                    <WorkButton type="submit" onClick={() => act(() => denyTimeOff(r.id), refreshTimeOff)} className="text-xs text-zinc-400 hover:text-white">✕ Deny</WorkButton>
                    <WorkButton type="submit" onClick={() => act(() => cancelTimeOff(r.id), refreshTimeOff)} className="text-xs text-zinc-400 hover:text-white">Cancel</WorkButton>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {!loading && tab === "coaching" && <CoachingPanel theme={theme} />}
      </div>
    </div>
  );
}
