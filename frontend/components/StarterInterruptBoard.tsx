"use client";
import { WorkButton , WorkStat} from "./WorkspaceUi";

// Finance's "Starter Interrupt" item -- the fifth slice of Sam's "Retail Automotive
// Lending Platform" expansion (2026-07-17). Real, stored starter-interrupt control
// over the same InstalledDevice registry GPS & Devices manages -- arm a device, send
// a required customer warning, then disable/re-enable the starter, with a real
// enforced rule that a warning must be on file before a disable command will run.
// Reuses `GpsDevicesBoard.tsx`'s exported `DeviceDetailModal` directly for the full
// per-device console -- one real device, one real detail view, two menu-item lenses.
import { PRODUCT_ACCENT_COLORS } from "@/lib/productTheme";
import { useEffect, useState } from "react";
import {
  getStarterInterruptDashboard,
  type StarterInterruptDashboard,
  type DeviceBrief,
} from "@/lib/deviceManagement";
import { DeviceDetailModal } from "@/components/GpsDevicesBoard";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const RIBBON = PRODUCT_ACCENT_COLORS;

function Kpi({ theme, label, value, color }: { theme: Theme; label: string; value: string; color: string }) { return <WorkStat label={label} value={value}/>; }

function deviceRow(d: DeviceBrief, onClick: () => void) {
  return (
    <WorkButton type="submit"
      key={d.id}
      onClick={onClick}
      className="w-full text-left flex items-center justify-between text-xs hover:text-brand-blue transition py-1 border-b border-zinc-800/50"
    >
      <span>{d.id} · {d.loan_id} · {d.serial_number}</span>
      <span className="flex items-center gap-1">
        <span className="text-xs px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400">
          {d.starter_interrupt_armed ? "armed" : "not armed"}
        </span>
        <span className={`text-xs px-1.5 py-0.5 rounded ${d.starter_status === "disabled" ? "bg-red-950/40 text-red-300" : "bg-green-950/40 text-green-300"}`}>
          {d.starter_status}
        </span>
      </span>
    </WorkButton>
  );
}

export function StarterInterruptBoard({ theme }: { theme: Theme }) {
  const [dashboard, setDashboard] = useState<StarterInterruptDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<string | null>(null);

  const cardClass = tc(theme, "rounded-lg border border-black/20 bg-brand-charcoal p-3", "rounded-lg border border-zinc-200 bg-zinc-50 p-3");

  function refresh() {
    setLoading(true);
    getStarterInterruptDashboard()
      .then(setDashboard)
      .catch(() => {})
      .finally(() => setLoading(false));
  }

  useEffect(refresh, []);

  const devices = dashboard?.devices ?? [];
  const pendingWarning = devices.filter((d) => d.starter_interrupt_armed && d.starter_status !== "disabled" && !d.last_warning_at);
  const disabled = devices.filter((d) => d.starter_status === "disabled");
  const rest = devices.filter((d) => !pendingWarning.includes(d) && !disabled.includes(d));

  return (
    <div className={tc(theme, "flex-1 flex flex-col min-h-0 bg-brand-ink text-white overflow-y-auto", "flex-1 flex flex-col min-h-0 bg-white text-black overflow-y-auto")}>
      <div className={tc(theme, "grid grid-cols-4 gap-3 p-4 border-b border-zinc-800", "grid grid-cols-4 gap-3 p-4 border-b border-zinc-200")}>
        <Kpi theme={theme} label="Capable Devices" value={String(dashboard?.starter_interrupt_capable_devices ?? 0)} color={RIBBON[0]} />
        <Kpi theme={theme} label="Armed" value={String(dashboard?.armed_count ?? 0)} color={RIBBON[1]} />
        <Kpi theme={theme} label="Disabled" value={String(dashboard?.disabled_count ?? 0)} color={RIBBON[3]} />
        <Kpi theme={theme} label="Pending Warning" value={String(dashboard?.pending_warning_count ?? 0)} color={RIBBON[2]} />
      </div>

      <div className="px-4 py-2 border-b border-zinc-800">
        <span className="text-xs px-2 py-1 rounded bg-amber-950/30 border border-amber-900/50 text-amber-300">
          {dashboard?.not_legal_advice_notice}
        </span>
      </div>

      <div className="flex-1 p-4 grid grid-cols-3 gap-3 overflow-y-auto">
        <div className={cardClass}>
          <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Pending Warning (armed, not yet warned)</div>
          <div className="space-y-1 max-h-96 overflow-y-auto">
            {loading ? (
              <div className="text-xs text-zinc-500">Loading…</div>
            ) : pendingWarning.length === 0 ? (
              <div className="text-xs text-zinc-500">No devices pending a warning.</div>
            ) : (
              pendingWarning.map((d) => deviceRow(d, () => setSelected(d.id)))
            )}
          </div>
        </div>

        <div className={cardClass}>
          <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Currently Disabled</div>
          <div className="space-y-1 max-h-96 overflow-y-auto">
            {loading ? (
              <div className="text-xs text-zinc-500">Loading…</div>
            ) : disabled.length === 0 ? (
              <div className="text-xs text-zinc-500">No devices currently disabled.</div>
            ) : (
              disabled.map((d) => deviceRow(d, () => setSelected(d.id)))
            )}
          </div>
        </div>

        <div className={cardClass}>
          <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">All Other Capable Devices</div>
          <div className="space-y-1 max-h-96 overflow-y-auto">
            {loading ? (
              <div className="text-xs text-zinc-500">Loading…</div>
            ) : rest.length === 0 ? (
              <div className="text-xs text-zinc-500">None.</div>
            ) : (
              rest.map((d) => deviceRow(d, () => setSelected(d.id)))
            )}
          </div>
        </div>
      </div>

      {selected && (
        <DeviceDetailModal theme={theme} deviceId={selected} onClose={() => setSelected(null)} onChanged={refresh} />
      )}
    </div>
  );
}
