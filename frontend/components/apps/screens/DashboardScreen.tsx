"use client";

// DevHub Dashboard screen (2026-10-24).
// Shows the programming schedule dashboard: progress by phase, issues by type,
// work by assignee, hours remaining, security issues and blockers.

import { useAsync, WiredScreen, StatGrid, ListCard, Row, Badge } from "./kit";
import { getDashboard, type PSDashboard, type PSItem } from "@/lib/programmingSchedule";
import { TYPE_ICONS, PHASE_ORDER, ASSIGNEE_LABELS, STATUS_COLORS } from "@/lib/programmingSchedule";
import { type AppDef, type AppScreen } from "@/lib/apps/registry";

export function DashboardScreen({ app, screen }: { app: AppDef; screen: AppScreen }) {
  const { loading, error, data: dash, reload } = useAsync<PSDashboard>(
    () => getDashboard(), []
  );

  return (
    <WiredScreen
      app={app} screen={screen} loading={loading} error={error}
      children={dash ? <DashboardContent dash={dash} app={app} /> : ""}
      onRetry={reload}
    />
  );
}

function DashboardContent({ dash: data, app }: { dash: PSDashboard; app: AppDef }) {
  const dash = data.dashboard;
  const phaseStats = PHASE_ORDER
    .filter((p) => dash.by_phase[p])
    .map((p) => ({
      label: p,
      value: `${dash.by_phase[p].done}/${dash.by_phase[p].total}`,
      hint: `${dash.by_phase[p].remaining_hours.toFixed(0)}h left`,
    }));

  const typeStats = Object.entries(dash.by_type).map(([k, v]) => ({
    label: k,
    value: v,
  }));

  const assigneeStats = Object.entries(dash.by_assignee).map(([k, v]) => ({
    label: ASSIGNEE_LABELS[k as keyof typeof ASSIGNEE_LABELS] || k,
    value: v,
  }));

  const totalHours = dash.remaining_hours + dash.logged_hours;
  const completedPct = totalHours > 0
    ? Math.round((dash.logged_hours / totalHours) * 100)
    : 0;

  return (
    <>
      <StatGrid app={app} stats={[
        { label: "Total items", value: dash.total },
        { label: "Completed", value: `${dash.completed} (${Math.round((dash.completed / dash.total) * 100)}%)` },
        { label: "Remaining hours", value: `${dash.remaining_hours.toFixed(0)}h` },
        { label: "Security issues", value: dash.security_issues, hint: dash.blockers > 0 ? `${dash.blockers} blocked` : undefined },
      ]} />

      <div className="mt-6 rounded-2xl border border-white/10 bg-white/[0.03] p-5 backdrop-blur-sm">
        <h3 className="mb-3 text-sm font-semibold text-white">Hours progress</h3>
        <div className="h-2 w-full rounded-full bg-white/10">
          <div
            className="h-2 rounded-full bg-sky-400"
            style={{ width: `${completedPct}%` }}
          />
        </div>
        <div className="mt-2 flex gap-4 text-xs text-zinc-400">
          <span>{dash.logged_hours.toFixed(0)}h logged</span>
          <span>{dash.remaining_hours.toFixed(0)}h remaining</span>
        </div>
      </div>

      <ListCard title="Phase progress" count={phaseStats.length}>
        {phaseStats.map((s) => (
          <Row key={s.label} primary={s.label} secondary={s.hint} meta={s.value} />
        ))}
      </ListCard>

      <ListCard title="Issues by type" count={typeStats.length}>
        {typeStats.map((s) => (
          <Row key={s.label} primary={s.label} meta={s.value} />
        ))}
      </ListCard>

      <ListCard title="Work by assignee" count={assigneeStats.length}>
        {assigneeStats.map((s) => (
          <Row key={s.label} primary={s.label} meta={s.value} />
        ))}
      </ListCard>
    </>
  );
}
