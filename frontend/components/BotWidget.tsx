"use client";

// The agentic bot (2026-07-13, session 36) -- Sam: "create a agentic bot for each
// section... it will prompt the user throughout the day with things that need to be
// done depending on their role assigned and section they're in... the prompt can then
// be clicked and loaded into the chat to be done, or if the person is sick / not
// there, the admin can decide to run the bot version of that operator for the day."
// Square turquoise button with a robot icon -- went cartoon robot -> NeuralIcon's
// circuit-chip glyph (session "much more themed, elegant... neural circuit / brain...
// something classier") -> this, a third icon (session 41, Sam: "lets go back to a
// robot, but lets have something that just looks modern and clean") --
// components/Icons.tsx's RobotIcon, a simple clean-line robot silhouette rather than
// either the literal cartoon bot or the circuit/chip abstraction. Next to the Send
// button on
// every chat-first page (distinct from the floating yellow "?" HelpWidget button — this
// one is proactive/personalized, that one is reactive/reference). Clicking a task prompt
// hands it straight to chat via `onRunPrompt` (the page's own sendMessage) and records
// an "acted" event; dismissing one records a "dismissed" event — both feed
// core/bot_learning.py's heuristic prioritization server-side.

import { useEffect, useState } from "react";
import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";
import { RobotIcon } from "@/components/Icons";
import { angledClip } from "@/components/BrandAngles";

export type BotTask = {
  key: string;
  title: string;
  description: string;
  prompt: string;
  priority: number;
};

// "Help Me With This Screen" (2026-07-19) -- Sam's own explicit ask: "add this
// into the bot feature... into the bar... when the user clicks on prompts
// they're loaded into the main chat (the chat stays as the interface, the bot
// is just its sidekick / prompter)." A screen-guidance item is a superset of
// BotTask (same key/title/description/prompt/priority contract so it reuses
// the exact same card UI/click-to-chat mechanism below) plus a few real,
// display-only fields (severity/count/basis) core/screen_guidance.py's own
// composition over core/enterprise_risk_center.py already carries through.
export type ScreenGuidanceItem = BotTask & {
  severity: "low" | "medium" | "high" | "critical";
  // Exception-sourced items always carry a real count; recommendation-sourced
  // items (core/readiness_recommendations.py) don't have a single top-level
  // count field, so this is null for those -- core/screen_guidance.py's own
  // "source" field distinguishes which.
  count: number | null;
  basis?: string | null;
  resolve?: { department?: string; item_key?: string; hint?: string } | null;
  source?: "exception" | "recommendation";
  // "Automate It" (2026-07-19) -- reuses core/network_playbooks.py's real 0/1/3
  // automation-tier scoring verbatim. 0 = no matching Workflow Automation
  // trigger type exists yet (no button); 1 = a real trigger type exists and no
  // live rule covers it yet (a real "Automate It" action, ADMIN/OPERATIONS
  // only, matching the backend gate); 3 = a live rule already covers this (an
  // "Already Automated" badge, no action). Tier 2 is deliberately unused.
  automation?: { tier: number; label: string; note?: string } | null;
  // "Do It" (2026-07-19) -- true only for the two guidance items with a real,
  // safe, bulk-suitable action already built (a missing Title / missing Deal
  // Jacket document request, core/document_workflows.py's real
  // request_document() run once per real currently-flagged entity). Every
  // other item is honestly false -- no fabricated fourth verb everywhere.
  do_it_available?: boolean;
};

type DirectoryEntry = { employee_id: string; role: string; name: string | null };

type CoverageRecord = {
  id: string;
  employee_id: string;
  activated_by: string;
  role: string;
  section: string;
  starts_at: string;
  ends_at: string;
  mode: "draft" | "auto";
  note: string | null;
  status: "active" | "ended";
};

const ROLE_OPTIONS = ["ADMIN", "OPERATIONS", "SALES", "MARKETING", "SERVICE", "FINANCE"];

function toLocalInputValue(date: Date) {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(
    date.getHours()
  )}:${pad(date.getMinutes())}`;
}

export function BotWidget({
  role,
  section,
  open,
  onOpenChange,
  onRunPrompt,
  onNavigate,
}: {
  role: string;
  section?: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onRunPrompt: (prompt: string) => void;
  // "Show Me ->" (2026-07-19) -- real cross-department navigation for a
  // guidance card's own resolve target, via the page's own useMenuDash()
  // instance (lib/useMenuDash.ts's open() can open ANY department's Top Menu
  // item Dash regardless of the page's currently-selected department tab,
  // the same mechanism the existing "account"/"entity" MenuDashKind values
  // already use). Optional -- pages that don't wire a menuDash instance
  // through simply don't get the button (only "Ask about it in chat ->"
  // shows), no crash.
  onNavigate?: (department: string, itemKey: string) => void;
}) {
  const [tasks, setTasks] = useState<BotTask[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [showGuidance, setShowGuidance] = useState(false);
  const [guidance, setGuidance] = useState<ScreenGuidanceItem[]>([]);
  const [guidanceLoading, setGuidanceLoading] = useState(false);
  const [guidanceError, setGuidanceError] = useState<string | null>(null);
  const [guidanceNote, setGuidanceNote] = useState<string | null>(null);
  const [guidanceFetched, setGuidanceFetched] = useState(false);

  const isAdmin = role === "ADMIN";
  const canAutomate = role === "ADMIN" || role === "OPERATIONS";

  const [automatingKey, setAutomatingKey] = useState<string | null>(null);
  const [automateMessages, setAutomateMessages] = useState<Record<string, string>>({});

  const [doingItKey, setDoingItKey] = useState<string | null>(null);
  const [doItMessages, setDoItMessages] = useState<Record<string, string>>({});

  const [showCoverageForm, setShowCoverageForm] = useState(false);
  const [directory, setDirectory] = useState<DirectoryEntry[]>([]);
  const [coverage, setCoverage] = useState<CoverageRecord[]>([]);
  const [coverageEmployeeId, setCoverageEmployeeId] = useState("");
  const [coverageRole, setCoverageRole] = useState("SALES");
  const [coverageSection, setCoverageSection] = useState("sales");
  const [coverageStarts, setCoverageStarts] = useState(() => toLocalInputValue(new Date()));
  const [coverageEnds, setCoverageEnds] = useState(() =>
    toLocalInputValue(new Date(Date.now() + 8 * 60 * 60 * 1000))
  );
  const [coverageMode, setCoverageMode] = useState<"draft" | "auto">("draft");
  const [coverageNote, setCoverageNote] = useState("");
  const [coverageError, setCoverageError] = useState<string | null>(null);
  const [coverageSubmitting, setCoverageSubmitting] = useState(false);

  async function loadTasks() {
    setLoading(true);
    setError(null);

    try {
      const params = section ? `?section=${encodeURIComponent(section)}` : "";
      const response = await fetch(`${API_BASE}/bot/tasks${params}`, {
        headers: { ...authHeaders() },
      });
      const data = await response.json();

      if (!response.ok || data.error) {
        throw new Error(data.error ?? `Backend returned ${response.status}`);
      }

      setTasks((data.tasks ?? []) as BotTask[]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to reach NXTDeal backend.");
    } finally {
      setLoading(false);
    }
  }

  async function loadGuidance() {
    setGuidanceLoading(true);
    setGuidanceError(null);

    try {
      const params = section ? `?section=${encodeURIComponent(section)}` : "";
      const response = await fetch(`${API_BASE}/bot/screen-guidance${params}`, {
        headers: { ...authHeaders() },
      });
      const data = await response.json();

      if (!response.ok || data.error) {
        throw new Error(data.error ?? `Backend returned ${response.status}`);
      }

      setGuidance((data.guidance ?? []) as ScreenGuidanceItem[]);
      setGuidanceNote(data.note ?? null);
    } catch (err) {
      setGuidanceError(err instanceof Error ? err.message : "Unable to reach NXTDeal backend.");
    } finally {
      setGuidanceLoading(false);
      setGuidanceFetched(true);
    }
  }

  async function loadCoverage() {
    try {
      const response = await fetch(`${API_BASE}/bot/coverage?active_only=true`, {
        headers: { ...authHeaders() },
      });
      const data = await response.json();
      if (response.ok && !data.error) {
        setCoverage((data.coverage ?? []) as CoverageRecord[]);
      }
    } catch {
      // Best-effort -- coverage list is a secondary admin-only view inside this widget.
    }
  }

  async function loadDirectory() {
    try {
      const response = await fetch(`${API_BASE}/messaging/directory`, {
        headers: { ...authHeaders() },
      });
      const data = await response.json();
      if (response.ok && Array.isArray(data)) {
        setDirectory(data as DirectoryEntry[]);
      }
    } catch {
      // Best-effort -- falls back to a plain text employee_id field.
    }
  }

  useEffect(() => {
    if (!open) return;
    loadTasks();
    if (isAdmin) {
      loadCoverage();
      loadDirectory();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, section]);

  // A different screen means stale guidance -- reset so the next "Help Me With
  // This Screen" click re-fetches for the new section rather than showing what
  // was relevant to wherever the user was looking before.
  useEffect(() => {
    setShowGuidance(false);
    setGuidance([]);
    setGuidanceFetched(false);
    setGuidanceNote(null);
    setGuidanceError(null);
  }, [section]);

  async function sendFeedback(taskKey: string, eventType: "acted" | "dismissed") {
    try {
      await fetch(`${API_BASE}/bot/tasks/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ task_key: taskKey, event_type: eventType }),
      });
    } catch {
      // Best-effort -- learning signal, not user-visible if it fails to record.
    }
  }

  function runTask(task: BotTask) {
    onRunPrompt(task.prompt);
    sendFeedback(task.key, "acted");
    setTasks((prev) => prev.filter((t) => t.key !== task.key));
    onOpenChange(false);
  }

  function dismissTask(task: BotTask) {
    sendFeedback(task.key, "dismissed");
    setTasks((prev) => prev.filter((t) => t.key !== task.key));
  }

  // "Help Me With This Screen" reuses runTask/dismissTask's own click-to-chat
  // mechanism verbatim (Sam's own instruction: "the chat stays as the
  // interface, the bot is just its sidekick / prompter") -- deliberately does
  // NOT call sendFeedback(), since core/bot_learning.py's affinity/suppression
  // learning loop is scoped to core/bot_tasks.py's own TASK_CATALOG keys, not
  // this separate recommendation source; recording feedback against a key it
  // never checks would be a no-op that looks like a real signal but isn't.
  function runGuidance(item: ScreenGuidanceItem) {
    onRunPrompt(item.prompt);
    setGuidance((prev) => prev.filter((g) => g.key !== item.key));
    onOpenChange(false);
  }

  function dismissGuidance(item: ScreenGuidanceItem) {
    setGuidance((prev) => prev.filter((g) => g.key !== item.key));
  }

  // Navigates straight to the real screen the item's own resolve target
  // names, rather than asking the AI assistant about it first -- a faster
  // path for someone who already knows what they want to do about it.
  // Deliberately does not remove the card or close the widget (matching
  // "Show Me" being a look, not a completed action) -- dismiss/run stay
  // the only actions that clear a card.
  function navigateToResolve(item: ScreenGuidanceItem) {
    if (!onNavigate || !item.resolve?.department || !item.resolve?.item_key) return;
    onNavigate(item.resolve.department, item.resolve.item_key);
    onOpenChange(false);
  }

  // "Automate It" (2026-07-19) -- the real, one-click tier-1 action. Calls
  // core/bot_api.py's automate_screen_guidance_api(), which creates a live
  // core/workflow_automation.py AutomationRule via the existing ADMIN/
  // OPERATIONS-gated create_rule_api(). On success, flips this item's own
  // automation tier to 3 locally (no card removal -- "already automated" is
  // a state to show, not something to dismiss) rather than a full re-fetch.
  async function automateGuidance(item: ScreenGuidanceItem) {
    setAutomatingKey(item.key);
    setAutomateMessages((prev) => ({ ...prev, [item.key]: "" }));

    try {
      const response = await fetch(`${API_BASE}/bot/screen-guidance/automate`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ item_key: item.key, title: item.title }),
      });
      const data = await response.json();

      if (!response.ok || data.error) {
        throw new Error(data.error ?? `Backend returned ${response.status}`);
      }

      setGuidance((prev) =>
        prev.map((g) =>
          g.key === item.key
            ? { ...g, automation: { tier: 3, label: "Already Automated" } }
            : g
        )
      );
      setAutomateMessages((prev) => ({ ...prev, [item.key]: `Rule created: ${data.name}` }));
    } catch (err) {
      setAutomateMessages((prev) => ({
        ...prev,
        [item.key]: err instanceof Error ? err.message : "Unable to reach NXTDeal backend.",
      }));
    } finally {
      setAutomatingKey(null);
    }
  }

  // "Do It" (2026-07-19) -- the real, one-click bulk action for the two
  // guidance items with a real, safe action behind them. Calls
  // core/bot_api.py's do_it_screen_guidance_api(), which creates a real
  // core/document_workflows.py document-request OperationsTask once per
  // real currently-flagged entity (deduped against any already-open
  // request). Doesn't remove the card or re-fetch guidance -- the same
  // exception it's requesting documents against is still real and still
  // worth seeing, it just now has a real request task tracking it.
  async function doItGuidance(item: ScreenGuidanceItem) {
    setDoingItKey(item.key);
    setDoItMessages((prev) => ({ ...prev, [item.key]: "" }));

    try {
      const response = await fetch(`${API_BASE}/bot/screen-guidance/do-it`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ item_key: item.key }),
      });
      const data = await response.json();

      if (!response.ok || data.error) {
        throw new Error(data.error ?? `Backend returned ${response.status}`);
      }

      const parts: string[] = [];
      if (data.created_count) parts.push(`${data.created_count} request(s) created`);
      if (data.skipped_existing_count) parts.push(`${data.skipped_existing_count} already requested`);
      if (data.errors?.length) parts.push(`${data.errors.length} error(s)`);
      setDoItMessages((prev) => ({
        ...prev,
        [item.key]: parts.length ? parts.join(" · ") : "Nothing to do.",
      }));
    } catch (err) {
      setDoItMessages((prev) => ({
        ...prev,
        [item.key]: err instanceof Error ? err.message : "Unable to reach NXTDeal backend.",
      }));
    } finally {
      setDoingItKey(null);
    }
  }

  function toggleGuidance() {
    const next = !showGuidance;
    setShowGuidance(next);
    if (next && !guidanceFetched) {
      loadGuidance();
    }
  }

  const severityColor: Record<ScreenGuidanceItem["severity"], string> = {
    critical: "text-[#EE3C25]",
    high: "text-[#F4C300]",
    medium: "text-[#3FBCC4]",
    low: "text-zinc-500",
  };

  async function submitCoverage() {
    setCoverageError(null);

    if (!coverageEmployeeId.trim()) {
      setCoverageError("Pick an employee to cover for.");
      return;
    }

    setCoverageSubmitting(true);

    try {
      const response = await fetch(`${API_BASE}/bot/coverage`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({
          employee_id: coverageEmployeeId,
          role: coverageRole,
          section: coverageSection,
          starts_at: new Date(coverageStarts).toISOString(),
          ends_at: new Date(coverageEnds).toISOString(),
          mode: coverageMode,
          note: coverageNote || null,
        }),
      });

      const data = await response.json();

      if (!response.ok || data.error) {
        throw new Error(data.error ?? `Backend returned ${response.status}`);
      }

      setCoverageNote("");
      setShowCoverageForm(false);
      loadCoverage();
    } catch (err) {
      setCoverageError(err instanceof Error ? err.message : "Unable to reach NXTDeal backend.");
    } finally {
      setCoverageSubmitting(false);
    }
  }

  async function endCoverage(id: string) {
    try {
      await fetch(`${API_BASE}/bot/coverage/${encodeURIComponent(id)}/end`, {
        method: "POST",
        headers: { ...authHeaders() },
      });
      loadCoverage();
    } catch {
      // Best-effort.
    }
  }

  return (
    <div className="relative">
      <button
        data-tour-id="tour-bot-button"
        onClick={() => onOpenChange(!open)}
        title="NXTDeal Bot"
        style={angledClip(9)}
        className="h-12 w-12 shrink-0 bg-black hover:bg-zinc-900 text-brand-teal flex items-center justify-center transition"
      >
        <RobotIcon size={22} />
      </button>

      {open && (
        <div className="absolute bottom-14 right-0 z-50 w-96 max-h-[70vh] overflow-y-auto bg-zinc-900 border border-zinc-800 rounded-xl shadow-xl">
          <div className="flex items-center justify-between p-3 border-b border-zinc-800">
            <div className="text-sm font-medium">NXTDeal Bot{section ? ` — ${section}` : ""}</div>
            <button onClick={() => onOpenChange(false)} className="text-zinc-500 hover:text-white transition">
              ✕
            </button>
          </div>

          <div className="p-3 border-b border-zinc-800 space-y-2">
            <button
              onClick={toggleGuidance}
              className="w-full flex items-center justify-between text-xs font-medium text-[#3FBCC4] hover:text-white transition"
            >
              <span>🔍 Help Me With This Screen</span>
              <span className="text-zinc-500">{showGuidance ? "▲" : "▼"}</span>
            </button>

            {showGuidance && (
              <div className="space-y-2 pt-1">
                {guidanceLoading && (
                  <div className="text-xs text-zinc-500">Reading this screen's real data…</div>
                )}
                {guidanceError && <div className="text-xs text-[#EE3C25]">{guidanceError}</div>}

                {!guidanceLoading && !guidanceError && guidance.length === 0 && (
                  <div className="text-xs text-zinc-500">
                    {guidanceNote ?? "Nothing to flag on this screen right now."}
                  </div>
                )}

                {guidance.map((item) => (
                  <div key={item.key} className="bg-zinc-950 border border-zinc-800 rounded-lg p-3">
                    <div className="flex items-start justify-between gap-2">
                      <div className="text-sm font-medium">
                        <span className={severityColor[item.severity]}>●</span> {item.title}
                        {item.count != null && (
                          <span className="text-zinc-500 font-normal"> ({item.count})</span>
                        )}
                        {item.automation?.tier === 3 && (
                          <span className="ml-2 text-[10px] text-zinc-500 font-normal align-middle">
                            ✓ Already Automated
                          </span>
                        )}
                      </div>
                      <button
                        onClick={() => dismissGuidance(item)}
                        title="Not useful"
                        className="text-zinc-600 hover:text-white transition text-xs shrink-0"
                      >
                        ✕
                      </button>
                    </div>
                    {item.description && (
                      <div className="text-xs text-zinc-400 mt-1 mb-2">{item.description}</div>
                    )}
                    <div className="flex items-center gap-3 flex-wrap">
                      <button
                        onClick={() => runGuidance(item)}
                        className="text-xs text-[#3FBCC4] hover:text-white transition"
                      >
                        Ask about it in chat →
                      </button>
                      {onNavigate && item.resolve?.department && item.resolve?.item_key && (
                        <button
                          onClick={() => navigateToResolve(item)}
                          title={item.resolve.hint ?? undefined}
                          className="text-xs text-zinc-400 hover:text-white transition"
                        >
                          Show me →
                        </button>
                      )}
                      {canAutomate && item.automation?.tier === 1 && (
                        <button
                          onClick={() => automateGuidance(item)}
                          disabled={automatingKey === item.key}
                          title={item.automation.note ?? undefined}
                          className="text-xs text-[#F4C300] hover:text-white transition disabled:opacity-50"
                        >
                          {automatingKey === item.key ? "Creating rule…" : "🤖 Automate it →"}
                        </button>
                      )}
                      {canAutomate && item.do_it_available && (
                        <button
                          onClick={() => doItGuidance(item)}
                          disabled={doingItKey === item.key}
                          title="Request the missing document(s) for every entity currently flagged."
                          className="text-xs text-green-400 hover:text-white transition disabled:opacity-50"
                        >
                          {doingItKey === item.key ? "Requesting…" : "✅ Do it →"}
                        </button>
                      )}
                    </div>
                    {automateMessages[item.key] && (
                      <div className="text-[10px] text-zinc-400 mt-1">{automateMessages[item.key]}</div>
                    )}
                    {doItMessages[item.key] && (
                      <div className="text-[10px] text-zinc-400 mt-1">{doItMessages[item.key]}</div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="p-3 space-y-2">
            {loading && <div className="text-xs text-zinc-500">Checking what's worth a look…</div>}
            {error && <div className="text-xs text-[#EE3C25]">{error}</div>}

            {!loading && !error && tasks.length === 0 && (
              <div className="text-xs text-zinc-500">Nothing urgent right now — nice work.</div>
            )}

            {tasks.map((task) => (
              <div key={task.key} className="bg-zinc-950 border border-zinc-800 rounded-lg p-3">
                <div className="flex items-start justify-between gap-2">
                  <div className="text-sm font-medium">{task.title}</div>
                  <button
                    onClick={() => dismissTask(task)}
                    title="Not useful"
                    className="text-zinc-600 hover:text-white transition text-xs shrink-0"
                  >
                    ✕
                  </button>
                </div>
                <div className="text-xs text-zinc-400 mt-1 mb-2">{task.description}</div>
                <button
                  onClick={() => runTask(task)}
                  className="text-xs text-[#3FBCC4] hover:text-white transition"
                >
                  Run it in chat →
                </button>
              </div>
            ))}
          </div>

          {isAdmin && (
            <div className="border-t border-zinc-800 p-3 space-y-3">
              <div className="flex items-center justify-between">
                <div className="text-xs uppercase text-zinc-500">Bot Coverage</div>
                <button
                  onClick={() => setShowCoverageForm((v) => !v)}
                  className="text-xs text-[#3FBCC4] hover:text-white transition"
                >
                  {showCoverageForm ? "Cancel" : "+ Cover for a teammate"}
                </button>
              </div>

              {coverage.length > 0 && (
                <div className="space-y-2">
                  {coverage.map((c) => (
                    <div key={c.id} className="bg-zinc-950 border border-zinc-800 rounded-lg p-2 text-xs">
                      <div className="flex items-center justify-between">
                        <div>
                          {c.employee_id} · {c.mode} · {c.section}
                        </div>
                        <button
                          onClick={() => endCoverage(c.id)}
                          className="text-[#EE3C25] hover:text-white transition"
                        >
                          End
                        </button>
                      </div>
                      <div className="text-zinc-500 mt-1">
                        until {new Date(c.ends_at).toLocaleString()}
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {showCoverageForm && (
                <div className="space-y-2">
                  {directory.length > 0 ? (
                    <select
                      value={coverageEmployeeId}
                      onChange={(e) => setCoverageEmployeeId(e.target.value)}
                      className="w-full h-9 px-2 text-xs rounded bg-zinc-950 border border-zinc-800"
                    >
                      <option value="">Select employee…</option>
                      {directory.map((d) => (
                        <option key={d.employee_id} value={d.employee_id}>
                          {d.name ?? d.employee_id} ({d.role})
                        </option>
                      ))}
                    </select>
                  ) : (
                    <input
                      value={coverageEmployeeId}
                      onChange={(e) => setCoverageEmployeeId(e.target.value)}
                      placeholder="Employee ID (e.g. EMP-00003)"
                      className="w-full h-9 px-2 text-xs rounded bg-zinc-950 border border-zinc-800"
                    />
                  )}

                  <div className="flex gap-2">
                    <select
                      value={coverageRole}
                      onChange={(e) => setCoverageRole(e.target.value)}
                      className="flex-1 h-9 px-2 text-xs rounded bg-zinc-950 border border-zinc-800"
                    >
                      {ROLE_OPTIONS.map((r) => (
                        <option key={r} value={r}>
                          {r}
                        </option>
                      ))}
                    </select>
                    <input
                      value={coverageSection}
                      onChange={(e) => setCoverageSection(e.target.value)}
                      placeholder="section (e.g. sales)"
                      className="flex-1 h-9 px-2 text-xs rounded bg-zinc-950 border border-zinc-800"
                    />
                  </div>

                  <div className="flex gap-2">
                    <input
                      type="datetime-local"
                      value={coverageStarts}
                      onChange={(e) => setCoverageStarts(e.target.value)}
                      className="flex-1 h-9 px-2 text-xs rounded bg-zinc-950 border border-zinc-800"
                    />
                    <input
                      type="datetime-local"
                      value={coverageEnds}
                      onChange={(e) => setCoverageEnds(e.target.value)}
                      className="flex-1 h-9 px-2 text-xs rounded bg-zinc-950 border border-zinc-800"
                    />
                  </div>

                  <select
                    value={coverageMode}
                    onChange={(e) => setCoverageMode(e.target.value as "draft" | "auto")}
                    className="w-full h-9 px-2 text-xs rounded bg-zinc-950 border border-zinc-800"
                  >
                    <option value="draft">Draft — stage suggestions for review</option>
                    <option value="auto">Auto-execute whitelisted actions</option>
                  </select>

                  <input
                    value={coverageNote}
                    onChange={(e) => setCoverageNote(e.target.value)}
                    placeholder="Note (e.g. out sick)"
                    className="w-full h-9 px-2 text-xs rounded bg-zinc-950 border border-zinc-800"
                  />

                  {coverageError && <div className="text-xs text-[#EE3C25]">{coverageError}</div>}

                  <button
                    onClick={submitCoverage}
                    disabled={coverageSubmitting}
                    className="w-full py-2 rounded-lg bg-[#3FBCC4] text-black text-xs hover:bg-[#5cd0d8] disabled:opacity-50"
                  >
                    {coverageSubmitting ? "Activating…" : "Activate coverage"}
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
