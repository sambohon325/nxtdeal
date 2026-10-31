"use client";
import { WorkButton , WorkStat} from "./WorkspaceUi";

// Service department's "Shop Control" item, third slice of Service's
// rebuild -- Sam's own framing: "This should be the operational heart of
// the shop." A real drag-and-drop Technician Dispatch Board (reusing
// DealDeskBoard.tsx's exact HTML5 drag-and-drop pattern), Technician
// Utilization, Stalled RO Detection, and a composed Bottlenecks feed. The
// Shop Workflow Board itself isn't rebuilt here -- that's
// RepairOrderWorkspaceBoard.tsx's real 10-stage Kanban, unchanged.
import { PRODUCT_ACCENT_COLORS } from "@/lib/productTheme";
import { useEffect, useState, type DragEvent } from "react";
import {
  getDispatchBoard,
  getTechnicianUtilization,
  getStalledRos,
  getBottlenecks,
  assignTechnician,
  type DispatchBoard,
  type TechnicianUtilization,
  type StalledRos,
  type Bottlenecks,
} from "@/lib/shopControl";
import { getRoCatalog, type RoCatalog } from "@/lib/repairOrders";
import { RoWorkspaceModal } from "@/components/RepairOrderWorkspaceBoard";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const RIBBON = PRODUCT_ACCENT_COLORS;
const DRAG_TYPE = "application/x-dealeros-ro-id";

function Kpi({ theme, label, value, color }: { theme: Theme; label: string; value: number; color: string }) { return <WorkStat label={label} value={value}/>; }

function DispatchColumn({
  theme,
  title,
  color,
  ros,
  onDrop,
  onOpen,
}: {
  theme: Theme;
  title: string;
  color: string;
  ros: { id: string; service_number: string; description: string }[];
  onDrop: (roId: string) => void;
  onOpen: (roId: string) => void;
}) {
  const [isOver, setIsOver] = useState(false);

  return (
    <div
      onDragOver={(e) => { e.preventDefault(); e.dataTransfer.dropEffect = "move"; setIsOver(true); }}
      onDragLeave={() => setIsOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setIsOver(false);
        const roId = e.dataTransfer.getData(DRAG_TYPE);
        if (roId) onDrop(roId);
      }}
      className={
        isOver
          ? "w-56 shrink-0 flex flex-col rounded-lg border-2 border-brand-teal bg-brand-teal/5 overflow-hidden"
          : tc(theme, "w-56 shrink-0 flex flex-col rounded-lg border border-zinc-800 bg-brand-charcoal overflow-hidden", "w-56 shrink-0 flex flex-col rounded-lg border border-zinc-300 bg-zinc-50 overflow-hidden")
      }
    >
      <div className="px-2.5 py-2 flex items-center justify-between shrink-0" style={{ borderBottom: `2px solid ${color}` }}>
        <span className="text-xs font-brand uppercase tracking-wide truncate">{title}</span>
        <span className="text-xs font-bold px-1.5 py-0.5 rounded-full shrink-0" style={{ backgroundColor: color, color: "#111" }}>{ros.length}</span>
      </div>
      <div className="flex-1 overflow-y-auto p-1.5 space-y-1.5 min-h-[80px]">
        {ros.length === 0 && <div className="text-xs text-zinc-600 text-center py-4">Drop an RO here</div>}
        {ros.map((r) => (
          <div
            key={r.id}
            draggable
            onDragStart={(e: DragEvent<HTMLDivElement>) => { e.dataTransfer.setData(DRAG_TYPE, r.id); e.dataTransfer.effectAllowed = "move"; }}
            onClick={() => onOpen(r.id)}
            className={tc(theme, "rounded-md border border-zinc-800 bg-black/20 px-2 py-1.5 cursor-grab active:cursor-grabbing hover:border-brand-blue transition", "rounded-md border border-zinc-300 bg-white px-2 py-1.5 cursor-grab active:cursor-grabbing hover:border-brand-blue transition")}
          >
            <div className="text-xs font-medium truncate">{r.service_number}</div>
            <div className="text-xs text-zinc-500 truncate">{r.description}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function ShopControlBoard({ theme }: { theme: Theme }) {
  const [board, setBoard] = useState<DispatchBoard | null>(null);
  const [utilization, setUtilization] = useState<TechnicianUtilization | null>(null);
  const [stalled, setStalled] = useState<StalledRos | null>(null);
  const [bottlenecks, setBottlenecks] = useState<Bottlenecks | null>(null);
  const [catalog, setCatalog] = useState<RoCatalog | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedRo, setSelectedRo] = useState<string | null>(null);

  function refresh() {
    setLoading(true);
    Promise.all([getDispatchBoard(), getTechnicianUtilization(), getStalledRos(), getBottlenecks(), getRoCatalog()])
      .then(([b, u, s, bn, c]) => { setBoard(b); setUtilization(u); setStalled(s); setBottlenecks(bn); setCatalog(c); })
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }

  useEffect(refresh, []);

  async function handleAssign(roId: string, technicianId: string | null) {
    try {
      await assignTechnician(roId, technicianId);
      refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const cardClass = tc(theme, "rounded-lg border border-black/20 bg-brand-charcoal p-3", "rounded-lg border border-zinc-200 bg-zinc-50 p-3");

  if (loading || !board) {
    return <div className="p-4 text-sm text-zinc-500">Loading Shop Control…</div>;
  }

  const overloadedCount = utilization?.technicians.filter((t) => t.overloaded).length || 0;

  return (
    <div className={tc(theme, "flex-1 flex flex-col min-h-0 bg-brand-ink text-white overflow-y-auto", "flex-1 flex flex-col min-h-0 bg-white text-black overflow-y-auto")}>
      <div className={tc(theme, "grid grid-cols-4 gap-3 p-4 border-b border-zinc-800", "grid grid-cols-4 gap-3 p-4 border-b border-zinc-200")}>
        <Kpi theme={theme} label="Stalled ROs" value={stalled?.count || 0} color={RIBBON[3]} />
        <Kpi theme={theme} label="Parts Delays" value={bottlenecks?.parts_delays.count || 0} color={RIBBON[2]} />
        <Kpi theme={theme} label="Approval Delays" value={bottlenecks?.approval_delays.count || 0} color={RIBBON[1]} />
        <Kpi theme={theme} label="Techs Overloaded" value={overloadedCount} color={RIBBON[0]} />
      </div>

      {error && <div className="mx-4 mt-2 text-xs px-3 py-2 rounded-lg bg-red-500/15 border border-red-500/40 text-red-300">{error}</div>}

      <div className="p-4">
        <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Technician Dispatch Board — drag an RO onto a technician</div>
        <div className="flex gap-3 overflow-x-auto pb-2">
          <DispatchColumn
            theme={theme}
            title="Unassigned"
            color="#71717a"
            ros={board.unassigned}
            onDrop={(roId) => handleAssign(roId, null)}
            onOpen={setSelectedRo}
          />
          {Object.entries(board.technicians).map(([techId, t], i) => (
            <DispatchColumn
              key={techId}
              theme={theme}
              title={t.name || techId}
              color={RIBBON[i % RIBBON.length]}
              ros={t.repair_orders}
              onDrop={(roId) => handleAssign(roId, techId)}
              onOpen={setSelectedRo}
            />
          ))}
        </div>
      </div>

      <div className="px-4 pb-4 grid grid-cols-2 gap-3">
        <div className={cardClass}>
          <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Stalled RO Detection</div>
          {stalled && stalled.count === 0 ? (
            <div className="text-xs text-zinc-600">No stalled ROs — nothing open {stalled.hours_threshold}+ hours with zero labor posted.</div>
          ) : (
            <div className="space-y-1">
              {stalled?.repair_orders.map((r) => (
                <WorkButton type="submit" key={r.id} onClick={() => setSelectedRo(r.id)} className="block w-full text-left text-xs hover:text-brand-blue transition">
                  {r.service_number} — {r.description} <span className="text-zinc-500">({r.hours_open}h open, no labor posted)</span>
                </WorkButton>
              ))}
            </div>
          )}
        </div>

        <div className={cardClass}>
          <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Technician Utilization — {utilization?.date}</div>
          {utilization && utilization.technicians.length === 0 ? (
            <div className="text-xs text-zinc-600">No labor logged against a live RO today yet.</div>
          ) : (
            <div className="space-y-1">
              {utilization?.technicians.map((t) => (
                <div key={t.technician_id} className="flex items-center justify-between text-xs">
                  <span>{t.name || t.technician_id}</span>
                  <span className={t.overloaded ? "text-red-400" : "text-zinc-500"}>{t.hours_booked}h / {t.assumed_capacity_hours}h ({t.utilization_pct}%)</span>
                </div>
              ))}
            </div>
          )}
          {utilization && <div className="text-xs text-zinc-600 italic mt-1">{utilization.note}</div>}
        </div>
      </div>

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
