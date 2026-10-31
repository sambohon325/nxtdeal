"""Thin ACL layer for core/unified_communications.py's Unified Communications Hub.

Read-only, broad view -- matches core/business_health_api.py's/
core/enterprise_risk_center_api.py's own precedent for a cross-department
visibility screen: every real role can see it (this is a staff-facing view of
already-real, already-permitted contact logs, no new sensitive data exposed
beyond what each source module already allows its own department to see).
"""

from core.unified_communications import get_unified_communications_overview

VIEW_ROLES = ("ADMIN", "OPERATIONS", "SALES", "MARKETING", "SERVICE", "FINANCE")


def get_unified_communications_overview_api(role, department=None, channel=None):
    if role not in VIEW_ROLES:
        return {"error": f"Role '{role}' is not permitted to view the Unified Communications Hub."}

    return get_unified_communications_overview(role, department=department, channel=channel)
