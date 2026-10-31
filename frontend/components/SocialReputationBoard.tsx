"use client";
import { WorkButton, WorkTextarea, WorkInput , WorkOverlay} from "./WorkspaceUi";
import { WorkField } from "./WorkField";
import { formatCalendarDate } from "@/lib/calendarDate";

// Marketing's "Social / Reputation" Top Menu item (session 83). Sam: "we need to have
// an appliaction like hootsuit where you can post to facebook, instagram, X, LinkedIn,
// tiktok, etc with a social content calendar... a built in social media post builder
// that includes dropping in inventory... there needs to be a toggle for reputation
// tracking, which connects, google, facebook, etc. reviews to show aggregate reviews,
// the ability to respond to each review, and have an bot function to respond to
// reviews / alert for bad reviews... competitors social tracking."
//
// One Dash, a Social/Reputation toggle at the top (Sam's own word: "toggle"). Social
// side: a real (simulated-publish) post builder with a platform tab strip, an
// inventory drop-in picker, and a content calendar. Reputation side: real per-review
// response, a bad-review alert banner, and a simulated competitor tracking panel
// (this sandbox has no real connection to competitors' review/social pages, labeled
// honestly). Mounted by components/MenuDashPanel.tsx the same way
// MarketingCRMBoard.tsx/EmailSmsBuilder.tsx are for the crm/email_sms items.
import { PRODUCT_ACCENT_COLORS } from "@/lib/productTheme";
import { useEffect, useMemo, useState, type DragEvent } from "react";
import {
  listSocialPlatforms,
  createSocialPost,
  updateSocialPost,
  listSocialPosts,
  getSocialPost,
  getSocialCalendar,
  searchInventoryForPost,
  publishSocialPost,
  cancelSocialPost,
  getReputationSummary,
  listReviews,
  listBadReviewAlerts,
  respondToReview,
  autoRespondToReview,
  getCompetitorTracking,
  generateSocialCaption,
  type SocialPlatform,
  type SocialPost,
  type LinkedVehicle,
  type CalendarPost,
  type Review,
  type BadReviewAlert,
  type CompetitorTracking,
} from "@/lib/socialReputation";
import { VISUALIZATION_DRAG_TYPE, type VisualizationDropPayload } from "@/lib/useVisualizationWorkspace";

type Theme = "dark" | "light";
type Section = "social" | "reputation";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

// Same brand-ribbon order as components/DepartmentWorkflowButtons.tsx's RIBBON_COLORS.
const KPI_RIBBON = PRODUCT_ACCENT_COLORS;

const PLATFORM_LABELS: Record<string, string> = {
  facebook: "Facebook",
  instagram: "Instagram",
  x: "X",
  linkedin: "LinkedIn",
  tiktok: "TikTok",
};

const PLATFORM_ICONS: Record<string, string> = {
  facebook: "📘",
  instagram: "📷",
  x: "𝕏",
  linkedin: "in",
  tiktok: "🎵",
  google: "G",
};

function DragHandle({
  theme,
  itemKey,
  fieldPath,
  sourceLabel,
  rows,
  numericColumns,
  labelColumn,
}: {
  theme: Theme;
  itemKey: string;
  fieldPath: string[];
  sourceLabel: string;
  rows: Record<string, unknown>[];
  numericColumns: string[];
  labelColumn: string;
}) {
  if (rows.length === 0 || numericColumns.length === 0) return null;

  function handleDragStart(event: DragEvent<HTMLButtonElement>) {
    const payload: VisualizationDropPayload = {
      department: "Marketing",
      itemKey,
      fieldPath,
      sourceLabel,
      rows,
      numericColumns,
      labelColumn,
    };
    event.dataTransfer.setData(VISUALIZATION_DRAG_TYPE, JSON.stringify(payload));
    event.dataTransfer.effectAllowed = "copy";
  }

  return (
    <WorkButton type="submit"
      draggable
      onDragStart={handleDragStart}
      title="Drag into the Workspace to build a chart, then pin it"
      className={tc(
        theme,
        "text-xs px-2 py-0.5 rounded border border-dashed border-zinc-700 text-zinc-500 hover:text-white hover:border-zinc-500 transition cursor-grab active:cursor-grabbing",
        "text-xs px-2 py-0.5 rounded border border-dashed border-zinc-400 text-zinc-600 hover:text-black hover:border-zinc-600 transition cursor-grab active:cursor-grabbing"
      )}
    >
      ⠿ Drag to Workspace
    </WorkButton>
  );
}

function Stars({ rating }: { rating: number }) {
  return (
    <span className="text-amber-400 text-xs" title={`${rating}/5`}>
      {"★".repeat(Math.round(rating))}
      <span className="text-zinc-600">{"★".repeat(5 - Math.round(rating))}</span>
    </span>
  );
}

export function SocialReputationBoard({ theme, initialSection = "social" }: { theme: Theme; initialSection?: Section }) {
  const [section, setSection] = useState<Section>(initialSection);

  return (
    <div className={tc(theme, "flex-1 flex flex-col min-h-0 bg-brand-ink text-white", "flex-1 flex flex-col min-h-0 bg-white text-black")}>
      <div className={tc(theme, "border-b border-zinc-800 px-4 py-2.5 flex items-center gap-2", "border-b border-zinc-200 px-4 py-2.5 flex items-center gap-2")}>
        <span className={tc(theme, "text-xs uppercase tracking-wide text-zinc-500 mr-1", "text-xs uppercase tracking-wide text-zinc-500 mr-1")}>Toggle</span>
        {(["social", "reputation"] as Section[]).map((s) => (
          <WorkButton type="submit"
            key={s}
            onClick={() => setSection(s)}
            className={
              section === s
                ? "text-xs px-3 py-1.5 rounded-md bg-brand-blue text-white font-medium transition"
                : tc(
                    theme,
                    "text-xs px-3 py-1.5 rounded-md text-zinc-400 hover:text-white hover:bg-zinc-900 transition border border-zinc-800",
                    "text-xs px-3 py-1.5 rounded-md text-zinc-600 hover:text-black hover:bg-zinc-100 transition border border-zinc-300"
                  )
            }
          >
            {s === "social" ? "📣 Social" : "⭐ Reputation"}
          </WorkButton>
        ))}
      </div>

      {section === "social" ? <SocialTab theme={theme} /> : <ReputationTab theme={theme} />}
    </div>
  );
}

// --- Social tab ---

function pad2(n: number): string {
  return String(n).padStart(2, "0");
}

function toISODate(d: Date): string {
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
}

function todayISODate(): string {
  return toISODate(new Date());
}

function getMonthGrid(year: number, month: number): Date[] {
  const first = new Date(year, month, 1);
  const gridStart = new Date(year, month, 1 - first.getDay());
  const days: Date[] = [];
  for (let i = 0; i < 42; i++) {
    days.push(new Date(gridStart.getFullYear(), gridStart.getMonth(), gridStart.getDate() + i));
  }
  return days;
}

// Week/day calendar view toggle (session 113 follow-up -- closes the gap session 91's
// own month-only calendar left open). Same "compute a plain list of Date objects" shape
// as getMonthGrid() above, so MonthCalendar's day-grid rendering works for a 7-day week
// grid unchanged -- only the day range and cell sizing differ; a single-day view gets
// its own dedicated agenda renderer (DayAgenda) rather than a 1-cell grid, since a real
// day view should show full post content, not a truncated calendar cell.
function getWeekGrid(anchor: Date): Date[] {
  const start = new Date(anchor.getFullYear(), anchor.getMonth(), anchor.getDate() - anchor.getDay());
  return Array.from({ length: 7 }, (_, i) => new Date(start.getFullYear(), start.getMonth(), start.getDate() + i));
}

type CalGranularity = "month" | "week" | "day";

const WEEKDAY_LABELS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

const STATUS_DOT: Record<string, string> = {
  draft: "bg-zinc-500",
  scheduled: "bg-amber-400",
  published: "bg-green-400",
};

function SocialTab({ theme }: { theme: Theme }) {
  const [platforms, setPlatforms] = useState<SocialPlatform[]>([]);
  const [posts, setPosts] = useState<SocialPost[]>([]);
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState<"calendar" | "feed">("calendar");
  const [calGranularity, setCalGranularity] = useState<CalGranularity>("month");
  const [monthCursor, setMonthCursor] = useState(() => {
    const d = new Date();
    return new Date(d.getFullYear(), d.getMonth(), 1);
  });
  const [calendar, setCalendar] = useState<Record<string, CalendarPost[]>>({});
  const [calendarLoading, setCalendarLoading] = useState(true);
  const [visiblePlatforms, setVisiblePlatforms] = useState<Set<string>>(new Set());
  const [composer, setComposer] = useState<{ date: string; editingPostId: string | null } | null>(null);

  function refreshPosts() {
    setLoading(true);
    listSocialPosts()
      .then(setPosts)
      .finally(() => setLoading(false));
  }

  const gridDays = useMemo(() => {
    if (calGranularity === "week") return getWeekGrid(monthCursor);
    if (calGranularity === "day") return [monthCursor];
    return getMonthGrid(monthCursor.getFullYear(), monthCursor.getMonth());
  }, [monthCursor, calGranularity]);

  function shiftCursor(dir: 1 | -1) {
    setMonthCursor((m) => {
      if (calGranularity === "day") return new Date(m.getFullYear(), m.getMonth(), m.getDate() + dir);
      if (calGranularity === "week") return new Date(m.getFullYear(), m.getMonth(), m.getDate() + dir * 7);
      return new Date(m.getFullYear(), m.getMonth() + dir, 1);
    });
  }

  function goToday() {
    const d = new Date();
    setMonthCursor(calGranularity === "month" ? new Date(d.getFullYear(), d.getMonth(), 1) : d);
  }

  function refreshCalendar() {
    setCalendarLoading(true);
    const startDate = toISODate(gridDays[0]);
    const endDate = toISODate(gridDays[gridDays.length - 1]);
    getSocialCalendar(startDate, endDate)
      .then((cal) => setCalendar(cal.by_date || {}))
      .finally(() => setCalendarLoading(false));
  }

  useEffect(() => {
    listSocialPlatforms().then((p) => {
      setPlatforms(p);
      setVisiblePlatforms(new Set(p));
    });
    refreshPosts();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    refreshCalendar();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [monthCursor, calGranularity]);

  function refreshAll() {
    refreshPosts();
    refreshCalendar();
  }

  const byStatus = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const p of posts) counts[p.status] = (counts[p.status] || 0) + 1;
    return counts;
  }, [posts]);

  const kpiRows = useMemo(
    () => Object.entries(byStatus).map(([status, count]) => ({ status, count })),
    [byStatus]
  );

  function openComposer(date: string, editingPostId: string | null = null) {
    setComposer({ date, editingPostId });
  }

  return (
    <div className="flex-1 min-h-0 flex flex-col overflow-hidden">
      {/* KPI strip */}
      <div className={tc(theme, "grid grid-cols-4 gap-3 p-4 border-b border-zinc-800", "grid grid-cols-4 gap-3 p-4 border-b border-zinc-200")}>
        {[
          { label: "Total Posts", value: posts.length },
          { label: "Draft", value: byStatus.draft || 0 },
          { label: "Scheduled", value: byStatus.scheduled || 0 },
          { label: "Simulated publications", value: byStatus.published || 0 },
        ].map((k, i) => (
          <div key={k.label} className={tc(theme, "relative overflow-hidden rounded-lg border border-black/20 bg-brand-charcoal p-3 pl-4", "relative overflow-hidden rounded-lg border border-zinc-200 bg-zinc-50 p-3 pl-4")}>
            <span className="nxt-accent absolute left-0 top-0 bottom-0 w-2.5"
              style={{ background: KPI_RIBBON[i % KPI_RIBBON.length], clipPath: "polygon(0 0, 100% 0, 45% 100%, 0 100%)" }}
            />
            <div className="text-2xl font-semibold">{k.value}</div>
            <div className="text-xs font-brand uppercase tracking-wide text-zinc-500">{k.label}</div>
          </div>
        ))}
        <div className="col-span-4 flex justify-end">
          <DragHandle
            theme={theme}
            itemKey="social_reputation"
            fieldPath={["social", "recent_posts"]}
            sourceLabel="Social Posts by Status"
            rows={kpiRows}
            numericColumns={["count"]}
            labelColumn="status"
          />
        </div>
      </div>

      <div className={tc(theme, "border-b border-zinc-800 px-4 py-2 flex items-center justify-between gap-2 flex-wrap", "border-b border-zinc-200 px-4 py-2 flex items-center justify-between gap-2 flex-wrap")}>
        <div className="flex items-center gap-2">
          {(["calendar", "feed"] as const).map((v) => (
            <WorkButton data-work-view aria-pressed={view === v} type="submit"
              key={v}
              onClick={() => setView(v)}
              className={
                view === v
                  ? "text-xs px-2.5 py-1 rounded-md bg-zinc-200 text-black font-medium transition"
                  : tc(theme, "text-xs px-2.5 py-1 rounded-md text-zinc-400 hover:text-white hover:bg-zinc-900 transition", "text-xs px-2.5 py-1 rounded-md text-zinc-600 hover:text-black hover:bg-zinc-200 transition")
              }
            >
              {v === "calendar" ? "🗓 Calendar" : "Feed"}
            </WorkButton>
          ))}
          {view === "calendar" && (
            <div className={tc(theme, "flex items-center gap-0.5 ml-1 rounded-md border border-zinc-700 p-0.5", "flex items-center gap-0.5 ml-1 rounded-md border border-zinc-300 p-0.5")}>
              {(["month", "week", "day"] as const).map((g) => (
                <WorkButton type="submit"
                  key={g}
                  onClick={() => setCalGranularity(g)}
                  className={
                    calGranularity === g
                      ? "text-xs px-2 py-0.5 rounded bg-brand-blue text-white font-medium transition"
                      : tc(theme, "text-xs px-2 py-0.5 rounded text-zinc-400 hover:text-white transition", "text-xs px-2 py-0.5 rounded text-zinc-500 hover:text-black transition")
                  }
                >
                  {g[0].toUpperCase() + g.slice(1)}
                </WorkButton>
              ))}
            </div>
          )}
        </div>

        <div className="flex items-center gap-2">
          {platforms.length > 0 && (
            <div className="flex items-center gap-1">
              {platforms.map((p) => {
                const active = visiblePlatforms.has(p);
                return (
                  <WorkButton type="submit"
                    key={p}
                    title={PLATFORM_LABELS[p] || p}
                    onClick={() =>
                      setVisiblePlatforms((prev) => {
                        const next = new Set(prev);
                        if (next.has(p)) next.delete(p);
                        else next.add(p);
                        return next;
                      })
                    }
                    className={
                      "text-xs w-7 h-7 rounded-md flex items-center justify-center transition border " +
                      (active
                        ? "border-brand-blue bg-brand-blue/20 opacity-100"
                        : tc(theme, "border-zinc-700 opacity-30 hover:opacity-70", "border-zinc-300 opacity-30 hover:opacity-70"))
                    }
                  >
                    {PLATFORM_ICONS[p] || "📱"}
                  </WorkButton>
                );
              })}
            </div>
          )}
          <WorkButton type="submit" variant="primary"
            onClick={() => openComposer(todayISODate())}
            className="text-xs px-3 py-1.5 rounded-md bg-brand-blue text-white font-medium hover:opacity-90 transition"
          >
            + New Post
          </WorkButton>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        {view === "feed" ? (
          loading ? (
            <div className="text-sm text-zinc-500">Loading…</div>
          ) : (
            <FeedView theme={theme} posts={posts} onChanged={refreshAll} onEdit={(p) => openComposer((p.scheduled_time || p.target_date || p.created_at).slice(0, 10), p.id)} />
          )
        ) : (
          <MonthCalendar
            theme={theme}
            monthCursor={monthCursor}
            granularity={calGranularity}
            gridDays={gridDays}
            calendar={calendar}
            loading={calendarLoading}
            visiblePlatforms={visiblePlatforms}
            onPrev={() => shiftCursor(-1)}
            onNext={() => shiftCursor(1)}
            onToday={goToday}
            onDayClick={(iso) => openComposer(iso)}
            onPostClick={(p, iso) => openComposer(iso, p.id)}
          />
        )}
      </div>

      {composer && (
        <PostComposerModal
          theme={theme}
          platforms={platforms}
          date={composer.date}
          editingPostId={composer.editingPostId}
          dayPosts={(calendar[composer.date] || []).filter((p) => p.id !== composer.editingPostId)}
          onClose={() => setComposer(null)}
          onSwitchPost={(id) => setComposer({ date: composer.date, editingPostId: id })}
          onSaved={() => {
            setComposer(null);
            refreshAll();
          }}
        />
      )}
    </div>
  );
}

function MonthCalendar({
  theme,
  monthCursor,
  granularity,
  gridDays,
  calendar,
  loading,
  visiblePlatforms,
  onPrev,
  onNext,
  onToday,
  onDayClick,
  onPostClick,
}: {
  theme: Theme;
  monthCursor: Date;
  granularity: CalGranularity;
  gridDays: Date[];
  calendar: Record<string, CalendarPost[]>;
  loading: boolean;
  visiblePlatforms: Set<string>;
  onPrev: () => void;
  onNext: () => void;
  onToday: () => void;
  onDayClick: (iso: string) => void;
  onPostClick: (post: CalendarPost, iso: string) => void;
}) {
  const today = todayISODate();
  const currentMonth = monthCursor.getMonth();

  const headerLabel =
    granularity === "day"
      ? monthCursor.toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric", year: "numeric" })
      : granularity === "week"
      ? `Week of ${gridDays[0]?.toLocaleDateString(undefined, { month: "short", day: "numeric" })} – ${gridDays[6]?.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}`
      : monthCursor.toLocaleDateString(undefined, { month: "long", year: "numeric" });

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <div className="text-sm font-brand uppercase tracking-wide">{headerLabel}</div>
        <div className="flex items-center gap-1.5">
          <WorkButton type="submit" onClick={onToday} className="text-xs px-2 py-1 rounded border border-zinc-700 text-zinc-400 hover:text-white transition">
            Today
          </WorkButton>
          <WorkButton type="submit" onClick={onPrev} className="text-xs px-2 py-1 rounded border border-zinc-700 text-zinc-400 hover:text-white transition">
            ← Prev
          </WorkButton>
          <WorkButton type="submit" onClick={onNext} className="text-xs px-2 py-1 rounded border border-zinc-700 text-zinc-400 hover:text-white transition">
            Next →
          </WorkButton>
        </div>
      </div>

      {granularity === "day" ? (
        <DayAgenda
          theme={theme}
          day={gridDays[0]}
          calendar={calendar}
          visiblePlatforms={visiblePlatforms}
          onDayClick={onDayClick}
          onPostClick={onPostClick}
        />
      ) : (
        <div className="grid grid-cols-7 gap-1.5">
          {WEEKDAY_LABELS.map((w) => (
            <div key={w} className="text-xs font-brand uppercase tracking-wide text-zinc-500 text-center py-1">
              {w}
            </div>
          ))}

          {gridDays.map((d) => {
            const iso = toISODate(d);
            const inMonth = granularity === "week" ? true : d.getMonth() === currentMonth;
            const isToday = iso === today;
            const dayPosts = (calendar[iso] || []).filter((p) => visiblePlatforms.has(p.platform));
            const maxPreview = granularity === "week" ? 6 : 3;
            const cellHeight = granularity === "week" ? "min-h-[220px]" : "min-h-[84px]";

            return (
              <button
                key={iso}
                onClick={() => onDayClick(iso)}
                className={tc(
                  theme,
                  `text-left rounded-lg border p-1.5 ${cellHeight} flex flex-col gap-1 transition hover:border-brand-blue ${
                    inMonth ? "border-black/20 bg-brand-charcoal" : "border-black/10 bg-brand-charcoal/40 opacity-40"
                  } ${isToday ? "ring-1 ring-brand-teal" : ""}`,
                  `text-left rounded-lg border p-1.5 ${cellHeight} flex flex-col gap-1 transition hover:border-brand-blue ${
                    inMonth ? "border-zinc-200 bg-zinc-50" : "border-zinc-100 bg-zinc-50/50 opacity-40"
                  } ${isToday ? "ring-1 ring-brand-teal" : ""}`
                )}
              >
                <span className={`text-xs ${isToday ? "font-semibold text-brand-teal" : "text-zinc-500"}`}>
                  {granularity === "week" ? d.toLocaleDateString(undefined, { month: "short", day: "numeric" }) : d.getDate()}
                </span>
                <div className="flex-1 flex flex-col gap-0.5 overflow-hidden">
                  {dayPosts.slice(0, maxPreview).map((p) => (
                    <span
                      role="button"
                      key={p.id}
                      onClick={(e) => {
                        e.stopPropagation();
                        onPostClick(p, iso);
                      }}
                      title={p.content}
                      className="text-xs px-1 py-0.5 rounded bg-black/20 hover:bg-black/40 transition flex items-center gap-1 truncate"
                    >
                      <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${STATUS_DOT[p.status] || "bg-zinc-500"}`} />
                      <span className="shrink-0">{PLATFORM_ICONS[p.platform] || "📱"}</span>
                      <span className="truncate">{p.content || "(no caption)"}</span>
                    </span>
                  ))}
                  {dayPosts.length > maxPreview && <span className="text-xs text-zinc-500">+{dayPosts.length - maxPreview} more</span>}
                </div>
              </button>
            );
          })}
        </div>
      )}

      {loading && <div className="text-xs text-zinc-500">Refreshing calendar…</div>}
    </div>
  );
}

// Day-granularity agenda -- a full, untruncated list of the day's posts rather than a
// small calendar cell, since a single-day view should actually show real content.
function DayAgenda({
  theme,
  day,
  calendar,
  visiblePlatforms,
  onDayClick,
  onPostClick,
}: {
  theme: Theme;
  day: Date;
  calendar: Record<string, CalendarPost[]>;
  visiblePlatforms: Set<string>;
  onDayClick: (iso: string) => void;
  onPostClick: (post: CalendarPost, iso: string) => void;
}) {
  const iso = toISODate(day);
  const dayPosts = (calendar[iso] || []).filter((p) => visiblePlatforms.has(p.platform));

  return (
    <div className={tc(theme, "rounded-lg border border-black/20 bg-brand-charcoal p-3", "rounded-lg border border-zinc-200 bg-zinc-50 p-3")}>
      {dayPosts.length === 0 ? (
        <div className="text-sm text-zinc-500 py-6 text-center">
          Nothing scheduled for this day.{" "}
          <WorkButton type="submit" onClick={() => onDayClick(iso)} className="text-brand-blue hover:underline">
            + New Post
          </WorkButton>
        </div>
      ) : (
        <div className="space-y-2">
          {dayPosts.map((p) => (
            <button
              key={p.id}
              onClick={() => onPostClick(p, iso)}
              className={tc(theme, "w-full text-left rounded-md border border-zinc-800 p-2.5 hover:border-brand-blue transition", "w-full text-left rounded-md border border-zinc-200 p-2.5 hover:border-brand-blue transition")}
            >
              <div className="flex items-center gap-2">
                <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${STATUS_DOT[p.status] || "bg-zinc-500"}`} />
                <span>{PLATFORM_ICONS[p.platform] || "📱"}</span>
                <span className="text-xs font-medium">{PLATFORM_LABELS[p.platform] || p.platform}</span>
                <span className="text-xs uppercase text-zinc-500">{p.status === "published" ? "Simulated publication" : p.status}</span>
                {p.scheduled_time && <span className="text-xs text-zinc-500 ml-auto">{p.scheduled_time.slice(11, 16)}</span>}
              </div>
              <div className="text-sm mt-1 whitespace-pre-wrap">{p.content || "(no caption)"}</div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function FeedView({
  theme,
  posts,
  onChanged,
  onEdit,
}: {
  theme: Theme;
  posts: SocialPost[];
  onChanged: () => void;
  onEdit: (post: SocialPost) => void;
}) {
  const [busy, setBusy] = useState<string | null>(null);

  async function handlePublish(id: string) {
    setBusy(id);
    try {
      await publishSocialPost(id);
      onChanged();
    } catch (e) {
      alert((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  async function handleCancel(id: string) {
    setBusy(id);
    try {
      await cancelSocialPost(id);
      onChanged();
    } catch (e) {
      alert((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  if (posts.length === 0) {
    return <div className="text-sm text-zinc-500">No posts yet -- use "+ New Post" to draft one.</div>;
  }

  return (
    <div className="space-y-2">
      {posts.map((p) => (
        <div key={p.id} className={tc(theme, "rounded-lg border border-black/20 bg-brand-charcoal p-3", "rounded-lg border border-zinc-200 bg-zinc-50 p-3")}>
          <div className="flex items-center justify-between gap-2">
            <WorkButton type="submit" className="flex items-center gap-2" onClick={() => onEdit(p)}>
              <span>{PLATFORM_ICONS[p.platform] || "📱"}</span>
              <span className="text-sm font-medium">{PLATFORM_LABELS[p.platform] || p.platform}</span>
              <span
                className={
                  "text-xs px-1.5 py-0.5 rounded uppercase " +
                  (p.status === "published" ? "bg-green-900 text-green-300" : p.status === "cancelled" ? "bg-zinc-800 text-zinc-500" : p.status === "scheduled" ? "bg-amber-900 text-amber-300" : "bg-zinc-800 text-zinc-400")
                }
              >
                {p.status === "published" ? "Simulated publication" : p.status}
              </span>
            </WorkButton>
            <div className="flex items-center gap-2">
              <WorkButton type="submit" onClick={() => onEdit(p)} className="text-xs px-2 py-1 rounded border border-zinc-700 text-zinc-400 hover:text-white transition">
                Edit
              </WorkButton>
              {(p.status === "draft" || p.status === "scheduled") && (
                <>
                  <WorkButton type="submit" variant="primary" disabled={busy === p.id} onClick={() => handlePublish(p.id)} className="text-xs px-2 py-1 rounded bg-brand-blue text-white hover:opacity-90 transition disabled:opacity-50">
                    Simulate publish
                  </WorkButton>
                  <WorkButton type="submit" disabled={busy === p.id} onClick={() => handleCancel(p.id)} className="text-xs px-2 py-1 rounded border border-zinc-700 text-zinc-400 hover:text-white transition disabled:opacity-50">
                    Cancel
                  </WorkButton>
                </>
              )}
            </div>
          </div>
          <div className="text-sm mt-1.5 whitespace-pre-wrap">{p.content}</div>
          {p.scheduled_time && <div className="text-xs text-zinc-500 mt-1">Scheduled: {new Date(p.scheduled_time).toLocaleString()}</div>}
          {!p.scheduled_time && p.target_date && p.status === "draft" && (
            <div className="text-xs text-zinc-500 mt-1">Planned for: {formatCalendarDate(p.target_date)}</div>
          )}
          {p.linked_vehicle_ids?.length > 0 && <div className="text-xs text-zinc-500 mt-1">🚗 {p.linked_vehicle_ids.length} vehicle(s) attached</div>}
        </div>
      ))}
    </div>
  );
}

function PostComposerModal({
  theme,
  platforms,
  date,
  editingPostId,
  dayPosts,
  onClose,
  onSwitchPost,
  onSaved,
}: {
  theme: Theme;
  platforms: SocialPlatform[];
  date: string;
  editingPostId: string | null;
  dayPosts: CalendarPost[];
  onClose: () => void;
  onSwitchPost: (id: string) => void;
  onSaved: () => void;
}) {
  const [loadingPost, setLoadingPost] = useState(!!editingPostId);
  const [editingStatus, setEditingStatus] = useState<string | null>(null);
  const [selectedPlatforms, setSelectedPlatforms] = useState<SocialPlatform[]>(platforms[0] ? [platforms[0]] : []);
  const [content, setContent] = useState("");
  const [postDate, setPostDate] = useState(date);
  const [timeOfDay, setTimeOfDay] = useState("09:00");
  const [mode, setMode] = useState<"draft" | "schedule" | "now">("draft");
  const [invQuery, setInvQuery] = useState("");
  const [invResults, setInvResults] = useState<LinkedVehicle[]>([]);
  const [linked, setLinked] = useState<LinkedVehicle[]>([]);
  const [saving, setSaving] = useState(false);
  const [aiGoal, setAiGoal] = useState("");
  const [aiTone, setAiTone] = useState("");
  const [aiBusy, setAiBusy] = useState(false);
  const [aiNote, setAiNote] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);

  useEffect(() => {
    if (!editingPostId) {
      setLoadingPost(false);
      return;
    }
    setLoadingPost(true);
    getSocialPost(editingPostId)
      .then((p) => {
        setEditingStatus(p.status);
        setSelectedPlatforms([p.platform]);
        setContent(p.content);
        setLinked(p.linked_vehicles || []);
        if (p.status === "scheduled" && p.scheduled_time) {
          setMode("schedule");
          const [d, t] = p.scheduled_time.split("T");
          if (d) setPostDate(d);
          if (t) setTimeOfDay(t.slice(0, 5));
        } else {
          setMode("draft");
          if (p.target_date) setPostDate(p.target_date);
        }
      })
      .catch((e) => setFormError((e as Error).message))
      .finally(() => setLoadingPost(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editingPostId]);

  function togglePlatform(p: SocialPlatform) {
    if (editingPostId) {
      setSelectedPlatforms([p]);
      return;
    }
    setSelectedPlatforms((prev) => (prev.includes(p) ? prev.filter((x) => x !== p) : [...prev, p]));
  }

  async function handleSearch() {
    setFormError(null);
    try { setInvResults(await searchInventoryForPost(invQuery)); }
    catch (e) { setFormError((e as Error).message); }
  }

  // AI caption generation (session 113 follow-up) -- grounded in the first linked
  // vehicle's real attributes when one is attached, never invents pricing/trim
  // details on its own. Falls back to a plain templated caption (still real, not an
  // error) if OpenAI can't be reached -- ai_generated tells us which happened.
  async function handleGenerateCaption() {
    if (!selectedPlatforms[0]) return;
    setAiBusy(true);
    setAiNote(null);
    try {
      const result = await generateSocialCaption({
        platform: selectedPlatforms[0],
        goal: aiGoal || undefined,
        tone: aiTone || undefined,
        vehicleId: linked[0]?.id,
      });
      setContent(result.caption);
      setAiNote(result.ai_generated ? "✨ AI-drafted -- review before posting." : "Drafted from a template (AI unavailable) -- review before posting.");
    } catch (e) {
      alert((e as Error).message);
    } finally {
      setAiBusy(false);
    }
  }

  function attachVehicle(v: LinkedVehicle) {
    if (!linked.find((l) => l.id === v.id)) setLinked([...linked, v]);
  }

  function removeVehicle(id: string) {
    setLinked(linked.filter((l) => l.id !== id));
  }

  const isReadOnly = editingStatus === "published" || editingStatus === "cancelled";
  const scheduledTimeValue = `${postDate}T${timeOfDay}`;

  async function handleSubmit() {
    setSaving(true);
    setFormError(null);
    try {
      if (editingPostId) {
        const patch: Record<string, unknown> = {
          content,
          platform: selectedPlatforms[0],
          linked_vehicle_ids: linked.map((l) => l.id),
        };
        if (mode === "schedule") {
          patch.scheduled_time = scheduledTimeValue;
          patch.target_date = null;
        } else if (mode === "draft") {
          patch.scheduled_time = null;
          patch.target_date = postDate;
        }
        await updateSocialPost(editingPostId, patch);
        if (mode === "now") {
          await publishSocialPost(editingPostId);
        }
      } else {
        const targets = selectedPlatforms.length ? selectedPlatforms : platforms.slice(0, 1);
        for (const plat of targets) {
          const created = await createSocialPost({
            platform: plat,
            content,
            linked_vehicle_ids: linked.map((l) => l.id),
            scheduled_time: mode === "schedule" ? scheduledTimeValue : null,
            target_date: mode !== "schedule" ? postDate : null,
          });
          if (mode === "now") {
            await publishSocialPost(created.id);
          }
        }
      }
      onSaved();
    } catch (e) {
      setFormError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function handleCancelPost() {
    if (!editingPostId) return;
    setSaving(true);
    try {
      await cancelSocialPost(editingPostId);
      onSaved();
    } catch (e) {
      alert((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  const textClass = tc(theme, "bg-zinc-900 border-zinc-700 text-white placeholder:text-zinc-600", "bg-white border-zinc-300 text-black placeholder:text-zinc-400");
  const formattedDate = new Date(`${postDate}T00:00:00`).toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" });

  return (
    <WorkOverlay className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div
        onClick={(e) => e.stopPropagation()}
        className={tc(theme, "w-full max-w-xl max-h-[90vh] overflow-y-auto rounded-xl border border-black/20 bg-brand-charcoal text-white shadow-2xl", "w-full max-w-xl max-h-[90vh] overflow-y-auto rounded-xl border border-zinc-200 bg-white text-black shadow-2xl")}
      >
        <div className={tc(theme, "flex items-center justify-between px-4 py-3 border-b border-zinc-800", "flex items-center justify-between px-4 py-3 border-b border-zinc-200")}>
          <div>
            <div className="text-sm font-brand uppercase tracking-wide">{editingPostId ? "Edit Post" : "Share to Social Media"}</div>
            <div className="text-xs text-zinc-500">{formattedDate}</div>
          </div>
          <WorkButton type="submit" onClick={onClose} className="text-zinc-500 hover:text-white text-lg leading-none">✕</WorkButton>
        </div>

        {formError && <p role="alert" className="mx-4 mt-3 text-sm text-red-600">{formError}</p>}
        {loadingPost ? (
          <div className="p-4 text-sm text-zinc-500">Loading…</div>
        ) : (
          <div className="p-4 space-y-3">
            {dayPosts.length > 0 && (
              <div>
                <label className="text-xs text-zinc-500">Also on this day</label>
                <div className="flex flex-wrap gap-1.5 mt-1">
                  {dayPosts.map((p) => (
                    <WorkButton type="submit"
                      key={p.id}
                      onClick={() => onSwitchPost(p.id)}
                      className="text-xs px-2 py-1 rounded border border-zinc-700 text-zinc-400 hover:text-white transition flex items-center gap-1"
                    >
                      <span className={`w-1.5 h-1.5 rounded-full ${STATUS_DOT[p.status] || "bg-zinc-500"}`} />
                      {PLATFORM_ICONS[p.platform] || "📱"} {p.content ? p.content.slice(0, 24) : "(no caption)"}
                    </WorkButton>
                  ))}
                </div>
              </div>
            )}

            <div>
              <label className="text-xs text-zinc-500">Channels{!editingPostId && " (select one or more)"}</label>
              <div className="flex flex-wrap gap-1.5 mt-1">
                {platforms.map((p) => (
                  <WorkButton type="submit"
                    key={p}
                    disabled={isReadOnly}
                    onClick={() => togglePlatform(p)}
                    className={
                      selectedPlatforms.includes(p)
                        ? "text-xs px-2.5 py-1.5 rounded-md bg-brand-blue text-white font-medium transition disabled:opacity-60"
                        : "text-xs px-2.5 py-1.5 rounded-md border border-zinc-700 text-zinc-400 hover:text-white transition disabled:opacity-60"
                    }
                  >
                    {PLATFORM_ICONS[p]} {PLATFORM_LABELS[p]}
                  </WorkButton>
                ))}
              </div>
            </div>

            <div>
              <label className="text-xs text-zinc-500">Caption</label>
              <WorkTextarea aria-label="Caption"
                value={content}
                onChange={(e) => setContent(e.target.value)}
                rows={4}
                disabled={isReadOnly}
                placeholder="Write your post…"
                className={`w-full mt-1 rounded-md border px-3 py-2 text-sm disabled:opacity-60 ${textClass}`}
              />
              {!isReadOnly && (
                <div className={tc(theme, "mt-1.5 rounded-md border border-zinc-800 p-2 space-y-1.5", "mt-1.5 rounded-md border border-zinc-200 p-2 space-y-1.5")}>
                  <div className="flex items-center gap-1.5">
                    <WorkField label="Goal"><WorkInput
                      value={aiGoal}
                      onChange={(e) => setAiGoal(e.target.value)}
                      placeholder="Goal (e.g. promote this truck)"
                      className={`flex-1 rounded-md border px-2 py-1 text-xs ${textClass}`}
                    /></WorkField>
                    <WorkField label="Tone (optional)"><WorkInput
                      value={aiTone}
                      onChange={(e) => setAiTone(e.target.value)}
                      placeholder="Tone (optional)"
                      className={`w-32 rounded-md border px-2 py-1 text-xs ${textClass}`}
                    /></WorkField>
                    <WorkButton type="submit" variant="primary"
                      onClick={handleGenerateCaption}
                      disabled={aiBusy || !selectedPlatforms[0]}
                      className="text-xs px-2.5 py-1 rounded-md bg-brand-blue text-white font-medium transition disabled:opacity-50 shrink-0"
                    >
                      {aiBusy ? "Thinking…" : "✨ AI Generate"}
                    </WorkButton>
                  </div>
                  {linked[0] && <div className="text-xs text-zinc-500">Grounded in: {linked[0].year} {linked[0].make} {linked[0].model}</div>}
                  {aiNote && <div className="text-xs text-brand-teal">{aiNote}</div>}
                </div>
              )}
            </div>

            <div>
              <label className="text-xs text-zinc-500">🚗 Drop in inventory</label>
              <div className="flex gap-1.5 mt-1">
                <WorkField label="Search unsold inventory"><WorkInput
                  value={invQuery}
                  onChange={(e) => setInvQuery(e.target.value)}
                  disabled={isReadOnly}
                  placeholder="Search unsold inventory…"
                  className={`flex-1 rounded-md border px-3 py-1.5 text-sm disabled:opacity-60 ${textClass}`}
                /></WorkField>
                <WorkButton type="submit" onClick={handleSearch} disabled={isReadOnly} className="text-xs px-3 py-1.5 rounded-md border border-zinc-700 text-zinc-400 hover:text-white transition disabled:opacity-60">
                  Search
                </WorkButton>
              </div>
              {invResults.length > 0 && (
                <div className={tc(theme, "mt-1.5 border border-zinc-800 rounded-md divide-y divide-zinc-800 max-h-32 overflow-y-auto", "mt-1.5 border border-zinc-200 rounded-md divide-y divide-zinc-200 max-h-32 overflow-y-auto")}>
                  {invResults.map((v) => (
                    <WorkButton type="submit" key={v.id} onClick={() => attachVehicle(v)} className="w-full text-left px-2.5 py-1.5 text-xs hover:bg-zinc-800/50 transition">
                      {v.year} {v.make} {v.model} {v.trim} — {v.price ? `$${Number(v.price).toLocaleString()}` : "—"}
                    </WorkButton>
                  ))}
                </div>
              )}
              {linked.length > 0 && (
                <div className="flex flex-wrap gap-1.5 mt-1.5">
                  {linked.map((v) => (
                    <span key={v.id} className="text-xs px-2 py-1 rounded bg-zinc-800 text-zinc-300 flex items-center gap-1.5">
                      {v.year} {v.make} {v.model}
                      {!isReadOnly && (
                        <WorkButton type="submit" onClick={() => removeVehicle(v.id)} className="text-zinc-500 hover:text-white">✕</WorkButton>
                      )}
                    </span>
                  ))}
                </div>
              )}
            </div>

            {!isReadOnly && (
              <div className={tc(theme, "rounded-lg border border-zinc-800 p-3 space-y-2", "rounded-lg border border-zinc-200 p-3 space-y-2")}>
                <label className="text-xs text-zinc-500">Post settings</label>
                <div className="flex flex-col gap-1.5">
                  {([
                    { key: "draft", label: "Set as draft", hint: "Parked on this day, not sent." },
                    { key: "schedule", label: "Schedule", hint: "Saves a planned time. Live platform delivery is not connected." },
                    { key: "now", label: "Simulate publish", hint: "Records a simulated publication; nothing is sent to a social platform." },
                  ] as const).map((opt) => (
                    <label key={opt.key} className="flex items-center gap-2 text-xs cursor-pointer">
                      <WorkInput type="radio" name="post-mode" checked={mode === opt.key} onChange={() => setMode(opt.key)} />
                      <span className="font-medium">{opt.label}</span>
                      <span className="text-zinc-500">— {opt.hint}</span>
                    </label>
                  ))}
                </div>

                <div className="flex gap-2 pt-1">
                  <div className="flex-1">
                    <label className="text-xs text-zinc-500">Date</label>
                    <WorkInput aria-label="Date"
                      type="date"
                      value={postDate}
                      onChange={(e) => setPostDate(e.target.value)}
                      disabled={mode === "now"}
                      className={`w-full mt-0.5 rounded-md border px-2 py-1 text-xs disabled:opacity-50 ${textClass}`}
                    />
                  </div>
                  {mode === "schedule" && (
                    <div className="flex-1">
                      <label className="text-xs text-zinc-500">Time</label>
                      <WorkInput aria-label="Time"
                        type="time"
                        value={timeOfDay}
                        onChange={(e) => setTimeOfDay(e.target.value)}
                        className={`w-full mt-0.5 rounded-md border px-2 py-1 text-xs ${textClass}`}
                      />
                    </div>
                  )}
                </div>
              </div>
            )}

            <div className="flex items-center justify-between pt-1">
              <div>
                {editingPostId && (editingStatus === "draft" || editingStatus === "scheduled") && (
                  <WorkButton type="submit" onClick={handleCancelPost} disabled={saving} className="text-xs px-3 py-1.5 rounded border border-zinc-700 text-zinc-400 hover:text-white transition disabled:opacity-50">
                    Cancel Post
                  </WorkButton>
                )}
              </div>
              <div className="flex items-center gap-2">
                <WorkButton type="submit" onClick={onClose} className="text-xs px-3 py-2 rounded-md border border-zinc-700 text-zinc-400 hover:text-white transition">
                  Close
                </WorkButton>
                {!isReadOnly && (
                  <WorkButton type="submit" variant="primary"
                    onClick={handleSubmit}
                    disabled={saving || !content.trim() || selectedPlatforms.length === 0}
                    className="text-xs px-4 py-2 rounded-md bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50"
                  >
                    {saving ? "Saving…" : mode === "now" ? "Simulate Publish" : mode === "schedule" ? "Save Scheduled Post" : "Save Draft"}
                  </WorkButton>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </WorkOverlay>
  );
}

// --- Reputation tab ---

function ReputationTab({ theme }: { theme: Theme }) {
  const [summary, setSummary] = useState<Record<string, any> | null>(null);
  const [reviews, setReviews] = useState<Review[]>([]);
  const [alerts, setAlerts] = useState<BadReviewAlert[]>([]);
  const [competitors, setCompetitors] = useState<CompetitorTracking | null>(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<"all" | "unresponded">("all");

  function refresh() {
    setLoading(true);
    Promise.all([getReputationSummary(), listReviews(), listBadReviewAlerts(), getCompetitorTracking()])
      .then(([s, r, a, c]) => {
        setSummary(s);
        setReviews(r);
        setAlerts(a);
        setCompetitors(c);
      })
      .finally(() => setLoading(false));
  }

  useEffect(refresh, []);

  const visibleReviews = filter === "unresponded" ? reviews.filter((r) => !r.responded) : reviews;

  if (loading) return <div className="p-4 text-sm text-zinc-500">Loading…</div>;

  return (
    <div className="flex-1 min-h-0 overflow-y-auto p-4 space-y-4">
      {/* KPI strip */}
      <div className="grid grid-cols-4 gap-3">
        {[
          { label: "Total Reviews", value: (summary?.total_reviews as number) ?? reviews.length },
          { label: "Unresponded (bad)", value: alerts.length },
          { label: "Avg Rating", value: competitors?.you.avg_rating ?? "—" },
          { label: "Platforms Tracked", value: Object.keys((summary?.by_platform as object) || {}).length },
        ].map((k, i) => (
          <div key={k.label} className={tc(theme, "relative overflow-hidden rounded-lg border border-black/20 bg-brand-charcoal p-3 pl-4", "relative overflow-hidden rounded-lg border border-zinc-200 bg-zinc-50 p-3 pl-4")}>
            <span className="nxt-accent absolute left-0 top-0 bottom-0 w-2.5"
              style={{ background: KPI_RIBBON[i % KPI_RIBBON.length], clipPath: "polygon(0 0, 100% 0, 45% 100%, 0 100%)" }}
            />
            <div className="text-2xl font-semibold">{k.value}</div>
            <div className="text-xs font-brand uppercase tracking-wide text-zinc-500">{k.label}</div>
          </div>
        ))}
      </div>

      {alerts.length > 0 && (
        <div className="rounded-lg border border-red-900 bg-red-950/40 p-3">
          <div className="text-xs font-medium text-red-300 mb-1.5">🔔 Bad Review Alerts ({alerts.length})</div>
          <div className="text-xs text-red-400/80">Unresponded reviews at or below 3 stars -- respond below, or use the bot to auto-draft a response.</div>
        </div>
      )}

      {competitors && (
        <div className={tc(theme, "rounded-lg border border-black/20 bg-brand-charcoal p-3", "rounded-lg border border-zinc-200 bg-zinc-50 p-3")}>
          <div className="text-xs font-medium mb-2">Competitor Social Tracking</div>
          <div className="grid grid-cols-4 gap-2 text-xs">
            <div className="font-medium">You: {competitors.you.avg_rating ?? "—"}★ ({competitors.you.review_count})</div>
            {competitors.competitors.map((c) => (
              <div key={c.label} className="text-zinc-400">{c.label}: {c.avg_rating}★ ({c.review_count})</div>
            ))}
          </div>
          <div className="text-xs text-zinc-600 mt-2">{competitors.notice}</div>
        </div>
      )}

      <div className="flex items-center gap-2">
        {(["all", "unresponded"] as const).map((f) => (
          <WorkButton aria-pressed={filter === f} type="submit"
            key={f}
            onClick={() => setFilter(f)}
            className={
              filter === f
                ? "text-xs px-2.5 py-1 rounded-md bg-zinc-200 text-black font-medium transition"
                : tc(theme, "text-xs px-2.5 py-1 rounded-md text-zinc-400 hover:text-white hover:bg-zinc-900 transition", "text-xs px-2.5 py-1 rounded-md text-zinc-600 hover:text-black hover:bg-zinc-200 transition")
            }
          >
            {f === "all" ? "All Reviews" : "Unresponded"}
          </WorkButton>
        ))}
      </div>

      <div className="space-y-2">
        {visibleReviews.map((r) => (
          <ReviewCard key={r.id} theme={theme} review={r} onChanged={refresh} />
        ))}
      </div>
    </div>
  );
}

function ReviewCard({ theme, review, onChanged }: { theme: Theme; review: Review; onChanged: () => void }) {
  const [responding, setResponding] = useState(false);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);

  async function handleRespond() {
    setBusy(true);
    try {
      await respondToReview(review.id, text);
      setResponding(false);
      onChanged();
    } catch (e) {
      alert((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function handleAutoRespond() {
    setBusy(true);
    try {
      await autoRespondToReview(review.id);
      onChanged();
    } catch (e) {
      alert((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={tc(theme, "rounded-lg border border-black/20 bg-brand-charcoal p-3", "rounded-lg border border-zinc-200 bg-zinc-50 p-3")}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span>{PLATFORM_ICONS[review.platform] || "⭐"}</span>
          <span className="text-sm font-medium">{review.author_name}</span>
          <Stars rating={review.rating} />
        </div>
        {!review.responded && (
          <div className="flex items-center gap-2">
            <WorkButton type="submit" onClick={handleAutoRespond} disabled={busy} className="text-xs px-2 py-1 rounded border border-zinc-700 text-zinc-400 hover:text-white transition disabled:opacity-50">
              🤖 Auto-respond
            </WorkButton>
            <WorkButton type="submit" variant="primary" onClick={() => setResponding(!responding)} className="text-xs px-2 py-1 rounded bg-brand-blue text-white hover:opacity-90 transition">
              Respond
            </WorkButton>
          </div>
        )}
      </div>
      <div className="text-sm mt-1.5">{review.text}</div>

      {review.responded && (
        <div className={tc(theme, "mt-2 rounded-md bg-zinc-800/50 p-2 text-xs text-zinc-300", "mt-2 rounded-md bg-zinc-100 p-2 text-xs text-zinc-700")}>
          <span className="text-zinc-500">{review.auto_responded ? "🤖 Bot response: " : "Response: "}</span>
          {review.response_text}
        </div>
      )}

      {responding && (
        <div className="mt-2 space-y-1.5">
          <WorkField label="Write a response"><WorkTextarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={3}
            placeholder="Write a response…"
            className={tc(theme, "w-full rounded-md border border-zinc-700 bg-zinc-900 text-white px-2 py-1.5 text-xs", "w-full rounded-md border border-zinc-300 bg-white text-black px-2 py-1.5 text-xs")}
          /></WorkField>
          <WorkButton type="submit" variant="primary" onClick={handleRespond} disabled={busy || !text.trim()} className="text-xs px-3 py-1 rounded bg-brand-blue text-white hover:opacity-90 transition disabled:opacity-50">
            Post Response
          </WorkButton>
        </div>
      )}
    </div>
  );
}
