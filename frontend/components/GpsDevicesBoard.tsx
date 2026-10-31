"use client";
import { WorkInput, WorkSelect, WorkButton , WorkStat, WorkOverlay} from "./WorkspaceUi";
import { WorkField } from "./WorkField";

// Finance's "GPS & Devices" item -- the fifth slice of Sam's "Retail Automotive
// Lending Platform" expansion (2026-07-17). A real installed-device registry
// (register/remove a GPS or GPS+Starter-Interrupt unit per loan) plus honestly
// SIMULATED GPS location telemetry -- no real GPS hardware/telematics API is
// connected in this sandbox, disclosed on every reading. `DeviceDetailModal` is
// exported and reused directly by `StarterInterruptBoard.tsx` (same real device,
// two operational lenses -- one detail view, not two).
import { PRODUCT_ACCENT_COLORS } from "@/lib/productTheme";
import { useEffect, useState } from "react";
import {
  getDeviceManagementDashboard,
  listDevices,
  registerDevice,
  getDeviceDetail,
  removeDevice,
  getSimulatedLocation,
  getLocationHistory,
  armStarterInterrupt,
  sendWarning,
  disableStarter,
  enableStarter,
  DEVICE_TYPES,
  type DeviceType,
  type DeviceBrief,
  type DeviceDetail,
  type DeviceManagementDashboard,
  type LocationHistory,
} from "@/lib/deviceManagement";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const RIBBON = PRODUCT_ACCENT_COLORS;

function Kpi({ theme, label, value, color }: { theme: Theme; label: string; value: string; color: string }) { return <WorkStat label={label} value={value}/>; }

export function GpsDevicesBoard({ theme }: { theme: Theme }) {
  const [dashboard, setDashboard] = useState<DeviceManagementDashboard | null>(null);
  const [devices, setDevices] = useState<DeviceBrief[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<string | null>(null);

  const [regLoanId, setRegLoanId] = useState("");
  const [regType, setRegType] = useState<DeviceType>("gps_starter_interrupt");
  const [regSerial, setRegSerial] = useState("");
  const [regBusy, setRegBusy] = useState(false);
  const [regError, setRegError] = useState<string | null>(null);

  const cardClass = tc(theme, "rounded-lg border border-black/20 bg-brand-charcoal p-3", "rounded-lg border border-zinc-200 bg-zinc-50 p-3");
  const textClass = tc(theme, "bg-zinc-900 border-zinc-700 text-white placeholder:text-zinc-600", "bg-white border-zinc-300 text-black placeholder:text-zinc-400");

  function refresh() {
    setLoading(true);
    Promise.all([getDeviceManagementDashboard(), listDevices("active")])
      .then(([d, list]) => {
        setDashboard(d);
        setDevices(list.devices);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }

  useEffect(refresh, []);

  async function handleRegister() {
    if (!regLoanId.trim() || !regSerial.trim()) return;
    setRegBusy(true);
    setRegError(null);
    try {
      const device = await registerDevice(regLoanId.trim().toUpperCase(), regType, regSerial.trim());
      setRegLoanId("");
      setRegSerial("");
      refresh();
      setSelected(device.id);
    } catch (e) {
      setRegError((e as Error).message);
    } finally {
      setRegBusy(false);
    }
  }

  return (
    <div className={tc(theme, "flex-1 flex flex-col min-h-0 bg-brand-ink text-white overflow-y-auto", "flex-1 flex flex-col min-h-0 bg-white text-black overflow-y-auto")}>
      <div className={tc(theme, "grid grid-cols-4 gap-3 p-4 border-b border-zinc-800", "grid grid-cols-4 gap-3 p-4 border-b border-zinc-200")}>
        <Kpi theme={theme} label="Total Devices" value={String(dashboard?.total_devices ?? 0)} color={RIBBON[0]} />
        <Kpi theme={theme} label="Active" value={String(dashboard?.active_devices ?? 0)} color={RIBBON[1]} />
        <Kpi theme={theme} label="GPS Only" value={String(dashboard?.gps_only_count ?? 0)} color={RIBBON[2]} />
        <Kpi theme={theme} label="GPS + Starter Interrupt" value={String(dashboard?.gps_starter_interrupt_count ?? 0)} color={RIBBON[3]} />
      </div>

      <div className="px-4 py-2 border-b border-zinc-800">
        <span className="text-xs px-2 py-1 rounded bg-amber-950/30 border border-amber-900/50 text-amber-300">
          {dashboard?.disclaimer}
        </span>
      </div>

      <div className="px-4 py-3 border-b border-zinc-800">
        <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Register Device</div>
        <div className="flex items-center gap-2 flex-wrap">
          <WorkField label="Loan id"><WorkInput value={regLoanId} onChange={(e) => setRegLoanId(e.target.value)} placeholder="Loan id (e.g. FIN-00001)…" className={`rounded-md border px-2 py-1.5 text-xs ${textClass}`} /></WorkField>
          <WorkField label="Device type"><WorkSelect value={regType} onChange={(e) => setRegType(e.target.value as DeviceType)} className={`rounded-md border px-2 py-1.5 text-xs ${textClass}`}>
            {DEVICE_TYPES.map((t) => <option key={t} value={t}>{t.replace(/_/g, " ")}</option>)}
          </WorkSelect></WorkField>
          <WorkField label="Serial number"><WorkInput value={regSerial} onChange={(e) => setRegSerial(e.target.value)} placeholder="Serial number…" className={`rounded-md border px-2 py-1.5 text-xs ${textClass}`} /></WorkField>
          <WorkButton type="submit" variant="primary"
            disabled={regBusy || !regLoanId.trim() || !regSerial.trim()}
            onClick={handleRegister}
            className="text-xs px-2.5 py-1.5 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50"
          >
            {regBusy ? "Registering…" : "Register Device"}
          </WorkButton>
          {regError && <span className="text-xs text-red-400">{regError}</span>}
        </div>
      </div>

      <div className="flex-1 p-4 overflow-y-auto">
        <div className={cardClass}>
          <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Active Devices</div>
          {loading ? (
            <div className="text-xs text-zinc-500">Loading…</div>
          ) : devices.length === 0 ? (
            <div className="text-xs text-zinc-500">No active devices registered.</div>
          ) : (
            <div className="space-y-1 max-h-[28rem] overflow-y-auto">
              {devices.map((d) => (
                <WorkButton type="submit"
                  key={d.id}
                  onClick={() => setSelected(d.id)}
                  className="w-full text-left flex items-center justify-between text-xs hover:text-brand-blue transition py-1 border-b border-zinc-800/50"
                >
                  <span>{d.id} · {d.loan_id} · {d.serial_number}</span>
                  <span className="flex items-center gap-1">
                    <span className="text-xs px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400">{d.device_type.replace(/_/g, " ")}</span>
                    {d.device_type === "gps_starter_interrupt" && (
                      <span className={`text-xs px-1.5 py-0.5 rounded ${d.starter_status === "disabled" ? "bg-red-950/40 text-red-300" : "bg-green-950/40 text-green-300"}`}>
                        {d.starter_status}
                      </span>
                    )}
                  </span>
                </WorkButton>
              ))}
            </div>
          )}
        </div>
      </div>

      {selected && (
        <DeviceDetailModal theme={theme} deviceId={selected} onClose={() => setSelected(null)} onChanged={refresh} />
      )}
    </div>
  );
}

export function DeviceDetailModal({
  theme,
  deviceId,
  onClose,
  onChanged,
}: {
  theme: Theme;
  deviceId: string;
  onClose: () => void;
  onChanged: () => void;
}) {
  const [detail, setDetail] = useState<DeviceDetail | null>(null);
  const [history, setHistory] = useState<LocationHistory | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [warningMessage, setWarningMessage] = useState("");
  const [removeReason, setRemoveReason] = useState("");

  const cardClass = tc(theme, "rounded-lg border border-zinc-800 bg-zinc-950 p-3", "rounded-lg border border-zinc-200 bg-zinc-50 p-3");
  const textClass = tc(theme, "bg-zinc-900 border-zinc-700 text-white placeholder:text-zinc-600", "bg-white border-zinc-300 text-black placeholder:text-zinc-400");

  function load() {
    setLoading(true);
    setError(null);
    Promise.all([getDeviceDetail(deviceId), getLocationHistory(deviceId, 7).catch(() => null)])
      .then(([d, h]) => {
        setDetail(d);
        setHistory(h);
      })
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }

  useEffect(load, [deviceId]);

  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      load();
      onChanged();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const starterCapable = detail?.device_type === "gps_starter_interrupt";

  return (
    <WorkOverlay className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className={tc(theme, "w-full max-w-3xl max-h-[85vh] overflow-y-auto rounded-lg border border-zinc-800 bg-brand-ink text-white p-5", "w-full max-w-3xl max-h-[85vh] overflow-y-auto rounded-lg border border-zinc-200 bg-white text-black p-5")}>
        <div className="flex items-center justify-between mb-3">
          <div>
            <div className="text-sm font-semibold">Device — {deviceId}</div>
            {detail && <div className="text-xs text-zinc-500">{detail.loan_id} · {detail.serial_number} · {detail.status}</div>}
          </div>
          <WorkButton type="submit" onClick={onClose} className="text-xs px-2 py-1 rounded bg-zinc-800 text-zinc-300 hover:text-white transition">Close</WorkButton>
        </div>

        {error && <div className="text-xs text-red-400 mb-2">{error}</div>}
        {loading ? (
          <div className="text-xs text-zinc-500">Loading…</div>
        ) : !detail ? (
          <div className="text-xs text-zinc-500">Unable to load device.</div>
        ) : (
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div className={cardClass}>
                <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1">Customer</div>
                <div className="text-xs">{(detail.customer?.name as string) || "—"}</div>
              </div>
              <div className={cardClass}>
                <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1">Vehicle</div>
                <div className="text-xs">{detail.vehicle ? `${detail.vehicle.year ?? ""} ${detail.vehicle.make ?? ""} ${detail.vehicle.model ?? ""}`.trim() : "—"}</div>
              </div>
            </div>

            {detail.status === "active" && detail.location && (
              <div className={cardClass}>
                <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1">Current Location <span className="ml-1 text-amber-400">(Simulated)</span></div>
                <div className="text-xs">{detail.location.approximate_address}</div>
                <div className="text-xs text-zinc-500 mt-1">{detail.location.latitude}, {detail.location.longitude} · {detail.location.moving ? `moving ${detail.location.speed_mph} mph` : "stationary"}</div>
                <div className="text-xs text-zinc-600 mt-1">{detail.location.disclaimer}</div>
              </div>
            )}

            {history && history.entries.length > 0 && (
              <div className={cardClass}>
                <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1">7-Day Location History <span className="ml-1 text-amber-400">(Simulated)</span></div>
                <div className="space-y-0.5">
                  {history.entries.map((e) => (
                    <div key={e.date} className="text-xs text-zinc-500">{e.date}: {e.latitude}, {e.longitude}</div>
                  ))}
                </div>
              </div>
            )}

            {starterCapable && (
              <div className={cardClass}>
                <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Starter Interrupt Control</div>
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-xs px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400">Armed: {detail.starter_interrupt_armed ? "yes" : "no"}</span>
                  <span className={`text-xs px-1.5 py-0.5 rounded ${detail.starter_status === "disabled" ? "bg-red-950/40 text-red-300" : "bg-green-950/40 text-green-300"}`}>
                    Starter: {detail.starter_status}
                  </span>
                  {detail.last_warning_at && <span className="text-xs text-zinc-500">Warned {detail.last_warning_at.slice(0, 16).replace("T", " ")}</span>}
                </div>

                <div className="flex items-center gap-2 flex-wrap">
                  {!detail.starter_interrupt_armed && (
                    <WorkButton type="submit" variant="primary" disabled={busy} onClick={() => run(() => armStarterInterrupt(deviceId))} className="text-xs px-2.5 py-1.5 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50">
                      Arm Device
                    </WorkButton>
                  )}
                  <WorkField label="Warning message (optional)"><WorkInput value={warningMessage} onChange={(e) => setWarningMessage(e.target.value)} placeholder="Warning message (optional)…" className={`flex-1 rounded-md border px-2 py-1.5 text-xs ${textClass}`} /></WorkField>
                  <WorkButton type="submit" disabled={busy} onClick={() => run(() => sendWarning(deviceId, warningMessage))} className="text-xs px-2.5 py-1.5 rounded bg-amber-800 text-white font-medium hover:opacity-90 transition disabled:opacity-50">
                    Send Warning
                  </WorkButton>
                  {detail.starter_status === "enabled" ? (
                    <WorkButton type="submit" variant="danger" disabled={busy} onClick={() => run(() => disableStarter(deviceId, "Delinquent loan"))} className="text-xs px-2.5 py-1.5 rounded bg-red-800 text-white font-medium hover:opacity-90 transition disabled:opacity-50">
                      Disable Starter
                    </WorkButton>
                  ) : (
                    <WorkButton type="submit" disabled={busy} onClick={() => run(() => enableStarter(deviceId, "Reinstated"))} className="text-xs px-2.5 py-1.5 rounded bg-green-800 text-white font-medium hover:opacity-90 transition disabled:opacity-50">
                      Re-Enable Starter
                    </WorkButton>
                  )}
                </div>
                <div className="text-xs text-zinc-600 mt-2">{detail.not_legal_advice_notice}</div>
              </div>
            )}

            <div className={cardClass}>
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Command History</div>
              <div className="space-y-0.5 max-h-32 overflow-y-auto">
                {detail.command_history.slice().reverse().map((h, i) => (
                  <div key={i} className="text-xs text-zinc-500">
                    {h.action} · {h.by} · {h.reason || "—"} · {h.at.slice(0, 16).replace("T", " ")}
                  </div>
                ))}
              </div>
            </div>

            {detail.status === "active" && (
              <div className={cardClass}>
                <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Remove Device</div>
                <div className="flex items-center gap-2">
                  <WorkField label="Reason"><WorkInput value={removeReason} onChange={(e) => setRemoveReason(e.target.value)} placeholder="Reason…" className={`flex-1 rounded-md border px-2 py-1.5 text-xs ${textClass}`} /></WorkField>
                  <WorkButton type="submit" disabled={busy} onClick={() => run(() => removeDevice(deviceId, removeReason))} className="text-xs px-2.5 py-1.5 rounded bg-zinc-800 text-zinc-300 hover:text-white transition disabled:opacity-50">
                    Remove Device
                  </WorkButton>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </WorkOverlay>
  );
}
