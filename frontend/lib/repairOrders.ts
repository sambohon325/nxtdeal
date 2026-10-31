// RO Workflow Engine -- the flagship build of Service's rebuild (Sam: "This
// should be the centerpiece of Service... a full operating environment").
// Backend: core/repair_orders.py / _api.py. Turns ServiceRecord into a real
// 10-stage lifecycle entity (Check-In -> RO Written -> Inspection -> Estimate
// -> Customer Approval -> Parts -> Repair -> Quality Control -> Delivery ->
// Follow-Up) with concern tracking, an estimate/approval flow, parts
// requests, a QC checklist, and a composed timeline. The Communication
// Center reuses the generic FieldNote mechanism server-side -- no separate
// client needed for it here, it's folded into the timeline.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type RoStage =
  | "Check-In" | "RO Written" | "Inspection" | "Estimate" | "Customer Approval"
  | "Parts" | "Repair" | "Quality Control" | "Delivery" | "Follow-Up";

export type QcItem = "repair_complete" | "road_test" | "qc_inspection" | "washed";
export type PartsStatus = "all_available" | "awaiting_shipment" | "backordered";
export type PartRequestStatus = "requested" | "in_stock" | "ordered" | "received" | "installed";
export type CommChannel = "call" | "text" | "email";

// NXTDeal VIN Intelligence, Phase 2 -- core/vin_decoder.py's
// check_vehicle_vin_match(), reused in-process (no separate route) by
// core/repair_orders.py's get_ro_workspace(). Read-only: never writes
// anything back to the Vehicle.
export type VinMatchMismatch = {
  field: "Year" | "Make";
  stored: string;
  decoded: string;
  basis: string | null;
};

export type VinMatchResult =
  | { vehicle_id: string; checked: false; note: string }
  | {
      vehicle_id: string;
      checked: true;
      vin: string;
      valid_format: boolean;
      format_error: string | null;
      check_digit_valid: boolean | null;
      compared_something: boolean;
      mismatches: VinMatchMismatch[];
      match: boolean;
      note: string | null;
      gap_note: string;
    };

export type RoCatalog = {
  stages: RoStage[];
  qc_items: QcItem[];
  parts_statuses: PartsStatus[];
  part_request_statuses: PartRequestStatus[];
  comm_channels: CommChannel[];
};

export type ReturnFollowup = {status?:"planned"|"completed";outcome?:string;completed_by?:string;completed_at?:string;owner_id:string;due_date:string;next_action:string;updated_at:string};
export type RoBrief = {
  return_followup?: ReturnFollowup | null;
  vehicle_returned_at?: string | null;
  id: string;
  service_number: string;
  vin: string | null;
  customer_id: string | null;
  description: string;
  pay_type: string;
  ro_stage: RoStage;
  technician: string | null;
  service_date: string | null;
};

export type RoBoard = Record<RoStage, RoBrief[]>;

export type Concern = {
  id: string;
  description: string;
  occurs_at: string;
  created_by: string;
  created_at: string;
  status: "open" | "resolved" | "declined" | "deferred";
  resolution_notes?: string;
  resolved_by?: string;
  resolved_at?: string;
};

export type Estimate = {
  amount: number;
  sent_by: string;
  sent_at: string;
  approved: boolean | null;
  approved_by: string | null;
  approved_at: string | null;
  decline_reason: string | null;
} | null;

export type PartsStatusEntry = {
  status: PartsStatus;
  notes: string;
  updated_by: string;
  updated_at: string;
} | null;

export type PartRequest = {
  id: string;
  description: string;
  status: PartRequestStatus;
  requested_by: string;
  requested_at: string;
  updated_by: string | null;
  updated_at: string | null;
};

export type QcChecklist = Partial<Record<QcItem, { complete: boolean; updated_by: string; updated_at: string }>>;

export type WorkflowChecklistEntry = { stage: RoStage; status: "complete" | "current" | "pending" };

export type TimelineEvent = {
  type: string;
  label: string;
  at: string | null;
  by: string | null;
  notes: string | null;
};

export type RoWorkspace = {
  id: string;
  service_number: string;
  description: string;
  service_date: string | null;
  pay_type: string;
  status: string;
  cost: number | string | null;
  parts_cost: number | string | null;
  labor_hours: number | string | null;
  technician: string | null;
  ro_stage: RoStage;
  ro_stage_is_default: boolean;
  workflow_checklist: WorkflowChecklistEntry[];
  customer: {
    id: string | null;
    name: string | null;
    phone: string | null;
    email: string | null;
    preferred_contact_method: string | null;
  };
  vehicle: {
    id: string | null;
    vin: string | null;
    year: string | null;
    make: string | null;
    model: string | null;
    mileage: string | number | null;
    warranty_status: { status: string; condition?: string | null; note: string };
    recall_status: { open_recalls: { id: string; recall_number: string; description: string; campaign_type: string }[]; count: number };
    vin_match: VinMatchResult | null;
  };
  concerns: Concern[];
  estimate: Estimate;
  parts_status: PartsStatusEntry;
  parts_requests: PartRequest[];
  qc_checklist: QcChecklist;
  qc_ready_for_pickup: boolean;
  delivery_blockers?: string[];
  return_followup?: ReturnFollowup | null;
  return_handover?: {recipient:string;settlement_reference:string;transport:string;recorded_by:string;recorded_at:string;work_changed_since:boolean} | null;
  return_review?: {transport:string;notes:string;recorded_by:string;recorded_at:string;current:boolean} | null;
  timeline: { events: TimelineEvent[] };
};

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

export async function getRoCatalog(): Promise<RoCatalog> {
  const res = await fetch(`${API_BASE}/repair-orders/catalog`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function getRoBoard(): Promise<RoBoard> {
  const res = await fetch(`${API_BASE}/repair-orders/board`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function getRoWorkspace(roId: string): Promise<RoWorkspace> {
  const res = await fetch(`${API_BASE}/repair-orders/${encodeURIComponent(roId)}`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function createRepairOrder(vehicleId: string, customerId: string, description: string, payType = "Customer Pay", preferredContactMethod?: string): Promise<RoWorkspace> {
  const res = await fetch(`${API_BASE}/repair-orders`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ vehicle_id: vehicleId, customer_id: customerId, description, pay_type: payType, preferred_contact_method: preferredContactMethod || null }),
  });
  return handle(res);
}

export async function advanceRoStage(roId: string, newStage: RoStage): Promise<RoWorkspace> {
  const res = await fetch(`${API_BASE}/repair-orders/${encodeURIComponent(roId)}/advance-stage`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ new_stage: newStage }),
  });
  return handle(res);
}

export async function addConcern(roId: string, description: string, occursAt = ""): Promise<RoWorkspace> {
  const res = await fetch(`${API_BASE}/repair-orders/${encodeURIComponent(roId)}/concerns`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ description, occurs_at: occursAt }),
  });
  return handle(res);
}

export async function resolveConcern(roId: string, concernId: string, resolutionNotes = "", outcome: "resolved" | "declined" | "deferred" = "resolved"): Promise<RoWorkspace> {
  const res = await fetch(`${API_BASE}/repair-orders/${encodeURIComponent(roId)}/concerns/resolve`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ concern_id: concernId, resolution_notes: resolutionNotes, outcome }),
  });
  return handle(res);
}

export async function sendEstimate(roId: string, amount: number): Promise<RoWorkspace> {
  const res = await fetch(`${API_BASE}/repair-orders/${encodeURIComponent(roId)}/estimate`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ amount }),
  });
  return handle(res);
}

export async function recordCustomerApproval(roId: string, approved: boolean, declineReason = ""): Promise<RoWorkspace> {
  const res = await fetch(`${API_BASE}/repair-orders/${encodeURIComponent(roId)}/approval`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ approved, decline_reason: declineReason }),
  });
  return handle(res);
}

export async function updatePartsStatus(roId: string, status: PartsStatus, notes = ""): Promise<RoWorkspace> {
  const res = await fetch(`${API_BASE}/repair-orders/${encodeURIComponent(roId)}/parts-status`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ status, notes }),
  });
  return handle(res);
}

export async function requestPart(roId: string, description: string): Promise<RoWorkspace> {
  const res = await fetch(`${API_BASE}/repair-orders/${encodeURIComponent(roId)}/parts-requests`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ description }),
  });
  return handle(res);
}

export async function updatePartRequestStatus(roId: string, requestId: string, status: PartRequestStatus): Promise<RoWorkspace> {
  const res = await fetch(`${API_BASE}/repair-orders/${encodeURIComponent(roId)}/parts-requests/status`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ request_id: requestId, status }),
  });
  return handle(res);
}

export async function updateQcItem(roId: string, item: QcItem, complete: boolean): Promise<RoWorkspace> {
  const res = await fetch(`${API_BASE}/repair-orders/${encodeURIComponent(roId)}/qc`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ item, complete }),
  });
  return handle(res);
}

export async function logRoCommunication(roId: string, channel: CommChannel, body: string): Promise<RoWorkspace> {
  const res = await fetch(`${API_BASE}/repair-orders/${encodeURIComponent(roId)}/communication`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ channel, body }),
  });
  return handle(res);
}

export async function recordReturnReview(roId:string,transport:string,notes:string,acknowledged:boolean):Promise<RoWorkspace>{
  return handle(await fetch(`${API_BASE}/repair-orders/${encodeURIComponent(roId)}/return-review`,{method:"POST",headers:{"Content-Type":"application/json",...authHeaders()},body:JSON.stringify({transport,notes,acknowledged})}));
}

export async function recordReturnHandover(roId:string,recipient:string,settlementReference:string,confirmed:boolean):Promise<RoWorkspace>{
  return handle(await fetch(`${API_BASE}/repair-orders/${encodeURIComponent(roId)}/return-handover`,{method:"POST",headers:{"Content-Type":"application/json",...authHeaders()},body:JSON.stringify({recipient,settlement_reference:settlementReference,confirmed})}));
}

export async function planReturnFollowup(roId:string,dueDate:string,nextAction:string):Promise<RoWorkspace>{
  return handle(await fetch(`${API_BASE}/repair-orders/${encodeURIComponent(roId)}/return-followup`,{method:"POST",headers:{"Content-Type":"application/json",...authHeaders()},body:JSON.stringify({due_date:dueDate,next_action:nextAction})}));
}

export async function completeReturnFollowup(roId:string,outcome:string,expectedUpdatedAt:string):Promise<RoWorkspace>{
 return handle(await fetch(`${API_BASE}/repair-orders/${encodeURIComponent(roId)}/return-followup/outcome`,{method:"POST",headers:{"Content-Type":"application/json",...authHeaders()},body:JSON.stringify({outcome,expected_updated_at:expectedUpdatedAt})}));
}
