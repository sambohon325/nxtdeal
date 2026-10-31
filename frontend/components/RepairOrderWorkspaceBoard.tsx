"use client";
import { WorkButton, WorkInput, WorkTextarea, WorkSelect , WorkStat, WorkOverlay} from "./WorkspaceUi";
import { WorkField } from "./WorkField";

// Service department's "Repair Orders" item -- the centerpiece of Service's
// rebuild (Sam: "This should be the centerpiece of Service... a full
// operating environment"). Reuses core/repair_orders.py's real 10-stage RO
// Workflow Engine for the Kanban board + a full RO Workspace modal: customer/
// vehicle info (with real warranty/recall status), concern tracking, an
// estimate/approval flow, parts requests, a QC checklist (with a computed
// ready-for-pickup gate), and a composed timeline that folds in the
// integrated Communication Center (Call/Text/Email, logged via the generic
// FieldNote mechanism server-side).
import { CustomerLoyaltyPanel } from "@/components/CustomerLoyaltyPanel";
import { PRODUCT_ACCENT_COLORS } from "@/lib/productTheme";
import { useEffect, useState } from "react";
import { CommsQuickActions } from "@/components/CommsQuickActions";
import {
  getRoCatalog,
  getRoBoard,
  getRoWorkspace,
  createRepairOrder,
  advanceRoStage, recordReturnReview, recordReturnHandover, planReturnFollowup, completeReturnFollowup,
  addConcern,
  resolveConcern,
  sendEstimate,
  recordCustomerApproval,
  updatePartsStatus,
  requestPart,
  updatePartRequestStatus,
  updateQcItem,
  logRoCommunication,
  type RoCatalog,
  type RoBoard,
  type RoWorkspace,
  type RoStage,
  type QcItem,
  type PartsStatus,
  type CommChannel,
} from "@/lib/repairOrders";
import { searchCustomers, type CustomerBrief } from "@/lib/deals";
import { searchInventoryForPost, type LinkedVehicle } from "@/lib/socialReputation";
import {
  getDviCatalog,
  getInspection,
  startInspection,
  updateInspectionItem,
  attachInspectionPhoto,
  completeInspection,
  createConcernsFromInspection,
  getVehicleInspectionHistory,
  type DviCatalog,
  type Inspection,
  type InspectionStatus,
  type InspectionHistory,
} from "@/lib/vehicleInspection";
import {
  generateApprovalLink,
  getApprovalLinkStatus,
  revokeApprovalLink,
  type ApprovalLinkStatus,
} from "@/lib/approvalCenter";
import {
  listLoanerFleet,
  checkoutLoaner,
  checkinLoaner,
  requestShuttle,
  assignShuttleDriver,
  updateShuttleStatus,
  getRoTransportationSummary,
  addLoanerVehicle,
  updateLoanerStatus,
  type LoanerVehicleBrief,
  type LoanerStatus,
  type RoTransportationSummary,
  type ShuttleDirection,
  type ShuttleStatus,
} from "@/lib/loanerShuttle";
import { getServiceEmployees, type ServiceEmployeeBrief } from "@/lib/appointments";
import { getSalesEmployees, type SalesEmployeeBrief } from "@/lib/salesOverview";
import {
  getRoHandoffStatus,
  flagManualOpportunity,
  promoteToSales,
  dismissOpportunity,
  type RoHandoffStatus,
} from "@/lib/serviceSalesHandoff";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const RIBBON = PRODUCT_ACCENT_COLORS;

const QC_LABELS: Record<QcItem, string> = {
  repair_complete: "Repair Complete",
  road_test: "Road Test",
  qc_inspection: "QC Inspection",
  washed: "Washed",
};

function money(v: string | number | null | undefined): string {
  if (v === null || v === undefined || v === "") return "—";
  const n = typeof v === "string" ? parseFloat(v) : v;
  if (Number.isNaN(n)) return String(v);
  return `$${n.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}

function fmt(ts: string | null | undefined): string {
  if (!ts) return "—";
  try {
    return new Date(ts).toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  } catch {
    return ts;
  }
}

function Kpi({ theme, label, value, color }: { theme: Theme; label: string; value: number; color: string }) { return <WorkStat label={label} value={value}/>; }

export function NewRoModal({
  theme,
  inline = false,
  onClose,
  onCreated, onDraftOpenChange, onSavingChange,
}: {
  theme: Theme;
  inline?: boolean;
  onClose: () => void;
  onCreated: (roId: string) => void;
  onDraftOpenChange?:(v:boolean)=>void;onSavingChange?:(v:boolean)=>void;
}) {
  const [customerQuery, setCustomerQuery] = useState("");
  const [customerResults, setCustomerResults] = useState<CustomerBrief[]>([]);
  const [customer, setCustomer] = useState<CustomerBrief | null>(null);
  const [vehicleQuery, setVehicleQuery] = useState("");
  const [vehicleResults, setVehicleResults] = useState<LinkedVehicle[]>([]);
  const [vehicle, setVehicle] = useState<LinkedVehicle | null>(null);
  const [description, setDescription] = useState("");
  const [payType, setPayType] = useState("Customer Pay");
  const [preferredContact, setPreferredContact] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const dirty=!!customer||!!vehicle||!!description.trim()||!!customerQuery.trim()||!!vehicleQuery.trim()||payType!=="Customer Pay"||!!preferredContact;
  useEffect(()=>{onDraftOpenChange?.(dirty);return()=>onDraftOpenChange?.(false)},[dirty,onDraftOpenChange]);
  useEffect(()=>{onSavingChange?.(busy);return()=>onSavingChange?.(false)},[busy,onSavingChange]);
  const [confirmClose, setConfirmClose] = useState(false);
  function requestClose() {
    if (busy) return;
    if (customer || vehicle || description.trim()) setConfirmClose(true);
    else onClose();
  }
  const textClass = tc(theme, "bg-zinc-900 border-zinc-700 text-white placeholder:text-zinc-600", "bg-white border-zinc-300 text-black placeholder:text-zinc-400");

  async function handleCreate() {
    if (!customer || !vehicle || !description.trim()) {
      setError("Customer, vehicle, and a stated concern are all required.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const ro = await createRepairOrder(vehicle.id, customer.id, description.trim(), payType, preferredContact || undefined);
      onCreated(ro.id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <WorkOverlay data-department-work="" className={inline ? "workspace-inline-editor" : "fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"} onClick={inline ? undefined : requestClose}>
      <div
        onClick={(e) => e.stopPropagation()}
        className={inline ? "workspace-editor-surface p-5 space-y-3" : tc(theme, "w-full max-w-lg rounded-xl border border-black/20 bg-brand-ink text-white p-5 space-y-3", "w-full max-w-lg rounded-xl border border-zinc-200 bg-white text-black p-5 space-y-3")}
      >
        <div className="flex items-center justify-between">
          <div className="work-detail-title">Check In New RO</div>
          <WorkButton type="submit" disabled={busy} onClick={requestClose} className="text-xs text-zinc-500 hover:text-white transition">{inline ? "← Back to Service work" : "✕ Close"}</WorkButton>
        </div>

        {confirmClose && <section role="alert" className="rounded-lg border p-3 space-y-2"><p>Keep this intake draft or discard it before leaving.</p><WorkButton type="submit" onClick={()=>setConfirmClose(false)}>Keep editing</WorkButton><WorkButton type="submit" disabled={busy} onClick={onClose}>Discard intake draft</WorkButton></section>}
        <p className="text-sm">Select the customer and the vehicle being serviced, then record their concern. Check-in creates a linked repair order; it does not send a customer message.</p>
        {error && <div className="text-xs px-3 py-2 rounded-lg bg-red-500/15 border border-red-500/40 text-red-300">{error}</div>}

        <div>
          <div className="text-xs text-zinc-500 mb-1">Customer</div>
          {customer ? (
            <div className="flex items-center justify-between text-xs rounded border border-zinc-800 px-2 py-1.5">
              <span>{customer.name} {customer.phone ? `· ${customer.phone}` : ""}</span>
              <span className="flex items-center gap-2">
                {customer.phone && <CommsQuickActions customerId={customer.id} phone={customer.phone} name={customer.name} size="xs" />}
                <WorkButton type="submit" onClick={() => setCustomer(null)} className="text-zinc-500 hover:text-white">Change</WorkButton>
              </span>
            </div>
          ) : (
            <>
              <WorkField label="Search customer by name/email/phone"><WorkInput
                value={customerQuery}
                onChange={(e) => { setCustomerQuery(e.target.value); searchCustomers(e.target.value).then(setCustomerResults); }}
                placeholder="Search customer by name/email/phone…"
                className={`w-full rounded-md border px-2 py-1.5 text-xs ${textClass}`}
              /></WorkField>
              {customerResults.length > 0 && (
                <div className="mt-1 max-h-32 overflow-y-auto space-y-0.5">
                  {customerResults.map((c) => (
                    <WorkButton type="submit" key={c.id} onClick={() => { setCustomer(c); setCustomerResults([]); setCustomerQuery(""); }} className="w-full text-left text-xs rounded border border-zinc-800 px-2 py-1 hover:border-brand-blue transition">
                      {c.name} {c.phone ? `· ${c.phone}` : ""}
                    </WorkButton>
                  ))}
                </div>
              )}
            </>
          )}
        </div>

        <div>
          <div className="text-xs text-zinc-500 mb-1">Vehicle</div>
          {vehicle ? (
            <div className="flex items-center justify-between text-xs rounded border border-zinc-800 px-2 py-1.5">
              <span>{vehicle.year} {vehicle.make} {vehicle.model} {vehicle.trim || ""}</span>
              <WorkButton type="submit" onClick={() => setVehicle(null)} className="text-zinc-500 hover:text-white">Change</WorkButton>
            </div>
          ) : (
            <>
              <WorkField label="Search vehicle by VIN/year/make/model"><WorkInput
                value={vehicleQuery}
                onChange={(e) => { setVehicleQuery(e.target.value); searchInventoryForPost(e.target.value).then(setVehicleResults); }}
                placeholder="Search vehicle by VIN/year/make/model…"
                className={`w-full rounded-md border px-2 py-1.5 text-xs ${textClass}`}
              /></WorkField>
              {vehicleResults.length > 0 && (
                <div className="mt-1 max-h-32 overflow-y-auto space-y-0.5">
                  {vehicleResults.map((v) => (
                    <WorkButton type="submit" key={v.id} onClick={() => { setVehicle(v); setVehicleResults([]); setVehicleQuery(""); }} className="w-full text-left text-xs rounded border border-zinc-800 px-2 py-1 hover:border-brand-blue transition">
                      {v.year} {v.make} {v.model} {v.trim || ""}
                    </WorkButton>
                  ))}
                </div>
              )}
            </>
          )}
        </div>

        <div>

          <WorkField label="Customer's Stated Concern"><WorkTextarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="e.g. Grinding noise, occurs at highway speed…"
            rows={2}
            className={`w-full rounded-md border px-2 py-1.5 text-xs ${textClass}`}
          /></WorkField>
        </div>

        <div className="grid grid-cols-2 gap-2">
          <div>

            <WorkField label="Pay Type"><WorkSelect value={payType} onChange={(e) => setPayType(e.target.value)} className={`w-full rounded-md border px-2 py-1.5 text-xs ${textClass}`}>
              <option>Customer Pay</option>
              <option>Warranty</option>
              <option>Internal</option>
            </WorkSelect></WorkField>
          </div>
          <div>

            <WorkField label="Preferred Contact"><WorkSelect value={preferredContact} onChange={(e) => setPreferredContact(e.target.value)} className={`w-full rounded-md border px-2 py-1.5 text-xs ${textClass}`}>
              <option value="">Not specified</option>
              <option value="call">Call</option>
              <option value="text">Text</option>
              <option value="email">Email</option>
            </WorkSelect></WorkField>
          </div>
        </div>

        <WorkButton type="submit" variant="primary" disabled={busy} onClick={handleCreate} className="w-full text-xs px-3 py-2 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50">
          {busy ? "Checking In…" : "Check In & Create RO"}
        </WorkButton>
      </div>
    </WorkOverlay>
  );
}

export type RoWorkspaceTab = "overview" | "concerns" | "estimate" | "parts" | "qc" | "pickup" | "followup" | "inspection" | "transportation" | "handoff" | "timeline";

export function RoWorkspaceModal({
  theme,
  inline = false,
  returnLabel = "Back to repair orders",
  onDraftOpenChange,
  onSavingChange,
  initialTab = "overview",
  roId,
  catalog,
  onClose,
  onChanged,
}: {
  theme: Theme;
  inline?: boolean;
  returnLabel?: string;
  onDraftOpenChange?: (open: boolean) => void;
  onSavingChange?: (saving: boolean) => void;
  initialTab?: RoWorkspaceTab;
  roId: string;
  catalog: RoCatalog;
  onClose: () => void;
  onChanged: () => void;
}) {
  const [data, setData] = useState<RoWorkspace | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<RoWorkspaceTab>(initialTab);
  useEffect(()=>setTab(initialTab),[initialTab]);

  const [concernDesc, setConcernDesc] = useState("");
  const [concernOccurs, setConcernOccurs] = useState("");
  const [estimateAmount, setEstimateAmount] = useState("");
  const [declineReason, setDeclineReason] = useState("");
  const [partDesc, setPartDesc] = useState("");
  const [partsNotes, setPartsNotes] = useState("");
  const [commChannel, setCommChannel] = useState<CommChannel>("text");
  const [commBody, setCommBody] = useState("");

  const [dviCatalog, setDviCatalog] = useState<DviCatalog | null>(null);
  const [inspection, setInspection] = useState<Inspection | null>(null);
  const [inspectionError, setInspectionError] = useState<string | null>(null);
  const [selectedFindings, setSelectedFindings] = useState<string[]>([]);
  const [mediaType,setMediaType]=useState<"photo"|"video">("photo");
  const [photoUrlDraft, setPhotoUrlDraft] = useState<Record<string, string>>({});
  const [inspectionHistory, setInspectionHistory] = useState<InspectionHistory | null>(null);
  const [inspectionHistoryError, setInspectionHistoryError] = useState<string | null>(null);

  const [approvalLink, setApprovalLink] = useState<ApprovalLinkStatus | null>(null);
  const [approvalLinkError, setApprovalLinkError] = useState<string | null>(null);
  const [approvalLinkCopied, setApprovalLinkCopied] = useState(false);

  const [transportation, setTransportation] = useState<RoTransportationSummary | null>(null);
  const [transportationError, setTransportationError] = useState<string | null>(null);
  const [loanerFleet, setLoanerFleet] = useState<LoanerVehicleBrief[]>([]);
  const [serviceEmployees, setServiceEmployees] = useState<ServiceEmployeeBrief[]>([]);
  const [checkoutLoanerId, setCheckoutLoanerId] = useState("");
  const [checkoutOdometer, setCheckoutOdometer] = useState("");
  const [checkoutFuel, setCheckoutFuel] = useState("Full");
  const [checkoutExpectedReturn, setCheckoutExpectedReturn] = useState("");
  const [checkinOdometer, setCheckinOdometer] = useState("");
  const [checkinFuel, setCheckinFuel] = useState("Full");
  const [shuttleDirection, setShuttleDirection] = useState<ShuttleDirection>("to_dealership");
  const [shuttlePickup, setShuttlePickup] = useState("");
  const [shuttleDropoff, setShuttleDropoff] = useState("");
  const [shuttleTime, setShuttleTime] = useState("");
  const [shuttleDriverPick, setShuttleDriverPick] = useState<Record<string, string>>({});
  const [fleetAdminOpen, setFleetAdminOpen] = useState(false);
  const [fullFleet, setFullFleet] = useState<LoanerVehicleBrief[]>([]);
  const [newLoanerMake, setNewLoanerMake] = useState("");
  const [newLoanerModel, setNewLoanerModel] = useState("");
  const [newLoanerYear, setNewLoanerYear] = useState("");
  const [newLoanerVin, setNewLoanerVin] = useState("");
  const [newLoanerMileage, setNewLoanerMileage] = useState("");

  const [handoff, setHandoff] = useState<RoHandoffStatus | null>(null);
  const [handoffError, setHandoffError] = useState<string | null>(null);
  const [salesEmployees, setSalesEmployees] = useState<SalesEmployeeBrief[]>([]);
  const [handoffAssignTo, setHandoffAssignTo] = useState("");
  const [handoffNotes, setHandoffNotes] = useState("");
  const [handoffDismissReason, setHandoffDismissReason] = useState("");
  const [handoffFlagNotes, setHandoffFlagNotes] = useState("");

  const [concernNotes, setConcernNotes] = useState<Record<string, string>>({});
  const [concernOutcomes, setConcernOutcomes] = useState<Record<string, "resolved" | "declined" | "deferred">>({});
  const [followupOutcome, setFollowupOutcome] = useState("");
  const [followupDate, setFollowupDate] = useState("");
  const [followupAction, setFollowupAction] = useState("");
  const [returnRecipient, setReturnRecipient] = useState("");
  const [settlementReference, setSettlementReference] = useState("");
  const [handoverConfirmed, setHandoverConfirmed] = useState(false);
  const [returnNotes, setReturnNotes] = useState("");
  const [returnTransport, setReturnTransport] = useState("");
  const [returnAcknowledged, setReturnAcknowledged] = useState(false);
  const [partStatusDrafts, setPartStatusDrafts] = useState<Record<string, string>>({});
  const [confirmClose, setConfirmClose] = useState(false);
  const [inspectionCategory, setInspectionCategory] = useState("");
  const hasCoreDraft = Object.values(photoUrlDraft).some(v=>v.trim()) || !!followupOutcome.trim() || !!followupDate || !!followupAction.trim() || !!returnRecipient.trim() || !!settlementReference.trim() || !!returnNotes.trim() || Object.values(concernNotes).some(value => value.trim()) || Object.keys(partStatusDrafts).length > 0 || [concernDesc, concernOccurs, estimateAmount, partDesc, commBody].some(value => value.trim());
  useEffect(() => { onDraftOpenChange?.(hasCoreDraft); return () => onDraftOpenChange?.(false); }, [hasCoreDraft, onDraftOpenChange]);
  useEffect(() => { onSavingChange?.(busy); return () => onSavingChange?.(false); }, [busy, onSavingChange]);
  function requestClose() {
    if (busy) return;
    if (hasCoreDraft) setConfirmClose(true);
    else onClose();
  }

  function refresh() {
    setLoading(true);
    setError(null);
    getRoWorkspace(roId)
      .then(setData)
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }

  function refreshInspection() {
    Promise.all([getDviCatalog(), getInspection(roId)])
      .then(([c, i]) => { setDviCatalog(c); setInspection(i); })
      .catch((e) => setInspectionError((e as Error).message));
  }

  function refreshInspectionHistory(vin: string) {
    getVehicleInspectionHistory(vin)
      .then(setInspectionHistory)
      .catch((e) => setInspectionHistoryError((e as Error).message));
  }

  function refreshApprovalLink() {
    getApprovalLinkStatus(roId)
      .then(setApprovalLink)
      .catch((e) => setApprovalLinkError((e as Error).message));
  }

  function refreshTransportation() {
    getRoTransportationSummary(roId)
      .then(setTransportation)
      .catch((e) => setTransportationError((e as Error).message));
  }

  function refreshHandoff() {
    getRoHandoffStatus(roId)
      .then(setHandoff)
      .catch((e) => setHandoffError((e as Error).message));
  }

  useEffect(() => {
    const previousFocus = document.activeElement;
    document.getElementById("repair-order-dialog")?.focus();
    return () => {
      if (previousFocus instanceof HTMLElement && previousFocus.isConnected) previousFocus.focus();
    };
  }, [roId]);

  useEffect(refresh, [roId]);
  useEffect(refreshInspection, [roId]);
  useEffect(refreshApprovalLink, [roId]);
  useEffect(refreshTransportation, [roId]);
  useEffect(refreshHandoff, [roId]);
  useEffect(() => {
    if (data?.vehicle?.vin) refreshInspectionHistory(data.vehicle.vin);
  }, [data?.vehicle?.vin]);
  useEffect(() => {
    listLoanerFleet("available").then((r) => setLoanerFleet(r.fleet)).catch(() => {});
    getServiceEmployees().then(setServiceEmployees).catch(() => {});
    getSalesEmployees().then(setSalesEmployees).catch(() => {});
  }, [roId]);

  async function withHandoffBusy(fn: () => Promise<unknown>) {
    setBusy(true);
    setHandoffError(null);
    try {
      await fn();
      refreshHandoff();
    } catch (e) {
      setHandoffError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function withTransportationBusy(fn: () => Promise<unknown>) {
    setBusy(true);
    setTransportationError(null);
    try {
      await fn();
      refreshTransportation();
      listLoanerFleet("available").then((r) => setLoanerFleet(r.fleet)).catch(() => {});
      if (fleetAdminOpen) refreshFullFleet();
    } catch (e) {
      setTransportationError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function refreshFullFleet() {
    listLoanerFleet().then((r) => setFullFleet(r.fleet)).catch(() => {});
  }

  async function withApprovalLinkBusy(fn: () => Promise<unknown>) {
    setBusy(true);
    setApprovalLinkError(null);
    setApprovalLinkCopied(false);
    try {
      await fn();
      refreshApprovalLink();
    } catch (e) {
      setApprovalLinkError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function approvalLinkUrl(path: string): string {
    if (typeof window === "undefined") return path;
    return `${window.location.origin}${path}`;
  }

  async function withInspectionBusy(fn: () => Promise<unknown>) {
    setBusy(true);
    setInspectionError(null);
    try {
      await fn();
      refreshInspection();
      return true;
    } catch (e) {
      setInspectionError((e as Error).message);
      return false;
    } finally {
      setBusy(false);
    }
  }

  const textClass = tc(theme, "bg-zinc-900 border-zinc-700 text-white placeholder:text-zinc-600", "bg-white border-zinc-300 text-black placeholder:text-zinc-400");
  const cardClass = tc(theme, "rounded-lg border border-black/20 bg-brand-charcoal p-3", "rounded-lg border border-zinc-200 bg-zinc-50 p-3");

  async function withBusy(fn: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      refresh();
      onChanged();
      return true;
    } catch (e) {
      setError((e as Error).message);
      return false;
    } finally {
      setBusy(false);
    }
  }

  const TABS: { key: typeof tab; label: string }[] = [
    { key: "overview", label: "Overview" },
    { key: "concerns", label: "Concerns" },
    { key: "estimate", label: "Estimate & Approval" },
    { key: "parts", label: "Parts" },
    { key: "qc", label: "Quality Control" },
    { key: "pickup", label: "Pickup & Return" },
    { key: "followup", label: "Follow-up" },
    { key: "inspection", label: "Inspection (DVI)" },
    { key: "transportation", label: "Loaner & Shuttle" },
    { key: "handoff", label: "Sales Handoff" },
    { key: "timeline", label: "Timeline & Comms" },
  ];

  return (
    <WorkOverlay data-department-work="" className={inline ? "workspace-inline-editor" : "fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"} onClick={inline ? undefined : requestClose}>
      <div
        id="repair-order-dialog"
        role={inline ? "region" : "dialog"}
        aria-modal={inline ? undefined : "true"}
        aria-label="Repair order workspace"
        tabIndex={-1}
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            event.preventDefault();
            event.stopPropagation();
            requestClose();
          }
          if (!inline && event.key === "Tab") {
            const controls = Array.from(event.currentTarget.querySelectorAll<HTMLElement>('button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), a[href], [tabindex="0"]'))
              .filter(control => control.getClientRects().length > 0);
            const first = controls[0];
            const last = controls[controls.length - 1];
            if (!first) { event.preventDefault(); return; }
            const active = document.activeElement;
            if (event.shiftKey && (active === first || active === event.currentTarget)) {
              event.preventDefault(); last.focus();
            } else if (!event.shiftKey && (active === last || active === event.currentTarget)) {
              event.preventDefault(); first.focus();
            }
          }
        }}
        onClick={(e) => e.stopPropagation()}
        className={inline ? "workspace-editor-surface p-5 space-y-4" : tc(theme, "w-full max-w-4xl max-h-[90vh] overflow-y-auto rounded-xl border border-black/20 bg-brand-ink text-white p-5 space-y-4", "w-full max-w-4xl max-h-[90vh] overflow-y-auto rounded-xl border border-zinc-200 bg-white text-black p-5 space-y-4")}
      >
        <WorkButton type="submit" disabled={busy} onClick={requestClose} className="min-h-11 text-sm underline disabled:opacity-50">{returnLabel}</WorkButton>
        {busy && <p role="status">Saving changes. Please wait before closing.</p>}
        {confirmClose && <section role="alert" className="rounded-lg border border-amber-500 p-3 space-y-2">
          <p>You have unsaved changes in this repair order.</p>
          <div className="flex flex-wrap gap-3">
            <WorkButton type="submit" autoFocus onClick={() => setConfirmClose(false)} className="min-h-11 px-3 rounded border">Keep editing</WorkButton>
            <WorkButton type="submit" disabled={busy} onClick={onClose} className="min-h-11 px-3 underline disabled:opacity-50">Discard draft and close</WorkButton>
          </div>
        </section>}
        {loading ? (
          <div role="status" className="text-sm text-zinc-400">Loading repair order…</div>
        ) : !data ? (
          <div role="alert"><p>{error || "Unable to load this repair order."}</p><WorkButton type="submit" onClick={refresh} className="mt-3 min-h-11 underline">Try again</WorkButton></div>
        ) : (
          <>
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="work-detail-title">{data.service_number} — {data.description}</div>
                <div className="text-xs text-zinc-500 mt-0.5">{data.vehicle.year} {data.vehicle.make} {data.vehicle.model} · {data.vehicle.vin} · {data.pay_type}</div>
              </div>
              {!inline && <WorkButton type="submit" onClick={requestClose} className="text-xs text-zinc-500 hover:text-white transition">✕ Close</WorkButton>}
            </div>

            {error && <div className="text-xs px-3 py-2 rounded-lg bg-red-500/15 border border-red-500/40 text-red-300">{error}</div>}

            <div className={cardClass}>
              <div className="flex items-center gap-1 flex-wrap">
                {data.workflow_checklist.map((c, i) => (
                  <span key={c.stage} className="flex items-center gap-1">
                    <span
                      className={`text-xs px-2 py-0.5 rounded-full font-brand uppercase tracking-wide ${
                        c.status === "complete" ? "bg-green-950/40 text-green-300" : c.status === "current" ? "bg-brand-blue text-white" : "bg-zinc-800 text-zinc-500"
                      }`}
                    >
                      {c.stage} {c.status === "complete" ? "✓" : c.status === "current" ? "●" : ""}
                    </span>
                    {i < data.workflow_checklist.length - 1 && <span className="text-zinc-700">→</span>}
                  </span>
                ))}
              </div>
              <div className="mt-2 flex items-center gap-1.5">
                <WorkSelect
                  aria-label="Move repair order to stage"
                  disabled={busy}
                  value=""
                  onChange={(e) => { if (e.target.value) withBusy(() => advanceRoStage(roId, e.target.value as RoStage)); }}
                  className={`rounded-md border px-2 py-1 text-xs ${textClass}`}
                >
                  <option value="">Move to stage…</option>
                  {catalog.stages.filter((s) => s !== data.ro_stage).map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </WorkSelect>
                {data.ro_stage_is_default && <span className="text-xs text-zinc-600 italic">(historical record, not yet moved through the live workflow)</span>}
              </div>
            </div>

            <div className="flex items-center gap-1.5 flex-wrap border-b border-zinc-800 pb-2">
              {TABS.map((t) => (
                <WorkButton data-work-view aria-pressed={tab === t.key} type="submit"
                  key={t.key}
                  onClick={() => setTab(t.key)}
                  className={`text-xs px-2.5 py-1 rounded-full font-brand uppercase tracking-wide transition ${
                    tab === t.key ? "bg-brand-blue text-white" : "bg-zinc-200/10 text-zinc-400 hover:text-white"
                  }`}
                >
                  {t.label}
                </WorkButton>
              ))}
            </div>

            {tab === "overview" && (
              <>
                {data.customer.id && <CustomerLoyaltyPanel key={data.customer.id} customerId={data.customer.id}/>}
                <div className={cardClass}>
                  <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Customer Information</div>
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div><span className="text-zinc-500">Customer</span><div>{data.customer.name || "—"}</div></div>
                    <div><span className="text-zinc-500">Preferred Contact</span><div>{data.customer.preferred_contact_method || "—"}</div></div>
                    <div><span className="text-zinc-500">Phone</span><div>{data.customer.phone || "—"}</div></div>
                    <div><span className="text-zinc-500">Email</span><div>{data.customer.email || "—"}</div></div>
                  </div>
                </div>

                <div className={cardClass}>
                  <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Vehicle Information</div>
                  <div className="grid grid-cols-3 gap-2 text-xs">
                    <div><span className="text-zinc-500">VIN</span><div>{data.vehicle.vin || "—"}</div></div>
                    <div><span className="text-zinc-500">Mileage</span><div>{data.vehicle.mileage || "—"}</div></div>
                    <div><span className="text-zinc-500">Technician</span><div>{data.technician || "Unassigned"}</div></div>
                  </div>
                  <div className="mt-2 pt-2 border-t border-zinc-800 grid grid-cols-2 gap-2 text-xs">
                    <div>
                      <span className="text-zinc-500">Warranty Status</span>
                      <div className={data.vehicle.warranty_status.status === "likely_covered" ? "text-green-400" : ""}>
                        {data.vehicle.warranty_status.status.replace(/_/g, " ")}
                      </div>
                      <div className="text-xs text-zinc-600 italic mt-0.5">{data.vehicle.warranty_status.note}</div>
                    </div>
                    <div>
                      <span className="text-zinc-500">Recall Status</span>
                      <div className={data.vehicle.recall_status.count > 0 ? "text-amber-400" : ""}>
                        {data.vehicle.recall_status.count > 0 ? `${data.vehicle.recall_status.count} open recall(s)` : "No open recalls"}
                      </div>
                      {data.vehicle.recall_status.open_recalls.map((r) => (
                        <div key={r.id} className="text-xs text-zinc-500">{r.recall_number} — {r.description}</div>
                      ))}
                    </div>
                  </div>
                  {data.vehicle.vin_match && data.vehicle.vin_match.checked && (
                    <div className="mt-2 pt-2 border-t border-zinc-800 text-xs">
                      <span className="text-zinc-500">VIN Match Check</span>
                      {data.vehicle.vin_match.valid_format ? (
                        data.vehicle.vin_match.mismatches.length > 0 ? (
                          <div className="text-amber-400 mt-0.5">
                            ⚠ {data.vehicle.vin_match.mismatches.map((m) => `${m.field}: stored "${m.stored}" vs. decoded "${m.decoded}"`).join("; ")}
                          </div>
                        ) : data.vehicle.vin_match.compared_something ? (
                          <div className="text-green-400 mt-0.5">✅ VIN matches on-file Year/Make</div>
                        ) : (
                          <div className="text-zinc-500 mt-0.5">{data.vehicle.vin_match.note}</div>
                        )
                      ) : (
                        <div className="text-zinc-500 mt-0.5">{data.vehicle.vin_match.format_error}</div>
                      )}
                    </div>
                  )}
                </div>
              </>
            )}

            {tab === "concerns" && (
              <div className={cardClass}>
                <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Concern Tracking</div><p className="mb-3 text-sm">Record what actually happened. Declined or deferred work remains visible for pickup review; it does not mean the repair was completed or the vehicle is safe to drive.</p>
                <div className="space-y-1.5 mb-2">
                  {data.concerns.map((c) => (
                    <div key={c.id} className="text-xs rounded border border-zinc-800 px-2 py-1.5">
                      <div className="flex items-center justify-between">
                        <span className={c.status === "resolved" ? "line-through text-zinc-500" : ""}>{c.description}</span>
                        <span className={`text-xs px-1.5 py-0.5 rounded ${c.status === "resolved" ? "bg-green-950/40 text-green-300" : "bg-amber-950/40 text-amber-300"}`}>{c.status}</span>
                      </div>
                      {c.occurs_at && <div className="text-xs text-zinc-500">Occurs at: {c.occurs_at}</div>}
                      {c.resolution_notes && <p className="mt-2 text-sm">{c.resolution_notes}</p>}
                      {c.status !== "resolved" && (
                        <div className="mt-2 space-y-2">
                          <label className="block">Outcome for {c.description}
                            <WorkSelect disabled={busy} value={concernOutcomes[c.id] ?? "resolved"} onChange={e=>setConcernOutcomes(previous=>({...previous,[c.id]:e.target.value as "resolved" | "declined" | "deferred"}))} className={`ml-2 min-h-11 rounded border px-2 ${textClass}`}>
                              <option value="resolved">Repair completed</option><option value="declined">Customer declined</option><option value="deferred">Deferred for later</option>
                            </WorkSelect>
                          </label>
                          <label className="block">Repair or decision notes for {c.description}
                            <WorkTextarea disabled={busy} value={concernNotes[c.id] ?? ""} onChange={e=>setConcernNotes(previous=>({...previous,[c.id]:e.target.value}))} className={`block w-full rounded border p-2 text-sm ${textClass}`} placeholder="Describe the work completed, or who made the decision and the follow-up needed." />
                          </label>
                          <WorkButton type="submit" variant="primary" disabled={busy || !concernNotes[c.id]?.trim()} onClick={() => withBusy(() => resolveConcern(roId,c.id,concernNotes[c.id],concernOutcomes[c.id] ?? "resolved")).then(saved=>{if(saved)setConcernNotes(previous=>{const next={...previous};delete next[c.id];return next;});})} className="min-h-11 rounded bg-brand-blue px-3 text-white disabled:opacity-50">Save concern outcome</WorkButton>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
                <div className="flex items-center gap-1.5 flex-wrap">
                  <WorkField label="New concern"><WorkInput disabled={busy} value={concernDesc} onChange={(e) => setConcernDesc(e.target.value)} placeholder="New concern…" className={`flex-1 rounded-md border px-2 py-1 text-xs ${textClass}`} /></WorkField>
                  <WorkField label="Occurs at (optional)"><WorkInput disabled={busy} value={concernOccurs} onChange={(e) => setConcernOccurs(e.target.value)} placeholder="Occurs at (optional)" className={`flex-1 rounded-md border px-2 py-1 text-xs ${textClass}`} /></WorkField>
                  <WorkButton type="submit" variant="primary" disabled={busy || !concernDesc.trim()} onClick={() => withBusy(() => addConcern(roId, concernDesc, concernOccurs)).then(saved => { if (saved) { setConcernDesc(""); setConcernOccurs(""); } })} className="text-xs px-2.5 py-1 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50">Add</WorkButton>
                </div>
              </div>
            )}

            {tab === "estimate" && (
              <div className={cardClass}>
                <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Estimate & Customer Approval</div>
                <p className="text-sm mb-3">Saving records an internal estimate; it does not email or text the customer. Record a decision only after receiving it from the customer.</p>
                {data.estimate ? (
                  <div className="text-xs space-y-1">
                    <div>Amount: <span className="font-semibold">{money(data.estimate.amount)}</span></div>
                    <div className="text-zinc-500">Recorded {fmt(data.estimate.sent_at)} by {data.estimate.sent_by}</div>
                    {data.estimate.approved === true && <div className="text-green-400">✅ Customer approved {fmt(data.estimate.approved_at)}</div>}
                    {data.estimate.approved === false && <div className="text-red-400">❌ Customer declined -- {data.estimate.decline_reason}</div>}
                    {data.estimate.approved === null && (
                      <div className="flex items-center gap-1.5 mt-2">
                        <WorkButton type="submit" disabled={busy} onClick={() => withBusy(() => recordCustomerApproval(roId, true))} className="text-xs px-2.5 py-1 rounded bg-green-700 text-white hover:opacity-90 transition disabled:opacity-50">Record Approval</WorkButton>
                        <WorkField label="Decline reason"><WorkInput value={declineReason} onChange={(e) => setDeclineReason(e.target.value)} placeholder="Decline reason…" className={`flex-1 rounded-md border px-2 py-1 text-xs ${textClass}`} /></WorkField>
                        <WorkButton type="submit" variant="danger" disabled={busy} onClick={() => withBusy(() => recordCustomerApproval(roId, false, declineReason))} className="text-xs px-2.5 py-1 rounded bg-red-700 text-white hover:opacity-90 transition disabled:opacity-50">Record Decline</WorkButton>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="flex items-center gap-1.5">
                    <WorkField label="Estimate amount"><WorkInput type="number" disabled={busy} value={estimateAmount} onChange={(e) => setEstimateAmount(e.target.value)} placeholder="Estimate amount…" className={`w-40 rounded-md border px-2 py-1 text-xs ${textClass}`} /></WorkField>
                    <WorkButton type="submit" variant="primary" disabled={busy || !estimateAmount || !Number.isFinite(Number(estimateAmount)) || Number(estimateAmount) < 0} onClick={() => withBusy(() => sendEstimate(roId, parseFloat(estimateAmount))).then(saved => { if (saved) setEstimateAmount(""); })} className="text-xs px-2.5 py-1 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50">Save estimate for approval</WorkButton>
                  </div>
                )}
              </div>
            )}

            {tab === "estimate" && (
              <div className={cardClass}>
                <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Customer-Facing Approval Link</div>
                {!data.estimate ? (
                  <div className="text-xs text-zinc-500">Save an estimate first -- a link can&apos;t be generated until there&apos;s something for the customer to approve.</div>
                ) : (
                  <div className="text-xs space-y-2">
                    {approvalLinkError && <div className="text-red-400">{approvalLinkError}</div>}
                    {approvalLink?.exists ? (
                      <>
                        <div className="flex items-center gap-1.5">
                          <span className={approvalLink.revoked ? "text-red-400" : "text-green-400"}>
                            {approvalLink.revoked ? "🔒 Revoked" : "🔗 Active"}
                          </span>
                          <span className="text-zinc-500">created {fmt(approvalLink.created_at ?? null)} by {approvalLink.created_by}</span>
                        </div>
                        {!approvalLink.revoked && (
                          <div className="flex items-center gap-1.5">
                            <WorkInput aria-label="Customer approval link" readOnly value={approvalLinkUrl(approvalLink.path ?? "")} className={`flex-1 rounded-md border px-2 py-1 text-xs ${textClass}`} />
                            <WorkButton type="submit"
                              onClick={() => {
                                navigator.clipboard?.writeText(approvalLinkUrl(approvalLink.path ?? ""));
                                setApprovalLinkCopied(true);
                              }}
                              className="text-xs px-2.5 py-1 rounded bg-zinc-200/10 text-zinc-300 hover:text-white transition"
                            >
                              {approvalLinkCopied ? "Copied!" : "Copy"}
                            </WorkButton>
                            <WorkButton type="submit" variant="danger" disabled={busy} onClick={() => withApprovalLinkBusy(() => revokeApprovalLink(roId))} className="text-xs px-2.5 py-1 rounded bg-red-700 text-white hover:opacity-90 transition disabled:opacity-50">Revoke</WorkButton>
                          </div>
                        )}
                        {approvalLink.revoked && (
                          <WorkButton type="submit" variant="primary" disabled={busy} onClick={() => withApprovalLinkBusy(() => generateApprovalLink(roId))} className="text-xs px-2.5 py-1 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50">Generate New Link</WorkButton>
                        )}
                      </>
                    ) : (
                      <WorkButton type="submit" variant="primary" disabled={busy} onClick={() => withApprovalLinkBusy(() => generateApprovalLink(roId))} className="text-xs px-2.5 py-1 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50">Generate Approval Link</WorkButton>
                    )}
                  </div>
                )}
              </div>
            )}

            {tab === "parts" && (
              <>
                <div className={cardClass}>
                  <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">RO Parts Status</div>
                  <div className="flex items-center gap-1.5 flex-wrap">
                    {catalog.parts_statuses.map((s) => (
                      <WorkButton type="submit"  key={s} disabled={busy} onClick={() => withBusy(() => updatePartsStatus(roId, s, partsNotes))} className={`text-xs px-2.5 py-1 rounded font-brand uppercase tracking-wide transition disabled:opacity-50 ${data.parts_status?.status === s ? "bg-brand-blue text-white" : "bg-zinc-200/10 text-zinc-400 hover:text-white"}`}>
                        {s.replace(/_/g, " ")}
                      </WorkButton>
                    ))}
                  </div>
                  <WorkField label="Notes"><WorkInput value={partsNotes} onChange={(e) => setPartsNotes(e.target.value)} placeholder="Notes (e.g. ETA)…" className={`mt-2 w-full rounded-md border px-2 py-1 text-xs ${textClass}`} /></WorkField>
                  {data.parts_status && <div className="mt-1 text-xs text-zinc-500">{data.parts_status.notes}</div>}
                </div>

                <div className={cardClass}>
                  <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Parts Requests</div>
                  <p className="text-sm mb-2">Requests appear in the Parts desk queue. Creating a request does not place a supplier order. Select a status, then save it. Record receipt or stock availability before installation; mark installed only after the work is done.</p>
                  <div className="space-y-1.5 mb-2">
                    {data.parts_requests.length === 0 ? (
                      <div className="text-xs text-zinc-600">No parts requested yet.</div>
                    ) : (
                      data.parts_requests.map((r) => (
                        <div key={r.id} className="flex items-center justify-between text-xs rounded border border-zinc-800 px-2 py-1.5">
                          <span>{r.description}</span>
                          <WorkSelect
                            aria-label={`Status for ${r.description}`}
                            disabled={busy}
                            value={partStatusDrafts[r.id] ?? r.status}
                            onChange={(e) => setPartStatusDrafts(previous => { const next = {...previous}; if(e.target.value === r.status) delete next[r.id]; else next[r.id] = e.target.value; return next; })}
                            className={`rounded-md border px-1.5 py-0.5 text-xs ${textClass}`}
                          >
                            {catalog.part_request_statuses.map((s) => <option key={s} value={s} disabled={s === "installed" && !["received", "in_stock", "installed"].includes(r.status)}>{s.replace(/_/g, " ")}</option>)}
                          </WorkSelect>
                          <WorkButton type="submit" variant="primary" aria-label={`Save status for ${r.description}`} disabled={busy || !partStatusDrafts[r.id]} onClick={() => withBusy(() => updatePartRequestStatus(roId, r.id, partStatusDrafts[r.id] as typeof r.status)).then(saved => { if(saved) setPartStatusDrafts(previous => { const next = {...previous}; delete next[r.id]; return next; }); })} className="min-h-11 rounded bg-brand-blue px-3 text-white disabled:opacity-50">Save status</WorkButton>
                        </div>
                      ))
                    )}
                  </div>
                  <div className="flex items-center gap-1.5">
                    <WorkField label="Part description"><WorkInput disabled={busy} value={partDesc} onChange={(e) => setPartDesc(e.target.value)} placeholder="Part description…" className={`flex-1 rounded-md border px-2 py-1 text-xs ${textClass}`} /></WorkField>
                    <WorkButton type="submit" variant="primary" disabled={busy || !partDesc.trim()} onClick={() => withBusy(() => requestPart(roId, partDesc)).then(saved => { if (saved) setPartDesc(""); })} className="text-xs px-2.5 py-1 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50">Request Part</WorkButton>
                  </div>
                </div>
              </>
            )}

            {tab === "qc" && (
              <div className={cardClass}>
                <div className="flex items-center justify-between mb-2">
                  <div className="text-xs font-brand uppercase tracking-wide text-zinc-500">Quality Control Process</div>
                  <span className={`text-xs px-2 py-0.5 rounded ${data.qc_ready_for_pickup ? "bg-green-950/40 text-green-300" : "bg-zinc-800 text-zinc-500"}`}>
                    {data.qc_ready_for_pickup ? "QC checklist complete" : "QC checklist incomplete"}
                  </span>
                </div>
                <p className="text-sm mb-3">Complete the workshop checks here, then review approvals, outstanding work and handover in Pickup &amp; Return.</p>
                <WorkButton data-work-view type="submit" className="min-h-11 rounded border px-3 mb-3" onClick={()=>setTab("pickup")}>Review pickup &amp; return →</WorkButton>
                <div className="space-y-1.5">
                  {catalog.qc_items.map((item) => {
                    const entry = data.qc_checklist[item];
                    return (
                      <label key={item} className="flex items-center gap-2 text-xs cursor-pointer">
                        <WorkInput
                          type="checkbox"
                          checked={entry?.complete || false}
                          disabled={busy}
                          onChange={(e) => withBusy(() => updateQcItem(roId, item, e.target.checked))}
                        />
                        <span className={entry?.complete ? "line-through text-zinc-500" : ""}>{QC_LABELS[item]}</span>
                        {entry?.updated_by && <span className="text-xs text-zinc-600">— {entry.updated_by}, {fmt(entry.updated_at)}</span>}
                      </label>
                    );
                  })}
                </div>
              </div>
            )}

            {tab === "pickup" && <div className={cardClass}>
                <section className="rounded border border-zinc-500/30 p-3 mb-3 space-y-2" aria-label="Pickup review">
                  <h3 className="font-semibold">Review before pickup</h3>


                  {(data.delivery_blockers?.length ?? 0) > 0 && <div className="rounded border border-amber-400/40 p-3"><p className="font-medium">Complete before normal delivery</p><ul className="list-disc pl-5">{data.delivery_blockers!.map(blocker=><li key={blocker}>{blocker}</li>)}</ul></div>}
                  <p className="text-sm">These checks do not verify payment or certify roadworthiness. Declined or deferred repairs require a separate return review.</p>
                  {data.return_handover ? <section aria-label="Recorded vehicle return" className="rounded border p-3"><h4 className="font-semibold">Vehicle return recorded — repairs not marked complete</h4><p>Received by: {data.return_handover.recipient} · {data.return_handover.transport.replace(/_/g," ")}</p><p>External settlement reference: {data.return_handover.settlement_reference}</p><p>Recorded {new Date(data.return_handover.recorded_at).toLocaleString()} by {data.return_handover.recorded_by}</p><p>Settlement is staff-recorded, not verified by a payment processor.</p>{data.return_handover.work_changed_since && <p>Work details changed after this return. Review the record before further action.</p>}</section> : data.return_review && <section aria-label="Record vehicle return" className="space-y-3 rounded border p-3"><h4 className="font-semibold">Record actual vehicle handover</h4><p>This records a custody return, not completed repairs or a payment. Confirm external settlement or no-charge authorization through your dealership process.</p>{!data.return_review.current && <p>Update the stale return review before handover.</p>}<label className="block">Received by<WorkInput className={`block w-full min-h-11 rounded border px-2 ${textClass}`} value={returnRecipient} onChange={e=>setReturnRecipient(e.target.value)} disabled={busy}/></label><label className="block">External settlement or no-charge reference<WorkInput className={`block w-full min-h-11 rounded border px-2 ${textClass}`} value={settlementReference} onChange={e=>setSettlementReference(e.target.value)} disabled={busy}/></label><label className="flex gap-2"><WorkInput type="checkbox" checked={handoverConfirmed} onChange={e=>setHandoverConfirmed(e.target.checked)} disabled={busy}/>Vehicle was handed over using the reviewed transport arrangement</label><WorkButton type="submit" variant="primary" className="min-h-11 rounded bg-brand-blue px-3 text-white disabled:opacity-50" disabled={busy || !data.return_review.current || !returnRecipient.trim() || !settlementReference.trim() || !handoverConfirmed} onClick={()=>withBusy(()=>recordReturnHandover(roId,returnRecipient,settlementReference,handoverConfirmed)).then(saved=>{if(saved){setReturnRecipient("");setSettlementReference("");setHandoverConfirmed(false);}})}>Record vehicle return</WorkButton></section>}

                  {data.concerns.some(c=>c.status==="declined" || c.status==="deferred") && <section aria-label="Unperformed work return review" className="space-y-3 rounded border p-3">
                    <h4 className="font-semibold">Plan a return with unfinished work</h4>
                    <p className="text-sm">Document the customer discussion and transport arrangements. Saving this review does not release the vehicle, verify payment, certify safety or mark repairs complete.</p>
                    {data.return_review && <div role="status"><p>{data.return_review.current ? "Return review recorded" : "Work details changed — review again"}</p><p>{data.return_review.notes}</p><p>Transport: {data.return_review.transport.replace(/_/g," ")}</p></div>}
                    <label className="block">Return transport<WorkSelect className={`block min-h-11 rounded border px-2 ${textClass}`} value={returnTransport} onChange={e=>setReturnTransport(e.target.value)} disabled={busy}><option value="">Choose transport…</option><option value="tow">Tow / carrier</option><option value="customer_pickup">Customer pickup</option><option value="other">Other documented arrangement</option></WorkSelect></label>
                    <label className="block">Unfinished work and return plan<WorkTextarea className={`block w-full rounded border p-2 ${textClass}`} value={returnNotes} onChange={e=>setReturnNotes(e.target.value)} disabled={busy}/></label>
                    <label className="flex gap-2"><WorkInput type="checkbox" checked={returnAcknowledged} onChange={e=>setReturnAcknowledged(e.target.checked)} disabled={busy}/>Unfinished work and the return plan have been reviewed with the customer</label>
                    <WorkButton type="submit" variant="primary" className="min-h-11 rounded bg-brand-blue px-3 text-white disabled:opacity-50" disabled={busy || !returnNotes.trim() || !returnTransport || !returnAcknowledged} onClick={()=>withBusy(()=>recordReturnReview(roId,returnTransport,returnNotes,returnAcknowledged)).then(saved=>{if(saved){setReturnNotes("");setReturnAcknowledged(false);}})}>Save return review</WorkButton>
                  </section>}

                  <p className="text-sm">Stage: {data.ro_stage}. QC completion alone does not confirm customer approval, payment or delivery.</p>
                  <p className="text-sm">{data.concerns.filter(c=>c.status!=="resolved").length} unresolved concerns · {data.parts_requests.filter(r=>r.status!=="installed").length} parts requests not marked installed</p>
                  <p className="text-sm">Estimate: {!data.estimate ? "not recorded" : data.estimate.approved===true ? "customer approval recorded" : data.estimate.approved===false ? "customer declined" : "awaiting customer decision"}</p>
                  <div className="flex flex-wrap gap-2"><WorkButton data-work-view type="submit" onClick={()=>setTab("concerns")} className="border rounded px-3 py-2 text-sm">Review concerns</WorkButton><WorkButton data-work-view type="submit" onClick={()=>setTab("estimate")} className="border rounded px-3 py-2 text-sm">Review approval</WorkButton><WorkButton data-work-view type="submit" onClick={()=>setTab("parts")} className="border rounded px-3 py-2 text-sm">Review parts</WorkButton></div>
                </section>
              <WorkButton data-work-view type="submit" className="min-h-11 rounded border px-3" onClick={()=>setTab("qc")}>Review quality checks</WorkButton>
              {data.return_handover && <WorkButton data-work-view type="submit" className="min-h-11 rounded border px-3 ml-2" onClick={()=>setTab("followup")}>Plan or record follow-up →</WorkButton>}
            </div>}
            {tab === "followup" && <div className={cardClass}>
              {data.return_handover && <section aria-label="Returned work follow-up" className="space-y-3 rounded border p-3">
                <h3 className="font-semibold">Next action after return</h3>
                {data.return_followup ? <>
                  <p>Owner: {data.return_followup.owner_id} · {data.return_followup.status === "completed" ? "Recorded follow-up" : `Due ${data.return_followup.due_date}`}</p>
                  <p>{data.return_followup.next_action}</p>
                  {data.return_followup.status === "completed" ? <div role="status"><p>Outcome: {data.return_followup.outcome}</p><p>Repairs remain open. Plan another follow-up if needed.</p></div> : <div className="space-y-2">
                    <p>Record the result. This does not close the repair order or complete deferred repairs.</p>
                    <label className="block">Follow-up outcome<WorkTextarea className={`block w-full rounded border p-2 ${textClass}`} disabled={busy} value={followupOutcome} onChange={e=>setFollowupOutcome(e.target.value)}/></label>
                    <WorkButton type="submit" variant="primary" className="min-h-11 rounded bg-brand-blue px-3 text-white disabled:opacity-50" disabled={busy || !followupOutcome.trim()} onClick={()=>withBusy(()=>completeReturnFollowup(roId,followupOutcome,data.return_followup!.updated_at)).then(saved=>{if(saved)setFollowupOutcome("");})}>Record follow-up outcome</WorkButton>
                  </div>}
                </> : <p>No follow-up plan recorded. The original advisor retains this work until someone takes ownership.</p>}
                <details open={!data.return_followup} className="rounded border p-3">
                  <summary className="cursor-pointer min-h-8 font-medium">{data.return_followup?.status === "completed" ? "Plan another follow-up" : data.return_followup ? "Change follow-up plan" : "Set follow-up plan"}</summary>
                  <p className="text-sm mb-2">Saving assigns this internal plan to you. No message or automatic reminder is sent.</p>
                  <div className="grid gap-3 sm:grid-cols-[12rem_1fr]">
                    <label>Follow-up due date (YYYY-MM-DD)<WorkInput type="text" placeholder="YYYY-MM-DD" maxLength={10} value={followupDate} onChange={e=>setFollowupDate(e.target.value)} className={`block w-full min-h-11 rounded border px-2 ${textClass}`} disabled={busy}/></label>
                    <label>Next action<WorkTextarea value={followupAction} onChange={e=>setFollowupAction(e.target.value)} className={`block w-full rounded border p-2 ${textClass}`} disabled={busy}/></label>
                  </div>
                  <WorkButton type="submit" variant="primary" className="mt-3 min-h-11 rounded bg-brand-blue px-3 text-white disabled:opacity-50" disabled={busy || !followupDate || !followupAction.trim()} onClick={()=>withBusy(()=>planReturnFollowup(roId,followupDate,followupAction)).then(saved=>{if(saved){setFollowupDate("");setFollowupAction("");}})}>Take ownership and save follow-up</WorkButton>
                </details>
              </section>}

              {!data.return_handover && <p>No unfinished-work vehicle return is recorded. Review pickup and return first; normal completed visits remain available through the existing Follow-Up stage.</p>}
              <WorkButton data-work-view type="submit" className="min-h-11 rounded border px-3 mt-3" onClick={()=>setTab("pickup")}>Review vehicle return</WorkButton>
            </div>}

            {tab === "inspection" && (
              <>
              <div className={cardClass}>
                <div className="flex items-center justify-between mb-2">
                  <div className="text-xs font-brand uppercase tracking-wide text-zinc-500">Digital Vehicle Inspection</div>
                  {inspection && (
                    <span className={`text-xs px-2 py-0.5 rounded ${inspection.status === "completed" ? "bg-green-950/40 text-green-300" : inspection.status === "in_progress" ? "bg-amber-950/40 text-amber-300" : "bg-zinc-800 text-zinc-500"}`}>
                      {inspection.status.replace(/_/g, " ")}
                    </span>
                  )}
                </div>

                {inspectionError && <div className="mb-2 text-xs px-3 py-2 rounded-lg bg-red-500/15 border border-red-500/40 text-red-300">{inspectionError}</div>}

                {!inspection || !dviCatalog ? (
                  <div className="text-xs text-zinc-600">Loading inspection…</div>
                ) : inspection.status === "not_started" ? (
                  <WorkButton type="submit" variant="primary" disabled={busy} onClick={() => withInspectionBusy(() => startInspection(roId))} className="text-xs px-3 py-1.5 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50">
                    Start Inspection
                  </WorkButton>
                ) : (
                  <>
                    <div className="flex items-center gap-2 mb-2 text-xs">
                      <span className="text-green-400">{inspection.summary.green} green</span>
                      <span className="text-amber-400">{inspection.summary.yellow} yellow</span>
                      <span className="text-red-400">{inspection.summary.red} red</span>
                      <span className="text-zinc-500">{inspection.summary.not_inspected} not inspected</span>
                    </div>

                    {inline && <label className="block text-sm mb-3">Inspection category<WorkSelect aria-label="Inspection category" className={`block w-full rounded-md border p-2 mt-1 ${textClass}`} value={inspectionCategory || Object.keys(dviCatalog.categories)[0]} onChange={e=>setInspectionCategory(e.target.value)}>{Object.entries(dviCatalog.categories).map(([key,category])=><option key={key} value={key}>{category.label}</option>)}</WorkSelect></label>}
                    <div className={inline ? "space-y-3" : "space-y-3 max-h-96 overflow-y-auto pr-1"}>
                      {Object.entries(dviCatalog.categories).filter(([key])=>!inline || key===(inspectionCategory || Object.keys(dviCatalog.categories)[0])).map(([catKey, cat]) => (
                        <div key={catKey}>
                          <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1">{cat.label}</div>
                          <div className="space-y-1">
                            {cat.items.map((itemName) => {
                              const itemKey = `${catKey}::${itemName}`;
                              const entry = inspection.items[itemKey];
                              if (!entry) return null;
                              const flagged = entry.status === "yellow" || entry.status === "red";
                              return (
                                <div key={itemKey} className="rounded border border-zinc-800 px-2 py-1.5">
                                  <div className="flex items-center justify-between gap-2">
                                    <div className="flex items-center gap-2 min-w-0">
                                      {flagged && inspection.status !== "completed" && (
                                        <WorkInput
                                          type="checkbox"
                                          checked={selectedFindings.includes(itemKey)}
                                          disabled={entry.concern_created}
                                          onChange={(e) => setSelectedFindings((prev) => e.target.checked ? [...prev, itemKey] : prev.filter((k) => k !== itemKey))}
                                        />
                                      )}
                                      <span className="text-xs truncate">{itemName}</span>
                                      {entry.concern_created && <span className="text-xs text-zinc-600 shrink-0">(concern created)</span>}
                                    </div>
                                    <WorkSelect
                                      aria-label={`${itemName} condition`}
                                      disabled={busy || inspection.status === "completed"}
                                      value={entry.status}
                                      onChange={(e) => withInspectionBusy(() => updateInspectionItem(roId, itemKey, e.target.value as InspectionStatus, entry.notes))}
                                      className={`shrink-0 rounded-md border px-1.5 py-0.5 text-xs ${textClass}`}
                                    >
                                      {dviCatalog.statuses.map((s) => <option key={s} value={s}>{s.replace(/_/g, " ")}</option>)}
                                    </WorkSelect>
                                  </div>
                                  {entry.status !== "not_inspected" && inspection.status !== "completed" && (
                                    <div className="mt-1 flex items-center gap-1.5">
                                      <WorkField label="Notes"><WorkInput
                                        defaultValue={entry.notes}
                                        placeholder="Notes…"
                                        onBlur={(e) => { if (e.target.value !== entry.notes) withInspectionBusy(() => updateInspectionItem(roId, itemKey, entry.status, e.target.value)); }}
                                        className={`flex-1 rounded-md border px-1.5 py-0.5 text-xs ${textClass}`}
                                      /></WorkField>
                                      <WorkField label="Media type"><WorkSelect value={mediaType} onChange={e=>setMediaType(e.target.value as "photo"|"video")}><option value="photo">Photo</option><option value="video">Video</option></WorkSelect></WorkField><WorkField label={`${mediaType === "photo" ? "Photo" : "Video"} URL`}><WorkInput
                                        value={photoUrlDraft[itemKey] || ""}
                                        onChange={(e) => setPhotoUrlDraft((prev) => ({ ...prev, [itemKey]: e.target.value }))}
                                        placeholder={`${mediaType === "photo" ? "Photo" : "Video"} URL…`}
                                        className={`flex-1 rounded-md border px-1.5 py-0.5 text-xs ${textClass}`}
                                      /></WorkField>
                                      <WorkButton type="submit"
                                        disabled={busy || !(photoUrlDraft[itemKey] || "").trim()}
                                        onClick={() => withInspectionBusy(() => attachInspectionPhoto(roId, itemKey, photoUrlDraft[itemKey],mediaType)).then((saved) => { if (saved) setPhotoUrlDraft((prev) => ({ ...prev, [itemKey]: "" })); })}
                                        className="shrink-0 text-xs px-1.5 py-0.5 rounded bg-zinc-700 text-white hover:opacity-90 transition disabled:opacity-50"
                                      >
                                        Attach
                                      </WorkButton>
                                    </div>
                                  )}
                                  <div className="work-actions">{[...entry.photo_urls.map(url=>({url,type:"Photo"})),...(entry.video_urls||[]).map(url=>({url,type:"Video"}))].filter(media=>/^https?:\/\//i.test(media.url)).map((media,index)=><a className="work-button" key={`${media.type}-${index}`} href={media.url} target="_blank" rel="noopener noreferrer">View {media.type.toLowerCase()} {index+1}</a>)}</div>
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      ))}
                    </div>

                    <div className="mt-2 flex items-center gap-2 flex-wrap">
                      {inspection.status !== "completed" && (
                        <WorkButton type="submit" variant="primary"
                          disabled={busy || inspection.summary.not_inspected > 0}
                          onClick={() => withInspectionBusy(() => completeInspection(roId))}
                          className="text-xs px-2.5 py-1 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50"
                        >
                          Complete Inspection
                        </WorkButton>
                      )}
                      {selectedFindings.length > 0 && (
                        <WorkButton type="submit" variant="primary"
                          disabled={busy}
                          onClick={() => withInspectionBusy(() => createConcernsFromInspection(roId, selectedFindings)).then(() => { setSelectedFindings([]); refresh(); })}
                          className="text-xs px-2.5 py-1 rounded border border-brand-blue text-brand-blue hover:bg-brand-blue/10 transition disabled:opacity-50"
                        >
                          Create Concern(s) From {selectedFindings.length} Selected Finding(s)
                        </WorkButton>
                      )}
                    </div>
                  </>
                )}
              </div>

              <div className={`${cardClass} mt-3`}>
                <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">
                  Vehicle Inspection History
                </div>
                {inspectionHistoryError && (
                  <div className="mb-2 text-xs px-3 py-2 rounded-lg bg-red-500/15 border border-red-500/40 text-red-300">{inspectionHistoryError}</div>
                )}
                {!inspectionHistory ? (
                  <div className="text-xs text-zinc-600">{data.vehicle.vin ? "Loading history…" : "A VIN is needed to look up earlier inspections. This repair order’s inspection is available above."}</div>
                ) : inspectionHistory.inspection_count === 0 ? (
                  <div className="text-xs text-zinc-600">No prior completed/in-progress inspections on file for this vehicle (VIN {inspectionHistory.vin || "—"}).</div>
                ) : (
                  <>
                    {inspectionHistory.recurring_findings.length > 0 && (
                      <div className="mb-3 rounded border border-amber-700/40 bg-amber-950/20 px-2.5 py-2">
                        <div className="text-xs font-brand uppercase tracking-wide text-amber-400 mb-1">Recurring Findings</div>
                        <div className="space-y-0.5">
                          {inspectionHistory.recurring_findings.map((f) => (
                            <div key={`${f.category}::${f.item}`} className="text-xs text-amber-300">
                              {f.label} — flagged in {f.occurrences} separate inspections
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    <div className="text-xs text-zinc-500 mb-1.5">
                      {inspectionHistory.inspection_count} inspection(s) across this vehicle's repair-order history
                    </div>

                    <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
                      {inspectionHistory.inspections.map((insp) => (
                        <div key={insp.ro_id} className="rounded border border-zinc-800 px-2.5 py-2">
                          <div className="flex items-center justify-between">
                            <div className="text-xs font-medium">
                              {insp.ro_id}{insp.ro_id === roId ? " (this RO)" : ""}
                            </div>
                            <span className={`text-xs px-2 py-0.5 rounded ${insp.dvi_status === "completed" ? "bg-green-950/40 text-green-300" : "bg-amber-950/40 text-amber-300"}`}>
                              {insp.dvi_status.replace(/_/g, " ")}
                            </span>
                          </div>
                          <div className="text-xs text-zinc-500 mt-0.5">{insp.service_date || "—"}</div>
                          <div className="flex items-center gap-2 mt-1 text-xs">
                            <span className="text-green-400">{insp.summary.green} green</span>
                            <span className="text-amber-400">{insp.summary.yellow} yellow</span>
                            <span className="text-red-400">{insp.summary.red} red</span>
                          </div>
                          {insp.flagged_items.length > 0 && (
                            <div className="mt-1 text-xs text-zinc-400">
                              {insp.flagged_items.map((fi) => `${fi.item} (${fi.status})`).join(", ")}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>

                    <div className="mt-2 text-xs text-zinc-600 italic">{inspectionHistory.note}</div>
                  </>
                )}
              </div>
              </>
            )}

            {tab === "transportation" && (
              <>
                {transportationError && <div className="text-red-400 text-xs mb-2">{transportationError}</div>}

                <div className={cardClass}>
                  <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Loaner Vehicle</div>
                  {transportation?.active_loaner_assignment ? (
                    <div className="text-xs space-y-1">
                      <div>
                        Loaner <span className="font-semibold">{transportation.active_loaner_assignment.loaner_vehicle_id}</span> checked out {fmt(transportation.active_loaner_assignment.checked_out_at)} by {transportation.active_loaner_assignment.checked_out_by}
                      </div>
                      <div className="text-zinc-500">Odometer out: {transportation.active_loaner_assignment.odometer_out} · Fuel: {transportation.active_loaner_assignment.fuel_out}</div>
                      {transportation.active_loaner_assignment.status === "overdue" && (
                        <div className="text-red-400">⚠ Overdue -- expected back {fmt(transportation.active_loaner_assignment.expected_return_at)}</div>
                      )}
                      <div className="flex items-center gap-1.5 mt-2">
                        <WorkField label="Odometer in"><WorkInput type="number" value={checkinOdometer} onChange={(e) => setCheckinOdometer(e.target.value)} placeholder="Odometer in…" className={`w-32 rounded-md border px-2 py-1 text-xs ${textClass}`} /></WorkField>
                        <WorkField label="Fuel level at check-in"><WorkSelect value={checkinFuel} onChange={(e) => setCheckinFuel(e.target.value)} className={`rounded-md border px-2 py-1 text-xs ${textClass}`}>
                          {["Full", "3/4", "1/2", "1/4", "Empty"].map((f) => <option key={f} value={f}>{f}</option>)}
                        </WorkSelect></WorkField>
                        <WorkButton type="submit"
                          disabled={busy || !checkinOdometer}
                          onClick={() => withTransportationBusy(() => checkinLoaner(transportation.active_loaner_assignment!.id, parseInt(checkinOdometer, 10), checkinFuel)).then(() => setCheckinOdometer(""))}
                          className="text-xs px-2.5 py-1 rounded bg-green-700 text-white hover:opacity-90 transition disabled:opacity-50"
                        >
                          Check In
                        </WorkButton>
                      </div>
                    </div>
                  ) : (
                    <div className="text-xs space-y-1.5">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <WorkField label="Loaner vehicle"><WorkSelect value={checkoutLoanerId} onChange={(e) => setCheckoutLoanerId(e.target.value)} className={`rounded-md border px-2 py-1 text-xs ${textClass}`}>
                          <option value="">Select available loaner…</option>
                          {loanerFleet.map((l) => (
                            <option key={l.loaner_id} value={l.loaner_id}>{l.year} {l.make} {l.model} ({l.loaner_id})</option>
                          ))}
                        </WorkSelect></WorkField>
                        <WorkField label="Odometer out"><WorkInput type="number" value={checkoutOdometer} onChange={(e) => setCheckoutOdometer(e.target.value)} placeholder="Odometer out…" className={`w-32 rounded-md border px-2 py-1 text-xs ${textClass}`} /></WorkField>
                        <WorkField label="Loaner fuel level"><WorkSelect value={checkoutFuel} onChange={(e) => setCheckoutFuel(e.target.value)} className={`rounded-md border px-2 py-1 text-xs ${textClass}`}>
                          {["Full", "3/4", "1/2", "1/4", "Empty"].map((f) => <option key={f} value={f}>{f}</option>)}
                        </WorkSelect></WorkField>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <WorkField label="Expected return"><WorkInput type="datetime-local" value={checkoutExpectedReturn} onChange={(e) => setCheckoutExpectedReturn(e.target.value)} className={`rounded-md border px-2 py-1 text-xs ${textClass}`} /></WorkField>
                        <WorkButton type="submit" variant="primary"
                          disabled={busy || !checkoutLoanerId || !checkoutOdometer || !data.customer.id}
                          onClick={() =>
                            withTransportationBusy(() =>
                              checkoutLoaner({
                                loanerVehicleId: checkoutLoanerId,
                                customerId: data.customer.id!,
                                odometerOut: parseInt(checkoutOdometer, 10),
                                fuelOut: checkoutFuel,
                                roId,
                                expectedReturnAt: checkoutExpectedReturn ? new Date(checkoutExpectedReturn).toISOString() : undefined,
                                agreementSigned: true,
                              })
                            ).then(() => { setCheckoutLoanerId(""); setCheckoutOdometer(""); setCheckoutExpectedReturn(""); })
                          }
                          className="text-xs px-2.5 py-1 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50"
                        >
                          Check Out Loaner
                        </WorkButton>
                      </div>
                    </div>
                  )}

                  {transportation && transportation.assignment_history.length > 0 && (
                    <div className="mt-3 pt-2 border-t border-white/10 space-y-1 text-xs text-zinc-500">
                      <div className="uppercase tracking-wide text-xs">History</div>
                      {transportation.assignment_history.map((a) => (
                        <div key={a.id}>
                          {a.loaner_vehicle_id} · {fmt(a.checked_out_at)} → {a.checked_in_at ? fmt(a.checked_in_at) : "still out"}{a.miles_driven !== null ? ` · ${a.miles_driven} mi` : ""}
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <div className={cardClass}>
                  <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Shuttle</div>
                  <div className="text-xs space-y-1.5">
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <WorkField label="Shuttle Direction"><WorkSelect value={shuttleDirection} onChange={(e) => setShuttleDirection(e.target.value as ShuttleDirection)} className={`rounded-md border px-2 py-1 text-xs ${textClass}`}>
                        <option value="to_dealership">To Dealership</option>
                        <option value="from_dealership">From Dealership</option>
                      </WorkSelect></WorkField>
                      <WorkField label="Pickup location"><WorkInput value={shuttlePickup} onChange={(e) => setShuttlePickup(e.target.value)} placeholder="Pickup location…" className={`flex-1 rounded-md border px-2 py-1 text-xs ${textClass}`} /></WorkField>
                      <WorkField label="Dropoff location"><WorkInput value={shuttleDropoff} onChange={(e) => setShuttleDropoff(e.target.value)} placeholder="Dropoff location…" className={`flex-1 rounded-md border px-2 py-1 text-xs ${textClass}`} /></WorkField>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <WorkField label="Shuttle Time"><WorkInput type="datetime-local" value={shuttleTime} onChange={(e) => setShuttleTime(e.target.value)} className={`rounded-md border px-2 py-1 text-xs ${textClass}`} /></WorkField>
                      <WorkButton type="submit" variant="primary"
                        disabled={busy || !shuttleTime || !data.customer.id}
                        onClick={() =>
                          withTransportationBusy(() =>
                            requestShuttle({
                              customerId: data.customer.id!,
                              direction: shuttleDirection,
                              pickupLocation: shuttlePickup,
                              dropoffLocation: shuttleDropoff,
                              requestedTime: new Date(shuttleTime).toISOString(),
                              roId,
                            })
                          ).then(() => { setShuttlePickup(""); setShuttleDropoff(""); setShuttleTime(""); })
                        }
                        className="text-xs px-2.5 py-1 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50"
                      >
                        Request Shuttle
                      </WorkButton>
                    </div>
                  </div>

                  {transportation && transportation.shuttle_requests.length > 0 && (
                    <div className="mt-3 pt-2 border-t border-white/10 space-y-2">
                      {transportation.shuttle_requests.map((s) => (
                        <div key={s.id} className="text-xs space-y-1">
                          <div className="flex items-center gap-1.5 flex-wrap">
                            <span className="font-medium">{s.direction === "to_dealership" ? "To dealership" : "From dealership"}</span>
                            <span className="text-zinc-500">{fmt(s.requested_time)}</span>
                            <span className={`px-1.5 py-0.5 rounded font-brand uppercase tracking-wide text-xs ${s.status === "completed" ? "bg-green-700 text-white" : s.status === "cancelled" ? "bg-zinc-600 text-white" : "bg-brand-blue text-white"}`}>{s.status.replace(/_/g, " ")}</span>
                          </div>
                          {s.status !== "completed" && s.status !== "cancelled" && (
                            <div className="flex items-center gap-1.5">
                              <WorkField label="Assign driver"><WorkSelect
                                value={shuttleDriverPick[s.id] ?? s.driver_id ?? ""}
                                onChange={(e) => setShuttleDriverPick((prev) => ({ ...prev, [s.id]: e.target.value }))}
                                className={`rounded-md border px-1.5 py-0.5 text-xs ${textClass}`}
                              >
                                <option value="">Assign driver…</option>
                                {serviceEmployees.map((emp) => <option key={emp.id} value={emp.id}>{emp.name}</option>)}
                              </WorkSelect></WorkField>
                              <WorkButton type="submit"
                                disabled={busy || !shuttleDriverPick[s.id]}
                                onClick={() => withTransportationBusy(() => assignShuttleDriver(s.id, shuttleDriverPick[s.id]))}
                                className="text-xs px-2 py-0.5 rounded bg-zinc-200/10 text-zinc-300 hover:text-white transition disabled:opacity-50"
                              >
                                Assign
                              </WorkButton>
                              {s.status !== "en_route" && (
                                <WorkButton type="submit" disabled={busy} onClick={() => withTransportationBusy(() => updateShuttleStatus(s.id, "en_route"))} className="text-xs px-2 py-0.5 rounded bg-zinc-200/10 text-zinc-300 hover:text-white transition disabled:opacity-50">En Route</WorkButton>
                              )}
                              <WorkButton type="submit" disabled={busy} onClick={() => withTransportationBusy(() => updateShuttleStatus(s.id, "completed"))} className="text-xs px-2 py-0.5 rounded bg-green-700 text-white hover:opacity-90 transition disabled:opacity-50">Complete</WorkButton>
                              <WorkButton type="submit" variant="danger" disabled={busy} onClick={() => withTransportationBusy(() => updateShuttleStatus(s.id, "cancelled" as ShuttleStatus))} className="text-xs px-2 py-0.5 rounded bg-red-700 text-white hover:opacity-90 transition disabled:opacity-50">Cancel</WorkButton>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <div className={cardClass}>
                  <WorkButton type="submit"
                    onClick={() => { setFleetAdminOpen((o) => !o); if (!fleetAdminOpen) refreshFullFleet(); }}
                    className="text-xs font-brand uppercase tracking-wide text-zinc-500 hover:text-zinc-300 transition"
                  >
                    {fleetAdminOpen ? "▾" : "▸"} Manage Loaner Fleet
                  </WorkButton>

                  {fleetAdminOpen && (
                    <div className="mt-2 space-y-3">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <WorkField label="Make"><WorkInput value={newLoanerMake} onChange={(e) => setNewLoanerMake(e.target.value)} placeholder="Make…" className={`w-24 rounded-md border px-2 py-1 text-xs ${textClass}`} /></WorkField>
                        <WorkField label="Model"><WorkInput value={newLoanerModel} onChange={(e) => setNewLoanerModel(e.target.value)} placeholder="Model…" className={`w-24 rounded-md border px-2 py-1 text-xs ${textClass}`} /></WorkField>
                        <WorkField label="Year"><WorkInput value={newLoanerYear} onChange={(e) => setNewLoanerYear(e.target.value)} placeholder="Year…" className={`w-16 rounded-md border px-2 py-1 text-xs ${textClass}`} /></WorkField>
                        <WorkField label="VIN"><WorkInput value={newLoanerVin} onChange={(e) => setNewLoanerVin(e.target.value)} placeholder="VIN…" className={`w-32 rounded-md border px-2 py-1 text-xs ${textClass}`} /></WorkField>
                        <WorkField label="Mileage"><WorkInput type="number" value={newLoanerMileage} onChange={(e) => setNewLoanerMileage(e.target.value)} placeholder="Mileage…" className={`w-24 rounded-md border px-2 py-1 text-xs ${textClass}`} /></WorkField>
                        <WorkButton type="submit" variant="primary"
                          disabled={busy || !newLoanerMake || !newLoanerModel}
                          onClick={() =>
                            withTransportationBusy(() =>
                              addLoanerVehicle(newLoanerMake, newLoanerModel, newLoanerYear, newLoanerVin, parseInt(newLoanerMileage, 10) || 0)
                            ).then(() => { setNewLoanerMake(""); setNewLoanerModel(""); setNewLoanerYear(""); setNewLoanerVin(""); setNewLoanerMileage(""); refreshFullFleet(); })
                          }
                          className="text-xs px-2.5 py-1 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50"
                        >
                          + Add to Fleet
                        </WorkButton>
                      </div>

                      <div className="space-y-1">
                        {fullFleet.map((l) => (
                          <div key={l.loaner_id} className="flex items-center gap-2 text-xs">
                            <span className="flex-1">{l.year} {l.make} {l.model} <span className="text-zinc-500">({l.loaner_id})</span></span>
                            <span className={`px-1.5 py-0.5 rounded font-brand uppercase tracking-wide text-xs ${l.status === "available" ? "bg-green-700 text-white" : l.status === "out" ? "bg-brand-blue text-white" : "bg-zinc-600 text-white"}`}>{l.status.replace(/_/g, " ")}</span>
                            {l.status !== "out" && (
                              <WorkField label="Set status"><WorkSelect
                                value=""
                                onChange={(e) => { if (e.target.value) withTransportationBusy(() => updateLoanerStatus(l.loaner_id, e.target.value as LoanerStatus)).then(refreshFullFleet); }}
                                className={`rounded-md border px-1.5 py-0.5 text-xs ${textClass}`}
                              >
                                <option value="">Set status…</option>
                                {(["available", "maintenance", "out_of_service"] as LoanerStatus[]).filter((s) => s !== l.status).map((s) => (
                                  <option key={s} value={s}>{s.replace(/_/g, " ")}</option>
                                ))}
                              </WorkSelect></WorkField>
                            )}
                          </div>
                        ))}
                        {fullFleet.length === 0 && <div className="text-zinc-600 text-xs">No loaner vehicles in the fleet yet.</div>}
                      </div>
                    </div>
                  )}
                </div>
              </>
            )}

            {tab === "handoff" && (
              <div className={cardClass}>
                <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Service-to-Sales Opportunity Handoff</div>
                {handoffError && <div className="text-red-400 text-xs mb-2">{handoffError}</div>}

                {handoff?.sales_handoff.status === "promoted" && (
                  <div className="text-xs text-green-400">
                    ✅ Promoted to Sales -- Lead {handoff.sales_handoff.promoted_lead_id}, assigned to {handoff.sales_handoff.assigned_to}, on {fmt(handoff.sales_handoff.promoted_at ?? null)}
                  </div>
                )}

                {handoff?.sales_handoff.status === "dismissed" && (
                  <div className="text-xs text-zinc-500">
                    ✕ Dismissed by {handoff.sales_handoff.dismissed_by} on {fmt(handoff.sales_handoff.dismissed_at ?? null)}{handoff.sales_handoff.reason ? ` -- ${handoff.sales_handoff.reason}` : ""}
                  </div>
                )}

                {(!handoff || handoff.sales_handoff.status === "open") && (
                  <div className="text-xs space-y-2">
                    <div className="text-zinc-500">
                      {handoff?.sales_handoff.opportunity_type === "manual" && handoff.sales_handoff.notes
                        ? `Flagged: ${handoff.sales_handoff.notes}`
                        : "Flag this RO if the customer seems like a good trade-in/upsell candidate, or promote it directly if it already qualifies (a declined estimate or an expensive repair)."}
                    </div>

                    <div className="flex items-center gap-1.5 flex-wrap">
                      <WorkField label="Assign handoff to"><WorkSelect value={handoffAssignTo} onChange={(e) => setHandoffAssignTo(e.target.value)} className={`rounded-md border px-2 py-1 text-xs ${textClass}`}>
                        <option value="">Assign to me</option>
                        {salesEmployees.map((emp) => <option key={emp.id} value={emp.id}>{emp.name}</option>)}
                      </WorkSelect></WorkField>
                      <WorkField label="Notes for the Sales rep"><WorkInput value={handoffNotes} onChange={(e) => setHandoffNotes(e.target.value)} placeholder="Notes for the Sales rep…" className={`flex-1 rounded-md border px-2 py-1 text-xs ${textClass}`} /></WorkField>
                      <WorkButton type="submit"
                        disabled={busy}
                        onClick={() => withHandoffBusy(() => promoteToSales(roId, handoff?.sales_handoff.opportunity_type, handoffAssignTo || undefined, handoffNotes)).then(() => { setHandoffNotes(""); refresh(); })}
                        className="text-xs px-2.5 py-1 rounded bg-green-700 text-white font-medium hover:opacity-90 transition disabled:opacity-50"
                      >
                        Promote to Sales
                      </WorkButton>
                    </div>

                    <div className="flex items-center gap-1.5">
                      <WorkField label="Dismiss reason (optional)"><WorkInput value={handoffDismissReason} onChange={(e) => setHandoffDismissReason(e.target.value)} placeholder="Dismiss reason (optional)…" className={`flex-1 rounded-md border px-2 py-1 text-xs ${textClass}`} /></WorkField>
                      <WorkButton type="submit"
                        disabled={busy}
                        onClick={() => withHandoffBusy(() => dismissOpportunity(roId, handoffDismissReason, handoff?.sales_handoff.opportunity_type)).then(() => setHandoffDismissReason(""))}
                        className="text-xs px-2.5 py-1 rounded bg-zinc-200/10 text-zinc-300 hover:text-white transition disabled:opacity-50"
                      >
                        Dismiss
                      </WorkButton>
                    </div>

                    {handoff?.sales_handoff.opportunity_type !== "manual" && (
                      <div className="flex items-center gap-1.5 pt-1 border-t border-white/10">
                        <WorkField label="Flag as an opportunity manually, with a note"><WorkInput value={handoffFlagNotes} onChange={(e) => setHandoffFlagNotes(e.target.value)} placeholder="Flag as an opportunity manually, with a note…" className={`flex-1 rounded-md border px-2 py-1 text-xs ${textClass}`} /></WorkField>
                        <WorkButton type="submit"
                          disabled={busy || !handoffFlagNotes}
                          onClick={() => withHandoffBusy(() => flagManualOpportunity(roId, handoffFlagNotes)).then(() => setHandoffFlagNotes(""))}
                          className="text-xs px-2.5 py-1 rounded bg-zinc-200/10 text-zinc-300 hover:text-white transition disabled:opacity-50"
                        >
                          Flag
                        </WorkButton>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}

            {tab === "timeline" && (
              <>
                <div className={cardClass}>
                  <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Communication Center</div>
                  <div className="flex items-center gap-1.5">
                    <WorkField label="Communication channel"><WorkSelect value={commChannel} onChange={(e) => setCommChannel(e.target.value as CommChannel)} className={`rounded-md border px-2 py-1 text-xs ${textClass}`}>
                      {catalog.comm_channels.map((c) => <option key={c} value={c}>{c}</option>)}
                    </WorkSelect></WorkField>
                    <WorkField label="Log a call/text/email"><WorkInput disabled={busy} value={commBody} onChange={(e) => setCommBody(e.target.value)} placeholder="Log a call/text/email…" className={`flex-1 rounded-md border px-2 py-1 text-xs ${textClass}`} /></WorkField>
                    <WorkButton type="submit" variant="primary" disabled={busy || !commBody.trim()} onClick={() => withBusy(() => logRoCommunication(roId, commChannel, commBody)).then(saved => { if (saved) setCommBody(""); })} className="text-xs px-2.5 py-1 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50">Log</WorkButton>
                  </div>
                </div>

                <div className={cardClass}>
                  <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Timeline — Full Audit Trail</div>
                  <div className="space-y-1.5 max-h-96 overflow-y-auto">
                    {data.timeline.events.length === 0 ? (
                      <div className="text-xs text-zinc-600">No activity recorded yet.</div>
                    ) : (
                      data.timeline.events.map((e, i) => (
                        <div key={i} className="flex items-start gap-2 text-xs border-b border-zinc-800/60 pb-1.5">
                          <div className="flex-1">
                            <div>{e.label}</div>
                            {e.notes && <div className="text-xs text-zinc-500 italic">{e.notes}</div>}
                          </div>
                          <div className="text-xs text-zinc-500 text-right shrink-0">
                            <div>{fmt(e.at)}</div>
                            {e.by && <div>{e.by}</div>}
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              </>
            )}
          </>
        )}
      </div>
    </WorkOverlay>
  );
}

export function RepairOrderWorkspaceBoard({ theme, inline=false, initialTab="overview", onDraftOpenChange, onSavingChange }: { theme: Theme; inline?:boolean; initialTab?:RoWorkspaceTab; onDraftOpenChange?:(v:boolean)=>void; onSavingChange?:(v:boolean)=>void }) {
  const [catalog, setCatalog] = useState<RoCatalog | null>(null);
  const [board, setBoard] = useState<RoBoard>({} as RoBoard);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<string | null>(null);
  const [showNewRo, setShowNewRo] = useState(false);

  function refresh() {
    setLoading(true);
    Promise.all([getRoCatalog(), getRoBoard()])
      .then(([c, b]) => {
        setCatalog(c);
        setBoard(b);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }

  useEffect(refresh, []);

  const liveStages = catalog ? catalog.stages.filter((s) => s !== "Follow-Up") : [];
  const openCount = liveStages.reduce((sum, s) => sum + (board[s]?.length || 0), 0);
  const waitingApproval = board["Customer Approval"]?.length || 0;
  const waitingParts = board["Parts"]?.length || 0;
  const inRepair = board["Repair"]?.length || 0;

  if(inline && showNewRo) return <NewRoModal onDraftOpenChange={onDraftOpenChange} onSavingChange={onSavingChange} inline theme={theme} onClose={()=>setShowNewRo(false)} onCreated={id=>{setShowNewRo(false);refresh();setSelected(id);}}/>;
  if(inline && selected && catalog) return <RoWorkspaceModal initialTab={initialTab} onDraftOpenChange={onDraftOpenChange} onSavingChange={onSavingChange} inline theme={theme} roId={selected} catalog={catalog} onClose={()=>setSelected(null)} onChanged={refresh}/>;

  return (
    <div className={tc(theme, "flex-1 flex flex-col min-h-0 bg-brand-ink text-white", "flex-1 flex flex-col min-h-0 bg-white text-black")}>
      <div className={tc(theme, "grid grid-cols-4 gap-3 p-4 border-b border-zinc-800", "grid grid-cols-4 gap-3 p-4 border-b border-zinc-200")}>
        <Kpi theme={theme} label="Open ROs" value={openCount} color={RIBBON[0]} />
        <Kpi theme={theme} label="Waiting Approval" value={waitingApproval} color={RIBBON[1]} />
        <Kpi theme={theme} label="Waiting Parts" value={waitingParts} color={RIBBON[2]} />
        <Kpi theme={theme} label="In Repair" value={inRepair} color={RIBBON[3]} />
      </div>

      <div className={tc(theme, "flex items-center justify-between px-4 py-3 border-b border-zinc-800", "flex items-center justify-between px-4 py-3 border-b border-zinc-200")}>
        <div className="text-xs font-brand uppercase tracking-wide text-zinc-500">RO Workflow — Check-In through Follow-Up</div>
        <WorkButton type="submit" variant="primary" onClick={() => setShowNewRo(true)} className="text-xs px-3 py-1.5 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition">+ Check In New RO</WorkButton>
      </div>

      <div className="flex-1 overflow-x-auto overflow-y-hidden p-4">
        {loading || !catalog ? (
          <div className="text-sm text-zinc-500">Loading…</div>
        ) : (
          <div className="flex gap-3 h-full min-w-max">
            {catalog.stages.map((stage, i) => {
              const ros = board[stage] || [];
              return (
                <div key={stage} className={tc(theme, "w-52 shrink-0 rounded-lg border border-zinc-800 bg-brand-charcoal flex flex-col", "w-52 shrink-0 rounded-lg border border-zinc-200 bg-zinc-50 flex flex-col")}>
                  <div className="px-2.5 py-2 border-b border-zinc-800 flex items-center justify-between">
                    <span className="text-xs font-brand uppercase tracking-wide">{stage}</span>
                    <span className="text-xs px-1.5 py-0.5 rounded" style={{ background: RIBBON[i % 4], color: "#000" }}>{ros.length}</span>
                  </div>
                  <div className="flex-1 overflow-y-auto p-1.5 space-y-1.5">
                    {ros.map((r) => (
                      <button
                        key={r.id}
                        onClick={() => setSelected(r.id)}
                        className={tc(theme, "w-full text-left rounded border border-zinc-800 bg-black/20 p-1.5 hover:border-brand-blue transition", "w-full text-left rounded border border-zinc-300 bg-white p-1.5 hover:border-brand-blue transition")}
                      >
                        <div className="text-xs font-medium truncate">{r.service_number}</div>
                        <div className="text-xs text-zinc-500 truncate">{r.description}</div>
                      </button>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {showNewRo && (
        <NewRoModal
          theme={theme}
          onClose={() => setShowNewRo(false)}
          onCreated={(roId) => { setShowNewRo(false); refresh(); setSelected(roId); }}
        />
      )}

      {selected && catalog && (
        <RoWorkspaceModal
          theme={theme}
          roId={selected}
          catalog={catalog}
          onClose={() => setSelected(null)}
          onChanged={refresh}
        />
      )}
    </div>
  );
}
