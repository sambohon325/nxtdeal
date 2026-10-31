"""
ACL layer for the GLBA Safeguards Rule Information Security Program tracker
(security-hardening pass, 2026-07-20, Task #11 "Add GLBA + PCI-DSS readiness
controls," half 2 of 2). Matches core/lending_compliance_api.py's "validate role +
call the real function" convention exactly.
"""

from core.permissions import ADMIN, OPERATIONS, SALES, FINANCE
from core.glba_program import (
    get_component_status,
    list_program_items,
    set_component_status,
    get_glba_readiness_summary,
)

_VIEW_ROLES = (ADMIN, OPERATIONS, SALES, FINANCE)
_COMPLIANCE_OFFICER_ROLES = (ADMIN, OPERATIONS, FINANCE)

_VIEW_FORBIDDEN = {
    "error": "You don't have access to GLBA program data with your current role -- "
             "Admin, Operations, Sales, or Finance can view it."
}
_COMPLIANCE_FORBIDDEN = {
    "error": "You don't have access to update the GLBA program with your current "
             "role -- Admin, Operations, or Finance can."
}


def get_glba_readiness_summary_api(role):

    if role not in _VIEW_ROLES:
        return _VIEW_FORBIDDEN

    return get_glba_readiness_summary()


def list_glba_program_items_api(role):

    if role not in _VIEW_ROLES:
        return _VIEW_FORBIDDEN

    return list_program_items()


def get_glba_component_status_api(role, component_key):

    if role not in _VIEW_ROLES:
        return _VIEW_FORBIDDEN

    return get_component_status(component_key)


def set_glba_component_status_api(role, component_key, status, owner_employee_id, notes, updated_by, last_reviewed_at=None):

    if role not in _COMPLIANCE_OFFICER_ROLES:
        return _COMPLIANCE_FORBIDDEN

    return set_component_status(component_key, status, owner_employee_id, notes, updated_by, last_reviewed_at)
