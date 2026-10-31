"use client";
import { WorkButton, WorkInput, WorkTextarea, WorkSelect } from "./WorkspaceUi";
import {CollectionPagination} from "./CollectionPagination";
import {RecordTable} from "./RecordTable";
import { AudienceMembers } from "./bdc/AudienceMembers";
import { WorkField } from "./WorkField";

// Marketing's "CRM" Top Menu item (session 79, reworked session 82). Sam: "id like to
// combine campaigns, audiences, and opportunities into one Hubspot style workflow dash
// called CRM." A HubSpot-style workspace with 4 tabs: Pipeline (a real, draggable Lead
// kanban board), Lists (session 82 rework -- real, named, curatable
// core/marketing_lists.py MarketingLists you click into for a paginated/filterable
// member browser, with the pre-existing Audience segments demoted to a "Quick-Start
// Segments" section that can now also be saved as a real List), Campaigns (session 82
// rework -- click a campaign to open a full editable detail view: name/notes, real
// stats, and the same paginated/filterable member browser), and Opportunities (session
// 82 rework -- the dollar-value pools gain real actions: "Save as List" for any
// campaign-type-backed pool, and "Assign to Sales →" for the Lead-typed Conquest pool
// specifically, closing the actual Marketing -> Sales handoff loop). Mounted by
// components/MenuDashPanel.tsx in place of the generic JSON tree view, same special-
// casing as the Reporting/Overview boards -- and, since MenuDashPanel's own pop-out
// button already reopens this whole Dash in its own OS window, every tab/detail view
// built here is automatically "pop-out capable" with no extra plumbing.
import { PRODUCT_ACCENT_COLORS } from "@/lib/productTheme";
import { useEffect, useMemo, useRef, useState, type DragEvent } from "react";
import {
  fetchCrmData,
  advanceLeadPipeline,
  previewCrmAudience,
  createCrmCampaign,
  activateCrmCampaign,
  completeCrmCampaign,
  cancelCrmCampaign,
  type CrmData,
  type CampaignType,
} from "@/lib/marketingCrm";
import {
  createList,
  listAllLists,
  buildListFromPool,
  getListMembers,
  updateList,
  archiveList,
  updateCampaign,
  getCampaignDetail,
  listSalesEmployees,
  saveOpportunityPoolAsList,
  assignOpportunityToSales,
  type MarketingList,
  type MemberPage,
  type CampaignDetail,
  type SalesEmployee,
} from "@/lib/marketingLists";
import { listAllTemplates, type EmailTemplate } from "@/lib/emailSms";
import { getSession } from "@/lib/auth";
import { EntityHoverLink } from "@/components/EntityHoverLink";
import { VISUALIZATION_DRAG_TYPE, type VisualizationDropPayload } from "@/lib/useVisualizationWorkspace";
import { searchCrm, type CrmSearchResult } from "@/lib/marketingCrm";
import { Customer360Panel } from "@/components/Customer360Panel";
import {
  getAudienceFields,
  listAudiencePresets,
  previewAudiencePreset,
  previewAudienceConditions,
  listSavedAudiences,
  createSmartAudience,
  deleteSmartAudience,
  evaluateSmartAudience,
  type AudienceField,
  type AudiencePreset,
  type AudienceCondition,
  type AudienceMember,
  type SavedAudience,
} from "@/lib/smartAudiences";
import { getLeadScoringLeaderboard, type Leaderboard } from "@/lib/leadScoring";

type Theme = "dark" | "light";
type PageSize = 25 | 50 | 100;
type EntityFilter = "" | "Customer" | "Lead";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const STATE_LABELS: Record<string, string> = {
  NEW: "New",
  CONTACTED: "Contacted",
  APPOINTMENT_SET: "Appointment Set",
  VISITED: "Visited",
  PROPOSAL: "Proposal",
  NEGOTIATION: "Negotiation",
  SOLD: "Sold",
  LOST: "Lost",
};

const STATE_COLORS: Record<string, string> = {
  NEW: "#5c5c66",
  CONTACTED: "#2B68AB",
  APPOINTMENT_SET: "#3FBCC4",
  VISITED: "#3FBCC4",
  PROPOSAL: "#FBCF09",
  NEGOTIATION: "#FBCF09",
  SOLD: "#22c55e",
  LOST: "#EE3C25",
};

// Which real CAMPAIGN_TYPES key each real audience pool can launch a campaign against
// -- equity mining/previous buyers/unsold leads have no matching campaign_type builder
// on the backend (core/campaigns.py's CAMPAIGN_TYPES), so those pools honestly have no
// "Start Campaign"/"Save as List" action.
const POOL_TO_CAMPAIGN_TYPE: Record<string, { campaign_type: string; params: Record<string, unknown> }> = {
  lease_maturity: { campaign_type: "finance_renewal", params: { months_to_maturity: 6 } },
  service_conquest: { campaign_type: "retention", params: { months_since_service: 0 } },
  service_defection: { campaign_type: "retention", params: { months_since_service: 12 } },
  upgrade_opportunities: { campaign_type: "accessory_accelerator", params: { days_since_sale: 30 } },
};

// Same mapping for the Opportunities tab's dollar-value pools (core/marketing_menu.py's
// _opportunities() -- different pool keys than _audiences() above, deliberately kept
// separate since they're two distinct backend functions). "conquest" is the only
// Lead-typed pool (core/campaigns.py's audience_entity_type()) -- the only one eligible
// for "Assign to Sales" rather than "Save as List".
const OPPORTUNITY_TO_CAMPAIGN_TYPE: Record<string, { campaign_type: string; params: Record<string, unknown>; leadTyped?: boolean }> = {
  conquest_opportunities: { campaign_type: "inventory_ads", params: {}, leadTyped: true },
  lease_opportunities: { campaign_type: "finance_renewal", params: { months_to_maturity: 6 } },
  service_opportunities: { campaign_type: "retention", params: { months_since_service: 6 } },
  retention_opportunities: { campaign_type: "retention", params: { months_since_service: 12 } },
};

const DRAG_TYPE = "application/x-dealeros-crm-lead";

// Same 4-color brand order as components/DepartmentWorkflowButtons.tsx's
// RIBBON_COLORS / components/BrandAngles.tsx's BRAND_RIBBON_ORDER -- cycled across the
// KPI strip so this board's summary cards carry the same angled accent language as
// every other dash rather than a plain flat card.
const KPI_RIBBON = PRODUCT_ACCENT_COLORS;

function fmtMoney(n: number | undefined | null): string {
  if (n === undefined || n === null) return "$0";
  return `$${n.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

function fmtDate(s: string | undefined | null): string {
  if (!s) return "—";
  try {
    return new Date(s).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
  } catch {
    return s;
  }
}

function AudienceChips({ theme, items }: { theme: Theme; items?: Array<{ id: string; entity_type: string; name: string }> }) {
  if (!items || items.length === 0) {
    return <div className={tc(theme, "text-xs text-zinc-600", "text-xs text-zinc-500")}>No matches yet.</div>;
  }
  return (
    <div className="flex flex-wrap gap-1">
      {items.map((m) => (
        <EntityHoverLink
          key={m.id}
          id={m.id}
          className={tc(
            theme,
            "text-xs px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-200 hover:bg-zinc-700 transition",
            "text-xs px-1.5 py-0.5 rounded bg-zinc-100 text-zinc-800 hover:bg-zinc-200 transition"
          )}
        />
      ))}
    </div>
  );
}

// Shared 25/50/100 page-size control -- Sam: "a page up and down also adjustable by
// 25, 50, 100. It should really default to this."
function PageSizeSelector({ theme, value, onChange }: { theme: Theme; value: PageSize; onChange: (v: PageSize) => void }) {
  return (
    <div className="flex items-center gap-1">
      <span className={tc(theme, "text-xs text-zinc-500", "text-xs text-zinc-600")}>Per page</span>
      {[25, 50, 100].map((n) => (
        <WorkButton type="submit"
          key={n}
          onClick={() => onChange(n as PageSize)}
          className={
            value === n
              ? "text-xs px-1.5 py-0.5 rounded bg-brand-teal text-black font-semibold"
              : tc(
                  theme,
                  "text-xs px-1.5 py-0.5 rounded border border-zinc-700 text-zinc-400 hover:text-white transition",
                  "text-xs px-1.5 py-0.5 rounded border border-zinc-300 text-zinc-600 hover:text-black transition"
                )
          }
        >
          {n}
        </WorkButton>
      ))}
    </div>
  );
}

function EntityFilterTabs({ theme, value, onChange }: { theme: Theme; value: EntityFilter; onChange: (v: EntityFilter) => void }) {
  const opts: Array<{ key: EntityFilter; label: string }> = [
    { key: "", label: "All" },
    { key: "Customer", label: "Customers" },
    { key: "Lead", label: "Leads" },
  ];
  return (
    <div className="flex items-center gap-1">
      {opts.map((o) => (
        <WorkButton type="submit"
          key={o.key || "all"}
          onClick={() => onChange(o.key)}
          className={
            value === o.key
              ? "text-xs px-2 py-0.5 rounded-full bg-brand-blue text-white font-semibold"
              : tc(
                  theme,
                  "text-xs px-2 py-0.5 rounded-full border border-zinc-700 text-zinc-400 hover:text-white transition",
                  "text-xs px-2 py-0.5 rounded-full border border-zinc-300 text-zinc-600 hover:text-black transition"
                )
          }
        >
          {o.label}
        </WorkButton>
      ))}
    </div>
  );
}

function MemberTable({ theme, page }: { theme: Theme; page: MemberPage | null }) {
  if (!page) {
    return <div className={tc(theme, "text-xs text-zinc-600 p-3", "text-xs text-zinc-500 p-3")}>Loading…</div>;
  }
  if (page.members.length === 0) {
    return <div className={tc(theme, "text-xs text-zinc-600 p-3", "text-xs text-zinc-500 p-3")}>No members match this filter.</div>;
  }
  return (
    <div className="overflow-x-auto">
      <RecordTable paginate={false} className="w-full text-xs">
        <thead>
          <tr className={tc(theme, "text-zinc-500 text-left border-b border-zinc-800", "text-zinc-600 text-left border-b border-zinc-300")}>
            <th className="py-1.5 pr-3 font-medium">Name</th>
            <th className="py-1.5 pr-3 font-medium">Type</th>
            <th className="py-1.5 pr-3 font-medium">Phone</th>
            <th className="py-1.5 pr-3 font-medium">Email</th>
            <th className="py-1.5 pr-3 font-medium">Source / Stage</th>
          </tr>
        </thead>
        <tbody>
          {page.members.map((m) => (
            <tr key={m.id} className={tc(theme, "border-b border-zinc-900 last:border-0", "border-b border-zinc-200 last:border-0")}>
              <td className="py-1.5 pr-3">
                <EntityHoverLink id={m.id} className="text-xs font-medium text-brand-teal hover:underline" />
                <span className={tc(theme, "text-xs text-zinc-300 ml-1.5", "text-xs text-zinc-700 ml-1.5")}>{m.name}</span>
              </td>
              <td className={tc(theme, "py-1.5 pr-3 text-xs text-zinc-500", "py-1.5 pr-3 text-xs text-zinc-500")}>{m.entity_type}</td>
              <td className={tc(theme, "py-1.5 pr-3 text-xs text-zinc-400", "py-1.5 pr-3 text-xs text-zinc-600")}>{m.phone ?? "—"}</td>
              <td className={tc(theme, "py-1.5 pr-3 text-xs text-zinc-400", "py-1.5 pr-3 text-xs text-zinc-600")}>{m.email ?? "—"}</td>
              <td className={tc(theme, "py-1.5 pr-3 text-xs text-zinc-400", "py-1.5 pr-3 text-xs text-zinc-600")}>
                {m.pipeline_state ?? m.source ?? "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </RecordTable>
    </div>
  );
}

function Pager({ theme, page, onPage }: { theme: Theme; page: MemberPage | null; onPage: (p: number) => void }) {
  if (!page) return null;
  return <CollectionPagination label="People" total={page.total} page={page.page-1} pageSize={page.page_size} onPageChange={p=>onPage(p+1)}/>;
}

// Reuses the exact same drag-to-Workspace mechanism components/MenuDashPanel.tsx's
// ObjectListView already established for the generic JSON tree view (session 70) --
// drop it on the collapsed Workspace tab to open the real chart editor, then pin it.
// Sam: "each module needs to be a workable process... the fields need to be
// expandable... as well as all modules in the crm" -- this is the CRM's version of
// that same "get this data out of the Dash and into a live chart" capability.
function DragToWorkspaceButton({
  theme,
  itemKey,
  fieldPath,
  sourceLabel,
  rows,
  numericColumns,
  labelColumn,
}: {
  theme: Theme;
  itemKey: string;
  fieldPath: string[];
  sourceLabel: string;
  rows: Record<string, unknown>[];
  numericColumns: string[];
  labelColumn: string;
}) {
  if (rows.length === 0 || numericColumns.length === 0) return null;

  function handleDragStart(event: DragEvent<HTMLButtonElement>) {
    const payload: VisualizationDropPayload = {
      department: "Marketing",
      itemKey,
      fieldPath,
      sourceLabel,
      rows,
      numericColumns,
      labelColumn,
    };
    event.dataTransfer.setData(VISUALIZATION_DRAG_TYPE, JSON.stringify(payload));
    event.dataTransfer.effectAllowed = "copy";
  }

  return (
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
  );
}

function PipelineTab({
  theme,
  data,
  onRefresh,
}: {
  theme: Theme;
  data: CrmData;
  onRefresh: () => void;
}) {
  const [dragOverState, setDragOverState] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  async function handleDrop(nextState: string, e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragOverState(null);
    const leadId = e.dataTransfer.getData(DRAG_TYPE);
    if (!leadId) return;

    setPending(true);
    try {
      await advanceLeadPipeline(leadId, nextState);
      onRefresh();
    } catch (err) {
      setToast(err instanceof Error ? err.message : "Couldn't move that lead.");
      setTimeout(() => setToast(null), 4000);
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="flex-1 min-h-0 flex flex-col">
      {toast && (
        <div className="mx-3 mt-2 text-xs px-3 py-2 rounded-lg bg-red-500/15 border border-red-500/40 text-red-300">
          {toast}
        </div>
      )}
      <div className="flex-1 min-h-0 overflow-x-auto overflow-y-hidden p-3">
        <div className="flex gap-3 h-full">
          {data.pipeline.states.map((state) => {
            const cards = data.pipeline.columns[state] ?? [];
            const isOver = dragOverState === state;
            return (
              <div
                key={state}
                onDragOver={(e) => {
                  e.preventDefault();
                  e.dataTransfer.dropEffect = "move";
                  setDragOverState(state);
                }}
                onDragLeave={() => setDragOverState((s) => (s === state ? null : s))}
                onDrop={(e) => handleDrop(state, e)}
                className={
                  isOver
                    ? "w-64 shrink-0 flex flex-col rounded-lg border-2 border-brand-teal bg-brand-teal/5 overflow-hidden"
                    : tc(
                        theme,
                        "w-64 shrink-0 flex flex-col rounded-lg border border-zinc-800 bg-brand-charcoal overflow-hidden",
                        "w-64 shrink-0 flex flex-col rounded-lg border border-zinc-300 bg-zinc-50 overflow-hidden"
                      )
                }
              >
                <div
                  className="px-2.5 py-2 flex items-center justify-between shrink-0"
                  style={{ borderBottom: `2px solid ${STATE_COLORS[state] ?? "#3f3f46"}` }}
                >
                  <span className={tc(theme, "text-xs font-bold uppercase tracking-wide text-zinc-300", "text-xs font-bold uppercase tracking-wide text-zinc-700")}>
                    {STATE_LABELS[state] ?? state}
                  </span>
                  <span
                    className="text-xs font-bold px-1.5 py-0.5 rounded-full"
                    style={{ backgroundColor: STATE_COLORS[state] ?? "#3f3f46", color: "#111" }}
                  >
                    {cards.length}
                  </span>
                </div>
                <div className="flex-1 overflow-y-auto p-1.5 space-y-1.5">
                  {cards.length === 0 && (
                    <div className={tc(theme, "text-xs text-zinc-700 text-center py-4", "text-xs text-zinc-400 text-center py-4")}>
                      Drop a lead here
                    </div>
                  )}
                  {cards.map((card) => (
                    <div
                      key={card.id}
                      draggable={!pending}
                      onDragStart={(e) => {
                        e.dataTransfer.setData(DRAG_TYPE, card.id);
                        e.dataTransfer.effectAllowed = "move";
                      }}
                      className={tc(
                        theme,
                        "rounded-md border border-zinc-800 bg-zinc-900 px-2 py-1.5 cursor-grab active:cursor-grabbing hover:border-zinc-600 transition",
                        "rounded-md border border-zinc-300 bg-white px-2 py-1.5 cursor-grab active:cursor-grabbing hover:border-zinc-400 transition"
                      )}
                    >
                      <div className={tc(theme, "text-xs font-semibold text-zinc-100 truncate", "text-xs font-semibold text-zinc-900 truncate")}>
                        {card.name}
                      </div>
                      <div className={tc(theme, "text-xs text-zinc-500 flex items-center justify-between mt-0.5", "text-xs text-zinc-500 flex items-center justify-between mt-0.5")}>
                        <span>{card.source ?? "—"}</span>
                        <EntityHoverLink id={card.id} className="text-xs text-brand-teal hover:underline" />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// A real List's paginated member browser -- Sam: "click on the list names and have
// them show as a list of names lets say in a list of 25 individuals, with a page up
// and down also adjustable by 25, 50, 100... you can filter by list, lead, customer."
// Takes over the full CRM panel (Sam: "the fields need to be expandable to the entire
// dash") rather than showing in a small modal -- "← Back to Lists" returns to the grid.
function ListDetailView({
  theme,
  list,
  onBack,
  onChanged,
}: {
  theme: Theme;
  list: MarketingList;
  onBack: () => void;
  onChanged: () => void;
}) {
  const session = getSession();
  const canEdit = session?.role === "ADMIN" || session?.role === "MARKETING" || list.created_by === session?.employeeId;

  const [page, setPage] = useState<MemberPage | null>(null);
  const [pageNum, setPageNum] = useState(1);
  const [pageSize, setPageSize] = useState<PageSize>(25);
  const [filter, setFilter] = useState<EntityFilter>("");
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(list.name);
  const [description, setDescription] = useState(list.description);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function load() {
    getListMembers(list.id, pageNum, pageSize, filter || null)
      .then(setPage)
      .catch((err) => setError(err instanceof Error ? err.message : "Couldn't load members."));
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [list.id, pageNum, pageSize, filter]);

  useEffect(() => {
    setPageNum(1);
  }, [pageSize, filter]);

  async function save() {
    setSaving(true);
    setError(null);
    try {
      await updateList(list.id, { name, description });
      setEditing(false);
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't save this list.");
    } finally {
      setSaving(false);
    }
  }

  async function handleArchive() {
    if (!confirm(`Archive "${list.name}"? It will be hidden from browse views but not deleted.`)) return;
    try {
      await archiveList(list.id);
      onChanged();
      onBack();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't archive this list.");
    }
  }

  return (
    <div className="work-record-content flex-1 min-h-0 flex flex-col p-5 gap-4">
      <WorkButton type="submit" onClick={onBack} className={tc(theme, "text-xs text-zinc-500 hover:text-white mb-2 self-start transition", "text-xs text-zinc-500 hover:text-black mb-2 self-start transition")}>
        ← Back to Lists
      </WorkButton>

      <div className={tc(theme, "rounded-lg border border-zinc-800 bg-brand-charcoal p-3 mb-3", "rounded-lg border border-zinc-300 bg-zinc-50 p-3 mb-3")}>
        {editing ? (
          <div className="space-y-2">
            <WorkField label="Name"><WorkInput
              value={name}
              onChange={(e) => setName(e.target.value)}
              className={tc(theme, "w-full h-8 px-2 text-sm font-semibold rounded bg-zinc-900 border border-zinc-700", "w-full h-8 px-2 text-sm font-semibold rounded bg-white border border-zinc-300")}
            /></WorkField>
            <WorkField label="Description (optional)"><WorkTextarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
              placeholder="Description (optional)"
              className={tc(theme, "w-full px-2 py-1.5 text-xs rounded bg-zinc-900 border border-zinc-700", "w-full px-2 py-1.5 text-xs rounded bg-white border border-zinc-300")}
            /></WorkField>
            <div className="flex gap-2">
              <WorkButton type="submit" onClick={save} disabled={saving} className="text-xs px-3 py-1.5 rounded-md bg-brand-teal text-black font-semibold disabled:opacity-50">
                {saving ? "Saving…" : "Save"}
              </WorkButton>
              <WorkButton type="submit" onClick={() => { setEditing(false); setName(list.name); setDescription(list.description); }} className={tc(theme, "text-xs px-3 py-1.5 rounded-md border border-zinc-700 text-zinc-300", "text-xs px-3 py-1.5 rounded-md border border-zinc-300 text-zinc-700")}>
                Cancel
              </WorkButton>
            </div>
          </div>
        ) : (
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <div className={tc(theme, "text-sm font-bold text-zinc-100", "text-sm font-bold text-zinc-900")}>{list.name}</div>
              {list.description && (
                <div className={tc(theme, "text-xs text-zinc-500 mt-0.5", "text-xs text-zinc-600 mt-0.5")}>{list.description}</div>
              )}
              <div className={tc(theme, "text-xs text-zinc-600 mt-1", "text-xs text-zinc-500 mt-1")}>
                Source: {list.source} &middot; Created {fmtDate(list.created_at)} &middot; Updated {fmtDate(list.updated_at)}
              </div>
            </div>
            {canEdit && (
              <div className="flex gap-1.5 shrink-0">
                <WorkButton type="submit" onClick={() => setEditing(true)} className={tc(theme, "text-xs px-2.5 py-1 rounded-md border border-zinc-700 text-zinc-300 hover:text-white transition", "text-xs px-2.5 py-1 rounded-md border border-zinc-300 text-zinc-700 hover:text-black transition")}>
                  Edit
                </WorkButton>
                <WorkButton type="submit" variant="danger" onClick={handleArchive} className="text-xs px-2.5 py-1 rounded-md border border-red-500/40 text-red-400 hover:bg-red-500/10 transition">
                  Archive
                </WorkButton>
              </div>
            )}
          </div>
        )}
      </div>

      {canEdit && !editing && <AudienceMembers listId={list.id} onChanged={()=>{load();onChanged()}}/>}
      {error && <div className="text-xs text-red-400 mb-2">{error}</div>}

      <div className={tc(theme, "flex-1 min-h-0 flex flex-col rounded-lg border border-zinc-800 bg-brand-charcoal overflow-hidden", "flex-1 min-h-0 flex flex-col rounded-lg border border-zinc-300 bg-zinc-50 overflow-hidden")}>
        <div className={tc(theme, "flex items-center justify-between gap-3 flex-wrap px-3 py-2 border-b border-zinc-800 shrink-0", "flex items-center justify-between gap-3 flex-wrap px-3 py-2 border-b border-zinc-300 shrink-0")}>
          <EntityFilterTabs theme={theme} value={filter} onChange={setFilter} />
          <PageSizeSelector theme={theme} value={pageSize} onChange={setPageSize} />
        </div>
        <div className="flex-1 min-h-0 overflow-y-auto px-3">
          <MemberTable theme={theme} page={page} />
        </div>
        <div className={tc(theme, "px-3 py-2 border-t border-zinc-800 shrink-0", "px-3 py-2 border-t border-zinc-300 shrink-0")}>
          <Pager theme={theme} page={page} onPage={setPageNum} />
        </div>
      </div>
    </div>
  );
}

function ListsTab({
  theme,
  data,
  onStartCampaign,
}: {
  theme: Theme;
  data: CrmData;
  onStartCampaign: (campaignType: string, params: Record<string, unknown>) => void;
}) {
  const session = getSession();
  const canCurate = session?.role === "ADMIN" || session?.role === "MARKETING";

  const [lists, setLists] = useState<MarketingList[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<MarketingList | null>(null);
  const [showNewForm, setShowNewForm] = useState(false);
  const [newName, setNewName] = useState("");
  const [creating, setCreating] = useState(false);
  const [savingKey, setSavingKey] = useState<string | null>(null);

  function refreshLists() {
    listAllLists()
      .then((ls) => {
        setLists(ls);
        setError(null);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Couldn't load lists."));
  }

  useEffect(() => {
    refreshLists();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleCreateEmpty() {
    if (!newName.trim()) return;
    setCreating(true);
    try {
      await createList(newName.trim());
      setNewName("");
      setShowNewForm(false);
      refreshLists();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't create this list.");
    } finally {
      setCreating(false);
    }
  }

  async function handleSaveSegmentAsList(key: string, label: string, campaignType: string, params: Record<string, unknown>) {
    setSavingKey(key);
    try {
      await buildListFromPool({ name: label, campaign_type: campaignType, params });
      refreshLists();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't save this segment as a list.");
    } finally {
      setSavingKey(null);
    }
  }

  if (selected) {
    return (
      <ListDetailView
        theme={theme}
        list={selected}
        onBack={() => setSelected(null)}
        onChanged={() => {
          refreshLists();
          setSelected((s) => (s ? { ...s } : s));
        }}
      />
    );
  }

  const audiences = data.audiences;
  const segmentCards: Array<{ key: string; label: string; count: number; sample?: Array<{ id: string; entity_type: string; name: string }> }> = [
    { key: "equity_mining", label: "Equity Mining", count: audiences.equity_mining.count, sample: audiences.equity_mining.sample },
    { key: "lease_maturity", label: "Lease / Finance Maturity", count: audiences.lease_maturity.count, sample: audiences.lease_maturity.sample },
    { key: "service_conquest", label: "Service Conquest", count: audiences.service_conquest.count, sample: audiences.service_conquest.sample },
    { key: "service_defection", label: "Service Defection", count: audiences.service_defection.count, sample: audiences.service_defection.sample },
    { key: "upgrade_opportunities", label: "Upgrade Opportunities", count: audiences.upgrade_opportunities.count, sample: audiences.upgrade_opportunities.sample },
    { key: "previous_buyers", label: "Previous Buyers", count: audiences.previous_buyers.count },
    { key: "unsold_leads", label: "Unsold / Lost Leads", count: audiences.unsold_leads.count },
  ];

  return (
    <div className="flex-1 min-h-0 overflow-y-auto p-3 space-y-4">
      <div>
        <div className="flex items-center justify-between mb-2">
          <span className={tc(theme, "text-xs font-bold text-zinc-200 uppercase tracking-wide", "text-xs font-bold text-zinc-800 uppercase tracking-wide")}>
            My Lists
          </span>
          {canCurate && (
            <WorkButton type="submit"
              onClick={() => setShowNewForm((s) => !s)}
              className="text-xs px-2.5 py-1 rounded-md bg-brand-teal text-black font-semibold hover:brightness-95 transition"
            >
              {showNewForm ? "Cancel" : "+ New List"}
            </WorkButton>
          )}
        </div>

        {showNewForm && (
          <div className={tc(theme, "flex items-center gap-2 mb-2 rounded-lg border border-zinc-800 bg-brand-charcoal p-5", "flex items-center gap-2 mb-2 rounded-lg border border-zinc-300 bg-zinc-50 p-5")}>
            <WorkField label="List name"><WorkInput
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="List name"
              className={tc(theme, "flex-1 h-8 px-2 text-xs rounded bg-zinc-900 border border-zinc-700", "flex-1 h-8 px-2 text-xs rounded bg-white border border-zinc-300")}
            /></WorkField>
            <WorkButton type="submit" onClick={handleCreateEmpty} disabled={creating || !newName.trim()} className="text-xs px-3 py-1.5 rounded-md bg-brand-teal text-black font-semibold disabled:opacity-50">
              {creating ? "Creating…" : "Create"}
            </WorkButton>
          </div>
        )}

        {error && <div className="text-xs text-red-400 mb-2">{error}</div>}

        {lists === null ? (
          <div className={tc(theme, "text-xs text-zinc-600", "text-xs text-zinc-500")}>Loading lists…</div>
        ) : lists.length === 0 ? (
          <div className={tc(theme, "text-xs text-zinc-600", "text-xs text-zinc-500")}>
            No lists yet — build one from a Quick-Start Segment below, or from Opportunities.
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-2.5">
            {lists.map((l) => (
              <button
                key={l.id}
                onClick={() => setSelected(l)}
                className={tc(
                  theme,
                  "text-left rounded-lg border border-zinc-800 bg-brand-charcoal p-3 hover:border-brand-teal transition",
                  "text-left rounded-lg border border-zinc-300 bg-zinc-50 p-3 hover:border-brand-blue transition"
                )}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className={tc(theme, "text-xs font-semibold text-zinc-200 truncate", "text-xs font-semibold text-zinc-800 truncate")}>{l.name}</span>
                  <span className="text-xs font-bold px-1.5 py-0.5 rounded bg-brand-blue text-white shrink-0 ml-2">
                    {(l.member_ids ?? []).length}
                  </span>
                </div>
                {l.description && (
                  <div className={tc(theme, "text-xs text-zinc-500 truncate", "text-xs text-zinc-600 truncate")}>{l.description}</div>
                )}
                <div className={tc(theme, "text-xs text-zinc-600 mt-1", "text-xs text-zinc-500 mt-1")}>{l.source}</div>
              </button>
            ))}
          </div>
        )}
      </div>

      <div>
        <div className="flex items-center justify-between mb-2">
          <div className={tc(theme, "text-xs font-bold text-zinc-200 uppercase tracking-wide", "text-xs font-bold text-zinc-800 uppercase tracking-wide")}>
            Quick-Start Segments
          </div>
          <DragToWorkspaceButton
            theme={theme}
            itemKey="crm"
            fieldPath={["audiences"]}
            sourceLabel="Segment Sizes"
            rows={segmentCards.map((c) => ({ segment: c.label, count: c.count }))}
            numericColumns={["count"]}
            labelColumn="segment"
          />
        </div>
        <div className={tc(theme, "text-xs text-zinc-600 mb-2", "text-xs text-zinc-500 mb-2")}>
          Real, live-computed audience pools. Save one as a curated List to start managing membership, or launch a campaign against it directly.
        </div>
        <div className="grid grid-cols-2 gap-3">
          {segmentCards.map((c) => {
            const launch = POOL_TO_CAMPAIGN_TYPE[c.key];
            return (
              <div
                key={c.key}
                className={tc(theme, "rounded-lg border border-zinc-800 bg-brand-charcoal p-3", "rounded-lg border border-zinc-300 bg-zinc-50 p-3")}
              >
                <div className="flex items-center justify-between mb-1.5">
                  <span className={tc(theme, "text-xs font-semibold text-zinc-200", "text-xs font-semibold text-zinc-800")}>
                    {c.label}
                  </span>
                  <span className="text-xs font-bold px-1.5 py-0.5 rounded bg-brand-blue text-white">{c.count}</span>
                </div>
                <AudienceChips theme={theme} items={c.sample} />
                <div className="flex gap-1.5 mt-2">
                  {launch && canCurate && (
                    <WorkButton type="submit"
                      onClick={() => handleSaveSegmentAsList(c.key, c.label, launch.campaign_type, launch.params)}
                      disabled={savingKey === c.key}
                      className={tc(
                        theme,
                        "text-xs px-2.5 py-1 rounded-md border border-zinc-700 text-zinc-300 hover:text-white transition disabled:opacity-50",
                        "text-xs px-2.5 py-1 rounded-md border border-zinc-300 text-zinc-700 hover:text-black transition disabled:opacity-50"
                      )}
                    >
                      {savingKey === c.key ? "Saving…" : "Save as List"}
                    </WorkButton>
                  )}
                  {launch && (
                    <WorkButton type="submit"
                      onClick={() => onStartCampaign(launch.campaign_type, launch.params)}
                      className="text-xs px-2.5 py-1 rounded-md bg-brand-teal text-black font-semibold hover:brightness-95 transition"
                    >
                      Start Campaign →
                    </WorkButton>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// A campaign's editable detail view -- Sam: "when you click on them they should show
// the list of people, all the information that has been included as well as active
// measurements / analytics." Takes over the full CRM panel same as ListDetailView.
// Exported (session 113 follow-up, Campaigns Top Menu split) so the new dedicated
// components/CampaignsBoard.tsx can reuse this exact detail view rather than building
// a second one -- this component never depended on the full CrmData shape, only on
// campaignId + the imported action functions, so it needed zero changes to be reused.
export function CampaignDetailView({
  theme,
  campaignId,
  onBack,
  onChanged,
  onDraftOpenChange,
  onSavingChange,
}: {
  theme: Theme;
  campaignId: string;
  onBack: () => void;
  onChanged: () => void;
  onDraftOpenChange?: (open:boolean)=>void; onSavingChange?: (saving:boolean)=>void;
}) {
  const session = getSession();

  const [detail, setDetail] = useState<CampaignDetail | null>(null);
  const [pageNum, setPageNum] = useState(1);
  const [pageSize, setPageSize] = useState<PageSize>(25);
  const [filter, setFilter] = useState<EntityFilter>("");
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState("");
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const mutationPending = useRef(false);
  useEffect(() => { onSavingChange?.(saving); return () => onSavingChange?.(false); }, [saving, onSavingChange]);
  const editingRef = useRef(false);
  const [exitRequested, setExitRequested] = useState(false);
  useEffect(() => { onDraftOpenChange?.(editing); return () => onDraftOpenChange?.(false); }, [editing, onDraftOpenChange]);
  function cancelEdit() {
    if (saving) return;
    editingRef.current = false; setEditing(false); setExitRequested(false);
    setName(String(detail?.campaign.name ?? "")); setNotes(String(detail?.campaign.notes ?? ""));
  }
  function back() { if(saving)return; if(editing)setExitRequested(true); else onBack(); }
  function load() {
    getCampaignDetail(campaignId, pageNum, pageSize, filter || null)
      .then((d) => {
        setDetail(d);
        if (!editingRef.current) { setName(String(d.campaign.name ?? "")); setNotes(String(d.campaign.notes ?? "")); }
        setError(null);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Couldn't load this campaign."));
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [campaignId, pageNum, pageSize, filter]);

  useEffect(() => {
    setPageNum(1);
  }, [pageSize, filter]);

  const canManage = session?.role === "ADMIN" || session?.role === "MARKETING" || detail?.campaign.created_by === session?.employeeId;

  async function save() {
    if(mutationPending.current)return; mutationPending.current=true;
    setSaving(true);
    setError(null);
    try {
      await updateCampaign(campaignId, { name, notes });
      editingRef.current = false; setEditing(false); setExitRequested(false);
      load();
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't save this campaign.");
    } finally {
      mutationPending.current=false; setSaving(false);
    }
  }

  async function handleStatusAction(fn: (id: string) => Promise<unknown>) {
    if(mutationPending.current)return; mutationPending.current=true; setSaving(true);
    setActionError(null);
    try {
      await fn(campaignId);
      load();
      onChanged();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "That action failed.");
    } finally { mutationPending.current=false; setSaving(false); }
  }

  if (!detail) {
    return (
      <div className="work-record-content flex-1 min-h-0 flex flex-col p-5 gap-4">
        <WorkButton type="submit" disabled={saving} onClick={back} className={tc(theme, "text-xs text-zinc-500 hover:text-white mb-2 self-start transition", "text-xs text-zinc-500 hover:text-black mb-2 self-start transition")}>
          ← Back to Campaigns
        </WorkButton>
        {error ? <div className="text-xs text-red-400">{error}</div> : <div className={tc(theme, "text-xs text-zinc-600", "text-xs text-zinc-500")}>Loading…</div>}
      </div>
    );
  }

  const c = detail.campaign;
  const stats = detail.stats;

  return (
    <div className="work-record-content flex-1 min-h-0 flex flex-col p-5 gap-4">
      <WorkButton type="submit" disabled={saving} onClick={back} className={tc(theme, "text-xs text-zinc-500 hover:text-white mb-2 self-start transition", "text-xs text-zinc-500 hover:text-black mb-2 self-start transition")}>
        ← Back to Campaigns
      </WorkButton>

      {exitRequested && <section role="alert" className="p-3 border rounded mb-3"><p>Leave this campaign edit? Your changes are still below.</p><WorkButton type="submit" onClick={() => setExitRequested(false)}>Keep editing campaign</WorkButton><WorkButton type="submit" disabled={saving} onClick={() => { if(saving)return; cancelEdit(); onBack(); }}>Discard edits and return</WorkButton></section>}
      <div className={tc(theme, "rounded-lg border border-zinc-800 bg-brand-charcoal p-3 mb-3", "rounded-lg border border-zinc-300 bg-zinc-50 p-3 mb-3")}>
        {editing ? (
          <div className="space-y-2">
            <WorkInput
              aria-label="Campaign name" disabled={saving}
              value={name}
              onChange={(e) => setName(e.target.value)}
              className={tc(theme, "w-full h-8 px-2 text-sm font-semibold rounded bg-zinc-900 border border-zinc-700", "w-full h-8 px-2 text-sm font-semibold rounded bg-white border border-zinc-300")}
            />
            <WorkTextarea
              aria-label="Campaign notes" disabled={saving}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={2}
              placeholder="Notes (optional)"
              className={tc(theme, "w-full px-2 py-1.5 text-xs rounded bg-zinc-900 border border-zinc-700", "w-full px-2 py-1.5 text-xs rounded bg-white border border-zinc-300")}
            />
            <div className="flex gap-2">
              <WorkButton type="submit" onClick={save} disabled={saving} className="text-xs px-3 py-1.5 rounded-md bg-brand-teal text-black font-semibold disabled:opacity-50">
                {saving ? "Saving…" : "Save"}
              </WorkButton>
              <WorkButton type="submit" disabled={saving} onClick={cancelEdit} className={tc(theme, "text-xs px-3 py-1.5 rounded-md border border-zinc-700 text-zinc-300", "text-xs px-3 py-1.5 rounded-md border border-zinc-300 text-zinc-700")}>
                Cancel
              </WorkButton>
            </div>
          </div>
        ) : (
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <div className="flex items-center gap-2">
                <h3 className="work-detail-title">{String(c.name)}</h3>
                <span
                  className="text-xs font-bold px-1.5 py-0.5 rounded"
                  style={{
                    backgroundColor: stats.status === "active" ? "#3FBCC4" : stats.status === "completed" ? "#22c55e" : stats.status === "cancelled" ? "#EE3C25" : "#5c5c66",
                    color: "#111",
                  }}
                >
                  {stats.status}
                </span>
              </div>
              {c.notes ? (
                <div className={tc(theme, "text-xs text-zinc-500 mt-0.5", "text-xs text-zinc-600 mt-0.5")}>{String(c.notes)}</div>
              ) : null}
              <div className={tc(theme, "text-xs text-zinc-600 mt-1", "text-xs text-zinc-500 mt-1")}>
                {stats.campaign_type} &middot; {stats.channel} &middot; created {fmtDate(stats.created_at)}
              </div>
            </div>
            {canManage && (
              <div className="flex gap-4 shrink-0 flex-wrap justify-end">
                <WorkButton type="submit" disabled={saving} onClick={() => { editingRef.current = true; setEditing(true); }} className={tc(theme, "text-xs px-2.5 py-1 rounded-md border border-zinc-700 text-zinc-300 hover:text-white transition", "text-xs px-2.5 py-1 rounded-md border border-zinc-300 text-zinc-700 hover:text-black transition")}>
                  Edit
                </WorkButton>
                {stats.status === "draft" && (
                  <WorkButton type="submit" disabled={saving} onClick={() => handleStatusAction(activateCrmCampaign)} className="text-xs px-2.5 py-1 rounded-md bg-brand-teal text-black font-semibold">
                    Activate
                  </WorkButton>
                )}
                {stats.status === "active" && (
                  <WorkButton type="submit" variant="primary" disabled={saving} onClick={() => handleStatusAction(completeCrmCampaign)} className="text-xs px-2.5 py-1 rounded-md bg-brand-blue text-white font-semibold">
                    Complete
                  </WorkButton>
                )}
                {(stats.status === "draft" || stats.status === "active") && (
                  <WorkButton type="submit" variant="danger" disabled={saving} onClick={() => handleStatusAction(cancelCrmCampaign)} className="text-xs px-2.5 py-1 rounded-md border border-red-500/40 text-red-400 hover:bg-red-500/10 transition">
                    Cancel
                  </WorkButton>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      {error && <div className="text-xs text-red-400 mb-2">{error}</div>}
      {actionError && <div className="text-xs text-red-400 mb-2">{actionError}</div>}

      {/* Active measurements / analytics */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className={tc(theme, "rounded-lg border border-zinc-800 bg-brand-charcoal p-5", "rounded-lg border border-zinc-300 bg-zinc-50 p-5")}>
          <div className={tc(theme, "text-xs text-zinc-500 uppercase tracking-wide", "text-xs text-zinc-600 uppercase tracking-wide")}>Audience</div>
          <div className={tc(theme, "text-lg font-bold text-zinc-100", "text-lg font-bold text-zinc-900")}>{stats.audience_count}</div>
        </div>
        <div className={tc(theme, "rounded-lg border border-zinc-800 bg-brand-charcoal p-5", "rounded-lg border border-zinc-300 bg-zinc-50 p-5")}>
          <div className={tc(theme, "text-xs text-zinc-500 uppercase tracking-wide", "text-xs text-zinc-600 uppercase tracking-wide")}>Sent</div>
          <div className="text-lg font-bold text-brand-teal">{stats.sent_count}</div>
        </div>
        <div className={tc(theme, "rounded-lg border border-zinc-800 bg-brand-charcoal p-5", "rounded-lg border border-zinc-300 bg-zinc-50 p-5")}>
          <div className={tc(theme, "text-xs text-zinc-500 uppercase tracking-wide", "text-xs text-zinc-600 uppercase tracking-wide")}>Days Active</div>
          <div className={tc(theme, "text-lg font-bold text-zinc-100", "text-lg font-bold text-zinc-900")}>{stats.days_active ?? "—"}</div>
        </div>
        <div className={tc(theme, "rounded-lg border border-zinc-800 bg-brand-charcoal p-5", "rounded-lg border border-zinc-300 bg-zinc-50 p-5")}>
          <div className={tc(theme, "text-xs text-zinc-500 uppercase tracking-wide", "text-xs text-zinc-600 uppercase tracking-wide")}>Activated</div>
          <div className={tc(theme, "text-xs font-semibold text-zinc-300 mt-1", "text-xs font-semibold text-zinc-700 mt-1")}>{fmtDate(stats.activated_at)}</div>
        </div>
      </div>

      {stats.not_yet_tracked && (
        <div className={tc(theme, "text-xs text-zinc-600 italic mb-3", "text-xs text-zinc-500 italic mb-3")}>
          Open/click rate: {stats.not_yet_tracked.open_rate}
        </div>
      )}

      {detail.linked_template && (
        <div className={tc(theme, "text-xs text-zinc-400 mb-3", "text-xs text-zinc-600 mb-3")}>
          Linked message: <span className="font-semibold">{detail.linked_template.name}</span> ({detail.linked_template.channel})
        </div>
      )}

      <div className={tc(theme, "flex-1 min-h-0 flex flex-col rounded-lg border border-zinc-800 bg-brand-charcoal overflow-hidden", "flex-1 min-h-0 flex flex-col rounded-lg border border-zinc-300 bg-zinc-50 overflow-hidden")}>
        <div className={tc(theme, "flex items-center justify-between gap-3 flex-wrap px-3 py-2 border-b border-zinc-800 shrink-0", "flex items-center justify-between gap-3 flex-wrap px-3 py-2 border-b border-zinc-300 shrink-0")}>
          <span className={tc(theme, "text-xs font-semibold text-zinc-300", "text-xs font-semibold text-zinc-700")}>Included People</span>
          <EntityFilterTabs theme={theme} value={filter} onChange={setFilter} />
          <PageSizeSelector theme={theme} value={pageSize} onChange={setPageSize} />
        </div>
        <div className="flex-1 min-h-0 overflow-y-auto px-3">
          <MemberTable theme={theme} page={detail.members} />
        </div>
        <div className={tc(theme, "px-3 py-2 border-t border-zinc-800 shrink-0", "px-3 py-2 border-t border-zinc-300 shrink-0")}>
          <Pager theme={theme} page={detail.members} onPage={setPageNum} />
        </div>
      </div>
    </div>
  );
}

// Exported (session 113 follow-up, Campaigns Top Menu split) -- narrowed from a full
// `data: CrmData` prop to just the `campaigns` slice of it, since this tab never read
// anything else off CrmData. That narrowing is what lets the new dedicated
// components/CampaignsBoard.tsx reuse this component with its own lean CampaignsData
// fetch instead of needing to load Pipeline/Lists/Opportunities/Customer 360/Smart
// Audiences/Lead Scoring alongside it. The CRM workspace's own Campaigns tab (this
// file's main export, below) is unaffected -- it just now passes `data.campaigns`
// instead of the whole `data` object.
export function CampaignsTab({
  theme,
  campaigns,
  prefillType,
  onClearPrefill,
  onRefresh,
  onDraftOpenChange,
  onSavingChange,
}: {
  theme: Theme;
  campaigns: CrmData["campaigns"];
  prefillType: { campaign_type: string; params: Record<string, unknown> } | null;
  onClearPrefill: () => void;
  onRefresh: () => void;
  onDraftOpenChange?: (open: boolean) => void; onSavingChange?: (saving:boolean)=>void;
}) {
  const session = getSession();
  const canManage = session?.role === "ADMIN" || session?.role === "MARKETING";

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [cancelRequested, setCancelRequested] = useState(false);
  useEffect(() => { onDraftOpenChange?.(showForm); }, [showForm, onDraftOpenChange]);
  const [campaignType, setCampaignType] = useState<string>("general");
  const [name, setName] = useState("");
  const [channel, setChannel] = useState<string>("email");
  const [fieldValues, setFieldValues] = useState<Record<string, string>>({});
  const [templateId, setTemplateId] = useState<string>("");
  const [templates, setTemplates] = useState<EmailTemplate[]>([]);
  const [preview, setPreview] = useState<{ count: number } | null>(null);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const previewVersion = useRef(0);
  const invalidatePreview = () => { previewVersion.current++; setPreview(null); };
  useEffect(() => () => { previewVersion.current++; }, []);
  const createPending = useRef(false);
  useEffect(() => { onSavingChange?.(saving); return () => onSavingChange?.(false); }, [saving, onSavingChange]);
  const [pendingCampaign, setPendingCampaign] = useState<string | null>(null);
  function resetDraft() {
    setCancelRequested(false); setShowForm(false); setName("");
    setCampaignType("general"); setChannel("email"); setFieldValues({});
    setTemplateId(""); invalidatePreview(); setFormError(null);
  }
  function openCampaign(id: string) {
    if (saving) return;
    if (showForm) { setPendingCampaign(id); setCancelRequested(true); }
    else setSelectedId(id);
  }

  const typesByKey = useMemo(() => {
    const map = new Map<string, CampaignType>();
    campaigns.available_types.forEach((t) => map.set(t.key, t));
    return map;
  }, [campaigns.available_types]);

  const selectedType = typesByKey.get(campaignType);

  useEffect(() => {
    if (prefillType) {
      setShowForm(true);
      setCampaignType(prefillType.campaign_type);
      setFieldValues(
        Object.fromEntries(Object.entries(prefillType.params).map(([k, v]) => [k, String(v)]))
      );
      const t = typesByKey.get(prefillType.campaign_type);
      if (t) setChannel(t.default_channel);
      onClearPrefill();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prefillType]);

  useEffect(() => {
    if (!showForm) return;
    listAllTemplates(channel === "sms" ? "sms" : "email")
      .then(setTemplates)
      .catch(() => setTemplates([]));
  }, [showForm, channel]);

  useEffect(() => {
    if (!showForm) return;
    const t = typesByKey.get(campaignType);
    if (t) {
      setChannel(t.default_channel);
      setFieldValues((prev) => {
        const next: Record<string, string> = {};
        t.audience_fields.forEach((f) => {
          next[f.key] = prev[f.key] ?? (f.default !== undefined ? String(f.default) : "");
        });
        return next;
      });
    }
    invalidatePreview();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [campaignType, showForm]);

  async function handlePreview() {
    const version = ++previewVersion.current;
    setPreview(null); setFormError(null);
    try {
      const params: Record<string, unknown> = { ...fieldValues };
      const result = await previewCrmAudience(campaignType, params);
      if(version === previewVersion.current)setPreview({ count: result.count });
    } catch (err) {
      if(version === previewVersion.current)setFormError(err instanceof Error ? err.message : "Couldn't preview this audience.");
    }
  }

  async function handleCreate() {
    if(createPending.current)return; createPending.current=true;
    setSaving(true);
    setFormError(null);
    try {
      await createCrmCampaign({
        campaign_type: campaignType,
        name: name || (selectedType?.name ?? "New Campaign"),
        channel,
        params: fieldValues,
        linked_template_id: templateId || null,
      });
      setShowForm(false);
      setName("");
      setTemplateId("");
      invalidatePreview();
      onRefresh();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Couldn't create this campaign.");
    } finally {
      createPending.current=false; setSaving(false);
    }
  }

  if (selectedId) {
    return (
      <CampaignDetailView
        theme={theme}
        campaignId={selectedId}
        onDraftOpenChange={onDraftOpenChange}
        onSavingChange={onSavingChange}
        onBack={() => setSelectedId(null)}
        onChanged={onRefresh}
      />
    );
  }

  return (
    <div className="flex-1 min-h-0 overflow-y-auto p-3 space-y-3">
      <div className="flex items-center gap-3 flex-wrap">
        <div className={tc(theme, "text-xs text-zinc-500", "text-xs text-zinc-600")}>
          {campaigns.total_campaigns} total &middot; {campaigns.pending_drafts.count} draft(s)
        </div>
        {Object.entries(campaigns.by_status).map(([status, count]) => (
          <span key={status} className={tc(theme, "text-xs px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-300", "text-xs px-1.5 py-0.5 rounded bg-zinc-200 text-zinc-700")}>
            {status}: {count}
          </span>
        ))}
        <DragToWorkspaceButton
          theme={theme}
          itemKey="crm"
          fieldPath={["campaigns", "recent_campaigns"]}
          sourceLabel="Recent Campaigns"
          rows={campaigns.recent_campaigns as unknown as Record<string, unknown>[]}
          numericColumns={["audience_count", "sent_count"]}
          labelColumn="name"
        />
        <WorkButton type="submit"
          disabled={saving}
          onClick={() => { setPendingCampaign(null); showForm ? setCancelRequested(true) : setShowForm(true); }}
          className="ml-auto text-xs px-3 py-1.5 rounded-md bg-brand-teal text-black font-semibold hover:brightness-95 transition"
        >
          {showForm ? "Cancel" : "+ New Campaign"}
        </WorkButton>
      </div>

      {cancelRequested && <div role="alert" className="p-3 border border-sky-300 rounded">
        <p>{pendingCampaign ? "Open another campaign? Your unfinished draft is still below." : "Discard this unsaved campaign draft?"}</p>
        <WorkButton type="submit" className="min-h-11 mr-4 underline" onClick={() => { setCancelRequested(false); setPendingCampaign(null); }}>Keep editing</WorkButton>
        <WorkButton type="submit" className="min-h-11 underline" disabled={saving} onClick={() => { if(saving)return; const next = pendingCampaign; resetDraft(); setPendingCampaign(null); if(next)setSelectedId(next); }}>{pendingCampaign ? "Discard draft and open campaign" : "Discard draft"}</WorkButton>
      </div>}
      {showForm && (
        <div className={tc(theme, "rounded-lg border border-zinc-800 bg-brand-charcoal p-3 space-y-2.5", "rounded-lg border border-zinc-300 bg-zinc-50 p-3 space-y-2.5")}>
          <div className="grid grid-cols-2 gap-2.5">
            <label className="block">
              <span className={tc(theme, "text-xs text-zinc-500", "text-xs text-zinc-600")}>Campaign Type</span>
              <WorkSelect
                value={campaignType}
                onChange={(e) => { invalidatePreview(); setCampaignType(e.target.value); }}
                className={tc(
                  theme,
                  "w-full h-8 mt-0.5 px-2 text-xs rounded bg-zinc-900 border border-zinc-700",
                  "w-full h-8 mt-0.5 px-2 text-xs rounded bg-white border border-zinc-300"
                )}
              >
                {campaigns.available_types.map((t) => (
                  <option key={t.key} value={t.key}>{t.name}</option>
                ))}
              </WorkSelect>
            </label>
            <label className="block">
              <span className={tc(theme, "text-xs text-zinc-500", "text-xs text-zinc-600")}>Channel</span>
              <WorkSelect
                value={channel}
                onChange={(e) => setChannel(e.target.value)}
                className={tc(
                  theme,
                  "w-full h-8 mt-0.5 px-2 text-xs rounded bg-zinc-900 border border-zinc-700",
                  "w-full h-8 mt-0.5 px-2 text-xs rounded bg-white border border-zinc-300"
                )}
              >
                {campaigns.available_channels.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </WorkSelect>
            </label>
          </div>

          {selectedType && (
            <div className={tc(theme, "text-xs text-zinc-500", "text-xs text-zinc-600")}>{selectedType.description}</div>
          )}

          <label className="block">
            <span className={tc(theme, "text-xs text-zinc-500", "text-xs text-zinc-600")}>Name</span>
            <WorkInput
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={selectedType?.name}
              className={tc(
                theme,
                "w-full h-8 mt-0.5 px-2 text-xs rounded bg-zinc-900 border border-zinc-700",
                "w-full h-8 mt-0.5 px-2 text-xs rounded bg-white border border-zinc-300"
              )}
            />
          </label>

          {selectedType?.audience_fields.map((f) => (
            <label key={f.key} className="block">
              <span className={tc(theme, "text-xs text-zinc-500", "text-xs text-zinc-600")}>{f.label}</span>
              <WorkInput
                value={fieldValues[f.key] ?? ""}
                onChange={(e) => { invalidatePreview(); setFieldValues((prev) => ({ ...prev, [f.key]: e.target.value })); }}
                className={tc(
                  theme,
                  "w-full h-8 mt-0.5 px-2 text-xs rounded bg-zinc-900 border border-zinc-700",
                  "w-full h-8 mt-0.5 px-2 text-xs rounded bg-white border border-zinc-300"
                )}
              />
            </label>
          ))}

          <label className="block">
            <span className={tc(theme, "text-xs text-zinc-500", "text-xs text-zinc-600")}>
              Linked Message (optional -- pulled from the Email/SMS builder)
            </span>
            <WorkSelect
              value={templateId}
              onChange={(e) => setTemplateId(e.target.value)}
              className={tc(
                theme,
                "w-full h-8 mt-0.5 px-2 text-xs rounded bg-zinc-900 border border-zinc-700",
                "w-full h-8 mt-0.5 px-2 text-xs rounded bg-white border border-zinc-300"
              )}
            >
              <option value="">None</option>
              {templates.map((t) => (
                <option key={t.id} value={t.id}>{t.name} ({t.subject || t.sms_body || "untitled"})</option>
              ))}
            </WorkSelect>
          </label>

          {formError && <div className="text-xs text-red-400">{formError}</div>}

          <div className="flex items-center gap-2">
            <WorkButton type="submit"
              onClick={handlePreview}
              className={tc(theme, "text-xs px-2.5 py-1.5 rounded-md border border-zinc-700 text-zinc-300 hover:text-white transition", "text-xs px-2.5 py-1.5 rounded-md border border-zinc-300 text-zinc-700 hover:text-black transition")}
            >
              Preview Audience
            </WorkButton>
            {preview && (
              <span className={tc(theme, "text-xs text-zinc-400", "text-xs text-zinc-600")}>
                {preview.count} recipient(s)
              </span>
            )}
            <WorkButton type="submit"
              onClick={handleCreate}
              disabled={saving}
              className="ml-auto text-xs px-3 py-1.5 rounded-md bg-brand-teal text-black font-semibold hover:brightness-95 transition disabled:opacity-50"
            >
              {saving ? "Creating…" : "Create Draft"}
            </WorkButton>
          </div>
        </div>
      )}

      <div className="space-y-1.5">
        {campaigns.recent_campaigns.map((c) => (
          <WorkButton type="submit"
            key={c.id}
            disabled={saving}
            onClick={() => openCampaign(c.id)}
            className={tc(
              theme,
              "w-full flex items-center gap-2 rounded-md border border-zinc-800 bg-brand-charcoal px-2.5 py-1.5 hover:border-brand-teal transition text-left",
              "w-full flex items-center gap-2 rounded-md border border-zinc-300 bg-zinc-50 px-2.5 py-1.5 hover:border-brand-blue transition text-left"
            )}
          >
            <span className={tc(theme, "text-xs font-medium text-zinc-200 truncate flex-1", "text-xs font-medium text-zinc-800 truncate flex-1")}>
              {c.name}
            </span>
            <span className={tc(theme, "text-xs text-zinc-500", "text-xs text-zinc-500")}>{c.campaign_type}</span>
            <span className={tc(theme, "text-xs text-zinc-500", "text-xs text-zinc-500")}>{c.channel}</span>
            <span className="text-xs font-bold px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-200">{c.audience_count}</span>
            <span
              className="text-xs font-bold px-1.5 py-0.5 rounded"
              style={{
                backgroundColor: c.status === "active" ? "#3FBCC4" : c.status === "completed" ? "#22c55e" : c.status === "cancelled" ? "#EE3C25" : "#5c5c66",
                color: "#111",
              }}
            >
              {c.status}
            </span>
            <span className={tc(theme, "text-xs text-zinc-600", "text-xs text-zinc-500")}>View →</span>
          </WorkButton>
        ))}
        {campaigns.recent_campaigns.length === 0 && (
          <div className={tc(theme, "text-xs text-zinc-600", "text-xs text-zinc-500")}>No campaigns yet.</div>
        )}
      </div>
      {!canManage && (
        <div className={tc(theme, "text-xs text-zinc-600 italic", "text-xs text-zinc-500 italic")}>
          Sales can view campaigns and their real audience/stats; only Marketing/Admin can activate, complete, or cancel.
        </div>
      )}
    </div>
  );
}

// Customer 360 (Marketing Growth Platform kickoff, 2026-07-17; the detail view
// itself became the shared, cross-department "Customer Intelligence Layer" panel
// 2026-07-19 -- see components/Customer360Panel.tsx's own header comment). Sam:
// "Marketing CRM needs to be an audience and customer intelligence platform... One
// record. One timeline." A CUST- id or name/email search here, opening the exact
// same real merged view (Lead History/Vehicle Ownership/Trade Equity/Service
// History/Finance History/Communication/Chat/Event Attendance/Campaign Activity/
// Purchase History/Credit Applications/Trade-Ins/one chronological Timeline) that
// Sales'/Service's/Finance's own boards now open too via their own "Full Customer
// 360" entry points -- this tab stays the one place a Marketing user searches for a
// customer by name/email rather than an id, everything past that point is shared.
function Customer360Tab({ theme }: { theme: Theme }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<CrmSearchResult[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const cardClass = tc(theme, "rounded-lg border border-zinc-800 bg-zinc-950 p-3", "rounded-lg border border-zinc-200 bg-zinc-50 p-3");
  const textClass = tc(theme, "bg-zinc-900 border-zinc-700 text-white placeholder:text-zinc-600", "bg-white border-zinc-300 text-black placeholder:text-zinc-400");

  async function runSearch() {
    if (!query.trim()) return;
    if (query.trim().toUpperCase().startsWith("CUST-")) {
      setSelectedId(query.trim().toUpperCase());
      setResults([]);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const r = await searchCrm(query.trim());
      setResults(r.results.filter((x) => x.entity_type === "Customer"));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex-1 p-4 overflow-y-auto space-y-4">
      <div className="flex items-center gap-2">
        <WorkField label="CUST- id, name, or email"><WorkInput
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && runSearch()}
          placeholder="CUST- id, name, or email…"
          className={`flex-1 rounded-md border px-3 py-1.5 text-xs ${textClass}`}
        /></WorkField>
        <WorkButton type="submit" variant="primary" onClick={runSearch} disabled={loading} className="text-xs px-3 py-1.5 rounded-md bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50">
          Search
        </WorkButton>
      </div>

      {error && <div className="text-xs text-red-400">{error}</div>}
      {loading && <div className={tc(theme, "text-xs text-zinc-500", "text-xs text-zinc-500")}>Loading…</div>}

      {results.length > 0 && (
        <div className={cardClass}>
          <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Results ({results.length})</div>
          <div className="space-y-1">
            {results.map((r) => (
              <WorkButton type="submit" key={r.id} onClick={() => setSelectedId(r.id)} className="block w-full text-left text-xs px-2 py-1.5 rounded hover:bg-zinc-800/40 transition">
                {r.name ?? r.id} <span className="text-zinc-500">({r.id})</span>
              </WorkButton>
            ))}
          </div>
        </div>
      )}

      {selectedId && <Customer360Panel theme={theme} customerId={selectedId} onClose={() => setSelectedId(null)} />}
    </div>
  );
}

// Smart Audiences + Lead Scoring (Marketing Growth Platform kickoff, 2026-07-17).
// Sam: "Smart Audiences... Visual Segment Builder... Very HubSpot-like: Vehicle =
// Truck AND Mileage > 75,000 AND Positive Equity. No coding required." Plus "Lead
// Scoring... Automatically prioritize."
function SmartAudiencesTab({ theme, data }: { theme: Theme; data: CrmData }) {
  const session = getSession();
  const canAct = session?.role === "ADMIN" || session?.role === "MARKETING";

  const [fields, setFields] = useState<AudienceField[]>([]);
  const [operators, setOperators] = useState<string[]>([]);
  const [presets, setPresets] = useState<AudiencePreset[]>([]);
  const [saved, setSaved] = useState<SavedAudience[]>([]);
  const [leaderboard, setLeaderboard] = useState<Leaderboard | null>(null);

  const [conditions, setConditions] = useState<AudienceCondition[]>([{ field: "", operator: "=", value: "" }]);
  const [previewResult, setPreviewResult] = useState<{ count: number; sample: AudienceMember[] } | null>(null);
  const [newAudienceName, setNewAudienceName] = useState("");
  const [presetPreview, setPresetPreview] = useState<Record<string, { count: number; sample: AudienceMember[] }>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const cardClass = tc(theme, "rounded-lg border border-zinc-800 bg-zinc-950 p-3", "rounded-lg border border-zinc-200 bg-zinc-50 p-3");
  const textClass = tc(theme, "bg-zinc-900 border-zinc-700 text-white placeholder:text-zinc-600", "bg-white border-zinc-300 text-black placeholder:text-zinc-400");

  function refresh() {
    getAudienceFields().then((r) => { setFields(r.fields); setOperators(r.operators); }).catch(() => {});
    listAudiencePresets().then((r) => setPresets(r.presets)).catch(() => {});
    listSavedAudiences().then((r) => setSaved(r.audiences)).catch(() => {});
    getLeadScoringLeaderboard(25).then(setLeaderboard).catch(() => {});
  }

  useEffect(refresh, []);

  async function runPreview() {
    setBusy(true);
    setError(null);
    try {
      const valid = conditions.filter((c) => c.field && c.operator);
      const r = await previewAudienceConditions(valid);
      setPreviewResult(r);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function previewOnePreset(key: string) {
    try {
      const r = await previewAudiencePreset(key, {});
      setPresetPreview((prev) => ({ ...prev, [key]: r }));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function saveCustomAudience() {
    if (!newAudienceName.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await createSmartAudience({ name: newAudienceName.trim(), conditions: conditions.filter((c) => c.field && c.operator) });
      setNewAudienceName("");
      setConditions([{ field: "", operator: "=", value: "" }]);
      setPreviewResult(null);
      refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function saveAsPreset(preset: AudiencePreset) {
    setBusy(true);
    setError(null);
    try {
      await createSmartAudience({ name: preset.name, preset_key: preset.key, preset_params: {} });
      refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function removeAudience(id: string) {
    setBusy(true);
    try {
      await deleteSmartAudience(id);
      refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const TIER_COLORS: Record<string, string> = { hot: "#EE3C25", warm: "#FBCF09", cool: "#5c5c66" };

  return (
    <div className="flex-1 p-4 overflow-y-auto space-y-4">
      {error && <div className="text-xs text-red-400">{error}</div>}

      <div className={cardClass}>
        <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Visual Segment Builder — No Coding Required</div>
        <div className="space-y-2">
          {conditions.map((c, i) => (
            <div key={i} className="flex items-center gap-2">
              <WorkField label="Field"><WorkSelect
                value={c.field}
                onChange={(e) => setConditions((prev) => prev.map((p, idx) => (idx === i ? { ...p, field: e.target.value } : p)))}
                className={`rounded-md border px-2 py-1.5 text-xs ${textClass}`}
              >
                <option value="">Field…</option>
                {fields.map((f) => (
                  <option key={f.key} value={f.key}>{f.label}</option>
                ))}
              </WorkSelect></WorkField>
              <WorkField label="Operator"><WorkSelect
                value={c.operator}
                onChange={(e) => setConditions((prev) => prev.map((p, idx) => (idx === i ? { ...p, operator: e.target.value } : p)))}
                className={`rounded-md border px-2 py-1.5 text-xs ${textClass}`}
              >
                {operators.map((op) => (
                  <option key={op} value={op}>{op}</option>
                ))}
              </WorkSelect></WorkField>
              <WorkField label="Value"><WorkInput
                value={c.value}
                onChange={(e) => setConditions((prev) => prev.map((p, idx) => (idx === i ? { ...p, value: e.target.value } : p)))}
                placeholder="Value"
                className={`flex-1 rounded-md border px-2 py-1.5 text-xs ${textClass}`}
              /></WorkField>
              {i > 0 && (
                <WorkButton type="submit" variant="danger" onClick={() => setConditions((prev) => prev.filter((_, idx) => idx !== i))} className="text-xs text-red-400 hover:text-red-300 transition">
                  Remove
                </WorkButton>
              )}
              {i < conditions.length - 1 && <span className="text-xs text-zinc-500 font-medium">AND</span>}
            </div>
          ))}
          <div className="flex items-center gap-2">
            <WorkButton type="submit" onClick={() => setConditions((prev) => [...prev, { field: "", operator: "=", value: "" }])} className="text-xs px-2 py-1 rounded bg-zinc-800 text-zinc-300 hover:text-white transition">
              + AND Condition
            </WorkButton>
            <WorkButton type="submit" variant="primary" onClick={runPreview} disabled={busy} className="text-xs px-2.5 py-1.5 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50">
              Preview
            </WorkButton>
          </div>
          {previewResult && (
            <div className="text-xs pt-1">
              <span className="font-semibold">{previewResult.count}</span> matches. <AudienceChips theme={theme} items={previewResult.sample.map((m) => ({ id: m.id, entity_type: "Customer", name: m.name }))} />
            </div>
          )}
          {canAct && (
            <div className="flex items-center gap-2 pt-1">
              <WorkField label="Save this segment as"><WorkInput value={newAudienceName} onChange={(e) => setNewAudienceName(e.target.value)} placeholder="Save this segment as…" className={`flex-1 rounded-md border px-2 py-1.5 text-xs ${textClass}`} /></WorkField>
              <WorkButton type="submit" onClick={saveCustomAudience} disabled={busy || !newAudienceName.trim()} className="text-xs px-2.5 py-1.5 rounded bg-brand-teal text-black font-semibold hover:opacity-90 transition disabled:opacity-50">
                Save Segment
              </WorkButton>
            </div>
          )}
        </div>
      </div>

      <div className={cardClass}>
        <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Preset Smart Audiences</div>
        <div className="grid grid-cols-2 gap-2">
          {presets.map((p) => (
            <div key={p.key} className="text-xs p-2 rounded border border-zinc-800/60">
              <div className="flex items-center justify-between">
                <span className="font-medium">{p.name}</span>
                <span className={`text-xs px-1.5 py-0.5 rounded uppercase ${p.basis === "real" ? "bg-green-950/40 text-green-300" : "bg-purple-950/40 text-purple-300"}`}>
                  {p.basis === "real" ? "Real" : "Heuristic"}
                </span>
              </div>
              <div className="flex items-center gap-2 mt-1.5">
                <WorkButton type="submit" onClick={() => previewOnePreset(p.key)} className="text-xs px-2 py-0.5 rounded bg-zinc-800 text-zinc-300 hover:text-white transition">
                  Preview
                </WorkButton>
                {canAct && (
                  <WorkButton type="submit" onClick={() => saveAsPreset(p)} disabled={busy} className="text-xs px-2 py-0.5 rounded bg-zinc-800 text-zinc-300 hover:text-white transition disabled:opacity-50">
                    Save
                  </WorkButton>
                )}
              </div>
              {presetPreview[p.key] && (
                <div className="text-xs text-zinc-500 mt-1">{presetPreview[p.key].count} matches</div>
              )}
            </div>
          ))}
        </div>
      </div>

      <div className={cardClass}>
        <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Saved Audiences ({saved.length})</div>
        <div className="space-y-1">
          {saved.length === 0 ? (
            <div className="text-xs text-zinc-600">No saved segments yet.</div>
          ) : (
            saved.map((a) => (
              <div key={a.id} className="flex items-center justify-between text-xs px-2 py-1.5 rounded hover:bg-zinc-800/40 transition">
                <span>{a.name} {a.preset_key && <span className="text-zinc-500">({a.preset_key})</span>}</span>
                {canAct && (
                  <WorkButton type="submit" variant="danger" onClick={() => removeAudience(a.id)} className="text-xs text-red-400 hover:text-red-300 transition">
                    Delete
                  </WorkButton>
                )}
              </div>
            ))
          )}
        </div>
      </div>

      <div className={cardClass}>
        <div className="flex items-center justify-between mb-2">
          <div className="text-xs font-brand uppercase tracking-wide text-zinc-500">Lead Scoring — Automatically Prioritized</div>
          {leaderboard && (
            <div className="flex items-center gap-2 text-xs">
              {Object.entries(leaderboard.by_tier).map(([tier, count]) => (
                <span key={tier} className="px-1.5 py-0.5 rounded" style={{ background: `${TIER_COLORS[tier]}22`, color: TIER_COLORS[tier] }}>
                  {tier}: {count}
                </span>
              ))}
            </div>
          )}
        </div>
        <div className="max-h-72 overflow-y-auto space-y-1">
          {(leaderboard?.leads ?? []).map((l) => (
            <div key={l.lead_id} className="flex items-center justify-between text-xs px-2 py-1.5 rounded hover:bg-zinc-800/40 transition">
              <div className="flex items-center gap-2">
                <EntityHoverLink id={l.lead_id} className="text-xs font-medium text-brand-teal hover:underline" />
                <span className="text-zinc-500">{l.pipeline_state} · {l.source ?? "—"}</span>
              </div>
              <span className="text-xs px-1.5 py-0.5 rounded font-semibold" style={{ background: `${TIER_COLORS[l.tier]}22`, color: TIER_COLORS[l.tier] }}>
                {l.score} pts
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// Opportunities: real workflow actions (session 82). Sam: "each module needs to be a
// workable process... how it would flow not only through the marketing department, but
// what parts would be accessible to sales." Every campaign-type-backed pool can be
// saved as a real curated List (MARKETING/ADMIN); the Lead-typed Conquest pool can
// additionally be handed directly to a salesperson via the real ASSIGNED_TO mechanism.
function OpportunitiesTab({ theme, data, onChanged }: { theme: Theme; data: CrmData; onChanged: () => void }) {
  const session = getSession();
  const canAct = session?.role === "ADMIN" || session?.role === "MARKETING";

  const [savingKey, setSavingKey] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [assignPool, setAssignPool] = useState<string | null>(null);
  const [salesEmployees, setSalesEmployees] = useState<SalesEmployee[]>([]);
  const [assignLeadId, setAssignLeadId] = useState<string>("");
  const [assignEmployeeId, setAssignEmployeeId] = useState<string>("");
  const [assigning, setAssigning] = useState(false);

  useEffect(() => {
    if (assignPool && salesEmployees.length === 0) {
      listSalesEmployees().then(setSalesEmployees).catch(() => setSalesEmployees([]));
    }
  }, [assignPool, salesEmployees.length]);

  const pools: Array<[string, string, CrmData["opportunities"]["equity_opportunities"]]> = [
    ["equity_opportunities", "Equity", data.opportunities.equity_opportunities],
    ["conquest_opportunities", "Conquest", data.opportunities.conquest_opportunities],
    ["lease_opportunities", "Lease / Finance", data.opportunities.lease_opportunities],
    ["service_opportunities", "Service", data.opportunities.service_opportunities],
    ["retention_opportunities", "Retention", data.opportunities.retention_opportunities],
  ];

  async function handleSaveAsList(key: string, label: string) {
    const launch = OPPORTUNITY_TO_CAMPAIGN_TYPE[key];
    if (!launch) return;
    setSavingKey(key);
    setMessage(null);
    try {
      await saveOpportunityPoolAsList({ name: `${label} Opportunities`, campaign_type: launch.campaign_type, params: launch.params });
      setMessage(`Saved "${label} Opportunities" as a list -- find it under the Lists tab.`);
      onChanged();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Couldn't save this pool as a list.");
    } finally {
      setSavingKey(null);
    }
  }

  async function handleAssign() {
    if (!assignLeadId || !assignEmployeeId) return;
    setAssigning(true);
    setMessage(null);
    try {
      await assignOpportunityToSales(assignLeadId, assignEmployeeId);
      setMessage(`Assigned ${assignLeadId} to ${salesEmployees.find((e) => e.id === assignEmployeeId)?.name ?? assignEmployeeId}.`);
      setAssignPool(null);
      setAssignLeadId("");
      setAssignEmployeeId("");
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Couldn't assign this lead.");
    } finally {
      setAssigning(false);
    }
  }

  return (
    <div className="flex-1 min-h-0 overflow-y-auto p-3 space-y-3">
      <div className="flex items-center justify-between gap-3">
        <div className={tc(theme, "text-xs text-zinc-500", "text-xs text-zinc-600")}>
          Marketing curates and saves opportunity pools as Lists for campaigns; the Conquest pool (Lead-typed) can be handed
          directly to a Sales rep here. Everything else flows to Sales through a saved List, since only Leads support direct
          assignment in this data model.
        </div>
        <DragToWorkspaceButton
          theme={theme}
          itemKey="crm"
          fieldPath={["opportunities"]}
          sourceLabel="Opportunity Pools"
          rows={pools.map(([, label, pool]) => ({
            pool: label,
            count: pool.count,
            revenue_estimate: pool.projected_revenue_estimate ?? 0,
          }))}
          numericColumns={["count", "revenue_estimate"]}
          labelColumn="pool"
        />
      </div>

      {message && (
        <div className={tc(theme, "text-xs px-3 py-2 rounded-lg bg-brand-teal/10 border border-brand-teal/40 text-brand-teal", "text-xs px-3 py-2 rounded-lg bg-brand-teal/10 border border-brand-teal/40 text-brand-blue")}>
          {message}
        </div>
      )}

      <div className="grid grid-cols-2 gap-3">
        {pools.map(([key, label, pool]) => {
          const launch = OPPORTUNITY_TO_CAMPAIGN_TYPE[key];
          return (
            <div key={key} className={tc(theme, "rounded-lg border border-zinc-800 bg-brand-charcoal p-3", "rounded-lg border border-zinc-300 bg-zinc-50 p-3")}>
              <div className="flex items-center justify-between mb-1">
                <span className={tc(theme, "text-xs font-semibold text-zinc-200", "text-xs font-semibold text-zinc-800")}>{label}</span>
                <span className="text-xs font-bold px-1.5 py-0.5 rounded bg-brand-blue text-white">{pool.count}</span>
              </div>
              {pool.projected_revenue_estimate !== undefined && (
                <div className={tc(theme, "text-sm font-bold text-brand-teal mb-1", "text-sm font-bold text-brand-blue mb-1")}>
                  {fmtMoney(pool.projected_revenue_estimate)}
                </div>
              )}
              <AudienceChips theme={theme} items={pool.sample} />
              <div className={tc(theme, "text-xs text-zinc-600 mt-1.5 italic", "text-xs text-zinc-500 mt-1.5 italic")}>{pool.note}</div>

              {canAct && launch && (
                <div className="flex gap-1.5 mt-2 flex-wrap">
                  <WorkButton type="submit"
                    onClick={() => handleSaveAsList(key, label)}
                    disabled={savingKey === key}
                    className={tc(
                      theme,
                      "text-xs px-2.5 py-1 rounded-md border border-zinc-700 text-zinc-300 hover:text-white transition disabled:opacity-50",
                      "text-xs px-2.5 py-1 rounded-md border border-zinc-300 text-zinc-700 hover:text-black transition disabled:opacity-50"
                    )}
                  >
                    {savingKey === key ? "Saving…" : "Save as List"}
                  </WorkButton>
                  {launch.leadTyped && (
                    <WorkButton type="submit"
                      onClick={() => setAssignPool(assignPool === key ? null : key)}
                      className="text-xs px-2.5 py-1 rounded-md bg-brand-teal text-black font-semibold hover:brightness-95 transition"
                    >
                      Assign to Sales →
                    </WorkButton>
                  )}
                </div>
              )}

              {assignPool === key && (
                <div className={tc(theme, "mt-2 rounded-md border border-zinc-800 bg-zinc-900 p-2 space-y-1.5", "mt-2 rounded-md border border-zinc-300 bg-white p-2 space-y-1.5")}>
                  <label className="block">
                    <span className={tc(theme, "text-xs text-zinc-500", "text-xs text-zinc-600")}>Lead (from sample above, or enter a Lead id)</span>
                    <WorkSelect
                      value={assignLeadId}
                      onChange={(e) => setAssignLeadId(e.target.value)}
                      className={tc(theme, "w-full h-7 mt-0.5 px-2 text-xs rounded bg-zinc-900 border border-zinc-700", "w-full h-7 mt-0.5 px-2 text-xs rounded bg-white border border-zinc-300")}
                    >
                      <option value="">Select a lead…</option>
                      {pool.sample.map((m) => (
                        <option key={m.id} value={m.id}>{m.name} ({m.id})</option>
                      ))}
                    </WorkSelect>
                  </label>
                  <label className="block">
                    <span className={tc(theme, "text-xs text-zinc-500", "text-xs text-zinc-600")}>Assign to</span>
                    <WorkSelect
                      value={assignEmployeeId}
                      onChange={(e) => setAssignEmployeeId(e.target.value)}
                      className={tc(theme, "w-full h-7 mt-0.5 px-2 text-xs rounded bg-zinc-900 border border-zinc-700", "w-full h-7 mt-0.5 px-2 text-xs rounded bg-white border border-zinc-300")}
                    >
                      <option value="">Select a salesperson…</option>
                      {salesEmployees.map((e) => (
                        <option key={e.id} value={e.id}>{e.name}{e.title ? ` — ${e.title}` : ""}</option>
                      ))}
                    </WorkSelect>
                  </label>
                  <WorkButton type="submit"
                    onClick={handleAssign}
                    disabled={assigning || !assignLeadId || !assignEmployeeId}
                    className="text-xs px-3 py-1 rounded-md bg-brand-teal text-black font-semibold disabled:opacity-50"
                  >
                    {assigning ? "Assigning…" : "Confirm Assignment"}
                  </WorkButton>
                </div>
              )}
            </div>
          );
        })}
      </div>

      <div className={tc(theme, "rounded-lg border border-zinc-800 bg-brand-charcoal p-3", "rounded-lg border border-zinc-300 bg-zinc-50 p-3")}>
        <div className={tc(theme, "text-xs font-semibold text-zinc-200 mb-1.5", "text-xs font-semibold text-zinc-800 mb-1.5")}>
          Who to Contact Today
        </div>
        <AudienceChips theme={theme} items={data.opportunities.who_to_contact_today} />
      </div>
    </div>
  );
}

type MarketingCrmTab = "pipeline" | "lists" | "campaigns" | "opportunities" | "customer360" | "audiences_scoring";

export function MarketingCRMBoard({ theme, initialTab = "pipeline", embedded = false, onDraftOpenChange, onSavingChange }: { theme: Theme; initialTab?: MarketingCrmTab; embedded?: boolean; onDraftOpenChange?: (open: boolean) => void; onSavingChange?: (saving:boolean)=>void }) {
  const [data, setData] = useState<CrmData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<MarketingCrmTab>(initialTab);
  const [prefillType, setPrefillType] = useState<{ campaign_type: string; params: Record<string, unknown> } | null>(null);

  const [campaignDraftOpen, setCampaignDraftOpen] = useState(false);
  const [campaignSaving, setCampaignSaving] = useState(false);
  useEffect(() => { onSavingChange?.(campaignSaving); return () => onSavingChange?.(false); }, [campaignSaving,onSavingChange]);
  const [leaveRequested, setLeaveRequested] = useState(false);
  useEffect(() => { onDraftOpenChange?.(campaignDraftOpen && tab === "campaigns"); }, [campaignDraftOpen, tab, onDraftOpenChange]);
  function returnToLists() { if(campaignSaving)return; setLeaveRequested(false); setPrefillType(null); setTab("lists"); }

  function refresh() {
    fetchCrmData()
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Unable to reach NXTDeal backend."))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const tabs: Array<{ key: typeof tab; label: string }> = [
    { key: "pipeline", label: "Pipeline" },
    { key: "lists", label: "Lists" },
    { key: "campaigns", label: "Campaigns" },
    { key: "opportunities", label: "Opportunities" },
    { key: "customer360", label: "Customer 360" },
    { key: "audiences_scoring", label: "Smart Audiences" },
  ];

  const kpis = useMemo(() => {
    if (!data) return null;
    const pipelineLeads = Object.values(data.pipeline.columns).reduce((sum, cards) => sum + cards.length, 0);
    const activeCampaigns = data.campaigns.by_status.active || 0;
    const opportunityCount =
      data.opportunities.equity_opportunities.count +
      data.opportunities.conquest_opportunities.count +
      data.opportunities.lease_opportunities.count +
      data.opportunities.service_opportunities.count +
      data.opportunities.retention_opportunities.count;
    return {
      pipelineLeads,
      activeCampaigns,
      totalCampaigns: data.campaigns.total_campaigns,
      opportunityCount,
    };
  }, [data]);

  if (loading) {
    return <div className={tc(theme, "p-4 text-sm text-zinc-600", "p-4 text-sm text-zinc-500")}>Loading CRM…</div>;
  }

  if (error || !data) {
    return <div className="p-4 text-sm text-red-400">{error ?? "Unable to load CRM data."}</div>;
  }

  return (
    <div className={tc(theme, "flex-1 flex flex-col min-h-0 bg-brand-ink text-white", "flex-1 flex flex-col min-h-0 bg-white text-black")}>
      {!embedded && kpis && (
        <div className={tc(theme, "grid grid-cols-4 gap-3 p-4 border-b border-zinc-800", "grid grid-cols-4 gap-3 p-4 border-b border-zinc-200")}>
          {[
            { label: "Pipeline Leads", value: kpis.pipelineLeads },
            { label: "Active Campaigns", value: kpis.activeCampaigns },
            { label: "Total Campaigns", value: kpis.totalCampaigns },
            { label: "Opportunities", value: kpis.opportunityCount },
          ].map((k, i) => (
            <div key={k.label} className={tc(theme, "relative overflow-hidden rounded-lg border border-black/20 bg-brand-charcoal p-3 pl-4", "relative overflow-hidden rounded-lg border border-zinc-200 bg-zinc-50 p-3 pl-4")}>
              <span className="nxt-accent absolute left-0 top-0 bottom-0 w-2.5"
                style={{ background: KPI_RIBBON[i % KPI_RIBBON.length], clipPath: "polygon(0 0, 100% 0, 45% 100%, 0 100%)" }}
              />
              <div className="text-2xl font-semibold">{k.value}</div>
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500">{k.label}</div>
            </div>
          ))}
        </div>
      )}

      {!embedded && <div className={tc(theme, "border-b border-zinc-800 px-4 py-2 flex items-center gap-2", "border-b border-zinc-200 px-4 py-2 flex items-center gap-2")}>
        {tabs.map((t) => (
          <WorkButton data-work-view aria-pressed={tab === t.key} type="submit"
            key={t.key}
            disabled={campaignSaving} onClick={() => setTab(t.key)}
            className={
              tab === t.key
                ? "text-xs px-2.5 py-1 rounded-md bg-zinc-200 text-black font-medium transition"
                : tc(
                    theme,
                    "text-xs px-2.5 py-1 rounded-md text-zinc-400 hover:text-white hover:bg-zinc-900 transition",
                    "text-xs px-2.5 py-1 rounded-md text-zinc-600 hover:text-black hover:bg-zinc-200 transition"
                  )
            }
          >
            {t.label}
          </WorkButton>
        ))}
      </div>}
      {embedded && tab === "campaigns" && <div className="p-3 border-b border-sky-200/20"><h3>Campaign from your audience</h3><p className="text-sm">Review the audience and save a draft. Creating a draft does not send it.</p><WorkButton type="submit" className="min-h-11 underline" disabled={campaignSaving} onClick={() => campaignDraftOpen ? setLeaveRequested(true) : returnToLists()}>Back to audience lists</WorkButton></div>}

      {leaveRequested && <div role="alert" className="p-3 border border-sky-300 rounded">
        <p>Your campaign has not been saved. Return to audience lists and discard it?</p>
        <WorkButton type="submit" className="min-h-11 mr-4 underline" onClick={() => setLeaveRequested(false)}>Keep editing campaign</WorkButton>
        <WorkButton type="submit" className="min-h-11 underline" disabled={campaignSaving} onClick={returnToLists}>Discard and return to lists</WorkButton>
      </div>}
      {tab === "pipeline" && <PipelineTab theme={theme} data={data} onRefresh={refresh} />}
      {tab === "lists" && (
        <ListsTab
          theme={theme}
          data={data}
          onStartCampaign={(campaignType, params) => {
            setPrefillType({ campaign_type: campaignType, params });
            setTab("campaigns");
          }}
        />
      )}
      {tab === "campaigns" && (
        <CampaignsTab
          theme={theme}
          campaigns={data.campaigns}
          onDraftOpenChange={setCampaignDraftOpen}
          onSavingChange={setCampaignSaving}
          prefillType={tab === "campaigns" ? prefillType : null}
          onClearPrefill={() => setPrefillType(null)}
          onRefresh={refresh}
        />
      )}
      {tab === "opportunities" && <OpportunitiesTab theme={theme} data={data} onChanged={refresh} />}
      {tab === "customer360" && <Customer360Tab theme={theme} />}
      {tab === "audiences_scoring" && <SmartAudiencesTab theme={theme} data={data} />}
    </div>
  );
}
