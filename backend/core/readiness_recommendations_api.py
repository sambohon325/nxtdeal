"""
core/readiness_recommendations_api.py -- ACL layer for core/readiness_recommendations.py.
Deliberately open to every real role (ADMIN, OPERATIONS, SALES, MARKETING,
SERVICE, FINANCE), matching core/business_health_api.py's and core/
enterprise_risk_center_api.py's own precedent for this same reframed Readiness
department -- this is exec-layer visibility every department head plus ADMIN/
OPERATIONS would legitimately want. The individual sub-signals composed inside
core/readiness_recommendations.py keep their OWN already-real ACL where one
exists (Collections stays ADMIN/OPERATIONS/FINANCE-gated at core/collections_api.py's
own layer via core/business_health.py's finance_health(); open compliance
issues/data-sync/etc. stay ADMIN/OPERATIONS-gated at their own layer via core/
enterprise_risk_center.py) -- this module's own gate is deliberately just "is
this a real role at all," not a second, redundant restriction on top; a caller
outside a sub-signal's own role set sees that one rule degrade to its own
module's real "you don't have access" error rather than the whole response
failing.

No mutation functions exist here at all -- same "monitor, don't duplicate the
resolution action" discipline core/enterprise_risk_center.py already
established. Every triggered recommendation carries a real `resolve` reference
pointing back to where the actual action already lives.
"""

from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE
from core.readiness_recommendations import get_recommendations_overview, get_recommendations_category

_ALL_ROLES = (ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE)


def _denied():
    return {"error": "You don't have access to Readiness Recommendations."}


def get_recommendations_overview_api(role):
    if role not in _ALL_ROLES:
        return _denied()
    return get_recommendations_overview(role)


def get_recommendations_category_api(role, category):
    if role not in _ALL_ROLES:
        return _denied()
    return get_recommendations_category(role, category)
