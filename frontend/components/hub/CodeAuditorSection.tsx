"use client";

// NXTDeal Hub -- AI-Powered Self-Auditing Code Layer console panel
// (2026-07-19).
//
// Sam's own kickoff request, scoped via AskUserQuestion into 3 binding
// decisions: (1) build this system first, then let it run the first full
// sweep; (2) every small-issue auto-fix lands on its own dedicated git
// branch with a real commit -- nothing is EVER auto-merged to main without
// a human; (3) since every dealer tenant runs the identical shared
// codebase (process-per-tenant, not per-tenant forks), "scanning deployed
// dealerships" means scanning the one shared codebase (backend/hub/
// frontend/extension) for code quality and bugs -- not per-tenant runtime
// health (that's the separate Infrastructure & Platform Ops/NOC system).
//
// Every finding below comes from a real, deterministic static-analysis
// rule over real files in this repo (hub/core/code_auditor_rules.py) --
// never an AI judgment call. See hub/core/code_auditor.py's own module
// docstring for the full severity ladder: small findings are auto-fixed
// onto their own branch immediately; medium findings get a drafted fix a
// human must explicitly approve or reject before anything is committed;
// large/systemic findings are never auto-fixed at all, only reported with
// real recommendations.

import { useEffect, useState } from "react";
import {
  HubApiError,
  getCodeAuditOverview,
  getCodeAuditSchedulerStatus,
  runCodeAuditScan,
  listCodeAuditFindings,
  getCodeAuditFinding,
  approveCodeAuditFinding,
  rejectCodeAuditFinding,
  resolveCodeAuditFinding,
  dismissCodeAuditFinding,
  listCodeAuditRuns,
  type CodeAuditOverview,
  type CodeAuditSchedulerStatus,
  type CodeAuditFinding,
  type CodeAuditRun,
  type CodeAuditSeverity,
  type CodeAuditStatus,
  type CodeAuditArea,
} from "@/lib/hubApi";

function relativeTime(iso: string | null): string {
  if (!iso) return "never";
  const diffMs = new Date(iso).getTime() - Date.now();
  const diffMin = Math.round(diffMs / 60000);
  const past = diffMin <= 0;
  const abs = Math.abs(diffMin);
  let label: string;
  if (abs < 60) label = `${abs} min`;
  else if (abs < 60 * 24) label = `${Math.round(abs / 60)} hr`;
  else label = `${Math.round(abs / (60 * 24))} day(s)`;
  return past ? `${label} ago` : `in ${label}`;
}

function errorMessage(error: unknown): string {
  return error instanceof HubApiError ? error.message : "Unable to reach the Hub.";
}

function KpiCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="bg-zinc-900 rounded-lg p-4">
      <div className="text-2xl font-semibold">{value}</div>
      <div className="text-[11px] uppercase tracking-wide text-zinc-500 mt-1">{label}</div>
    </div>
  );
}

function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="mb-4 text-sm text-red-400 bg-red-950/30 border border-red-900 rounded-lg px-4 py-3">
      {message}
    </div>
  );
}

const SEVERITY_STYLE: Record<CodeAuditSeverity, { dot: string; text: string; label: string }> = {
  small: { dot: "#33C481", text: "text-emerald-400", label: "Small -- Auto-Fixed" },
  medium: { dot: "#F4C300", text: "text-amber-400", label: "Medium -- Needs Approval" },
  large: { dot: "#EE3C25", text: "text-red-400", label: "Large / Systemic -- Urgent" },
};

const STATUS_STYLE: Record<CodeAuditStatus, { text: string; bg: string; label: string }> = {
  new: { text: "text-zinc-300", bg: "bg-zinc-800", label: "New" },
  auto_fixed: { text: "text-emerald-400", bg: "bg-emerald-950/40", label: "Auto-Fixed" },
  awaiting_approval: { text: "text-amber-400", bg: "bg-amber-950/40", label: "Awaiting Approval" },
  approved: { text: "text-emerald-400", bg: "bg-emerald-950/40", label: "Approved" },
  rejected: { text: "text-zinc-400", bg: "bg-zinc-800", label: "Rejected" },
  reported: { text: "text-red-400", bg: "bg-red-950/40", label: "Reported" },
  resolved: { text: "text-zinc-500", bg: "bg-zinc-900", label: "Resolved" },
  dismissed: { text: "text-zinc-500", bg: "bg-zinc-900", label: "Dismissed" },
};

const ALL_VALUE = "__all__";

export default function CodeAuditorSection() {
  const [overview, setOverview] = useState<CodeAuditOverview | null>(null);
  const [schedulerStatus, setSchedulerStatus] = useState<CodeAuditSchedulerStatus | null>(null);
  const [findings, setFindings] = useState<CodeAuditFinding[] | null>(null);
  const [runs, setRuns] = useState<CodeAuditRun[] | null>(null);
  const [error, setError] = useState("");
  const [selectedFindingId, setSelectedFindingId] = useState<string | null>(null);

  const [severityFilter, setSeverityFilter] = useState<CodeAuditSeverity | "">("");
  const [statusFilter, setStatusFilter] = useState<CodeAuditStatus | "">("");
  const [areaFilter, setAreaFilter] = useState<CodeAuditArea | "">("");
  const [runIdFilter, setRunIdFilter] = useState<string>("");

  const [triggeredBy, setTriggeredBy] = useState("nxtdeal_staff");
  const [scanning, setScanning] = useState(false);
  const [lastScanSummary, setLastScanSummary] = useState<CodeAuditRun | null>(null);

  async function load() {
    try {
      const [o, s, f, r] = await Promise.all([
        getCodeAuditOverview(),
        getCodeAuditSchedulerStatus(),
        listCodeAuditFindings({
          severity: severityFilter || undefined,
          status: statusFilter || undefined,
          area: areaFilter || undefined,
          run_id: runIdFilter || undefined,
        }),
        listCodeAuditRuns(),
      ]);
      setOverview(o);
      setSchedulerStatus(s);
      setFindings(f.findings);
      setRuns(r.runs);
      setError("");
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [severityFilter, statusFilter, areaFilter, runIdFilter]);

  async function handleScan() {
    if (!triggeredBy.trim()) return;
    setScanning(true);
    setError("");
    try {
      const run = await runCodeAuditScan(triggeredBy.trim());
      setLastScanSummary(run);
      await load();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setScanning(false);
    }
  }

  if (selectedFindingId) {
    return (
      <FindingDetailPanel
        findingId={selectedFindingId}
        onBack={() => setSelectedFindingId(null)}
        onChanged={load}
      />
    );
  }

  return (
    <div>
      <div className="mb-4">
        <h2 className="text-lg font-brand font-bold tracking-tight">
          AI-Powered Self-Auditing Code Layer
        </h2>
        <p className="text-xs text-zinc-500 mt-1 max-w-2xl leading-relaxed">
          Scans the one shared codebase every dealer tenant runs -- backend, hub, frontend,
          and the Network Connect extension -- for real design/data flaws and bugs. Every
          finding is a real, deterministic static-analysis rule, never an AI judgment call.
          Small issues fix themselves on their own git branch (never merged to main). Medium
          issues draft a fix and wait for a human to approve or reject. Large/systemic issues
          are never auto-fixed -- only reported, with real recommendations.
        </p>
      </div>

      {error && <ErrorBanner message={error} />}

      <div className="bg-zinc-900 rounded-lg p-4 mb-6 flex items-end gap-3 flex-wrap">
        <div>
          <label className="block text-[10px] uppercase tracking-wide text-zinc-500 mb-1">
            Triggered By
          </label>
          <input
            value={triggeredBy}
            onChange={(e) => setTriggeredBy(e.target.value)}
            className="h-9 px-3 rounded bg-zinc-950 border border-zinc-800 text-sm focus:outline-none w-56"
          />
        </div>
        <button
          onClick={handleScan}
          disabled={scanning || !triggeredBy.trim()}
          className="brand-cta font-brand font-bold uppercase tracking-wide text-xs px-5 py-2.5 disabled:opacity-50"
        >
          {scanning ? "Scanning..." : "Run Scan Now"}
        </button>
        {lastScanSummary && (
          <div className="text-xs text-zinc-400">
            Run {lastScanSummary.run_id}: {lastScanSummary.total_findings} new finding(s) --
            {" "}small {lastScanSummary.by_severity.small ?? 0}, medium{" "}
            {lastScanSummary.by_severity.medium ?? 0}, large {lastScanSummary.by_severity.large ?? 0}
            {lastScanSummary.status === "failed" && (
              <span className="text-red-400"> -- scan failed: {lastScanSummary.error}</span>
            )}
          </div>
        )}
      </div>

      <div className="bg-zinc-900 rounded-lg p-4 mb-6 flex items-center gap-4 flex-wrap">
        <div className="flex items-center gap-1.5">
          <span
            className={`h-2 w-2 rounded-full shrink-0 ${
              schedulerStatus?.running ? "bg-emerald-500" : "bg-zinc-600"
            }`}
          />
          <span className="text-xs font-medium text-zinc-300">
            Automated scan {schedulerStatus?.running ? "running" : "not running"}
            {schedulerStatus && ` -- every ${Math.round(schedulerStatus.tick_seconds / 3600)}h`}
          </span>
        </div>
        <div className="text-xs text-zinc-500">
          Last automated run:{" "}
          <span className="text-zinc-300">{relativeTime(schedulerStatus?.last_scheduled_run_at ?? null)}</span>
          {schedulerStatus?.last_scheduled_run && (
            <span>
              {" "}
              ({schedulerStatus.last_scheduled_run.total_findings} new finding(s), run{" "}
              {schedulerStatus.last_scheduled_run.run_id})
            </span>
          )}
        </div>
        <div className="text-xs text-zinc-500">
          Next automated run:{" "}
          <span className="text-zinc-300">{relativeTime(schedulerStatus?.next_scheduled_run_at ?? null)}</span>
        </div>
      </div>

      <div className="grid grid-cols-5 gap-3 mb-3">
        <KpiCard label="Total Findings" value={overview?.total_findings ?? "..."} />
        <KpiCard label="Open" value={overview?.open_findings ?? "..."} />
        <KpiCard label="Auto-Fixed" value={overview?.auto_fixed_count ?? "..."} />
        <KpiCard label="Awaiting Approval" value={overview?.awaiting_approval_count ?? "..."} />
        <KpiCard label="Reported (Large)" value={overview?.reported_large_count ?? "..."} />
      </div>

      {overview && (
        <div className="grid grid-cols-2 gap-3 mb-6">
          <div className="bg-zinc-900 rounded-lg p-4">
            <div className="text-[11px] uppercase tracking-wide text-zinc-500 mb-2">
              Open By Severity
            </div>
            <div className="flex gap-4">
              {(Object.keys(overview.by_severity_open) as CodeAuditSeverity[]).map((sev) => (
                <div key={sev} className="flex items-center gap-1.5">
                  <span
                    className="h-2 w-2 rounded-full"
                    style={{ background: SEVERITY_STYLE[sev].dot }}
                  />
                  <span className="text-xs text-zinc-400">
                    {sev}: {overview.by_severity_open[sev]}
                  </span>
                </div>
              ))}
            </div>
          </div>
          <div className="bg-zinc-900 rounded-lg p-4">
            <div className="text-[11px] uppercase tracking-wide text-zinc-500 mb-2">
              Open By Area
            </div>
            <div className="flex gap-4 flex-wrap">
              {(Object.keys(overview.by_area_open) as CodeAuditArea[]).map((area) => (
                <span key={area} className="text-xs text-zinc-400">
                  {area}: {overview.by_area_open[area]}
                </span>
              ))}
            </div>
          </div>
        </div>
      )}

      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <h3 className="font-brand font-bold uppercase tracking-wide text-sm">Findings</h3>
        <div className="flex gap-2 flex-wrap">
          <select
            value={severityFilter}
            onChange={(e) => setSeverityFilter(e.target.value as CodeAuditSeverity | "")}
            className="h-8 px-2 rounded bg-zinc-950 border border-zinc-800 text-xs focus:outline-none"
          >
            <option value="">All severities</option>
            <option value="small">Small</option>
            <option value="medium">Medium</option>
            <option value="large">Large</option>
          </select>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as CodeAuditStatus | "")}
            className="h-8 px-2 rounded bg-zinc-950 border border-zinc-800 text-xs focus:outline-none"
          >
            <option value="">All statuses</option>
            <option value="new">New</option>
            <option value="auto_fixed">Auto-Fixed</option>
            <option value="awaiting_approval">Awaiting Approval</option>
            <option value="approved">Approved</option>
            <option value="rejected">Rejected</option>
            <option value="reported">Reported</option>
            <option value="resolved">Resolved</option>
            <option value="dismissed">Dismissed</option>
          </select>
          <select
            value={areaFilter}
            onChange={(e) => setAreaFilter(e.target.value as CodeAuditArea | "")}
            className="h-8 px-2 rounded bg-zinc-950 border border-zinc-800 text-xs focus:outline-none"
          >
            <option value="">All areas</option>
            <option value="backend">Backend</option>
            <option value="hub">Hub</option>
            <option value="frontend">Frontend</option>
            <option value="extension">Extension</option>
          </select>
          {runIdFilter && (
            <button
              onClick={() => setRunIdFilter("")}
              className="h-8 px-2 rounded bg-zinc-800 text-zinc-400 hover:text-white text-xs"
            >
              Clear run filter ({runIdFilter}) ✕
            </button>
          )}
        </div>
      </div>

      {findings && findings.length === 0 && (
        <div className="text-sm text-zinc-500 bg-zinc-900 rounded-lg p-5 mb-6">
          No findings match these filters. If no scan has ever run, click &quot;Run Scan
          Now&quot; above to sweep the shared codebase for real.
        </div>
      )}

      {findings && findings.length > 0 && (
        <div className="bg-zinc-900 rounded-lg overflow-hidden mb-6">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-[10px] uppercase tracking-wide text-zinc-500 border-b border-zinc-800">
                <th className="text-left px-4 py-2">Rule</th>
                <th className="text-left px-4 py-2">Severity</th>
                <th className="text-left px-4 py-2">Area</th>
                <th className="text-left px-4 py-2">File</th>
                <th className="text-left px-4 py-2">Status</th>
                <th className="text-left px-4 py-2">Found</th>
              </tr>
            </thead>
            <tbody>
              {findings.map((f) => {
                const sev = SEVERITY_STYLE[f.severity];
                const st = STATUS_STYLE[f.status];
                return (
                  <tr
                    key={f.finding_id}
                    onClick={() => setSelectedFindingId(f.finding_id)}
                    className="border-b border-zinc-800/60 last:border-0 hover:bg-zinc-800/40 cursor-pointer"
                  >
                    <td className="px-4 py-3 font-medium">{f.rule_title}</td>
                    <td className="px-4 py-3">
                      <span className="flex items-center gap-1.5">
                        <span className="h-2 w-2 rounded-full shrink-0" style={{ background: sev.dot }} />
                        <span className={`text-xs ${sev.text}`}>{f.severity}</span>
                      </span>
                    </td>
                    <td className="px-4 py-3 text-xs text-zinc-400">{f.area}</td>
                    <td className="px-4 py-3 text-xs text-zinc-500 font-mono">
                      {f.file_path}
                      {f.line_number ? `:${f.line_number}` : ""}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`text-[10px] uppercase tracking-wide ${st.bg} ${st.text} px-2 py-0.5 rounded`}
                      >
                        {st.label}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-xs text-zinc-500">
                      {new Date(f.created_at).toLocaleDateString()}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <h3 className="font-brand font-bold uppercase tracking-wide text-sm mb-3">Recent Runs</h3>

      {runs && runs.length === 0 && (
        <div className="text-sm text-zinc-500 bg-zinc-900 rounded-lg p-5 mb-6">
          No scans have run yet.
        </div>
      )}

      {runs && runs.length > 0 && (
        <div className="bg-zinc-900 rounded-lg overflow-hidden mb-6">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-[10px] uppercase tracking-wide text-zinc-500 border-b border-zinc-800">
                <th className="text-left px-4 py-2">Run</th>
                <th className="text-left px-4 py-2">Triggered By</th>
                <th className="text-left px-4 py-2">Started</th>
                <th className="text-left px-4 py-2">Findings</th>
                <th className="text-left px-4 py-2">Status</th>
              </tr>
            </thead>
            <tbody>
              {[...runs]
                .sort((a, b) => (a.started_at < b.started_at ? 1 : -1))
                .map((r) => (
                  <tr
                    key={r.run_id}
                    onClick={() => setRunIdFilter(r.run_id)}
                    className="border-b border-zinc-800/60 last:border-0 hover:bg-zinc-800/40 cursor-pointer"
                  >
                    <td className="px-4 py-3 font-medium">{r.run_id}</td>
                    <td className="px-4 py-3 text-xs text-zinc-400">
                      {r.triggered_by}
                      {r.triggered_by === "scheduler" && (
                        <span className="ml-1.5 text-[10px] uppercase tracking-wide bg-zinc-800 text-emerald-400 px-1.5 py-0.5 rounded">
                          Automated
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-xs text-zinc-500">
                      {new Date(r.started_at).toLocaleString()}
                    </td>
                    <td className="px-4 py-3 text-xs text-zinc-400">
                      {r.total_findings} (small {r.by_severity.small ?? 0}, medium{" "}
                      {r.by_severity.medium ?? 0}, large {r.by_severity.large ?? 0})
                    </td>
                    <td className="px-4 py-3 text-xs text-zinc-400">{r.status}</td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      )}

      {overview && <p className="text-[11px] text-zinc-500 leading-relaxed">{overview.note}</p>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Finding detail -- description/evidence/recommendation + the real
// approve/reject/resolve/dismiss actions.
// ---------------------------------------------------------------------------

function FindingDetailPanel({
  findingId,
  onBack,
  onChanged,
}: {
  findingId: string;
  onBack: () => void;
  onChanged: () => void;
}) {
  const [finding, setFinding] = useState<CodeAuditFinding | null>(null);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState("");

  const [actorName, setActorName] = useState("nxtdeal_staff");
  const [note, setNote] = useState("");

  async function load() {
    try {
      setFinding(await getCodeAuditFinding(findingId));
      setError("");
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [findingId]);

  async function handleApprove() {
    if (!actorName.trim()) return;
    setSaving("approve");
    setError("");
    try {
      const updated = await approveCodeAuditFinding(findingId, actorName.trim(), note || undefined);
      setFinding(updated);
      onChanged();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setSaving("");
    }
  }

  async function handleReject() {
    if (!actorName.trim()) return;
    setSaving("reject");
    setError("");
    try {
      const updated = await rejectCodeAuditFinding(findingId, actorName.trim(), note || undefined);
      setFinding(updated);
      onChanged();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setSaving("");
    }
  }

  async function handleResolve() {
    if (!actorName.trim()) return;
    setSaving("resolve");
    setError("");
    try {
      const updated = await resolveCodeAuditFinding(findingId, actorName.trim(), note || undefined);
      setFinding(updated);
      onChanged();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setSaving("");
    }
  }

  async function handleDismiss() {
    if (!actorName.trim() || !note.trim()) {
      setError("Dismissing a finding requires a real note explaining why.");
      return;
    }
    setSaving("dismiss");
    setError("");
    try {
      const updated = await dismissCodeAuditFinding(findingId, actorName.trim(), note.trim());
      setFinding(updated);
      onChanged();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setSaving("");
    }
  }

  if (!finding) {
    return (
      <div>
        <button onClick={onBack} className="text-xs text-zinc-500 hover:text-white mb-4">
          ← Back to Findings
        </button>
        {error && <ErrorBanner message={error} />}
        <div className="text-sm text-zinc-500">Loading...</div>
      </div>
    );
  }

  const sev = SEVERITY_STYLE[finding.severity];
  const st = STATUS_STYLE[finding.status];
  const isTerminal = finding.status === "resolved" || finding.status === "dismissed";

  return (
    <div>
      <button onClick={onBack} className="text-xs text-zinc-500 hover:text-white mb-4">
        ← Back to Findings
      </button>

      {error && <ErrorBanner message={error} />}

      <div className="bg-zinc-900 rounded-lg p-5 mb-4">
        <div className="flex items-center justify-between flex-wrap gap-2 mb-2">
          <h2 className="text-lg font-brand font-bold tracking-tight">{finding.rule_title}</h2>
          <div className="flex items-center gap-2">
            <span className="flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full shrink-0" style={{ background: sev.dot }} />
              <span className={`text-xs ${sev.text}`}>{sev.label}</span>
            </span>
            <span className={`text-[10px] uppercase tracking-wide ${st.bg} ${st.text} px-2 py-0.5 rounded`}>
              {st.label}
            </span>
          </div>
        </div>
        <div className="text-xs text-zinc-500 font-mono mb-3">
          {finding.area} / {finding.file_path}
          {finding.line_number ? `:${finding.line_number}` : ""}
        </div>

        <div className="text-sm text-zinc-300 mb-3">{finding.description}</div>

        {finding.evidence && (
          <div className="mb-3">
            <div className="text-[10px] uppercase tracking-wide text-zinc-500 mb-1">Evidence</div>
            <pre className="text-xs text-zinc-400 bg-zinc-950 rounded p-3 overflow-x-auto whitespace-pre-wrap">
              {finding.evidence}
            </pre>
          </div>
        )}

        <div>
          <div className="text-[10px] uppercase tracking-wide text-zinc-500 mb-1">Recommendation</div>
          <div className="text-sm text-zinc-300">{finding.recommendation}</div>
        </div>
      </div>

      {(finding.status === "auto_fixed" || finding.status === "approved") && (
        <div className="bg-emerald-950/20 border border-emerald-900 rounded-lg p-5 mb-4">
          <div className="text-[10px] uppercase tracking-wide text-emerald-400 mb-2">
            {finding.status === "auto_fixed" ? "Auto-Fixed On Its Own Branch" : "Fix Approved -- Committed On Its Own Branch"}
          </div>
          <div className="text-xs text-zinc-400 mb-1">
            Branch: <span className="font-mono text-zinc-300">{finding.branch_name}</span>
          </div>
          <div className="text-xs text-zinc-400">
            Commit: <span className="font-mono text-zinc-300">{finding.commit_sha}</span>
          </div>
          <p className="text-[11px] text-zinc-500 mt-2 leading-relaxed">
            This was never merged to main -- review the branch and merge it yourself once
            you&apos;ve confirmed the change is correct.
          </p>
        </div>
      )}

      {finding.proposed_fix && (
        <div className="bg-zinc-900 rounded-lg p-5 mb-4">
          <div className="text-[10px] uppercase tracking-wide text-zinc-500 mb-2">
            Proposed Fix (drafted, not yet applied)
          </div>
          <pre className="text-xs text-zinc-400 bg-zinc-950 rounded p-3 overflow-x-auto whitespace-pre-wrap max-h-96 overflow-y-auto">
            {finding.proposed_fix}
          </pre>
        </div>
      )}

      {finding.resolved_note && (
        <div className="bg-zinc-900 rounded-lg p-5 mb-4">
          <div className="text-[10px] uppercase tracking-wide text-zinc-500 mb-1">
            {finding.resolved_by} said
          </div>
          <div className="text-sm text-zinc-300">{finding.resolved_note}</div>
        </div>
      )}

      {!isTerminal && (
        <div className="bg-zinc-900 rounded-lg p-5">
          <div className="text-[10px] uppercase tracking-wide text-zinc-500 mb-3">Actions</div>

          <div className="flex gap-3 mb-3 flex-wrap">
            <div>
              <label className="block text-[10px] uppercase tracking-wide text-zinc-500 mb-1">
                Your Name
              </label>
              <input
                value={actorName}
                onChange={(e) => setActorName(e.target.value)}
                className="h-9 px-3 rounded bg-zinc-950 border border-zinc-800 text-sm focus:outline-none w-56"
              />
            </div>
            <div className="flex-1 min-w-[240px]">
              <label className="block text-[10px] uppercase tracking-wide text-zinc-500 mb-1">
                Note (required to dismiss)
              </label>
              <input
                value={note}
                onChange={(e) => setNote(e.target.value)}
                className="h-9 px-3 rounded bg-zinc-950 border border-zinc-800 text-sm focus:outline-none w-full"
              />
            </div>
          </div>

          <div className="flex gap-2 flex-wrap">
            {finding.status === "awaiting_approval" && (
              <>
                <button
                  onClick={handleApprove}
                  disabled={saving === "approve" || !finding.proposed_fix}
                  className="brand-cta font-brand font-bold uppercase tracking-wide text-xs px-4 py-2 disabled:opacity-50"
                  title={!finding.proposed_fix ? "No safe automatic fix was generated -- nothing to approve." : ""}
                >
                  {saving === "approve" ? "Committing..." : "Approve & Commit To Branch"}
                </button>
                <button
                  onClick={handleReject}
                  disabled={saving === "reject"}
                  className="bg-zinc-800 text-zinc-300 hover:text-white font-medium uppercase tracking-wide text-xs px-4 py-2 rounded disabled:opacity-50"
                >
                  {saving === "reject" ? "Rejecting..." : "Reject Proposed Fix"}
                </button>
              </>
            )}
            <button
              onClick={handleResolve}
              disabled={saving === "resolve"}
              className="bg-zinc-800 text-zinc-300 hover:text-white font-medium uppercase tracking-wide text-xs px-4 py-2 rounded disabled:opacity-50"
            >
              {saving === "resolve" ? "Marking..." : "Mark Resolved"}
            </button>
            <button
              onClick={handleDismiss}
              disabled={saving === "dismiss"}
              className="bg-zinc-800 text-zinc-400 hover:text-white font-medium uppercase tracking-wide text-xs px-4 py-2 rounded disabled:opacity-50"
            >
              {saving === "dismiss" ? "Dismissing..." : "Dismiss"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
