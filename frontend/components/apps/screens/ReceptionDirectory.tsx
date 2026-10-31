"use client";

// Receptionist "Directory" — the store roster live off GET /sales/employees +
// GET /service/employees (core/sales_overview.py / appointments_api.py), with tap-to-notify
// stubs. Read of two rosters merged and deduped.

import { type AppDef, type AppScreen } from "@/lib/apps/registry";
import { getSalesEmployees } from "@/lib/salesOverview";
import { getServiceEmployees } from "@/lib/appointments";
import { useAsync, WiredScreen, ListCard, Row, EmptyNote } from "./kit";

type Person = { id: string; name: string; title: string | null; dept: string };

export function ReceptionDirectory({ app, screen }: { app: AppDef; screen: AppScreen }) {
  const { loading, error, data, reload } = useAsync<Person[]>(async () => {
    const [sales, service] = await Promise.all([
      getSalesEmployees(),
      getServiceEmployees(),
    ]);
    const byId = new Map<string, Person>();
    sales.forEach((e) => byId.set(e.id, { ...e, dept: "Sales" }));
    service.forEach((e) => { if (!byId.has(e.id)) byId.set(e.id, { ...e, dept: "Service" }); });
    return [...byId.values()].sort((a, b) => a.name.localeCompare(b.name));
  }, []);

  const people = data ?? [];

  return (
    <WiredScreen app={app} screen={screen} loading={loading} error={error} empty={!data} onRetry={reload}>
      <ListCard title="Staff directory" count={people.length}>
        {people.map((p) => (
          <Row key={p.id} primary={p.name} secondary={[p.title, p.dept].filter(Boolean).join(" · ") || undefined} />
        ))}
        {people.length === 0 && <EmptyNote>No staff records available.</EmptyNote>}
      </ListCard>
    </WiredScreen>
  );
}
