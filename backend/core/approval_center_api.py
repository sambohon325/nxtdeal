"""
core/approval_center_api.py -- ACL layer for the STAFF-facing side of
core/approval_center.py (generate/view/revoke a link). Matches the RO
Workflow Engine's own mutate set (ADMIN/OPERATIONS/SERVICE) -- generating
or revoking a customer-facing link is an operational action, same
narrower set as advancing an RO's stage. Viewing link status (not the
link's target, just whether one exists/its metadata) is broad, matching
every other RO Workflow Engine view. The public read/write functions
(get_public_approval_view/record_public_approval_decision) have NO ACL
wrapper at all -- they're genuinely unauthenticated, called directly from
api/app.py's /public/* routes, same convention as core/websites.py's
public website render.
"""

from core.permissions import ADMIN, OPERATIONS, SALES, SERVICE, FINANCE
from core.approval_center import (
    generate_approval_link,
    get_approval_link_status,
    revoke_approval_link,
)

_VIEW_ROLES = (ADMIN, OPERATIONS, SALES, SERVICE, FINANCE)
_MUTATE_ROLES = (ADMIN, OPERATIONS, SERVICE)


def _denied():
    return {"error": "You don't have access to the Approval Center"}


def generate_approval_link_api(role, ro_id, created_by):
    if role not in _MUTATE_ROLES:
        return _denied()
    return generate_approval_link(ro_id, created_by)


def get_approval_link_status_api(role, ro_id):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_approval_link_status(ro_id)


def revoke_approval_link_api(role, ro_id, revoked_by):
    if role not in _MUTATE_ROLES:
        return _denied()
    return revoke_approval_link(ro_id, revoked_by)
