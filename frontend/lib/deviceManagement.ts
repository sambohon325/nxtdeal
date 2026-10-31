// Finance's "GPS & Devices" + "Starter Interrupt" items -- the fifth slice of Sam's
// Retail Automotive Lending Platform expansion (2026-07-17). One real engine
// (core/device_management.py / _api.py) backs both Finance Top Menu items, since a
// GPS/starter-interrupt unit is one real physical device with two operational
// lenses. GPS location telemetry is honestly SIMULATED (no real GPS hardware/
// telematics API connected in this sandbox, disclosed on every reading). The
// starter-interrupt command lifecycle (arm/warn/disable/enable) is real, stored
// state with a real enforced rule: a warning must be on file before disable() will
// run.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type DeviceType = "gps_only" | "gps_starter_interrupt";
export type DeviceStatus = "active" | "removed";
export type StarterStatus = "enabled" | "disabled";

export const DEVICE_TYPES: DeviceType[] = ["gps_only", "gps_starter_interrupt"];

export type DeviceBrief = {
  id: string;
  loan_id: string;
  device_type: DeviceType;
  serial_number: string;
  status: DeviceStatus;
  starter_status: StarterStatus | null;
  starter_interrupt_armed: boolean | null;
  install_date: string;
  last_warning_at: string | null;
};

export type DevicesList = { count: number; devices: DeviceBrief[] };

export type CommandHistoryEntry = { action: string; by: string; reason: string; at: string };

export type SimulatedLocation = {
  device_id: string;
  loan_id: string;
  latitude: number;
  longitude: number;
  approximate_address: string;
  speed_mph: number;
  moving: boolean;
  last_ping_at: string;
  basis: string;
  disclaimer: string;
};

export type LocationHistory = {
  device_id: string;
  days: number;
  entries: { date: string; latitude: number; longitude: number }[];
  basis: string;
  disclaimer: string;
};

export type DeviceDetail = {
  id: string;
  customer: Record<string, unknown> | null;
  vehicle: Record<string, unknown> | null;
  loan_id: string;
  device_type: DeviceType;
  serial_number: string;
  install_date: string;
  installed_by: string;
  status: DeviceStatus;
  starter_interrupt_armed: boolean | null;
  starter_status: StarterStatus | null;
  last_warning_at: string | null;
  last_warning_message: string | null;
  last_warning_by: string | null;
  command_history: CommandHistoryEntry[];
  removed_at: string | null;
  removed_by: string | null;
  removed_reason: string | null;
  location: SimulatedLocation | null;
  not_legal_advice_notice: string;
};

export type DeviceManagementDashboard = {
  total_devices: number;
  active_devices: number;
  removed_devices: number;
  gps_only_count: number;
  gps_starter_interrupt_count: number;
  basis: string;
  disclaimer: string;
};

export type StarterInterruptDashboard = {
  starter_interrupt_capable_devices: number;
  armed_count: number;
  disabled_count: number;
  pending_warning_count: number;
  not_legal_advice_notice: string;
  devices: DeviceBrief[];
};

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

function get<T>(path: string): Promise<T> {
  return fetch(`${API_BASE}${path}`, { headers: { ...authHeaders() } }).then(handle<T>);
}

function post<T>(path: string, body: unknown): Promise<T> {
  return fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(body),
  }).then(handle<T>);
}

export function getDeviceManagementDashboard(): Promise<DeviceManagementDashboard> {
  return get(`/devices/dashboard`);
}

export function getStarterInterruptDashboard(): Promise<StarterInterruptDashboard> {
  return get(`/devices/starter-interrupt/dashboard`);
}

export function listDevices(status?: DeviceStatus, loanId?: string, deviceType?: DeviceType): Promise<DevicesList> {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  if (loanId) params.set("loan_id", loanId);
  if (deviceType) params.set("device_type", deviceType);
  const qs = params.toString();
  return get(`/devices${qs ? `?${qs}` : ""}`);
}

export function registerDevice(loanId: string, deviceType: DeviceType, serialNumber: string, installDate?: string): Promise<DeviceDetail> {
  return post(`/devices`, { loan_id: loanId, device_type: deviceType, serial_number: serialNumber, install_date: installDate ?? null });
}

export function getDeviceDetail(deviceId: string): Promise<DeviceDetail> {
  return get(`/devices/${encodeURIComponent(deviceId)}`);
}

export function removeDevice(deviceId: string, reason = ""): Promise<DeviceDetail> {
  return post(`/devices/${encodeURIComponent(deviceId)}/remove`, { reason });
}

export function getSimulatedLocation(deviceId: string): Promise<SimulatedLocation> {
  return get(`/devices/${encodeURIComponent(deviceId)}/location`);
}

export function getLocationHistory(deviceId: string, days = 7): Promise<LocationHistory> {
  return get(`/devices/${encodeURIComponent(deviceId)}/location-history?days=${days}`);
}

export function armStarterInterrupt(deviceId: string): Promise<DeviceDetail> {
  return post(`/devices/${encodeURIComponent(deviceId)}/arm`, {});
}

export function sendWarning(deviceId: string, message = ""): Promise<DeviceDetail> {
  return post(`/devices/${encodeURIComponent(deviceId)}/warning`, { message });
}

export function disableStarter(deviceId: string, reason = ""): Promise<DeviceDetail> {
  return post(`/devices/${encodeURIComponent(deviceId)}/disable`, { reason });
}

export function enableStarter(deviceId: string, reason = ""): Promise<DeviceDetail> {
  return post(`/devices/${encodeURIComponent(deviceId)}/enable`, { reason });
}
