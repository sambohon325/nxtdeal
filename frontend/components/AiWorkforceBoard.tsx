"use client";
import { WorkButton } from "./WorkspaceUi";

// AiWorkforceBoard — the NXTDeal AI Workforce dashboard (Connect slice 6, 2026-07-24).
// Sam's NXTDeal Workforce spec: a customer-facing AI agent per role (Receptionist, BDC,
// Sales, Service, Marketing, Finance, Collections, Operator) that handles inbound touches
// across phone/SMS/email/chat and works an outbound queue. This board lists the eight
// workers with each one's activation status/mode, how many interactions it has handled,
// and how many actions it has executed vs. drafted. ADMIN can activate a worker in draft,
// assisted, or autonomous mode (autonomous is additionally gated server-side by the same
// AI kill switch plus the default-deny ai.worker.autonomous capability — the workforce
// inherits that safety boundary, it does not relax it) or deactivate it, and can run a
// worker's outbound queue. Selecting a worker reveals its safe actions and recent actions.
// Reads/acts through lib/aiWorker.ts; same styling vocabulary (RIBBON palette, theme-aware
// tc() classes) as FleetBoard.tsx.
//
// NOTE: distinct from Operations' WorkforceBoard.tsx (HR: directory / scheduling / time-off).
// This is the *AI* workforce — customer-facing agents — under Administration.
//
// Honesty posture mirrors the backend: nothing financial or contractual ever auto-executes;
// only informational safe actions can run autonomously, and everything else drafts for a
// human. A worker with no handled interactions yet says exactly that rather than inventing work.

import { PRODUCT_ACCENT_COLORS } from "@/lib/productTheme";
import { useEffect, useState } from "react";
import { getSession } from "@/lib/auth";
import {
  fetchWorkforce,
  fetchWorkerDetail,
  activateWorker,
  deactivateWorker,
  runWorkerQueue,
  type AiWorker,
  type WorkforceSummary,
  type WorkerDetail,
  type WorkerMode,
  type RunResult,
} from "@/lib/aiWorker";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const RIBBON = PRODUCT_ACCENT_COLORS;

const MODES: WorkerMode[] = ["draft", "assisted", "autonomous"];

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

// Turn a stable action_key ("book_appointment") into a readable label.
function prettyAction(key: string | null | undefined): string {
  if (!key) return "—";
  return key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function StatusBadge({ theme, worker }: { theme: Theme; worker: AiWorker }) {
  const active = worker.status === "active";
  const auto = active && worker.mode === "autonomous";
  const bg = !active ? tc(theme, "#374151", "#e5e7eb") : auto ? "#EE3C25" : "#2B68AB";
  const fg = !active ? tc(theme, "#d1d5db", "#4b5563") : "#ffffff";
  const label = !active
    ? "Inactive"
    : `Active · ${worker.mode.charAt(0).toUpperCase()}${worker.mode.slice(1)}`;
  return (
    <span
      className="rounded-full px-2 py-0.5 text-xs font-semibold uppercase tracking-wide"
      style={{ backgroundColor: bg, color: fg }}
    >
      {label}
    </span>
  );
}

// One KPI tile — codebase-standard markup (a font-semibold value over an uppercase
// tracking-wide label) so the universal <BoardCaptureButton> can scrape it.
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

export function AiWorkforceBoard({ theme, hideHeading=false }: { theme: Theme; hideHeading?:boolean }) {
  const [workers, setWorkers] = useState<AiWorker[]>([]);
  const [summary, setSummary] = useState<WorkforceSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<WorkerDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const [busy, setBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const [running, setRunning] = useState(false);
  const [lastRun, setLastRun] = useState<RunResult | null>(null);
  const [runError, setRunError] = useState<string | null>(null);

  const isAdmin = getSession()?.role === "ADMIN";

  async function loadWorkforce() {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchWorkforce();
      setWorkers(data.workforce);
      setSummary(data.summary);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to load the AI workforce.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadWorkforce();
  }, []);

  async function loadDetail(role: string) {
    setSelected(role);
    setDetailLoading(true);
    setLastRun(null);
    setRunError(null);
    try {
      setDetail(await fetchWorkerDetail(role));
    } catch (e) {
      setDetail(null);
      setActionError(e instanceof Error ? e.message : "Unable to load this worker.");
    } finally {
      setDetailLoading(false);
    }
  }

  async function doRun(role: string) {
    setRunning(true);
    setRunError(null);
    try {
      const run = await runWorkerQueue(role);
      await loadWorkforce(); // refresh tallies
      if (selected === role) await loadDetail(role); // refresh recent_actions (clears lastRun)
      setLastRun(run); // set after refresh so the result stays visible
    } catch (e) {
      setRunError(e instanceof Error ? e.message : "Unable to run this worker's queue.");
    } finally {
      setRunning(false);
    }
  }

  async function doActivate(role: string, mode: WorkerMode) {
    setBusy(role);
    setActionError(null);
    try {
      await activateWorker(role, mode);
      await loadWorkforce();
      if (selected === role) await loadDetail(role);
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Activation failed.");
    } finally {
      setBusy(null);
    }
  }

  async function doDeactivate(role: string) {
    setBusy(role);
    setActionError(null);
    try {
      await deactivateWorker(role);
      await loadWorkforce();
      if (selected === role) await loadDetail(role);
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Deactivation failed.");
    } finally {
      setBusy(null);
    }
  }

  const cardBase = tc(theme, "border-white/10 bg-white/[0.03]", "border-black/10 bg-white");
  const subtle = tc(theme, "text-gray-400", "text-gray-500");
  const heading = tc(theme, "text-white", "text-gray-900");

  return (
    <div className="space-y-5">
      <div>
        {!hideHeading && <h2 className={`text-xl font-semibold ${heading}`}>Workforce Automation</h2>}
        <p className={`mt-1 text-sm ${subtle}`}>
          A customer-facing AI worker for every role — the communications team plus the Digital
          Retail roles (Product Specialist, Trade Manager, Negotiator, Delivery Coordinator,
          Ownership Concierge). Each handles inbound touches across phone, SMS, email and chat
          and works an outbound queue.
          {isAdmin
            ? " Activate a worker in draft (it prepares every touch for a human), assisted, or autonomous mode (gated by the AI kill switch and the same default-deny capability the bot fleet uses), or deactivate it, and run its queue."
            : " Activation is managed by an administrator."}
        </p>
      </div>

      {/* Honest disclosure — what an active worker can and cannot do. */}
      <div
        className={`rounded-lg border p-3 text-xs ${tc(theme, "border-white/10 bg-white/[0.02] text-gray-300", "border-black/10 bg-black/[0.02] text-gray-600")}`}
        style={{ borderLeft: `3px solid ${RIBBON[1]}` }}
      >
        Nothing financial or contractual ever auto-executes. Only informational safe actions
        (routing a call, sending a confirmation, booking against an existing calendar slot) can
        run in autonomous mode — everything else drafts for a human to send. Autonomous mode also
        requires the AI kill switch on and the default-deny ai.worker.autonomous grant; without
        both, an active worker still only drafts.
      </div>

      {loading ? (
        <div className={`text-sm ${subtle}`}>Loading the AI workforce…</div>
      ) : error ? (
        <div className="rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-400">
          {error}
        </div>
      ) : (
        <>
          {summary && (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
              <Tile theme={theme} value={summary.total_workers} label="AI Workers" accent={RIBBON[0]} />
              <Tile theme={theme} value={summary.active_workers} label="Active" accent={RIBBON[1]} />
              <Tile theme={theme} value={summary.autonomous_workers} label="Autonomous" accent={RIBBON[3]} />
              <Tile theme={theme} value={summary.total_interactions} label="Interactions" accent={RIBBON[2]} />
              <Tile theme={theme} value={summary.total_actions_executed} label="Actions Executed" accent={RIBBON[1]} />
              <Tile theme={theme} value={summary.total_actions_drafted} label="Actions Drafted" accent={RIBBON[0]} />
            </div>
          )}

          {actionError && (
            <div className="rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-400">
              {actionError}
            </div>
          )}

          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
            {workers.map((worker, i) => {
              const isSel = selected === worker.role;
              const acting = busy === worker.role;
              return (
                <div
                  key={worker.id || worker.role}
                  className={`rounded-lg border p-4 transition ${cardBase} ${isSel ? "ring-2" : ""}`}
                  style={isSel ? { boxShadow: `0 0 0 2px ${RIBBON[i % RIBBON.length]}` } : undefined}
                >
                  <div className="flex items-start justify-between gap-2">
                    <WorkButton
                      type="button"
                      onClick={() => loadDetail(worker.role)}
                      className={`text-left text-sm font-semibold ${heading} hover:underline`}
                    >
                      {worker.display_name}
                    </WorkButton>
                    <StatusBadge theme={theme} worker={worker} />
                  </div>

                  <div className={`mt-2 text-xs ${subtle}`}>{worker.channels.join(" · ")}</div>

                  <div className={`mt-3 flex gap-4 text-xs ${subtle}`}>
                    <span>
                      <span className={`font-semibold ${heading}`}>{worker.interactions_handled}</span> handled
                    </span>
                    <span>
                      <span className={`font-semibold ${heading}`}>{worker.actions_executed}</span> executed
                    </span>
                    <span>
                      <span className={`font-semibold ${heading}`}>{worker.actions_drafted}</span> drafted
                    </span>
                  </div>

                  {worker.status === "active" && worker.activated_at && (
                    <div className={`mt-2 text-xs ${subtle}`}>
                      Activated {fmt(worker.activated_at)}
                      {worker.activated_by ? ` by ${worker.activated_by}` : ""}
                    </div>
                  )}

                  {isAdmin && (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {MODES.map((mode) =>
                        worker.status !== "active" || worker.mode !== mode ? (
                          <WorkButton
                            key={mode}
                            type="button"
                            disabled={acting}
                            onClick={() => doActivate(worker.role, mode)}
                            className="rounded-md px-2.5 py-1 text-xs font-semibold text-white disabled:opacity-50"
                            style={{ backgroundColor: mode === "autonomous" ? RIBBON[3] : RIBBON[0] }}
                          >
                            {acting ? "…" : `${mode.charAt(0).toUpperCase()}${mode.slice(1)}`}
                          </WorkButton>
                        ) : null
                      )}
                      {worker.status === "active" && (
                        <>
                          <WorkButton
                            type="button"
                            disabled={running}
                            onClick={() => doRun(worker.role)}
                            className="rounded-md px-2.5 py-1 text-xs font-semibold text-white disabled:opacity-50"
                            style={{ backgroundColor: RIBBON[1] }}
                          >
                            {running ? "…" : "Run queue"}
                          </WorkButton>
                          <WorkButton
                            type="button"
                            disabled={acting}
                            onClick={() => doDeactivate(worker.role)}
                            className={`rounded-md border px-2.5 py-1 text-xs font-semibold disabled:opacity-50 ${tc(theme, "border-white/20 text-gray-200", "border-black/20 text-gray-700")}`}
                          >
                            {acting ? "…" : "Deactivate"}
                          </WorkButton>
                        </>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {selected && (
            <div className={`rounded-lg border p-4 ${cardBase}`}>
              {detailLoading ? (
                <div className={`text-sm ${subtle}`}>Loading worker…</div>
              ) : !detail ? (
                <div className={`text-sm ${subtle}`}>No detail available for this worker yet.</div>
              ) : (
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <h3 className={`text-sm font-semibold ${heading}`}>
                      {detail.display_name} — recent actions
                    </h3>
                    <span className={`text-xs ${subtle}`}>
                      {detail.interactions_handled} handled · {detail.actions_executed} executed ·{" "}
                      {detail.actions_drafted} drafted
                    </span>
                  </div>

                  {/* Last run result (stays visible after the refresh). */}
                  {lastRun && (
                    <div
                      className={`rounded-md border p-3 ${tc(theme, "border-white/10 bg-white/[0.02]", "border-black/10 bg-black/[0.02]")}`}
                      style={{ borderLeft: `3px solid ${RIBBON[2]}` }}
                    >
                      {lastRun.available === false ? (
                        <div className={`text-xs ${subtle}`}>{lastRun.note}</div>
                      ) : (
                        <>
                          <div className={`text-xs font-semibold ${heading}`}>
                            Queue run — {lastRun.mode} mode · {lastRun.status}
                          </div>
                          {lastRun.actions && lastRun.actions.length > 0 ? (
                            <div className="mt-2 space-y-1.5">
                              {lastRun.actions.map((a, ai) => (
                                <div
                                  key={ai}
                                  className={`flex items-center justify-between gap-2 text-xs ${tc(theme, "text-gray-300", "text-gray-600")}`}
                                >
                                  <span>{prettyAction(a.action_key)}</span>
                                  <span
                                    className="rounded px-1.5 py-0.5 text-xs font-semibold uppercase tracking-wide"
                                    style={{
                                      backgroundColor: a.status === "executed" ? RIBBON[1] : tc(theme, "#374151", "#e5e7eb"),
                                      color: a.status === "executed" ? "#ffffff" : tc(theme, "#d1d5db", "#4b5563"),
                                    }}
                                  >
                                    {a.status}
                                  </span>
                                </div>
                              ))}
                            </div>
                          ) : (
                            <div className={`mt-1 text-xs ${subtle}`}>
                              Nothing in the queue right now — the worker had no outbound touches to make.
                            </div>
                          )}
                        </>
                      )}
                    </div>
                  )}
                  {runError && <div className="text-xs text-red-400">{runError}</div>}

                  {/* Safe actions this worker can execute autonomously (informational only). */}
                  <div>
                    <h4 className={`mb-2 text-xs font-semibold uppercase tracking-wide ${subtle}`}>
                      Safe actions (may run autonomously)
                    </h4>
                    {detail.safe_actions && detail.safe_actions.length > 0 ? (
                      <div className="flex flex-wrap gap-1.5">
                        {detail.safe_actions.map((a) => (
                          <span
                            key={a}
                            className={`rounded px-1.5 py-0.5 text-xs font-medium ${tc(theme, "bg-white/10 text-gray-100", "bg-black/[0.06] text-gray-800")}`}
                          >
                            {prettyAction(a)}
                          </span>
                        ))}
                      </div>
                    ) : (
                      <div className={`text-sm ${subtle}`}>
                        This worker has no autonomous safe actions — every touch drafts for a human.
                      </div>
                    )}
                  </div>

                  {/* Recent recorded actions. */}
                  {detail.recent_actions && detail.recent_actions.length > 0 ? (
                    <div>
                      <h4 className={`mb-2 text-xs font-semibold uppercase tracking-wide ${subtle}`}>
                        Recent actions
                      </h4>
                      <div className="space-y-1">
                        {detail.recent_actions.map((a, idx) => (
                          <div
                            key={idx}
                            className={`flex items-center justify-between gap-3 text-xs ${tc(theme, "text-gray-300", "text-gray-600")}`}
                          >
                            <span className={`font-medium ${heading}`}>
                              {prettyAction(a.action_key)}
                              {a.channel ? <span className={subtle}> · {a.channel}</span> : null}
                            </span>
                            <span className={subtle}>
                              <span
                                className="mr-2 rounded px-1.5 py-0.5 text-xs font-semibold uppercase tracking-wide"
                                style={{
                                  backgroundColor: a.status === "executed" ? RIBBON[1] : tc(theme, "#374151", "#e5e7eb"),
                                  color: a.status === "executed" ? "#ffffff" : tc(theme, "#d1d5db", "#4b5563"),
                                }}
                              >
                                {a.status}
                              </span>
                              {fmt(a.recorded_at)}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : (
                    <div className={`text-sm ${subtle}`}>
                      No actions recorded yet — this worker hasn&apos;t handled an interaction or run
                      its queue.
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
