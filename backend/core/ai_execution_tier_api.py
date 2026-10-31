"""
Thin ACL layer for core/ai_execution_tier.py -- imported directly into
api/app.py's route handlers, same "no service layer indirection" convention
every other `*_api.py` module in this codebase follows.

Role rule: viewing the execution-tier catalog is ADMIN/OPERATIONS-only,
matching core/ai_management_api.py's own established gate for the AI
Management screen this classification layer directly extends -- which real
AI/automation surfaces require Approval Chain gating is control-plane
information, not broad department-visible reporting.
"""

from core.ai_execution_tier import (
    list_execution_tier_catalog,
    get_execution_tier_summary,
    get_execution_tier,
    EXECUTION_TIERS,
    TIER_DESCRIPTIONS,
)
from core.permissions import ADMIN, OPERATIONS

_ADMIN_ROLES = (ADMIN, OPERATIONS)
_ADMIN_ONLY_ERROR = {"error": "Admin/Operations role required."}


def get_execution_tier_overview_api(role):
    if role not in _ADMIN_ROLES:
        return _ADMIN_ONLY_ERROR
    return {
        "tiers": list(EXECUTION_TIERS),
        "tier_descriptions": TIER_DESCRIPTIONS,
        "summary": get_execution_tier_summary(),
        "catalog": list_execution_tier_catalog(),
    }


def get_execution_tier_for_feature_api(role, feature_key):
    if role not in _ADMIN_ROLES:
        return _ADMIN_ONLY_ERROR
    return {"feature_key": feature_key, **get_execution_tier(feature_key)}
