"use client";
import { WorkButton, WorkSelect , WorkStat} from "./WorkspaceUi";
import { WorkField } from "./WorkField";
import {PublishedWebsiteOffers} from "./PublishedWebsiteOffers";

// Sales' "Overview" item -- personalized section rendered ABOVE the existing generic
// Overview KPI board (Sam's own scoping answer, session 94 follow-up), not a
// replacement for it. Sam's Sales sub-menu spec: "My Tasks Widget (Leads requiring
// contact today, Appointments arriving within 2 hours, Missing follow-ups, Unsold
// showroom visits, Deals awaiting manager approval), Action Center (Call/Text/Email/
// Schedule Appointment/Create Deal/Transfer Lead per item), Daily Sales Dashboard,
// Sales Manager Dashboard."
//
// The Action Center reuses Prospects' real LeadRecordModal (Communication Hub,
// Convert to Customer + Create Deal, Transfer Lead) rather than a second, parallel
// per-lead action UI -- clicking any lead row here opens the exact same record.
import { PRODUCT_ACCENT_COLORS } from "@/lib/productTheme";
import { useEffect, useState } from "react";
import { getMyDay, type MyDay, type ActionItem } from "@/lib/salesOverview";
import { LeadRecordModal } from "@/components/ProspectsBoard";
import { claimTO, resolveTO, type TurnOver, type ToOutcome } from "@/lib/managerTo";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const RIBBON = PRODUCT_ACCENT_COLORS;

const TO_REASON_LABELS: Record<string, string> = {
  price: "Price",
  payment: "Payment",
  trade_value: "Trade Value",
  financing: "Financing",
  just_looking: "Just Looking",
  spouse_approval: "Spouse Approval",
  product_objection: "Product Objection",
  other: "Other",
};

const TO_OUTCOME_LABELS: Record<ToOutcome, string> = {
  saved: "Saved",
  lost: "Lost",
  escalated: "Escalated",
};

function fmt(ts: string | null | undefined): string {
  if (!ts) return "Never contacted";
  try {
    return new Date(ts).toLocaleString();
  } catch {
    return ts;
  }
}

function Kpi({ theme, label, value, color }: { theme: Theme; label: string; value: number | string; color: string }) { return <WorkStat label={label} value={value}/>; }

function LeadRow({ theme, item, onOpen }: { theme: Theme; item: ActionItem; onOpen: () => void }) {
  return (
    <button
      onClick={onOpen}
      className={tc(
        theme,
        "w-full text-left rounded-lg border border-black/20 bg-brand-charcoal p-2.5 flex items-center justify-between gap-2 hover:border-brand-blue/60 transition",
        "w-full text-left rounded-lg border border-zinc-200 bg-zinc-50 p-2.5 flex items-center justify-between gap-2 hover:border-brand-blue/60 transition"
      )}
    >
      <div className="min-w-0">
        <div className="text-xs font-medium truncate">{item.name || item.id}</div>
        <div className="text-xs text-zinc-500 truncate">{item.source || "—"} · {item.pipeline_state || "—"} · {fmt(item.last_contact)}</div>
      </div>
      <div className="flex items-center gap-1.5 shrink-0">
        {item.overdue_task_count > 0 && (
          <span className="text-xs px-1.5 py-0.5 rounded bg-red-950/40 text-red-300 border border-red-900">{item.overdue_task_count} overdue</span>
        )}
        <span className="text-xs text-zinc-500">📞 💬 ✉️</span>
      </div>
    </button>
  );
}

function Bucket({ theme, title, count, items, onOpenLead, emptyLabel }: { theme: Theme; title: string; count: number; items: ActionItem[]; onOpenLead: (id: string) => void; emptyLabel: string }) {
  return (
    <div>
      <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1.5">{title} ({count})</div>
      {items.length === 0 ? (
        <div className="text-xs text-zinc-600">{emptyLabel}</div>
      ) : (
        <div className="space-y-1.5 max-h-56 overflow-y-auto pr-0.5">
          {items.slice(0, 12).map((item) => (
            <LeadRow key={item.id} theme={theme} item={item} onOpen={() => onOpenLead(item.id)} />
          ))}
        </div>
      )}
    </div>
  );
}

function TORequestRow({
  theme,
  to,
  resolvingId,
  outcome,
  busy,
  onOpenResolve,
  onClaim,
  onOutcomeChange,
  onResolve,
}: {
  theme: Theme;
  to: TurnOver;
  resolvingId: string | null;
  outcome: ToOutcome;
  busy: boolean;
  onOpenResolve: (id: string | null) => void;
  onClaim: (id: string) => void;
  onOutcomeChange: (o: ToOutcome) => void;
  onResolve: (id: string) => void;
}) {
  return (
    <div className={tc(theme, "rounded-lg border border-black/20 bg-brand-charcoal p-2.5", "rounded-lg border border-zinc-200 bg-zinc-50 p-2.5")}>
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <div className="text-xs font-medium truncate">{to.linked_entity_label || to.linked_entity_id}</div>
          <div className="text-xs text-zinc-500 truncate">
            {TO_REASON_LABELS[to.reason] || to.reason} · requested by {to.requested_by_name || to.requested_by} · {fmt(to.requested_at)}
          </div>
          {to.status === "claimed" && (
            <div className="text-xs text-amber-400">Claimed by {to.claimed_by_name || to.claimed_by}</div>
          )}
        </div>
        <div className="flex gap-1.5 shrink-0">
          {to.status === "requested" && (
            <WorkButton type="submit"
              onClick={() => onClaim(to.id)}
              disabled={busy}
              className="text-xs px-2 py-1 rounded bg-zinc-200 text-black font-medium disabled:opacity-50"
            >
              Claim
            </WorkButton>
          )}
          <WorkButton type="submit"
            onClick={() => onOpenResolve(resolvingId === to.id ? null : to.id)}
            disabled={busy}
            className="text-xs px-2 py-1 rounded border border-emerald-800 text-emerald-400 disabled:opacity-50"
          >
            Resolve
          </WorkButton>
        </div>
      </div>

      {resolvingId === to.id && (
        <div className="flex items-center gap-1.5 mt-1.5 pt-1.5 border-t border-zinc-800">
          <WorkField label="Outcome"><WorkSelect
            value={outcome}
            onChange={(e) => onOutcomeChange(e.target.value as ToOutcome)}
            className="text-xs rounded border border-zinc-700 bg-black px-1.5 py-1 text-white"
          >
            {(Object.keys(TO_OUTCOME_LABELS) as ToOutcome[]).map((o) => (
              <option key={o} value={o}>{TO_OUTCOME_LABELS[o]}</option>
            ))}
          </WorkSelect></WorkField>
          <WorkButton type="submit" variant="primary" onClick={() => onResolve(to.id)} disabled={busy} className="text-xs px-2 py-1 rounded bg-brand-blue text-white font-medium disabled:opacity-50">
            Confirm Resolution
          </WorkButton>
        </div>
      )}
    </div>
  );
}

export function SalesOverviewBoard({ theme }: { theme: Theme }) {
  const [data, setData] = useState<MyDay | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [openLeadId, setOpenLeadId] = useState<string | null>(null);

  const [toBusy, setToBusy] = useState(false);
  const [resolvingToId, setResolvingToId] = useState<string | null>(null);
  const [toOutcome, setToOutcome] = useState<ToOutcome>("saved");

  function refresh() {
    setLoading(true);
    getMyDay()
      .then(setData)
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }

  useEffect(refresh, []);

  async function handleClaimTO(toId: string) {
    setToBusy(true);
    try {
      await claimTO(toId);
      refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setToBusy(false);
    }
  }

  async function handleResolveTO(toId: string) {
    setToBusy(true);
    try {
      await resolveTO(toId, toOutcome);
      setResolvingToId(null);
      refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setToBusy(false);
    }
  }

  if (loading) {
    return <div className="p-4 text-sm text-zinc-500">Loading your day…</div>;
  }

  if (error || !data) {
    return <div className="p-4 text-sm text-red-400">{error || "Unable to load Sales Overview."}</div>;
  }

  const { my_tasks, daily_dashboard, manager_dashboard, is_manager_view } = data;

  return (
    <div className={tc(theme, "bg-brand-ink text-white", "bg-white text-black")}>
      <div className="p-4 space-y-5 border-b border-zinc-800/60">
      <PublishedWebsiteOffers/>
        {/* Daily Sales Dashboard */}
        <div>
          <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1.5">Daily Sales Dashboard</div>
          <div className="grid grid-cols-4 gap-3">
            <Kpi theme={theme} label="Today's Leads" value={daily_dashboard.todays_leads.count} color={RIBBON[0]} />
            <Kpi theme={theme} label="Today's Shows" value={daily_dashboard.todays_shows.count} color={RIBBON[1]} />
            <Kpi theme={theme} label="Write-Ups Today" value={daily_dashboard.write_ups_today.count} color={RIBBON[2]} />
            <Kpi theme={theme} label="Deliveries Today" value={daily_dashboard.deliveries_today.count} color={RIBBON[3]} />
          </div>
        </div>

        {/* My Tasks Widget + Action Center */}
        <div className="grid grid-cols-3 gap-4">
          <Bucket theme={theme} title="Needs Contact Today" count={my_tasks.leads_requiring_contact_today.count} items={my_tasks.leads_requiring_contact_today.items} onOpenLead={setOpenLeadId} emptyLabel="Nothing needs contact right now." />
          <Bucket theme={theme} title="Missing Follow-Ups" count={my_tasks.missing_follow_ups.count} items={my_tasks.missing_follow_ups.items} onOpenLead={setOpenLeadId} emptyLabel="No overdue tasks." />
          <Bucket theme={theme} title="Unsold Showroom Visits" count={my_tasks.unsold_showroom_visits.count} items={my_tasks.unsold_showroom_visits.items} onOpenLead={setOpenLeadId} emptyLabel="No unsold showroom visits." />
        </div>

        {my_tasks.not_yet_tracked && Object.keys(my_tasks.not_yet_tracked).length > 0 && (
          <div className="text-xs text-zinc-600 space-y-0.5">
            {Object.entries(my_tasks.not_yet_tracked).map(([k, v]) => (
              <div key={k}>• {v}</div>
            ))}
          </div>
        )}

        {/* Sales Manager Dashboard */}
        {is_manager_view && manager_dashboard && (
          <div>
            <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1.5">Sales Manager Dashboard</div>
            <div className="grid grid-cols-5 gap-3">
              <Kpi theme={theme} label="Unworked Leads" value={manager_dashboard.unworked_leads.count} color={RIBBON[0]} />
              <Kpi theme={theme} label="Overdue Follow-Ups" value={manager_dashboard.overdue_follow_ups.count} color={RIBBON[1]} />
              <Kpi theme={theme} label="Deals Stuck in F&I" value={manager_dashboard.deals_stuck_in_fi.count} color={RIBBON[2]} />
              <Kpi theme={theme} label="Trades Awaiting Appraisal" value={manager_dashboard.trades_awaiting_appraisal.count} color={RIBBON[3]} />
              <Kpi theme={theme} label="Manager TO Needed" value={manager_dashboard.open_to_requests.count} color={RIBBON[0]} />
            </div>

            {manager_dashboard.open_to_requests.count > 0 && (
              <div className="mt-3">
                <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1.5">
                  Open TO Requests ({manager_dashboard.open_to_requests.count})
                  {manager_dashboard.open_to_requests.stats.save_rate_pct !== null && (
                    <span className="text-zinc-600 normal-case tracking-normal"> · {manager_dashboard.open_to_requests.stats.save_rate_pct}% save rate</span>
                  )}
                </div>
                <div className="space-y-1.5 max-h-56 overflow-y-auto pr-0.5">
                  {manager_dashboard.open_to_requests.requests.map((to) => (
                    <TORequestRow
                      key={to.id}
                      theme={theme}
                      to={to}
                      resolvingId={resolvingToId}
                      outcome={toOutcome}
                      busy={toBusy}
                      onOpenResolve={setResolvingToId}
                      onClaim={handleClaimTO}
                      onOutcomeChange={setToOutcome}
                      onResolve={handleResolveTO}
                    />
                  ))}
                </div>
              </div>
            )}

            {manager_dashboard.not_yet_tracked && Object.keys(manager_dashboard.not_yet_tracked).length > 0 && (
              <div className="text-xs text-zinc-600 mt-2 space-y-0.5">
                {Object.entries(manager_dashboard.not_yet_tracked).map(([k, v]) => (
                  <div key={k}>• {v}</div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {openLeadId && (
        <LeadRecordModal
          theme={theme}
          leadId={openLeadId}
          onClose={() => setOpenLeadId(null)}
          onChanged={refresh}
        />
      )}
    </div>
  );
}
