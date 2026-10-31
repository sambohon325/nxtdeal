import { WorkField } from "./WorkField";
import { WorkButton, WorkInput, WorkSelect } from "./WorkspaceUi";
// components/SharedKnowledgePanel.tsx — Pillar 5: the agent fleet's ONE shared AI knowledge
// (2026-07-23). Mounted at the bottom of FleetBoard. Fleet-wide (not per-agent): shows the
// single pool every team agent reads from and writes to — the live cross-team patterns 2+
// teams have independently recognized, the persisted workflow + insight entries, an admin
// "publish recognized workflows" action, and a contribute-an-insight form open to any user.
// Reuses the same RIBBON/tc() vocabulary as FleetBoard; KPI tile markup matches the rest of
// the platform so the universal board-capture button can grab it.

import { PRODUCT_ACCENT_COLORS } from "@/lib/productTheme";
import { useEffect, useState } from "react";
import { getSession } from "@/lib/auth";
import {
  fetchFleetKnowledge,
  contributeInsight,
  publishWorkflows,
  deleteEntry,
  type FleetKnowledge,
  type KnowledgeSummary,
  type SharedEntry,
} from "@/lib/fleetKnowledge";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const RIBBON = PRODUCT_ACCENT_COLORS;

const SECTIONS = [
  "sales",
  "service",
  "marketing",
  "inventory",
  "finance",
  "operations",
  "administration",
  "readiness",
  "network",
];

function pretty(key: string): string {
  return key
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function Tile({ theme, value, label, accent }: { theme: Theme; value: number | string; label: string; accent: string }) {
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

export function SharedKnowledgePanel({ theme }: { theme: Theme }) {
  const [knowledge, setKnowledge] = useState<FleetKnowledge | null>(null);
  const [summary, setSummary] = useState<KnowledgeSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionMsg, setActionMsg] = useState<string | null>(null);

  const [section, setSection] = useState("sales");
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");

  const isAdmin = getSession()?.role === "ADMIN";

  const subtle = tc(theme, "text-gray-400", "text-gray-500");
  const heading = tc(theme, "text-white", "text-gray-900");
  const cardBase = tc(theme, "border-white/10 bg-white/[0.03]", "border-black/10 bg-white");

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchFleetKnowledge();
      setKnowledge(data.knowledge);
      setSummary(data.summary);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to load shared knowledge.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function doPublish() {
    setBusy(true);
    setActionMsg(null);
    try {
      const r = await publishWorkflows();
      setActionMsg(`Published ${r.published} new and refreshed ${r.updated} workflow(s) into the shared pool.`);
      await load();
    } catch (e) {
      setActionMsg(e instanceof Error ? e.message : "Publish failed.");
    } finally {
      setBusy(false);
    }
  }

  async function doContribute() {
    if (!title.trim() || !body.trim()) {
      setActionMsg("An insight needs both a title and a body.");
      return;
    }
    setBusy(true);
    setActionMsg(null);
    try {
      const r = await contributeInsight(section, title.trim(), body.trim());
      setActionMsg(r.created ? "Insight added to the shared pool." : "Existing insight updated.");
      setTitle("");
      setBody("");
      await load();
    } catch (e) {
      setActionMsg(e instanceof Error ? e.message : "Could not contribute the insight.");
    } finally {
      setBusy(false);
    }
  }

  async function doDelete(id: string) {
    setBusy(true);
    setActionMsg(null);
    try {
      await deleteEntry(id);
      await load();
    } catch (e) {
      setActionMsg(e instanceof Error ? e.message : "Could not remove the entry.");
    } finally {
      setBusy(false);
    }
  }

  const inputCls = `rounded-md border px-2 py-1.5 text-sm ${tc(theme, "border-white/15 bg-white/[0.04] text-white placeholder-gray-500", "border-black/15 bg-white text-gray-900 placeholder-gray-400")}`;

  return (
    <div className="space-y-4 border-t pt-6" style={{ borderColor: theme === "dark" ? "rgba(255,255,255,0.08)" : "rgba(0,0,0,0.08)" }}>
      <div>
        <h3 className={`text-lg font-semibold ${heading}`}>🧠 Shared Knowledge</h3>
        <p className={`mt-1 text-sm ${subtle}`}>
          One shared pool the whole fleet reads from and writes to — every team agent&apos;s learning in
          a single place, all on the one graph. Workflow entries are real recurring workflows a team
          recognized; insights are contributed by people; cross-team workflows are patterns two or more
          teams independently arrived at.
        </p>
      </div>

      {loading ? (
        <div className={`text-sm ${subtle}`}>Loading shared knowledge…</div>
      ) : error ? (
        <div className="rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-400">{error}</div>
      ) : (
        <>
          {summary && (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <Tile theme={theme} value={summary.total_entries} label="Shared Entries" accent={RIBBON[0]} />
              <Tile theme={theme} value={summary.cross_team_pattern_count} label="Cross-Team Patterns" accent={RIBBON[1]} />
              <Tile theme={theme} value={summary.workflow_entries} label="Workflow Entries" accent={RIBBON[2]} />
              <Tile theme={theme} value={summary.insight_entries} label="Insights" accent={RIBBON[3]} />
            </div>
          )}

          {actionMsg && (
            <div className={`rounded-lg border p-2.5 text-xs ${tc(theme, "border-white/10 bg-white/[0.03] text-gray-200", "border-black/10 bg-black/[0.02] text-gray-700")}`}>
              {actionMsg}
            </div>
          )}

          {/* Cross-team shared patterns — the clearest expression of shared knowledge. */}
          {knowledge && knowledge.cross_team_workflows.length > 0 && (
            <div className={`rounded-lg border p-4 ${cardBase}`}>
              <h4 className={`mb-2 text-xs font-semibold uppercase tracking-wide ${subtle}`}>
                Patterns recognized by multiple teams
              </h4>
              <div className="space-y-2">
                {knowledge.cross_team_workflows.map((c, i) => (
                  <div key={i} className="flex flex-wrap items-center justify-between gap-2">
                    <span className={`text-sm ${heading}`}>{c.steps.map(pretty).join(" → ")}</span>
                    <span className={`text-xs ${subtle}`}>
                      {c.teams.map(pretty).join(", ")} · {c.total_occurrences}× total
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* The persisted pool. */}
          <div className={`rounded-lg border p-4 ${cardBase}`}>
            <h4 className={`mb-2 text-xs font-semibold uppercase tracking-wide ${subtle}`}>
              Shared pool ({knowledge?.entry_count ?? 0})
            </h4>
            {knowledge && knowledge.entries.length > 0 ? (
              <div className="space-y-2">
                {knowledge.entries.map((e: SharedEntry) => (
                  <div
                    key={e.id}
                    className={`rounded-md border p-2.5 ${tc(theme, "border-white/10 bg-white/[0.02]", "border-black/10 bg-black/[0.02]")}`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <span
                            className="rounded px-1.5 py-0.5 text-xs font-semibold uppercase text-white"
                            style={{ background: e.kind === "workflow" ? RIBBON[0] : RIBBON[3] }}
                          >
                            {e.kind}
                          </span>
                          <span className={`text-xs ${subtle}`}>{e.source_display}</span>
                          {e.occurrences ? <span className={`text-xs ${subtle}`}>· {e.occurrences}×</span> : null}
                        </div>
                        <div className={`mt-1 text-sm ${heading}`}>{e.title}</div>
                        {e.body && <div className={`mt-0.5 text-xs ${subtle}`}>{e.body}</div>}
                      </div>
                      {isAdmin && (
                        <WorkButton variant="danger"
                          type="button"
                          onClick={() => doDelete(e.id)}
                          disabled={busy}
                          className={`shrink-0 text-xs ${subtle} hover:text-red-400 disabled:opacity-50`}
                        >
                          Remove
                        </WorkButton>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className={`text-sm ${subtle}`}>
                Nothing published yet.{" "}
                {isAdmin
                  ? "Publish the fleet's recognized workflows below, or contribute an insight."
                  : "An admin can publish the fleet's recognized workflows; anyone can contribute an insight."}
              </p>
            )}
          </div>

          {/* Contribute + publish. */}
          <div className={`rounded-lg border p-4 ${cardBase}`}>
            <h4 className={`mb-3 text-xs font-semibold uppercase tracking-wide ${subtle}`}>Contribute an insight</h4>
            <div className="flex flex-col gap-2 sm:flex-row sm:items-start">
              <WorkField label="Section"><WorkSelect value={section} onChange={(e) => setSection(e.target.value)} className={inputCls}>
                {SECTIONS.map((s) => (
                  <option key={s} value={s}>
                    {pretty(s)}
                  </option>
                ))}
              </WorkSelect></WorkField>
              <WorkField label="Title"><WorkInput
                type="text"
                placeholder="Title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                className={`${inputCls} sm:w-56`}
              /></WorkField>
              <WorkField label="What should the fleet know?"><WorkInput
                type="text"
                placeholder="What should the fleet know?"
                value={body}
                onChange={(e) => setBody(e.target.value)}
                className={`${inputCls} flex-1`}
              /></WorkField>
              <WorkButton
                type="button"
                onClick={doContribute}
                disabled={busy}
                className="shrink-0 rounded-md px-3 py-1.5 text-sm font-semibold text-white disabled:opacity-50"
                style={{ background: RIBBON[0] }}
              >
                Add
              </WorkButton>
            </div>

            {isAdmin && (
              <div className="mt-4 flex items-center gap-3">
                <WorkButton
                  type="button"
                  onClick={doPublish}
                  disabled={busy}
                  className="rounded-md px-3 py-1.5 text-sm font-semibold text-white disabled:opacity-50"
                  style={{ background: RIBBON[1] }}
                >
                  Publish recognized workflows
                </WorkButton>
                <span className={`text-xs ${subtle}`}>
                  Promotes every team&apos;s currently-recognized workflows into the shared pool.
                </span>
              </div>
            )}
          </div>

          {knowledge?.note && <p className={`text-xs ${subtle}`}>{knowledge.note}</p>}
        </>
      )}
    </div>
  );
}
