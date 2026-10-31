"use client";
import {FinanceWorkflowPanel} from "./FinanceWorkflowPanel";
import {SupportWorkflowPanel} from "./SupportWorkflowPanel";
import {InventoryWorkflowPanel} from "./InventoryWorkflowPanel";
import {ServiceWorkflowPanel} from "./ServiceWorkflowPanel";
import {MarketingWorkflowPanel} from "./MarketingWorkflowPanel";
import { WorkButton, WorkInput, WorkTextarea, WorkSection, WorkEmpty } from "./WorkspaceUi";
import {RecordCollection} from "./RecordCollection";
import {RecordTable} from "./RecordTable";

import { PRODUCT_ACCENT_COLORS } from "@/lib/productTheme";
import { useEffect, useState } from "react";
import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";
import { JsonValue } from "@/components/MenuDashPanel";
import { EntityHoverLink, VinHoverLink } from "@/components/EntityHoverLink";
import { UpSystemBoard, type UpSystemSection } from "@/components/UpSystemBoard";
import { BdcBoard, type BdcSection } from "@/components/BdcBoard";
import { DemoDriveBoard, type DemoDriveSection } from "@/components/DemoDriveBoard";
import { CreditAppBoard, type CreditAppSection } from "@/components/CreditAppBoard";
import { ESignatureBoard, type ESignatureSection } from "@/components/ESignatureBoard";
import { FIProductsBoard, type FIProductsSection } from "@/components/FIProductsBoard";
import { LostSaleRecoveryBoard, type LostSaleRecoverySection } from "@/components/LostSaleRecoveryBoard";
import { OrphanOwnerMiningBoard, type OrphanOwnerMiningSection } from "@/components/OrphanOwnerMiningBoard";
import { LeadCadenceBoard, type LeadCadenceSection } from "@/components/LeadCadenceBoard";
import { DealWorkflowPanel, type DealPanelSection } from "@/components/DealWorkflowPanel";
import { OperationsWorkflowPanel, type OperationsWorkflowSection } from "@/components/OperationsWorkflowPanel";
import type { MenuDash } from "@/lib/useMenuDash";

// Department workflows share a full-width workspace, section navigation and record lists.
// The server catalog controls which daily-work destinations each employee can access.

type CoreFunctionality = {
  title: string;
  description: string;
};

export type WorkflowDef = {
  key: string;
  title: string;
  entity_type: string | null;
  entity_label: string;
  description: string;
  why_it_matters: string;
  stages: string[];
  tabs?: string[];
  core_functionality?: CoreFunctionality[];
};

export type Catalog = Record<string, WorkflowDef[]>;

// Session 57, "wire it all up" -- shape of GET /workflows/tab-data's response
// (core/workflow_tab_data.py). `linked_entity`/`related_entities` reuse core/ai_tools.py's
// already-role-filtered entity lookup; `sources` are workflow-specific real data pulled
// from whatever existing dashboard/compliance/network/readiness/connections function is a
// genuine match for that workflow (see that module's REAL_SOURCES map) -- absent entirely
// for workflows nothing in the graph backs yet.
type SerializedEntity = { id: string; entity_type: string; attributes: Record<string, unknown> };

type TabDataSource = { id: string; label: string; data: unknown };

type TabData = {
  workflow_key: string;
  linked_entity: SerializedEntity | { error: string } | null;
  related_entities: { relationship_type: string; entity: SerializedEntity }[] | null;
  sources: TabDataSource[];
  error?: string;
};

type WorkflowInstance = {
  id: string;
  workflow_key: string;
  department: string;
  title: string;
  stages: string[];
  current_stage_index: number;
  status: "in_progress" | "completed" | "cancelled";
  linked_entity_id: string | null;
  linked_entity_raw: string | null;
  started_by: string;
  started_at: string;
  updated_at: string;
  completed_at: string | null;
  history: { stage: string; action: string; by: string; at: string; notes: string | null }[];
};

// Corporate-bar palette (session 54) -- the exact 4 colors/order the now-deleted
// DepartmentDashboard.tsx used one-per-button ("Sales & Deal Desk" blue, "Service &
// Parts" teal, "Marketing & Web" yellow, "Finance & Executive" red). Sam: "change the
// new buttons to have the same dots as the deleted ones (multi / corporate ribbon
// themed instead of all one color)" -- so each department's 4 workflow buttons cycle
// through these 4 colors by position rather than all sharing one color per
// department (the old DEPARTMENT_COLORS approach this replaces).
export const RIBBON_COLORS = PRODUCT_ACCENT_COLORS;

let cachedCatalog: Catalog | null = null;

export async function fetchCatalog(): Promise<Catalog> {
  if (cachedCatalog) return cachedCatalog;

  const response = await fetch(`${API_BASE}/workflows/catalog`, {
    headers: { ...authHeaders() },
  });

  if (!response.ok) throw new Error("Unable to load department workflows.");
  const data = await response.json();
  cachedCatalog = data as Catalog;
  return cachedCatalog;
}

// Start, track and advance work using the same controls as department pages.
function OverviewTab({
  workflow,
  color,
  instances,
  loading,
  error,
  starting,
  linkedEntityId,
  notes,
  showStartForm,
  onLinkedEntityIdChange,
  onNotesChange,
  onToggleStartForm,
  onStart,
  onAdvance,
}: {
  workflow: WorkflowDef;
  color: string;
  instances: WorkflowInstance[];
  loading: boolean;
  error: string | null;
  starting: boolean;
  linkedEntityId: string;
  notes: string;
  showStartForm: boolean;
  onLinkedEntityIdChange: (v: string) => void;
  onNotesChange: (v: string) => void;
  onToggleStartForm: () => void;
  onStart: () => void;
  onAdvance: (instanceId: string) => void;
}) {
  return <div className="workflow-overview">
    <p>{workflow.description}</p>
    <ol className="workflow-stage-list" aria-label="Workflow stages">{workflow.stages.map(stage=><li key={stage}>{stage}</li>)}</ol>
    {error && <p role="alert">{error}</p>}
    <WorkSection title="In progress" description="Track a work item here. Use the sections above to perform and save the work; changing a tracking step does not execute a business action." actions={<WorkButton variant="primary" onClick={onToggleStartForm}>{showStartForm ? "Close start form" : "Start new"}</WorkButton>}>
      {showStartForm && <form className="workflow-start-form" onSubmit={event=>{event.preventDefault();onStart();}}>
        <label>{workflow.entity_label}<WorkInput value={linkedEntityId} onChange={e=>onLinkedEntityIdChange(e.target.value)}/></label>
        <label>Notes (optional)<WorkTextarea value={notes} onChange={e=>onNotesChange(e.target.value)} rows={3}/></label>
        <div className="work-actions"><WorkButton variant="primary" type="submit" disabled={starting}>{starting ? "Starting..." : `Start ${workflow.title}`}</WorkButton></div>
      </form>}
      {loading ? <p role="status">Loading work...</p> : instances.length === 0 ? <WorkEmpty title="No work in progress" description="Start a workflow to track a record through its next steps."/> :
        <RecordTable label="Work in progress"><thead><tr><th>Record</th><th>Current step</th><th>Progress</th><th>Next action</th></tr></thead><tbody>{instances.map(instance=><tr key={instance.id}>
          <td>{instance.linked_entity_raw || instance.linked_entity_id || instance.id}</td><td>{instance.stages[instance.current_stage_index]}</td><td>{instance.current_stage_index+1} of {instance.stages.length}</td>
          <td><WorkButton onClick={()=>onAdvance(instance.id)}>{instance.current_stage_index+1 >= instance.stages.length ? "Mark complete" : `Continue to ${instance.stages[instance.current_stage_index+1]}`}</WorkButton></td>
        </tr>)}</tbody></RecordTable>}
    </WorkSection>
  </div>;
}

// A doc-sourced tab ([Tab N] from Sam's attached modal-navigation spec) that isn't the
// Overview tab. Honest placeholder -- this workspace zone doesn't have real data or
// backend logic behind it yet, but the navigation itself is real, sourced directly
// from core/workflow_catalog.py's `tabs` field.
function PlaceholderTab({
  tabTitle,
  workflowTitle,
  color,
}: {
  tabTitle: string;
  workflowTitle: string;
  color: string;
}) {
  return <WorkEmpty title={`${tabTitle} is not available yet`} description={`Use Overview to start and track ${workflowTitle.toLowerCase()}. This step does not yet support record updates.`}/>;
}

// Session 57, "wire it all up" -- generic renderers for whatever shape
// GET /workflows/tab-data's sources come back in. Deliberately generic (one renderer,
// not one component per source) since the sources span dashboards, lists, and
// nested objects with no single common schema.
function ValuePreview({ value }: { value: unknown }) {
  if (value === null || value === undefined || value === "") {
    return <span className="text-zinc-600">—</span>;
  }
  if (typeof value === "object") {
    const isArray = Array.isArray(value);
    return (
      <details>
        <summary className="cursor-pointer text-zinc-400">
          {isArray ? `[${(value as unknown[]).length}]` : "{…}"}
        </summary>
        <pre className="mt-1 p-2 rounded bg-zinc-950 border border-zinc-800 text-xs overflow-x-auto max-w-md whitespace-pre-wrap">
          {JSON.stringify(value, null, 2)}
        </pre>
      </details>
    );
  }
  // Session 76 fourth/fifth follow-up -- same entity-ID-as-link treatment
  // components/MenuDashPanel.tsx's JsonValue applies, kept in sync deliberately since
  // this file's ObjectTable/ListTable are the OTHER real renderer for workflow-window
  // Core Functionality data (JsonValue itself is reused directly for SourceBlock/
  // linked-entity data below, but ValuePreview is this file's own separate one).
  // components/EntityHoverLink.tsx owns the hover-preview-card + pop-out/push-to-Dash
  // behavior (fifth follow-up: "pop up in a modal when you hover... pop it out into a
  // new window or push into the dash / sub menu area").
  const text = String(value);
  const match = /\b([A-Z]{2,10}-\d{4,6})\b/.exec(text);

  if (match && match[0] === text) {
    return <EntityHoverLink id={text} />;
  }

  // Session 76 sixth follow-up: "i can't click on a vin number thats attached to a
  // car to start a process, or to pull up that cars information." A plain 17-char VIN
  // (core/vin_decoder.py's real ISO 3779 format -- alphanumeric, no I/O/Q) isn't a
  // NXTDeal id itself, so it can't hit GET /entity/{id} directly -- VinHoverLink
  // resolves it to the real Vehicle first, then hands off to EntityHoverLink.
  if (/^[A-HJ-NPR-Z0-9]{17}$/.test(text)) {
    return <VinHoverLink vin={text} />;
  }

  return <span>{text}</span>;
}

function ObjectTable({ obj }: { obj: Record<string, unknown> }) {
  const entries = Object.entries(obj ?? {});
  if (entries.length === 0) return <div className="text-xs text-zinc-600">No data.</div>;
  return (
    <table className="w-full text-xs">
      <tbody>
        {entries.map(([k, v]) => (
          <tr key={k} className="border-b border-zinc-900 last:border-0">
            <td className="py-1 pr-3 text-zinc-500 align-top whitespace-nowrap">{k}</td>
            <td className="py-1 text-zinc-200 align-top">
              <ValuePreview value={v} />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

const PREFERRED_LIST_COLUMNS = [
  "id", "department", "title", "name", "status", "key", "entity_type",
  "confidence_pct", "label", "ready", "employee_id", "role",
];

// Full result sets use the same paging contract as department work lists.
function ListTable({items}:{items:unknown[]}) {
 if(!items.length)return <p>Nothing here right now.</p>;
 if(!items.every(item=>item&&typeof item==="object"&&!Array.isArray(item)))return <ul><RecordCollection list>{items.map((item,i)=><li key={i}>{typeof item==="object"?JSON.stringify(item):String(item)}</li>)}</RecordCollection></ul>;
 const rows=items as Record<string,unknown>[];
 const keys=new Set(rows.flatMap(row=>Object.keys(row)));
 const preferred=PREFERRED_LIST_COLUMNS.filter(key=>keys.has(key)).slice(0,5);
 const columns=preferred.length?preferred:Array.from(keys).slice(0,5);
 return <RecordTable><thead><tr>{columns.map(key=><th key={key}>{key.replaceAll("_"," ")}</th>)}</tr></thead><tbody>{rows.map((row,i)=><tr key={i}>{columns.map(key=><td key={key}><ValuePreview value={row[key]}/></td>)}</tr>)}</tbody></RecordTable>;
}

function SourceBlock({ source }: { source: TabDataSource }) {
  const data = source.data as Record<string, unknown> | unknown[] | null;
  const isErrorObj =
    data && typeof data === "object" && !Array.isArray(data) && "error" in (data as Record<string, unknown>);

  return (
    <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800 mb-2">
      <div className="flex items-center gap-2 mb-2">
        <span className="text-xs font-medium text-zinc-200">{source.label}</span>
        {!isErrorObj && (
          <span className="text-xs px-1.5 py-0.5 rounded border border-emerald-800 text-emerald-500">
            live
          </span>
        )}
      </div>
      {isErrorObj ? (
        <div className="text-xs text-zinc-600">
          {String((data as Record<string, unknown>).error)}
        </div>
      ) : (
        // JsonValue (shared with MenuDashPanel.tsx) handles object/array/entity
        // rendering uniformly here -- includes the Visualize chart toggle on any
        // array of objects with a numeric column, and inline entity editing if this
        // source's data happens to be entity-shaped.
        <JsonValue value={data} theme="dark" />
      )}
    </div>
  );
}

// Shared across every tab in a WorkflowWindow (not just Overview) -- real graph data is
// relevant no matter which named sub-tab is selected. Renders nothing if there's neither
// a linked entity nor any REAL_SOURCES for this workflow, so workflows with no real data
// behind them yet don't show an empty "Live Data" heading.
function LiveDataPanel({
  workflowKey,
  linkedEntityId,
  color,
}: {
  workflowKey: string;
  linkedEntityId: string | null;
  color: string;
}) {
  const [data, setData] = useState<TabData | null>(null);
  const [loading, setLoading] = useState(true);
  // Collapsed by default (session's own "front and center" fix): Sam -- "the live
  // data is above the actual part where you can enter new things in, start
  // processes... we either need to have the live data fanned up into a thin box, or
  // below where to start the workflow." This component now renders below the Start
  // action (see WorkflowWindowBody's render order below) AND starts as a thin,
  // one-line collapsed strip rather than a fully-expanded block, so both of Sam's two
  // suggested fixes are applied at once.
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);

    const params = new URLSearchParams({ workflow_key: workflowKey });
    if (linkedEntityId) params.set("linked_entity_id", linkedEntityId);

    fetch(`${API_BASE}/workflows/tab-data?${params.toString()}`, {
      headers: { ...authHeaders() },
    })
      .then((r) => r.json())
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch(() => {
        if (!cancelled) setData(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [workflowKey, linkedEntityId]);

  if (loading) return <div className="text-xs text-zinc-600 mb-3">Loading live data…</div>;
  if (!data || data.error) return null;

  const linkedEntity =
    data.linked_entity && !("error" in data.linked_entity) ? data.linked_entity : null;
  const hasSources = data.sources && data.sources.length > 0;

  if (!linkedEntity && !hasSources) return null;

  const sourceCount = data.sources?.length ?? 0;

  return (
    <div className="mb-5">
      <WorkButton type="submit"
        onClick={() => setExpanded((e) => !e)}
        className="w-full flex items-center gap-2 mb-2 text-left"
      >
        <span className="text-zinc-500 text-xs">{expanded ? "▾" : "▸"}</span>
        <span className="text-xs uppercase tracking-wide" style={{ color }}>Live Data</span>
        <span className="text-xs px-1.5 py-0.5 rounded border border-emerald-800 text-emerald-500">
          Supporting records
        </span>
        {!expanded && (
          <span className="text-xs text-zinc-600">
            {linkedEntity ? "1 linked record" : ""}
            {linkedEntity && sourceCount > 0 ? " + " : ""}
            {sourceCount > 0 ? `${sourceCount} source${sourceCount === 1 ? "" : "s"}` : ""}
            {" — click to expand"}
          </span>
        )}
      </WorkButton>

      {expanded && (
        <>
          {linkedEntity && (
            <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800 mb-2">
              {/* JsonValue detects the {id, entity_type, attributes} shape and renders
                  its own edit-capable card -- see MenuDashPanel.tsx's EntityEditCard --
                  so this linked entity is inline-editable here for free. */}
              <JsonValue value={linkedEntity} theme="dark" />
              {data.related_entities && data.related_entities.length > 0 && (
                <div className="mt-2 pt-2 border-t border-zinc-800">
                  <div className="text-xs text-zinc-500 mb-1">Related (one hop on the graph):</div>
                  <ul className="text-xs text-zinc-300 space-y-0.5">
                    {data.related_entities.map((r, i) => (
                      <li key={i}>
                        <span className="text-zinc-500">{r.relationship_type}</span> → {r.entity.entity_type}{" "}
                        {r.entity.id}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          {data.sources.map((s) => (
            <SourceBlock key={s.id} source={s} />
          ))}
        </>
      )}
    </div>
  );
}

// Session 102 follow-up (Sam: "it doesn't look like the tabs are working... it needs
// to be a working process, not just a list") -- maps a workflow's real `tabs` (from
// core/workflow_catalog.py) onto the specific `section` each bespoke board component
// should render for that tab, so every named tab shows genuinely different content
// instead of the same board repeated on all 5. Every workflow key not listed here
// still falls back to PlaceholderTab, unchanged -- this only covers the 7 Sales
// workflows that now have a real bespoke component behind them.
const TAB_TO_SECTION: Record<string, Record<string, string>> = {
  "sales.up_system": {
    "Floor Rotation": "rotation",
    "Log an Up": "log",
    "Working Ups": "working",
    "Be-Back Board": "beback",
    "Outcome Tracking": "outcomes",
  },
  "sales.bdc": {
    "Untouched Queue": "queue",
    "Response-Time Scorecard": "scorecard",
    "First Contact": "first_contact",
    "Qualification": "qualification",
    "Handoff to Floor": "handoff",
  },
  "sales.demo_drive": {
    "Keys-Out Board": "board",
    "Log a Drive": "log",
    "License Verification": "license",
    "Return & Odometer": "return",
    "Interest & Follow-Up": "interest",
  },
  "sales.lead_cadence": {
    "Lead Assignment": "assignment",
    "Communication Timeline": "timeline",
    "Needs Analysis": "needs_analysis",
    "Appointment Scheduling": "appointments",
    "Opportunity Creation": "opportunity",
  },
  "sales.desking": {
    "Customer Financial Profile": "financial_profile",
    "Trade Appraisal": "trade_appraisal",
    "Deal Structuring": "structuring",
    "Payment Presentation": "presentation",
    "Management Approval": "approval",
  },
  "sales.fi_turnover": {
    "Deal Packaging": "packaging",
    "Customer Transfer": "transfer",
    "Product Presentation": "product_presentation",
    "Lender Submission": "lender_submission",
    "Contract Readiness": "contract_readiness",
  },
  "sales.delivery": {
    "Vehicle Preparation": "vehicle_prep",
    "Delivery Quality Control": "quality_control",
    "Technology Setup": "tech_setup",
    "Delivery Documentation": "documentation",
    "CSI & Review Trigger": "csi",
  },
  "sales.credit_app": {
    "Application Queue": "queue",
    "Applicant Information": "applicant",
    "Consent & Submit": "consent",
    "Decision Results": "decision",
    "Application History": "history",
  },
  "sales.esignature": {
    "Envelope Queue": "queue",
    "Signer Setup": "signers",
    "Send for Signature": "send",
    "Sign & Consent": "sign",
    "Completed Envelopes": "history",
  },
  "sales.fi_products": {
    "Product Menu": "menu",
    "Customer Selections": "selections",
    "Deal F&I Summary": "summary",
    "Product Penetration": "penetration",
    "Compliance & Disclosures": "compliance",
  },
  "sales.lost_sale_recovery": {
    "Recovery Queue": "queue",
    "Lost Reason Capture": "reason_capture",
    "Outreach Log": "outreach",
    "Reactivation": "reactivation",
    "Win-Back Lists & Stats": "winback",
  },
  "sales.orphan_owner_mining": {
    "Orphan Queue": "queue",
    "Customer Detail": "detail",
    "Claim & Assign": "claim",
    "Claimed Owners": "claimed",
    "Mining Stats": "stats",
  },
  "operations.recon": {
    "Stock Assignment & Source": "stock_source",
    "Inspection & Condition Report": "inspection",
    "Repair & Recon Management": "repair_recon",
    "Media & Merchandising": "media_merchandising",
    "Frontline Readiness": "frontline_readiness",
  },
  "operations.deal_jacket_audit": {
    "Customer Verification": "customer_verification",
    "Contract Audit": "contract_audit",
    "Lender Requirements": "lender_requirements",
    "Registration & Insurance": "registration_insurance",
    "Compliance Approval": "compliance_approval",
  },
  "operations.inventory_reconciliation": {
    "Floorplan Ledger": "floorplan_ledger",
    "Physical Lot Audit": "lot_audit",
    "Aging Analysis": "aging_analysis",
    "Pricing Adjustments": "pricing_adjustments",
    "Reconciliation Review": "reconciliation_review",
  },
  "operations.interdept_sla": {
    "Request Intake": "request_intake",
    "Parts Allocation": "parts_allocation",
    "Service Scheduling": "service_scheduling",
    "Financial Routing": "financial_routing",
    "Completion Verification": "completion_verification",
  },
};

const OPERATIONS_WORKFLOW_KEYS = new Set([
  "operations.recon", "operations.deal_jacket_audit", "operations.inventory_reconciliation", "operations.interdept_sla",
]);

const DEAL_WORKFLOW_KEYS = new Set(["sales.desking", "sales.fi_turnover", "sales.delivery"]);

function NamedTabContent({
  workflowKey,
  tab,
  linkedEntityId,
  workflowTitle,
  color, theme, onDraftOpenChange, onSavingChange,
}: {
  theme:"light"|"dark";onDraftOpenChange:(v:boolean)=>void;onSavingChange:(v:boolean)=>void;
  workflowKey: string;
  tab: string;
  linkedEntityId: string | null;
  workflowTitle: string;
  color: string;
}) {
  if(workflowKey.startsWith("marketing."))return <MarketingWorkflowPanel workflowKey={workflowKey} tab={tab} theme={theme} onDraftOpenChange={onDraftOpenChange} onSavingChange={onSavingChange}/>;
  if(workflowKey.startsWith("inventory."))return <InventoryWorkflowPanel workflowKey={workflowKey} tab={tab} theme={theme} onDraftOpenChange={onDraftOpenChange} onSavingChange={onSavingChange}/>;
  if(workflowKey.startsWith("service."))return <ServiceWorkflowPanel workflowKey={workflowKey} tab={tab} theme={theme} onDraftOpenChange={onDraftOpenChange} onSavingChange={onSavingChange}/>;
  if(workflowKey.startsWith("finance."))return <FinanceWorkflowPanel workflowKey={workflowKey} tab={tab} theme={theme} onDraftOpenChange={onDraftOpenChange} onSavingChange={onSavingChange}/>;
  if(workflowKey.startsWith("administration.")||workflowKey.startsWith("readiness."))return <SupportWorkflowPanel workflowKey={workflowKey} tab={tab} theme={theme} onDraftOpenChange={onDraftOpenChange} onSavingChange={onSavingChange}/>;
  const section = TAB_TO_SECTION[workflowKey]?.[tab];

  if (!section) {
    return <PlaceholderTab tabTitle={tab} workflowTitle={workflowTitle} color={color} />;
  }

  if (workflowKey === "sales.up_system") return <UpSystemBoard section={section as UpSystemSection} />;
  if (workflowKey === "sales.bdc") return <BdcBoard section={section as BdcSection} />;
  if (workflowKey === "sales.demo_drive") return <DemoDriveBoard section={section as DemoDriveSection} />;
  if (workflowKey === "sales.credit_app") return <CreditAppBoard section={section as CreditAppSection} />;
  if (workflowKey === "sales.esignature") return <ESignatureBoard section={section as ESignatureSection} />;
  if (workflowKey === "sales.fi_products") return <FIProductsBoard section={section as FIProductsSection} />;
  if (workflowKey === "sales.lost_sale_recovery") return <LostSaleRecoveryBoard section={section as LostSaleRecoverySection} />;
  if (workflowKey === "sales.orphan_owner_mining") return <OrphanOwnerMiningBoard section={section as OrphanOwnerMiningSection} />;
  if (workflowKey === "sales.lead_cadence") return <LeadCadenceBoard leadId={linkedEntityId} section={section as LeadCadenceSection} />;
  if (DEAL_WORKFLOW_KEYS.has(workflowKey)) return <DealWorkflowPanel dealId={linkedEntityId} section={section as DealPanelSection} />;
  if (OPERATIONS_WORKFLOW_KEYS.has(workflowKey)) return <OperationsWorkflowPanel workflowKey={workflowKey} entityId={linkedEntityId} section={section as OperationsWorkflowSection} />;

  return <PlaceholderTab tabTitle={tab} workflowTitle={workflowTitle} color={color} />;
}

// Session 56's central-content + toolbar body, extracted (session 57) into its own
// exported component so both the in-page floating WorkflowWindow and the pop-out
// window (frontend/app/panel/workflow/page.tsx) can render the exact same real
// functionality -- no drag/resize chrome of its own, that stays in whichever shell
// mounts it.
export function WorkflowWindowBody({
  workflow,
  color,
  onRequestClose, theme="dark", onDraftOpenChange, onSavingChange,
}: {
  theme?:"light"|"dark";onDraftOpenChange?:(v:boolean)=>void;onSavingChange?:(v:boolean)=>void;
  workflow: WorkflowDef;
  color: string;
  onRequestClose?: () => void;
}) {
  const [selectedTab, setSelectedTab] = useState("Overview");
  const [discardVersion,setDiscardVersion]=useState(0);
  const [childDirty,setChildDirty]=useState(false),[childSaving,setChildSaving]=useState(false),[pendingTab,setPendingTab]=useState<string|null>(null);
  useEffect(()=>{onDraftOpenChange?.(childDirty);return()=>onDraftOpenChange?.(false)},[childDirty,onDraftOpenChange]);
  useEffect(()=>{onSavingChange?.(childSaving);return()=>onSavingChange?.(false)},[childSaving,onSavingChange]);
  function selectTab(tab:string){if(tab===selectedTab)return;if(childDirty||childSaving){setPendingTab(tab);return;}setPendingTab(null);setSelectedTab(tab);}

  const tabs = ["Overview", ...(workflow.tabs ?? [])];

  // Keep form state while switching workflow sections.
  const [instances, setInstances] = useState<WorkflowInstance[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [linkedEntityId, setLinkedEntityId] = useState("");
  const [notes, setNotes] = useState("");
  const [showStartForm, setShowStartForm] = useState(false);

  async function loadInstances() {
    setLoading(true);
    try {
      const response = await fetch(
        `${API_BASE}/workflows?workflow_key=${encodeURIComponent(workflow.key)}&status=in_progress`,
        { headers: { ...authHeaders() } }
      );
      const data = await response.json();
      if (!response.ok || data.error) { setError(data.error ?? "Unable to load work in progress."); return; }
      setInstances(data.instances ?? []);
    } catch {
      setError("Unable to reach NXTDeal backend.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadInstances();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workflow.key]);

  async function handleStart() {
    setStarting(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/workflows/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({
          workflow_key: workflow.key,
          linked_entity_id: linkedEntityId || null,
          notes: notes || null,
        }),
      });
      const data = await response.json();
      if (!response.ok || data.error) {
        setError(data.error ?? "Something went wrong.");
        return;
      }
      setLinkedEntityId("");
      setNotes("");
      setShowStartForm(false);
      await loadInstances();
    } catch {
      setError("Unable to reach NXTDeal backend.");
    } finally {
      setStarting(false);
    }
  }

  async function handleAdvance(instanceId: string) {
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/workflows/${instanceId}/advance`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({}),
      });
      const data = await response.json();
      if (!response.ok || data.error) {
        setError(data.error ?? "Something went wrong.");
        return;
      }
      await loadInstances();
    } catch {
      setError("Unable to reach NXTDeal backend.");
    }
  }

  // Best-effort context for LiveDataPanel: whichever in-progress instance is most
  // recent, falling back to whatever the (not-yet-submitted) start form currently has
  // typed in it -- so department-agnostic workflows still show real data once a real
  // linked entity is in view, without requiring a separate "focus an instance" UI.
  const focusedLinkedEntityId = instances[0]?.linked_entity_id ?? (linkedEntityId || null);

  return <div className="workflow-workspace" data-department-work="">
    <nav className="workflow-section-navigation" aria-label={`${workflow.title} sections`}>{tabs.map(tab=><WorkButton key={tab} aria-current={selectedTab===tab ? "page" : undefined} onClick={()=>selectTab(tab)}>{tab}</WorkButton>)}</nav>
    {pendingTab&&<section role="alert"><p>{childSaving?"Wait for the save to finish.":"You have unsaved workflow changes."}</p><WorkButton onClick={()=>setPendingTab(null)}>Keep editing</WorkButton><WorkButton disabled={childSaving} onClick={()=>{setChildDirty(false);setDiscardVersion(v=>v+1);setSelectedTab(pendingTab);setPendingTab(null);}}>Discard and continue</WorkButton></section>}
    <div className="workflow-section-content">
      {selectedTab === "Overview" ? <>
        <OverviewTab workflow={workflow} color={color} instances={instances} loading={loading} error={error} starting={starting} linkedEntityId={linkedEntityId} notes={notes} showStartForm={showStartForm} onLinkedEntityIdChange={setLinkedEntityId} onNotesChange={setNotes} onToggleStartForm={()=>setShowStartForm(v=>!v)} onStart={handleStart} onAdvance={handleAdvance}/>
        <LiveDataPanel workflowKey={workflow.key} linkedEntityId={focusedLinkedEntityId} color={color}/>
      </> : <NamedTabContent key={discardVersion} theme={theme} onDraftOpenChange={setChildDirty} onSavingChange={setChildSaving} workflowKey={workflow.key} tab={selectedTab} linkedEntityId={focusedLinkedEntityId} workflowTitle={workflow.title} color={color}/>}
    </div>
  </div>;
}

// Fixed neutral accent for the docked Dash panel (session 72) -- replaces the old
// floating window's per-workflow RIBBON_COLORS border/header tint. Sam: "lets use the
// same grey ui as the others instead of them each being uniquely colored" -- "the
// others" being components/MenuDashPanel.tsx's charcoal Top Menu Dash, which uses this
// same brand-teal accent stripe regardless of which item is open. The 4 launcher
// buttons below keep their RIBBON_COLORS flags (a separate, already-shipped ask) --
// only the opened window's own chrome changes here.
export const DASH_ACCENT = "#3FBCC4";

// The grey/charcoal docked Dash panel (session 72) -- replaces the old floating,
// draggable/resizable WorkflowWindow. Sam: "instead of poping out as separate windows,
// can we treat them the same as we do with the sub menu and collapse the workspace and
// fill that entire space? same as the others, where you can pop it out if you want but
// it stays static." Same chrome shape as components/MenuDashPanel.tsx's
// MenuDashPanel -- a charcoal header with a teal left stripe, pop-out (⇱) and close
// (×) -- so a job-workflow Dash and a Top Menu Dash are visually indistinguishable
// except for their content, exactly the "same grey ui" Sam asked for.
export function WorkflowDashPanel({
  department,
  workflowKey,
  onClose,
  onPopOut,
}: {
  department: string;
  workflowKey: string;
  onClose: () => void;
  onPopOut: () => void;
}) {
  const [catalog, setCatalog] = useState<Catalog | null>(null);

  useEffect(() => {
    fetchCatalog().then(setCatalog);
  }, []);

  const workflow = catalog?.[department]?.find((w) => w.key === workflowKey);

  return (
    <div className="flex-1 min-w-0 flex flex-col bg-brand-ink border-x border-zinc-800">
      <div className="relative flex items-center justify-between pl-5 pr-4 py-3 border-b border-zinc-800 shrink-0 bg-brand-charcoal overflow-hidden">
        <span className="absolute left-0 top-0 bottom-0 w-1.5 bg-brand-teal" />
        <div className="flex items-center gap-2 min-w-0">
          <span className="font-brand font-bold uppercase tracking-wide truncate">{department}</span>
          <span className="text-xs text-zinc-500 shrink-0 font-brand uppercase tracking-wider">
            — {workflow ? workflow.title : "Workflow"}
          </span>
        </div>
        <div className="flex items-center gap-3 shrink-0 ml-3">
          <WorkButton type="submit"
            onClick={onPopOut}
            title="Pop out to its own window -- drag it to a second monitor"
            className="text-zinc-400 hover:text-white transition text-sm leading-none"
          >
            ⇱
          </WorkButton>
          <WorkButton type="submit" onClick={onClose} className="text-zinc-400 hover:text-white transition text-lg leading-none">
            ×
          </WorkButton>
        </div>
      </div>

      {!catalog ? (
        <div className="flex-1 flex items-center justify-center text-sm text-zinc-600">Loading…</div>
      ) : workflow ? (
        <WorkflowWindowBody workflow={workflow} color={DASH_ACCENT} onRequestClose={onClose} />
      ) : (
        <div className="flex-1 flex items-center justify-center text-sm text-zinc-600">Workflow not found.</div>
      )}
    </div>
  );
}

export function DepartmentWorkflowButtons({
  department,
  menuDash,
}: {
  department: string;
  menuDash: MenuDash;
}) {
  const [catalog, setCatalog] = useState<Catalog | null>(null);

  useEffect(() => {
    fetchCatalog().then(setCatalog);
  }, []);

  const workflows = catalog?.[department] ?? [];

  if (workflows.length === 0) return null;

  return (
    <div className="grid grid-cols-2 gap-2 mb-3">
      {workflows.map((workflow, index) => {
        const color = RIBBON_COLORS[index % RIBBON_COLORS.length];
        const isOpen =
          menuDash.active?.kind === "workflow" &&
          menuDash.active.department === department &&
          menuDash.active.itemKey === workflow.key;

        return (
          <WorkButton type="submit"
            key={workflow.key}
            onClick={() => menuDash.open(department, workflow.key, "workflow")}
            className={
              isOpen
                ? "relative flex items-center gap-2.5 text-left text-xs bg-zinc-900 border rounded-lg pl-4 pr-3 py-2.5 overflow-hidden transition"
                : "relative flex items-center gap-2.5 text-left text-xs bg-zinc-900 border border-zinc-800 rounded-lg pl-4 pr-3 py-2.5 overflow-hidden hover:border-current transition"
            }
            style={{ borderColor: isOpen ? color : undefined }}
          >
            {/* Angled brand-color flag (styleguide's 27-degree shear) in place of the
                old plain round dot -- the automotive-performance "cut corner" accent
                applied to every job-workflow button, not just decorative shapes. */}
            <span className="nxt-accent absolute left-0 top-0 bottom-0 w-2.5"
              style={{ background: color, clipPath: "polygon(0 0, 100% 0, 45% 100%, 0 100%)" }}
            />
            <span className="text-zinc-200 leading-tight font-brand font-semibold uppercase tracking-wide text-xs">
              {workflow.title}
            </span>
          </WorkButton>
        );
      })}
    </div>
  );
}
