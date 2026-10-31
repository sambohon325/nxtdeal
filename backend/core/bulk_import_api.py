"""
API layer for Bulk Import (Bumper parity, 2026-07-25). Thin wrappers over
core/bulk_import.py, same "no service indirection" convention as the other *_api.py
modules. Import is a powerful, graph-mutating action, so committing an import is gated
to MARKETING/ADMIN (the same activation-class roles that can send a campaign); parsing,
column suggestion, and the non-destructive preview are open to any authenticated role so
a rep can prepare an import for someone with permission to commit it.
"""

from core.bulk_import import (
    parse_csv,
    suggest_mapping,
    plan_import,
    run_import,
    TARGET_FIELDS,
)
from core.permissions import ADMIN, MARKETING
from core.audit import audit_log
from core.audit_storage import save_audit_log
from core.storage_paths import AUDIT_PATH


def _can_commit(role):
    return role == ADMIN or role == MARKETING


def list_import_targets_api():
    """The importable entity types and their canonical fields (drives the mapping UI)."""
    return {"targets": [{"target_type": t, "fields": f} for t, f in TARGET_FIELDS.items()]}


def analyze_csv_api(csv_text, target_type):
    """Parse the uploaded CSV and suggest a column mapping. Non-destructive; any role."""
    if not isinstance(csv_text, str) or not csv_text.strip():
        return {"error": "csv_text is empty"}
    if target_type not in TARGET_FIELDS:
        return {"error": f"target_type must be one of {list(TARGET_FIELDS)}"}
    headers, rows = parse_csv(csv_text)
    if not headers:
        return {"error": "no header row found in CSV"}
    return {
        "headers": headers,
        "row_count": len(rows),
        "suggested_mapping": suggest_mapping(headers, target_type),
        "target_fields": TARGET_FIELDS[target_type],
        "sample_rows": rows[:5],
    }


def preview_import_api(csv_text, mapping, target_type, dedupe=True):
    """Non-destructive preview of exactly what a commit would do. Any authed role."""
    if not isinstance(csv_text, str) or not csv_text.strip():
        return {"error": "csv_text is empty"}
    headers, rows = parse_csv(csv_text)
    if not headers:
        return {"error": "no header row found in CSV"}
    return plan_import(rows, mapping or {}, target_type, dedupe=dedupe)


def commit_import_api(role, employee_id, csv_text, mapping, target_type, dedupe=True):
    """Actually create the records. MARKETING/ADMIN only."""
    if not _can_commit(role):
        return {"error": "You don't have access to commit imports"}
    if not isinstance(csv_text, str) or not csv_text.strip():
        return {"error": "csv_text is empty"}
    headers, rows = parse_csv(csv_text)
    if not headers:
        return {"error": "no header row found in CSV"}

    result = run_import(rows, mapping or {}, target_type, employee_id, dedupe=dedupe)

    if isinstance(result, dict) and result.get("error") and "created_count" not in result:
        return result

    audit_log.record(
        event_type="bulk_import_committed",
        summary=(
            f"Bulk import ({target_type}) by {employee_id}: "
            f"{result['created_count']} created, {result['skipped_count']} skipped, "
            f"{result['error_count']} errored"
        ),
        entity_id=None,
        actor=employee_id,
        details={
            "target_type": target_type,
            "created_count": result["created_count"],
            "skipped_count": result["skipped_count"],
            "error_count": result["error_count"],
            "dedupe": dedupe,
        },
    )
    save_audit_log(AUDIT_PATH)
    return result
