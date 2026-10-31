"""
core/service_sales_handoff_api.py -- ACL layer for
core/service_sales_handoff.py. Viewing the opportunity queue/stats is broad
(ADMIN/OPERATIONS/SALES/SERVICE/FINANCE, matching the RO Workflow Engine's
own view set) -- Sales needs to see what Service is surfacing just as much
as Service does. Promoting/dismissing/flagging is deliberately open to BOTH
SERVICE (who spots the signal) and SALES (who might independently want to
claim a lead off a Service record), alongside ADMIN/OPERATIONS -- a genuine
bridge action between two departments, not a single department's own
narrower workflow.
"""

from core.permissions import ADMIN, OPERATIONS, SALES, SERVICE, FINANCE
from core.service_sales_handoff import (
    get_opportunity_queue,
    get_conversion_opportunities,
    get_ro_handoff_status,
    flag_manual_opportunity,
    promote_to_sales,
    dismiss_opportunity,
    get_handoff_stats,
)

_VIEW_ROLES = (ADMIN, OPERATIONS, SALES, SERVICE, FINANCE)
_MUTATE_ROLES = (ADMIN, OPERATIONS, SALES, SERVICE)


def _denied():
    return {"error": "You don't have access to the Service-to-Sales Handoff"}


def get_opportunity_queue_api(role, limit=50):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_opportunity_queue(limit=limit)


def get_conversion_opportunities_api(role, limit=50):
    """Phase 7: the combined queue including the equity/maturity-at-service signal."""
    if role not in _VIEW_ROLES:
        return _denied()
    return get_conversion_opportunities(limit=limit)


def get_ro_handoff_status_api(role, ro_id):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_ro_handoff_status(ro_id)


def flag_manual_opportunity_api(role, flagged_by, ro_id, notes=""):
    if role not in _MUTATE_ROLES:
        return _denied()
    return flag_manual_opportunity(ro_id, flagged_by, notes=notes)


def promote_to_sales_api(role, promoted_by, ro_id, assigned_to=None, notes="", opportunity_type=None):
    if role not in _MUTATE_ROLES:
        return _denied()
    return promote_to_sales(ro_id, promoted_by, assigned_to=assigned_to, notes=notes, opportunity_type=opportunity_type)


def dismiss_opportunity_api(role, dismissed_by, ro_id, reason="", opportunity_type=None):
    if role not in _MUTATE_ROLES:
        return _denied()
    return dismiss_opportunity(ro_id, dismissed_by, reason=reason, opportunity_type=opportunity_type)


def get_handoff_stats_api(role):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_handoff_stats()
