"use client";
import { WorkButton, WorkInput, WorkSelect, WorkTextarea , WorkStat} from "./WorkspaceUi";

// Operations' new "Communications" Top Menu item -- the Unified Communications
// Hub (2026-07-19). Composes real, already-logged customer-facing touches from
// Sales' Communication Hub, Service's RO Communication Center, and Finance's
// Collections contact log into one real, filterable, cross-department feed --
// a staff-facing mirror of the Customer Intelligence Layer's own merged
// Customer 360 Timeline. Read-only -- logging a new touch still happens
// through each department's own dedicated screen.
import { PRODUCT_ACCENT_COLORS } from "@/lib/productTheme";
import { useEffect, useMemo, useState } from "react";
import {
  getUnifiedCommunicationsOverview,
  type UnifiedCommunicationsOverview,
  type CommTouch,
} from "@/lib/unifiedCommunications";
import {
  getCommunicationsHubOverview,
  logCommunication,
  completeFollowUp,
  generateAiSummary,
  COMM_CHANNELS,
  COMM_DIRECTIONS,
  type CommunicationsHubOverview,
  type Communication,
  type CommChannel,
  type CommDirection,
  type LogCommunicationInput,
} from "@/lib/communicationsHub";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const RIBBON = PRODUCT_ACCENT_COLORS;

const CHANNEL_ICON: Record<string, string> = {
  call: "📞",
  text: "💬",
  email: "✉️",
  video: "🎥",
  phone: "📞",
  chat: "💬",
  social: "📱",
};

const SENTIMENT_COLOR: Record<string, string> = {
  positive: "#3FBCC4",
  neutral: "#9CA3AF",
  negative: "#EE3C25",
};

function fmt(ts: string | null | undefined): string {
  if (!ts) return "—";
  try {
    return new Date(ts).toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  } catch {
    return ts;
  }
}

function Kpi({ theme, label, value, color }: { theme: Theme; label: string; value: string; color: string }) { return <WorkStat label={label} value={value}/>; }

function TouchRow({ theme, touch }: { theme: Theme; touch: CommTouch }) {
  return (
    <div className={tc(theme, "rounded-lg border border-zinc-800 bg-brand-charcoal p-3", "rounded-lg border border-zinc-200 bg-zinc-50 p-3")}>
      <div className="flex items-center justify-between gap-2 mb-1">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-base">{CHANNEL_ICON[touch.channel ?? ""] ?? "📝"}</span>
          <span className="text-xs font-brand uppercase tracking-wide text-zinc-500">{touch.department ?? "—"}</span>
          <span className="text-xs text-zinc-500">·</span>
          <span className="text-xs text-zinc-400 capitalize">{touch.channel ?? "note"}</span>
        </div>
        <span className="text-xs text-zinc-500 whitespace-nowrap">{fmt(touch.created_at)}</span>
      </div>
      {touch.linked_entity_label && (
        <div className="text-xs font-medium text-zinc-200 mb-1 truncate">{touch.linked_entity_label}</div>
      )}
      <div className="text-xs text-zinc-400 whitespace-pre-wrap break-words">{touch.body}</div>
      {touch.created_by && <div className="text-xs text-zinc-600 mt-1">Logged by {touch.created_by}</div>}
    </div>
  );
}

function HubCommCard({
  theme,
  comm,
  onGenerateSummary,
  onCompleteFollowUp,
  summaryBusy,
  followUpBusy,
}: {
  theme: Theme;
  comm: Communication;
  onGenerateSummary: (commId: string) => void;
  onCompleteFollowUp: (commId: string) => void;
  summaryBusy: boolean;
  followUpBusy: boolean;
}) {
  const rec = comm.recording;
  return (
    <div className={tc(theme, "rounded-lg border border-zinc-800 bg-brand-charcoal p-3", "rounded-lg border border-zinc-200 bg-zinc-50 p-3")}>
      <div className="flex items-center justify-between gap-2 mb-1">
        <div className="flex items-center gap-2 min-w-0 flex-wrap">
          <span className="text-base">{CHANNEL_ICON[comm.channel] ?? "📝"}</span>
          <span className="text-xs font-brand uppercase tracking-wide text-zinc-500">{comm.department ?? "—"}</span>
          <span className="text-xs text-zinc-500">·</span>
          <span className="text-xs text-zinc-400 capitalize">{comm.channel}</span>
          <span className="text-xs text-zinc-500">·</span>
          <span className="text-xs text-zinc-400 capitalize">{comm.direction}</span>
        </div>
        <span className="text-xs text-zinc-500 whitespace-nowrap">{fmt(comm.created_at)}</span>
      </div>

      {comm.linked_entity_id && <div className="text-xs text-zinc-500 mb-1">Linked to {comm.linked_entity_id}</div>}

      <div className="text-xs text-zinc-400 whitespace-pre-wrap break-words">{comm.body}</div>
      {comm.created_by && <div className="text-xs text-zinc-600 mt-1">Logged by {comm.created_by}</div>}

      {rec && (
        <div className={tc(theme, "mt-2 rounded-md border border-zinc-700 bg-black/20 p-2", "mt-2 rounded-md border border-zinc-300 bg-white p-2")}>
          <div className="flex items-center justify-between gap-2">
            <span className="text-xs font-brand uppercase tracking-wide text-zinc-500">
              📼 Simulated Call Recording — {rec.duration_seconds}s
            </span>
            <span
              className="text-xs font-brand uppercase tracking-wide capitalize"
              style={{ color: SENTIMENT_COLOR[rec.sentiment_label] ?? "#9CA3AF" }}
            >
              {rec.sentiment_label} ({rec.sentiment_score.toFixed(2)})
            </span>
          </div>
          <div className="text-xs text-zinc-400 italic mt-1 whitespace-pre-wrap break-words">&quot;{rec.transcript}&quot;</div>
          <div className="text-xs text-zinc-600 mt-1">{rec.disclaimer}</div>
        </div>
      )}

      {comm.follow_up?.required && (
        <div
          className={tc(
            theme,
            "mt-2 flex items-center justify-between gap-2 rounded-md border border-yellow-700/40 bg-yellow-500/5 p-2",
            "mt-2 flex items-center justify-between gap-2 rounded-md border border-yellow-300 bg-yellow-50 p-2"
          )}
        >
          <div className="text-xs text-zinc-300 min-w-0">
            <span className="font-brand uppercase tracking-wide text-xs text-yellow-500 mr-1">
              {comm.follow_up.completed ? "Follow-up completed" : "Follow-up due"}
            </span>
            {comm.follow_up.due_at && <span className="text-zinc-500">{fmt(comm.follow_up.due_at)}</span>}
            {comm.follow_up.note && <div className="text-zinc-500 truncate">{comm.follow_up.note}</div>}
          </div>
          {!comm.follow_up.completed && (
            <WorkButton type="submit"
              onClick={() => onCompleteFollowUp(comm.id)}
              disabled={followUpBusy}
              className="text-xs px-2 py-1 rounded-full bg-zinc-200 text-black font-medium disabled:opacity-50 whitespace-nowrap"
            >
              {followUpBusy ? "…" : "✓ Complete"}
            </WorkButton>
          )}
        </div>
      )}

      <div className="mt-2">
        {comm.ai_summary ? (
          <div className={tc(theme, "rounded-md border border-zinc-700 bg-black/20 p-2", "rounded-md border border-zinc-300 bg-white p-2")}>
            <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1">
              🤖 AI Summary {comm.ai_summary.ai_generated ? "" : "(fallback)"}
            </div>
            <div className="text-xs text-zinc-300">{comm.ai_summary.summary}</div>
            {comm.ai_summary.key_points?.length > 0 && (
              <ul className="text-xs text-zinc-500 list-disc list-inside mt-1">
                {comm.ai_summary.key_points.map((kp, i) => (
                  <li key={i}>{kp}</li>
                ))}
              </ul>
            )}
            {comm.ai_summary.suggested_follow_up && (
              <div className="text-xs text-zinc-500 mt-1 italic">Suggested follow-up: {comm.ai_summary.suggested_follow_up}</div>
            )}
          </div>
        ) : (
          <WorkButton type="submit"
            onClick={() => onGenerateSummary(comm.id)}
            disabled={summaryBusy}
            className="text-xs px-2.5 py-1 rounded-full bg-zinc-200/10 text-zinc-400 hover:text-white disabled:opacity-50"
          >
            {summaryBusy ? "Generating…" : "✨ Generate AI Summary"}
          </WorkButton>
        )}
      </div>
    </div>
  );
}

export function OperationsCommunicationsBoard({ theme }: { theme: Theme }) {
  const [data, setData] = useState<UnifiedCommunicationsOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [department, setDepartment] = useState<string | "all">("all");
  const [channel, setChannel] = useState<string | "all">("all");

  // Communications Hub (new, real-logging half) -- distinct state/data source
  // from the legacy read-only feed above; composed side by side, not merged.
  const [hubData, setHubData] = useState<CommunicationsHubOverview | null>(null);
  const [hubLoading, setHubLoading] = useState(true);
  const [hubError, setHubError] = useState<string | null>(null);

  const [showLogForm, setShowLogForm] = useState(false);
  const [logDepartment, setLogDepartment] = useState("Operations");
  const [logChannel, setLogChannel] = useState<CommChannel>("phone");
  const [logDirection, setLogDirection] = useState<CommDirection>("outbound");
  const [logBody, setLogBody] = useState("");
  const [logLinkedEntityId, setLogLinkedEntityId] = useState("");
  const [logDuration, setLogDuration] = useState("");
  const [logFollowUpRequired, setLogFollowUpRequired] = useState(false);
  const [logFollowUpDueAt, setLogFollowUpDueAt] = useState("");
  const [logFollowUpNote, setLogFollowUpNote] = useState("");
  const [logSubmitting, setLogSubmitting] = useState(false);
  const [logError, setLogError] = useState<string | null>(null);

  const [summaryBusyId, setSummaryBusyId] = useState<string | null>(null);
  const [followUpBusyId, setFollowUpBusyId] = useState<string | null>(null);

  function refresh() {
    setLoading(true);
    setError(null);
    getUnifiedCommunicationsOverview()
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : "Unable to load the Unified Communications Hub."))
      .finally(() => setLoading(false));
  }

  function refreshHub() {
    setHubLoading(true);
    setHubError(null);
    getCommunicationsHubOverview()
      .then(setHubData)
      .catch((e) => setHubError(e instanceof Error ? e.message : "Unable to load the Communications Hub."))
      .finally(() => setHubLoading(false));
  }

  useEffect(refresh, []);
  useEffect(refreshHub, []);

  async function handleLogSubmit() {
    if (!logBody.trim()) {
      setLogError("A body / summary of the communication is required.");
      return;
    }
    setLogSubmitting(true);
    setLogError(null);
    try {
      const input: LogCommunicationInput = {
        department: logDepartment.trim() || "Operations",
        channel: logChannel,
        direction: logDirection,
        body: logBody.trim(),
        linked_entity_id: logLinkedEntityId.trim() || null,
        duration_seconds: logChannel === "phone" && logDuration ? Number(logDuration) : null,
        follow_up_required: logFollowUpRequired,
        follow_up_due_at: logFollowUpRequired && logFollowUpDueAt ? logFollowUpDueAt : null,
        follow_up_note: logFollowUpRequired && logFollowUpNote.trim() ? logFollowUpNote.trim() : null,
      };
      await logCommunication(input);
      setLogBody("");
      setLogLinkedEntityId("");
      setLogDuration("");
      setLogFollowUpRequired(false);
      setLogFollowUpDueAt("");
      setLogFollowUpNote("");
      setShowLogForm(false);
      refreshHub();
    } catch (e) {
      setLogError(e instanceof Error ? e.message : "Unable to log this communication.");
    } finally {
      setLogSubmitting(false);
    }
  }

  async function handleGenerateSummary(commId: string) {
    setSummaryBusyId(commId);
    setHubError(null);
    try {
      await generateAiSummary(commId);
      refreshHub();
    } catch (e) {
      setHubError(e instanceof Error ? e.message : "Unable to generate a summary. Please try again.");
    } finally {
      setSummaryBusyId(null);
    }
  }

  async function handleCompleteFollowUp(commId: string) {
    setFollowUpBusyId(commId);
    setHubError(null);
    try {
      await completeFollowUp(commId);
      refreshHub();
    } catch (e) {
      setHubError(e instanceof Error ? e.message : "Unable to complete the follow-up. Refresh before trying again.");
    } finally {
      setFollowUpBusyId(null);
    }
  }

  const feed = data?.feed;

  const items = useMemo(() => {
    if (!feed) return [];
    return feed.items.filter(
      (t) =>
        (department === "all" || t.department === department) &&
        (channel === "all" || t.channel === channel)
    );
  }, [feed, department, channel]);

  const departments = feed ? Object.keys(feed.by_department) : [];
  const channels = feed ? Object.keys(feed.by_channel) : [];

  return (
    <div className={tc(theme, "flex-1 flex flex-col min-h-0 bg-brand-ink text-white overflow-y-auto", "flex-1 flex flex-col min-h-0 bg-white text-black overflow-y-auto")}>
      <div className={tc(theme, "grid grid-cols-4 gap-3 p-4 border-b border-zinc-800", "grid grid-cols-4 gap-3 p-4 border-b border-zinc-200")}>
        <Kpi theme={theme} label="Total Logged Touches" value={String(feed?.total ?? 0)} color={RIBBON[0]} />
        <Kpi theme={theme} label="Departments Represented" value={String(departments.length)} color={RIBBON[1]} />
        <Kpi theme={theme} label="Channels Represented" value={String(channels.length)} color={RIBBON[2]} />
        <Kpi theme={theme} label="Marketing Templates Sent" value={String(data?.marketing_sends?.attached_to_campaign ?? 0)} color={RIBBON[3]} />
      </div>

      <div className="flex flex-wrap items-center gap-1.5 px-4 py-2 border-b border-zinc-800">
        <span className="text-xs text-zinc-500 mr-1">Department:</span>
        <WorkButton type="submit"
          onClick={() => setDepartment("all")}
          className={`text-xs px-2.5 py-1 rounded-full font-brand uppercase tracking-wide transition ${department === "all" ? "bg-zinc-200 text-black font-medium" : "bg-zinc-200/10 text-zinc-400 hover:text-white"}`}
        >
          All
        </WorkButton>
        {departments.map((d) => (
          <WorkButton type="submit"
            key={d}
            onClick={() => setDepartment(d)}
            className={`text-xs px-2.5 py-1 rounded-full font-brand uppercase tracking-wide transition ${department === d ? "bg-zinc-200 text-black font-medium" : "bg-zinc-200/10 text-zinc-400 hover:text-white"}`}
          >
            {d} ({feed?.by_department[d]})
          </WorkButton>
        ))}
        <span className="text-xs text-zinc-500 ml-3 mr-1">Channel:</span>
        <WorkButton type="submit"
          onClick={() => setChannel("all")}
          className={`text-xs px-2.5 py-1 rounded-full font-brand uppercase tracking-wide transition ${channel === "all" ? "bg-zinc-200 text-black font-medium" : "bg-zinc-200/10 text-zinc-400 hover:text-white"}`}
        >
          All
        </WorkButton>
        {channels.map((c) => (
          <WorkButton type="submit"
            key={c}
            onClick={() => setChannel(c)}
            className={`text-xs px-2.5 py-1 rounded-full font-brand uppercase tracking-wide capitalize transition ${channel === c ? "bg-zinc-200 text-black font-medium" : "bg-zinc-200/10 text-zinc-400 hover:text-white"}`}
          >
            {CHANNEL_ICON[c] ?? ""} {c} ({feed?.by_channel[c]})
          </WorkButton>
        ))}
        <WorkButton type="submit" onClick={refresh} className="ml-auto text-xs px-2.5 py-1 rounded-full bg-zinc-200/10 text-zinc-400 hover:text-white">
          ↻ Refresh
        </WorkButton>
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto p-4 space-y-2">
        {loading && <div className="text-sm text-zinc-500">Loading…</div>}
        {error && <div className="text-sm text-red-400">{error}</div>}
        {!loading && !error && items.length === 0 && (
          <div className="text-sm text-zinc-500">No logged touches match this filter.</div>
        )}
        {!loading && !error && items.map((t) => <TouchRow key={t.id} theme={theme} touch={t} />)}
      </div>

      {data?.not_yet_tracked && (
        <div className={tc(theme, "border-t border-zinc-800 p-3", "border-t border-zinc-200 p-3")}>
          <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1">Not Yet Tracked</div>
          <ul className="text-xs text-zinc-500 space-y-0.5 list-disc list-inside">
            {Object.values(data.not_yet_tracked).map((note, i) => (
              <li key={i}>{note}</li>
            ))}
          </ul>
        </div>
      )}

      <div className={tc(theme, "border-t border-zinc-800 p-4 space-y-3", "border-t border-zinc-200 p-4 space-y-3")}>
        <div className="flex items-center justify-between gap-2">
          <div className="text-sm font-brand uppercase tracking-wide text-zinc-400">📡 Communications Hub</div>
          <div className="flex items-center gap-1.5">
            <WorkButton type="submit" onClick={refreshHub} className="text-xs px-2.5 py-1 rounded-full bg-zinc-200/10 text-zinc-400 hover:text-white">
              ↻ Refresh
            </WorkButton>
            <WorkButton type="submit"
              onClick={() => setShowLogForm((s) => !s)}
              className="text-xs px-2.5 py-1 rounded-full bg-zinc-200 text-black font-medium"
            >
              {showLogForm ? "✕ Cancel" : "+ Log Communication"}
            </WorkButton>
          </div>
        </div>

        {hubData?.hub_stats && (
          <div className="grid grid-cols-4 gap-3">
            <Kpi theme={theme} label="Total Communications" value={String(hubData.hub_stats.total_communications)} color={RIBBON[0]} />
            <Kpi theme={theme} label="Open Follow-Ups" value={String(hubData.hub_stats.open_follow_ups)} color={RIBBON[1]} />
            <Kpi theme={theme} label="Calls With Recording" value={String(hubData.hub_stats.phone_calls_with_simulated_recording)} color={RIBBON[2]} />
            <Kpi theme={theme} label="Channels Logged" value={String(Object.keys(hubData.hub_stats.by_channel).length)} color={RIBBON[3]} />
          </div>
        )}

        {hubData?.hub_stats?.recording_basis_note && (
          <div className="text-xs text-zinc-600 italic">{hubData.hub_stats.recording_basis_note}</div>
        )}

        {showLogForm && (
          <div
            className={tc(
              theme,
              "rounded-lg border border-zinc-800 bg-black/20 p-3 space-y-2",
              "rounded-lg border border-zinc-200 bg-zinc-50 p-3 space-y-2"
            )}
          >
            <div className="grid grid-cols-2 gap-2">
              <label className="text-xs text-zinc-500 flex flex-col gap-1">
                Department
                <WorkInput
                  value={logDepartment}
                  onChange={(e) => setLogDepartment(e.target.value)}
                  className={tc(
                    theme,
                    "text-xs rounded border border-zinc-700 bg-black/30 px-2 py-1 text-white",
                    "text-xs rounded border border-zinc-300 bg-white px-2 py-1 text-black"
                  )}
                />
              </label>
              <label className="text-xs text-zinc-500 flex flex-col gap-1">
                Channel
                <WorkSelect
                  value={logChannel}
                  onChange={(e) => setLogChannel(e.target.value as CommChannel)}
                  className={tc(
                    theme,
                    "text-xs rounded border border-zinc-700 bg-black/30 px-2 py-1 text-white capitalize",
                    "text-xs rounded border border-zinc-300 bg-white px-2 py-1 text-black capitalize"
                  )}
                >
                  {COMM_CHANNELS.map((c) => (
                    <option key={c} value={c} className="capitalize">
                      {c}
                    </option>
                  ))}
                </WorkSelect>
              </label>
              <label className="text-xs text-zinc-500 flex flex-col gap-1">
                Direction
                <WorkSelect
                  value={logDirection}
                  onChange={(e) => setLogDirection(e.target.value as CommDirection)}
                  className={tc(
                    theme,
                    "text-xs rounded border border-zinc-700 bg-black/30 px-2 py-1 text-white capitalize",
                    "text-xs rounded border border-zinc-300 bg-white px-2 py-1 text-black capitalize"
                  )}
                >
                  {COMM_DIRECTIONS.map((d) => (
                    <option key={d} value={d} className="capitalize">
                      {d}
                    </option>
                  ))}
                </WorkSelect>
              </label>
              <label className="text-xs text-zinc-500 flex flex-col gap-1">
                Linked Entity ID (optional)
                <WorkInput
                  value={logLinkedEntityId}
                  onChange={(e) => setLogLinkedEntityId(e.target.value)}
                  placeholder="e.g. LEAD-00123"
                  className={tc(
                    theme,
                    "text-xs rounded border border-zinc-700 bg-black/30 px-2 py-1 text-white",
                    "text-xs rounded border border-zinc-300 bg-white px-2 py-1 text-black"
                  )}
                />
              </label>
              {logChannel === "phone" && (
                <label className="text-xs text-zinc-500 flex flex-col gap-1">
                  Duration (seconds)
                  <WorkInput
                    value={logDuration}
                    onChange={(e) => setLogDuration(e.target.value)}
                    type="number"
                    min="0"
                    placeholder="e.g. 180"
                    className={tc(
                      theme,
                      "text-xs rounded border border-zinc-700 bg-black/30 px-2 py-1 text-white",
                      "text-xs rounded border border-zinc-300 bg-white px-2 py-1 text-black"
                    )}
                  />
                </label>
              )}
            </div>

            <label className="text-xs text-zinc-500 flex flex-col gap-1">
              Body
              <WorkTextarea
                value={logBody}
                onChange={(e) => setLogBody(e.target.value)}
                rows={2}
                placeholder="What was discussed…"
                className={tc(
                  theme,
                  "text-xs rounded border border-zinc-700 bg-black/30 px-2 py-1 text-white",
                  "text-xs rounded border border-zinc-300 bg-white px-2 py-1 text-black"
                )}
              />
            </label>

            <label className="flex items-center gap-2 text-xs text-zinc-400">
              <WorkInput
                type="checkbox"
                checked={logFollowUpRequired}
                onChange={(e) => setLogFollowUpRequired(e.target.checked)}
              />
              Requires follow-up
            </label>

            {logFollowUpRequired && (
              <div className="grid grid-cols-2 gap-2">
                <label className="text-xs text-zinc-500 flex flex-col gap-1">
                  Due at
                  <WorkInput
                    value={logFollowUpDueAt}
                    onChange={(e) => setLogFollowUpDueAt(e.target.value)}
                    type="datetime-local"
                    className={tc(
                      theme,
                      "text-xs rounded border border-zinc-700 bg-black/30 px-2 py-1 text-white",
                      "text-xs rounded border border-zinc-300 bg-white px-2 py-1 text-black"
                    )}
                  />
                </label>
                <label className="text-xs text-zinc-500 flex flex-col gap-1">
                  Note
                  <WorkInput
                    value={logFollowUpNote}
                    onChange={(e) => setLogFollowUpNote(e.target.value)}
                    className={tc(
                      theme,
                      "text-xs rounded border border-zinc-700 bg-black/30 px-2 py-1 text-white",
                      "text-xs rounded border border-zinc-300 bg-white px-2 py-1 text-black"
                    )}
                  />
                </label>
              </div>
            )}

            {logError && <div className="text-xs text-red-400">{logError}</div>}

            <WorkButton type="submit"
              onClick={handleLogSubmit}
              disabled={logSubmitting}
              className="text-xs px-3 py-1.5 rounded-full bg-zinc-200 text-black font-medium disabled:opacity-50"
            >
              {logSubmitting ? "Logging…" : "Log Communication"}
            </WorkButton>
          </div>
        )}

        {hubLoading && <div className="text-sm text-zinc-500">Loading Communications Hub…</div>}
        {hubError && <div className="text-sm text-red-400">{hubError}</div>}

        {hubData && hubData.hub_open_follow_ups.length > 0 && (
          <div className="space-y-1.5">
            <div className="text-xs font-brand uppercase tracking-wide text-yellow-500">Open Follow-Ups</div>
            {hubData.hub_open_follow_ups.map((c) => (
              <HubCommCard
                key={c.id}
                theme={theme}
                comm={c}
                onGenerateSummary={handleGenerateSummary}
                onCompleteFollowUp={handleCompleteFollowUp}
                summaryBusy={summaryBusyId === c.id}
                followUpBusy={followUpBusyId === c.id}
              />
            ))}
          </div>
        )}

        {hubData && hubData.hub_recent_communications.length > 0 && (
          <div className="space-y-1.5">
            <div className="text-xs font-brand uppercase tracking-wide text-zinc-500">Recent Communications</div>
            {hubData.hub_recent_communications.map((c) => (
              <HubCommCard
                key={c.id}
                theme={theme}
                comm={c}
                onGenerateSummary={handleGenerateSummary}
                onCompleteFollowUp={handleCompleteFollowUp}
                summaryBusy={summaryBusyId === c.id}
                followUpBusy={followUpBusyId === c.id}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
