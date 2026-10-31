"use client";
import { WorkButton , WorkStat} from "./WorkspaceUi";
import {RecordCollection} from "./RecordCollection";

// Sales' "Communications" item -- a real unified inbox (session 98 follow-up).
// Aggregates the Communication Hub log built for Prospects (session 92) across
// every lead in the department, plus the real follow-up cadence queue and
// marketing-compliance alerts. Honest framing: this is a real, staff-logged history
// of customer touches -- not an automated call-recording/SMS/email-provider
// integration (this codebase has no telephony/SMS/email-provider connection
// anywhere). Mass messaging/templates live in Marketing's Email/SMS CRM, reused
// rather than duplicated here.
import { PRODUCT_ACCENT_COLORS } from "@/lib/productTheme";
import { useEffect, useState } from "react";
import { getCommunicationsSummary, type CommunicationsSummary, type InboxItem } from "@/lib/communications";
import { LeadRecordModal } from "@/components/ProspectsBoard";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const RIBBON = PRODUCT_ACCENT_COLORS;

const CHANNEL_LABELS: Record<string, string> = { call: "📞 Call", text: "💬 Text", email: "✉️ Email", video: "🎥 Video" };

function fmt(ts: string | null | undefined): string {
  if (!ts) return "—";
  try {
    return new Date(ts).toLocaleString();
  } catch {
    return ts;
  }
}

function Kpi({ theme, label, value, color }: { theme: Theme; label: string; value: number; color: string }) { return <WorkStat label={label} value={value}/>; }

function InboxRow({ theme, item, onOpen }: { theme: Theme; item: InboxItem; onOpen: () => void }) {
  return (
    <button
      onClick={onOpen}
      className={tc(
        theme,
        "w-full text-left rounded-lg border border-black/20 bg-brand-charcoal p-2.5 flex items-start gap-2 hover:border-brand-blue/60 transition",
        "w-full text-left rounded-lg border border-zinc-200 bg-zinc-50 p-2.5 flex items-start gap-2 hover:border-brand-blue/60 transition"
      )}
    >
      <span className="text-sm shrink-0">{(CHANNEL_LABELS[item.category] || item.category).split(" ")[0]}</span>
      <div className="min-w-0 flex-1">
        <div className="text-xs font-medium truncate">{item.linked_entity_name || item.linked_entity_id}</div>
        <div className="text-xs text-zinc-400 truncate mt-0.5">{item.body}</div>
        <div className="text-xs text-zinc-500 mt-0.5">{item.created_by} · {fmt(item.created_at)}</div>
      </div>
    </button>
  );
}

export function CommunicationsBoard({ theme }: { theme: Theme }) {
  const [summary, setSummary] = useState<CommunicationsSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [channelFilter, setChannelFilter] = useState<string | null>(null);
  const [openLeadId, setOpenLeadId] = useState<string | null>(null);

  function refresh() {
    setLoading(true);
    getCommunicationsSummary()
      .then(setSummary)
      .catch(() => setSummary(null))
      .finally(() => setLoading(false));
  }

  useEffect(refresh, []);

  const byChannel = summary?.unified_inbox.by_channel || {};
  const items = summary?.unified_inbox.items || [];
  const filtered = channelFilter ? items.filter((i) => i.category === channelFilter) : items;

  const overdueFollowUps = (summary?.follow_up_cadence_queue.items || []).filter(
    (f) => f.current_state && !["SOLD", "LOST"].includes(f.current_state)
  );

  return (
    <div className={tc(theme, "flex-1 flex flex-col min-h-0 bg-brand-ink text-white", "flex-1 flex flex-col min-h-0 bg-white text-black")}>
      <div className={tc(theme, "grid grid-cols-4 gap-3 p-4 border-b border-zinc-800", "grid grid-cols-4 gap-3 p-4 border-b border-zinc-200")}>
        <Kpi theme={theme} label="Calls Logged" value={byChannel.call || 0} color={RIBBON[0]} />
        <Kpi theme={theme} label="Texts Logged" value={byChannel.text || 0} color={RIBBON[1]} />
        <Kpi theme={theme} label="Emails Logged" value={byChannel.email || 0} color={RIBBON[2]} />
        <Kpi theme={theme} label="Follow-Ups Due" value={overdueFollowUps.length} color={RIBBON[3]} />
      </div>

      <div className={tc(theme, "border-b border-zinc-800 px-4 py-2 flex items-center gap-1.5", "border-b border-zinc-200 px-4 py-2 flex items-center gap-1.5")}>
        {(["call", "text", "email", "video"] as const).map((c) => (
          <WorkButton type="submit"
            key={c}
            onClick={() => setChannelFilter(channelFilter === c ? null : c)}
            className={
              channelFilter === c
                ? "text-xs px-2.5 py-1 rounded-md bg-zinc-200 text-black font-medium transition"
                : tc(theme, "text-xs px-2.5 py-1 rounded-md text-zinc-400 hover:text-white hover:bg-zinc-900 transition", "text-xs px-2.5 py-1 rounded-md text-zinc-600 hover:text-black hover:bg-zinc-200 transition")
            }
          >
            {CHANNEL_LABELS[c]} ({byChannel[c] || 0})
          </WorkButton>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-5">
        {loading ? (
          <div className="text-sm text-zinc-500">Loading…</div>
        ) : (
          <>
            <div>
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1.5">
                Unified Inbox ({filtered.length})
              </div>
              {filtered.length === 0 ? (
                <div className="text-xs text-zinc-600">No communications logged yet.</div>
              ) : (
                <div className="space-y-1.5">
                  <RecordCollection>{filtered.map((item) => (
                    <InboxRow key={item.id} theme={theme} item={item} onOpen={() => item.linked_entity_id && setOpenLeadId(item.linked_entity_id)} />
                  ))}</RecordCollection>
                </div>
              )}
            </div>

            <div>
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1.5">
                Follow-Up Cadence Queue ({overdueFollowUps.length})
              </div>
              {overdueFollowUps.length === 0 ? (
                <div className="text-xs text-zinc-600">Nothing overdue for outreach.</div>
              ) : (
                <div className="grid grid-cols-2 gap-2">
                  <RecordCollection>{overdueFollowUps.map((f) => (
                    <button
                      key={f.lead_id}
                      onClick={() => setOpenLeadId(f.lead_id)}
                      className={tc(theme, "text-left rounded-lg border border-black/20 bg-brand-charcoal p-2.5 hover:border-brand-blue/60 transition", "text-left rounded-lg border border-zinc-200 bg-zinc-50 p-2.5 hover:border-brand-blue/60 transition")}
                    >
                      <div className="text-xs font-medium truncate">{f.name || f.lead_id}</div>
                      <div className="text-xs text-zinc-500">{f.current_state} · {f.days_in_state}d in state</div>
                    </button>
                  ))}</RecordCollection>
                </div>
              )}
            </div>

            <div>
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1.5">
                Compliance Logs ({summary?.compliance_logs.count ?? 0})
              </div>
              {(summary?.compliance_logs.alerts.length ?? 0) === 0 ? (
                <div className="text-xs text-zinc-600">No open marketing-compliance alerts (or your role doesn't have access to compliance data).</div>
              ) : (
                <div className="space-y-1.5">
                  <RecordCollection>{summary!.compliance_logs.alerts.map((a) => (
                    <div key={a.id} className={tc(theme, "rounded-lg border border-black/20 bg-brand-charcoal p-2.5 text-xs", "rounded-lg border border-zinc-200 bg-zinc-50 p-2.5 text-xs")}>
                      <div className="font-medium">{a.law || a.id}</div>
                      <div className="text-xs text-zinc-500 mt-0.5">{a.description}</div>
                    </div>
                  ))}</RecordCollection>
                </div>
              )}
            </div>

            {summary?.not_yet_tracked && Object.keys(summary.not_yet_tracked).length > 0 && (
              <div className="text-xs text-zinc-600 space-y-0.5">
                {Object.entries(summary.not_yet_tracked).map(([k, v]) => (
                  <div key={k}>• {v}</div>
                ))}
              </div>
            )}
          </>
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
