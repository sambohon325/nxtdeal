"use client";

// The chart editor that takes over the Workspace <aside> when a Reporting section is
// dropped onto WorkspaceCollapsedTab (Sam: "select the section and drag and drop it
// into the workspace where you can then edit it into the chart / graph you want to see
// before pinning"). Scoped per Sam's own choice: chart type + which numeric columns to
// plot, not a fuller title/color editor. Lives alongside DepartmentWorkflowButtons /
// DepartmentQuickActions as one more thing the Workspace column can show -- swapped in
// by app/workspace/page.tsx's layout branch instead of the usual workflow-buttons
// content while a visualization draft is open.
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
import type { ChartType, VisualizationDraft } from "@/lib/useVisualizationWorkspace";
import { angledClip } from "@/components/BrandAngles";

const SERIES_COLORS = ["#3FBCC4", "#2B68AB", "#FBCF09", "#EE3C25", "#8B5CF6", "#22C55E"];

const CHART_TYPES: { key: ChartType; label: string }[] = [
  { key: "bar", label: "📊 Bar" },
  { key: "line", label: "📈 Line" },
  { key: "pie", label: "🥧 Pie" },
];

function prettify(key: string): string {
  return key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function VisualizationWorkspace({
  draft,
  onChangeChartType,
  onToggleColumn,
  onClose,
  onPin,
  pinned,
  onAddToWorkspace,
  addedToWorkspace,
}: {
  draft: VisualizationDraft;
  onChangeChartType: (t: ChartType) => void;
  onToggleColumn: (column: string) => void;
  onClose: () => void;
  onPin: () => void;
  pinned: boolean;
  // Session 76 -- "add it to my Workspace notes" as a real, separate action from
  // pinning to Knowledge: pinning bookmarks a view for later, adding to Workspace
  // drops it into the persisted OneNote-style board (lib/useWorkspaceBoard.ts)
  // alongside any notes, immediately visible in the Workspace column.
  onAddToWorkspace?: () => void;
  addedToWorkspace?: boolean;
}) {
  const chartData = draft.rows.slice(0, 20).map((r) => {
    const out: Record<string, unknown> = { _label: String(r[draft.labelColumn] ?? "") };
    draft.selectedColumns.forEach((c) => {
      out[c] = typeof r[c] === "number" ? r[c] : Number(r[c]) || 0;
    });
    return out;
  });

  const pieColumn = draft.selectedColumns[0];
  const pieData = pieColumn
    ? chartData.map((d) => ({ name: String(d._label), value: Number(d[pieColumn]) || 0 }))
    : [];

  return (
    <div className="flex-1 min-w-0 flex flex-col bg-black">
      <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800 shrink-0 bg-zinc-950">
        <div className="min-w-0">
          <div className="text-sm font-medium truncate">Visualize — {draft.sourceLabel}</div>
          <div className="text-[11px] text-zinc-600 truncate">
            {draft.department} → Reporting
          </div>
        </div>
        <button onClick={onClose} className="text-zinc-400 hover:text-white transition text-lg leading-none shrink-0 ml-3">
          ×
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        <div>
          <div className="text-[11px] uppercase tracking-wider text-zinc-600 mb-1.5">Chart type</div>
          <div className="flex gap-1.5">
            {CHART_TYPES.map((t) => (
              <button
                key={t.key}
                onClick={() => onChangeChartType(t.key)}
                className={
                  draft.chartType === t.key
                    ? "text-xs px-2.5 py-1.5 rounded-lg bg-zinc-200 text-black font-medium transition"
                    : "text-xs px-2.5 py-1.5 rounded-lg border border-zinc-800 text-zinc-400 hover:text-white hover:border-zinc-600 transition"
                }
              >
                {t.label}
              </button>
            ))}
          </div>
        </div>

        <div>
          <div className="text-[11px] uppercase tracking-wider text-zinc-600 mb-1.5">
            {draft.chartType === "pie" ? "Value column" : "Columns to plot"}
          </div>
          <div className="flex flex-wrap gap-1.5">
            {draft.numericColumns.map((c) => {
              const active = draft.selectedColumns.includes(c);
              // Pie only really makes sense with one series -- selecting a new column
              // while another is active swaps it rather than stacking, but the toggle
              // handler itself stays generic (owned by useVisualizationWorkspace).
              return (
                <button
                  key={c}
                  onClick={() => onToggleColumn(c)}
                  className={
                    active
                      ? "text-xs px-2.5 py-1 rounded-full bg-[#3FBCC4] text-black font-medium transition"
                      : "text-xs px-2.5 py-1 rounded-full border border-zinc-800 text-zinc-400 hover:text-white hover:border-zinc-600 transition"
                  }
                >
                  {prettify(c)}
                </button>
              );
            })}
          </div>
        </div>

        <div className="rounded-xl border border-zinc-800 bg-zinc-950 p-3" style={{ height: 260 }}>
          {draft.selectedColumns.length === 0 ? (
            <div className="h-full flex items-center justify-center text-xs text-zinc-600">
              Pick at least one column to plot.
            </div>
          ) : (
            <ResponsiveContainer>
              {draft.chartType === "pie" ? (
                <PieChart>
                  <Tooltip contentStyle={{ fontSize: 11, background: "#18181b", border: "1px solid #3f3f46" }} />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <Pie data={pieData} dataKey="value" nameKey="name" outerRadius={90} label={{ fontSize: 10 }}>
                    {pieData.map((_, i) => (
                      <Cell key={i} fill={SERIES_COLORS[i % SERIES_COLORS.length]} />
                    ))}
                  </Pie>
                </PieChart>
              ) : draft.chartType === "line" ? (
                <LineChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                  <XAxis
                    dataKey="_label"
                    tick={{ fontSize: 10, fill: "#a1a1aa" }}
                    interval={0}
                    angle={-30}
                    textAnchor="end"
                    height={50}
                  />
                  <YAxis tick={{ fontSize: 10, fill: "#a1a1aa" }} />
                  <Tooltip contentStyle={{ fontSize: 11, background: "#18181b", border: "1px solid #3f3f46" }} />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  {draft.selectedColumns.map((c, i) => (
                    <Line
                      key={c}
                      type="monotone"
                      dataKey={c}
                      stroke={SERIES_COLORS[i % SERIES_COLORS.length]}
                      strokeWidth={2}
                      dot={{ r: 2 }}
                    />
                  ))}
                </LineChart>
              ) : (
                <BarChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                  <XAxis
                    dataKey="_label"
                    tick={{ fontSize: 10, fill: "#a1a1aa" }}
                    interval={0}
                    angle={-30}
                    textAnchor="end"
                    height={50}
                  />
                  <YAxis tick={{ fontSize: 10, fill: "#a1a1aa" }} />
                  <Tooltip contentStyle={{ fontSize: 11, background: "#18181b", border: "1px solid #3f3f46" }} />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  {draft.selectedColumns.map((c, i) => (
                    <Bar key={c} dataKey={c} fill={SERIES_COLORS[i % SERIES_COLORS.length]} radius={[3, 3, 0, 0]} />
                  ))}
                </BarChart>
              )}
            </ResponsiveContainer>
          )}
        </div>

        <div className="text-[11px] text-zinc-600">
          {draft.rows.length} row{draft.rows.length === 1 ? "" : "s"} from this drop
          {draft.rows.length > 20 ? " (first 20 charted)" : ""}.
        </div>
      </div>

      <div className="border-t border-zinc-800 p-3 shrink-0 space-y-2">
        {onAddToWorkspace && (
          <button
            onClick={onAddToWorkspace}
            disabled={addedToWorkspace || draft.selectedColumns.length === 0}
            className="w-full text-sm px-3 py-2 rounded-lg border border-zinc-700 text-zinc-200 font-brand font-bold uppercase tracking-wide hover:border-zinc-500 hover:text-white transition disabled:opacity-40 disabled:cursor-default"
          >
            {addedToWorkspace ? "✓ Added to Workspace" : "+ Add to Workspace"}
          </button>
        )}

        <button
          onClick={onPin}
          disabled={pinned || draft.selectedColumns.length === 0}
          style={pinned ? undefined : angledClip(10)}
          className="w-full text-sm px-3 py-2 bg-brand-teal text-black font-brand font-bold uppercase tracking-wide hover:bg-[#5cd0d8] transition disabled:opacity-40 disabled:cursor-default rounded-lg"
        >
          {pinned ? "📌 Pinned to Knowledge" : "📌 Pin to Knowledge"}
        </button>
      </div>
    </div>
  );
}
