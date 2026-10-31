"use client";

// The OneNote-style persisted Workspace board (session 76). Sam: "the workspace needs
// to be dynamic in the sense that yes you can add graphs, but what other knowledge do
// you want to add?... it needs a feature where you can add in ai generated content
// explaining the graph... You should be able to prompt 'in the workspace window'...
// and be able to add in a paragraph. The idea is something like microsoft OneNote."
//
// Distinct from lib/useVisualizationWorkspace.ts's `draft` (the small "editing a chart
// before committing it" state, unchanged) -- this hook owns the persisted, ordered list
// of chart + note items that actually live in the user's Workspace, backed by
// GET/POST /workspace-board (core/workspace_board.py, one board per employee).
//
// Chart items don't persist their `rows` -- only the live reference (department/
// item_key/field_path/chart config), same "always reflects the current graph" rule
// pins already follow. On load, each chart item's rows are re-fetched from
// GET /menu/data and resolved via resolveFieldPath, same mechanism
// app/workspace/page.tsx's loadVisualizationPin already uses for pins.

import { useCallback, useEffect, useRef, useState } from "react";
import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";
import type { ChartType, VisualizationDraft } from "@/lib/useVisualizationWorkspace";
import { resolveFieldPath } from "@/lib/useVisualizationWorkspace";

export type WorkspaceChartItem = {
  id: string;
  kind: "chart";
  span: 1 | 2;
  order: number;
  createdAt: string;
  // Free-form canvas position in px (session 76 follow-up -- "add notes inside of
  // workspace... drag those around the canvas similar to OneNote").
  x: number;
  y: number;
  department: string;
  itemKey: string;
  fieldPath: string[];
  sourceLabel: string;
  labelColumn: string;
  chartType: ChartType;
  selectedColumns: string[];
  // A chart's own explanatory note (session 76 second follow-up -- Sam: "create a
  // chart, and then create a note under it explaining what it is, and save that as one
  // single piece of knowledge"). Lives ON the chart, not as a separate board item --
  // one card, one drag handle, one Save-to-Knowledge action for the pair.
  noteText: string;
  noteAiGenerated: boolean;
  // Client-only, not persisted -- filled in by a live GET /menu/data fetch after load.
  rows: Record<string, unknown>[];
  rowsLoading: boolean;
};

// A standalone, freeform note -- NOT the note attached to a chart (that's
// WorkspaceChartItem.noteText above). Born from the "+ Add Note" button or the
// "add to workspace: ..." chat command -- text with no chart of its own.
export type WorkspaceNoteItem = {
  id: string;
  kind: "note";
  span: 1 | 2;
  order: number;
  createdAt: string;
  x: number;
  y: number;
  title: string;
  text: string;
  sourceContext: string;
  aiGenerated: boolean;
};

// A "snapshot" -- a frozen frame of data grabbed from ANYWHERE in the app (a report
// table, a detail record) via the reusable AddToWorkspaceButton (Workspace grab-all,
// 2026-07-23). Unlike a chart item it carries its own data (no live re-fetch) and is
// honestly labelled "captured <when>".
export type WorkspaceSnapshotRow = Record<string, string | number | boolean | null>;
export type WorkspaceSnapshotItem = {
  id: string;
  kind: "snapshot";
  span: 1 | 2;
  order: number;
  createdAt: string;
  x: number;
  y: number;
  title: string;
  sourceLabel: string;
  sourceContext: string;
  capturedAt: string;
  dataKind: "table" | "text";
  columns: string[];
  rows: WorkspaceSnapshotRow[];
  text: string;
  noteText: string;
  noteAiGenerated: boolean;
};

export type WorkspaceBoardItem = WorkspaceChartItem | WorkspaceNoteItem | WorkspaceSnapshotItem;

// Matches core/ai_api.py's `suggested_report` shape exactly (snake_case, straight off
// the /ai/chat JSON response) -- see core/ai_tools.py's propose_report tool.
export type ReportSuggestion = {
  department: string;
  item_key: string;
  source_label: string;
  field_path: string[];
  label_column: string;
  numeric_columns: string[];
  chart_type: ChartType;
  row_count?: number;
};

const CASCADE_STEP = 32;
const CASCADE_WRAP = 8;

type RawItem = Record<string, unknown>;

function fromRaw(raw: RawItem): WorkspaceBoardItem | null {
  if (raw.kind === "chart") {
    return {
      id: String(raw.id),
      kind: "chart",
      span: raw.span === 2 ? 2 : 1,
      order: typeof raw.order === "number" ? raw.order : 0,
      createdAt: String(raw.created_at ?? ""),
      x: typeof raw.x === "number" ? raw.x : 0,
      y: typeof raw.y === "number" ? raw.y : 0,
      department: String(raw.department ?? ""),
      itemKey: String(raw.item_key ?? ""),
      fieldPath: Array.isArray(raw.field_path) ? raw.field_path.map(String) : [],
      sourceLabel: String(raw.source_label ?? ""),
      labelColumn: String(raw.label_column ?? ""),
      chartType: (["bar", "line", "pie"].includes(String(raw.chart_type)) ? raw.chart_type : "bar") as ChartType,
      selectedColumns: Array.isArray(raw.selected_columns) ? raw.selected_columns.map(String) : [],
      noteText: String(raw.note_text ?? ""),
      noteAiGenerated: !!raw.note_ai_generated,
      rows: [],
      rowsLoading: true,
    };
  }

  if (raw.kind === "note") {
    return {
      id: String(raw.id),
      kind: "note",
      span: raw.span === 2 ? 2 : 1,
      order: typeof raw.order === "number" ? raw.order : 0,
      createdAt: String(raw.created_at ?? ""),
      x: typeof raw.x === "number" ? raw.x : 0,
      y: typeof raw.y === "number" ? raw.y : 0,
      title: String(raw.title ?? ""),
      text: String(raw.text ?? ""),
      sourceContext: String(raw.source_context ?? ""),
      aiGenerated: !!raw.ai_generated,
    };
  }

  if (raw.kind === "snapshot") {
    return {
      id: String(raw.id),
      kind: "snapshot",
      span: raw.span === 2 ? 2 : 1,
      order: typeof raw.order === "number" ? raw.order : 0,
      createdAt: String(raw.created_at ?? ""),
      x: typeof raw.x === "number" ? raw.x : 0,
      y: typeof raw.y === "number" ? raw.y : 0,
      title: String(raw.title ?? ""),
      sourceLabel: String(raw.source_label ?? ""),
      sourceContext: String(raw.source_context ?? ""),
      capturedAt: String(raw.captured_at ?? ""),
      dataKind: raw.data_kind === "text" ? "text" : "table",
      columns: Array.isArray(raw.columns) ? raw.columns.map(String) : [],
      rows: Array.isArray(raw.rows) ? (raw.rows as WorkspaceSnapshotRow[]) : [],
      text: String(raw.text ?? ""),
      noteText: String(raw.note_text ?? ""),
      noteAiGenerated: !!raw.note_ai_generated,
    };
  }

  return null;
}

function toRaw(item: WorkspaceBoardItem): RawItem {
  if (item.kind === "chart") {
    return {
      id: item.id,
      kind: "chart",
      span: item.span,
      order: item.order,
      created_at: item.createdAt,
      x: item.x,
      y: item.y,
      department: item.department,
      item_key: item.itemKey,
      field_path: item.fieldPath,
      source_label: item.sourceLabel,
      label_column: item.labelColumn,
      chart_type: item.chartType,
      selected_columns: item.selectedColumns,
      note_text: item.noteText,
      note_ai_generated: item.noteAiGenerated,
    };
  }

  if (item.kind === "snapshot") {
    return {
      id: item.id,
      kind: "snapshot",
      span: item.span,
      order: item.order,
      created_at: item.createdAt,
      x: item.x,
      y: item.y,
      title: item.title,
      source_label: item.sourceLabel,
      source_context: item.sourceContext,
      captured_at: item.capturedAt,
      data_kind: item.dataKind,
      columns: item.columns,
      rows: item.rows,
      text: item.text,
      note_text: item.noteText,
      note_ai_generated: item.noteAiGenerated,
    };
  }

  return {
    id: item.id,
    kind: "note",
    span: item.span,
    order: item.order,
    created_at: item.createdAt,
    x: item.x,
    y: item.y,
    title: item.title,
    text: item.text,
    source_context: item.sourceContext,
    ai_generated: item.aiGenerated,
  };
}

const SAVE_DEBOUNCE_MS = 700;

export function useWorkspaceBoard() {
  const [items, setItems] = useState<WorkspaceBoardItem[]>([]);
  const [loading, setLoading] = useState(true);
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const loadedOnce = useRef(false);

  const hydrateChartRows = useCallback((chart: WorkspaceChartItem) => {
    const params = new URLSearchParams({ department: chart.department, item_key: chart.itemKey });

    fetch(`${API_BASE}/menu/data?${params.toString()}`, { headers: { ...authHeaders() } })
      .then((r) => r.json())
      .then((data) => {
        const rows = resolveFieldPath(data, chart.fieldPath) ?? [];
        setItems((prev) =>
          prev.map((it) => (it.id === chart.id && it.kind === "chart" ? { ...it, rows, rowsLoading: false } : it))
        );
      })
      .catch(() => {
        setItems((prev) =>
          prev.map((it) => (it.id === chart.id && it.kind === "chart" ? { ...it, rows: [], rowsLoading: false } : it))
        );
      });
  }, []);

  useEffect(() => {
    fetch(`${API_BASE}/workspace-board`, { headers: { ...authHeaders() } })
      .then((r) => r.json())
      .then((d) => {
        const raw: RawItem[] = Array.isArray(d.items) ? d.items : [];
        const parsed = raw.map(fromRaw).filter((i): i is WorkspaceBoardItem => i !== null);
        setItems(parsed);

        parsed.forEach((item) => {
          if (item.kind === "chart") hydrateChartRows(item);
        });
      })
      .catch(() => setItems([]))
      .finally(() => {
        setLoading(false);
        loadedOnce.current = true;
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Debounced auto-save, same pattern as ReportDashboardBuilder -- skips the very first
  // render (the load effect above already reflects server state, no need to immediately
  // re-save it back).
  useEffect(() => {
    if (!loadedOnce.current) return;

    if (saveTimer.current) clearTimeout(saveTimer.current);

    saveTimer.current = setTimeout(() => {
      fetch(`${API_BASE}/workspace-board`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ items: items.map(toRaw) }),
      }).catch(() => {
        // Best-effort -- a failed autosave isn't worth surfacing as an error for a
        // personal notes board; the next edit will just retry.
      });
    }, SAVE_DEBOUNCE_MS);

    return () => {
      if (saveTimer.current) clearTimeout(saveTimer.current);
    };
  }, [items]);

  function nextOrder() {
    return items.length === 0 ? 0 : Math.max(...items.map((i) => i.order)) + 1;
  }

  // A brand new item (from a chat command, a dragged-in chart, or a report
  // suggestion) has to land somewhere on the canvas before the user's ever dragged
  // anything -- cascades diagonally like an OS opening a new window, wrapping back to
  // the top-left every CASCADE_WRAP items rather than marching off-canvas forever.
  function cascadePosition(index: number) {
    const cycle = index % CASCADE_WRAP;
    return { x: 24 + cycle * CASCADE_STEP, y: 24 + cycle * CASCADE_STEP };
  }

  function addChartFromDraft(draft: VisualizationDraft) {
    const id = `local-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    const pos = cascadePosition(items.length);

    const item: WorkspaceChartItem = {
      id,
      kind: "chart",
      span: 1,
      order: nextOrder(),
      createdAt: new Date().toISOString(),
      x: pos.x,
      y: pos.y,
      department: draft.department,
      itemKey: draft.itemKey,
      fieldPath: draft.fieldPath,
      sourceLabel: draft.sourceLabel,
      labelColumn: draft.labelColumn,
      chartType: draft.chartType,
      selectedColumns: draft.selectedColumns,
      noteText: "",
      noteAiGenerated: false,
      rows: draft.rows,
      rowsLoading: false,
    };

    setItems((prev) => [...prev, item]);
    return id;
  }

  function addNote(text: string, opts?: { title?: string; sourceContext?: string; aiGenerated?: boolean }) {
    const id = `local-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    const pos = cascadePosition(items.length);

    const item: WorkspaceNoteItem = {
      id,
      kind: "note",
      span: 1,
      order: nextOrder(),
      createdAt: new Date().toISOString(),
      x: pos.x,
      y: pos.y,
      title: opts?.title ?? "",
      text,
      sourceContext: opts?.sourceContext ?? "",
      aiGenerated: !!opts?.aiGenerated,
    };

    setItems((prev) => [...prev, item]);
    return id;
  }

  // "build me a report on X" (session 76 follow-up) -- core/ai_api.py's
  // suggested_report, once the user clicks the chat button offering it. Drops a live,
  // editable chart with the model's own explanation already attached as its note --
  // one card, one item, matching core/ai_tools.py's propose_report + the surrounding
  // chat answer as a single unit rather than two separately-positioned pieces.
  function addChartFromReportSuggestion(suggestion: ReportSuggestion, explanationText: string) {
    const pos = cascadePosition(items.length);
    const chartId = `local-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

    const chartItem: WorkspaceChartItem = {
      id: chartId,
      kind: "chart",
      span: 1,
      order: nextOrder(),
      createdAt: new Date().toISOString(),
      x: pos.x,
      y: pos.y,
      department: suggestion.department,
      itemKey: suggestion.item_key,
      fieldPath: suggestion.field_path,
      sourceLabel: suggestion.source_label,
      labelColumn: suggestion.label_column,
      chartType: suggestion.chart_type,
      selectedColumns: suggestion.numeric_columns,
      noteText: explanationText || "",
      noteAiGenerated: true,
      rows: [],
      rowsLoading: true,
    };

    setItems((prev) => [...prev, chartItem]);
    hydrateChartRows(chartItem);

    return chartId;
  }

  // Reopening a "visualization" Knowledge pin that was saved from a board ChartCard
  // (has noteText/noteAiGenerated, see VisualizationPinConfig's comment in
  // useVisualizationWorkspace.ts) -- brings the whole chart+note pair back onto the
  // canvas as a real, editable card, rather than the old drag-and-drop editor's
  // pin-reopen behavior (which this config shape is deliberately distinct from).
  function addChartFromPinConfig(config: {
    department: string;
    itemKey: string;
    fieldPath: string[];
    sourceLabel: string;
    labelColumn: string;
    chartType: ChartType;
    selectedColumns: string[];
    noteText?: string;
    noteAiGenerated?: boolean;
  }) {
    const pos = cascadePosition(items.length);
    const id = `local-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

    const item: WorkspaceChartItem = {
      id,
      kind: "chart",
      span: 1,
      order: nextOrder(),
      createdAt: new Date().toISOString(),
      x: pos.x,
      y: pos.y,
      department: config.department,
      itemKey: config.itemKey,
      fieldPath: config.fieldPath,
      sourceLabel: config.sourceLabel,
      labelColumn: config.labelColumn,
      chartType: config.chartType,
      selectedColumns: config.selectedColumns,
      noteText: config.noteText ?? "",
      noteAiGenerated: config.noteAiGenerated ?? false,
      rows: [],
      rowsLoading: true,
    };

    setItems((prev) => [...prev, item]);
    hydrateChartRows(item);

    return id;
  }

  function removeItem(id: string) {
    setItems((prev) => prev.filter((i) => i.id !== id));
  }

  function updatePosition(id: string, x: number, y: number) {
    setItems((prev) => prev.map((it) => (it.id === id ? { ...it, x, y } : it)));
  }

  function updateChart(id: string, patch: Partial<Pick<WorkspaceChartItem, "chartType" | "selectedColumns" | "span">>) {
    setItems((prev) =>
      prev.map((it) => (it.id === id && it.kind === "chart" ? { ...it, ...patch } : it))
    );
  }

  function updateNoteText(id: string, text: string) {
    setItems((prev) =>
      prev.map((it) => (it.id === id && it.kind === "note" ? { ...it, text } : it))
    );
  }

  // Edits a chart's OWN attached note (session 76 second follow-up) -- distinct from
  // updateNoteText above, which is for standalone freeform notes.
  function updateChartNote(id: string, text: string, opts?: { aiGenerated?: boolean }) {
    setItems((prev) =>
      prev.map((it) =>
        it.id === id && it.kind === "chart"
          ? { ...it, noteText: text, noteAiGenerated: opts?.aiGenerated ?? it.noteAiGenerated }
          : it
      )
    );
  }

  async function explainChart(chart: WorkspaceChartItem, promptContext?: string) {
    try {
      const res = await fetch(`${API_BASE}/workspace-board/explain`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({
          source_label: chart.sourceLabel,
          department: chart.department,
          item_key: chart.itemKey,
          label_column: chart.labelColumn,
          numeric_columns: chart.selectedColumns,
          rows: chart.rows.slice(0, 30),
          prompt_context: promptContext ?? "",
        }),
      });
      const data = await res.json();

      if (data.text) {
        updateChartNote(chart.id, data.text, { aiGenerated: true });
      }
    } catch {
      updateChartNote(chart.id, "Unable to generate an explanation -- couldn't reach NXTDeal's AI service.");
    }
  }

  return {
    items,
    loading,
    addChartFromDraft,
    addNote,
    addChartFromReportSuggestion,
    addChartFromPinConfig,
    removeItem,
    updatePosition,
    updateChart,
    updateNoteText,
    updateChartNote,
    explainChart,
  };
}

export type WorkspaceBoard = ReturnType<typeof useWorkspaceBoard>;
