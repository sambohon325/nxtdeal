"use client";

// Service Operations "Manager" — the advisor/manager "My Day" off GET /service/my-day
// (core/service_overview.py). Advisor tiles for everyone; the command center + today's risks
// render only for a manager-tier caller (is_manager_view), same convention as the web board.

import { type AppDef, type AppScreen } from "@/lib/apps/registry";
import { getServiceMyDay, type ServiceMyDay } from "@/lib/serviceOverview";
import { useAsync, WiredScreen, StatGrid, ListCard, Row, EmptyNote } from "./kit";

export function ServiceManager({ app, screen }: { app: AppDef; screen: AppScreen }) {
  const { loading, error, data, reload } = useAsync<ServiceMyDay>(() => getServiceMyDay(), []);

  const ad = data?.advisor_dashboard;
  const cc = data?.command_center;

  return (
    <WiredScreen app={app} screen={screen} loading={loading} error={error} empty={!data} onRetry={reload}>
      {ad && (
        <>
          <div className="text-sm font-medium text-zinc-300">
            {ad.advisor.name ? `${ad.advisor.name}'s day` : "My day"}
          </div>
          <StatGrid
            app={app}
            stats={[
              { label: "Appts today", value: ad.my_appointments.today_count },
              { label: "This week", value: ad.my_appointments.this_week_count },
              { label: "Waiting", value: ad.my_waiting_customers.count },
              { label: "Ready", value: ad.my_vehicles_ready.count },
            ]}
          />
        </>
      )}

      {ad && ad.my_pending_approvals.count > 0 && (
        <ListCard title="Pending approvals" count={ad.my_pending_approvals.count}>
          {ad.my_pending_approvals.repair_orders.map((ro) => (
            <Row key={ro.id} primary={`${ro.service_number} · ${ro.description || "Service"}`} meta={ro.technician || undefined} />
          ))}
        </ListCard>
      )}

      {data?.is_manager_view && cc ? (
        <ListCard title="Command center">
          <Row primary="Open ROs" meta={cc.open_ros.count} />
          <Row primary="Waiting approval" meta={cc.waiting_approval.count} />
          <Row primary="Waiting parts" meta={cc.waiting_parts.count} />
          <Row primary="Waiting technician" meta={cc.waiting_technician.count} />
          <Row primary="Waiting delivery" meta={cc.waiting_delivery.count} />
          <Row primary="Comebacks" meta={cc.comebacks.count} />
        </ListCard>
      ) : (
        !data?.is_manager_view && <EmptyNote>Command center + today&apos;s risks show for manager-tier sign-ins.</EmptyNote>
      )}
    </WiredScreen>
  );
}
