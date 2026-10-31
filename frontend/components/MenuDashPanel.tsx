"use client";
import { WorkButton, WorkInput , WorkOverlay} from "./WorkspaceUi";
import {RecordCollection} from "./RecordCollection";
import {RecordTable} from "./RecordTable";
import { WorkField } from "./WorkField";

// The Top Menu item's own "dash" (session 60). Sam: "when you click on the menu items,
// they'll open up as their own dashes, but instead of floating on top, we need to
// collapse the middle column into the chat, and the right column to the edge, with a
// little tab icon if you want to reopen it. We should leave this one colored black
// (charcoal) - same deal, if you want to pop it out into another window you can - both
// columns return to normal."
//
// Deliberately charcoal/neutral (bg-black, zinc borders) rather than
// components/DepartmentWorkflowButtons.tsx's RIBBON_COLORS palette -- a visually
// distinct "you're in the DMS-style navigation layer now" cue, not another floating
// colored modal. MenuDashBody is exported chrome-free (no header, no positioning) so
// both the in-page collapsed-takeover panel below and the pop-out route
// (app/panel/menudash/page.tsx) render the exact same real functionality, same split
// as WorkflowWindowBody/WorkflowWindow.
//
// Session-60 follow-up (Sam, same day): (1) a light/dark theme selector, default dark,
// "in case people want to see it in a more traditional list" -- JsonValue and the
// panel chrome below both take a `theme` prop rather than relying on Tailwind's global
// dark-mode variant, since the rest of NXTDeal is unconditionally dark-styled with
// literal zinc classes, not `dark:` variants. (2) a real print feature -- honors
// whatever search query is currently filtering the view (the same `data` already on
// screen), and paginates the largest list found in the response into pages of an
// adjustable size, starting from an adjustable page number, via a genuine
// print-only DOM region + `window.print()` (the standard "hide everything else"
// technique), not a fake button. (3) the left-hand item nav was removed for the
// in-page usage (MenuDashPanel passes hideNav) since components/DepartmentMenuBar.tsx
// already provides that navigation at the top of the page -- Sam: "take out the
// navigation on the left, its already at the top." The pop-out window (which has no
// DepartmentMenuBar of its own) keeps a top item strip instead of a left sidebar, same
// "navigation lives at the top, never on the left" rule applied there too.
import { PRODUCT_CHART_COLORS } from "@/lib/productTheme";
import { useState, useEffect, useMemo, useRef, type DragEvent } from "react";
import { useWorkspaceTools } from "@/lib/workspaceTools";
import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";
import { fetchMenuCatalog, DEPARTMENT_MENU_GROUPS, type MenuCatalogItem } from "@/components/DepartmentMenuBar";
import { ReportDashboardBuilder } from "@/components/ReportDashboardBuilder";
import {
  VISUALIZATION_DRAG_TYPE,
  type VisualizationDropPayload,
} from "@/lib/useVisualizationWorkspace";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from "recharts";
import { EntityHoverLink, VinHoverLink } from "@/components/EntityHoverLink";
import { MarketingCRMBoard } from "@/components/MarketingCRMBoard";
import { CampaignsBoard } from "@/components/CampaignsBoard";
import { CampaignLibraryBoard } from "@/components/CampaignLibraryBoard";
import { CampaignSchedulerBoard } from "@/components/CampaignSchedulerBoard";
import { LeadImportBoard } from "@/components/LeadImportBoard";
import { FileManagerBoard } from "@/components/FileManagerBoard";
import { UserManagementBoard } from "@/components/UserManagementBoard";
import { LeadRoutingBoard } from "@/components/LeadRoutingBoard";
import { ConnectionsBoard } from "@/components/ConnectionsBoard";
import { PropensityBoard } from "@/components/PropensityBoard";
import { PayrollBoard } from "@/components/PayrollBoard";
import { PURLBoard } from "@/components/PURLBoard";
import { EmailSmsBuilder } from "@/components/EmailSmsBuilder";
import { SocialReputationBoard } from "@/components/SocialReputationBoard";
import { DealDeskBoard } from "@/components/DealDeskBoard";
import { ProspectsBoard } from "@/components/ProspectsBoard";
import { SalesOverviewBoard } from "@/components/SalesOverviewBoard";
import { CustomersBoard } from "@/components/CustomersBoard";
import { AppointmentsBoard } from "@/components/AppointmentsBoard";
import { ServiceAppointmentsBoard } from "@/components/ServiceAppointmentsBoard";
import { RepairOrderWorkspaceBoard } from "@/components/RepairOrderWorkspaceBoard";
import { ServiceOverviewBoard } from "@/components/ServiceOverviewBoard";
import { ShopControlBoard } from "@/components/ShopControlBoard";
import { CustomersServiceBoard } from "@/components/CustomersServiceBoard";
import { PartsDeskBoard } from "@/components/PartsDeskBoard";
import { WarrantyDeskBoard } from "@/components/WarrantyDeskBoard";
import { VehicleLifecycleBoard } from "@/components/VehicleLifecycleBoard";
import { OperationsOverviewBoard } from "@/components/OperationsOverviewBoard";
import { OperationsTasksBoard } from "@/components/OperationsTasksBoard";
import { InventoryAgingBoard } from "@/components/InventoryAgingBoard";
import { OperationsSchedulingBoard } from "@/components/OperationsSchedulingBoard";
import { DocumentWorkflowsBoard } from "@/components/DocumentWorkflowsBoard";
import { OperationsAlertsBoard } from "@/components/OperationsAlertsBoard";
import { OperationsCommunicationsBoard } from "@/components/OperationsCommunicationsBoard";
import { OperationsCustomerJourneyBoard } from "@/components/OperationsCustomerJourneyBoard";
import { AccessoriesAcceleratorBoard } from "@/components/AccessoriesAcceleratorBoard";
import { EquityCenterBoard } from "@/components/EquityCenterBoard";
import { InventoryAdvertisingBoard } from "@/components/InventoryAdvertisingBoard";
import { LoyaltyProgramBoard as LoyaltyRewardsBoard } from "@/components/LoyaltyProgramBoard";
import { SuccessCenterBoard } from "@/components/SuccessCenterBoard";
import { ConsultingEngineBoard } from "@/components/ConsultingEngineBoard";
import { WorkforceBoard } from "@/components/WorkforceBoard";
import { OperationsWorkflowV2Board } from "@/components/OperationsWorkflowV2Board";
import { CommunicationsBoard } from "@/components/CommunicationsBoard";
import { InventoryWorkspaceBoard } from "@/components/InventoryWorkspaceBoard";
import { AcquisitionsBoard } from "@/components/AcquisitionsBoard";
import { PricingDeskBoard } from "@/components/PricingDeskBoard";
import { LotControlBoard } from "@/components/LotControlBoard";
import { MerchandisingBoard } from "@/components/MerchandisingBoard";
import { WholesaleDeskBoard } from "@/components/WholesaleDeskBoard";
import { InventoryBoard } from "@/components/InventoryBoard";
import { AdvertisingBoard } from "@/components/AdvertisingBoard";
import { AttributionBoard } from "@/components/AttributionBoard";
import { EventsBoard } from "@/components/EventsBoard";
import { WebsiteBuilderBoard } from "@/components/WebsiteBuilderBoard";
import { PortfolioBoard } from "@/components/PortfolioBoard";
import { PaymentsBoard } from "@/components/PaymentsBoard";
import { CollectionsBoard } from "@/components/CollectionsBoard";
import { RepossessionsBoard } from "@/components/RepossessionsBoard";
import { GpsDevicesBoard } from "@/components/GpsDevicesBoard";
import { StarterInterruptBoard } from "@/components/StarterInterruptBoard";
import { AssetManagementBoard } from "@/components/AssetManagementBoard";
import { LenderIntelligenceBoard } from "@/components/LenderIntelligenceBoard";
import { InventorySyndicationBoard } from "@/components/InventorySyndicationBoard";
import { LendingComplianceBoard } from "@/components/LendingComplianceBoard";
import { LoanAccountingBoard } from "@/components/LoanAccountingBoard";
import { RolesPermissionsBoard } from "@/components/RolesPermissionsBoard";
import { VendorManagementBoard } from "@/components/VendorManagementBoard";
import { OrganizationsBoard } from "@/components/OrganizationsBoard";
import { DataManagementBoard } from "@/components/DataManagementBoard";
import { IdentityAccessBoard } from "@/components/IdentityAccessBoard";
import { AuditCenterBoard } from "@/components/AuditCenterBoard";
import { GovernanceBoard } from "@/components/GovernanceBoard";
import { WorkflowAutomationBoard } from "@/components/WorkflowAutomationBoard";
import { AiManagementBoard } from "@/components/AiManagementBoard";
import { AddModulesBoard } from "@/components/AddModulesBoard";
import { AiSpendBoard } from "@/components/AiSpendBoard";
import { FleetBoard } from "@/components/FleetBoard";
import { AiWorkforceBoard } from "@/components/AiWorkforceBoard";
import { ConnectBoard } from "@/components/ConnectBoard";
import { DigitalRetailBoard } from "@/components/DigitalRetailBoard";
import { MarketplaceBoard, type MarketplaceView } from "@/components/MarketplaceBoard";
import AddToWorkspaceButton from "@/components/AddToWorkspaceButton";
import BoardCaptureButton from "@/components/BoardCaptureButton";
import BoardPredictionButton from "@/components/BoardPredictionButton";
import { DEPARTMENT_TO_PREDICTION_KEY } from "@/lib/predictionTimeline";
import { AdminUsersBoard } from "@/components/AdminUsersBoard";
import { BusinessHealthBoard } from "@/components/BusinessHealthBoard";
import { EnterpriseRiskCenterBoard } from "@/components/EnterpriseRiskCenterBoard";
import { ReadinessRecommendationsBoard } from "@/components/ReadinessRecommendationsBoard";
import { ReadinessOverviewBoard } from "@/components/ReadinessOverviewBoard";
import { DataHealthBoard } from "@/components/DataHealthBoard";
import { PerformanceReadinessBoard } from "@/components/PerformanceReadinessBoard";
import { ReadinessForecastsBoard } from "@/components/ReadinessForecastsBoard";
import { ReadinessScenariosBoard } from "@/components/ReadinessScenariosBoard";
import { StrategicPlanningBoard } from "@/components/StrategicPlanningBoard";
import { SecurityAdminPanel } from "@/components/SecurityAdminPanel";
import { NetworkOverviewBoard } from "@/components/NetworkOverviewBoard";
import { NetworkOpportunitiesBoard } from "@/components/NetworkOpportunitiesBoard";
import { NetworkGapAnalysisBoard } from "@/components/NetworkGapAnalysisBoard";
import { NetworkTrendsBoard } from "@/components/NetworkTrendsBoard";
import { NetworkForecastsBoard } from "@/components/NetworkForecastsBoard";
import { NetworkPlaybooksBoard } from "@/components/NetworkPlaybooksBoard";
import { NetworkAdvisorsBoard } from "@/components/NetworkAdvisorsBoard";

const QUERY_CAPABLE_ITEMS = new Set(["vehicles", "documents"]);

// Code Auditor finding CAF-00122 (god_component_menu_dash_panel, large/systemic) --
// this file's render-dispatch decision used to be a long chain of sequential,
// order-dependent boolean conditions (some bare `itemKey === "X"`, some
// `department === "Y" && itemKey === "X"`), the exact shape that once let an
// earlier, unconditional `itemKey === "overview"` branch silently shadow a later,
// more specific `department === "Readiness" && itemKey === "overview"` branch --
// a real bug documented at length elsewhere in this codebase's history. That one
// instance was already patched with a `!(department === "Readiness")` exclusion,
// but the underlying PATTERN (many sequential conditions, correctness depending on
// write order) remained a standing structural risk for any future addition.
//
// Fix: every department+itemKey combination this file renders a bespoke board for
// is enumerated once, explicitly, in the two Sets below. resolveDispatchKey()
// resolves `department`+`itemKey` into exactly ONE canonical string per render --
// department-specific boards get "{department}:{itemKey}", department-agnostic
// boards get their bare itemKey, and the render ternary below now branches on
// `dispatchKey === "..."` equality checks instead of re-deriving the same boolean
// logic inline. Since dispatchKey can only ever equal one string at a time, the
// branches are now inherently mutually exclusive and order-independent -- the same
// shadowing bug class can no longer occur no matter what order a future branch is
// inserted in. Every JSX body below is untouched; only the guard condition on each
// branch changed.
const GENERIC_BOARD_KEYS = new Set<string>(["crm", "campaigns", "purls", "email_sms", "social_reputation", "advertising", "analytics", "events", "website", "deals", "prospects", "campaign_library", "campaign_scheduler", "lead_import", "file_manager", "propensity"]);

const SPECIFIC_BOARD_KEYS = new Set<string>([
  "Administration:team_management",
  "Administration:lead_routing",
  "Administration:connections",
  "Operations:payroll",
  "Sales:customers",
  "Sales:appointments",
  "Sales:workflows",
  "Sales:communications",
  "Sales:inventory",
  "Service:appointments",
  "Service:repair_orders",
  "Service:shop_control",
  "Service:customers",
  "Service:parts",
  "Service:warranty",
  "Operations:vehicles",
  "Operations:tasks",
  "Operations:inventory",
  "Operations:scheduling",
  "Operations:documents",
  "Operations:alerts",
  "Operations:communications",
  "Operations:workforce",
  "Operations:workflows",
  "Inventory:inventory",
  "Inventory:acquisitions",
  "Inventory:pricing",
  "Inventory:lot_management",
  "Inventory:merchandising",
  "Inventory:wholesale",
  "Inventory:syndication",
  "Finance:portfolio",
  "Finance:payments",
  "Finance:collections",
  "Finance:repossessions",
  "Finance:gps_devices",
  "Finance:starter_interrupt",
  "Finance:assets",
  "Finance:compliance",
  "Finance:accounting",
  "Finance:lender_intelligence",
  "Administration:roles_permissions",
  "Administration:vendors",
  "Administration:organizations",
  "Administration:data_management",
  "Administration:identity_access",
  "Administration:audit_center",
  "Administration:governance",
  "Administration:workflow_automation",
  "Administration:ai_management",
  "Administration:modules",
  "Administration:ai_spend",
  "Administration:fleet",
  "Administration:ai_workforce",
  "Administration:connect",
  "Administration:digital_retail",
  "Marketplace:browse",
  "Marketplace:installed",
  "Marketplace:oem",
  "Marketplace:phase2",
  "Marketplace:partners",
  "Readiness:business_health",
  "Readiness:exceptions",
  "Readiness:recommendations",
  "Readiness:overview",
  "Readiness:data_health",
  "Readiness:readiness",
  "Readiness:forecasts",
  "Readiness:simulations",
  "Readiness:strategic_planning",
  "Network:opportunities",
  "Network:gap_analysis",
  "Network:trends",
  "Network:forecasts",
  "Network:playbooks",
  "Network:ai_advisors",
  "Administration:users",
  "Operations:customer_journey",
  "Sales:accessories",
  "Sales:equity_center",
  "Marketing:inventory_advertising",
  "Marketing:loyalty",
  "Administration:success_center",
  "Network:consulting_engine",
]);

function resolveDispatchKey(department: string, itemKey: string): string {
  // The one compound condition in the original chain: Reporting is shared by every
  // department, and Overview uses the same generic report-dashboard board too --
  // EXCEPT for Readiness, which has its own dedicated Overview board further down
  // (the exact override that used to get shadowed, see the comment above).
  if (itemKey === "reporting" || (itemKey === "overview" && department !== "Readiness")) {
    return "reporting_overview";
  }
  if (GENERIC_BOARD_KEYS.has(itemKey)) {
    return itemKey;
  }
  const specific = `${department}:${itemKey}`;
  if (SPECIFIC_BOARD_KEYS.has(specific)) {
    return specific;
  }
  // No bespoke board registered for this department+itemKey -- falls through to the
  // generic JSON/table view at the end of the render chain, same as before.
  return "generic_fallback";
}

type Theme = "dark" | "light";

function prettify(key: string): string {
  return key
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

// Session 76 fourth follow-up (Sam: "it should all be accessible at every point...
// linked through the chat, and through the sub menu dashes as well"). Same regex shape
// components/MessageContent.tsx already uses for chat -- any Menu Dash value that looks
// like a real NXTDeal entity ID (VEH-00042, CUST-00001, ...) becomes a real connection
// into that entity's profile. Fifth follow-up (Sam: "instead of clicking the link and
// it opening in a new tab - can it pop up in a modal when you hover over it, with the
// option to pop it out into a new window or to push into the dash / sub menu area") --
// components/EntityHoverLink.tsx owns the hover-preview-card + pop-out/push-to-Dash
// behavior now; this file just detects the ID shape and hands off to it.
const ENTITY_ID_PATTERN = /\b([A-Z]{2,10}-\d{4,6})\b/;

function renderPrimitiveValue(value: unknown, className: string) {
  const text = String(value);
  const match = ENTITY_ID_PATTERN.exec(text);

  if (match && match[0] === text) {
    return <EntityHoverLink id={text} className={className} />;
  }

  // Session 76 sixth follow-up -- same VIN treatment
  // components/DepartmentWorkflowButtons.tsx's ValuePreview applies, kept in sync
  // deliberately (this is the OTHER real renderer for entity-shaped data, the generic
  // Top Menu Dash JSON tree).
  if (/^[A-HJ-NPR-Z0-9]{17}$/.test(text)) {
    return <VinHoverLink vin={text} className={className} />;
  }

  return <span className={className}>{text}</span>;
}

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

// Visualize (Sam: "I should be able to access parts of the menu dashes and
// visualize the data in the workflow") -- a lightweight first version: any array of
// objects with at least one numeric column gets a "Visualize" toggle that renders an
// inline recharts bar chart of that data instead of the table, using the first
// non-numeric column as the label axis. Deliberately small in scope for now (a toggle
// on data that's already rendered, not the full expand-to-center/AI-chart-editing
// workspace originally described) -- Sam scoped this pass to "start small" with room
// to grow into the bigger workspace later.
function ObjectListView({
  rows,
  totalCount,
  depth,
  theme,
  path = [],
  dragCtx,
}: {
  rows: Record<string, unknown>[];
  totalCount: number;
  depth: number;
  theme: Theme;
  path?: (string | number)[];
  dragCtx?: { department: string; itemKey: string };
}) {
  const [chartMode, setChartMode] = useState(false);

  const keySet = new Set<string>();
  rows.forEach((r) => Object.keys(r).forEach((k) => keySet.add(k)));
  const columns = Array.from(keySet).slice(0, 6);

  const numericColumns = columns.filter((c) => rows.some((r) => typeof r[c] === "number"));
  const labelColumn = columns.find((c) => !numericColumns.includes(c)) ?? columns[0];
  const canChart = numericColumns.length > 0 && rows.length > 1;
  const workspaceTools = useWorkspaceTools();
  const canDrag = workspaceTools && canChart && !!dragCtx;

  const chartData = useMemo(() => {
    return rows.slice(0, 20).map((r) => {
      const out: Record<string, unknown> = { _label: String(r[labelColumn] ?? "") };
      numericColumns.forEach((c) => {
        out[c] = r[c];
      });
      return out;
    });
  }, [rows, labelColumn, numericColumns]);

  function handleDragStart(event: DragEvent<HTMLButtonElement>) {
    if (!dragCtx) return;

    const payload: VisualizationDropPayload = {
      department: dragCtx.department,
      itemKey: dragCtx.itemKey,
      fieldPath: path.map((p) => String(p)),
      sourceLabel: prettify(String(path[path.length - 1] ?? dragCtx.itemKey)),
      rows,
      numericColumns,
      labelColumn,
    };

    event.dataTransfer.setData(VISUALIZATION_DRAG_TYPE, JSON.stringify(payload));
    event.dataTransfer.effectAllowed = "copy";
  }

  return (
    <div>
      <div className="flex items-center gap-2 mb-1">
        {canChart && (
          <WorkButton type="submit"
            onClick={() => setChartMode((m) => !m)}
            className={tc(
              theme,
              "text-xs px-2 py-0.5 rounded border border-zinc-800 text-zinc-400 hover:text-white hover:border-zinc-600 transition",
              "text-xs px-2 py-0.5 rounded border border-zinc-300 text-zinc-600 hover:text-black hover:border-zinc-500 transition"
            )}
          >
            {chartMode ? "☰ Table" : "📊 Visualize"}
          </WorkButton>
        )}

        {canDrag && (
          <WorkButton type="submit"
            draggable
            onDragStart={handleDragStart}
            title="Drag into the Workspace to build a chart, then pin it"
            className={tc(
              theme,
              "text-xs px-2 py-0.5 rounded border border-dashed border-zinc-700 text-zinc-500 hover:text-white hover:border-zinc-500 transition cursor-grab active:cursor-grabbing",
              "text-xs px-2 py-0.5 rounded border border-dashed border-zinc-400 text-zinc-600 hover:text-black hover:border-zinc-600 transition cursor-grab active:cursor-grabbing"
            )}
          >
            ⠿ Drag to Workspace
          </WorkButton>
        )}

        {/* Grab this exact table into the Workspace as a snapshot (works for ANY table,
            not just chart-capable data) -- Workspace grab-all, 2026-07-23. */}
        {rows.length > 0 && (
          <AddToWorkspaceButton
            theme={theme}
            title={prettify(String(path[path.length - 1] ?? dragCtx?.itemKey ?? "Data"))}
            sourceLabel={dragCtx ? `${dragCtx.department} · ${prettify(dragCtx.itemKey)}` : undefined}
            columns={columns}
            rows={rows}
          />
        )}
      </div>

      {chartMode && canChart ? (
        <div style={{ width: "100%", height: 220 }}>
          <ResponsiveContainer>
            <BarChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke={theme === "dark" ? "#27272a" : "#e4e4e7"} />
              <XAxis
                dataKey="_label"
                tick={{ fontSize: 10, fill: theme === "dark" ? "#a1a1aa" : "#52525b" }}
                interval={0}
                angle={-30}
                textAnchor="end"
                height={50}
              />
              <YAxis tick={{ fontSize: 10, fill: theme === "dark" ? "#a1a1aa" : "#52525b" }} />
              <Tooltip
                contentStyle={{
                  fontSize: 11,
                  background: theme === "dark" ? "#18181b" : "#ffffff",
                  border: "1px solid #3f3f46",
                }}
              />
              {numericColumns.slice(0, 3).map((c, i) => (
                <Bar key={c} dataKey={c} fill={PRODUCT_CHART_COLORS[i % PRODUCT_CHART_COLORS.length]} radius={[3, 3, 0, 0]} />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <RecordTable className="w-full text-xs">
            <thead>
              <tr className={tc(theme, "text-zinc-500 text-left border-b border-zinc-800", "text-zinc-600 text-left border-b border-zinc-300")}>
                {columns.map((c) => (
                  <th key={c} className="py-1 pr-3 font-medium">
                    {prettify(c)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i} className={tc(theme, "border-b border-zinc-900 last:border-0", "border-b border-zinc-200 last:border-0")}>
                  {columns.map((c) => (
                    <td key={c} className="py-1 pr-3 align-top">
                      <JsonValue value={r[c]} depth={depth + 1} theme={theme} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </RecordTable>

        </div>
      )}
    </div>
  );
}

// Inline entity editing (Sam: "we need to be able to edit the information in the menu
// dashes where it makes sense"). Detected wherever JsonValue encounters an object
// shaped like {id, entity_type, attributes} -- exactly what GET /entity/{id},
// core/ai_tools.py's get_entity_by_id/get_related_entities, and
// core/entity_update_api.py's response all already return, so this fires naturally
// on a workflow window's linked_entity block and related_entities list without any
// per-source wiring. Only primitive (string/number/boolean/null) attribute values are
// directly editable inline; nested objects/arrays render read-only via JsonValue,
// matching the backend's own patch rule (arbitrary nested writes aren't attempted).
function EntityEditCard({
  entity,
  theme,
}: {
  entity: { id: string; entity_type: string; attributes: Record<string, unknown> };
  theme: Theme;
}) {
  const [current, setCurrent] = useState(entity);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setCurrent(entity);
  }, [entity]);

  const editableKeys = Object.keys(current.attributes).filter((k) => {
    const v = current.attributes[k];
    return v === null || typeof v === "string" || typeof v === "number" || typeof v === "boolean";
  });

  function startEditing() {
    const seed: Record<string, string> = {};
    editableKeys.forEach((k) => {
      const v = current.attributes[k];
      seed[k] = v === null || v === undefined ? "" : String(v);
    });
    setDraft(seed);
    setError(null);
    setEditing(true);
  }

  async function save() {
    setSaving(true);
    setError(null);

    const patch: Record<string, unknown> = {};
    editableKeys.forEach((k) => {
      const original = current.attributes[k];
      const next = draft[k];
      let coerced: unknown = next;
      if (typeof original === "number") coerced = next === "" ? null : Number(next);
      else if (typeof original === "boolean") coerced = next === "true";
      if (coerced !== original) patch[k] = coerced;
    });

    if (Object.keys(patch).length === 0) {
      setEditing(false);
      setSaving(false);
      return;
    }

    try {
      const res = await fetch(`${API_BASE}/entity/${current.id}/update`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ patch }),
      });
      const data = await res.json();

      if (data.error) {
        setError(data.error);
      } else {
        setCurrent(data);
        setEditing(false);
      }
    } catch {
      setError("Unable to reach NXTDeal backend.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className={tc(theme, "rounded-lg border border-zinc-800 overflow-hidden", "rounded-lg border border-zinc-300 overflow-hidden")}>
      <div
        className={tc(
          theme,
          "flex items-center justify-between px-3 py-2 bg-brand-charcoal border-b border-black/20",
          "flex items-center justify-between px-3 py-2 bg-zinc-100 border-b border-zinc-300"
        )}
      >
        <div className="text-xs">
          <span className={tc(theme, "text-zinc-500", "text-zinc-600")}>{current.entity_type}</span>{" "}
          <span className={tc(theme, "text-zinc-200", "text-zinc-900")}>{current.id}</span>
        </div>

        {editing ? (
          <div className="flex items-center gap-2">
            <WorkButton type="submit"
              onClick={() => setEditing(false)}
              disabled={saving}
              className={tc(
                theme,
                "text-xs text-zinc-500 hover:text-white transition disabled:opacity-40",
                "text-xs text-zinc-500 hover:text-black transition disabled:opacity-40"
              )}
            >
              Cancel
            </WorkButton>
            <WorkButton type="submit"
              onClick={save}
              disabled={saving}
              className="text-xs px-2 py-1 rounded bg-zinc-200 text-black font-medium hover:bg-white transition disabled:opacity-40"
            >
              {saving ? "Saving..." : "💾 Save"}
            </WorkButton>
          </div>
        ) : (
          <WorkButton type="submit"
            onClick={startEditing}
            className={tc(theme, "text-xs text-zinc-400 hover:text-white transition", "text-xs text-zinc-600 hover:text-black transition")}
          >
            {"✎ Edit"}
          </WorkButton>
        )}
      </div>

      {error && <div className="px-3 py-2 text-xs text-red-400">{error}</div>}

      <div className="p-2">
        <table className="work-property-table w-full">
          <tbody>
            {Object.entries(current.attributes).map(([k, v]) => (
              <tr key={k} className={tc(theme, "border-b border-zinc-900 last:border-0 align-top", "border-b border-zinc-200 last:border-0 align-top")}>
                <td className={tc(theme, "py-1 pr-3 text-zinc-500 whitespace-nowrap", "py-1 pr-3 text-zinc-600 whitespace-nowrap")}>
                  {prettify(k)}
                </td>
                <td className="py-1">
                  {editing && editableKeys.includes(k) ? (
                    <WorkInput
                      aria-label={k.replaceAll("_", " ")} value={draft[k] ?? ""}
                      onChange={(e) => setDraft((d) => ({ ...d, [k]: e.target.value }))}
                      className={tc(
                        theme,
                        "w-full h-7 px-2 text-xs rounded bg-zinc-900 border border-zinc-700 focus:outline-none focus:border-zinc-500",
                        "w-full h-7 px-2 text-xs rounded bg-white border border-zinc-300 text-zinc-900 focus:outline-none focus:border-zinc-500"
                      )}
                    />
                  ) : (
                    <JsonValue value={v} depth={1} theme={theme} />
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// Exported (session -- Sam: "I should be able to access parts of the menu dashes and
// visualize the data in the workflow") so components/DepartmentWorkflowButtons.tsx's
// workflow-window LiveDataPanel can reuse the exact same renderer -- Visualize toggle
// and inline entity editing included -- instead of maintaining a second, divergent
// object/array renderer. One engine, not one component per surface.
export function JsonValue({
  value,
  depth = 0,
  theme,
  path = [],
  dragCtx,
}: {
  value: unknown;
  depth?: number;
  theme: Theme;
  // Path of object/array keys from the response root down to `value` -- carried along
  // so a drag source deep in the recursion (ObjectListView) can report exactly which
  // field a chartable array came from (VisualizationDropPayload.fieldPath), letting a
  // pinned visualization re-fetch that same field live later rather than freezing a
  // snapshot.
  path?: (string | number)[];
  // Present only when this JsonValue tree is rendering a Reporting Top-Menu item (Sam
  // scoped drag-to-workspace to Reporting dashes only) -- when set, chartable arrays
  // get a draggable handle; when undefined (every other menu item, and
  // DepartmentWorkflowButtons.tsx's workflow-window usage), dragging stays disabled.
  dragCtx?: { department: string; itemKey: string };
}) {
  if (value === null || value === undefined || value === "") {
    return <span className={tc(theme, "text-zinc-600", "text-zinc-400")}>—</span>;
  }

  if (typeof value !== "object") {
    return renderPrimitiveValue(value, tc(theme, "text-zinc-200", "text-zinc-900"));
  }

  if (depth >= 4) {
    return (
      <details>
        <summary className={tc(theme, "cursor-pointer text-zinc-500 text-xs", "cursor-pointer text-zinc-500 text-xs")}>
          expand…
        </summary>
        <pre
          className={tc(
            theme,
            "mt-1 p-2 rounded bg-brand-ink border border-black/20 text-xs overflow-x-auto whitespace-pre-wrap",
            "mt-1 p-2 rounded bg-zinc-50 border border-zinc-300 text-xs overflow-x-auto whitespace-pre-wrap"
          )}
        >
          {JSON.stringify(value, null, 2)}
        </pre>
      </details>
    );
  }

  if (Array.isArray(value)) {
    if (value.length === 0) return <span className={tc(theme, "text-zinc-600", "text-zinc-400")}>Nothing here.</span>;

    const isObjectList = value.every((v) => v && typeof v === "object" && !Array.isArray(v));

    if (!isObjectList) {
      return (
        <ul className={tc(theme, "text-xs text-zinc-300 list-disc pl-4 space-y-0.5", "text-xs text-zinc-800 list-disc pl-4 space-y-0.5")}>
          <RecordCollection list>{value.map((v, i) => (
            <li key={i}>
              <JsonValue value={v} depth={depth + 1} theme={theme} path={[...path, i]} dragCtx={dragCtx} />
            </li>
          ))}</RecordCollection>
        </ul>
      );
    }

    const rows = value as Record<string, unknown>[];

    return (
      <ObjectListView
        rows={rows}
        totalCount={value.length}
        depth={depth}
        theme={theme}
        path={path}
        dragCtx={dragCtx}
      />
    );
  }

  const obj = value as Record<string, unknown>;

  // Inline entity editing hook -- fires wherever a value is shaped exactly like
  // GET /entity/{id} / core/ai_tools.py's entity-serialization shape, so a workflow
  // window's linked_entity block and related_entities list both get this for free.
  if (
    typeof obj.id === "string" &&
    typeof obj.entity_type === "string" &&
    obj.attributes &&
    typeof obj.attributes === "object" &&
    !Array.isArray(obj.attributes)
  ) {
    return (
      <EntityEditCard
        entity={obj as { id: string; entity_type: string; attributes: Record<string, unknown> }}
        theme={theme}
      />
    );
  }

  const entries = Object.entries(obj);
  if (entries.length === 0) return <span className={tc(theme, "text-zinc-600", "text-zinc-400")}>—</span>;

  return (
    <table className="work-property-table w-full">
      <tbody>
        {entries.map(([k, v]) => (
          <tr key={k} className={tc(theme, "border-b border-zinc-900 last:border-0 align-top", "border-b border-zinc-200 last:border-0 align-top")}>
            <td className={tc(theme, "py-1 pr-3 text-zinc-500 whitespace-nowrap", "py-1 pr-3 text-zinc-600 whitespace-nowrap")}>
              {prettify(k)}
            </td>
            <td className="py-1">
              <JsonValue value={v} depth={depth + 1} theme={theme} path={[...path, k]} dragCtx={dragCtx} />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// Print pagination -- finds the largest array-of-objects anywhere up to 2 levels deep
// in the response (Tasks' `tasks`, Vehicles' `results`, Documents' flattened
// `by_type`, etc.) to paginate; everything else in the response prints once, up front,
// as a summary section. Real pagination over whatever's actually in `data` -- not a
// fixed template.
function findPrintableRows(value: unknown, depth = 0): { key: string; rows: Record<string, unknown>[] } | null {
  if (depth > 2 || !value || typeof value !== "object" || Array.isArray(value)) return null;

  let best: { key: string; rows: Record<string, unknown>[] } | null = null;

  for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
    if (Array.isArray(v) && v.length > 0 && v.every((item) => item && typeof item === "object" && !Array.isArray(item))) {
      if (!best || v.length > best.rows.length) best = { key: k, rows: v as Record<string, unknown>[] };
    } else if (v && typeof v === "object" && !Array.isArray(v)) {
      const nested = findPrintableRows(v, depth + 1);
      if (nested && (!best || nested.rows.length > best.rows.length)) best = nested;
    }
  }

  return best;
}

function chunk<T>(arr: T[], size: number): T[][] {
  if (size <= 0) return [arr];
  const out: T[][] = [];
  for (let i = 0; i < arr.length; i += size) out.push(arr.slice(i, i + size));
  return out;
}

function PrintHeader({
  department,
  itemLabel,
  query,
  printedAt,
}: {
  department: string;
  itemLabel: string;
  query: string;
  printedAt: string;
}) {
  return (
    <div style={{ borderBottom: "2px solid #000", paddingBottom: 8, marginBottom: 16 }}>
      <div style={{ fontSize: 16, fontWeight: 600 }}>
        NXTDeal — {department} — {itemLabel}
      </div>
      <div style={{ fontSize: 11, color: "#555" }}>
        Printed {printedAt}
        {query ? ` — Filter: "${query}"` : ""}
      </div>
    </div>
  );
}

function PrintFooter({ pageNumber }: { pageNumber: number }) {
  return (
    <div style={{ marginTop: 16, fontSize: 11, color: "#555", textAlign: "right" }}>
      Page {pageNumber}
    </div>
  );
}

function PrintDocument({
  department,
  itemLabel,
  query,
  data,
  rowsPerPage,
  startPage,
}: {
  department: string;
  itemLabel: string;
  query: string;
  data: unknown;
  rowsPerPage: number;
  startPage: number;
}) {
  if (!data) return null;

  const found = findPrintableRows(data);
  const summary = found
    ? Object.fromEntries(Object.entries(data as Record<string, unknown>).filter(([k]) => k !== found.key))
    : data;
  const pages = found ? chunk(found.rows, rowsPerPage) : [];
  const printedAt = new Date().toLocaleString();

  return (
    <>
      <div className="print-page">
        <PrintHeader department={department} itemLabel={itemLabel} query={query} printedAt={printedAt} />
        <JsonValue value={summary} theme="light" />
        <PrintFooter pageNumber={startPage} />
      </div>

      {pages.map((rows, i) => (
        <div className="print-page" key={i}>
          <PrintHeader department={department} itemLabel={itemLabel} query={query} printedAt={printedAt} />
          <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 8 }}>{prettify(found!.key)}</div>
          <JsonValue value={rows} theme="light" />
          <PrintFooter pageNumber={startPage + i + 1} />
        </div>
      ))}
    </>
  );
}

// Standalone panel nav dropdown (2026-07-24). When a Dash is opened on its own (gear-icon
// settings menu / pop-out), MenuDashBody renders its own top nav. For a department with domain
// groups (Administration), this renders each group as a real dropdown TAB matching the main
// DepartmentMenuBar -- instead of the old flat wall of grouped buttons -- so the standalone
// Administration surface reads as tabs, not "little groupings" (Sam's feedback). Wired to
// onSelect so a pick switches THIS panel's board, not a page navigation.
function PanelNavDropdown({
  theme,
  label,
  groupItems,
  activeKey,
  onSelect,
}: {
  theme: Theme;
  label: string;
  groupItems: MenuCatalogItem[];
  activeKey: string;
  onSelect: (key: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    function handle(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handle);
    return () => document.removeEventListener("mousedown", handle);
  }, [open]);
  const active = groupItems.some((it) => it.key === activeKey);
  return (
    <div ref={ref} className="relative">
      <WorkButton type="submit"
        onClick={() => setOpen((v) => !v)}
        className={
          open || active
            ? "text-xs font-bold uppercase tracking-wide px-2.5 py-1 rounded-md bg-brand-teal text-black transition flex items-center gap-1.5"
            : tc(
                theme,
                "text-xs font-semibold uppercase tracking-wide px-2.5 py-1 rounded-md text-zinc-400 hover:text-white hover:bg-zinc-900 transition flex items-center gap-1.5",
                "text-xs font-semibold uppercase tracking-wide px-2.5 py-1 rounded-md text-zinc-600 hover:text-black hover:bg-zinc-200 transition flex items-center gap-1.5"
              )
        }
      >
        {label}
        <span className={open ? "text-xs rotate-180 transition" : "text-xs transition"}>▾</span>
      </WorkButton>
      {open && (
        <div className="absolute left-0 top-full mt-1 z-30 w-60 bg-brand-charcoal border border-black/20 rounded-lg shadow-xl p-1.5 flex flex-col gap-1">
          {groupItems.map((item) => (
            <WorkButton type="submit"
              key={item.key}
              onClick={() => {
                onSelect(item.key);
                setOpen(false);
              }}
              title={item.description}
              className={
                item.key === activeKey
                  ? "w-full text-left text-xs font-semibold uppercase tracking-wide bg-brand-teal text-black px-3 py-2 rounded-md transition"
                  : "w-full text-left text-xs font-semibold uppercase tracking-wide text-zinc-300 hover:bg-zinc-900 px-3 py-2 rounded-md transition"
              }
            >
              {item.label}
            </WorkButton>
          ))}
        </div>
      )}
    </div>
  );
}

// A single direct tab in the standalone nav (an ungrouped item, or a one-item group).
function PanelNavTab({
  theme,
  item,
  activeKey,
  onSelect,
}: {
  theme: Theme;
  item: MenuCatalogItem;
  activeKey: string;
  onSelect: (key: string) => void;
}) {
  const isActive = item.key === activeKey;
  return (
    <WorkButton type="submit"
      onClick={() => onSelect(item.key)}
      title={item.description}
      className={
        isActive
          ? "text-xs font-bold uppercase tracking-wide px-2.5 py-1 rounded-md bg-brand-teal text-black transition"
          : tc(
              theme,
              "text-xs font-semibold uppercase tracking-wide px-2.5 py-1 rounded-md text-zinc-400 hover:text-white hover:bg-zinc-900 transition",
              "text-xs font-semibold uppercase tracking-wide px-2.5 py-1 rounded-md text-zinc-600 hover:text-black hover:bg-zinc-200 transition"
            )
      }
    >
      {item.label}
    </WorkButton>
  );
}

export function MenuDashBody({
  onDraftOpenChange,
  onSavingChange,
  department,
  itemKey,
  onSelectItem,
  hideNav = false,
  hideAssistant = false,
  initialQuery = "",
  initialTheme = "dark",
}: {
  department: string;
  itemKey: string;
  onSelectItem: (key: string) => void;
  hideNav?: boolean;
  hideAssistant?: boolean;
  // Session 76: pre-fills the search box when this Dash was opened from a chat
  // "deep link" suggestion for a specific, query-capable record (e.g. a VIN).
  initialQuery?: string;
  initialTheme?: Theme;
  onDraftOpenChange?: (open:boolean)=>void; onSavingChange?: (saving:boolean)=>void;
}) {
  const [items, setItems] = useState<MenuCatalogItem[]>([]);
  const [data, setData] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState(initialQuery);
  const [theme, setTheme] = useState<Theme>(initialTheme);
  useEffect(() => { setTheme(initialTheme); }, [initialTheme]);
  const [showPrintSettings, setShowPrintSettings] = useState(false);
  const [rowsPerPage, setRowsPerPage] = useState(20);
  const [startPage, setStartPage] = useState(1);
  // Session 72, Sam: "in the sub menu areas, where it has dark, light, and print in the
  // same line - can we add a zoom in / zoom out / reset option for people that want to
  // zoom in the text?" -- a CSS transform/scale on the content area below the toolbar
  // (not the toolbar itself, so the zoom controls stay a fixed, predictable size no
  // matter how far in/out the content is zoomed). Width is compensated by the inverse
  // percentage so scaled-down content doesn't leave a dead gap, and scaled-up content
  // still reads left-to-right rather than clipping.
  const [zoom, setZoom] = useState(100);

  useEffect(() => {
    fetchMenuCatalog(department).then(setItems);
  }, [department]);

  useEffect(() => {
    // Session 73: the Reporting item no longer renders this raw /menu/data fetch at
    // all -- components/ReportDashboardBuilder.tsx fetches its own module catalog
    // (which itself re-derives from the same underlying reporting() data
    // server-side), so this call would just be wasted bandwidth for that one item.
    // Session 77: Overview gets the exact same treatment -- it's now a
    // ReportDashboardBuilder board too (board="overview"), not a raw JSON dump.
    // Session 79: Marketing's CRM and Email/SMS items are their own real
    // workspaces (components/MarketingCRMBoard.tsx / EmailSmsBuilder.tsx) with
    // their own fetches (crm() and email_sms() come back through the same real
    // /menu/data route those components call directly) -- no raw JSON dump here.
    // Session 83: same treatment for Social/Reputation and Advertising
    // (components/SocialReputationBoard.tsx / AdvertisingBoard.tsx) -- both talk
    // directly to their own /social, /reputation, /advertising routes rather than
    // the generic /menu/data JSON dump. Session 84: same treatment for Events
    // (components/EventsBoard.tsx) -- talks directly to /alerts/* and /events/*.
    // Session 85: same treatment for Website (components/WebsiteBuilderBoard.tsx) --
    // talks directly to /websites/*, /personal-sites/*, and the chat routes.
    if (
      itemKey === "reporting" ||
      itemKey === "overview" ||
      itemKey === "crm" ||
      itemKey === "campaigns" ||
      itemKey === "purls" ||
      itemKey === "email_sms" ||
      itemKey === "social_reputation" ||
      itemKey === "advertising" ||
      itemKey === "analytics" ||
      itemKey === "events" ||
      itemKey === "website" ||
      itemKey === "deals" ||
      itemKey === "prospects" ||
      (department === "Sales" && itemKey === "customers") ||
      (department === "Sales" && itemKey === "appointments") ||
      (department === "Sales" && itemKey === "communications") ||
      (department === "Sales" && itemKey === "inventory") ||
      (department === "Service" && itemKey === "appointments") ||
      (department === "Service" && itemKey === "repair_orders") ||
      (department === "Service" && itemKey === "shop_control") ||
      (department === "Service" && itemKey === "customers") ||
      (department === "Service" && itemKey === "parts") ||
      (department === "Service" && itemKey === "warranty") ||
      (department === "Operations" && itemKey === "vehicles") ||
      (department === "Operations" && itemKey === "tasks") ||
      (department === "Operations" && itemKey === "inventory") ||
      (department === "Operations" && itemKey === "scheduling") ||
      (department === "Operations" && itemKey === "documents") ||
      (department === "Operations" && itemKey === "alerts") ||
      (department === "Operations" && itemKey === "communications") ||
      (department === "Operations" && itemKey === "workforce") ||
      (department === "Inventory" && itemKey === "inventory") ||
      (department === "Inventory" && itemKey === "acquisitions") ||
      (department === "Inventory" && itemKey === "pricing") ||
      (department === "Inventory" && itemKey === "lot_management") ||
      (department === "Inventory" && itemKey === "merchandising") ||
      (department === "Inventory" && itemKey === "wholesale") ||
      (department === "Inventory" && itemKey === "syndication") ||
      (department === "Finance" && itemKey === "portfolio") ||
      (department === "Finance" && itemKey === "payments") ||
      (department === "Finance" && itemKey === "collections") ||
      (department === "Finance" && itemKey === "repossessions") ||
      (department === "Finance" && itemKey === "gps_devices") ||
      (department === "Finance" && itemKey === "starter_interrupt") ||
      (department === "Finance" && itemKey === "assets") ||
      (department === "Finance" && itemKey === "compliance") ||
      (department === "Finance" && itemKey === "accounting") ||
      (department === "Finance" && itemKey === "lender_intelligence") ||
      (department === "Administration" && itemKey === "roles_permissions") ||
      (department === "Administration" && itemKey === "vendors") ||
      (department === "Administration" && itemKey === "organizations") ||
      (department === "Administration" && itemKey === "data_management") ||
      (department === "Administration" && itemKey === "identity_access") ||
      (department === "Administration" && itemKey === "audit_center") ||
      (department === "Administration" && itemKey === "governance") ||
      (department === "Administration" && itemKey === "workflow_automation") ||
      (department === "Administration" && itemKey === "ai_management") ||
      (department === "Administration" && itemKey === "fleet") ||
      (department === "Administration" && itemKey === "ai_workforce") ||
      (department === "Administration" && itemKey === "connect") ||
      (department === "Administration" && itemKey === "digital_retail") ||
      (department === "Administration" && itemKey === "users") ||
      department === "Marketplace" ||
      (department === "Readiness" && itemKey === "business_health") ||
      (department === "Readiness" && itemKey === "exceptions") ||
      (department === "Readiness" && itemKey === "recommendations") ||
      (department === "Readiness" && itemKey === "overview") ||
      (department === "Readiness" && itemKey === "data_health") ||
      (department === "Readiness" && itemKey === "readiness") ||
      (department === "Readiness" && itemKey === "forecasts") ||
      (department === "Readiness" && itemKey === "simulations") ||
      (department === "Readiness" && itemKey === "strategic_planning") ||
      (department === "Network" && itemKey === "opportunities") ||
      (department === "Network" && itemKey === "gap_analysis") ||
      (department === "Network" && itemKey === "trends") ||
      (department === "Network" && itemKey === "forecasts") ||
      (department === "Network" && itemKey === "playbooks") ||
      (department === "Network" && itemKey === "ai_advisors")
    ) {
      setData(null);
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);

    const params = new URLSearchParams({ department, item_key: itemKey });
    if (query && QUERY_CAPABLE_ITEMS.has(itemKey)) params.set("query", query);

    fetch(`${API_BASE}/menu/data?${params.toString()}`, { headers: { ...authHeaders() } })
      .then((r) => r.json())
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch(() => {
        if (!cancelled) setData({ error: "Unable to reach NXTDeal backend." });
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [department, itemKey, query]);

  const current = items.find((i) => i.key === itemKey);
  const isQueryCapable = QUERY_CAPABLE_ITEMS.has(itemKey);

  const printPageCount = useMemo(() => {
    const found = findPrintableRows(data);
    return found ? 1 + Math.ceil(found.rows.length / Math.max(1, rowsPerPage)) : 1;
  }, [data, rowsPerPage]);

  function handlePrint() {
    setShowPrintSettings(false);
    // Give the (now-updated) print-only region a paint cycle before invoking the
    // browser's print dialog.
    requestAnimationFrame(() => requestAnimationFrame(() => window.print()));
  }

  const workspaceTools = useWorkspaceTools();
  const dispatchKey = resolveDispatchKey(department, itemKey);
  const boardRef = useRef<HTMLDivElement>(null);

  return (
    <div data-appearance={theme} ref={boardRef} className={tc(theme, "relative flex-1 flex flex-col min-h-0 bg-brand-ink", "relative flex-1 flex flex-col min-h-0 bg-white")}>
      {/* Universal "grab this view into Workspace" -- scrapes the rendered board's KPI
          tiles + tables (Workspace grab-all, 2026-07-23), so every dash is grabbable
          without wiring a button into each board component. print:hidden so it never
          appears on printed output. */}
      {workspaceTools && <div className="absolute bottom-3 right-3 z-30 print:hidden flex flex-col items-end gap-2">
        {/* Pillar 2 (predictive layer, 2026-07-23): the same universal-mount idea as the
            Workspace capture button below — one floating "Predict" control brings the
            existing PredictionHorizonSlider to every board of a forecastable department
            (Sales/Service/Finance/Marketing), so the predictive horizon reaches all
            reporting surfaces without per-board wiring. Suppressed on the
            Reporting/Overview boards, which already surface their own prediction UI
            (inline full-width slider / per-module ModuleHorizonControl). */}
        {DEPARTMENT_TO_PREDICTION_KEY[department] && dispatchKey !== "reporting_overview" && (
          <BoardPredictionButton department={department} theme={theme} openUp />
        )}
        <BoardCaptureButton
          getEl={() => boardRef.current}
          title={current?.label ?? prettify(itemKey)}
          sourceLabel={`${department} · ${current?.label ?? prettify(itemKey)}`}
          theme={theme}
          openUp
        />
      </div>}
      {/* Session-60 follow-up: navigation lives at the top, never on the left. The
          in-page usage (MenuDashPanel) suppresses this via hideNav since
          components/DepartmentMenuBar.tsx already renders the same 8 items at the top
          of the page; the pop-out window (no DepartmentMenuBar of its own) keeps it. */}
      {!hideNav && items.length > 0 && (() => {
        // Navigation strip. When the department defines domain groups (DepartmentMenuBar's
        // DEPARTMENT_MENU_GROUPS -- e.g. Administration: Workspace / Security & Governance /
        // Platform Operations / ...), render the strip organized into those labeled domains
        // rather than one long flat row; otherwise fall back to the flat row.
        const navBtn = (item: MenuCatalogItem) => (
          <WorkButton type="submit"
            key={item.key}
            onClick={() => onSelectItem(item.key)}
            className={
              item.key === itemKey
                ? "text-xs px-2.5 py-1 rounded-md bg-zinc-200 text-black font-medium transition"
                : tc(
                    theme,
                    "text-xs px-2.5 py-1 rounded-md text-zinc-400 hover:text-white hover:bg-zinc-900 transition",
                    "text-xs px-2.5 py-1 rounded-md text-zinc-600 hover:text-black hover:bg-zinc-200 transition"
                  )
            }
          >
            {item.label}
          </WorkButton>
        );
        const groups = DEPARTMENT_MENU_GROUPS[department];
        return (
          <div className={tc(theme, "border-b border-black/20 bg-brand-charcoal px-3 py-2", "border-b border-zinc-200 bg-zinc-100 px-3 py-2")}>
            {groups ? (
              // Dropdown TABS (matching the main DepartmentMenuBar): a one-item group or a bare
              // item is a direct tab; a multi-item group is a labeled dropdown. Replaces the old
              // flat wall of grouped buttons (Sam: "instead of tabs it just laid them out with
              // little groupings").
              <div className="flex items-center gap-1.5 flex-wrap font-brand">
                {groups.map((entry, gi) => {
                  const keys = entry.type === "group" ? entry.keys : [entry.key];
                  const groupItems = keys
                    .map((k) => items.find((it) => it.key === k))
                    .filter((it): it is MenuCatalogItem => Boolean(it));
                  if (groupItems.length === 0) return null;
                  if (entry.type === "group" && groupItems.length > 1) {
                    return (
                      <PanelNavDropdown
                        key={"grp:" + entry.label}
                        theme={theme}
                        label={entry.label}
                        groupItems={groupItems}
                        activeKey={itemKey}
                        onSelect={onSelectItem}
                      />
                    );
                  }
                  return (
                    <PanelNavTab
                      key={groupItems[0].key}
                      theme={theme}
                      item={groupItems[0]}
                      activeKey={itemKey}
                      onSelect={onSelectItem}
                    />
                  );
                })}
              </div>
            ) : (
              <div className="flex items-center gap-1 flex-wrap">{items.map(navBtn)}</div>
            )}
          </div>
        );
      })()}

      {/* Board area (2026-07-24, Sam: dashes were getting cut off with no scroll). One
          flex-col + overflow-y-auto wrapper so EVERY board fits its shell: a full-height board
          (flex-1, e.g. reporting/CRM) fills and self-scrolls as before, while a natural-height
          content board now scrolls here instead of overflowing the panel. */}
      <div className="flex-1 min-h-0 flex flex-col overflow-y-auto">
      {dispatchKey === "reporting_overview" ? (
        // Session 73: Reporting is no longer a raw JSON dump -- it's a fully
        // customizable, drag-and-drop dashboard of real per-department report
        // modules. Session 77: Overview gets the identical treatment, as its own
        // board -- a default-seeded "BI visual glance" of that department's top
        // KPIs, still fully drag-and-drop customizable, and still able to pull in
        // any Reporting section flagged "Show in Overview." ReportDashboardBuilder
        // owns its own theme/full-screen/print toolbar (a dashboard board needs
        // different controls -- available-modules tray, per-module settings -- than
        // a plain JSON tree does), so none of the Dark/Light/Zoom/Print row or
        // print-settings modal below applies to either board. Session 78, Sam: "all
        // the modules in the overview need to have the time horizon adjusters on
        // them, and the top predictive horizon chart on all of the overviews (that
        // have it) needs to be deleted" -- the single big slider now stays Reporting
        // -only; Overview's per-module ModuleHorizonControl (inside each
        // ReportDashboardModule card, wired up by ReportDashboardBuilder) replaces it.
        <div className="flex-1 min-h-0 flex flex-col overflow-hidden">
          {/* Sam (2026-07-24): the large PREDICTIVE HORIZON slider is removed from every
              department's Reporting/Overview — prediction belongs inside each report module
              (per-module ModuleHorizonControl) or as an add-on, not a big banner chart. The
              floating "Predict" board button still offers it on demand. */}
          {/* Session 94 follow-up, Sam: add Sales' real My Tasks/Action Center/Daily
              Sales/Sales Manager dashboards ABOVE the generic KPI board, not in place
              of it -- every other department's Overview stays exactly this generic
              board, unchanged. */}
          {department === "Sales" && itemKey === "overview" && (
            <div className="shrink-0">
              <SalesOverviewBoard theme={theme} />
            </div>
          )}
          {/* Session 106 follow-up #2, Sam's Operations spec: real Action Center/
              Department Health/Workload Distribution ABOVE the generic KPI board,
              same "ABOVE, not instead of" precedent as Sales' Overview. */}
          {department === "Operations" && itemKey === "overview" && (
            <div className="shrink-0">
              <OperationsOverviewBoard theme={theme} />
            </div>
          )}
          {/* Service rebuild, second slice: real Command Center/Today's Risks
              (manager-tier only)/Advisor Dashboard ABOVE the generic KPI
              board, same "ABOVE, not instead of" precedent as Sales/
              Operations' own Overview enrichments. */}
          {department === "Service" && itemKey === "overview" && (
            <div className="shrink-0">
              <ServiceOverviewBoard theme={theme} />
            </div>
          )}
          {/* Intelligence Network reframe, slice 1: real Executive Summary/
              Largest Opportunities/Total Identified Opportunity ABOVE the
              generic KPI board, same "ABOVE, not instead of" precedent as
              Sales/Operations/Service's own Overview enrichments. */}
          {department === "Network" && itemKey === "overview" && (
            <div className="shrink-0 overflow-y-auto max-h-[70vh]">
              <NetworkOverviewBoard theme={theme} hideAssistant={hideAssistant} />
            </div>
          )}
          <div className="flex-1 min-h-0">
            <ReportDashboardBuilder
              theme={theme}
              department={department}
              board={itemKey === "overview" ? "overview" : "reporting"}
            />
          </div>
        </div>
      ) : dispatchKey === "crm" ? (
        // Session 79: Marketing's "CRM" item -- HubSpot-style Pipeline/Lists/
        // Campaigns/Opportunities workspace, replacing the old standalone
        // Campaigns/Audiences/Opportunities menu items with one real workflow dash.
        <MarketingCRMBoard theme={theme} />
      ) : dispatchKey === "campaigns" ? (
        // Session 113 follow-up: Marketing's own dedicated "Campaigns" item, split
        // back out of the merged "CRM" item per Sam's later 12-item Growth Platform
        // menu spec (Sam: "klets do it") -- reuses CrmBoard's own CampaignsTab/
        // CampaignDetailView, fed by a leaner campaigns()-only fetch. The CRM item's
        // own Campaigns tab above is completely untouched.
        <CampaignsBoard theme={theme} />
      ) : dispatchKey === "campaign_library" ? (
        // Bumper-parity: browsable library of prebuilt campaign templates (one-click launch).
        <CampaignLibraryBoard theme={theme} />
      ) : dispatchKey === "campaign_scheduler" ? (
        // Bumper-parity: Duplication Station + Recurring Schedule + Multi-Planner.
        <CampaignSchedulerBoard theme={theme} />
      ) : dispatchKey === "lead_import" ? (
        // Bumper-parity: bulk CSV import with column mapping + dedupe.
        <LeadImportBoard theme={theme} />
      ) : dispatchKey === "file_manager" ? (
        // Bumper-parity: general multi-type digital-asset library (image/video/audio/document).
        <FileManagerBoard theme={theme} />
      ) : dispatchKey === "propensity" ? (
        // Competitive roadmap Phase 1: 0-100 buy-propensity leaderboard + outreach + enrichment.
        <PropensityBoard theme={theme} />
      ) : dispatchKey === "Operations:payroll" ? (
        // Competitive roadmap Phase 5: time clock + pay plans + payroll runs + paychecks.
        <PayrollBoard theme={theme} />
      ) : dispatchKey === "purls" ? (
        // Session 113 follow-up: Marketing's "PURLs" item -- the Personalized URL
        // Platform (dealer.com/john-smith), a real Generate/List/Revoke workspace
        // with a client-side QR code + Mail Piece for direct mail.
        <PURLBoard theme={theme} />
      ) : dispatchKey === "email_sms" ? (
        // Session 79: Marketing's "Email / SMS" item -- AI wizard + drag-and-drop
        // block builder, an Email/SMS channel toggle, and a recipient picker that
        // pulls straight from the same real CRM audience/campaign engine above.
        <EmailSmsBuilder theme={theme} />
      ) : dispatchKey === "social_reputation" ? (
        // Session 83: Marketing's "Social / Reputation" item -- a Hootsuite-style
        // social post builder/calendar with inventory drop-in, toggled against real
        // per-review response + bad-review alerting + simulated competitor tracking.
        <SocialReputationBoard theme={theme} />
      ) : dispatchKey === "advertising" ? (
        // Session 83: Marketing's "Advertising" item -- Meta/Google ad campaigns
        // with inventory integration, AI-recommended or fully manual.
        <AdvertisingBoard theme={theme} />
      ) : dispatchKey === "analytics" ? (
        // Session 113 follow-up: Marketing's "Analytics" item -- the Attribution
        // Engine capstone: real first-touch Channel Mix & ROI by Lead Source, a
        // Marketing ROI Dashboard rolling up real Campaign/PURL revenue
        // correlation, and Vehicle Attribution (marketed vs. actually-selling
        // Make/Model combinations).
        <AttributionBoard theme={theme} />
      ) : dispatchKey === "events" ? (
        // Session 84: Marketing's "Events" item -- a Timeline/Events toggle: a live
        // AutoAlert/automotiveMastermind-style trigger-alert feed, and real NXTDeal
        // Bumper-style dealership events with CRM-list-backed invites/RSVPs. Both
        // one-click promote into a real new CRM Lead.
        <EventsBoard theme={theme} />
      ) : dispatchKey === "website" ? (
        // Session 85: Marketing's "Website" item -- the full website builder now
        // actually mounted in the Dash (layout templates, drag-and-drop sections
        // with per-section AI writing, image library, per-page SEO/DNS/robots/
        // analytics, live chat wired into the CRM, personal URL microsites).
        <WebsiteBuilderBoard theme={theme} />
      ) : dispatchKey === "deals" ? (
        // Session 91: Sales' "Deals" item -- the real DMS Deal Desk (backend has
        // existed since session 33; this is the first frontend on top of it). A
        // draggable Pipeline Kanban (desking -> financing -> contract -> funded), a
        // Deal Worksheet with a multi-scenario Pencil Tool, a Trade Appraisal panel
        // with manager approval, and Desking/Financing through to funding.
        <DealDeskBoard inline theme={theme} />
      ) : dispatchKey === "prospects" ? (
        // Session 92 follow-up: Sales' "Prospects" item -- the CRM-style lead
        // center. Source-bucketed summary + search, opening a real Lead Record
        // (Customer Profile, merged Activity Timeline, Communication Hub, Task
        // Management, Customer Notes, rules-based Next Best Action) with a
        // Convert-to-Customer action feeding straight into the Deal Desk's
        // New Deal flow.
        <ProspectsBoard theme={theme} />
      ) : dispatchKey === "Sales:customers" ? (
        // Session 95 follow-up: Sales' "Customers" item -- customer-centric search,
        // a real grouped Customer 360 (Purchase History, Service History, Finance
        // Contracts, Vehicles Owned), Equity Mining, and a Retention Center (both
        // reusing the real Trigger Alert Timeline built for Marketing's Events dash
        // rather than a second signal-detection pass). Service's own "Customers"
        // item is untouched -- this branch is Sales-only.
        <CustomersBoard theme={theme} />
      ) : dispatchKey === "Sales:appointments" ? (
        // Session 96 follow-up: Sales' "Appointments" item -- the real sales
        // calendar (core/appointments.py), closing the single most-repeated
        // "not_yet_tracked" gap in this codebase. Service's own "Appointments" item
        // is untouched (backend data is real there too now, but no dedicated
        // frontend was built for it this pass) -- this branch is Sales-only.
        <AppointmentsBoard workflow theme={theme} />
      ) : dispatchKey === "Sales:communications" ? (
        // Session 98 follow-up: Sales' "Communications" item -- a real unified
        // inbox aggregating the Communication Hub log (call/text/email/video,
        // built for Prospects session 92) across every lead, plus the real
        // follow-up cadence queue and marketing-compliance alerts. Mass
        // messaging/templates are Marketing's Email/SMS CRM, reused rather than
        // duplicated here. This branch is Sales-only.
        <CommunicationsBoard theme={theme} />
      ) : dispatchKey === "Sales:inventory" ? (
        // Session 99 follow-up: Sales' "Inventory" item -- the last of the original
        // 8 submenus. A sales-facing vehicle browser/locator (distinct from the
        // Inventory department's own management Dash), real payment-based search
        // (an honest ESTIMATE), a real Reservation/Hold mechanism
        // (core/vehicle_holds.py -- closes a genuine gap: nothing previously
        // prevented two reps desking the same unsold vehicle at once), and a
        // side-by-side Comparison Tool. This branch is Sales-only.
        <InventoryBoard inline theme={theme} />
      ) : dispatchKey === "Service:appointments" ? (
        // Session 105 follow-up: Service's "Appointments" item -- the dedicated
        // service scheduling center (core/appointments.py, real since session 96,
        // shared with Sales via a `department` attribute). Today's/This Week's
        // schedule, technician/advisor calendars, waiter-vs-drop-off, recall
        // appointments, and no-show tracking. This branch is Service-only --
        // Sales' own "Appointments" item is untouched.
        <ServiceAppointmentsBoard theme={theme} />
      ) : dispatchKey === "Service:repair_orders" ? (
        // Service department rebuild kickoff -- the RO Workflow Engine, the
        // centerpiece Sam asked for ("This should be the centerpiece of
        // Service... a full operating environment"). Turns ServiceRecord into
        // a real 10-stage lifecycle entity (Check-In -> RO Written ->
        // Inspection -> Estimate -> Customer Approval -> Parts -> Repair ->
        // Quality Control -> Delivery -> Follow-Up, core/repair_orders.py)
        // with a real Kanban board, concern tracking, an estimate/approval
        // flow, parts requests, a QC checklist (gated ready-for-pickup), and
        // a composed timeline that folds in the integrated Communication
        // Center. This branch is Service-only.
        <RepairOrderWorkspaceBoard inline theme={theme} />
      ) : dispatchKey === "Service:shop_control" ? (
        // Service rebuild, third slice -- Shop Control, Sam's own framing:
        // "the operational heart of the shop." A real drag-and-drop
        // Technician Dispatch Board (core/shop_control.py), Technician
        // Utilization (HEURISTIC over an assumed daily capacity -- no real
        // time-clock data exists), Stalled RO Detection ("RO Open 9 Hours,
        // No Labor Posted"), and a composed Bottlenecks feed. The Shop
        // Workflow Board itself isn't duplicated here -- that's
        // RepairOrderWorkspaceBoard.tsx's real Kanban. This branch is
        // Service-only.
        <ShopControlBoard theme={theme} />
      ) : dispatchKey === "Service:customers" ? (
        // Service rebuild, fourth slice -- Customers, Sam's own framing:
        // "Service should be relationship-driven." A real Customer Service
        // Profile (Vehicles Owned with warranty/recall status, Service
        // History, Declined Services, Retention metrics off
        // core/service_customers.py), Lost Customer Recovery (no service in
        // 12+ months), and a Declined Services feed ("one of the biggest
        // profit drivers") where each record opens the real RO Workspace for
        // a one-click follow-up. Sales' own "Customers" item (CustomersBoard,
        // Purchase History/Equity Mining/Retention Center) is untouched --
        // this branch is Service-only.
        <CustomersServiceBoard theme={theme} />
      ) : dispatchKey === "Service:parts" ? (
        // Service rebuild, fifth slice -- Parts. A real department-wide
        // Parts Request Queue (previously only visible one RO at a time via
        // the RO Workflow Engine's own Parts tab), Special Order Tracking
        // (vendor/ETA, a genuinely new capability -- core/parts_desk.py),
        // and Inventory Recommendations (REAL, computed off real PartSale
        // velocity vs. real Part.QuantityOnHand, no fabrication needed).
        // RO Parts Status itself isn't duplicated here -- that's already
        // real inside each RO's own Parts tab. This branch is Service-only.
        <PartsDeskBoard theme={theme} onDraftOpenChange={onDraftOpenChange} onSavingChange={onSavingChange} />
      ) : dispatchKey === "Service:warranty" ? (
        // Service rebuild, sixth slice -- Warranty. Warranty Eligibility
        // Check (real Condition-based inference plus a real open-recall
        // cross-reference), a real Submission Workflow (draft -> submitted
        // -> approved/rejected -> paid, core/warranty_desk.py), a Rejected
        // Claims Queue, and Recall Management (real per-vehicle recall-
        // completion tracking, a genuinely new capability -- nothing
        // previously tracked which vehicles had actually had a given open
        // recall's repair completed). This branch is Service-only.
        <WarrantyDeskBoard theme={theme} onDraftOpenChange={onDraftOpenChange} onSavingChange={onSavingChange} />
      ) : dispatchKey === "Operations:vehicles" ? (
        // Session 106 follow-up: Operations' "Vehicles" item -- Vehicle Lifecycle
        // Management, the flagship build of Operations' rebuild (core/
        // vehicle_lifecycle.py). A real 10-stage pipeline board (Acquired ->
        // ... -> Delivered), a real Recon Checklist, real Vendor Coordination,
        // and real Internal Messaging between departments about a specific
        // vehicle (reusing core/field_notes.py). This branch is Operations-only.
        <VehicleLifecycleBoard theme={theme} />
      ) : dispatchKey === "Operations:tasks" ? (
        // Session 106 follow-up #3: Operations' "Tasks" item -- the Universal
        // Operations Work Queue (core/operations_tasks.py). A real first-class
        // OperationsTask entity (open -> in_progress -> closed) with live SLA
        // fields (hours_open/is_overdue), Assign Owner, Bulk Actions, and a
        // "Sync From Signals" button that turns real graph gaps (wholesale
        // candidates, lot-audit discrepancies, open compliance alerts) -- the
        // same three signal types core/operations_menu.py's old read-only
        // tasks() view already surfaced -- into real trackable tickets. This
        // branch is Operations-only.
        <OperationsTasksBoard theme={theme} />
      ) : dispatchKey === "Operations:inventory" ? (
        // Session 106 follow-up #4: Operations' "Inventory" item -- Inventory
        // Aging Management (core/inventory_aging.py). A real price-band board
        // (the honest HEURISTIC proxy for true day-based aging -- no
        // acquisition-date field exists on Vehicle) with 5 real actions: Price
        // Reduction (a genuine mutation), Wholesale/Manager Review and Auction
        // Assignment (create a real OperationsTask, reusing the engine built
        // for the Tasks item), and Marketing Campaign tie-in (creates a real
        // draft inventory_ads Campaign). This branch is Operations-only --
        // Sales' own "Inventory" item (components/InventoryBoard.tsx) is
        // untouched.
        <InventoryAgingBoard theme={theme} />
      ) : dispatchKey === "Operations:scheduling" ? (
        // Session 106 follow-up #5: Operations' "Scheduling" item -- Recon
        // Scheduling, Delivery Scheduling with real automatic risk detection
        // (cross-references contract/funded Deals against real open delivery
        // Appointments), and Transport Scheduling (a real transport_status
        // mutation on AuctionTransaction -- previously read-only since
        // seeding). This branch is Operations-only.
        <OperationsSchedulingBoard theme={theme} />
      ) : dispatchKey === "Operations:documents" ? (
        // Session 106 follow-up #6: Operations' "Documents" item -- Deal
        // Jacket Workflow / Title Processing / Compliance Packets (all the
        // same real completeness-check + request action over the existing
        // categorized Document vault) and Digital Approvals (a genuinely new
        // approve/reject capability -- Document had no approval_status field
        // before this slice). This branch is Operations-only.
        <DocumentWorkflowsBoard theme={theme} />
      ) : dispatchKey === "Operations:alerts" ? (
        // Session 106 follow-up #7: Operations' "Alerts" item -- upgraded from
        // a read-only exception report into a real nervous system. Unifies
        // seven real signal types across five modules into one severity-
        // ranked feed, each with a real action button (deep-linking into an
        // already-built engine for five of them; acknowledge_alert() creates
        // a real OperationsTask for the two that had no prior action). This
        // branch is Operations-only.
        <OperationsAlertsBoard theme={theme} />
      ) : dispatchKey === "Operations:communications" ? (
        // The Unified Communications Hub (2026-07-19) -- a real, read-only,
        // cross-department feed composing Sales'/Service's/Finance's own
        // already-real contact logs into one company-wide inbox. This
        // branch is Operations-only; Sales' own communications item
        // (department === "Sales" && itemKey === "communications", above)
        // is untouched.
        <OperationsCommunicationsBoard theme={theme} />
      ) : dispatchKey === "Operations:customer_journey" ? (
        <OperationsCustomerJourneyBoard theme={theme} />
      ) : dispatchKey === "Sales:accessories" ? (
        <AccessoriesAcceleratorBoard theme={theme} />
      ) : dispatchKey === "Sales:equity_center" ? (
        <EquityCenterBoard theme={theme} />
      ) : dispatchKey === "Marketing:inventory_advertising" ? (
        <InventoryAdvertisingBoard theme={theme} />
      ) : dispatchKey === "Marketing:loyalty" ? (
        <LoyaltyRewardsBoard theme={theme} />
      ) : dispatchKey === "Administration:success_center" ? (
        <SuccessCenterBoard theme={theme} />
      ) : dispatchKey === "Network:consulting_engine" ? (
        <ConsultingEngineBoard theme={theme} />
      ) : dispatchKey === "Operations:workforce" ? (
        // Workforce Management (2026-07-19) -- real Directory/Shift
        // Scheduling/Time-Off Requests (a real manager-tier approval gate)/
        // Coverage/Performance, closing the "Workforce" item from Sam's
        // six-pillar spec.
        <WorkforceBoard theme={theme} />
      ) : dispatchKey === "Operations:workflows" ? (
        // Operations Workflow Engine v2 (2026-07-21) -- the Workflow Dashboard +
        // Step Progression pilot rebuild (Sam's "workflows should be the primary
        // way work gets done" spec). OperationsWorkflowV2Board.tsx was later
        // generalized (2026-07-21) into a department-parameterized component so
        // Sales could reuse it directly -- see the Sales:workflows branch below.
        // Deliberately separate from the pre-existing v1 job-workflow-catalog
        // buttons (components/OperationsWorkflowPanel.tsx's floating
        // WorkflowWindow modal manager), which are untouched for both
        // departments.
        <OperationsWorkflowV2Board theme={theme} department="Operations" />
      ) : dispatchKey === "Sales:workflows" ? (
        // Sales Workflow Engine v2 (2026-07-21) -- reuses the exact same
        // OperationsWorkflowV2Board component as Operations' own pilot above,
        // just parameterized to Sales' real 18-workflow catalog (Prospecting/
        // Engagement/Deals/Finance/Retention: Lead Management, BDC Workflow, Up
        // System, Orphan Owner Mining, Appointment Workflow, Showroom Workflow,
        // Demo Drive, Trade Appraisal, Desking, Credit Application, Manager TO,
        // F&I Handoff, F&I Workflow, eSignature, Delivery Experience, Equity
        // Mining, Lease Maturity, Lost Sale Recovery) -- zero backend engine
        // changes were needed, since core/workflow_engine_v2.py/_api.py were
        // already fully department-agnostic.
        <OperationsWorkflowV2Board theme={theme} department="Sales" />
      ) : dispatchKey === "Inventory:inventory" ? (
        // Inventory department rebuild, first slice -- Sam picked "Inventory" (the
        // master vehicle workspace) over Acquisitions/Pricing/Overview as the
        // centerpiece. Reuses core/vehicle_lifecycle.py's real 10-stage Kanban
        // board engine (already built for Operations' "Vehicles" item) plus this
        // slice's own new real pieces: Cost Breakdown, Ownership assignment, and a
        // composed Activity Feed. A VIN/stock/free-text search sits above the
        // board. This branch is Inventory-only -- Operations' own "Inventory" item
        // (components/InventoryAgingBoard.tsx) and Sales' own "Inventory" item
        // (components/InventoryBoard.tsx) are both untouched.
        <InventoryWorkspaceBoard theme={theme} />
      ) : dispatchKey === "Inventory:acquisitions" ? (
        // Inventory department rebuild, second slice -- Sam's own framing:
        // "probably one of the most important modules... an entire buying
        // center." A real AcquisitionRequest moves through Evaluate -> Price
        // Risk -> Estimate Recon -> Review Market -> a 2-step Purchase
        // Approval chain (Inventory Manager -> GM/Admin) -> Purchased,
        // deliberately distinct from AuctionTransaction (acquisition-only,
        // already-purchased auction units) and Vehicle (may not exist yet at
        // evaluation time -- e.g. a walk-in seller's car). The Buy
        // Recommendation Engine and Factory Allocations feed are SIMULATED
        // per Sam's direct instruction (2026-07-17: "when a lack of data is
        // a problem, lets simply make up simulated data to accommodate it")
        // -- every simulated figure is surfaced with its disclaimer text
        // visible in the UI. This branch is Inventory-only.
        <AcquisitionsBoard theme={theme} />
      ) : dispatchKey === "Inventory:pricing" ? (
        // Inventory department rebuild, third slice -- the pricing desk. A
        // real worklist (unsold inventory ranked by worst real margin_pct
        // first) with SIMULATED market pricing/competitor comparisons/
        // age-based adjustment blended into a real recommendation, floored
        // at a real 3% margin over the vehicle's real Cost. Applying a
        // recommendation is a real, bidirectional Vehicle.Price mutation
        // (core/inventory_aging.py's new set_price(), a sibling to that
        // module's existing reduction-only reduce_price()) -- every
        // simulated figure carries a visible "Simulated" badge + disclaimer
        // per Sam's direct instruction (2026-07-17: "when a lack of data is
        // a problem, lets simply make up simulated data to accommodate
        // it"). This branch is Inventory-only.
        <PricingDeskBoard theme={theme} />
      ) : dispatchKey === "Inventory:lot_management" ? (
        // Inventory department rebuild, fifth slice -- Lot Management.
        // Unlike Pricing/Acquisitions (SIMULATED, since real market data
        // genuinely doesn't exist anywhere this system could obtain it),
        // Key Management/Damage Reports/Showroom Assignments/a granular Lot
        // Map are all REAL features here -- internal tracking capabilities
        // this codebase simply hadn't built yet, not external data gaps.
        // Geofencing remains an honest not_yet_tracked gap even under the
        // simulate-data policy (a simulated GPS coordinate with no real map
        // behind it would be misleading, not a useful stand-in). This
        // branch is Inventory-only.
        <LotControlBoard theme={theme} />
      ) : dispatchKey === "Inventory:merchandising" ? (
        // Inventory department rebuild, sixth slice -- Merchandising. A
        // deliberate mix: photo upload/description/featured flag are REAL
        // (internal capabilities nobody had built, same "build it real"
        // call Lot Management made); VDP Health Score and Feed Sync Status
        // are SIMULATED (a genuine external gap -- no real VDP-analytics
        // platform or third-party listing feed, e.g. Cars.com/AutoTrader,
        // is connected anywhere in this system), clearly labeled. This
        // branch is Inventory-only.
        <MerchandisingBoard theme={theme} onDraftOpenChange={onDraftOpenChange} onSavingChange={onSavingChange} />
      ) : dispatchKey === "Inventory:wholesale" ? (
        // Inventory department rebuild, seventh slice -- the Wholesale
        // Desk. Open Offers, Sold Wholesale Units, and Fund Collection are
        // all REAL features (internal tracking capabilities nobody had
        // built, same "build it real" call Lot Management/Merchandising
        // made) -- a real WholesaleOffer entity backs the offer lifecycle
        // (submit/accept/reject/counter/withdraw), a real
        // disposition_channel flag on Vehicle distinguishes a wholesale
        // sale from a retail one, and a real append-only settlement record
        // backs Fund Collection. This branch is Inventory-only.
        <WholesaleDeskBoard theme={theme} />
      ) : dispatchKey === "Inventory:syndication" ? (
        // Inventory's new "Syndication" item (2026-07-19) -- closes the
        // "Inventory Syndication" item from Sam's own six-pillar spec. A
        // dealership-wide rollup of core/merchandising.py's per-vehicle
        // SIMULATED feed-sync status (Cars.com/AutoTrader/CarGurus/CarFax)
        // plus real Lead.Source-based revenue/conversion performance per
        // syndication platform, reusing core/marketing_attribution.py's
        // channel mix verbatim. This branch is Inventory-only.
        <InventorySyndicationBoard theme={theme} />
      ) : dispatchKey === "Finance:portfolio" ? (
        // Finance's "Portfolio" item -- Loan Management, the first slice of
        // Sam's "Retail Automotive Lending Platform" expansion (2026-07-17).
        // A real amortization schedule/balance/terms-remaining computed
        // over each FinanceContract's real contract terms, plus a SIMULATED
        // delinquency-bucket payment status (no real payment ledger exists
        // yet -- see the upcoming Payments module) per Sam's direct
        // instruction ("when a lack of data is a problem, lets simply make
        // up simulated data to accommodate it"). This branch is
        // Finance-only.
        <PortfolioBoard theme={theme} />
      ) : dispatchKey === "Finance:payments" ? (
        // Finance's "Payments" item -- the real payment ledger, second slice
        // of Sam's "Retail Automotive Lending Platform" expansion
        // (2026-07-17). Real recording, an honestly SIMULATED gateway
        // approval/decline (no real processor connected), Auto Drafts,
        // Promises To Pay, and a real Customer Payment Portal link -- the
        // per-loan actions reuse PortfolioBoard.tsx's LoanDetailModal
        // directly. This branch is Finance-only.
        <PaymentsBoard theme={theme} />
      ) : dispatchKey === "Finance:collections" ? (
        // Finance's "Collections" item -- the third slice of Sam's "Retail
        // Automotive Lending Platform" expansion (2026-07-17). A real
        // bucketed delinquency work queue, a real Collection Agent
        // Workspace per loan (risk score, priority recommendation,
        // collection-stage path, contact logging), built entirely on top
        // of core/loan_servicing.py's own delinquency computation. "AI
        // Collection Prioritization" is a real, transparent rules engine,
        // not machine learning. This branch is Finance-only.
        <CollectionsBoard theme={theme} />
      ) : dispatchKey === "Finance:repossessions" ? (
        // Finance's "Repossessions" item -- the fourth slice of Sam's "Retail
        // Automotive Lending Platform" expansion (2026-07-17), the direct
        // continuation of Collections' own "repossession_referral" stage. A
        // real Referral Queue, case lifecycle, Deficiency Balance
        // calculation, and redemption path, cascading real loan_status
        // updates back onto Portfolio. This branch is Finance-only.
        <RepossessionsBoard theme={theme} />
      ) : dispatchKey === "Finance:gps_devices" ? (
        // Finance's "GPS & Devices" item -- the fifth slice of Sam's "Retail
        // Automotive Lending Platform" expansion (2026-07-17). A real
        // device registry with honestly SIMULATED GPS location telemetry.
        // Shares one real engine with Starter Interrupt below. This branch
        // is Finance-only.
        <GpsDevicesBoard theme={theme} />
      ) : dispatchKey === "Finance:starter_interrupt" ? (
        // Finance's "Starter Interrupt" item -- the fifth slice of Sam's
        // "Retail Automotive Lending Platform" expansion (2026-07-17). Real,
        // stored arm/warn/disable/enable control with a real enforced
        // warning-required-before-disable rule. Reuses GpsDevicesBoard's
        // exported DeviceDetailModal directly. This branch is Finance-only.
        <StarterInterruptBoard theme={theme} />
      ) : dispatchKey === "Finance:assets" ? (
        // Finance's "Assets" item -- the sixth slice of Sam's "Retail
        // Automotive Lending Platform" expansion (2026-07-17). Real Title
        // status, real Lien tracking (release gated on the loan being paid
        // off), real dealer-entered Insurance tracking, and a Collateral
        // Valuation/LTV blending real book value with SIMULATED market
        // value. Routes live at /collateral/*, not /assets/*, to avoid
        // colliding with Marketing's own Asset workflow. This branch is
        // Finance-only.
        <AssetManagementBoard theme={theme} />
      ) : dispatchKey === "Finance:compliance" ? (
        // Finance's "Compliance" item, extended -- the seventh slice of Sam's
        // "Retail Automotive Lending Platform" expansion (2026-07-17). Real
        // OFAC/SDN screening (a blocking deal_fund rule) and real IRS Form
        // 8300 cash-payment tracking with an honest pending/overdue
        // obligation status, layered on top of the pre-existing general
        // compliance rule catalog / open exceptions / deal jacket audits.
        // Routes live at /lending-compliance/*, not /compliance/*. This
        // branch is Finance-only.
        <LendingComplianceBoard theme={theme} />
      ) : dispatchKey === "Finance:accounting" ? (
        // Finance's "Accounting" item, extended -- the eighth slice of Sam's
        // "Retail Automotive Lending Platform" expansion (2026-07-17). A
        // real cash-basis loan sub-ledger built from core/payments.py's own
        // real Payment records: Interest Income/Principal Reduction/Cash
        // Collected, a daily journal-style ledger with a post/unposted
        // workflow, and a real month-end close. General Ledger/Bank
        // Reconciliation stay honest gaps -- no chart of accounts or bank
        // feed exists in this codebase. This branch is Finance-only.
        <LoanAccountingBoard theme={theme} />
      ) : dispatchKey === "Finance:lender_intelligence" ? (
        // Finance's "Lender Intelligence" item (2026-07-19) -- closes the
        // "Lender Intelligence" item from Sam's own six-pillar spec. Real
        // per-lender scorecards (approval rate, average offered APR, average
        // decision turnaround) computed off Deal Desk's own new, real,
        // append-only lender_submission_history log, plus a real,
        // transparent, rules-based lender recommendation -- never a
        // fabricated AI score. This branch is Finance-only.
        <LenderIntelligenceBoard theme={theme} />
      ) : dispatchKey === "Administration:roles_permissions" ? (
        // Administration Control Center rebuild, first slice (2026-07-18) --
        // Roles & Permissions. A real, additive layer on top of the platform's
        // 6 core roles (core/permissions_registry.py): a granular permission
        // catalog mirroring already-real ACL sets elsewhere in this codebase,
        // per-employee overrides, field-level security (already wired into
        // Customer 360's CreditScore / Credit Applications' ssn_last4), and a
        // real Employee -> Manager -> Executive approval-hierarchy engine off
        // core/bot_tasks.py's own infer_tier(). This branch is
        // Administration-only.
        <RolesPermissionsBoard theme={theme} />
      ) : dispatchKey === "Administration:vendors" ? (
        // Administration Control Center rebuild, continued -- Vendors. Real
        // Vendor entities (core/vendor_management.py): contact info, contract
        // term, monthly cost, category. ADMIN/OPERATIONS-only. This branch is
        // Administration-only.
        <VendorManagementBoard theme={theme} />
      ) : dispatchKey === "Administration:organizations" ? (
        // Administration Control Center rebuild, continued -- Organizations +
        // System Configuration, combined into one real singleton settings
        // record (core/system_config.py): dealership profile, locations,
        // business hours, defaults, feature flags. Viewing open to any role,
        // editing ADMIN/OPERATIONS-only. This branch is Administration-only.
        <OrganizationsBoard theme={theme} />
      ) : dispatchKey === "Administration:data_management" ? (
        // Administration Control Center rebuild, continued -- Data
        // Management. Real per-entity-type CSV export + a real graph.json
        // backup/restore action (core/data_backup.py) -- restore is the
        // single most consequential real action in this whole rebuild,
        // ADMIN-only, gated behind a typed confirmation phrase in the board
        // itself. This branch is Administration-only.
        <DataManagementBoard theme={theme} />
      ) : dispatchKey === "Administration:identity_access" ? (
        // Administration Control Center rebuild, continued -- Identity &
        // Access. Real, per-employee API keys (core/api_keys.py) already
        // wired into api/app.py's _authenticate() bearer-token fallback -- a
        // generated key genuinely authenticates a request. This branch is
        // Administration-only.
        <IdentityAccessBoard theme={theme} />
      ) : dispatchKey === "Administration:audit_center" ? (
        // Administration Control Center rebuild, final slice -- Audit
        // Center. A real investigative workspace over the audit log
        // (core/audit_center.py): filtering/search, a per-actor activity
        // summary, and a real, transparent rules-based suspicious-activity
        // flag list (no ML/AI). This branch is Administration-only.
        <AuditCenterBoard theme={theme} />
      ) : dispatchKey === "Administration:governance" ? (
        // Administration Control Center rebuild, continuing (2026-07-18) --
        // Compliance & Governance, enriched. Ties core/compliance.py's
        // cited-federal-rules alert engine and core/permissions_registry.py's
        // real tier-gated cross-department ApprovalRequest hierarchy into one
        // workspace (core/governance.py), on top of the pre-existing content
        // approval queue and escalation-rules dashboard. This branch is
        // Administration-only.
        <GovernanceBoard theme={theme} />
      ) : dispatchKey === "Administration:workflow_automation" ? (
        // Administration Control Center rebuild, continuing (2026-07-18/19) --
        // Workflow Automation. A real, admin-configurable "if condition, then
        // action" rule engine (core/workflow_automation.py) evaluated
        // on-demand/on-fetch, deliberately not a third background scheduler.
        // This branch is Administration-only.
        <WorkflowAutomationBoard theme={theme} />
      ) : dispatchKey === "Administration:ai_management" ? (
        // Administration Control Center rebuild, continuing (2026-07-18/19) --
        // AI Management. A real catalog of every OpenAI-backed feature in this
        // codebase, each with a real per-feature kill switch actually wired
        // into that feature's own consumer function (core/ai_management.py),
        // plus honest in-memory call-attempt counters. This sandbox has no
        // outbound network path to the real OpenAI API, so no fabricated
        // usage/cost numbers are shown -- see the board's own disclosure
        // banner. This branch is Administration-only.
        <AiManagementBoard theme={theme} />
      ) : dispatchKey === "Administration:modules" ? (
        // Freemium Platform roadmap, Phase 5 -- the NXTDeal Foundation + paid Modules entitlement
        // board (core/entitlements.py). Switch the dealer between the full-build reference profile
        // and Tier-0 Foundation, add/level individual Modules, and set Foundation usage caps. The
        // running product actually enforces this record. This branch is Administration-only.
        <AddModulesBoard theme={theme} />
      ) : dispatchKey === "Administration:ai_spend" ? (
        // Freemium Platform roadmap, Phase 5 -- the AI Spend Governor (core/ai_spend.py) for a
        // bring-your-own-key model: provider posture + per-user monthly AI-action limits + the
        // aggregate consumption view (derived from the AI audit log). This branch is
        // Administration-only.
        <AiSpendBoard theme={theme} />
      ) : dispatchKey === "Administration:fleet" ? (
        // Agentic-bot FLEET dashboard (Pillar 4 slice 2, 2026-07-23) -- the nine
        // NXTDeal team agents, each recording its team's real observed workflows and
        // admin-activatable in draft/auto mode (auto gated by the same default-deny
        // bot.coverage.auto_mode capability as Bot Coverage). Backend: core/bot_fleet.py
        // + /bot/fleet* routes. This branch is Administration-only.
        <FleetBoard hideHeading={hideNav} theme={theme} />
      ) : dispatchKey === "Administration:ai_workforce" ? (
        // Customer-facing AI WORKFORCE dashboard (Connect slice 6, 2026-07-24) -- the
        // eight AI workers (Receptionist/BDC/Sales/Service/Marketing/Finance/Collections/
        // Operator), each handling inbound touches across phone/SMS/email/chat and working
        // an outbound queue, admin-activatable in draft/assisted/autonomous mode (autonomous
        // gated by the AI kill switch + default-deny ai.worker.autonomous capability).
        // Backend: core/ai_worker.py + /workforce* routes. This branch is Administration-only.
        <AiWorkforceBoard hideHeading={hideNav} theme={theme} />
      ) : dispatchKey === "Administration:connect" ? (
        // NXTDeal CONNECT dashboard (Connect slice 6b, 2026-07-24) -- the unified
        // customer-engagement surface: one inbox across every channel, a per-customer
        // timeline (communications + booked appointments), and analytics splitting
        // AI-handled from human-handled with rules-based sentiment/score on every channel.
        // Read-only. Backend: core/connect.py + /connect/* routes. Administration-only.
        <ConnectBoard hideHeading={hideNav} theme={theme} />
      ) : department === "Marketplace" ? (
        // NXTDeal Marketplace (2026-07-24) -- a certified catalog of apps, integrations, and
        // connectors a dealer installs with one click while NXTDeal stays the system of record.
        // Five views (browse/installed/oem/phase2/partners) off the Marketplace department's menu
        // items; backend core/marketplace.py via /marketplace. Install/uninstall is ADMIN.
        <MarketplaceBoard hideHeading={hideNav} theme={theme} view={itemKey as MarketplaceView} />
      ) : dispatchKey === "Administration:digital_retail" ? (
        // Digital Retail KPI dashboard (DR-8, 2026-07-24) -- how the self-service purchase
        // journey performs: digital deals/closings/gross, AI Workforce performance, and the
        // verification->deal->finance->contracting->delivery drop-off funnel. Read-only roll-up
        // over the DR-1..7 records. Backend: core/digital_retail_analytics.py + the
        // /digital-retail/dashboard route. Administration-only.
        <DigitalRetailBoard hideHeading={hideNav} theme={theme} />
      ) : dispatchKey === "Readiness:business_health" ? (
        // Readiness reframe -- Business Health (2026-07-18), the first slice of
        // Sam's "Enterprise Readiness & Intelligence" reframe: an executive layer
        // above every production department, distinct from Data Health's data-
        // confidence question. core/business_health.py composes each department's
        // own already-real KPI engines -- every figure carries a visible
        // real/heuristic/simulated/gap badge, no fabricated blended score. Open to
        // every real role.
        <BusinessHealthBoard theme={theme} />
      ) : dispatchKey === "Readiness:exceptions" ? (
        // Readiness reframe -- Exceptions, enriched (2026-07-18) into the real
        // Enterprise Risk Center Sam separately named as a capstone feature --
        // built once, not twice (core/enterprise_risk_center.py). Composes 9
        // already-real signals plus one genuinely new per-deal check
        // (negative_gross_deals) into Critical/Financial/Operational categories,
        // each with a real, computed Low/Medium/High/Critical severity and a
        // reference to where it's resolved. Open to every real role.
        <EnterpriseRiskCenterBoard theme={theme} />
      ) : dispatchKey === "Readiness:recommendations" ? (
        // Readiness reframe -- Recommendations (2026-07-19), item #8 of Sam's
        // 10-item structure: "This is where AI becomes truly valuable." A real,
        // transparent 12-rule engine (core/readiness_recommendations.py) across
        // Sales/Service/Finance/Inventory/Marketing, each recommendation tracing
        // to a real condition crossing a real threshold -- same standing
        // convention core/network_audit.py established (a rules engine over
        // real data, never a fabricated LLM narrative). Open to every real role.
        <ReadinessRecommendationsBoard theme={theme} />
      ) : dispatchKey === "Readiness:overview" ? (
        // Readiness reframe -- Overview, REBUILT (2026-07-19) into the real
        // Enterprise Readiness Dashboard, and, confirmed the same real
        // feature before building anything, ALSO the answer to Sam's
        // separately-named "Readiness Heatmap" capstone ("show every
        // department % with drill-down capability") -- built once, not
        // twice (core/readiness_overview.py). A real color-coded heatmap
        // across the 5 departments core/prediction.py actually covers
        // (click a cell to drill into BusinessHealthBoard's own real
        // per-department detail), Today's Risks reused verbatim from the
        // Enterprise Risk Center, and a real rules-based Executive Summary
        // with an optional isolated-OpenAI phrasing polish that can never
        // invent a fact. Open to every real role.
        <ReadinessOverviewBoard theme={theme} hideAssistant={hideAssistant} />
      ) : dispatchKey === "Readiness:data_health" ? (
        // Readiness reframe -- Data Health, GREATLY EXPANDED (2026-07-19) --
        // Sam: "This is what the current screen appears focused on. I'd keep
        // it but greatly expand it." core/data_health.py composes 4 new real
        // sections (Integration Monitoring, Data Completeness, real
        // duplicate-customer/duplicate-vehicle detection + real
        // Inventory-Mismatch reuse for Data Accuracy, and Data Freshness)
        // on top of the pre-existing Connected Systems/Historical Coverage
        // view. Pricing Discrepancies is an honest, explained gap -- see the
        // board's own note. ADMIN/OPERATIONS-only.
        <DataHealthBoard theme={theme} />
      ) : dispatchKey === "Readiness:readiness" ? (
        // Readiness reframe -- Performance Readiness (2026-07-19), item #4 of
        // Sam's 10-item proposed structure: "This is where scores become
        // useful." Goal Tracking against real pace -- core/
        // performance_readiness.py composes a real ADMIN/OPERATIONS-settable
        // monthly target (core/system_config.py's department_goals) against
        // a real current-month linear pace projection and core/
        // prediction.py's own real ledger forecast. An unset goal or missing
        // pace/forecast data renders honestly, never a fabricated 100%. The
        // pre-existing confidence-score content (data trustworthiness, a
        // genuinely different concept) is shown below it. Open to every
        // real role for viewing; goal-setting itself is ADMIN/OPERATIONS-only,
        // enforced by the backend.
        <PerformanceReadinessBoard theme={theme} />
      ) : dispatchKey === "Readiness:forecasts" ? (
        // Readiness reframe -- Forecasts (2026-07-19), item #5 of Sam's 10-item
        // proposed structure: "This should become a predictive analytics engine."
        // core/readiness_forecasts.py composes real Sales/Service/Inventory/Finance
        // forecast dimensions -- ledger-based where core/prediction.py already
        // covers the metric, a real simple linear run-rate projection where it
        // doesn't (clearly labeled, never oversold), and a real transparent rules
        // engine for Inventory's Units Likely To Sell/Age. Also closes the
        // separately-named "Readiness Timeline" capstone (Last 7/30/90 Days, Year
        // To Date) via a Forecasts/Timeline tab toggle, reusing core/prediction.py's
        // new historical_trend() rather than a second data source. Open to every
        // real role; Collections/Portfolio Performance keep their own narrower
        // ADMIN/OPERATIONS/FINANCE gate and degrade gracefully.
        <ReadinessForecastsBoard theme={theme} />
      ) : dispatchKey === "Readiness:simulations" ? (
        // Readiness reframe -- Scenarios / What-If Modeling (2026-07-19), item
        // #6 of Sam's 10-item proposed structure: "one of NXTDeal' most
        // powerful features." core/readiness_scenarios.py composes real,
        // transparent formula-based projections (Marketing/Lead Volume,
        // Inventory Pricing, Staffing, Finance Portfolio) over this
        // dealership's own real current-data ratios -- never an invented
        // multiplier. Open to every real role; Finance Portfolio's
        // underlying data stays gated at its own narrower ADMIN/OPERATIONS/
        // FINANCE layer and degrades gracefully.
        <ReadinessScenariosBoard theme={theme} />
      ) : dispatchKey === "Readiness:strategic_planning" ? (
        // Readiness reframe -- Strategic Planning (2026-07-19), item #9 of
        // Sam's 10-item proposed structure: "A completely new area." Real
        // Quarterly Planning (Objectives/Goals/Budgets), Department
        // Planning, and Initiative Tracking (core/strategic_planning.py) --
        // status computed live, real for Sales/Service/Marketing off actual
        // ledger pace generalized to a quarter window, an honest manual
        // self-report for every other department; a quarterly objective can
        // be explicitly, one-way pushed into Performance Readiness's own
        // monthly goal. Open to every real role for viewing; creating/
        // editing is ADMIN/OPERATIONS-only, enforced by the backend.
        <StrategicPlanningBoard theme={theme} />
      ) : dispatchKey === "Network:opportunities" ? (
        // Intelligence Network reframe, slice 1 -- Opportunities, enriched
        // with the same real, dollar-denominated department totals + grand
        // total + largest-opportunities list Overview shows (core/
        // network_opportunity_value.py), above the existing 5-bucket
        // recommendation grouping (unchanged). A full replacement of the
        // generic JSON-dump default, not an "ABOVE" injection, since
        // "opportunities" isn't caught by any earlier itemKey check.
        <NetworkOpportunitiesBoard theme={theme} />
      ) : dispatchKey === "Network:gap_analysis" ? (
        // Intelligence Network reframe, slice 3 -- Gap Analysis, enriched with
        // Root Cause Analysis + Revenue Impact (core/network_root_cause.py +
        // core/network_opportunity_value.py's dollar-conversion formulas
        // reused verbatim). Also the slice that FIXED a previously-flagged
        // bug: direction/severity now respect each KPI's real higher-is-
        // better/lower-is-better semantic (core/network_benchmark.py's
        // gap_direction()) -- the bhph department's 3 lower-is-better rate
        // KPIs are no longer mislabeled as an opportunity when this dealer is
        // already ahead of peers on them. A full replacement of the generic
        // JSON-dump default, not an "ABOVE" injection, same precedent as
        // Opportunities above.
        <NetworkGapAnalysisBoard theme={theme} />
      ) : dispatchKey === "Network:trends" ? (
        // Intelligence Network reframe, slice 4 -- Trends, enriched with a real
        // bhph day-over-day delta (never covered before this slice) plus a real
        // 90-day-or-however-many-days-were-actually-recorded snapshot history
        // view (core/network_trends.py). A full replacement of the generic
        // JSON-dump default, same precedent as Gap Analysis/Opportunities above.
        <NetworkTrendsBoard theme={theme} />
      ) : dispatchKey === "Network:forecasts" ? (
        // Intelligence Network reframe, slice 4 -- Forecasts, a brand-new Top
        // Menu item: a real linear (OLS) projection of this dealer's own
        // recorded trend, compared against the static SIMULATED peer average
        // to estimate whether a real gap is closing/widening/holding.
        // Deliberately NOT a competitive forecast -- peers have no real trend
        // of their own to project (core/network_trends.py).
        <NetworkForecastsBoard theme={theme} />
      ) : dispatchKey === "Network:playbooks" ? (
        // Intelligence Network reframe, slice 5 -- Playbooks, a real curated
        // best-practice library (core/network_playbooks.py) replacing the old
        // recommendation-feed-only analog. Every entry references a real
        // NXTDeal screen/workflow, is live-checked against a real
        // core/network_root_cause.py diagnostic, and carries a real
        // Automation Score against core/workflow_automation.py's rule engine.
        <NetworkPlaybooksBoard theme={theme} />
      ) : dispatchKey === "Network:ai_advisors" ? (
        // Intelligence Network reframe, slice 6 -- AI Advisors, a new Top Menu
        // item: 5 real, department-specific Q&A advisors (Sales/Service/
        // Parts/F&I/BHPH). A dedicated POST route (core/network_advisors.py),
        // not the generic /menu/data GET path, since it needs a question
        // body -- same "bespoke board bypasses /menu/data" precedent as
        // every other Network slice this reframe has established.
        <NetworkAdvisorsBoard theme={theme} />
      ) : dispatchKey === "Administration:users" ? (
        // Administration Control Center rebuild, closing slice (2026-07-19) --
        // Users, enriched. A real per-employee identity + access + security
        // composite (permission overrides, API keys, lockout state) composed
        // from three modules this rebuild already built, plus a real
        // Permission/Role Change Requests queue off the Roles & Permissions
        // approval-hierarchy engine. Every mutating action here reuses the
        // already-real client each individual item shipped with -- nothing
        // is duplicated. This branch is Administration-only.
        <AdminUsersBoard theme={theme} onDraftOpenChange={onDraftOpenChange} onSavingChange={onSavingChange} />
      ) : dispatchKey === "Administration:team_management" ? (
        // Bumper-parity: create a user (Employee + login + role) in one action, assign
        // roles including the new BDC role. ADMIN-only.
        <UserManagementBoard theme={theme} onDraftOpenChange={onDraftOpenChange} onSavingChange={onSavingChange} />
      ) : dispatchKey === "Administration:lead_routing" ? (
        // Bumper-parity: named lead-distribution rules (Leads Configuration).
        <LeadRoutingBoard theme={theme} />
      ) : dispatchKey === "Administration:connections" ? (
        // Track B: external provider integrations — live/simulated status + credential store.
        <ConnectionsBoard theme={theme} />
      ) : (
      <div className="flex-1 overflow-y-auto p-4">
        {/* Theme selector + print, session-60 follow-up. */}
        <div className="flex items-center justify-between gap-3 mb-3">
          {!hideNav && <div className={tc(theme, "flex items-center gap-1 text-xs rounded-lg border border-zinc-800 p-0.5", "flex items-center gap-1 text-xs rounded-lg border border-zinc-300 p-0.5")}>
            <WorkButton type="submit"
              onClick={() => setTheme("dark")}
              className={
                theme === "dark"
                  ? "px-2.5 py-1 rounded-md bg-zinc-700 text-white"
                  : tc(theme, "px-2.5 py-1 rounded-md text-zinc-500 hover:text-white transition", "px-2.5 py-1 rounded-md text-zinc-500 hover:text-black transition")
              }
              title="Dark (default)"
            >
              ● Dark
            </WorkButton>
            <WorkButton type="submit"
              onClick={() => setTheme("light")}
              className={
                theme === "light"
                  ? "px-2.5 py-1 rounded-md bg-zinc-200 text-black"
                  : tc(theme, "px-2.5 py-1 rounded-md text-zinc-500 hover:text-white transition", "px-2.5 py-1 rounded-md text-zinc-500 hover:text-black transition")
              }
              title="Light — a more traditional list view"
            >
              ○ Light
            </WorkButton>
          </div>}

          <div className={tc(theme, "flex items-center gap-0.5 text-xs rounded-lg border border-zinc-800 p-0.5", "flex items-center gap-0.5 text-xs rounded-lg border border-zinc-300 p-0.5")}>
            <WorkButton type="submit"
              onClick={() => setZoom((z) => Math.max(50, z - 10))}
              disabled={zoom <= 50}
              title="Zoom out"
              className={tc(
                theme,
                "w-6 h-6 flex items-center justify-center rounded text-zinc-400 hover:text-white hover:bg-zinc-800 transition disabled:opacity-30",
                "w-6 h-6 flex items-center justify-center rounded text-zinc-600 hover:text-black hover:bg-zinc-200 transition disabled:opacity-30"
              )}
            >
              −
            </WorkButton>
            <WorkButton type="submit"
              onClick={() => setZoom(100)}
              title="Reset zoom"
              className={tc(
                theme,
                "px-1.5 h-6 flex items-center justify-center rounded text-zinc-400 hover:text-white hover:bg-zinc-800 transition text-xs tabular-nums",
                "px-1.5 h-6 flex items-center justify-center rounded text-zinc-600 hover:text-black hover:bg-zinc-200 transition text-xs tabular-nums"
              )}
            >
              {zoom}%
            </WorkButton>
            <WorkButton type="submit"
              onClick={() => setZoom((z) => Math.min(200, z + 10))}
              disabled={zoom >= 200}
              title="Zoom in"
              className={tc(
                theme,
                "w-6 h-6 flex items-center justify-center rounded text-zinc-400 hover:text-white hover:bg-zinc-800 transition disabled:opacity-30",
                "w-6 h-6 flex items-center justify-center rounded text-zinc-600 hover:text-black hover:bg-zinc-200 transition disabled:opacity-30"
              )}
            >
              +
            </WorkButton>
          </div>

          <WorkButton type="submit"
            onClick={() => setShowPrintSettings(true)}
            disabled={loading || !data}
            className={tc(
              theme,
              "text-xs px-3 py-1.5 rounded-lg border border-zinc-700 text-zinc-300 hover:text-white hover:border-zinc-500 transition disabled:opacity-40",
              "text-xs px-3 py-1.5 rounded-lg border border-zinc-300 text-zinc-700 hover:text-black hover:border-zinc-500 transition disabled:opacity-40"
            )}
          >
            🖨 Print
          </WorkButton>
        </div>

        <div style={zoom !== 100 ? { transform: `scale(${zoom / 100})`, transformOrigin: "top left", width: `${10000 / zoom}%` } : undefined}>
          {/* Administration Control Center rebuild, continued -- Security expansion.
              Real per-employee account-lockout lookup/unlock + IP allowlist management
              (core/auth_api.py), layered ABOVE the existing generic /menu/data render
              (which already carries the roster-wide summary from
              core/administration_menu.py's security()) rather than replacing it. */}
          {department === "Administration" && itemKey === "security" && (
            <SecurityAdminPanel theme={theme} />
          )}
          {!hideNav && current && <p className={tc(theme, "text-xs text-zinc-500 mb-3", "text-xs text-zinc-600 mb-3")}>{current.description}</p>}

          {isQueryCapable && (
            <WorkField label="Query"><WorkInput
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={itemKey === "vehicles" ? "Search VIN, stock number, VEH-00001…" : "Search documents…"}
              className={tc(
                theme,
                "w-full h-9 px-3 mb-4 text-sm rounded-lg bg-zinc-900 border border-zinc-800 focus:outline-none focus:border-zinc-600",
                "w-full h-9 px-3 mb-4 text-sm rounded-lg bg-white border border-zinc-300 text-zinc-900 focus:outline-none focus:border-zinc-500"
              )}
            /></WorkField>
          )}

          {loading ? (
            <div className={tc(theme, "text-sm text-zinc-600", "text-sm text-zinc-500")}>Loading…</div>
          ) : (
            <JsonValue
              value={data}
              theme={theme}
              path={[]}
              dragCtx={itemKey === "reporting" ? { department, itemKey } : undefined}
            />
          )}
        </div>
      </div>
      )}
      </div>

      {showPrintSettings && (
        <WorkOverlay
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 print:hidden"
          onClick={() => setShowPrintSettings(false)}
        >
          <div
            className="bg-brand-charcoal border border-black/30 rounded-xl p-5 w-80 text-white"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="text-sm font-brand font-medium mb-3">Print Settings</div>

            <label className="block text-xs text-zinc-500 mb-1">Rows per page</label>
            <WorkInput aria-label="Rows per page"
              type="number"
              min={1}
              value={rowsPerPage}
              onChange={(e) => setRowsPerPage(Math.max(1, Number(e.target.value) || 1))}
              className="w-full h-9 px-2 mb-3 text-sm rounded bg-zinc-950 border border-zinc-800"
            />

            <label className="block text-xs text-zinc-500 mb-1">Starting page number</label>
            <WorkInput aria-label="Rows per page"
              type="number"
              min={1}
              value={startPage}
              onChange={(e) => setStartPage(Math.max(1, Number(e.target.value) || 1))}
              className="w-full h-9 px-2 mb-3 text-sm rounded bg-zinc-950 border border-zinc-800"
            />

            <div className="text-xs text-zinc-500 mb-4">
              {query ? `Filter applied: "${query}" — ` : "No filter applied — "}
              {printPageCount} page{printPageCount === 1 ? "" : "s"} at this page size.
            </div>

            <div className="flex justify-end gap-2">
              <WorkButton type="submit"
                onClick={() => setShowPrintSettings(false)}
                className="text-xs px-3 py-1.5 rounded-lg border border-zinc-700 text-zinc-400 hover:text-white transition"
              >
                Cancel
              </WorkButton>
              <WorkButton type="submit"
                onClick={handlePrint}
                className="text-xs px-3 py-1.5 rounded-lg bg-zinc-200 text-black font-medium hover:bg-white transition"
              >
                Print
              </WorkButton>
            </div>
          </div>
        </WorkOverlay>
      )}

      {/* Print-only region -- hidden on screen (`hidden print:block`), and the
          injected stylesheet below hides everything else on the page while printing
          so only this renders. Standard "print this element only" technique. */}
      <div className="hidden print:block dealeros-print-region">
        <PrintDocument
          department={department}
          itemLabel={current?.label ?? itemKey}
          query={query}
          data={data}
          rowsPerPage={rowsPerPage}
          startPage={startPage}
        />
      </div>

      <style>{`
        @media print {
          body * { visibility: hidden; }
          .dealeros-print-region, .dealeros-print-region * { visibility: visible; }
          .dealeros-print-region { position: absolute; left: 0; top: 0; width: 100%; }
          .print-page { break-after: page; padding: 32px; color: #000; background: #fff; }
          .print-page:last-child { break-after: auto; }
        }
      `}</style>
    </div>
  );
}

export function MenuDashPanel({
  department,
  itemKey,
  onSelectItem,
  onClose,
  onPopOut,
  showNav = false,
  initialQuery = "",
}: {
  department: string;
  itemKey: string;
  onSelectItem: (key: string) => void;
  onClose: () => void;
  onPopOut: () => void;
  // Session 74 (gear icon settings menu): true when this Dash was opened standalone,
  // from a page that has no DepartmentMenuBar of its own for `department` (e.g.
  // opening Administration's Top Menu from /workspace via the gear icon) -- in that
  // case MenuDashBody needs to render its own item-switcher nav rather than relying on
  // a page-level DepartmentMenuBar that isn't there. Same-page usage (a page opening
  // one of its own department's items) leaves this false, unchanged from session 60.
  showNav?: boolean;
  initialQuery?: string;
}) {
  return (
    <div className="flex-1 min-w-0 flex flex-col bg-brand-ink border-x border-zinc-800">
      <div className="relative flex items-center justify-between pl-5 pr-4 py-3 border-b border-zinc-800 shrink-0 bg-brand-charcoal overflow-hidden print:hidden">
        <span className="absolute left-0 top-0 bottom-0 w-1.5 bg-brand-teal" />
        <div className="flex items-center gap-2 min-w-0">
          <span className="font-brand font-bold uppercase tracking-wide truncate">{department}</span>
          <span className="text-xs text-zinc-500 shrink-0 font-brand uppercase tracking-wider">— Top Menu</span>
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

      {/* hideNav: components/DepartmentMenuBar.tsx already provides this navigation at
          the top of the page for the in-page usage -- no need to duplicate it here.
          Standalone (gear-icon-opened) usage passes showNav so MenuDashBody renders
          its own item-switcher instead. */}
      <MenuDashBody department={department} itemKey={itemKey} onSelectItem={onSelectItem} hideNav={!showNav} initialQuery={initialQuery} />
    </div>
  );
}

// The Workspace column's collapsed edge tab (session 60; the chat column's equivalent
// tab was removed in the same-session follow-up -- Sam: "lets just drop the chat
// completely instead of squishing it," so chat isn't rendered at all while a Dash is
// open, not even as a thin tab). Reopening this tab closes the Dash, restoring the
// Workspace column (and, since chat was never touched, it's already showing).
export function WorkspaceCollapsedTab({
  onReopen,
  onDrop,
  alert = false,
}: {
  onReopen: () => void;
  // Sam: "select the section and drag and drop it into the workspace where you can
  // then edit it into the chart/graph you want to see before pinning" -- dropping a
  // chartable section (dragged from MenuDashPanel's ObjectListView) here reopens the
  // Workspace column with the visualization editor already loaded, instead of its
  // usual workflow-buttons content. Optional so the pop-out/other usages of this tab
  // don't need to wire drop handling if they don't support it.
  onDrop?: (payload: VisualizationDropPayload) => void;
  // 2026-07-19 (Sam: "add alert icons ... to let people know that things are happening
  // on the closed areas") -- an optional red dot, same convention as the new sibling
  // components/CollapsedColumnTab.tsx. Defaults false so every existing call site
  // (this component predates the ask) is unaffected.
  alert?: boolean;
}) {
  const [dragOver, setDragOver] = useState(false);

  function handleDragOver(event: DragEvent<HTMLButtonElement>) {
    if (!onDrop) return;
    if (!event.dataTransfer.types.includes(VISUALIZATION_DRAG_TYPE)) return;

    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
    setDragOver(true);
  }

  function handleDrop(event: DragEvent<HTMLButtonElement>) {
    if (!onDrop) return;

    const raw = event.dataTransfer.getData(VISUALIZATION_DRAG_TYPE);
    setDragOver(false);
    if (!raw) return;

    event.preventDefault();

    try {
      const payload = JSON.parse(raw) as VisualizationDropPayload;
      onDrop(payload);
    } catch {
      // Malformed drag payload -- ignore rather than crash the drop handler.
    }
  }

  return (
    <button
      onClick={onReopen}
      onDragOver={handleDragOver}
      onDragLeave={() => setDragOver(false)}
      onDrop={handleDrop}
      title={onDrop ? "Reopen Workspace -- or drop a section here to visualize it" : "Reopen Workspace"}
      className={
        dragOver
          ? "relative w-10 shrink-0 flex flex-col items-center justify-center gap-2 border-l-2 border-zinc-400 bg-zinc-800 transition text-white print:hidden"
          : "relative w-10 shrink-0 flex flex-col items-center justify-center gap-2 border-l border-zinc-900 bg-zinc-950 hover:bg-zinc-900 transition text-zinc-500 hover:text-white print:hidden"
      }
    >
      {alert && (
        <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-red-500 ring-2 ring-zinc-950 animate-pulse" />
      )}
      <span className="text-base leading-none">{dragOver ? "⬇" : "▤"}</span>
      <span
        className="text-xs uppercase tracking-wider"
        style={{ writingMode: "vertical-rl" }}
      >
        Workspace
      </span>
    </button>
  );
}
