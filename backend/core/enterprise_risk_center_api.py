"""
core/enterprise_risk_center_api.py -- ACL layer for core/enterprise_risk_center.py.
Deliberately open to every real role (ADMIN, OPERATIONS, SALES, MARKETING,
SERVICE, FINANCE), matching core/business_health_api.py's own precedent for this
same reframed Readiness department -- this is exec-layer visibility every
department head plus ADMIN/OPERATIONS would legitimately want. The individual
sub-signals composed inside core/enterprise_risk_center.py keep their OWN
already-real ACL where one exists (compliance alerts and Data Connections both
stay ADMIN/OPERATIONS-only at their own layer, core/compliance_api.py's
COMPLIANCE_ROLES / core/data_connections_api.py's CONNECTION_ROLES) -- this
module's own gate is deliberately just "is this a real role at all," not a
second, redundant restriction on top; a caller outside a sub-signal's own role
set sees that one exception type degrade to its own module's real "you don't
have access" error rather than the whole response failing.

No mutation functions exist here at all -- Sam's spec asks this dashboard to
MONITOR, not duplicate, the real resolution actions that already exist
elsewhere (compliance resolve/override, document requests, price reductions,
delivery scheduling, technician dispatch). Every exception item carries a real
`resolve` reference (department + Top Menu item_key + a plain-language hint)
pointing back to where the actual fix already lives.
"""

from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE
from core.enterprise_risk_center import get_risk_center_overview, get_risk_center_category

_ALL_ROLES = (ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE)


def _denied():
    return {"error": "You don't have access to the Enterprise Risk Center."}


def get_risk_center_overview_api(role):
    if role not in _ALL_ROLES:
        return _denied()
    return get_risk_center_overview(role)


def get_risk_center_category_api(role, category):
    if role not in _ALL_ROLES:
        return _denied()
    return get_risk_center_category(role, category)
