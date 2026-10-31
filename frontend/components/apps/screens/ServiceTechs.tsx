"use client";

// Service Operations "Techs" — technician dispatch, derived live from the RO board
// (GET /repair-orders/board) grouped by assigned technician, alongside the service roster
// (GET /service/employees). Shows each tech's active workload; unassigned ROs surface at the top.

import { type AppDef, type AppScreen } from "@/lib/apps/registry";
import { getRoBoard, type RoBoard, type RoBrief, type RoStage } from "@/lib/repairOrders";
import { getServiceEmployees, type ServiceEmployeeBrief } from "@/lib/appointments";
import { useAsync, WiredScreen, ListCard, Row, EmptyNote } from "./kit";

const STAGES: RoStage[] = [
  "Check-In", "RO Written", "Inspection", "Estimate", "Customer Approval",
  "Parts", "Repair", "Quality Control", "Delivery", "Follow-Up",
];

type TechGroup = { key: string; name: string; ros: RoBrief[] };

export function ServiceTechs({ app, screen }: { app: AppDef; screen: AppScreen }) {
  const { loading, error, data, reload } = useAsync<{ board: RoBoard; roster: ServiceEmployeeBrief[] }>(async () => {
    const [board, roster] = await Promise.all([
      getRoBoard(),
      getServiceEmployees(),
    ]);
    return { board, roster };
  }, []);

  const groups: TechGroup[] = [];
  if (data) {
    const nameById = new Map(data.roster.map((e) => [e.id, e.name]));
    const byTech = new Map<string, RoBrief[]>();
    for (const stage of STAGES) {
      for (const ro of data.board[stage] ?? []) {
        const key = ro.technician || "__unassigned__";
        if (!byTech.has(key)) byTech.set(key, []);
        byTech.get(key)!.push(ro);
      }
    }
    for (const [key, ros] of byTech) {
      const name = key === "__unassigned__" ? "Unassigned" : nameById.get(key) || key;
      groups.push({ key, name, ros });
    }
    groups.sort((a, b) => (a.key === "__unassigned__" ? -1 : b.key === "__unassigned__" ? 1 : b.ros.length - a.ros.length));
  }

  return (
    <WiredScreen app={app} screen={screen} loading={loading} error={error} empty={!data} onRetry={reload}>
      {groups.length === 0 && <EmptyNote>No repair orders on the board to dispatch.</EmptyNote>}
      {groups.map((g) => (
        <ListCard key={g.key} title={g.name} count={g.ros.length}>
          {g.ros.map((ro) => (
            <Row key={ro.id} primary={`${ro.service_number} · ${ro.description || "Service"}`} secondary={ro.ro_stage} meta={ro.pay_type || undefined} />
          ))}
        </ListCard>
      ))}
    </WiredScreen>
  );
}
