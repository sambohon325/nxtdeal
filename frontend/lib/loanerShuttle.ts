// Loaner & Shuttle Management -- the third of Sam's "completely missing"
// Service features. A real dealership-owned loaner fleet (distinct from
// sale inventory) with a checkout/checkin lifecycle, and a real shuttle
// request queue (pickup/dropoff, driver assignment, status lifecycle).
// Both optionally tie to a specific RO. Backend: core/loaner_shuttle.py /
// _api.py.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type LoanerStatus = "available" | "out" | "maintenance" | "out_of_service";
export type ShuttleStatus = "requested" | "assigned" | "en_route" | "completed" | "cancelled";
export type ShuttleDirection = "to_dealership" | "from_dealership";

export type LoanerVehicleBrief = {
  loaner_id: string;
  make: string;
  model: string;
  year: string | number | null;
  vin: string;
  mileage: number | null;
  status: LoanerStatus;
};

export type LoanerAssignment = {
  id: string;
  loaner_vehicle_id: string;
  customer_id: string;
  ro_id: string | null;
  checked_out_by: string;
  checked_out_at: string;
  odometer_out: number;
  fuel_out: string;
  expected_return_at: string | null;
  agreement_signed: boolean;
  notes: string;
  checked_in_by: string | null;
  checked_in_at: string | null;
  odometer_in: number | null;
  fuel_in: string | null;
  miles_driven: number | null;
  status: "out" | "overdue" | "returned";
  customer: { customer_id: string; name: string | null };
};

export type LoanerBoard = {
  total_fleet: number;
  by_status: Record<LoanerStatus, number>;
  active_assignments: LoanerAssignment[];
  overdue_count: number;
};

export type ShuttleRequest = {
  id: string;
  customer_id: string;
  ro_id: string | null;
  direction: ShuttleDirection;
  pickup_location: string;
  dropoff_location: string;
  requested_time: string;
  requested_by: string;
  created_at: string;
  status: ShuttleStatus;
  driver_id: string | null;
  completed_at: string | null;
  cancelled_reason: string | null;
  notes: string;
  customer: { customer_id: string; name: string | null };
};

export type ShuttleQueue = {
  total: number;
  by_status: Record<ShuttleStatus, number>;
  pending: ShuttleRequest[];
};

export type RoTransportationSummary = {
  ro_id: string;
  active_loaner_assignment: LoanerAssignment | null;
  assignment_history: LoanerAssignment[];
  shuttle_requests: ShuttleRequest[];
};

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

// ---- Fleet ----

export async function addLoanerVehicle(
  make: string,
  model: string,
  year: string | number,
  vin: string,
  mileage: number,
  notes = ""
): Promise<LoanerVehicleBrief> {
  const res = await fetch(`${API_BASE}/loaner-fleet`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ make, model, year, vin, mileage, notes }),
  });
  return handle(res);
}

export async function listLoanerFleet(status?: LoanerStatus): Promise<{ count: number; fleet: LoanerVehicleBrief[] }> {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  const res = await fetch(`${API_BASE}/loaner-fleet?${params.toString()}`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function getLoanerBoard(): Promise<LoanerBoard> {
  const res = await fetch(`${API_BASE}/loaner-fleet/board`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function updateLoanerStatus(loanerId: string, status: LoanerStatus, notes = ""): Promise<LoanerVehicleBrief> {
  const res = await fetch(`${API_BASE}/loaner-fleet/${encodeURIComponent(loanerId)}/status`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ status, notes }),
  });
  return handle(res);
}

// ---- Assignments ----

export async function checkoutLoaner(input: {
  loanerVehicleId: string;
  customerId: string;
  odometerOut: number;
  fuelOut?: string;
  roId?: string;
  expectedReturnAt?: string;
  agreementSigned?: boolean;
  notes?: string;
}): Promise<LoanerAssignment> {
  const res = await fetch(`${API_BASE}/loaner-assignments/checkout`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({
      loaner_vehicle_id: input.loanerVehicleId,
      customer_id: input.customerId,
      odometer_out: input.odometerOut,
      fuel_out: input.fuelOut ?? "Full",
      ro_id: input.roId ?? null,
      expected_return_at: input.expectedReturnAt ?? null,
      agreement_signed: input.agreementSigned ?? false,
      notes: input.notes ?? "",
    }),
  });
  return handle(res);
}

export async function checkinLoaner(
  assignmentId: string,
  odometerIn: number,
  fuelIn = "Full",
  sendToMaintenance = false,
  notes = ""
): Promise<LoanerAssignment> {
  const res = await fetch(`${API_BASE}/loaner-assignments/${encodeURIComponent(assignmentId)}/checkin`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ odometer_in: odometerIn, fuel_in: fuelIn, send_to_maintenance: sendToMaintenance, notes }),
  });
  return handle(res);
}

export async function getAssignmentsForRo(roId: string): Promise<LoanerAssignment[]> {
  const res = await fetch(`${API_BASE}/repair-orders/${encodeURIComponent(roId)}/loaner-assignments`, { headers: { ...authHeaders() } });
  return handle(res);
}

// ---- Shuttle ----

export async function requestShuttle(input: {
  customerId: string;
  direction: ShuttleDirection;
  pickupLocation: string;
  dropoffLocation: string;
  requestedTime: string;
  roId?: string;
  notes?: string;
}): Promise<ShuttleRequest> {
  const res = await fetch(`${API_BASE}/shuttle-requests`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({
      customer_id: input.customerId,
      direction: input.direction,
      pickup_location: input.pickupLocation,
      dropoff_location: input.dropoffLocation,
      requested_time: input.requestedTime,
      ro_id: input.roId ?? null,
      notes: input.notes ?? "",
    }),
  });
  return handle(res);
}

export async function assignShuttleDriver(requestId: string, driverId: string): Promise<ShuttleRequest> {
  const res = await fetch(`${API_BASE}/shuttle-requests/${encodeURIComponent(requestId)}/assign-driver`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ driver_id: driverId }),
  });
  return handle(res);
}

export async function updateShuttleStatus(requestId: string, status: ShuttleStatus, notes = ""): Promise<ShuttleRequest> {
  const res = await fetch(`${API_BASE}/shuttle-requests/${encodeURIComponent(requestId)}/status`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ status, notes }),
  });
  return handle(res);
}

export async function listShuttleRequests(status?: ShuttleStatus): Promise<{ count: number; requests: ShuttleRequest[] }> {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  const res = await fetch(`${API_BASE}/shuttle-requests?${params.toString()}`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function getShuttleQueue(): Promise<ShuttleQueue> {
  const res = await fetch(`${API_BASE}/shuttle-requests/queue`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function getShuttleRequestsForRo(roId: string): Promise<ShuttleRequest[]> {
  const res = await fetch(`${API_BASE}/repair-orders/${encodeURIComponent(roId)}/shuttle-requests`, { headers: { ...authHeaders() } });
  return handle(res);
}

// ---- Composed ----

export async function getRoTransportationSummary(roId: string): Promise<RoTransportationSummary> {
  const res = await fetch(`${API_BASE}/repair-orders/${encodeURIComponent(roId)}/transportation`, { headers: { ...authHeaders() } });
  return handle(res);
}
