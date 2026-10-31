"use client";
import { WorkButton, WorkInput, WorkSelect , WorkStat} from "./WorkspaceUi";
import {RecordCollection} from "./RecordCollection";
import { WorkField } from "./WorkField";
import { SecurityReviewPanel } from "@/components/SecurityReviewPanel";

// Administration's "Audit Center" item (Administration Control Center
// rebuild, final slice). A real investigative workspace over the audit log
// (core/audit_center.py) every ~20+ modules across this codebase already
// write to -- distinct from Security/Systems/Governance's own thin slices of
// it: real filtering/search, a real per-actor activity summary, and a real,
// transparent RULES-based suspicious-activity flag list. No ML/AI anomaly
// detection anywhere here or on the backend -- every flag states the exact
// rule that fired.
import { PRODUCT_ACCENT_COLORS } from "@/lib/productTheme";
import { useEffect, useState } from "react";
import {
  getAuditCenterOverview,
  searchAuditLog,
  getActorActivity,
  getActorTimeline,
  getSuspiciousActivity,
  downloadAuditExport,
  type AuditCenterOverview,
  type AuditEvent,
  type ActorBucket,
  type SuspiciousActivity,
  type SearchFilters,
} from "@/lib/auditCenter";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const RIBBON = PRODUCT_ACCENT_COLORS;

const SEVERITY_TONE: Record<string, string> = {
  high: "bg-red-950/40 text-red-300",
  medium: "bg-amber-950/40 text-amber-300",
  low: "bg-zinc-800 text-zinc-400",
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

function Btn({ onClick, children, disabled, tone }: { onClick: () => void; children: React.ReactNode; disabled?: boolean; tone?: "primary" | "danger" }) {
  return (
    <WorkButton type="submit"
      onClick={onClick}
      disabled={disabled}
      className={`text-xs px-2.5 py-1 rounded font-medium disabled:opacity-40 ${
        tone === "danger" ? "bg-red-900/60 text-red-200 hover:bg-red-900" : tone === "primary" ? "bg-zinc-200 text-black hover:bg-white" : "bg-zinc-800 text-zinc-300 hover:bg-zinc-700"
      }`}
    >
      {children}
    </WorkButton>
  );
}

function Input({ value, onChange, placeholder }: { value: string; onChange: (v: string) => void; placeholder?: string }) {
  return (
    <WorkField label={placeholder || "Value"}><WorkInput
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      className="text-xs px-2 py-1 rounded bg-zinc-900 border border-zinc-700 text-zinc-200 placeholder:text-zinc-600 w-full"
    /></WorkField>
  );
}

function EventRow({ event }: { event: AuditEvent }) {
  return (
    <div className="flex items-start justify-between gap-2 text-xs px-2 py-1.5 rounded border border-zinc-800">
      <div className="min-w-0">
        <div>
          <span className="text-zinc-200">{event.summary}</span>
        </div>
        <div className="text-xs text-zinc-500 mt-0.5">
          <span className="px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400 mr-1.5">{event.category}</span>
          {event.event_type} · {event.actor} {event.entity_id ? `→ ${event.entity_id}` : ""} · {fmt(event.timestamp)}
        </div>
      </div>
    </div>
  );
}

export function AuditCenterBoard({ theme, initialTab = "overview" }: { theme: Theme; initialTab?: "overview" | "search" | "actors" | "suspicious" | "security" }) {
  const [tab, setTab] = useState<"overview" | "search" | "actors" | "suspicious" | "security">(initialTab);
  useEffect(()=>setTab(initialTab),[initialTab]);
  const [overview, setOverview] = useState<AuditCenterOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [filters, setFilters] = useState<SearchFilters>({});
  const [queryText, setQueryText] = useState("");
  const [entityId, setEntityId] = useState("");
  const [actorFilter, setActorFilter] = useState("");
  const [category, setCategory] = useState("");
  const [searchResults, setSearchResults] = useState<AuditEvent[] | null>(null);
  const [searchTotal, setSearchTotal] = useState(0);
  const [searchLoading, setSearchLoading] = useState(false);

  const [actors, setActors] = useState<ActorBucket[]>([]);
  const [selectedActor, setSelectedActor] = useState<string | null>(null);
  const [actorEvents, setActorEvents] = useState<AuditEvent[] | null>(null);

  const [suspicious, setSuspicious] = useState<SuspiciousActivity | null>(null);
  const [severityFilter, setSeverityFilter] = useState<"all" | "high" | "medium" | "low">("all");

  function refreshOverview() {
    setLoading(true);
    setError(null);
    getAuditCenterOverview()
      .then(setOverview)
      .catch((e) => setError(e instanceof Error ? e.message : "Unable to load Audit Center data."))
      .finally(() => setLoading(false));
  }

  useEffect(refreshOverview, []);

  useEffect(() => {
    if (tab === "actors" && actors.length === 0) {
      getActorActivity(50)
        .then((r) => setActors(r.actors))
        .catch(() => setActors([]));
    }
    if (tab === "suspicious" && !suspicious) {
      getSuspiciousActivity()
        .then(setSuspicious)
        .catch(() => setSuspicious(null));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab]);

  async function runSearch() {
    setSearchLoading(true);
    setError(null);
    const activeFilters: SearchFilters = {
      ...filters,
      query: queryText || undefined,
      entityId: entityId || undefined,
      actor: actorFilter || undefined,
      category: category || undefined,
    };
    try {
      const result = await searchAuditLog(activeFilters);
      setSearchResults(result.events);
      setSearchTotal(result.total_matches);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to search the audit log.");
    } finally {
      setSearchLoading(false);
    }
  }

  async function loadActorTimeline(actor: string) {
    setSelectedActor(actor);
    setActorEvents(null);
    try {
      const timeline = await getActorTimeline(actor);
      setActorEvents(timeline.events);
    } catch {
      setActorEvents([]);
    }
  }

  async function handleExport() {
    try {
      await downloadAuditExport({
        query: queryText || undefined,
        entityId: entityId || undefined,
        actor: actorFilter || undefined,
        category: category || undefined,
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to export audit events.");
    }
  }

  const filteredFlags = suspicious ? suspicious.flags.filter((f) => severityFilter === "all" || f.severity === severityFilter) : [];

  return (
    <div className={tc(theme, "flex-1 flex flex-col min-h-0 bg-brand-ink text-white overflow-y-auto", "flex-1 flex flex-col min-h-0 bg-white text-black overflow-y-auto")}>
      <div className={tc(theme, "grid grid-cols-4 gap-3 p-4 border-b border-zinc-800", "grid grid-cols-4 gap-3 p-4 border-b border-zinc-200")}>
        <Kpi theme={theme} label="Total Events Logged" value={String(overview?.total_events ?? 0)} color={RIBBON[0]} />
        <Kpi theme={theme} label="Event Types Tracked" value={String(overview?.event_catalog.total_event_types ?? 0)} color={RIBBON[1]} />
        <Kpi theme={theme} label="Actors Seen" value={String(overview?.top_actors.total_actors ?? 0)} color={RIBBON[2]} />
        <Kpi theme={theme} label="Suspicious Flags" value={String(overview?.suspicious_activity_summary.total_flags ?? 0)} color={RIBBON[3]} />
      </div>

      <div className="flex items-center gap-1.5 px-4 py-2 border-b border-zinc-800">
        {([
          ["overview", "Overview"],
          ["search", "Investigate"],
          ["actors", "Actor Activity"],
          ["suspicious", "Suspicious Activity"],
          ["security", "Security Review"],
        ] as const).map(([key, label]) => (
          <WorkButton data-work-view aria-pressed={tab === key} type="submit"
            key={key}
            onClick={() => setTab(key)}
            className={`text-xs px-2.5 py-1 rounded-full font-brand uppercase tracking-wide transition ${tab === key ? "bg-zinc-200 text-black font-medium" : "bg-zinc-200/10 text-zinc-400 hover:text-white"}`}
          >
            {label}
          </WorkButton>
        ))}
      </div>

      {error && <div className="mx-4 mt-2 text-xs text-red-400">{error}</div>}

      <div className="flex-1 p-4">
        {tab === "security" ? <SecurityReviewPanel /> : loading ? (
          <div className="text-sm text-zinc-500">Loading…</div>
        ) : tab === "overview" ? (
          <div className="space-y-4">
            <div className="text-xs text-zinc-500">
              Every real event this platform already logs (logins, credential changes, permission
              grants, compliance overrides, deal/lead/campaign/workflow actions, and more) in one
              place — distinct from Security/Systems/Governance&apos;s own thin slices of the same
              log.
            </div>
            <div>
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1.5">
                Events By Type ({Object.keys(overview?.by_type || {}).length} types seen)
              </div>
              <div className="grid grid-cols-3 gap-1.5">
                <RecordCollection label="Event types">{Object.entries(overview?.by_type || {})
                  .sort((a, b) => b[1] - a[1])
                  .map(([type, count]) => (
                    <div key={type} className="flex items-center justify-between text-xs px-2 py-1 rounded border border-zinc-800">
                      <span className="text-zinc-300 truncate">{type}</span>
                      <span className="text-zinc-500 ml-2">{count}</span>
                    </div>
                  ))}</RecordCollection>
              </div>
            </div>
            <div>
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1.5">Most Recent Events</div>
              <div className="space-y-1">
                <RecordCollection>{(overview?.recent || []).map((e) => (
                  <EventRow key={e.id} event={{ ...e, category: e.category || "Other" } as AuditEvent} />
                ))}</RecordCollection>
              </div>
            </div>
          </div>
        ) : tab === "search" ? (
          <div className="space-y-4">
            <div className="rounded border border-zinc-800 p-3 space-y-2">
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500">Search / Filter The Audit Log</div>
              <div className="grid grid-cols-4 gap-2">
                <Input value={queryText} onChange={setQueryText} placeholder="Free text (summary/actor/entity)" />
                <Input value={entityId} onChange={setEntityId} placeholder="Entity ID" />
                <Input value={actorFilter} onChange={setActorFilter} placeholder="Actor (EMP-…)" />
                <WorkField label="Category"><WorkSelect
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                  className="text-xs px-2 py-1 rounded bg-zinc-900 border border-zinc-700 text-zinc-200"
                >
                  <option value="">All categories</option>
                  {Object.keys(overview?.event_catalog.categories || {}).map((c) => (
                    <option key={c} value={c}>{c}</option>
                  ))}
                </WorkSelect></WorkField>
              </div>
              <div className="flex gap-2">
                <Btn tone="primary" onClick={runSearch} disabled={searchLoading}>Search</Btn>
                <Btn onClick={handleExport}>Export CSV</Btn>
              </div>
            </div>
            <p className="text-xs opacity-75">CSV downloads prefix formula-like text with [text] for spreadsheet viewing. Original audit records are unchanged.</p>

            {searchResults !== null && (
              <div>
                <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1.5">
                  {searchTotal} matching event{searchTotal === 1 ? "" : "s"} ({searchResults.length} shown)
                </div>
                <div className="space-y-1">
                  {searchResults.length === 0 && <div className="text-xs text-zinc-600">No matching events.</div>}
                  {searchResults.map((e) => (
                    <EventRow key={e.id} event={e} />
                  ))}
                </div>
              </div>
            )}
          </div>
        ) : tab === "actors" ? (
          <div className="grid grid-cols-2 gap-4">
            <div>
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1.5">Actor Leaderboard ({actors.length})</div>
              <div className="space-y-1 max-h-[28rem] overflow-y-auto">
                {actors.map((a) => (
                  <button
                    key={a.actor}
                    onClick={() => loadActorTimeline(a.actor)}
                    className={`w-full text-left flex items-center justify-between gap-2 text-xs px-2 py-1.5 rounded border ${selectedActor === a.actor ? "border-zinc-500 bg-zinc-800/60" : "border-zinc-800 hover:border-zinc-600"}`}
                  >
                    <div>
                      <span className="text-zinc-200">{a.actor}</span>
                      <span className="text-zinc-600 ml-2">{fmt(a.first_seen)} → {fmt(a.last_seen)}</span>
                    </div>
                    <span className="px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400 text-xs">{a.total} events</span>
                  </button>
                ))}
              </div>
            </div>
            <div>
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1.5">
                {selectedActor ? `${selectedActor}'s Timeline` : "Select an actor"}
              </div>
              <div className="space-y-1 max-h-[28rem] overflow-y-auto">
                {actorEvents === null && selectedActor && <div className="text-xs text-zinc-600">Loading…</div>}
                {actorEvents?.map((e) => (
                  <EventRow key={e.id} event={e} />
                ))}
              </div>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="text-xs text-zinc-500">
              Every flag below is a plain, explainable rule over real data — no machine-learning
              model, no AI call. Each one states exactly why it fired.
            </div>
            <div className="flex items-center gap-1.5">
              {([
                ["all", `All (${suspicious?.total_flags ?? 0})`],
                ["high", `High (${suspicious?.by_severity.high ?? 0})`],
                ["medium", `Medium (${suspicious?.by_severity.medium ?? 0})`],
                ["low", `Low (${suspicious?.by_severity.low ?? 0})`],
              ] as const).map(([key, label]) => (
                <WorkButton type="submit"
                  key={key}
                  onClick={() => setSeverityFilter(key)}
                  className={`text-xs px-2 py-1 rounded-full ${severityFilter === key ? "bg-zinc-200 text-black font-medium" : "bg-zinc-800 text-zinc-400"}`}
                >
                  {label}
                </WorkButton>
              ))}
            </div>
            <div className="space-y-1">
              {suspicious === null && <div className="text-xs text-zinc-600">Loading…</div>}
              {suspicious && filteredFlags.length === 0 && <div className="text-xs text-zinc-600">No flags at this severity.</div>}
              {filteredFlags.map((f, i) => (
                <div key={`${f.flag_type}-${f.entity_id}-${i}`} className="flex items-start justify-between gap-2 text-xs px-2 py-1.5 rounded border border-zinc-800">
                  <div>
                    <span className={`px-1.5 py-0.5 rounded text-xs mr-2 ${SEVERITY_TONE[f.severity]}`}>{f.severity}</span>
                    <span className="text-zinc-300">{f.flag_type.replace(/_/g, " ")}</span>
                    {f.entity_id && <span className="text-zinc-600 ml-2">{f.entity_id}</span>}
                    <div className="text-zinc-500 mt-0.5">{f.detail}</div>
                  </div>
                </div>
              ))}
            </div>
            {suspicious?.not_yet_tracked && (
              <div className="text-xs text-zinc-600 space-y-0.5 pt-2 border-t border-zinc-800">
                {Object.entries(suspicious.not_yet_tracked).map(([k, v]) => (
                  <div key={k}>
                    <span className="text-zinc-500">{k.replace(/_/g, " ")}:</span> {v}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
