"""
NXTDeal Hub -- AI-Powered Self-Auditing Code Layer (added 2026-07-19).

Sam's ask, verbatim from the kickoff message: "I want to build an ai powered
self auiting coding / programming layer that looks for design and data
flaws, bugs, has a built in scaling system (small issue - fixes itself,
medium issue - informs with summary before changing, large / systemic
issues - reports urgently with several recommendations) - this should live
on the hub, and scan through not only the hub but existing / deployed
dealerships and Dealer Network browser extensions."

This followed a first, separate ask -- "auditing the entirety of what we've
built, sweep for bugs... make sure the way we've structured everything...
isn't seen as just 'vibe coding'... rebuild things in a way that human
programmers would expect them to be." Three governing decisions Sam made
directly (AskUserQuestion, 2026-07-19), binding on this whole build:

  1. SEQUENCING -- build this system FIRST, then let it run the first real
     sweep against the real codebase, rather than doing a separate manual/
     subagent audit pass beforehand. (This module's own first real run is
     documented in CLAUDE.md once it completes.)
  2. AUTO-FIX AUTHORITY -- every SMALL-tier auto-fix lands on its own
     dedicated git branch with a real commit (see code_auditor_git.py).
     NOTHING this system does is EVER auto-merged to main. A human always
     reviews and merges.
  3. SCAN SCOPE -- every dealer tenant runs the IDENTICAL shared codebase
     (process-per-tenant, not a per-tenant fork -- see CLAUDE.md's "NXTDeal
     Hub / Multi-Tenant Architecture"). So "scan deployed dealerships"
     means scanning the ONE real shared codebase (backend/, hub/, frontend/,
     network-connect-extension/) for code-quality/bug issues -- NOT
     per-tenant runtime health monitoring, which is a fully separate,
     already-built concern (Infrastructure & Platform Operations / NOC).

DESIGN -- "real rules, never fake AI," matching this codebase's own
established convention (hub_core/network_audit.py, hub_core/collections.py's risk
scoring, hub_core/lead_record.py's next_best_action(),
hub_core/readiness_recommendations.py): the actual finding/severity
determination is a real, deterministic, INSPECTABLE static-analysis rule
engine over real file content (see code_auditor_rules.py) -- not an opaque
LLM judgment call. Every finding traces to a real rule, a real file path
and line number, and a real matched snippet. An OPTIONAL AI-drafted
narrative can sit on top later for a human-readable urgent-report summary
(matching readiness_summary_wizard.py's/network_summary_wizard.py's
isolated-client + honest-fallback pattern) -- not built in this pass, since
the real, structured findings below are already fully human-readable
without one; flagged as a natural future enrichment, not a gap in the core
mechanism.

DATA MODEL -- matching this Hub's OWN established convention (confirmed by
reading hub/hub_core/dealer_backups.py + hub/hub_core/hub_audit.py before writing
this file), NOT the backend/'s graph-entity/id-prefix pattern -- a direct
search confirmed hub/ has no entity_types.py or id_generator.py anywhere,
meaning the Hub's real convention is a plain dataclass + an in-memory
registry class with its own next_id() counter, persisted via a matching
code_auditor_storage.py using the same atomic-write + truncated-JSON-
recovery convention as dealer_backups_storage.py.

SEVERITY LADDER (Sam's own 3-tier spec, exactly as given):
  small   -- a real, narrow, mechanically-safe fix. Auto-fixed: this system
             generates the real fix, verifies it re-parses as valid code,
             creates a real dedicated git branch, and commits it -- never
             merges, never touches main. If a fix can't be generated safely
             (e.g. an ambiguous target), the finding is reported as medium
             instead of guessed at.
  medium  -- a real issue where an automatic fix carries real risk of being
             wrong or incomplete. This system drafts a real, specific
             summary of the problem (and a proposed fix where one exists)
             but never applies it until a human explicitly approves via the
             Hub console.
  large   -- a real, systemic/structural finding with no single safe fix.
             This system never attempts to fix it -- only a real, concrete,
             multi-recommendation urgent report.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from hub_core import code_auditor_rules as rules
from hub_core import code_auditor_git as git_actions


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


SEVERITY_LEVELS = ("small", "medium", "large")

SEVERITY_LABELS = {
    "small": "Small -- Auto-Fixed",
    "medium": "Medium -- Needs Approval",
    "large": "Large / Systemic -- Urgent Report",
}

STATUS_VALUES = (
    "new",
    "auto_fixed",
    "awaiting_approval",
    "approved",
    "rejected",
    "reported",
    "resolved",
    "dismissed",
)

AREAS = ("backend", "hub", "frontend", "extension")


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class CodeAuditFinding:
    finding_id: str
    run_id: str
    rule_key: str
    rule_title: str
    severity: str
    area: str
    file_path: str
    line_number: Optional[int]
    description: str
    evidence: str
    recommendation: str
    status: str = "new"
    proposed_fix: Optional[str] = None
    branch_name: Optional[str] = None
    commit_sha: Optional[str] = None
    resolved_by: Optional[str] = None
    resolved_note: Optional[str] = None
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    def to_dict(self):
        return {
            "finding_id": self.finding_id,
            "run_id": self.run_id,
            "rule_key": self.rule_key,
            "rule_title": self.rule_title,
            "severity": self.severity,
            "severity_label": SEVERITY_LABELS.get(self.severity, self.severity),
            "area": self.area,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "description": self.description,
            "evidence": self.evidence,
            "recommendation": self.recommendation,
            "status": self.status,
            "proposed_fix": self.proposed_fix,
            "branch_name": self.branch_name,
            "commit_sha": self.commit_sha,
            "resolved_by": self.resolved_by,
            "resolved_note": self.resolved_note,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @staticmethod
    def from_dict(data):
        return CodeAuditFinding(
            finding_id=data["finding_id"],
            run_id=data.get("run_id", ""),
            rule_key=data.get("rule_key", ""),
            rule_title=data.get("rule_title", ""),
            severity=data.get("severity", "large"),
            area=data.get("area", "backend"),
            file_path=data.get("file_path", ""),
            line_number=data.get("line_number"),
            description=data.get("description", ""),
            evidence=data.get("evidence", ""),
            recommendation=data.get("recommendation", ""),
            status=data.get("status", "new"),
            proposed_fix=data.get("proposed_fix"),
            branch_name=data.get("branch_name"),
            commit_sha=data.get("commit_sha"),
            resolved_by=data.get("resolved_by"),
            resolved_note=data.get("resolved_note"),
            created_at=data.get("created_at", _now_iso()),
            updated_at=data.get("updated_at", _now_iso()),
        )


@dataclass
class CodeAuditRun:
    run_id: str
    triggered_by: str
    areas_scanned: List[str] = field(default_factory=list)
    started_at: str = field(default_factory=_now_iso)
    completed_at: Optional[str] = None
    total_findings: int = 0
    by_severity: Dict[str, int] = field(default_factory=dict)
    status: str = "running"
    error: Optional[str] = None

    def to_dict(self):
        return {
            "run_id": self.run_id,
            "triggered_by": self.triggered_by,
            "areas_scanned": self.areas_scanned,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "total_findings": self.total_findings,
            "by_severity": self.by_severity,
            "status": self.status,
            "error": self.error,
        }

    @staticmethod
    def from_dict(data):
        return CodeAuditRun(
            run_id=data["run_id"],
            triggered_by=data.get("triggered_by", "nxtdeal_staff"),
            areas_scanned=list(data.get("areas_scanned", [])),
            started_at=data.get("started_at", _now_iso()),
            completed_at=data.get("completed_at"),
            total_findings=data.get("total_findings", 0),
            by_severity=dict(data.get("by_severity", {})),
            status=data.get("status", "completed"),
            error=data.get("error"),
        )


class CodeAuditRegistry:

    def __init__(self):
        self.findings: Dict[str, CodeAuditFinding] = {}
        self.runs: Dict[str, CodeAuditRun] = {}
        self._finding_counter = 0
        self._run_counter = 0

    def add_finding(self, finding: CodeAuditFinding):
        self.findings[finding.finding_id] = finding

    def next_finding_id(self):
        self._finding_counter += 1
        return f"CAF-{self._finding_counter:05}"

    def list_findings(self, severity=None, status=None, area=None, run_id=None):
        items = list(self.findings.values())
        if severity:
            items = [f for f in items if f.severity == severity]
        if status:
            items = [f for f in items if f.status == status]
        if area:
            items = [f for f in items if f.area == area]
        if run_id:
            items = [f for f in items if f.run_id == run_id]
        return sorted(items, key=lambda f: f.created_at, reverse=True)

    def get_finding(self, finding_id):
        return self.findings.get(finding_id)

    def add_run(self, run: CodeAuditRun):
        self.runs[run.run_id] = run

    def next_run_id(self):
        self._run_counter += 1
        return f"CAR-{self._run_counter:05}"

    def list_runs(self):
        return sorted(self.runs.values(), key=lambda r: r.started_at, reverse=True)

    def get_run(self, run_id):
        return self.runs.get(run_id)

    def recover_counters(self):
        highest_f = 0
        for f in self.findings.values():
            try:
                highest_f = max(highest_f, int(f.finding_id.split("-")[1]))
            except (IndexError, ValueError):
                continue
        self._finding_counter = max(self._finding_counter, highest_f)

        highest_r = 0
        for r in self.runs.values():
            try:
                highest_r = max(highest_r, int(r.run_id.split("-")[1]))
            except (IndexError, ValueError):
                continue
        self._run_counter = max(self._run_counter, highest_r)

    def reset(self):
        self.findings = {}
        self.runs = {}
        self._finding_counter = 0
        self._run_counter = 0


registry = CodeAuditRegistry()


# ---------------------------------------------------------------------------
# Scan orchestration
# ---------------------------------------------------------------------------

def run_scan(triggered_by="nxtdeal_staff", areas=None):
    """Runs every real rule in code_auditor_rules.ALL_RULES against the
    real repo on disk, creates a real CodeAuditRun, and creates a real
    CodeAuditFinding per result -- deduped against any still-open finding
    from a prior run covering the identical (rule_key, file_path,
    line_number), so re-running the sweep doesn't pile up duplicate
    findings for a problem nobody has acted on yet (same dedup discipline
    hub_core/compliance.py's run_full_scan()/hub_core/trigger_alerts.py's
    run_scan() already established in the backend). SMALL-tier findings
    are auto-fixed immediately, inline, as part of this same run -- see
    _attempt_auto_fix() below."""

    run = CodeAuditRun(
        run_id=registry.next_run_id(),
        triggered_by=triggered_by,
        areas_scanned=list(areas) if areas else list(AREAS),
        status="running",
    )
    registry.add_run(run)

    try:
        raw_findings = []
        for rule_fn in rules.ALL_RULES:
            raw_findings.extend(rule_fn())

        # Deduped against EVERY finding ever created for this (rule_key,
        # file_path, line_number), not just the still-open ones. Found
        # 2026-07-19 reviewing this system's own first sweep: the rule
        # engine is deterministic over unchanged source, so a dismissed
        # false positive (e.g. missing_acl_gate flagging a function that's
        # actually gated one call-hop deeper -- a pattern the regex can't
        # see) would otherwise silently re-appear as a brand-new "new"
        # finding on every later scan, since dismissing a finding doesn't
        # change the code that triggered it. That would make a human's
        # dismissal decision non-durable. Once a location has been triaged
        # to ANY status, revisiting that exact finding_id in the Hub
        # console is the right path, not a fresh duplicate.
        existing_open_keys = {
            (f.rule_key, f.file_path, f.line_number)
            for f in registry.findings.values()
        }

        by_severity = {"small": 0, "medium": 0, "large": 0}
        created = 0

        for raw in raw_findings:

            key = (raw["rule_key"], raw["file_path"], raw.get("line_number"))
            if key in existing_open_keys:
                continue

            finding = CodeAuditFinding(
                finding_id=registry.next_finding_id(),
                run_id=run.run_id,
                rule_key=raw["rule_key"],
                rule_title=raw["rule_title"],
                severity=raw["severity"],
                area=raw["area"],
                file_path=raw["file_path"],
                line_number=raw.get("line_number"),
                description=raw["description"],
                evidence=raw["evidence"],
                recommendation=raw["recommendation"],
            )

            if finding.severity == "small":
                _attempt_auto_fix(finding)
            elif finding.severity == "medium":
                _attempt_draft_fix(finding)
                finding.status = "awaiting_approval"
            else:
                finding.status = "reported"

            registry.add_finding(finding)
            existing_open_keys.add(key)
            by_severity[finding.severity] = by_severity.get(finding.severity, 0) + 1
            created += 1

        run.total_findings = created
        run.by_severity = by_severity
        run.status = "completed"
        run.completed_at = _now_iso()

    except Exception as exc:  # noqa: BLE001 -- a scan failure must never crash the Hub process
        run.status = "failed"
        run.error = str(exc)
        run.completed_at = _now_iso()

    return run


# ---------------------------------------------------------------------------
# Small-tier: real, conservative, AST-verified auto-fix. Only the
# missing_save_graph rule has a real auto-fix implemented today -- every
# other rule's findings are medium/large by design (see
# code_auditor_rules.py's own per-rule severity choices) and never reach
# this function at all.
# ---------------------------------------------------------------------------

def _attempt_auto_fix(finding: CodeAuditFinding):

    if finding.rule_key != "missing_save_graph":
        # No other rule currently has a real auto-fix generator. Downgrade
        # honestly rather than silently leaving it stuck at severity=small
        # with no fix ever applied -- a human should see this in the
        # "needs approval" queue, not a queue that implies it already
        # happened.
        finding.severity = "medium"
        finding.status = "awaiting_approval"
        return

    import os
    full_path = os.path.join(rules.repo_root(), finding.file_path.replace("/", os.sep))
    source = rules._read(full_path)  # noqa: SLF001 -- same module family, internal helper reuse

    fix = _generate_save_graph_fix(source)

    if fix is None:
        finding.severity = "medium"
        finding.status = "awaiting_approval"
        finding.description += (
            " (Auto-fix was not attempted: this file has more than one "
            "candidate mutating function, or doesn't already import both "
            "save_graph and a resolvable GRAPH_PATH -- applying a fix here "
            "safely needs a human to choose the right insertion point.)"
        )
        return

    branch_name, commit_sha, error = git_actions.create_fix_branch_and_commit(
        finding_id=finding.finding_id,
        rule_key=finding.rule_key,
        file_path=finding.file_path,
        new_content=fix,
        commit_message=(
            f"code-auditor: add missing save_graph() in {finding.file_path} "
            f"({finding.finding_id})"
        ),
    )

    if error and branch_name is None:
        # The git action itself failed outright (e.g. dirty working tree) --
        # downgrade to medium so a human sees a real, specific reason
        # rather than a finding that silently never got fixed.
        finding.severity = "medium"
        finding.status = "awaiting_approval"
        finding.proposed_fix = fix
        finding.description += f" (Auto-fix generation succeeded but the git action failed: {error})"
        return

    finding.status = "auto_fixed"
    finding.branch_name = branch_name
    finding.commit_sha = commit_sha
    finding.proposed_fix = fix
    if error:
        # Fix committed for real, but the "return to original branch"
        # cleanup step itself failed -- still a real, safe fix (on its own
        # branch, not main), just needs a human to check the repo's
        # current branch. Recorded, not hidden.
        finding.description += f" (Note: {error})"
    finding.updated_at = _now_iso()


def _generate_save_graph_fix(source):
    """Returns the real, full new file content with save_graph(GRAPH_PATH)
    inserted before every top-level return statement (or appended at the
    end of the function body if there is none) of the SINGLE mutating,
    save-less module-level function in this file -- or None if the fix
    can't be generated safely (more than one candidate, missing canonical
    imports, branching/exception paths, or invalid generated syntax)."""

    import ast

    if not source:
        return None

    if "GRAPH_PATH" not in source:
        return None
    if not ("save_graph" in source):
        return None

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None

    # Text mentions (including qualified calls and comments) do not bind the
    # bare names inserted below. Only accept explicit canonical imports.
    imports = {
        (node.module, alias.name, alias.asname or alias.name)
        for node in tree.body if isinstance(node, ast.ImportFrom) and not node.level
        for alias in node.names
    }
    if not {
        ("core.storage", "save_graph", "save_graph"),
        ("core.storage_paths", "GRAPH_PATH", "GRAPH_PATH"),
    }.issubset(imports):
        return None

    candidates = []
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        try:
            func_text = ast.unparse(node)
        except Exception:  # noqa: BLE001
            continue
        has_mutation = bool(rules._MUTATION_SIGNAL_RE.search(func_text))  # noqa: SLF001
        has_save = bool(rules._SAVE_GRAPH_CALL_RE.search(func_text))  # noqa: SLF001
        if has_mutation and not has_save:
            candidates.append(node)

    if len(candidates) != 1:
        return None

    target = candidates[0]

    # A save before a validation/authorization return changes a rejected
    # request into a write. Branching, rollback and exception paths require
    # human reasoning; generate edits only for a straight-line mutation.
    if any(isinstance(node, (ast.If, ast.For, ast.AsyncFor, ast.While,
                             ast.With, ast.AsyncWith, ast.Try, ast.Match))
           for node in ast.walk(target)):
        return None
    if any(isinstance(node, ast.Return) for node in target.body[:-1]):
        return None

    return_lines = []

    def _collect_top_level_returns(body):
        for stmt in body:
            if isinstance(stmt, ast.Return):
                return_lines.append(stmt.lineno)
            elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                continue  # never insert inside a nested function/closure
            elif isinstance(stmt, (ast.If, ast.For, ast.While, ast.With, ast.Try)):
                for attr in ("body", "orelse", "finalbody", "handlers"):
                    sub = getattr(stmt, attr, None)
                    if not sub:
                        continue
                    if attr == "handlers":
                        for handler in sub:
                            _collect_top_level_returns(handler.body)
                    else:
                        _collect_top_level_returns(sub)

    _collect_top_level_returns(target.body)

    lines = source.split("\n")

    def _indent_of(line_no):
        raw = lines[line_no - 1]
        return raw[: len(raw) - len(raw.lstrip())]

    insertions = []  # (line_no_1_indexed, text_to_insert_before_it)

    if return_lines:
        for line_no in sorted(set(return_lines)):
            indent = _indent_of(line_no)
            insertions.append((line_no, f"{indent}save_graph(GRAPH_PATH)"))
    else:
        end_line = target.end_lineno or target.lineno
        body_indent = "    "
        if target.body:
            first_stmt_line = target.body[0].lineno
            body_indent = _indent_of(first_stmt_line)
        insertions.append((end_line + 1, f"{body_indent}save_graph(GRAPH_PATH)"))

    # Apply insertions from bottom to top so earlier ones don't shift later
    # line numbers.
    for line_no, text in sorted(insertions, key=lambda pair: pair[0], reverse=True):
        insert_at = min(line_no - 1, len(lines))
        lines.insert(insert_at, text)

    new_source = "\n".join(lines)

    try:
        ast.parse(new_source)
    except SyntaxError:
        return None  # the generated edit doesn't even parse -- never ship it

    return new_source


# ---------------------------------------------------------------------------
# Medium-tier: draft a real proposed_fix where the same generator above can
# produce one, purely for human review -- never applied automatically.
# ---------------------------------------------------------------------------

def _attempt_draft_fix(finding: CodeAuditFinding):

    if finding.rule_key != "missing_save_graph":
        return  # the other rules (route shadowing / missing ACL / structural) have no auto-generatable patch -- the recommendation text IS the guidance

    import os
    full_path = os.path.join(rules.repo_root(), finding.file_path.replace("/", os.sep))
    source = rules._read(full_path)  # noqa: SLF001
    fix = _generate_save_graph_fix(source)
    if fix:
        finding.proposed_fix = fix


# ---------------------------------------------------------------------------
# Human review actions
# ---------------------------------------------------------------------------

def approve_medium_finding(finding_id, approved_by, note=None):
    """A human approving a medium-tier finding's drafted fix -- applies the
    SAME real git-branch-and-commit action small-tier findings already use.
    Only works when a proposed_fix was actually drafted; otherwise there's
    nothing to apply and the human should resolve this manually instead."""

    finding = registry.get_finding(finding_id)
    if not finding:
        return None, f"no finding with id '{finding_id}'"

    if finding.status != "awaiting_approval":
        return None, f"finding is '{finding.status}', not 'awaiting_approval'"

    if not finding.proposed_fix:
        return None, (
            "This finding has no auto-generated fix to apply -- review the "
            "recommendation and make the change directly, then mark this "
            "finding resolved."
        )

    branch_name, commit_sha, error = git_actions.create_fix_branch_and_commit(
        finding_id=finding.finding_id,
        rule_key=finding.rule_key,
        file_path=finding.file_path,
        new_content=finding.proposed_fix,
        commit_message=(
            f"code-auditor: {finding.rule_title} in {finding.file_path} "
            f"({finding.finding_id}, approved by {approved_by})"
        ),
    )

    if error and branch_name is None:
        return None, error

    finding.status = "approved"
    finding.branch_name = branch_name
    finding.commit_sha = commit_sha
    finding.resolved_by = approved_by
    finding.resolved_note = note
    finding.updated_at = _now_iso()

    return finding, error  # error may be a non-fatal "couldn't switch back" note


def reject_medium_finding(finding_id, rejected_by, note=None):

    finding = registry.get_finding(finding_id)
    if not finding:
        return None, f"no finding with id '{finding_id}'"

    if finding.status != "awaiting_approval":
        return None, f"finding is '{finding.status}', not 'awaiting_approval'"

    finding.status = "rejected"
    finding.resolved_by = rejected_by
    finding.resolved_note = note
    finding.updated_at = _now_iso()

    return finding, None


def mark_finding_resolved(finding_id, resolved_by, note=None):

    finding = registry.get_finding(finding_id)
    if not finding:
        return None, f"no finding with id '{finding_id}'"

    if finding.status in ("resolved", "dismissed"):
        return None, f"finding is already '{finding.status}'"

    finding.status = "resolved"
    finding.resolved_by = resolved_by
    finding.resolved_note = note
    finding.updated_at = _now_iso()

    return finding, None


def dismiss_finding(finding_id, dismissed_by, note=None):

    finding = registry.get_finding(finding_id)
    if not finding:
        return None, f"no finding with id '{finding_id}'"

    if finding.status in ("resolved", "dismissed"):
        return None, f"finding is already '{finding.status}'"

    if not note or not note.strip():
        return None, "a reason is required to dismiss a finding (e.g. why it's a false positive)"

    finding.status = "dismissed"
    finding.resolved_by = dismissed_by
    finding.resolved_note = note.strip()
    finding.updated_at = _now_iso()

    return finding, None


# ---------------------------------------------------------------------------
# Read views
# ---------------------------------------------------------------------------

def get_overview():

    findings = list(registry.findings.values())
    runs = registry.list_runs()

    open_findings = [f for f in findings if f.status not in ("resolved", "dismissed")]

    by_severity_open = {"small": 0, "medium": 0, "large": 0}
    by_area_open = {"backend": 0, "hub": 0, "frontend": 0, "extension": 0}
    for f in open_findings:
        by_severity_open[f.severity] = by_severity_open.get(f.severity, 0) + 1
        by_area_open[f.area] = by_area_open.get(f.area, 0) + 1

    return {
        "total_findings": len(findings),
        "open_findings": len(open_findings),
        "by_severity_open": by_severity_open,
        "by_area_open": by_area_open,
        "auto_fixed_count": len([f for f in findings if f.status == "auto_fixed"]),
        "awaiting_approval_count": len([f for f in findings if f.status == "awaiting_approval"]),
        "reported_large_count": len([f for f in findings if f.status == "reported"]),
        "last_run": runs[0].to_dict() if runs else None,
        "total_runs": len(runs),
        "severity_labels": SEVERITY_LABELS,
        "note": (
            "Every finding below comes from a real, deterministic static-"
            "analysis rule over real files in this repo -- not an AI "
            "judgment call. Small-tier findings are auto-fixed onto their "
            "own dedicated git branch (never merged automatically). Medium-"
            "tier findings are drafted and wait for a human to approve or "
            "reject. Large/systemic findings are never auto-fixed -- only "
            "reported, with real recommendations."
        ),
    }
