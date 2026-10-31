"use client";
import { WorkButton, WorkInput , WorkStat} from "./WorkspaceUi";
import { WorkField } from "./WorkField";

// Operations' "Alerts" item -- upgraded from a read-only exception report into
// a real nervous system (session 106 follow-up #7, "keep going" autonomous
// continuation, seventh slice of Operations' rebuild). Sam's spec: red/yellow
// severity, real actions, not just a list. Backend: core/operations_alerts.py
// / _api.py.
//
// Every card's action button calls a real backend mutation. Five alert types
// deep-link straight into an already-built engine (compliance resolve,
// document request, task escalate, delivery scheduling, price reduction);
// the two types with no prior action anywhere in this codebase
// (ownership_mismatch, stalled_deal) call acknowledgeAlert(), which creates a
// real, deduped OperationsTask -- clicking Acknowledge is what turns the
// alert into a trackable ticket.

import { useEffect, useState } from "react";
import {
  getAlertFeed,
  getAlertStats,
  acknowledgeAlert,
  resolveComplianceAlert,
  type Alert,
  type AlertFeed,
  type AlertStats,
} from "@/lib/operationsAlerts";
import { escalateOperationsTask } from "@/lib/operationsTasks";
import { scheduleDelivery } from "@/lib/operationsScheduling";
import { reduceVehiclePrice } from "@/lib/inventoryAging";
import { requestDocument } from "@/lib/documentWorkflows";
import { EntityHoverLink } from "@/components/EntityHoverLink";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const SEVERITY_TONE: Record<Alert["severity"], string> = {
  red: "border-red-900 bg-red-950/30",
  yellow: "border-amber-900 bg-amber-950/20",
};

const SEVERITY_BADGE: Record<Alert["severity"], string> = {
  red: "bg-red-900 text-red-200",
  yellow: "bg-amber-900 text-amber-200",
};

function Kpi({ theme, label, value, tone }: { theme: Theme; label: string; value: number | string; tone?: string }) { return <WorkStat label={label} value={value} tone={tone}/>; }

function ActionArea({
  theme,
  alert,
  onDone,
}: {
  theme: Theme;
  alert: Alert;
  onDone: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notes, setNotes] = useState("");
  const [priceInput, setPriceInput] = useState("");
  const [dateInput, setDateInput] = useState("");
  const [expanded, setExpanded] = useState(false);

  const inputClass = tc(theme, "bg-zinc-900 border-zinc-700 text-white placeholder:text-zinc-600", "bg-white border-zinc-300 text-black placeholder:text-zinc-400");

  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      onDone();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (alert.suggested_action === "acknowledge") {
    return (
      <div className="space-y-1.5">
        {error && <div className="text-xs text-red-400">{error}</div>}
        <WorkButton type="submit" variant="primary"
          disabled={busy}
          onClick={() => run(() => acknowledgeAlert(alert.alert_type, alert.source_id, "Acknowledged from Alerts feed"))}
          className="text-xs px-2.5 py-1.5 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50"
        >
          Acknowledge (creates a real task)
        </WorkButton>
      </div>
    );
  }

  if (alert.suggested_action === "escalate_task") {
    return (
      <div className="space-y-1.5">
        {error && <div className="text-xs text-red-400">{error}</div>}
        <WorkButton type="submit" variant="danger"
          disabled={busy}
          onClick={() => run(() => escalateOperationsTask(alert.source_id, "Escalated from Alerts feed"))}
          className="text-xs px-2.5 py-1.5 rounded bg-red-800 text-white font-medium hover:opacity-90 transition disabled:opacity-50"
        >
          Escalate Task
        </WorkButton>
      </div>
    );
  }

  if (alert.suggested_action === "request_deal_jacket") {
    return (
      <div className="space-y-1.5">
        {error && <div className="text-xs text-red-400">{error}</div>}
        <WorkButton type="submit" variant="primary"
          disabled={busy}
          onClick={() => run(() => requestDocument("Deal", alert.source_id, "Deal Jacket"))}
          className="text-xs px-2.5 py-1.5 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50"
        >
          Request Deal Jacket
        </WorkButton>
      </div>
    );
  }

  if (alert.suggested_action === "resolve_compliance") {
    return (
      <div className="space-y-1.5">
        {error && <div className="text-xs text-red-400">{error}</div>}
        {!expanded ? (
          <WorkButton type="submit" onClick={() => setExpanded(true)} className="text-xs px-2.5 py-1.5 rounded bg-green-800 text-white font-medium hover:opacity-90 transition">
            Resolve
          </WorkButton>
        ) : (
          <div className="flex items-center gap-1.5">
            <WorkField label="Resolution notes"><WorkInput value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Resolution notes…" className={`flex-1 rounded-md border px-2 py-1 text-xs ${inputClass}`} /></WorkField>
            <WorkButton type="submit" disabled={busy} onClick={() => run(() => resolveComplianceAlert(alert.source_id, notes))} className="text-xs px-2.5 py-1.5 rounded bg-green-800 text-white font-medium hover:opacity-90 transition disabled:opacity-50">
              Confirm
            </WorkButton>
          </div>
        )}
      </div>
    );
  }

  if (alert.suggested_action === "schedule_delivery") {
    return (
      <div className="space-y-1.5">
        {error && <div className="text-xs text-red-400">{error}</div>}
        {!expanded ? (
          <WorkButton type="submit" variant="primary" onClick={() => setExpanded(true)} className="text-xs px-2.5 py-1.5 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition">
            Schedule Delivery
          </WorkButton>
        ) : (
          <div className="flex items-center gap-1.5">
            <WorkField label="Due date"><WorkInput type="datetime-local" value={dateInput} onChange={(e) => setDateInput(e.target.value)} className={`rounded-md border px-2 py-1 text-xs ${inputClass}`} /></WorkField>
            <WorkButton type="submit" variant="primary"
              disabled={busy || !dateInput}
              onClick={() => run(() => scheduleDelivery(alert.source_id, new Date(dateInput).toISOString()))}
              className="text-xs px-2.5 py-1.5 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50"
            >
              Confirm
            </WorkButton>
          </div>
        )}
      </div>
    );
  }

  if (alert.suggested_action === "reduce_price") {
    return (
      <div className="space-y-1.5">
        {error && <div className="text-xs text-red-400">{error}</div>}
        {!expanded ? (
          <WorkButton type="submit" variant="primary" onClick={() => setExpanded(true)} className="text-xs px-2.5 py-1.5 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition">
            Reduce Price
          </WorkButton>
        ) : (
          <div className="flex items-center gap-1.5">
            <WorkField label="New price"><WorkInput type="number" value={priceInput} onChange={(e) => setPriceInput(e.target.value)} placeholder="New price…" className={`w-28 rounded-md border px-2 py-1 text-xs ${inputClass}`} /></WorkField>
            <WorkButton type="submit" variant="primary"
              disabled={busy || !priceInput}
              onClick={() => run(() => reduceVehiclePrice(alert.source_id, Number(priceInput), "Reduced from Alerts feed"))}
              className="text-xs px-2.5 py-1.5 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50"
            >
              Confirm
            </WorkButton>
          </div>
        )}
      </div>
    );
  }

  return null;
}

function AlertCard({ theme, alert, onDone }: { theme: Theme; alert: Alert; onDone: () => void }) {
  return (
    <div className={`rounded-lg border p-3 ${SEVERITY_TONE[alert.severity]}`}>
      <div className="flex items-start justify-between gap-2 mb-1">
        <div className="text-xs font-medium">{alert.title}</div>
        <span className={`text-xs px-1.5 py-0.5 rounded uppercase tracking-wide ${SEVERITY_BADGE[alert.severity]}`}>{alert.severity}</span>
      </div>
      <div className="text-xs text-zinc-400 mb-1.5">{alert.detail}</div>
      {alert.linked_entity_id && (
        <div className="text-xs text-zinc-600 mb-2">
          <EntityHoverLink id={alert.linked_entity_id} />
        </div>
      )}
      <ActionArea theme={theme} alert={alert} onDone={onDone} />
    </div>
  );
}

export function OperationsAlertsBoard({ theme }: { theme: Theme }) {
  const [feed, setFeed] = useState<AlertFeed | null>(null);
  const [stats, setStats] = useState<AlertStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [typeFilter, setTypeFilter] = useState<string>("all");

  function refresh() {
    setLoading(true);
    Promise.all([getAlertFeed(), getAlertStats()])
      .then(([f, s]) => {
        setFeed(f);
        setStats(s);
      })
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }

  useEffect(refresh, []);

  const wrapClass = tc(theme, "flex-1 flex flex-col min-h-0 bg-brand-ink text-white", "flex-1 flex flex-col min-h-0 bg-white text-black");

  if (loading && !feed) return <div className={wrapClass}><div className="p-4 text-sm text-zinc-500">Loading…</div></div>;

  const types = feed ? Array.from(new Set(feed.alerts.map((a) => a.alert_type))) : [];
  const visible = feed ? (typeFilter === "all" ? feed.alerts : feed.alerts.filter((a) => a.alert_type === typeFilter)) : [];

  return (
    <div className={wrapClass}>
      <div className="p-4 space-y-3 overflow-y-auto flex-1">
        {error && <div className="text-xs px-3 py-2 rounded-lg bg-red-500/15 border border-red-500/40 text-red-300">{error}</div>}
        <div className="text-xs text-zinc-600 italic">
          A unified, severity-ranked feed across every real exception signal this codebase computes -- compliance, ownership mismatches, stalled deals, missing deal jackets, overdue tasks, at-risk deliveries, and critical-band aging inventory. This is a triage list, not a status board -- an all-clear item isn't in it.
        </div>
        {stats && (
          <div className="grid grid-cols-4 gap-2">
            <Kpi theme={theme} label="Total" value={stats.total} />
            <Kpi theme={theme} label="Red" value={stats.red} tone="text-red-400" />
            <Kpi theme={theme} label="Yellow" value={stats.yellow} tone="text-amber-400" />
            <Kpi theme={theme} label="Types" value={Object.keys(stats.by_type).length} />
          </div>
        )}
        <div className="flex items-center gap-1.5 flex-wrap">
          <WorkButton type="submit"  onClick={() => setTypeFilter("all")} className={`text-xs px-2.5 py-1 rounded ${typeFilter === "all" ? "bg-brand-blue text-white" : "bg-zinc-800 text-zinc-300"}`}>All</WorkButton>
          {types.map((t) => (
            <WorkButton type="submit"  key={t} onClick={() => setTypeFilter(t)} className={`text-xs px-2.5 py-1 rounded ${typeFilter === t ? "bg-brand-blue text-white" : "bg-zinc-800 text-zinc-300"}`}>
              {t.replace(/_/g, " ")}
            </WorkButton>
          ))}
        </div>
        {visible.length === 0 ? (
          <div className="text-sm text-zinc-500 py-6 text-center">No open alerts{typeFilter !== "all" ? " of this type" : ""}. All clear.</div>
        ) : (
          <div className="grid grid-cols-2 gap-2">
            {visible.map((a, i) => (
              <AlertCard key={`${a.alert_type}-${a.source_id}-${i}`} theme={theme} alert={a} onDone={refresh} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
