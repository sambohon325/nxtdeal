"use client";
import { WorkButton, WorkInput } from "./WorkspaceUi";
import {RecordTable} from "./RecordTable";
import { WorkField } from "./WorkField";

// One module card on a department's customizable Reporting dashboard (session 73).
// Sam: "lets also have each report / graph have a toggle where you can switch to text
// mode (like it is now)... they can create several modules (all editable as far as
// what parameters they want to show, what type of graph, colors, etc)."
//
// Deliberately a lean, self-contained renderer rather than reusing
// components/MenuDashPanel.tsx's full JsonValue tree (Visualize toggle, inline entity
// editing, unlimited recursion) -- importing JsonValue here would create an import
// cycle, since MenuDashPanel's MenuDashBody is what mounts
// components/ReportDashboardBuilder.tsx (which renders this component) for the
// Reporting tab. A report-dashboard card is meant to be a small, focused snapshot of
// one section of a department's real "reporting" rollup, not a full generic object
// browser.
import { useMemo, useState, type DragEvent } from "react";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  LineChart,
  Line,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  CartesianGrid,
} from "recharts";
import type {
  DashboardModuleInstance,
  ReportModuleCatalogEntry,
  ReportChartType,
  DashboardBoard,
} from "@/lib/reportDashboard";
import type { TimelineResponse } from "@/lib/predictionTimeline";
import { ModuleHorizonControl } from "@/components/ModuleHorizonControl";

type Theme = "dark" | "light";

const PALETTE = ["#8bd5fb", "#548fbd", "#c3dbe9", "#839bb7"];
const LEGACY_COLORS = ["#3fbcc4", "#2b68ab", "#fbcf09", "#ee3c25"];

function prettify(key: string): string {
  return key
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

// Same numeric-column/list-of-objects detection components/MenuDashPanel.tsx's
// ObjectListView already uses for its Visualize toggle -- kept independent here (not
// imported, to avoid the import cycle noted above) since it's a small, stable bit of
// logic rather than something worth threading a shared module for.
function classify(data: Record<string, unknown>) {
  const scalarFields = Object.entries(data)
    .filter(([, v]) => typeof v === "number")
    .map(([k]) => k);

  let listField: { key: string; rows: Record<string, unknown>[] } | null = null;
  for (const [k, v] of Object.entries(data)) {
    if (Array.isArray(v) && v.length > 0 && v.every((item) => item && typeof item === "object" && !Array.isArray(item))) {
      listField = { key: k, rows: v as Record<string, unknown>[] };
      break;
    }
  }

  if (listField) {
    const keySet = new Set<string>();
    listField.rows.forEach((r) => Object.keys(r).forEach((k) => keySet.add(k)));
    const columns = Array.from(keySet).slice(0, 8);
    const numericColumns = columns.filter((c) => listField!.rows.some((r) => typeof r[c] === "number"));
    const labelColumn = columns.find((c) => !numericColumns.includes(c)) ?? columns[0];

    if (numericColumns.length > 0) {
      return {
        mode: "list" as const,
        rows: listField.rows,
        numericColumns,
        labelColumn,
        scalarFields,
      };
    }
  }

  return {
    mode: scalarFields.length > 0 ? ("kpi" as const) : ("none" as const),
    rows: [],
    numericColumns: [] as string[],
    labelColumn: "",
    scalarFields,
  };
}

export function ReportDashboardModule({
  instance,
  catalogEntry,
  theme,
  board = "reporting",
  timeline,
  onUpdate,
  onRemove,
  dragProps,
}: {
  instance: DashboardModuleInstance;
  catalogEntry: ReportModuleCatalogEntry | undefined;
  theme: Theme;
  // Session 77: "Show in Overview" only makes sense on a Reporting-board module (it's
  // what feeds Overview's tray) -- omitted entirely when this card is itself rendering
  // on the Overview board.
  board?: DashboardBoard;
  // Session 78: the department's real prediction timeline, fetched once by
  // components/ReportDashboardBuilder.tsx and handed to every module card on the
  // Overview board -- null/undefined on the Reporting board (which keeps its own
  // standalone slider) or for a department with no real prediction source.
  timeline?: TimelineResponse | null;
  onUpdate: (patch: Partial<DashboardModuleInstance>) => void;
  onRemove: () => void;
  dragProps?: {
    draggable: boolean;
    onDragStart: (e: DragEvent<HTMLDivElement>) => void;
    onDragOver: (e: DragEvent<HTMLDivElement>) => void;
    onDrop: (e: DragEvent<HTMLDivElement>) => void;
    onDragEnd: (e: DragEvent<HTMLDivElement>) => void;
  };
}) {
  const [showSettings, setShowSettings] = useState(false);
  const oldColorIndex = LEGACY_COLORS.indexOf(instance.color.toLowerCase());
  const chartColor = oldColorIndex < 0 ? instance.color : PALETTE[oldColorIndex];

  const data = catalogEntry?.data ?? {};
  const classification = useMemo(() => classify(data), [data]);

  const availableFields =
    classification.mode === "list" ? classification.numericColumns : classification.scalarFields;

  const selectedFields = useMemo(() => {
    const chosen = instance.fields.filter((f) => availableFields.includes(f));
    if (chosen.length > 0) return chosen;
    return availableFields.slice(0, classification.mode === "list" ? 3 : 6);
  }, [instance.fields, availableFields, classification.mode]);

  const chartRows = useMemo(() => {
    if (classification.mode === "kpi") {
      return selectedFields.map((f) => ({ _label: prettify(f), value: data[f] as number }));
    }
    if (classification.mode === "list") {
      return classification.rows.slice(0, 12).map((r) => {
        const out: Record<string, unknown> = { _label: String(r[classification.labelColumn] ?? "") };
        selectedFields.forEach((c) => {
          out[c] = r[c];
        });
        return out;
      });
    }
    return [];
  }, [classification, selectedFields, data]);

  const seriesKeys = classification.mode === "kpi" ? ["value"] : selectedFields;
  const chartable = classification.mode !== "none";
  const canText = true;

  const mode = chartable ? instance.mode : "text";

  function renderChart(chartType: ReportChartType) {
    if (chartType === "pie") {
      const key = seriesKeys[0] ?? "value";
      const pieData = chartRows.map((r) => ({ name: String(r._label), value: Number((r as Record<string, unknown>)[key]) || 0 }));
      return (
        <ResponsiveContainer>
          <PieChart>
            <Pie data={pieData} dataKey="value" nameKey="name" outerRadius="80%">
              {pieData.map((_, i) => (
                <Cell key={i} fill={i === 0 ? chartColor : PALETTE[i % PALETTE.length]} />
              ))}
            </Pie>
            <Tooltip contentStyle={{ fontSize: 11, background: theme === "dark" ? "#0b2131" : "#fff", border: "1px solid #3f3f46" }} />
            <Legend wrapperStyle={{ fontSize: 10 }} />
          </PieChart>
        </ResponsiveContainer>
      );
    }

    const ChartComp = chartType === "line" ? LineChart : BarChart;

    return (
      <ResponsiveContainer>
        <ChartComp data={chartRows}>
          <CartesianGrid strokeDasharray="3 3" stroke={theme === "dark" ? "#7bbde522" : "#e4e4e7"} />
          <XAxis
            dataKey="_label"
            tick={{ fontSize: 11, fill: theme === "dark" ? "#a1a1aa" : "#52525b" }}
            interval={0}
            angle={-25}
            textAnchor="end"
            height={44}
          />
          <YAxis tick={{ fontSize: 11, fill: theme === "dark" ? "#a1a1aa" : "#52525b" }} />
          <Tooltip contentStyle={{ fontSize: 11, background: theme === "dark" ? "#0b2131" : "#fff", border: "1px solid #3f3f46" }} />
          {seriesKeys.length > 1 && <Legend wrapperStyle={{ fontSize: 10 }} />}
          {seriesKeys.map((key, i) =>
            chartType === "line" ? (
              <Line key={key} type="monotone" dataKey={key} stroke={i === 0 ? chartColor : PALETTE[i % PALETTE.length]} strokeWidth={2} dot={false} />
            ) : (
              <Bar key={key} dataKey={key} fill={i === 0 ? chartColor : PALETTE[i % PALETTE.length]} radius={[3, 3, 0, 0]} />
            )
          )}
        </ChartComp>
      </ResponsiveContainer>
    );
  }

  function renderText() {
    if (classification.mode === "list") {
      const columns = [classification.labelColumn, ...selectedFields];
      return (
        <div className="overflow-x-auto">
          <RecordTable className="w-full text-xs">
            <thead>
              <tr className={tc(theme, "text-zinc-500 text-left border-b border-zinc-800", "text-zinc-600 text-left border-b border-zinc-300")}>
                {columns.map((c) => (
                  <th key={c} className="py-1 pr-3 font-medium">{prettify(c)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {classification.rows.slice(0, 12).map((r, i) => (
                <tr key={i} className={tc(theme, "border-b border-zinc-900 last:border-0", "border-b border-zinc-200 last:border-0")}>
                  {columns.map((c) => (
                    <td key={c} className="py-1 pr-3">{r[c] === null || r[c] === undefined ? "—" : String(r[c])}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </RecordTable>
        </div>
      );
    }

    return (
      <table className="work-property-table w-full">
        <tbody>
          {Object.entries(data).map(([k, v]) => (
            <tr key={k} className={tc(theme, "border-b border-zinc-900 last:border-0 align-top", "border-b border-zinc-200 last:border-0 align-top")}>
              <td className={tc(theme, "py-1 pr-3 text-zinc-500 whitespace-nowrap", "py-1 pr-3 text-zinc-600 whitespace-nowrap")}>{prettify(k)}</td>
              <td className={tc(theme, "py-1 text-zinc-200", "py-1 text-zinc-900")}>
                {Array.isArray(v)
                  ? `${v.length} item${v.length === 1 ? "" : "s"}`
                  : v === null || v === undefined
                  ? "—"
                  : typeof v === "object"
                  ? Object.entries(v as Record<string, unknown>).map(([key, value]) => `${prettify(key)}: ${value === null ? "—" : typeof value === "object" ? JSON.stringify(value) : String(value)}`).join(" · ")
                  : String(v)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    );
  }

  return (
    <div
      {...dragProps}
      className={tc(
        theme,
        "nxt-report-card relative flex flex-col rounded-lg border border-zinc-800/60 bg-brand-charcoal overflow-hidden",
        "nxt-report-card relative flex flex-col rounded-lg border border-zinc-300 bg-white overflow-hidden"
      )}
      style={{ gridColumn: instance.span === 2 ? "span 2" : "span 1" }}
    >
      <header className={tc(theme, "relative flex items-center justify-between gap-2 px-3 py-2 border-b border-black/20 cursor-grab active:cursor-grabbing", "relative flex items-center justify-between gap-2 px-3 py-2 border-b border-zinc-300 cursor-grab active:cursor-grabbing")}>
        <span className={tc(theme, "nxt-report-title text-xs font-brand", "nxt-report-title text-xs font-brand text-zinc-800")}>
          {catalogEntry?.label ?? instance.module_key}
        </span>

        <div className="nxt-report-tools flex items-center gap-1 shrink-0">
          {chartable && (
            <WorkButton type="submit"
              onClick={() => onUpdate({ mode: mode === "graph" ? "text" : "graph" })}
              title={mode === "graph" ? "Switch to text mode" : "Switch to graph mode"}
              className={tc(theme, "text-xs px-1.5 py-0.5 rounded border border-zinc-700 text-zinc-400 hover:text-white transition", "text-xs px-1.5 py-0.5 rounded border border-zinc-300 text-zinc-600 hover:text-black transition")}
            >
              {mode === "graph" ? "☰" : "📊"}
            </WorkButton>
          )}
          <WorkButton type="submit"
            onClick={() => onUpdate({ span: instance.span === 2 ? 1 : 2 })}
            title={instance.span === 2 ? "Shrink to one column" : "Stretch across both columns"}
            className={tc(theme, "text-xs px-1.5 py-0.5 rounded border border-zinc-700 text-zinc-400 hover:text-white transition", "text-xs px-1.5 py-0.5 rounded border border-zinc-300 text-zinc-600 hover:text-black transition")}
          >
            {instance.span === 2 ? "⇤⇥" : "⇥"}
          </WorkButton>
          <WorkButton type="submit"
            onClick={() => setShowSettings((s) => !s)}
            title="Module settings"
            className={tc(theme, "text-xs px-1.5 py-0.5 rounded border border-zinc-700 text-zinc-400 hover:text-white transition", "text-xs px-1.5 py-0.5 rounded border border-zinc-300 text-zinc-600 hover:text-black transition")}
          >
            ⚙
          </WorkButton>
          <WorkButton type="submit"
            onClick={onRemove}
            title="Hide this module (it stays available to drag back in)"
            className={tc(theme, "text-xs px-1.5 py-0.5 rounded border border-zinc-700 text-zinc-400 hover:text-white transition", "text-xs px-1.5 py-0.5 rounded border border-zinc-300 text-zinc-600 hover:text-black transition")}
          >
            ×
          </WorkButton>
        </div>
      </header>

      {showSettings && (
        <div className={tc(theme, "px-3 py-2 border-b border-black/20 bg-brand-ink/60 space-y-2", "px-3 py-2 border-b border-zinc-300 bg-zinc-100 space-y-2")}>
          {chartable && (
            <div className="flex items-center gap-2">
              <span className={tc(theme, "text-xs text-zinc-500 w-14 shrink-0", "text-xs text-zinc-600 w-14 shrink-0")}>Chart</span>
              <div className="flex items-center gap-1">
                {(["bar", "line", "pie"] as ReportChartType[]).map((ct) => (
                  <WorkButton type="submit"
                    key={ct}
                    onClick={() => onUpdate({ chart_type: ct })}
                    className={
                      instance.chart_type === ct
                        ? "text-xs px-2 py-0.5 rounded bg-brand-teal text-black font-semibold"
                        : tc(theme, "text-xs px-2 py-0.5 rounded border border-zinc-700 text-zinc-400 hover:text-white transition", "text-xs px-2 py-0.5 rounded border border-zinc-300 text-zinc-600 hover:text-black transition")
                    }
                  >
                    {ct === "bar" ? "▊ Bar" : ct === "line" ? "／ Line" : "◔ Pie"}
                  </WorkButton>
                ))}
              </div>
            </div>
          )}

          <div className="flex items-center gap-2">
            <span className={tc(theme, "text-xs text-zinc-500 w-14 shrink-0", "text-xs text-zinc-600 w-14 shrink-0")}>Color</span>
            <div className="flex items-center gap-1">
              {PALETTE.map((c) => (
                <WorkButton type="submit"
                  key={c}
                  onClick={() => onUpdate({ color: c })}
                  className={instance.color === c ? "w-5 h-5 rounded-full ring-2 ring-white" : "w-5 h-5 rounded-full"}
                  style={{ background: c }}
                />
              ))}
              <WorkField label="Color"><WorkInput
                type="color"
                value={instance.color}
                onChange={(e) => onUpdate({ color: e.target.value })}
                className="w-5 h-5 rounded bg-transparent border-0 cursor-pointer"
                title="Custom color"
              /></WorkField>
            </div>
          </div>

          {availableFields.length > 0 && (
            <div className="flex items-start gap-2">
              <span className={tc(theme, "text-xs text-zinc-500 w-14 shrink-0 pt-0.5", "text-xs text-zinc-600 w-14 shrink-0 pt-0.5")}>Fields</span>
              <div className="flex flex-wrap gap-1">
                {availableFields.map((f) => {
                  const active = selectedFields.includes(f);
                  return (
                    <WorkButton type="submit"
                      key={f}
                      onClick={() => {
                        const next = active ? selectedFields.filter((x) => x !== f) : [...selectedFields, f];
                        onUpdate({ fields: next });
                      }}
                      className={
                        active
                          ? "text-xs px-2 py-0.5 rounded-full bg-brand-teal text-black font-medium"
                          : tc(theme, "text-xs px-2 py-0.5 rounded-full border border-zinc-700 text-zinc-400 hover:text-white transition", "text-xs px-2 py-0.5 rounded-full border border-zinc-300 text-zinc-600 hover:text-black transition")
                      }
                    >
                      {prettify(f)}
                    </WorkButton>
                  );
                })}
              </div>
            </div>
          )}

          {board === "reporting" && (
            <div className="flex items-center gap-2">
              <span className={tc(theme, "text-xs text-zinc-500 w-14 shrink-0", "text-xs text-zinc-600 w-14 shrink-0")}>Overview</span>
              <WorkButton type="submit"
                onClick={() => onUpdate({ show_in_overview: !instance.show_in_overview })}
                title="Also list this module in this department's Overview board tray"
                className={
                  instance.show_in_overview
                    ? "text-xs px-2 py-0.5 rounded-full bg-brand-teal text-black font-medium"
                    : tc(theme, "text-xs px-2 py-0.5 rounded-full border border-zinc-700 text-zinc-400 hover:text-white transition", "text-xs px-2 py-0.5 rounded-full border border-zinc-300 text-zinc-600 hover:text-black transition")
                }
              >
                {instance.show_in_overview ? "✓ Shown in Overview" : "Show in Overview"}
              </WorkButton>
            </div>
          )}
        </div>
      )}

      <div className="flex-1 p-3" style={{ minHeight: mode === "graph" ? 200 : undefined }}>
        {board === "overview" && timeline && (
          <ModuleHorizonControl timeline={timeline} theme={theme} />
        )}
        {!catalogEntry ? (
          <div className={tc(theme, "text-xs text-zinc-600", "text-xs text-zinc-500")}>This module's data source is no longer available.</div>
        ) : mode === "graph" && chartable ? (
          <div style={{ width: "100%", height: 200 }}>{renderChart(instance.chart_type)}</div>
        ) : canText ? (
          renderText()
        ) : null}

      </div>
    </div>
  );
}
