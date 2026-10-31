"use client";

// Drag-a-section-into-workspace visualization editor (Sam: "in reporting for each
// section/department... select the section and drag and drop it into the workspace
// where you can then edit it into the chart/graph you want to see before pinning").
// Scoped to a Top Menu Dash's Reporting item, per Sam's own choice when asked. Lives
// alongside lib/useMenuDash.ts -- one hook instance per page, threaded down to
// MenuDashPanel (the drag source) and components/VisualizationWorkspace.tsx (the
// editor UI that takes over the Workspace <aside> while the Dash stays open, "chat
// still hidden, back to its original form where you can scale it").
import { useState } from "react";

export type ChartType = "bar" | "line" | "pie";

export type VisualizationDraft = {
  department: string;
  itemKey: string;
  // Path of object keys from the item's JSON root down to the array-of-objects being
  // charted, e.g. ["salesperson_scorecards"] or ["department_intelligence", "kpis"].
  // Lets a pinned visualization re-fetch this exact same array later instead of
  // freezing a snapshot (Sam's choice: pins stay live, matching every other pin kind).
  fieldPath: string[];
  sourceLabel: string;
  rows: Record<string, unknown>[];
  numericColumns: string[];
  labelColumn: string;
  chartType: ChartType;
  selectedColumns: string[];
};

export type VisualizationDropPayload = {
  department: string;
  itemKey: string;
  fieldPath: string[];
  sourceLabel: string;
  rows: Record<string, unknown>[];
  numericColumns: string[];
  labelColumn: string;
};

export function useVisualizationWorkspace() {
  const [draft, setDraft] = useState<VisualizationDraft | null>(null);

  function open(
    payload: VisualizationDropPayload,
    initial?: { chartType?: ChartType; selectedColumns?: string[] }
  ) {
    setDraft({
      ...payload,
      chartType: initial?.chartType ?? "bar",
      selectedColumns:
        initial?.selectedColumns && initial.selectedColumns.length > 0
          ? initial.selectedColumns
          : payload.numericColumns.slice(0, 3),
    });
  }

  function close() {
    setDraft(null);
  }

  function setChartType(chartType: ChartType) {
    setDraft((d) => (d ? { ...d, chartType } : d));
  }

  function toggleColumn(column: string) {
    setDraft((d) => {
      if (!d) return d;

      const has = d.selectedColumns.includes(column);

      return {
        ...d,
        selectedColumns: has
          ? d.selectedColumns.filter((c) => c !== column)
          : [...d.selectedColumns, column],
      };
    });
  }

  function replaceRows(rows: Record<string, unknown>[]) {
    setDraft((d) => (d ? { ...d, rows } : d));
  }

  return { draft, open, close, setChartType, toggleColumn, replaceRows };
}

export type VisualizationWorkspaceHook = ReturnType<typeof useVisualizationWorkspace>;

// Shared drag-payload MIME type -- the drag source (MenuDashPanel.tsx's
// ObjectListView) and drop target (components/MenuDashPanel.tsx's
// WorkspaceCollapsedTab) both reference this constant rather than a hardcoded string.
export const VISUALIZATION_DRAG_TYPE = "application/x-dealeros-visualization";

function prettifyLabel(key: string): string {
  return key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

// The full chart config a "visualization" pin needs to (a) look right the instant it's
// re-opened and (b) re-fetch live data rather than freeze a snapshot (Sam's choice --
// pins stay live, matching every other pin kind in this codebase). Encoded into
// Pin.refId as JSON since PinKind's existing shape has no room for a nested config
// object -- app/workspace/page.tsx's handleOpenPin parses this back out via
// parseVisualizationPinRefId() below and re-fetches GET /menu/data before walking
// fieldPath to pull the current array.
export type VisualizationPinConfig = {
  department: string;
  itemKey: string;
  fieldPath: string[];
  sourceLabel: string;
  labelColumn: string;
  chartType: ChartType;
  selectedColumns: string[];
  // Only present on a pin saved from a Workspace board ChartCard (session 76 second
  // follow-up), not from this file's own drag-a-Reporting-section editor -- their
  // presence is how app/workspace/page.tsx's loadVisualizationPin tells the two pin
  // shapes apart (reopen onto the board vs. reopen the standalone editor).
  noteText?: string;
  noteAiGenerated?: boolean;
};

export function buildVisualizationPin(draft: VisualizationDraft): {
  kind: "visualization";
  label: string;
  refId: string;
  tag: string;
} {
  const config: VisualizationPinConfig = {
    department: draft.department,
    itemKey: draft.itemKey,
    fieldPath: draft.fieldPath,
    sourceLabel: draft.sourceLabel,
    labelColumn: draft.labelColumn,
    chartType: draft.chartType,
    selectedColumns: draft.selectedColumns,
  };

  return {
    kind: "visualization",
    label: `${draft.sourceLabel} — ${prettifyLabel(draft.department)} (${draft.chartType})`,
    refId: JSON.stringify(config),
    tag: draft.department,
  };
}

export function parseVisualizationPinRefId(refId: string): VisualizationPinConfig | null {
  try {
    const parsed = JSON.parse(refId);
    if (parsed && typeof parsed === "object" && typeof parsed.department === "string") {
      return parsed as VisualizationPinConfig;
    }
    return null;
  } catch {
    return null;
  }
}

// Walks a fetched GET /menu/data response down `fieldPath` (e.g.
// ["salesperson_scorecards"] or ["kpis", 2, "breakdown"]) to recover the same
// array-of-objects a pin was originally dragged from.
export function resolveFieldPath(data: unknown, fieldPath: string[]): Record<string, unknown>[] | null {
  let current: unknown = data;

  for (const key of fieldPath) {
    if (current === null || typeof current !== "object") return null;
    current = Array.isArray(current) ? current[Number(key)] : (current as Record<string, unknown>)[key];
  }

  if (Array.isArray(current) && current.every((v) => v && typeof v === "object" && !Array.isArray(v))) {
    return current as Record<string, unknown>[];
  }

  return null;
}
