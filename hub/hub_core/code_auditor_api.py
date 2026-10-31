"""
NXTDeal Hub -- thin functions between hub/app.py's route handlers and
hub_core/code_auditor.py, matching backend/core/*_api.py's "validate + call the
real function + shape the response" convention. Same as every other Hub
*_api.py module, there's no per-action role system here -- hub/app.py's own
X-NXTDeal-Hub-Key gate is the whole authorization boundary for this feature
(same as every other Hub screen); "who did this" is just a plain actor
string passed straight through, same convention hub/hub_core/dealer_backups_api.py's
logged_by/hub/hub_core/dealer_onboarding_api.py's completed_by already use.
"""

from hub_core.code_auditor import (
    registry,
    run_scan as _run_scan,
    approve_medium_finding as _approve_medium_finding,
    reject_medium_finding as _reject_medium_finding,
    mark_finding_resolved as _mark_finding_resolved,
    dismiss_finding as _dismiss_finding,
    get_overview as _get_overview,
    SEVERITY_LEVELS,
    STATUS_VALUES,
    AREAS,
)
from hub_core.code_auditor_storage import (
    save_code_audit_findings,
    save_code_audit_runs,
)
from hub_core.hub_audit_api import record_and_save

CODE_AUDIT_FINDINGS_PATH = "storage/code_audit_findings.json"
CODE_AUDIT_RUNS_PATH = "storage/code_audit_runs.json"


def _save_all():
    save_code_audit_findings(CODE_AUDIT_FINDINGS_PATH)
    save_code_audit_runs(CODE_AUDIT_RUNS_PATH)


def get_code_audit_catalog_api():
    return {
        "severity_levels": list(SEVERITY_LEVELS),
        "status_values": list(STATUS_VALUES),
        "areas": list(AREAS),
    }


def get_code_audit_overview_api():
    return _get_overview()


def run_code_audit_scan_api(triggered_by="nxtdeal_staff", areas=None):

    run = _run_scan(triggered_by=triggered_by, areas=areas)

    _save_all()

    record_and_save(
        event_type="code_audit_run_completed",
        summary=(
            f"Code audit run {run.run_id} completed by {triggered_by}: "
            f"{run.total_findings} new finding(s) "
            f"(small={run.by_severity.get('small', 0)}, "
            f"medium={run.by_severity.get('medium', 0)}, "
            f"large={run.by_severity.get('large', 0)})"
        ),
        actor=triggered_by,
        details={"run_id": run.run_id, "by_severity": run.by_severity},
    )

    return run.to_dict()


def list_code_audit_findings_api(severity=None, status=None, area=None, run_id=None):

    if severity and severity not in SEVERITY_LEVELS:
        return {"error": f"invalid severity '{severity}' -- must be one of {list(SEVERITY_LEVELS)}"}

    if status and status not in STATUS_VALUES:
        return {"error": f"invalid status '{status}' -- must be one of {list(STATUS_VALUES)}"}

    if area and area not in AREAS:
        return {"error": f"invalid area '{area}' -- must be one of {list(AREAS)}"}

    findings = registry.list_findings(severity=severity, status=status, area=area, run_id=run_id)

    return {
        "findings": [f.to_dict() for f in findings],
        "total_matches": len(findings),
    }


def get_code_audit_finding_api(finding_id):

    finding = registry.get_finding(finding_id)
    if not finding:
        return {"error": f"no finding with id '{finding_id}'"}

    return finding.to_dict()


def list_code_audit_runs_api():
    return {"runs": [r.to_dict() for r in registry.list_runs()]}


def get_code_audit_run_api(run_id):

    run = registry.get_run(run_id)
    if not run:
        return {"error": f"no run with id '{run_id}'"}

    return {
        "run": run.to_dict(),
        "findings": [f.to_dict() for f in registry.list_findings(run_id=run_id)],
    }


def approve_code_audit_finding_api(finding_id, approved_by, note=None):

    finding, error = _approve_medium_finding(finding_id, approved_by, note=note)

    if finding is None:
        return {"error": error}

    _save_all()

    record_and_save(
        event_type="code_audit_finding_approved",
        summary=f"{finding.rule_title} in {finding.file_path} approved by {approved_by}",
        actor=approved_by,
        details={"finding_id": finding.finding_id, "branch_name": finding.branch_name},
    )

    result = finding.to_dict()
    if error:
        result["warning"] = error  # a non-fatal note (e.g. couldn't return to the original branch)
    return result


def reject_code_audit_finding_api(finding_id, rejected_by, note=None):

    finding, error = _reject_medium_finding(finding_id, rejected_by, note=note)

    if finding is None:
        return {"error": error}

    _save_all()

    record_and_save(
        event_type="code_audit_finding_rejected",
        summary=f"{finding.rule_title} in {finding.file_path} rejected by {rejected_by}",
        actor=rejected_by,
        details={"finding_id": finding.finding_id, "note": note},
    )

    return finding.to_dict()


def resolve_code_audit_finding_api(finding_id, resolved_by, note=None):

    finding, error = _mark_finding_resolved(finding_id, resolved_by, note=note)

    if finding is None:
        return {"error": error}

    _save_all()

    record_and_save(
        event_type="code_audit_finding_resolved",
        summary=f"{finding.rule_title} in {finding.file_path} marked resolved by {resolved_by}",
        actor=resolved_by,
        details={"finding_id": finding.finding_id, "note": note},
    )

    return finding.to_dict()


def dismiss_code_audit_finding_api(finding_id, dismissed_by, note=None):

    finding, error = _dismiss_finding(finding_id, dismissed_by, note=note)

    if finding is None:
        return {"error": error}

    _save_all()

    record_and_save(
        event_type="code_audit_finding_dismissed",
        summary=f"{finding.rule_title} in {finding.file_path} dismissed by {dismissed_by}: {note}",
        actor=dismissed_by,
        details={"finding_id": finding.finding_id, "note": note},
    )

    return finding.to_dict()
