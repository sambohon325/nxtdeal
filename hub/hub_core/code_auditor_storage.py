"""
NXTDeal Hub -- persistence for the AI-Powered Self-Auditing Code Layer
(hub/storage/code_audit_findings.json, hub/storage/code_audit_runs.json).
Same atomic-write + truncated-JSON-recovery convention as
hub/hub_core/dealer_backups_storage.py -- two separate files (findings/runs)
rather than one combined file, since they're separately paginated/queried
in practice and this keeps each file's own recovery-on-corruption blast
radius smaller.
"""

import json
import os

from hub_core.code_auditor import registry, CodeAuditFinding, CodeAuditRun


def save_code_audit_findings(filepath):

    data = [f.to_dict() for f in registry.findings.values()]

    tmp_path = filepath + ".tmp"

    os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)

    with open(tmp_path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4)

    os.replace(tmp_path, filepath)


def load_code_audit_findings(filepath):

    try:
        with open(filepath, "r", encoding="utf-8") as file:
            raw = file.read()
    except FileNotFoundError:
        return

    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        data = _recover_partial_array(raw)
        print(
            "WARNING: hub/storage/code_audit_findings.json was corrupt or "
            "truncated; recovered {} complete record(s) and continued.".format(len(data))
        )

    for entry_data in data:
        registry.add_finding(CodeAuditFinding.from_dict(entry_data))

    registry.recover_counters()


def save_code_audit_runs(filepath):

    data = [r.to_dict() for r in registry.runs.values()]

    tmp_path = filepath + ".tmp"

    os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)

    with open(tmp_path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4)

    os.replace(tmp_path, filepath)


def load_code_audit_runs(filepath):

    try:
        with open(filepath, "r", encoding="utf-8") as file:
            raw = file.read()
    except FileNotFoundError:
        return

    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        data = _recover_partial_array(raw)
        print(
            "WARNING: hub/storage/code_audit_runs.json was corrupt or "
            "truncated; recovered {} complete record(s) and continued.".format(len(data))
        )

    for entry_data in data:
        registry.add_run(CodeAuditRun.from_dict(entry_data))

    registry.recover_counters()


def _recover_partial_array(text):
    """Mirrors hub/hub_core/dealer_integrations_storage.py's
    _recover_partial_array exactly."""

    close = text.rfind("}")

    while close != -1:

        candidate = text[:close + 1] + "]"

        try:
            recovered = json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            close = text.rfind("}", 0, close)
            continue

        if isinstance(recovered, list):
            return recovered

        return []

    return []
