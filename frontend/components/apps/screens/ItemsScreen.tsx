"use client";

// DevHub Items screen (2026-10-24).
// Lists all programming schedule items with filter controls and inline status/progress updates.

import { useEffect, useState } from "react";
import { useAsync, WiredScreen, ListCard, Row, Badge, EmptyNote } from "./kit";
import {
  listItems, updateItem, setProgress, setStatus, assignItem, type PSItem,
  type ItemType, type Phase, type Status, type Priority, type Assignee,
  TYPE_ICONS, PRIORITY_COLORS, STATUS_COLORS, ASSIGNEE_LABELS, PHASE_ORDER,
} from "@/lib/programmingSchedule";
import { type AppDef, type AppScreen } from "@/lib/apps/registry";

const ITEMS_PER_PAGE = 20;
const PHASES: Phase[] = PHASE_ORDER;
const PRIORITIES: Priority[] = ["critical", "high", "medium", "low"];
const STATUSES: Status[] = ["todo", "in_progress", "in_review", "done", "blocked"];
const ASSIGNEES: Assignee[] = ["unassigned", "backend", "frontend", "devops", "sample"];

export function ItemsScreen({ app, screen }: { app: AppDef; screen: AppScreen }) {
  const [filters, setFilters] = useState<Record<string, string>>({});
  const { loading, error, data: items, reload } = useAsync<PSItem[]>(
    () => listItems(filters), [JSON.stringify(filters)]
  );

  const filtered = items || [];

  return (
    <WiredScreen
      app={app} screen={screen} loading={loading} error={error}
      children={
        <>
          <FilterBar filters={filters} setFilters={setFilters} />
          <ItemsList items={filtered} onUpdated={reload} app={app} />
          {filtered.length === 0 && !loading && (
            <EmptyNote>No items match these filters. Try adjusting or clearing them.</EmptyNote>
          )}
        </>
      }
      onRetry={reload}
    />
  );
}

function FilterBar({
  filters, setFilters,
}: {
  filters: Record<string, string>;
  setFilters: (f: Record<string, string>) => void;
}) {
  const hasFilter = Object.keys(filters).length > 0;
  return (
    <div className="flex flex-wrap gap-2">
      <SelectFilter
        label="Phase"
        options={PHASES}
        current={filters.phase}
        onChange={(v) => setFilters({ ...filters, phase: v })}
        placeholder="All phases"
      />
      <SelectFilter
        label="Type"
        options={["feature", "bug", "security", "tech-debt"]}
        current={filters.item_type}
        onChange={(v) => setFilters({ ...filters, item_type: v })}
        placeholder="All types"
      />
      <SelectFilter
        label="Status"
        options={STATUSES}
        current={filters.status}
        onChange={(v) => setFilters({ ...filters, status: v })}
        placeholder="All statuses"
      />
      <SelectFilter
        label="Assignee"
        options={ASSIGNEES}
        current={filters.assignee}
        onChange={(v) => setFilters({ ...filters, assignee: v })}
        placeholder="All assignees"
      />
      <SelectFilter
        label="Priority"
        options={PRIORITIES}
        current={filters.priority}
        onChange={(v) => setFilters({ ...filters, priority: v })}
        placeholder="All priorities"
      />
      {hasFilter && (
        <button
          onClick={() => setFilters({})}
          className="rounded-lg border border-white/20 px-3 py-1.5 text-xs text-zinc-300 hover:bg-white/5"
        >
          Clear all
        </button>
      )}
    </div>
  );
}

function SelectFilter({
  label, options, current, onChange, placeholder,
}: {
  label: string;
  options: string[];
  current?: string;
  onChange: (v: string) => void;
  placeholder: string;
}) {
  return (
    <select
      value={current || ""}
      onChange={(e) => onChange(e.target.value)}
      className="rounded-lg border border-white/20 bg-white/[0.05] px-3 py-1.5 text-xs text-white"
      title={label}
    >
      <option value="" className="bg-zinc-800">{placeholder}</option>
      {options.map((opt) => (
        <option key={opt} value={opt}>{opt}</option>
      ))}
    </select>
  );
}

function ItemsList({ items, onUpdated, app }: { items: PSItem[]; onUpdated: () => void; app: AppDef }) {
  const [updating, setUpdating] = useState<string | null>(null);

  const updateField = async (item: PSItem, field: string, value: unknown) => {
    setUpdating(item.id);
    try {
      await updateItem(item.id, { [field]: value } as Partial<PSItem>);
      onUpdated();
    } catch (e) {
      console.error(e);
    } finally {
      setUpdating(null);
    }
  };

  return (
    <div className="mt-4 space-y-3">
      {items.slice(0, ITEMS_PER_PAGE).map((item) => (
        <ItemRow key={item.id} item={item} updating={updating === item.id} onUpdated={updateField} app={app} />
      ))}
      {items.length > ITEMS_PER_PAGE && (
        <EmptyNote>Showing first {ITEMS_PER_PAGE} of {items.length} items.</EmptyNote>
      )}
    </div>
  );
}

function ItemRow({
  item, updating, onUpdated, app,
}: {
  item: PSItem;
  updating: boolean;
  onUpdated: (item: PSItem, field: string, value: unknown) => void | Promise<void>;
  app: AppDef;
}) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4 backdrop-blur-sm">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-lg">{TYPE_ICONS[item.type]}</span>
            <span className="font-medium text-white">{item.title}</span>
            <Badge app={app}>{item.phase}</Badge>
          </div>
          {item.description && (
            <p className="mt-1 text-xs text-zinc-400">{item.description}</p>
          )}
          <div className="mt-2 flex flex-wrap gap-2">
            <Badge app={app}>{item.type}</Badge>
            <span className={STATUS_COLORS[item.status]}>{item.status.replace("_", " ")}</span>
            <span className={PRIORITY_COLORS[item.priority]}>{item.priority}</span>
            {item.assignee !== "unassigned" && (
              <span className="text-xs text-zinc-300">
                → {ASSIGNEE_LABELS[item.assignee]}
              </span>
            )}
            {item.security_severity && (
              <span className={`text-xs font-medium ${
                item.security_severity === "critical" ? "text-red-400" :
                item.security_severity === "high" ? "text-orange-400" :
                "text-amber-400"
              }`}>Security: {item.security_severity}</span>
            )}
          </div>
          <div className="mt-2 flex items-center gap-3 text-xs text-zinc-500">
            <span>{item.progress}% complete</span>
            <span>{item.logged_hours.toFixed(1)}h / {item.est_hours.toFixed(0)}h est</span>
            {item.depends_on.length > 0 && (
              <span>depends on: {item.depends_on.join(", ")}</span>
            )}
          </div>
        </div>

        <QuickActions item={item} updating={updating} onUpdated={onUpdated} />
      </div>
    </div>
  );
}

function QuickActions({
  item, updating, onUpdated,
}: {
  item: PSItem;
  updating: boolean;
  onUpdated: (item: PSItem, field: string, value: unknown) => void | Promise<void>;
}) {
  if (item.status === "done") {
    return (
      <span className="text-xs text-emerald-400">✓ done</span>
    );
  }

  return (
    <div className="flex gap-1">
      <button
        onClick={() => {
          const next = item.status === "in_progress" ? "done" : "in_progress";
          onUpdated(item, "status", next);
        }}
        disabled={updating}
        className="rounded-lg border border-white/20 px-2 py-1 text-xs text-white hover:bg-white/5 disabled:opacity-50"
        title={item.status === "in_progress" ? "Mark done" : "Start working"}
      >
        {item.status === "in_progress" ? "✓" : "▶"}
      </button>
      <button
        onClick={() => {
          const newProgress = item.progress < 100 ? Math.min(100, item.progress + 25) : item.progress;
          onUpdated(item, "progress", newProgress);
        }}
        disabled={updating}
        className="rounded-lg border border-white/20 px-2 py-1 text-xs text-white hover:bg-white/5 disabled:opacity-50"
        title="Add 25% progress"
      >
        +25%
      </button>
    </div>
  );
}
