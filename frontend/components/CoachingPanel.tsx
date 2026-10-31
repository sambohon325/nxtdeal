"use client";
import { WorkField } from "./WorkField";

// Coaching (2026-07-19) -- the fourth "NXTDeal Workforce AI" pillar, mounted
// as a tab inside Operations' existing WorkforceBoard.tsx (not a new Top Menu
// item). Three real pieces, each scoped directly with Sam via AskUserQuestion
// before any code was written: Intensity Tiers (bot nudge frequency/tone
// only), AI Performance Reviews (a data-grounded draft, never auto-sent to the
// reviewed employee until a manager explicitly shares it), and AI Career
// Pathing (a real comparative $ signal, never fabricated career advice). Every
// mutating action here is gated server-side (core/coaching_api.py) to
// ADMIN/OPERATIONS or a manager-/executive-tier caller -- this component does
// not attempt to duplicate that gate client-side; it just surfaces whatever
// error the backend returns.

import { useEffect, useState } from "react";
import {
  getIntensityCatalog,
  resolveIntensity,
  setIntensityOverride,
  listIntensityOverrides,
  createPerformanceReview,
  listPerformanceReviews,
  updateReviewNotes,
  finalizeReview,
  shareReview,
  discardReview,
  getCareerPathingBoard,
  type IntensityCatalog,
  type IntensityResolution,
  type IntensityOverride,
  type IntensityScope,
  type IntensityTier,
  type PerformanceReview,
  type CareerPathingBoard,
} from "@/lib/coaching";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

function Card({ theme, children }: { theme: Theme; children: React.ReactNode }) {
  return (
    <div className={tc(theme, "rounded-lg border border-zinc-800 bg-brand-charcoal p-3", "rounded-lg border border-zinc-200 bg-zinc-50 p-3")}>
      {children}
    </div>
  );
}

function Label({ children }: { children: React.ReactNode }) {
  return <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">{children}</div>;
}

function Pill({ children, tone }: { children: React.ReactNode; tone?: string }) {
  return (
    <span
      className="text-[10px] px-2 py-0.5 rounded-full font-brand uppercase tracking-wide"
      style={{ background: tone ? `${tone}22` : "rgba(255,255,255,0.08)", color: tone ?? "#a1a1aa" }}
    >
      {children}
    </span>
  );
}

const INTENSITY_COLOR: Record<string, string> = {
  participant: "#3FBCC4",
  productive: "#71717a",
  aggressive: "#EE3C25",
};

const REVIEW_STATUS_COLOR: Record<string, string> = {
  draft: "#71717a",
  finalized: "#FBCF09",
  shared: "#22c55e",
};

const SIGNAL_COLOR: Record<string, string> = {
  ready_for_more_responsibility: "#22c55e",
  skill_gap: "#EE3C25",
  on_par_with_peers: "#3FBCC4",
  insufficient_peer_data: "#71717a",
};

const SUB_TABS = [
  ["intensity", "Intensity Tiers"],
  ["reviews", "Performance Reviews"],
  ["pathing", "Career Pathing"],
] as const;

export function CoachingPanel({ theme }: { theme: Theme }) {
  const [subTab, setSubTab] = useState<(typeof SUB_TABS)[number][0]>("intensity");
  const [actionError, setActionError] = useState<string | null>(null);

  // --- Intensity ---
  const [catalog, setCatalog] = useState<IntensityCatalog | null>(null);
  const [selfIntensity, setSelfIntensity] = useState<IntensityResolution | null>(null);
  const [overrides, setOverrides] = useState<IntensityOverride[]>([]);
  const [newOverride, setNewOverride] = useState<{ scope: IntensityScope; scope_target: string; intensity: IntensityTier; reason: string }>({
    scope: "individual",
    scope_target: "",
    intensity: "productive",
    reason: "",
  });

  function refreshIntensity() {
    getIntensityCatalog().then(setCatalog).catch(() => setCatalog(null));
    resolveIntensity().then(setSelfIntensity).catch(() => setSelfIntensity(null));
    listIntensityOverrides().then((r) => setOverrides(r.overrides)).catch(() => setOverrides([]));
  }

  // --- Performance Reviews ---
  const [reviews, setReviews] = useState<PerformanceReview[]>([]);
  const [expandedReview, setExpandedReview] = useState<PerformanceReview | null>(null);
  const [newReview, setNewReview] = useState({ target_employee_id: "", period_label: "" });
  const [notesDraft, setNotesDraft] = useState("");

  function refreshReviews() {
    listPerformanceReviews().then((r) => setReviews(r.reviews)).catch(() => setReviews([]));
  }

  // --- Career Pathing ---
  const [pathingBoard, setPathingBoard] = useState<CareerPathingBoard | null>(null);
  const [pathingDept, setPathingDept] = useState("");

  function refreshPathing() {
    getCareerPathingBoard(pathingDept ? { department: pathingDept } : undefined)
      .then(setPathingBoard)
      .catch(() => setPathingBoard(null));
  }

  useEffect(() => {
    if (subTab === "intensity") refreshIntensity();
    if (subTab === "reviews") refreshReviews();
    if (subTab === "pathing") refreshPathing();
  }, [subTab]); // eslint-disable-line react-hooks/exhaustive-deps

  async function act<T>(fn: () => Promise<T>, after: (result: T) => void) {
    setActionError(null);
    try {
      const result = await fn();
      after(result);
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Action failed.");
    }
  }

  async function submitOverride() {
    if (!newOverride.scope_target && newOverride.scope !== "global") {
      setActionError("scope_target is required (e.g. an Employee ID, a department name, or staff/manager/executive).");
      return;
    }
    await act(
      () => setIntensityOverride({ ...newOverride, scope_target: newOverride.scope === "global" ? "*" : newOverride.scope_target }),
      () => {
        setNewOverride({ scope: "individual", scope_target: "", intensity: "productive", reason: "" });
        refreshIntensity();
      }
    );
  }

  async function submitReview() {
    if (!newReview.target_employee_id) {
      setActionError("target_employee_id is required (an Employee ID).");
      return;
    }
    await act(
      () => createPerformanceReview(newReview.target_employee_id, newReview.period_label),
      () => {
        setNewReview({ target_employee_id: "", period_label: "" });
        refreshReviews();
      }
    );
  }

  function openReview(r: PerformanceReview) {
    setExpandedReview(r);
    setNotesDraft(r.manager_notes ?? "");
    setActionError(null);
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-1.5">
        {SUB_TABS.map(([key, label]) => (
          <button
            key={key}
            onClick={() => setSubTab(key)}
            className={`text-[11px] px-2.5 py-1 rounded-full font-brand uppercase tracking-wide transition ${subTab === key ? "bg-zinc-200 text-black font-medium" : "bg-zinc-200/10 text-zinc-400 hover:text-white"}`}
          >
            {label}
          </button>
        ))}
      </div>

      {actionError && <div className="text-xs text-red-400">{actionError}</div>}

      <div className="text-[11px] text-zinc-600">
        Real, gated actions -- mutating Coaching requires ADMIN/OPERATIONS or a manager-/executive-tier employee
        (via that employee&apos;s own real Title). No fabricated career advice or auto-sent reviews anywhere in this pillar.
      </div>

      {subTab === "intensity" && (
        <div className="space-y-4">
          <Card theme={theme}>
            <Label>Your Own Resolved Intensity</Label>
            {selfIntensity ? (
              <div className="flex items-center gap-2">
                <Pill tone={INTENSITY_COLOR[selfIntensity.intensity]}>{selfIntensity.intensity}</Pill>
                <span className="text-[11px] text-zinc-500">resolved from: {selfIntensity.resolved_from}</span>
              </div>
            ) : (
              <div className="text-xs text-zinc-500">Loading…</div>
            )}
          </Card>

          {catalog && (
            <Card theme={theme}>
              <Label>What Each Tier Does</Label>
              <div className="space-y-2">
                {catalog.tiers.map((t) => (
                  <div key={t.key} className="flex items-start gap-2">
                    <Pill tone={INTENSITY_COLOR[t.key]}>{t.label}</Pill>
                    <span className="text-[11px] text-zinc-500">{t.description}</span>
                  </div>
                ))}
              </div>
            </Card>
          )}

          <Card theme={theme}>
            <Label>+ Set an Intensity Override</Label>
            <div className="grid grid-cols-4 gap-2">
              <WorkField label="Scope"><select
                value={newOverride.scope}
                onChange={(e) => setNewOverride({ ...newOverride, scope: e.target.value as IntensityScope, scope_target: "" })}
                className="text-xs bg-transparent border border-zinc-700 rounded px-2 py-1"
              >
                {(catalog?.scopes ?? []).map((s) => (
                  <option key={s.key} value={s.key} className="text-black">
                    {s.label}
                  </option>
                ))}
              </select></WorkField>
              {newOverride.scope !== "global" ? (
                <WorkField label="Scope target"><input
                  placeholder={
                    newOverride.scope === "individual"
                      ? "Employee ID (EMP-...)"
                      : newOverride.scope === "role"
                        ? "staff / manager / executive"
                        : "Department name"
                  }
                  value={newOverride.scope_target}
                  onChange={(e) => setNewOverride({ ...newOverride, scope_target: e.target.value })}
                  className="text-xs bg-transparent border border-zinc-700 rounded px-2 py-1"
                /></WorkField>
              ) : (
                <div className="text-[11px] text-zinc-600 self-center">applies to every employee with no more-specific override</div>
              )}
              <WorkField label="Intensity"><select
                value={newOverride.intensity}
                onChange={(e) => setNewOverride({ ...newOverride, intensity: e.target.value as IntensityTier })}
                className="text-xs bg-transparent border border-zinc-700 rounded px-2 py-1"
              >
                {(catalog?.tiers ?? []).map((t) => (
                  <option key={t.key} value={t.key} className="text-black">
                    {t.label}
                  </option>
                ))}
              </select></WorkField>
              <WorkField label="Reason (optional)"><input
                placeholder="Reason (optional)"
                value={newOverride.reason}
                onChange={(e) => setNewOverride({ ...newOverride, reason: e.target.value })}
                className="text-xs bg-transparent border border-zinc-700 rounded px-2 py-1"
              /></WorkField>
            </div>
            <button onClick={submitOverride} className="mt-2 text-[11px] px-2.5 py-1 rounded-full bg-zinc-200 text-black font-medium">
              Set Override
            </button>
          </Card>

          <Card theme={theme}>
            <Label>Active + Superseded Overrides</Label>
            {overrides.length === 0 && <div className="text-xs text-zinc-500">None set -- every employee defaults to Productive.</div>}
            {overrides.map((o) => (
              <div key={o.id} className="flex items-center justify-between text-xs py-1 border-b border-zinc-800/60 last:border-0">
                <span>
                  {o.scope}={o.scope_target === "*" ? "(global default)" : o.scope_target}
                  {o.reason && <span className="text-zinc-600"> -- {o.reason}</span>}
                </span>
                <div className="flex items-center gap-2">
                  <Pill tone={INTENSITY_COLOR[o.intensity]}>{o.intensity}</Pill>
                  <Pill tone={o.active ? "#22c55e" : "#71717a"}>{o.active ? "active" : "superseded"}</Pill>
                </div>
              </div>
            ))}
          </Card>
        </div>
      )}

      {subTab === "reviews" && (
        <div className="space-y-4">
          {expandedReview ? (
            <Card theme={theme}>
              <button onClick={() => setExpandedReview(null)} className="text-[11px] text-zinc-500 hover:text-white mb-2">
                ← Back to list
              </button>
              <div className="flex items-center justify-between mb-2">
                <div className="text-sm font-medium">
                  {expandedReview.employee_name} -- {expandedReview.period_label || "(no period label)"}
                </div>
                <Pill tone={REVIEW_STATUS_COLOR[expandedReview.status]}>{expandedReview.status}</Pill>
              </div>

              <div className="text-[11px] font-brand uppercase tracking-wide text-zinc-500 mb-1">Factual Summary (real numbers, no AI judgment language)</div>
              <div className="space-y-1 mb-3">
                {expandedReview.factual_summary.map((s, i) => (
                  <div key={i} className="text-xs text-zinc-300">
                    · {s}
                  </div>
                ))}
              </div>


              <WorkField label="Manager Notes (human-typed, never generated)"><textarea
                value={notesDraft}
                onChange={(e) => setNotesDraft(e.target.value)}
                disabled={expandedReview.status !== "draft"}
                rows={3}
                className="w-full text-xs bg-transparent border border-zinc-700 rounded px-2 py-1 mb-2 disabled:opacity-50"
              /></WorkField>

              <div className="flex items-center gap-2">
                {expandedReview.status === "draft" && (
                  <>
                    <button
                      onClick={() =>
                        act(
                          () => updateReviewNotes(expandedReview.id, notesDraft),
                          (saved) => {
                            refreshReviews();
                            setExpandedReview(saved);
                          }
                        )
                      }
                      className="text-[11px] px-2.5 py-1 rounded-full bg-zinc-200/10 text-zinc-400 hover:text-white"
                    >
                      Save Notes
                    </button>
                    <button
                      onClick={() =>
                        act(
                          async () => {
                            await updateReviewNotes(expandedReview.id, notesDraft);
                            return finalizeReview(expandedReview.id);
                          },
                          (saved) => {
                            refreshReviews();
                            setExpandedReview(saved);
                          }
                        )
                      }
                      className="text-[11px] px-2.5 py-1 rounded-full bg-zinc-200 text-black font-medium"
                    >
                      Finalize
                    </button>
                    <button
                      onClick={() =>
                        act(
                          () => discardReview(expandedReview.id),
                          () => {
                            refreshReviews();
                            setExpandedReview(null);
                          }
                        )
                      }
                      className="text-[11px] px-2.5 py-1 rounded-full bg-zinc-200/10 text-red-400 hover:text-red-300"
                    >
                      Discard Draft
                    </button>
                  </>
                )}
                {expandedReview.status === "finalized" && (
                  <button
                    onClick={() =>
                      act(
                        () => shareReview(expandedReview.id),
                        (saved) => {
                          refreshReviews();
                          setExpandedReview(saved);
                        }
                      )
                    }
                    className="text-[11px] px-2.5 py-1 rounded-full bg-zinc-200 text-black font-medium"
                  >
                    Share With Employee
                  </button>
                )}
                {expandedReview.status === "shared" && (
                  <div className="text-[11px] text-zinc-500">
                    Shared by {expandedReview.shared_by} on {expandedReview.shared_at?.slice(0, 10)} -- now visible to {expandedReview.employee_name}.
                  </div>
                )}
              </div>
            </Card>
          ) : (
            <>
              <Card theme={theme}>
                <Label>+ Draft a Performance Review</Label>
                <div className="grid grid-cols-2 gap-2">
                  <WorkField label="Employee ID (EMP-...)"><input
                    placeholder="Employee ID (EMP-...)"
                    value={newReview.target_employee_id}
                    onChange={(e) => setNewReview({ ...newReview, target_employee_id: e.target.value })}
                    className="text-xs bg-transparent border border-zinc-700 rounded px-2 py-1"
                  /></WorkField>
                  <WorkField label="Period label"><input
                    placeholder="Period label (e.g. Q3 2026)"
                    value={newReview.period_label}
                    onChange={(e) => setNewReview({ ...newReview, period_label: e.target.value })}
                    className="text-xs bg-transparent border border-zinc-700 rounded px-2 py-1"
                  /></WorkField>
                </div>
                <button onClick={submitReview} className="mt-2 text-[11px] px-2.5 py-1 rounded-full bg-zinc-200 text-black font-medium">
                  Draft Review
                </button>
              </Card>

              <div className="space-y-1">
                {reviews.length === 0 && <div className="text-xs text-zinc-500">No reviews yet.</div>}
                {reviews.map((r) => (
                  <button
                    key={r.id}
                    onClick={() => openReview(r)}
                    className={tc(
                      theme,
                      "w-full flex items-center justify-between text-left rounded-lg border border-zinc-800 bg-brand-charcoal p-2 hover:border-zinc-600",
                      "w-full flex items-center justify-between text-left rounded-lg border border-zinc-200 bg-zinc-50 p-2 hover:border-zinc-400"
                    )}
                  >
                    <div className="text-xs">
                      {r.employee_name} -- {r.period_label || "(no period label)"}
                      <div className="text-zinc-500">{r.created_at.slice(0, 10)}</div>
                    </div>
                    <Pill tone={REVIEW_STATUS_COLOR[r.status]}>{r.status}</Pill>
                  </button>
                ))}
              </div>
            </>
          )}
        </div>
      )}

      {subTab === "pathing" && (
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <WorkField label="Filter by department (optional)"><input
              placeholder="Filter by department (optional)"
              value={pathingDept}
              onChange={(e) => setPathingDept(e.target.value)}
              onBlur={refreshPathing}
              className="text-xs bg-transparent border border-zinc-700 rounded px-2 py-1"
            /></WorkField>
            <button onClick={refreshPathing} className="text-[11px] px-2.5 py-1 rounded-full bg-zinc-200/10 text-zinc-400 hover:text-white">
              ↻ Refresh
            </button>
          </div>

          {pathingBoard && (
            <div className="text-[11px] text-zinc-500">
              {pathingBoard.count} employee(s) --{" "}
              {Object.entries(pathingBoard.by_signal)
                .map(([s, c]) => `${s}: ${c}`)
                .join(" · ")}
            </div>
          )}

          <div className="space-y-1">
            {(pathingBoard?.employees ?? []).map((e) => (
              <Card key={e.employee_id} theme={theme}>
                <div className="flex items-center justify-between mb-1">
                  <div className="text-sm font-medium">
                    {e.name} -- {e.department} ({e.tier})
                  </div>
                  <Pill tone={SIGNAL_COLOR[e.signal]}>{e.signal.replace(/_/g, " ")}</Pill>
                </div>
                <div className="text-xs text-zinc-400">{e.finding}</div>
              </Card>
            ))}
            {pathingBoard && pathingBoard.employees.length === 0 && <div className="text-xs text-zinc-500">No employees found for this filter.</div>}
          </div>

          <div className="text-[10px] text-zinc-600">
            A real, comparative $ signal only (core/employee_value.py) -- never a fabricated skills assessment or a guaranteed promotion
            recommendation. No tenure data exists anywhere in this codebase to factor in.
          </div>
        </div>
      )}
    </div>
  );
}
