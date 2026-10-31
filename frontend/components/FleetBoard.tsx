"use client";
import { WorkButton } from "./WorkspaceUi";

// FleetBoard — the agentic-bot FLEET dashboard (Pillar 4 slice 2, 2026-07-23).
// Sam's architectural pillar #4: "a fleet of team agents that each record their team's
// workflows and can be admin-activated." This board lists the nine NXTDeal team agents
// (one per section) with each agent's activation status/mode, how many real workflow
// steps it has observed, and how many recurring workflows it has recognized so far.
// ADMIN can activate an agent in draft or auto mode (auto is additionally gated
// server-side by the same default-deny bot.coverage.auto_mode capability the existing Bot
// Coverage uses — the fleet inherits that safety boundary, it does not relax it) or
// deactivate it. Selecting an agent reveals that team's recognized workflows and recent
// observed steps. Reads/acts through lib/botFleet.ts; same styling vocabulary
// (RIBBON palette, theme-aware tc() classes) as ConsultingEngineBoard.tsx.
//
// Honesty posture mirrors the backend: recognized workflows are REAL recurring action
// sequences actually observed on the team (each seen at least twice), never fabricated —
// and an agent with no observed steps yet says exactly that rather than inventing work.

import { PRODUCT_ACCENT_COLORS } from "@/lib/productTheme";
import { useEffect, useState } from "react";
import { getSession } from "@/lib/auth";
import {
  fetchFleet,
  fetchTeamWorkflows,
  activateAgent,
  deactivateAgent,
  runWorkflow,
  type TeamAgent,
  type FleetSummary,
  type TeamWorkflows,
  type AgentMode,
  type WorkflowRun,
} from "@/lib/botFleet";
import { SharedKnowledgePanel } from "@/components/SharedKnowledgePanel";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const RIBBON = PRODUCT_ACCENT_COLORS;

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

// Turn a stable action_key ("create_deal") into a readable label when the backend didn't
// supply an explicit step_label.
function prettyAction(key: string | null | undefined): string {
  if (!key) return "—";
  return key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function StatusBadge({ theme, agent }: { theme: Theme; agent: TeamAgent }) {
  const active = agent.status === "active";
  const auto = active && agent.mode === "auto";
  const bg = !active ? tc(theme, "#374151", "#e5e7eb") : auto ? "#EE3C25" : "#2B68AB";
  const fg = !active ? tc(theme, "#d1d5db", "#4b5563") : "#ffffff";
  const label = !active ? "Inactive" : auto ? "Active · Auto" : "Active · Draft";
  return (
    <span
      className="rounded-full px-2 py-0.5 text-xs font-semibold uppercase tracking-wide"
      style={{ backgroundColor: bg, color: fg }}
    >
      {label}
    </span>
  );
}

// One KPI tile — deliberately the codebase-standard markup (a font-semibold value over an
// uppercase tracking-wide label) so the universal <BoardCaptureButton> can scrape it.
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

export function FleetBoard({ theme, hideHeading=false }: { theme: Theme; hideHeading?:boolean }) {
  const [agents, setAgents] = useState<TeamAgent[]>([]);
  const [summary, setSummary] = useState<FleetSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [selected, setSelected] = useState<string | null>(null);
  const [workflows, setWorkflows] = useState<TeamWorkflows | null>(null);
  const [workflowLoading, setWorkflowLoading] = useState(false);

  const [busy, setBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const [running, setRunning] = useState(false);
  const [lastRun, setLastRun] = useState<WorkflowRun | null>(null);
  const [runError, setRunError] = useState<string | null>(null);

  const isAdmin = getSession()?.role === "ADMIN";

  async function loadFleet() {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchFleet();
      setAgents(data.fleet);
      setSummary(data.summary);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to load the agent fleet.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadFleet();
  }, []);

  async function loadWorkflows(section: string) {
    setSelected(section);
    setWorkflowLoading(true);
    setLastRun(null);
    setRunError(null);
    try {
      setWorkflows(await fetchTeamWorkflows(section));
    } catch (e) {
      setWorkflows({
        available: false,
        note: e instanceof Error ? e.message : "Unable to load this team's workflows.",
      });
    } finally {
      setWorkflowLoading(false);
    }
  }

  async function doRun(section: string) {
    setRunning(true);
    setRunError(null);
    try {
      const run = await runWorkflow(section);
      await loadWorkflows(section); // refresh recent_runs + auto_execute_ready (clears lastRun)
      setLastRun(run); // set after refresh so the result stays visible
    } catch (e) {
      setRunError(e instanceof Error ? e.message : "Unable to run this workflow.");
    } finally {
      setRunning(false);
    }
  }

  async function doActivate(section: string, mode: AgentMode) {
    setBusy(section);
    setActionError(null);
    try {
      await activateAgent(section, mode);
      await loadFleet();
      if (selected === section) await loadWorkflows(section);
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Activation failed.");
    } finally {
      setBusy(null);
    }
  }

  async function doDeactivate(section: string) {
    setBusy(section);
    setActionError(null);
    try {
      await deactivateAgent(section);
      await loadFleet();
      if (selected === section) await loadWorkflows(section);
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
        {!hideHeading && <h2 className={`text-xl font-semibold ${heading}`}>AI Agents</h2>}
        <p className={`mt-1 text-sm ${subtle}`}>
          Nine team agents — one per NXTDeal section. Each agent records its team&apos;s real,
          observed workflow steps and surfaces the recurring workflows it has actually seen.
          {isAdmin
            ? " Activate an agent in draft mode (it watches and drafts) or auto mode (gated by the same default-deny capability as Bot Coverage), or deactivate it."
            : " Activation is managed by an administrator."}
        </p>
      </div>

      {/* Honest disclosure — what an active agent can and cannot do in this slice. */}
      <div
        className={`rounded-lg border p-3 text-xs ${tc(theme, "border-white/10 bg-white/[0.02] text-gray-300", "border-black/10 bg-black/[0.02] text-gray-600")}`}
        style={{ borderLeft: `3px solid ${RIBBON[1]}` }}
      >
        Recognized workflows are real recurring action sequences observed on a team (each seen
        at least twice) — never fabricated, and only shown once a pattern has genuinely repeated.
        Activating an agent lets it observe and draft; it adds no unattended action surface —
        any future auto-execution still routes through the existing safe-action whitelist and
        permission grants.
      </div>

      {loading ? (
        <div className={`text-sm ${subtle}`}>Loading the agent fleet…</div>
      ) : error ? (
        <div className="rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-400">
          {error}
        </div>
      ) : (
        <>
          {summary && (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
              <Tile theme={theme} value={summary.total_agents} label="Team Agents" accent={RIBBON[0]} />
              <Tile theme={theme} value={summary.active_agents} label="Active" accent={RIBBON[1]} />
              <Tile theme={theme} value={summary.auto_agents} label="In Auto Mode" accent={RIBBON[3]} />
              <Tile theme={theme} value={summary.total_workflow_steps} label="Steps Observed" accent={RIBBON[2]} />
              <Tile theme={theme} value={summary.total_recognized_workflows} label="Workflows Recognized" accent={RIBBON[0]} />
            </div>
          )}

          {actionError && (
            <div className="rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-400">
              {actionError}
            </div>
          )}

          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
            {agents.map((agent, i) => {
              const isSel = selected === agent.section;
              const acting = busy === agent.section;
              return (
                <div
                  key={agent.id || agent.section}
                  className={`rounded-lg border p-4 transition ${cardBase} ${isSel ? "ring-2" : ""}`}
                  style={isSel ? { boxShadow: `0 0 0 2px ${RIBBON[i % RIBBON.length]}` } : undefined}
                >
                  <div className="flex items-start justify-between gap-2">
                    <WorkButton
                      type="button"
                      onClick={() => loadWorkflows(agent.section)}
                      className={`text-left text-sm font-semibold ${heading} hover:underline`}
                    >
                      {agent.display_name}
                    </WorkButton>
                    <StatusBadge theme={theme} agent={agent} />
                  </div>

                  <div className={`mt-3 flex gap-4 text-xs ${subtle}`}>
                    <span>
                      <span className={`font-semibold ${heading}`}>{agent.workflow_step_count}</span> steps
                    </span>
                    <span>
                      <span className={`font-semibold ${heading}`}>{agent.recognized_workflow_count}</span> workflows
                    </span>
                  </div>

                  {agent.status === "active" && agent.activated_at && (
                    <div className={`mt-2 text-xs ${subtle}`}>
                      Activated {fmt(agent.activated_at)}
                      {agent.activated_by ? ` by ${agent.activated_by}` : ""}
                    </div>
                  )}

                  {isAdmin && (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {agent.status !== "active" || agent.mode !== "draft" ? (
                        <WorkButton
                          type="button"
                          disabled={acting}
                          onClick={() => doActivate(agent.section, "draft")}
                          className="rounded-md px-2.5 py-1 text-xs font-semibold text-white disabled:opacity-50"
                          style={{ backgroundColor: RIBBON[0] }}
                        >
                          {acting ? "…" : "Draft mode"}
                        </WorkButton>
                      ) : null}
                      {agent.status !== "active" || agent.mode !== "auto" ? (
                        <WorkButton
                          type="button"
                          disabled={acting}
                          onClick={() => doActivate(agent.section, "auto")}
                          className="rounded-md px-2.5 py-1 text-xs font-semibold text-white disabled:opacity-50"
                          style={{ backgroundColor: RIBBON[3] }}
                        >
                          {acting ? "…" : "Auto mode"}
                        </WorkButton>
                      ) : null}
                      {agent.status === "active" && (
                        <WorkButton
                          type="button"
                          disabled={acting}
                          onClick={() => doDeactivate(agent.section)}
                          className={`rounded-md border px-2.5 py-1 text-xs font-semibold disabled:opacity-50 ${tc(theme, "border-white/20 text-gray-200", "border-black/20 text-gray-700")}`}
                        >
                          {acting ? "…" : "Deactivate"}
                        </WorkButton>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {selected && (
            <div className={`rounded-lg border p-4 ${cardBase}`}>
              {workflowLoading ? (
                <div className={`text-sm ${subtle}`}>Loading workflows…</div>
              ) : !workflows || !workflows.available ? (
                <div className={`text-sm ${subtle}`}>
                  {workflows?.note || "No workflow data available for this team yet."}
                </div>
              ) : (
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <h3 className={`text-sm font-semibold ${heading}`}>
                      {workflows.display_name} — recognized workflows
                    </h3>
                    <span className={`text-xs ${subtle}`}>
                      {workflows.step_count} steps · {workflows.distinct_actors?.length ?? 0} people
                    </span>
                  </div>

                  {/* Slice 4e: run the recognized workflow. ADMIN-only. Steps only
                      auto-execute when the agent is armed AND on the safe whitelist
                      (empty by default) — otherwise every step drafts for a human. */}
                  {isAdmin &&
                    workflows.recognized_workflows &&
                    workflows.recognized_workflows.length > 0 && (
                      <div
                        className={`rounded-md border p-3 ${tc(theme, "border-white/10 bg-white/[0.02]", "border-black/10 bg-black/[0.02]")}`}
                        style={{ borderLeft: `3px solid ${RIBBON[2]}` }}
                      >
                        <div className="flex items-center justify-between gap-3">
                          <div className={`text-xs ${subtle}`}>
                            {workflows.auto_execute_ready
                              ? "Armed — active in auto mode with fleet auto-execute granted. Whitelisted safe steps will execute; everything else drafts."
                              : "Draft only — the agent will prepare each step as a suggestion for a human (arm it via auto mode + the bot.fleet.auto_execute grant to let whitelisted safe steps run)."}
                          </div>
                          <WorkButton
                            type="button"
                            disabled={running}
                            onClick={() => selected && doRun(selected)}
                            className="shrink-0 rounded-md px-2.5 py-1 text-xs font-semibold text-white disabled:opacity-50"
                            style={{ backgroundColor: RIBBON[0] }}
                          >
                            {running ? "Running…" : "Run recognized workflow"}
                          </WorkButton>
                        </div>

                        {runError && (
                          <div className="mt-2 text-xs text-red-400">{runError}</div>
                        )}

                        {lastRun && (
                          <div className="mt-3 space-y-1.5">
                            <div className={`text-xs font-semibold ${heading}`}>
                              Run — {lastRun.mode === "auto" ? "auto" : "draft"} mode ·{" "}
                              {lastRun.executed_count} executed · {lastRun.drafted_count} drafted
                            </div>
                            {lastRun.steps.map((s, si) => (
                              <div
                                key={si}
                                className={`flex items-center justify-between gap-2 text-xs ${tc(theme, "text-gray-300", "text-gray-600")}`}
                              >
                                <span>{prettyAction(s.action_key)}</span>
                                <span
                                  className="rounded px-1.5 py-0.5 text-xs font-semibold uppercase tracking-wide"
                                  style={{
                                    backgroundColor: s.status === "executed" ? RIBBON[1] : tc(theme, "#374151", "#e5e7eb"),
                                    color: s.status === "executed" ? "#ffffff" : tc(theme, "#d1d5db", "#4b5563"),
                                  }}
                                >
                                  {s.status}
                                </span>
                              </div>
                            ))}
                            {lastRun.note && (
                              <p className={`pt-1 text-xs ${subtle}`}>{lastRun.note}</p>
                            )}
                          </div>
                        )}
                      </div>
                    )}

                  {workflows.recognized_workflows && workflows.recognized_workflows.length > 0 ? (
                    <div className="space-y-2">
                      {workflows.recognized_workflows.map((wf, idx) => (
                        <div
                          key={idx}
                          className={`rounded-md border p-3 ${tc(theme, "border-white/10 bg-white/[0.02]", "border-black/10 bg-black/[0.02]")}`}
                        >
                          <div className="flex flex-wrap items-center gap-1.5">
                            {wf.steps.map((step, si) => (
                              <span key={si} className="flex items-center gap-1.5">
                                <span
                                  className={`rounded px-1.5 py-0.5 text-xs font-medium ${tc(theme, "bg-white/10 text-gray-100", "bg-black/[0.06] text-gray-800")}`}
                                >
                                  {prettyAction(step)}
                                </span>
                                {si < wf.steps.length - 1 && <span className={subtle}>→</span>}
                              </span>
                            ))}
                          </div>
                          <div className={`mt-1.5 text-xs ${subtle}`}>
                            Seen {wf.occurrences} times · {wf.length} steps
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className={`text-sm ${subtle}`}>
                      No recurring workflow recognized yet — this agent needs to observe a step
                      sequence repeat before it will surface one. {workflows.step_count === 0
                        ? "No steps have been recorded for this team so far."
                        : ""}
                    </div>
                  )}

                  {workflows.recent_steps && workflows.recent_steps.length > 0 && (
                    <div>
                      <h4 className={`mb-2 text-xs font-semibold uppercase tracking-wide ${subtle}`}>
                        Recent observed steps
                      </h4>
                      <div className="space-y-1">
                        {workflows.recent_steps
                          .slice()
                          .reverse()
                          .map((step, idx) => (
                            <div
                              key={idx}
                              className={`flex items-center justify-between gap-3 text-xs ${tc(theme, "text-gray-300", "text-gray-600")}`}
                            >
                              <span className={`font-medium ${heading}`}>
                                {step.step_label || prettyAction(step.action_key)}
                              </span>
                              <span className={subtle}>
                                {step.actor ? `${step.actor} · ` : ""}
                                {fmt(step.recorded_at)}
                              </span>
                            </div>
                          ))}
                      </div>
                    </div>
                  )}

                  {workflows.note && (
                    <p className={`text-xs ${subtle}`}>{workflows.note}</p>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Pillar 5 — the fleet's ONE shared knowledge pool (fleet-wide, not per-agent). */}
          <SharedKnowledgePanel theme={theme} />
        </>
      )}
    </div>
  );
}
