// Operations' "Scheduling" item (session 106 follow-up #5) -- Recon
// Scheduling, Delivery Scheduling with automatic risk detection, Transport
// Scheduling. Backend: core/operations_scheduling.py / _api.py.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type ReconVehicleBrief = {
  vehicle_id: string;
  vin: string | null;
  stock_number: string | null;
  lot: string | null;
  year: string | null;
  make: string | null;
  model: string | null;
};

export type ReconSchedule = {
  used_unsold_count: number;
  by_lot: Record<string, number>;
  vehicles: ReconVehicleBrief[];
  note: string;
};

export type DeliveryRiskDeal = {
  deal_id: string;
  customer_id: string | null;
  vehicle_id: string | null;
  status: string;
  appointment_id?: string;
  scheduled_start?: string;
};

export type DeliveryRiskBoard = {
  total_pending_delivery: number;
  on_track: { count: number; deals: DeliveryRiskDeal[] };
  no_delivery_scheduled: { count: number; deals: DeliveryRiskDeal[] };
  overdue: { count: number; deals: DeliveryRiskDeal[] };
  note: string;
};

export type TransportTransaction = {
  id: string;
  vehicle_id: string;
  vin: string | null;
  auction_house: string | null;
  bid_amount: number | null;
  purchase_date: string | null;
  transport_status: "at_auction_yard" | "in_transit" | "delivered";
  carrier: string | null;
  expected_arrival: string | null;
};

export type TransportSchedule = {
  count: number;
  by_transport_status: Record<string, number>;
  transactions: TransportTransaction[];
};

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

export async function getReconSchedule(): Promise<ReconSchedule> {
  const res = await fetch(`${API_BASE}/operations-scheduling/recon`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function scheduleRecon(vehicleId: string, targetDate: string, notes = ""): Promise<{ id: string }> {
  const res = await fetch(`${API_BASE}/operations-scheduling/recon/${encodeURIComponent(vehicleId)}/schedule`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ target_date: targetDate, notes }),
  });
  return handle(res);
}

export async function getDeliveryRiskBoard(): Promise<DeliveryRiskBoard> {
  const res = await fetch(`${API_BASE}/operations-scheduling/delivery-risk`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function scheduleDelivery(dealId: string, scheduledStart: string, assignedTo?: string, notes = ""): Promise<{ id: string }> {
  const res = await fetch(`${API_BASE}/operations-scheduling/delivery/${encodeURIComponent(dealId)}/schedule`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ scheduled_start: scheduledStart, assigned_to: assignedTo ?? null, notes }),
  });
  return handle(res);
}

export async function getTransportSchedule(): Promise<TransportSchedule> {
  const res = await fetch(`${API_BASE}/operations-scheduling/transport`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function updateTransportStatus(transactionId: string, newStatus: TransportTransaction["transport_status"]): Promise<{ id: string; old_status: string; new_status: string }> {
  const res = await fetch(`${API_BASE}/operations-scheduling/transport/${encodeURIComponent(transactionId)}/status`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ new_status: newStatus }),
  });
  return handle(res);
}
