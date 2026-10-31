"use client";

// Sales Pro / Sales "Today" & "Pipeline" — live off GET /sales/my-day (core/sales_overview.py).
// Shows the rep's daily numbers and the real action-center tasks; manager callers also see the
// manager dashboard rollup. Failed reads show an explicit retryable state.

import { type AppDef, type AppScreen } from "@/lib/apps/registry";
import { getMyDay, type MyDay } from "@/lib/salesOverview";
import { useAsync, WiredScreen, StatGrid, ListCard, Row, EmptyNote } from "./kit";
import { AppContactActions } from "@/components/apps/AppContactActions";

export function SalesToday({ app, screen }: { app: AppDef; screen: AppScreen }) {
  const { loading, error, data, reload } = useAsync<MyDay>(() => getMyDay(), []);

  const d = data?.daily_dashboard;
  const t = data?.my_tasks;
  const stats = d
    ? [
        { label: "Today's leads", value: d.todays_leads.count },
        { label: "Today's shows", value: d.todays_shows.count },
        { label: "Write-ups", value: d.write_ups_today.count },
        { label: "Deliveries", value: d.deliveries_today.count },
      ]
    : [];

  return (
    <WiredScreen app={app} screen={screen} loading={loading} error={error} empty={!data} onRetry={reload}>


      {t && (
        <ListCard title="Contact today" count={t.leads_requiring_contact_today.count}>
          {t.leads_requiring_contact_today.items.map((it) => (
            <div key={it.id} className="rounded-lg border border-white/5 px-3 py-2">
              <div className="min-w-0">
                <div className="truncate text-sm text-zinc-100">{it.name || "Lead"}</div>
                <div className="truncate text-[11px] text-zinc-500">
                  {[it.source, it.pipeline_state].filter(Boolean).join(" · ") || it.phone || ""}
                </div>
              </div>
              <div className="mt-1.5">
                <AppContactActions customerId={it.id} phone={it.phone} name={it.name || undefined} size="xs" />
              </div>
            </div>
          ))}
          {t.leads_requiring_contact_today.count === 0 && <EmptyNote>All caught up — no contacts due.</EmptyNote>}
        </ListCard>
      )}

      {t && t.missing_follow_ups.count > 0 && (
        <ListCard title="Missing follow-ups" count={t.missing_follow_ups.count}>
          {t.missing_follow_ups.items.map((it) => (
            <Row key={it.id} primary={it.name || "Lead"} secondary={it.pipeline_state || undefined} meta={`${it.overdue_task_count} overdue`} />
          ))}
        </ListCard>
      )}

      {t && t.unsold_showroom_visits.count > 0 && (
        <ListCard title="Unsold showroom visits" count={t.unsold_showroom_visits.count}>
          {t.unsold_showroom_visits.items.map((it) => (
            <Row key={it.id} primary={it.name || "Visitor"} secondary={it.last_contact ? `Last: ${it.last_contact}` : undefined} />
          ))}
        </ListCard>
      )}

      {stats.length > 0 && <section aria-label="Today's activity"><h3 className="mb-3 text-base font-semibold text-white">Today's activity</h3><StatGrid app={app} stats={stats} /></section>}

      {data?.is_manager_view && data.manager_dashboard && (
        <ListCard title="Store (manager view)">
          <Row primary="Unworked leads" meta={data.manager_dashboard.unworked_leads.count} />
          <Row primary="Overdue follow-ups" meta={data.manager_dashboard.overdue_follow_ups.count} />
          <Row primary="Deals stuck in F&I" meta={data.manager_dashboard.deals_stuck_in_fi.count} />
          <Row primary="Trades awaiting appraisal" meta={data.manager_dashboard.trades_awaiting_appraisal.count} />
        </ListCard>
      )}
    </WiredScreen>
  );
}
