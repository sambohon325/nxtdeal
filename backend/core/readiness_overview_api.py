"""
core/readiness_overview_api.py -- ACL layer for Readiness' rebuilt "Overview"
Top Menu item (core/readiness_overview.py), which is also the real Readiness
Heatmap capstone. Deliberately open to every real role (ADMIN, OPERATIONS,
SALES, MARKETING, SERVICE, FINANCE), matching core/business_health_api.py's/
core/enterprise_risk_center_api.py's/core/readiness_recommendations_api.py's
own established precedent for this reframed department -- this is exec-layer,
read-only visibility every department head plus ADMIN/OPERATIONS would
legitimately want. The individual sub-signals composed inside (Enterprise
Risk Center, Recommendations) keep their OWN already-real ACL where one
exists; this module's own gate is deliberately just "is this a real role at
all," same convention as every other slice of this reframe.

No mutation functions exist here except regenerate_executive_summary_api(),
which is a pure read (it recomputes and optionally re-polishes the summary --
no graph state changes) rather than a write.
"""

from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE
from core.readiness_overview import (
    get_enterprise_readiness_overview,
    get_department_heatmap,
    get_todays_risks,
    generate_executive_summary,
)

_ALL_ROLES = (ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE)


def _denied():
    return {"error": "You don't have access to the Readiness Overview."}


def get_enterprise_readiness_overview_api(role, polish_summary=True):
    if role not in _ALL_ROLES:
        return _denied()
    return get_enterprise_readiness_overview(role, polish_summary=polish_summary)


def get_department_heatmap_api(role):
    if role not in _ALL_ROLES:
        return _denied()
    return get_department_heatmap()


def regenerate_executive_summary_api(role, polish=True):
    """On-demand regenerate action -- re-runs the real template (and,
    optionally, the isolated OpenAI polish step) fresh. No graph mutation."""

    if role not in _ALL_ROLES:
        return _denied()
    return generate_executive_summary(role, polish=bool(polish))
