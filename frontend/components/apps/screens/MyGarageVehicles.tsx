"use client";

// My Garage "My Vehicles" — the verified customer's own vehicles, equity/trade value, and
// service history (App Suite roadmap Phase 7 data). Sits behind CustomerVerifyGate: the
// customer verifies once, then this fetches THEIR data from the token-scoped /public/garage
// endpoints (core/garage.py). Equity figures are desk estimates, labeled as such.

import { type AppDef, type AppScreen, accentOf } from "@/lib/apps/registry";
import { getMyVehicles, type GarageVehiclesView } from "@/lib/garage";
import { CustomerVerifyGate } from "@/components/apps/CustomerVerifyGate";
import { useAsync, StatGrid, ListCard, Row, EmptyNote, CustomerLoadError } from "./kit";

function money(v: number | null): string {
  return v === null || v === undefined ? "—" : `$${Math.round(v).toLocaleString()}`;
}

function Inner({ app }: { app: AppDef }) {
  const accent = accentOf(app);
  const { loading, error, data, reload } = useAsync<GarageVehiclesView>(() => getMyVehicles(), []);

  if (loading) {
    return <div className="flex justify-center py-12"><div className={`h-6 w-6 animate-spin rounded-full border-2 border-white/15 ${accent.text} border-t-current`} /></div>;
  }
  if (error) {
    return <CustomerLoadError subject="your vehicle records" onRetry={reload} />;
  }
  if (!data) return null;

  const eq = data.equity;
  return (
    <div className="space-y-4">
      <div className="text-sm text-zinc-300">Welcome back, {data.customer.name.split(" ")[0] || "there"}.</div>

      <StatGrid
        app={app}
        stats={[
          { label: "Your vehicles", value: data.vehicle_count },
          { label: "Est. equity", value: money(eq.equity_amount), hint: eq.status },
          { label: "Service visits", value: data.service_summary.count },
        ]}
      />

      {eq.equity_amount !== null && (
        <div className="rounded-2xl border border-white/10 bg-white/[0.05] p-4">
          <div className="text-sm font-semibold text-white">Your equity &amp; trade value</div>
          <div className="mt-1 text-2xl font-bold text-white">{money(eq.equity_amount)}</div>
          <div className="text-[11px] text-zinc-500">
            Est. value {money(eq.estimated_value)} − payoff {money(eq.estimated_payoff)}
            {eq.lease_maturing_soon ? " · lease maturing soon" : ""}
          </div>
          {eq.disclaimer && <div className="mt-1 text-[10px] text-zinc-500">{eq.disclaimer}</div>}
        </div>
      )}

      <ListCard title="My vehicles" count={data.vehicle_count}>
        {data.vehicles.length === 0 && <EmptyNote>No vehicles on file yet.</EmptyNote>}
        {data.vehicles.map((v, i) => {
          const title = [v.year, v.make, v.model].filter(Boolean).join(" ") || String(v.id ?? `Vehicle ${i + 1}`);
          return <Row key={String(v.id ?? i)} primary={title} secondary={(v.vin as string) || undefined} />;
        })}
      </ListCard>

      <ListCard title="Recent service" count={data.service_summary.count}>
        {data.service_summary.recent.length === 0 && <EmptyNote>No service history yet.</EmptyNote>}
        {data.service_summary.recent.map((r, i) => (
          <Row key={i} primary={String(r.description ?? "Service")} secondary={String(r.service_date ?? "")} meta={r.cost ? `$${r.cost}` : undefined} />
        ))}
      </ListCard>
    </div>
  );
}

export function MyGarageVehicles({ app, screen }: { app: AppDef; screen: AppScreen }) {
  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-xl font-bold text-white">{screen.heading}</h2>
        <p className="mt-0.5 text-sm text-zinc-400">{screen.intro}</p>
      </div>
      <CustomerVerifyGate what="your equity, trade-in value, and service history">
        <Inner app={app} />
      </CustomerVerifyGate>
    </div>
  );
}
