"use client";
import { WorkButton } from "./WorkspaceUi";

// Service's "Overview" item, second slice of Service's rebuild -- Sam's spec:
// a Service Command Center (real clickable waiting-buckets), Today's Risks
// (actionable), and an Advisor Dashboard. Rendered ABOVE the generic Overview
// KPI board, same "ABOVE, not instead of" precedent SalesOverviewBoard.tsx/
// OperationsOverviewBoard.tsx established -- every other department's
// Overview stays the generic board, unchanged.
import { PRODUCT_ACCENT_COLORS } from "@/lib/productTheme";
import { useEffect, useState } from "react";
import { getServiceMyDay, type ServiceMyDay, type RoBucket } from "@/lib/serviceOverview";
import { getRoCatalog, type RoCatalog } from "@/lib/repairOrders";
import { RoWorkspaceModal } from "@/components/RepairOrderWorkspaceBoard";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const RIBBON = PRODUCT_ACCENT_COLORS;

function BucketCard({
  theme,
  label,
  bucket,
  color,
  onOpen,
}: {
  theme: Theme;
  label: string;
  bucket: RoBucket | { count: number };
  color: string;
  onOpen: (roId: string) => void;
}) {
  const ros = "repair_orders" in bucket ? bucket.repair_orders : [];
  return (
    <div className={tc(theme, "relative overflow-hidden rounded-lg border border-black/20 bg-brand-charcoal p-3 pl-4", "relative overflow-hidden rounded-lg border border-zinc-200 bg-zinc-50 p-3 pl-4")}>
      <span className="nxt-accent absolute left-0 top-0 bottom-0 w-2.5" style={{ background: color, clipPath: "polygon(0 0, 100% 0, 45% 100%, 0 100%)" }} />
      <div className="text-2xl font-semibold">{bucket.count}</div>
      <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1.5">{label}</div>
      {ros.length > 0 && (
        <div className="space-y-0.5">
          {ros.slice(0, 4).map((r) => (
            <WorkButton type="submit" key={r.id} onClick={() => onOpen(r.id)} className="block w-full text-left text-xs text-brand-blue hover:underline truncate">
              {r.service_number} — {r.description}
            </WorkButton>
          ))}
        </div>
      )}
    </div>
  );
}

export function ServiceOverviewBoard({ theme }: { theme: Theme }) {
  const [data, setData] = useState<ServiceMyDay | null>(null);
  const [catalog, setCatalog] = useState<RoCatalog | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedRo, setSelectedRo] = useState<string | null>(null);

  function refresh() {
    setLoading(true);
    setError(null);
    Promise.all([getServiceMyDay(), getRoCatalog()])
      .then(([d, c]) => { setData(d); setCatalog(c); })
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }

  useEffect(refresh, []);

  const cardClass = tc(theme, "rounded-lg border border-black/20 bg-brand-charcoal p-3", "rounded-lg border border-zinc-200 bg-zinc-50 p-3");

  if (loading) {
    return <div className="p-4 text-sm text-zinc-500">Loading Service Overview…</div>;
  }

  if (!data || error) {
    return <div role="alert" className="p-4"><p>{error || "Unable to load service records."}</p><WorkButton type="submit" onClick={refresh}>Try again</WorkButton></div>;
  }

  const advisor = data.advisor_dashboard;

  return (
    <div className={tc(theme, "p-4 space-y-3 bg-brand-ink text-white", "p-4 space-y-3 bg-white text-black")}>
      <div>
        <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">
          My Day — {advisor.advisor.name || advisor.advisor.id}
        </div>
        <div className="grid grid-cols-4 gap-3">
          <div className={cardClass}>
            <div className="text-2xl font-semibold">{advisor.my_appointments.today_count}</div>
            <div className="text-xs font-brand uppercase tracking-wide text-zinc-500">My Appointments Today</div>
          </div>
          <BucketCard theme={theme} label="My Waiting Customers" bucket={advisor.my_waiting_customers} color={RIBBON[0]} onOpen={setSelectedRo} />
          <BucketCard theme={theme} label="My Pending Approvals" bucket={advisor.my_pending_approvals} color={RIBBON[1]} onOpen={setSelectedRo} />
          <BucketCard theme={theme} label="My Vehicles Ready" bucket={advisor.my_vehicles_ready} color={RIBBON[2]} onOpen={setSelectedRo} />
        </div>
      </div>

      {data.is_manager_view && data.command_center && (
        <div>
          <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Service Command Center</div>
          <div className="grid grid-cols-3 gap-3 mb-2">
            <BucketCard theme={theme} label="Open ROs" bucket={data.command_center.open_ros} color={RIBBON[0]} onOpen={setSelectedRo} />
            <BucketCard theme={theme} label="Waiting Approval" bucket={data.command_center.waiting_approval} color={RIBBON[1]} onOpen={setSelectedRo} />
            <BucketCard theme={theme} label="Waiting Parts" bucket={data.command_center.waiting_parts} color={RIBBON[2]} onOpen={setSelectedRo} />
          </div>
          <div className="grid grid-cols-3 gap-3">
            <BucketCard theme={theme} label="Waiting Technician" bucket={data.command_center.waiting_technician} color={RIBBON[3]} onOpen={setSelectedRo} />
            <BucketCard theme={theme} label="Waiting Delivery" bucket={data.command_center.waiting_delivery} color={RIBBON[0]} onOpen={setSelectedRo} />
            <BucketCard theme={theme} label="Comebacks" bucket={data.command_center.comebacks} color={RIBBON[1]} onOpen={setSelectedRo} />
          </div>
          <div className="text-xs text-zinc-600 italic mt-1">{data.command_center.note}</div>
        </div>
      )}

      {data.is_manager_view && data.todays_risks && (
        <div>
          <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Today&rsquo;s Risks</div>
          <div className="grid grid-cols-3 gap-3 mb-2">
            <BucketCard theme={theme} label="Customers Waiting" bucket={data.todays_risks.customers_waiting} color={RIBBON[2]} onOpen={setSelectedRo} />
            <BucketCard theme={theme} label="Jobs Behind Schedule" bucket={data.todays_risks.jobs_behind_schedule} color={RIBBON[3]} onOpen={setSelectedRo} />
            <BucketCard theme={theme} label="Parts Delayed" bucket={data.todays_risks.parts_delayed} color={RIBBON[0]} onOpen={setSelectedRo} />
          </div>
          <div className={cardClass}>
            <div className="text-2xl font-semibold">{data.todays_risks.techs_overloaded.count}</div>
            <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1">Techs Overloaded</div>
            {data.todays_risks.techs_overloaded.technicians.map((t) => (
              <div key={t.technician_id} className="text-xs text-zinc-500">{t.technician_id}: {t.hours_booked_today}h booked (assumed {t.assumed_capacity_hours}h capacity)</div>
            ))}
            <div className="text-xs text-zinc-600 italic mt-1">{data.todays_risks.techs_overloaded.note}</div>
          </div>
          <div className="text-xs text-zinc-600 italic mt-1">{data.todays_risks.promised_today_not_started.not_yet_tracked}</div>
        </div>
      )}

      {selectedRo && catalog && (
        <RoWorkspaceModal
          theme={theme}
          roId={selectedRo}
          catalog={catalog}
          onClose={() => setSelectedRo(null)}
          onChanged={refresh}
        />
      )}
    </div>
  );
}
