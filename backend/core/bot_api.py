"""
core/bot_api.py — REST-facing layer for the agentic bot (2026-07-13, session 36):
per-employee task suggestions (core/bot_tasks.py), feedback that feeds the heuristic
learning loop (core/bot_learning.py), and ADMIN-only coverage management
(core/bot_coverage.py). Same "no service layer indirection" convention every other
`*_api.py` module in this codebase follows -- api/app.py imports these functions
directly into route handlers.
"""

from core.permissions import ADMIN

from core.bot_tasks import generate_tasks
from core.bot_learning import record_task_event, VALID_EVENT_TYPES
from core.bot_coverage import start_coverage, end_coverage, list_coverage
from core.screen_guidance import (
    get_screen_guidance,
    create_automation_rule_from_guidance,
    create_document_requests_from_guidance,
)


def get_my_tasks_api(employee_id, role, section):

    return {"tasks": generate_tasks(employee_id, role, section)}


def get_screen_guidance_api(role, section, employee_id=None):
    """"Help Me With This Screen" (2026-07-19) -- no separate ACL beyond passing
    the caller's own role straight through to core/enterprise_risk_center.py's
    already-real per-sub-signal gating (it degrades gracefully per item, same
    convention this whole module's other read paths already follow).
    employee_id is optional -- when supplied, real Coaching Intensity Tier
    post-processing (core/coaching.py) is applied to the result."""

    return get_screen_guidance(role, section, employee_id=employee_id)


def automate_screen_guidance_api(role, employee_id, item_key, title):
    """"Automate It" (2026-07-19) -- the real, one-click action behind a
    tier-1 guidance item. ACL enforcement lives inside
    create_automation_rule_from_guidance() itself, via the existing
    ADMIN/OPERATIONS-gated create_rule_api() it calls -- this wrapper adds
    no separate gate, matching this whole module's "no service layer
    indirection" convention."""

    return create_automation_rule_from_guidance(role, employee_id, item_key, title)


def do_it_screen_guidance_api(role, employee_id, item_key):
    """"Do It" (2026-07-19) -- the real, one-click bulk action behind the two
    guidance items with a real, safe, bulk-suitable action already built
    (a missing Title / missing Deal Jacket document request). ACL
    enforcement lives inside create_document_requests_from_guidance() itself
    -- this wrapper adds no separate gate, matching this whole module's "no
    service layer indirection" convention."""

    return create_document_requests_from_guidance(role, employee_id, item_key)


def record_feedback_api(employee_id, task_key, event_type):

    if event_type not in VALID_EVENT_TYPES:
        return {
            "error": f"Unknown event_type '{event_type}' -- must be one of {VALID_EVENT_TYPES}"
        }

    if not task_key:
        return {"error": "task_key is required"}

    record_task_event(employee_id, task_key, event_type)

    return {"success": True}


def start_coverage_api(
    admin_role, admin_id, employee_id, role, section, starts_at, ends_at, mode, note=None
):

    if admin_role != ADMIN:
        return {"error": "Admin role required to activate bot coverage"}

    return start_coverage(admin_id, employee_id, role, section, starts_at, ends_at, mode, note)


def end_coverage_api(admin_role, admin_id, coverage_id):

    if admin_role != ADMIN:
        return {"error": "Admin role required to end bot coverage"}

    return end_coverage(coverage_id, admin_id)


def list_coverage_api(admin_role, active_only=False):

    if admin_role != ADMIN:
        return {"error": "Admin role required to view bot coverage"}

    return {"coverage": list_coverage(active_only=active_only)}
