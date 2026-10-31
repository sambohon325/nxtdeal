"""
core/coaching_api.py -- the ACL layer for core/coaching.py (2026-07-19), matching
this codebase's "no service layer indirection" convention -- api/app.py imports
these functions directly into route handlers.

Real employee-evaluation content (Performance Reviews, Career Pathing) is gated
more narrowly than most of this session's operational business-intelligence
work: ADMIN/OPERATIONS, OR a manager-/executive-tier employee (via
core/bot_tasks.py's own infer_tier() off the CALLER's own real Employee.Title --
the same seniority-tier convention core/manager_to.py's/
core/permissions_registry.py's Approval Hierarchy already established for
tier-gated actions). No org-chart/direct-report validation exists anywhere in
this codebase (confirmed absent, same finding sessions 65/94/106/109/110
already independently made for tenure/hire-date data) -- so this is a real,
honest tier gate, not a fabricated "only YOUR manager can see this" hierarchy
check.

One deliberate exception: an employee can always view their OWN resolved
Coaching Intensity (informational, no HR-risk content) and their OWN performance
reviews, but only once a review has been explicitly marked 'shared' -- matching
core/coaching.py's own "never visible to the reviewed employee until a manager
explicitly shares it" rule at the data layer, enforced again here at the API
layer as a second, defense-in-depth check.
"""

from core.permissions import ADMIN, OPERATIONS
from core.bot_tasks import infer_tier, TIER_MANAGER, TIER_EXECUTIVE
from core.dealeros import ledger
from core.entity_types import EMPLOYEE

from core.coaching import (
    get_intensity_catalog,
    resolve_intensity,
    set_intensity_override,
    list_intensity_overrides,
    apply_intensity_to_tasks,
    create_performance_review,
    update_review_notes,
    finalize_review,
    share_review,
    discard_review,
    get_review,
    list_reviews,
    get_career_pathing_signal,
    get_career_pathing_board,
    REVIEW_STATUS_SHARED,
)

_MANAGER_TIERS = (TIER_MANAGER, TIER_EXECUTIVE)
_DENIED = {"error": "Admin/Operations role, or manager-tier employee, required."}


def _caller_tier(caller_employee_id):
    if not caller_employee_id:
        return None
    employee = ledger.get_entity(caller_employee_id)
    if not employee or employee.entity_type != EMPLOYEE:
        return None
    return infer_tier(employee.attributes.get("Title"))


def _is_manager_or_admin(role, caller_employee_id):
    if role in (ADMIN, OPERATIONS):
        return True
    return _caller_tier(caller_employee_id) in _MANAGER_TIERS


# ---------------------------------------------------------------------------
# 1. Coaching Intensity Tiers
# ---------------------------------------------------------------------------

def get_intensity_catalog_api():
    return get_intensity_catalog()


def resolve_intensity_api(role, caller_employee_id, target_employee_id=None, department=None):
    """Any employee can resolve their OWN intensity (informational, no HR
    content). Resolving someone else's requires ADMIN/OPERATIONS or a
    manager-tier caller."""

    if target_employee_id and target_employee_id != caller_employee_id:
        if not _is_manager_or_admin(role, caller_employee_id):
            return _DENIED

    employee_id = target_employee_id or caller_employee_id
    intensity, resolved_from = resolve_intensity(employee_id, department=department)
    return {"employee_id": employee_id, "intensity": intensity, "resolved_from": resolved_from}


def set_intensity_override_api(role, caller_employee_id, scope, scope_target, intensity, reason=""):
    if not _is_manager_or_admin(role, caller_employee_id):
        return _DENIED
    return set_intensity_override(scope, scope_target, intensity, caller_employee_id, reason=reason)


def list_intensity_overrides_api(role, caller_employee_id):
    if not _is_manager_or_admin(role, caller_employee_id):
        return _DENIED
    return {"overrides": list_intensity_overrides()}


def preview_intensity_api(role, caller_employee_id, target_employee_id, items, department=None):
    """A live preview of what a given intensity resolution does to a real
    already-generated task/guidance list -- used by the frontend's Intensity
    tab to show, e.g., what an Aggressive-tier employee's bot currently looks
    like, without waiting for a real fetch of that screen."""

    if target_employee_id != caller_employee_id and not _is_manager_or_admin(role, caller_employee_id):
        return _DENIED

    result, intensity, resolved_from = apply_intensity_to_tasks(
        items, target_employee_id, department=department
    )
    return {"items": result, "intensity": intensity, "resolved_from": resolved_from}


# ---------------------------------------------------------------------------
# 2. AI Performance Reviews
# ---------------------------------------------------------------------------

def create_performance_review_api(role, caller_employee_id, target_employee_id, period_label=""):
    if not _is_manager_or_admin(role, caller_employee_id):
        return _DENIED
    return create_performance_review(target_employee_id, caller_employee_id, period_label=period_label)


def update_review_notes_api(role, caller_employee_id, review_id, manager_notes):
    if not _is_manager_or_admin(role, caller_employee_id):
        return _DENIED
    return update_review_notes(review_id, manager_notes, caller_employee_id)


def finalize_review_api(role, caller_employee_id, review_id):
    if not _is_manager_or_admin(role, caller_employee_id):
        return _DENIED
    return finalize_review(review_id, caller_employee_id)


def share_review_api(role, caller_employee_id, review_id):
    if not _is_manager_or_admin(role, caller_employee_id):
        return _DENIED
    return share_review(review_id, caller_employee_id)


def discard_review_api(role, caller_employee_id, review_id):
    if not _is_manager_or_admin(role, caller_employee_id):
        return _DENIED
    return discard_review(review_id, caller_employee_id)


def get_review_api(role, caller_employee_id, review_id):
    review = get_review(review_id)
    if review is None:
        return {"error": f"Performance review '{review_id}' not found"}

    if review.get("employee_id") == caller_employee_id:
        if review.get("status") != REVIEW_STATUS_SHARED:
            return {"error": "This review has not been shared with you yet."}
        return review

    if not _is_manager_or_admin(role, caller_employee_id):
        return _DENIED

    return review


def list_reviews_api(role, caller_employee_id, employee_id=None, status=None):
    """An employee querying their own reviews only ever sees the SHARED ones
    (matching core/coaching.py's own data-layer rule) -- a manager/ADMIN/
    OPERATIONS caller sees every status for whichever employee they ask
    about."""

    if employee_id and employee_id == caller_employee_id and not _is_manager_or_admin(role, caller_employee_id):
        return {"reviews": list_reviews(employee_id=caller_employee_id, status=REVIEW_STATUS_SHARED)}

    if not _is_manager_or_admin(role, caller_employee_id):
        return _DENIED

    return {"reviews": list_reviews(employee_id=employee_id, status=status)}


# ---------------------------------------------------------------------------
# 3. AI Career Pathing
# ---------------------------------------------------------------------------

def get_career_pathing_signal_api(role, caller_employee_id, target_employee_id=None):
    """Manager/HR tool -- gated to ADMIN/OPERATIONS or manager-tier throughout,
    matching Performance Reviews' own gate (a real internal-mobility signal is
    HR-sensitive content, same risk class)."""

    if not _is_manager_or_admin(role, caller_employee_id):
        return _DENIED
    employee_id = target_employee_id or caller_employee_id
    return get_career_pathing_signal(employee_id)


def get_career_pathing_board_api(role, caller_employee_id, department=None, signal=None):
    if not _is_manager_or_admin(role, caller_employee_id):
        return _DENIED
    return get_career_pathing_board(department=department, signal=signal)
