"""
core/ai_business_analyst_api.py -- ACL layer for core/ai_business_analyst.py.
Deliberately broad (every real role), matching core/readiness_overview_api.py/
core/business_health_api.py/core/enterprise_risk_center_api.py/
core/readiness_recommendations_api.py's own established precedent for this
whole reframed department: exec-layer, read-only visibility every department
head plus ADMIN/OPERATIONS would legitimately want to ask a question of. The
individual sub-signals composed inside (Collections/Portfolio Quality,
Marketing ROI) keep their OWN already-real narrower ACL where one exists --
this module's own gate is deliberately just "is this a real role at all,"
same convention as every other slice of this reframe.
"""

from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE
from core.ai_business_analyst import ask_business_analyst

_ALL_ROLES = (ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE)


def _denied():
    return {"error": "You don't have access to the AI Business Analyst."}


def ask_business_analyst_api(role, question, employee_id=None):
    if role not in _ALL_ROLES:
        return _denied()
    return ask_business_analyst(question, role, employee_id=employee_id)
