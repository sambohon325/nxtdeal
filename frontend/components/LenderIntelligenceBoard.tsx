"use client";
import { WorkButton, WorkInput , WorkStat} from "./WorkspaceUi";
import {RecordTable} from "./RecordTable";
import { WorkField } from "./WorkField";

// Finance's "Lender Intelligence" item (2026-07-19) -- closes the "Lender
// Intelligence" item from Sam's own six-pillar spec. Real per-lender scorecards
// (approval rate, average offered APR, average decision turnaround) computed off
// Deal Desk's own new, real, append-only lender_submission_history log (core/
// deals.py's submit_to_lender()/record_lender_decision()) -- and a real,
// transparent, rules-based lender recommendation (core/lender_intelligence.py),
// never a fabricated AI score. Historical deals seeded before this slice have no
// submission history at all -- reported honestly, never guessed at.
import { PRODUCT_ACCENT_COLORS } from "@/lib/productTheme";
import { useEffect, useState } from "react";
import {
  getLenderIntelligenceOverview,
  getSubmissionLog,
  getLenderRecommendation,
  type LenderIntelligenceOverview,
  type SubmissionLogEntry,
  type LenderRecommendation,
} from "@/lib/lenderIntelligence";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const RIBBON = PRODUCT_ACCENT_COLORS;

function pct(v: number | null | undefined): string {
  return v === null || v === undefined ? "—" : `${v}%`;
}

function money(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return `$${v.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}

function days(v: number | null | undefined): string {
  return v === null || v === undefined ? "—" : `${v.toFixed(1)}d`;
}

function decisionBadge(decision: string | null): { label: string; cls: string } {
  if (decision === "approved") return { label: "Approved", cls: "bg-emerald-950/30 border-emerald-900/50 text-emerald-300" };
  if (decision === "declined") return { label: "Declined", cls: "bg-red-950/30 border-red-900/50 text-red-300" };
  if (decision === "countered") return { label: "Countered", cls: "bg-amber-950/30 border-amber-900/50 text-amber-300" };
  return { label: "Pending", cls: "bg-zinc-800/50 border-zinc-700 text-zinc-400" };
}

function Kpi({ theme, label, value, color }: { theme: Theme; label: string; value: string; color: string }) { return <WorkStat label={label} value={value}/>; }

export function LenderIntelligenceBoard({ theme }: { theme: Theme }) {
  const [overview, setOverview] = useState<LenderIntelligenceOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<"scorecards" | "submissions" | "recommendation">("scorecards");
  const [submissions, setSubmissions] = useState<SubmissionLogEntry[] | null>(null);
  const [submissionsLoading, setSubmissionsLoading] = useState(false);
  const [dealLookup, setDealLookup] = useState("");
  const [rec, setRec] = useState<LenderRecommendation | null>(null);
  const [recLoading, setRecLoading] = useState(false);

  const cardClass = tc(theme, "rounded-lg border border-black/20 bg-brand-charcoal p-3", "rounded-lg border border-zinc-200 bg-zinc-50 p-3");
  const textClass = tc(theme, "bg-zinc-900 border-zinc-700 text-white placeholder:text-zinc-600", "bg-white border-zinc-300 text-black placeholder:text-zinc-400");
  const tableHeadClass = tc(theme, "text-[10px] uppercase tracking-wide text-zinc-500 border-b border-zinc-800", "text-[10px] uppercase tracking-wide text-zinc-500 border-b border-zinc-200");
  const rowBorder = tc(theme, "border-b border-zinc-800/60", "border-b border-zinc-100");

  function refresh() {
    setLoading(true);
    setError(null);
    getLenderIntelligenceOverview()
      .then(setOverview)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load"))
      .finally(() => setLoading(false));
  }

  useEffect(refresh, []);

  useEffect(() => {
    if (tab !== "submissions" || submissions) return;
    setSubmissionsLoading(true);
    getSubmissionLog(undefined, 200)
      .then((r) => setSubmissions(r.submissions))
      .catch(() => setSubmissions([]))
      .finally(() => setSubmissionsLoading(false));
  }, [tab, submissions]);

  useEffect(() => {
    if (tab !== "recommendation" || rec) return;
    setRecLoading(true);
    getLenderRecommendation()
      .then(setRec)
      .catch(() => setRec(null))
      .finally(() => setRecLoading(false));
  }, [tab, rec]);

  function lookupRecommendation() {
    setRecLoading(true);
    getLenderRecommendation(dealLookup.trim().toUpperCase() || undefined)
      .then(setRec)
      .catch(() => setRec(null))
      .finally(() => setRecLoading(false));
  }

  if (error) {
    return (
      <div className={tc(theme, "flex-1 flex items-center justify-center bg-brand-ink text-red-400 text-sm p-6", "flex-1 flex items-center justify-center bg-white text-red-600 text-sm p-6")}>
        {error}
      </div>
    );
  }

  return (
    <div className={tc(theme, "flex-1 flex flex-col min-h-0 bg-brand-ink text-white overflow-y-auto", "flex-1 flex flex-col min-h-0 bg-white text-black overflow-y-auto")}>
      <div className={tc(theme, "grid grid-cols-4 gap-3 p-4 border-b border-zinc-800", "grid grid-cols-4 gap-3 p-4 border-b border-zinc-200")}>
        <Kpi theme={theme} label="Total Submissions" value={loading ? "…" : String(overview?.total_submissions ?? 0)} color={RIBBON[0]} />
        <Kpi theme={theme} label="Decided / Pending" value={loading ? "…" : `${overview?.decided_submissions ?? 0} / ${overview?.pending_submissions ?? 0}`} color={RIBBON[1]} />
        <Kpi theme={theme} label="Overall Approval Rate" value={loading ? "…" : pct(overview?.overall_approval_rate_pct)} color={RIBBON[2]} />
        <Kpi theme={theme} label="Lenders w/ Sufficient Data" value={loading ? "…" : `${overview?.lenders_with_sufficient_data ?? 0} / ${overview?.total_lenders ?? 0}`} color={RIBBON[3]} />
      </div>

      {overview?.not_yet_tracked && Object.keys(overview.not_yet_tracked).length > 0 && (
        <div className="px-4 py-2 border-b border-zinc-800 flex flex-wrap gap-2">
          {Object.entries(overview.not_yet_tracked).map(([key, note]) => (
            <span key={key} className="text-xs px-2 py-1 rounded bg-amber-950/30 border border-amber-900/50 text-amber-300">
              {key}: {note}
            </span>
          ))}
        </div>
      )}

      <div className="px-4 py-2 border-b border-zinc-800 flex gap-2">
        {(["scorecards", "submissions", "recommendation"] as const).map((t) => (
          <WorkButton data-work-view aria-pressed={tab === t} type="submit"
            key={t}
            onClick={() => setTab(t)}
            className={`text-xs px-3 py-1.5 rounded font-medium capitalize transition ${
              tab === t
                ? "bg-brand-blue text-white"
                : tc(theme, "bg-zinc-800 text-zinc-300 hover:bg-zinc-700", "bg-zinc-100 text-zinc-600 hover:bg-zinc-200")
            }`}
          >
            {t === "scorecards" ? "Lender Scorecards" : t === "submissions" ? "Submission Log" : "Recommendation"}
          </WorkButton>
        ))}
      </div>

      <div className="flex-1 p-4 overflow-y-auto">
        {tab === "scorecards" && (
          <div className="space-y-2">
            {loading ? (
              <div className="text-xs text-zinc-500">Loading…</div>
            ) : !overview?.scorecards?.length ? (
              <div className="text-xs text-zinc-500">No lender submissions have been made through the live app yet.</div>
            ) : (
              <RecordTable className="w-full text-xs">
                <thead>
                  <tr className={tableHeadClass}>
                    <th className="text-left py-2 pr-3">Lender</th>
                    <th className="text-right py-2 pr-3">Submissions</th>
                    <th className="text-right py-2 pr-3">Decided</th>
                    <th className="text-right py-2 pr-3">Approved</th>
                    <th className="text-right py-2 pr-3">Declined</th>
                    <th className="text-right py-2 pr-3">Countered</th>
                    <th className="text-right py-2 pr-3">Approval Rate</th>
                    <th className="text-right py-2 pr-3">Avg APR</th>
                    <th className="text-right py-2 pr-3">Avg Turnaround</th>
                    <th className="text-right py-2">Data</th>
                  </tr>
                </thead>
                <tbody>
                  {overview.scorecards.map((s) => (
                    <tr key={s.lender_id} className={rowBorder}>
                      <td className="py-2 pr-3 font-medium">{s.lender_name}</td>
                      <td className="py-2 pr-3 text-right">{s.total_submissions}</td>
                      <td className="py-2 pr-3 text-right">{s.decided_submissions}</td>
                      <td className="py-2 pr-3 text-right text-emerald-400">{s.approved_count}</td>
                      <td className="py-2 pr-3 text-right text-red-400">{s.declined_count}</td>
                      <td className="py-2 pr-3 text-right text-amber-400">{s.countered_count}</td>
                      <td className="py-2 pr-3 text-right">{pct(s.approval_rate_pct)}</td>
                      <td className="py-2 pr-3 text-right">{s.avg_offered_apr != null ? `${s.avg_offered_apr}%` : "—"}</td>
                      <td className="py-2 pr-3 text-right">{days(s.avg_turnaround_days)}</td>
                      <td className="py-2 text-right">
                        {s.has_sufficient_data ? (
                          <span className="text-xs px-1.5 py-0.5 rounded bg-emerald-950/30 border border-emerald-900/50 text-emerald-300">Sufficient</span>
                        ) : (
                          <span className="text-xs px-1.5 py-0.5 rounded bg-zinc-800/50 border border-zinc-700 text-zinc-400">Low sample</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </RecordTable>
            )}
          </div>
        )}

        {tab === "submissions" && (
          <div className="space-y-2">
            {submissionsLoading ? (
              <div className="text-xs text-zinc-500">Loading…</div>
            ) : !submissions?.length ? (
              <div className="text-xs text-zinc-500">No real lender submissions on file.</div>
            ) : (
              submissions.map((entry, i) => {
                const badge = decisionBadge(entry.decision);
                return (
                  <div key={i} className={`${cardClass} flex items-center justify-between gap-3`}>
                    <div className="min-w-0">
                      <div className="font-medium text-sm truncate">
                        {entry.deal_id} — {entry.lender_name}
                      </div>
                      <div className="text-xs text-zinc-500 truncate">
                        {entry.customer_name ?? "Unknown customer"} · {entry.vehicle_description ?? "—"} · Tier: {entry.customer_credit_tier}
                      </div>
                      <div className="text-xs text-zinc-600">
                        Submitted {entry.submitted_at} {entry.decided_at ? `· Decided ${entry.decided_at}` : ""}
                        {entry.turnaround_days != null ? ` · ${days(entry.turnaround_days)} turnaround` : ""}
                      </div>
                      {entry.notes && <div className="text-xs text-zinc-500 mt-0.5">{entry.notes}</div>}
                    </div>
                    <div className="flex flex-col items-end gap-1 shrink-0">
                      <span className={`text-xs px-2 py-0.5 rounded border ${badge.cls}`}>{badge.label}</span>
                      {entry.terms?.apr != null && (
                        <span className="text-xs text-zinc-500">{entry.terms.apr}% APR</span>
                      )}
                    </div>
                  </div>
                );
              })
            )}
          </div>
        )}

        {tab === "recommendation" && (
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <WorkField label="Deal id"><WorkInput
                value={dealLookup}
                onChange={(e) => setDealLookup(e.target.value)}
                placeholder="Deal id (e.g. DEAL-00001)… optional, tier-scoped"
                className={`rounded-md border px-2 py-1.5 text-xs flex-1 ${textClass}`}
              /></WorkField>
              <WorkButton type="submit" variant="primary"
                onClick={lookupRecommendation}
                className="text-xs px-2.5 py-1.5 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition"
              >
                Get Recommendation
              </WorkButton>
            </div>

            {recLoading ? (
              <div className="text-xs text-zinc-500">Loading…</div>
            ) : rec?.error ? (
              <div className="text-xs text-red-400">{rec.error}</div>
            ) : rec ? (
              <>
                {rec.tier_note && (
                  <div className="text-xs px-2 py-1.5 rounded bg-amber-950/30 border border-amber-900/50 text-amber-300 inline-block">
                    {rec.tier_note}
                  </div>
                )}
                {rec.credit_tier && (
                  <div className="text-xs text-zinc-500">Credit tier: <span className="font-medium">{rec.credit_tier}</span> · min sample size for ranking: {rec.min_sample_size}</div>
                )}

                <div>
                  <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1.5">Ranked Recommendation</div>
                  {!rec.ranked?.length ? (
                    <div className="text-xs text-zinc-500">No lender currently clears the minimum sample size for a ranked recommendation.</div>
                  ) : (
                    <div className="space-y-1.5">
                      {rec.ranked.map((r, i) => (
                        <div key={r.lender_id} className={`${cardClass} flex items-center justify-between`}>
                          <div className="flex items-center gap-2">
                            <span className="text-xs font-semibold w-5 text-center">{i + 1}</span>
                            <span className="font-medium text-sm">{r.lender_name}</span>
                          </div>
                          <div className="flex items-center gap-4 text-xs text-zinc-400">
                            <span>{pct(r.approval_rate_pct)} approval</span>
                            <span>{r.avg_offered_apr != null ? `${r.avg_offered_apr}% APR` : "—"}</span>
                            <span>{days(r.avg_turnaround_days)}</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {!!rec.insufficient_data?.length && (
                  <div>
                    <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1.5 mt-3">Insufficient Data (not ranked)</div>
                    <div className="space-y-1.5">
                      {rec.insufficient_data.map((r) => (
                        <div key={r.lender_id} className={`${cardClass} flex items-center justify-between opacity-60`}>
                          <span className="font-medium text-sm">{r.lender_name}</span>
                          <span className="text-xs text-zinc-500">{r.decided_submissions} decided submission(s) — {r.basis}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </>
            ) : (
              <div className="text-xs text-zinc-500">No data.</div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
