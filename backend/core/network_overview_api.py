"""
core/network_overview_api.py -- ACL layer backing the dedicated Network
Overview/Opportunities board's own on-demand actions (core/
network_opportunity_value.py). Reuses the exact same NETWORK_ROLES tier
(ADMIN/OPERATIONS/FINANCE) core/network_api.py already established for every
other Network route -- not a new/different tier, just a consistent top-level
check for a clean single error message before composing, same precedent
core/readiness_overview_api.py/core/business_health_api.py already set for
their own dedicated boards even though some/most of what they compose
already self-gates too.
"""

from core.permissions import ADMIN, OPERATIONS, FINANCE
from core.network_opportunity_value import (
    get_dollar_denominated_gaps,
    get_department_dollar_opportunities,
    get_total_identified_opportunity,
    get_largest_opportunities,
    generate_executive_summary,
)

NETWORK_ROLES = (ADMIN, OPERATIONS, FINANCE)

_FORBIDDEN = {
    "error": "You don't have access to the network with your current role -- Admin, "
    "Operations, or Finance can open it."
}


def get_dollar_gaps_api(role):
    if role not in NETWORK_ROLES:
        return _FORBIDDEN
    return get_dollar_denominated_gaps(role)


def get_department_dollar_opportunities_api(role):
    if role not in NETWORK_ROLES:
        return _FORBIDDEN
    return get_department_dollar_opportunities(role)


def get_total_identified_opportunity_api(role):
    if role not in NETWORK_ROLES:
        return _FORBIDDEN
    return get_total_identified_opportunity(role)


def get_largest_opportunities_api(role, limit=5):
    if role not in NETWORK_ROLES:
        return _FORBIDDEN
    return get_largest_opportunities(role, limit=limit)


def regenerate_network_summary_api(role, polish=True):
    """On-demand regenerate action -- re-runs the real template (and,
    optionally, the isolated OpenAI polish step) fresh. No graph mutation."""

    if role not in NETWORK_ROLES:
        return _FORBIDDEN
    return generate_executive_summary(role, polish=bool(polish))
