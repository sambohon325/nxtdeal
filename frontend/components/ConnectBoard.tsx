"use client";
import { WorkSelect, WorkInput, WorkButton } from "./WorkspaceUi";
import { WorkField } from "./WorkField";

// ConnectBoard — the NXTDeal Connect dashboard (Connect slice 6b, 2026-07-24).
// Sam's spec: "NXTDeal Connect is the communications and customer engagement layer...
// Unified Inbox... Customer Timeline... Communications Analytics." This board reads the three
// /connect/* views: an analytics rollup (channel mix, AI-vs-human split, sentiment + average
// conversation score across every channel), one filterable inbox across every channel with each
// touch flagged AI-handled and carrying its rules-based sentiment/score, and a per-customer
// timeline (communications merged with the appointments booked off them) drilled into by
// clicking an inbox item's linked entity. Read-only — Connect composes the Communications
// already logged; it fabricates nothing. Reads through lib/connect.ts; same styling vocabulary
// (RIBBON palette, theme-aware tc() classes) as FleetBoard.tsx / AiWorkforceBoard.tsx.

import { PRODUCT_ACCENT_COLORS } from "@/lib/productTheme";
import { useEffect, useState } from "react";
import {
  fetchInbox,
  fetchTimeline,
  fetchConnectAnalytics,
  type Inbox,
  type InboxItem,
  type Timeline,
  type ConnectAnalytics,
  type Sentiment,
} from "@/lib/connect";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const RIBBON = PRODUCT_ACCENT_COLORS;

const SENTIMENT_COLOR: Record<Sentiment, string> = {
  positive: "#22c55e",
  neutral: "#71717a",
  at_risk: "#FBCF09",
  escalation: "#EE3C25",
};

const SENTIMENT_LABEL: Record<Sentiment, string> = {
  positive: "Positive",
  neutral: "Neutral",
  at_risk: "At Risk",
  escalation: "Escalation",
};

const SENTIMENTS: Sentiment[] = ["positive", "neutral", "at_risk", "escalation"];

function fmt(ts: string | null | undefined): string {
  if (!ts) return "—";
  try {
    return new Date(ts).toLocaleString([], {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  } catch {
    return ts;
  }
}

function cap(s: string | null | undefined): string {
  if (!s) return "—";
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function Tile({
  theme,
  value,
  label,
  accent,
}: {
  theme: Theme;
  value: number | string;
  label: string;
  accent: string;
}) {
  return (
    <div
      className={`rounded-lg border p-3 ${tc(theme, "border-white/10 bg-white/[0.03]", "border-black/10 bg-black/[0.02]")}`}
      style={{ borderLeft: `3px solid ${accent}` }}
    >
      <div className={`text-2xl font-semibold ${tc(theme, "text-white", "text-gray-900")}`}>{value}</div>
      <div className={`mt-1 text-xs font-brand uppercase tracking-wide ${tc(theme, "text-gray-400", "text-gray-500")}`}>
        {label}
      </div>
    </div>
  );
}

function SentimentBadge({ sentiment }: { sentiment?: Sentiment }) {
  if (!sentiment) return null;
  return (
    <span
      className="rounded-full px-2 py-0.5 text-xs font-semibold uppercase tracking-wide text-white"
      style={{ backgroundColor: SENTIMENT_COLOR[sentiment] }}
    >
      {SENTIMENT_LABEL[sentiment]}
    </span>
  );
}

export function ConnectBoard({ theme, hideHeading=false }: { theme: Theme; hideHeading?:boolean }) {
  const [analytics, setAnalytics] = useState<ConnectAnalytics | null>(null);
  const [inbox, setInbox] = useState<Inbox | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Inbox filters.
  const [channel, setChannel] = useState<string>("");
  const [direction, setDirection] = useState<string>("");
  const [aiOnly, setAiOnly] = useState(false);

  // Timeline drill-down.
  const [timelineEntity, setTimelineEntity] = useState<string | null>(null);
  const [timeline, setTimeline] = useState<Timeline | null>(null);
  const [timelineLoading, setTimelineLoading] = useState(false);

  async function loadAll() {
    setLoading(true);
    setError(null);
    try {
      const [a, i] = await Promise.all([
        fetchConnectAnalytics(),
        fetchInbox({
          channel: channel || undefined,
          direction: direction || undefined,
          ai_only: aiOnly || undefined,
          limit: 100,
        }),
      ]);
      setAnalytics(a);
      setInbox(i);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to load NXTDeal Connect.");
    } finally {
      setLoading(false);
    }
  }

  // Refetch the inbox when a filter changes (analytics is filter-independent).
  async function loadInbox() {
    try {
      setInbox(
        await fetchInbox({
          channel: channel || undefined,
          direction: direction || undefined,
          ai_only: aiOnly || undefined,
          limit: 100,
        })
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to load the inbox.");
    }
  }

  useEffect(() => {
    loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!loading) loadInbox();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [channel, direction, aiOnly]);

  async function openTimeline(entityId: string) {
    setTimelineEntity(entityId);
    setTimelineLoading(true);
    try {
      setTimeline(await fetchTimeline(entityId));
    } catch {
      setTimeline(null);
    } finally {
      setTimelineLoading(false);
    }
  }

  const cardBase = tc(theme, "border-white/10 bg-white/[0.03]", "border-black/10 bg-white");
  const subtle = tc(theme, "text-gray-400", "text-gray-500");
  const heading = tc(theme, "text-white", "text-gray-900");

  const filterSelect = `rounded-md border px-2 py-1 text-xs ${tc(theme, "border-white/20 bg-transparent text-gray-200", "border-black/20 bg-white text-gray-700")}`;

  return (
    <div className="space-y-5">
      <div>
        {!hideHeading && <h2 className={`text-xl font-semibold ${heading}`}>NXTDeal Connect</h2>}
        <p className={`mt-1 text-sm ${subtle}`}>
          Every customer interaction in one place — a unified inbox across phone, SMS, email,
          chat and social, a per-customer timeline, and analytics that split AI-handled from
          human-handled touches. Read-only: Connect composes the communications already logged,
          and its sentiment/score are a transparent rules-based rubric, never fabricated.
        </p>
      </div>

      {loading ? (
        <div className={`text-sm ${subtle}`}>Loading NXTDeal Connect…</div>
      ) : error ? (
        <div className="rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-400">
          {error}
        </div>
      ) : (
        <>
          {analytics && (
            <>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
                <Tile theme={theme} value={analytics.communications.total_communications} label="Total Touches" accent={RIBBON[0]} />
                <Tile theme={theme} value={analytics.ai_handled} label="AI-Handled" accent={RIBBON[1]} />
                <Tile theme={theme} value={analytics.human_handled} label="Human-Handled" accent={RIBBON[0]} />
                <Tile theme={theme} value={analytics.communications.open_follow_ups} label="Open Follow-Ups" accent={RIBBON[3]} />
                <Tile theme={theme} value={analytics.intelligence.avg_score ?? "—"} label="Avg Conv. Score" accent={RIBBON[2]} />
                <Tile theme={theme} value={analytics.workforce.active_workers} label="Active AI Workers" accent={RIBBON[1]} />
              </div>

              {/* Sentiment mix + channel breakdown. */}
              <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
                <div className={`rounded-lg border p-4 ${cardBase}`}>
                  <h3 className={`mb-3 text-sm font-semibold ${heading}`}>Sentiment mix (all channels)</h3>
                  <div className="space-y-2">
                    {SENTIMENTS.map((s) => {
                      const n = analytics.intelligence.sentiment[s] ?? 0;
                      const total = analytics.intelligence.total_analyzed || 1;
                      const pct = Math.round((n / total) * 100);
                      return (
                        <div key={s} className="flex items-center gap-2">
                          <span className={`w-20 text-xs ${subtle}`}>{SENTIMENT_LABEL[s]}</span>
                          <div className={`h-2 flex-1 overflow-hidden rounded-full ${tc(theme, "bg-white/10", "bg-black/10")}`}>
                            <div className="h-full rounded-full" style={{ width: `${pct}%`, backgroundColor: SENTIMENT_COLOR[s] }} />
                          </div>
                          <span className={`w-10 text-right text-xs ${subtle}`}>{n}</span>
                        </div>
                      );
                    })}
                  </div>
                </div>

                <div className={`rounded-lg border p-4 ${cardBase}`}>
                  <h3 className={`mb-3 text-sm font-semibold ${heading}`}>Touches by channel</h3>
                  <div className="space-y-2">
                    {Object.entries(analytics.communications.by_channel).map(([ch, n]) => {
                      const total = analytics.communications.total_communications || 1;
                      const pct = Math.round((n / total) * 100);
                      return (
                        <div key={ch} className="flex items-center gap-2">
                          <span className={`w-20 text-xs ${subtle}`}>{cap(ch)}</span>
                          <div className={`h-2 flex-1 overflow-hidden rounded-full ${tc(theme, "bg-white/10", "bg-black/10")}`}>
                            <div className="h-full rounded-full" style={{ width: `${pct}%`, backgroundColor: RIBBON[0] }} />
                          </div>
                          <span className={`w-10 text-right text-xs ${subtle}`}>{n}</span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
            </>
          )}

          {/* Inbox filters. */}
          <div className="flex flex-wrap items-center gap-2">
            <WorkField label="Channel"><WorkSelect value={channel} onChange={(e) => setChannel(e.target.value)} className={filterSelect}>
              <option value="">All channels</option>
              {(inbox?.channels ?? []).map((ch) => (
                <option key={ch} value={ch}>
                  {cap(ch)}
                </option>
              ))}
            </WorkSelect></WorkField>
            <WorkField label="Direction"><WorkSelect value={direction} onChange={(e) => setDirection(e.target.value)} className={filterSelect}>
              <option value="">Both directions</option>
              <option value="inbound">Inbound</option>
              <option value="outbound">Outbound</option>
            </WorkSelect></WorkField>
            <label className={`flex items-center gap-1.5 text-xs ${subtle}`}>
              <WorkInput type="checkbox" checked={aiOnly} onChange={(e) => setAiOnly(e.target.checked)} />
              AI-handled only
            </label>
            {inbox && (
              <span className={`ml-auto text-xs ${subtle}`}>
                Showing {inbox.count} of {inbox.total_matching}
              </span>
            )}
          </div>

          {/* Unified inbox. */}
          <div className="space-y-2">
            {inbox && inbox.items.length === 0 ? (
              <div className={`rounded-lg border p-4 text-sm ${cardBase} ${subtle}`}>
                No communications match these filters yet.
              </div>
            ) : (
              inbox?.items.map((item: InboxItem) => (
                <div key={item.id} className={`rounded-lg border p-3 ${cardBase}`}>
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span
                          className={`rounded px-1.5 py-0.5 text-xs font-semibold uppercase tracking-wide ${tc(theme, "bg-white/10 text-gray-100", "bg-black/[0.06] text-gray-800")}`}
                        >
                          {cap(item.channel)}
                        </span>
                        <span className={`text-xs ${subtle}`}>{cap(item.direction)}</span>
                        {item.department ? <span className={`text-xs ${subtle}`}>· {item.department}</span> : null}
                        {item.handled_by_ai && (
                          <span
                            className="rounded px-1.5 py-0.5 text-xs font-semibold uppercase tracking-wide text-white"
                            style={{ backgroundColor: RIBBON[1] }}
                          >
                            AI · {item.ai_worker_role}
                          </span>
                        )}
                        <SentimentBadge sentiment={item.intelligence?.sentiment} />
                      </div>
                      <p className={`mt-1.5 truncate text-sm ${tc(theme, "text-gray-200", "text-gray-800")}`}>
                        {item.ai_summary || item.body || "—"}
                      </p>
                    </div>
                    <div className="shrink-0 text-right">
                      <div className={`text-xs ${subtle}`}>{fmt(item.created_at)}</div>
                      {item.linked_entity_id && (
                        <WorkButton
                          type="button"
                          onClick={() => openTimeline(item.linked_entity_id!)}
                          className="mt-1 text-xs font-semibold hover:underline"
                          style={{ color: RIBBON[0] }}
                        >
                          Timeline →
                        </WorkButton>
                      )}
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>

          {/* Customer timeline drill-down. */}
          {timelineEntity && (
            <div className={`rounded-lg border p-4 ${cardBase}`}>
              <div className="mb-3 flex items-center justify-between">
                <h3 className={`text-sm font-semibold ${heading}`}>
                  Customer timeline — {timelineEntity}
                </h3>
                <WorkButton
                  type="button"
                  onClick={() => {
                    setTimelineEntity(null);
                    setTimeline(null);
                  }}
                  className={`text-xs ${subtle} hover:underline`}
                >
                  Close
                </WorkButton>
              </div>
              {timelineLoading ? (
                <div className={`text-sm ${subtle}`}>Loading timeline…</div>
              ) : !timeline || timeline.events.length === 0 ? (
                <div className={`text-sm ${subtle}`}>No events linked to this customer yet.</div>
              ) : (
                <div className="space-y-2">
                  {timeline.events.map((ev, idx) => (
                    <div
                      key={`${ev.ref_id}-${idx}`}
                      className={`flex items-start gap-3 rounded-md border p-2 ${tc(theme, "border-white/10 bg-white/[0.02]", "border-black/10 bg-black/[0.02]")}`}
                    >
                      <span
                        className="mt-0.5 rounded px-1.5 py-0.5 text-xs font-semibold uppercase tracking-wide"
                        style={{
                          backgroundColor: ev.kind === "appointment" ? RIBBON[2] : RIBBON[0],
                          color: ev.kind === "appointment" ? "#1a1a1a" : "#ffffff",
                        }}
                      >
                        {ev.kind === "appointment" ? "Appt" : cap(ev.channel) || "Msg"}
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className={`truncate text-sm ${tc(theme, "text-gray-200", "text-gray-800")}`}>
                          {ev.summary || "—"}
                        </p>
                        <div className={`mt-0.5 flex flex-wrap items-center gap-1.5 text-xs ${subtle}`}>
                          {ev.direction ? <span>{cap(ev.direction)}</span> : null}
                          {ev.handled_by_ai && ev.ai_worker_role ? <span>· AI · {ev.ai_worker_role}</span> : null}
                          <SentimentBadge sentiment={ev.sentiment} />
                          <span>· {fmt(ev.at)}</span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
