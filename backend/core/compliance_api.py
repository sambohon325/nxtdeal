"""
ACL layer for the compliance agent (2026-07-13, session 38) -- imported directly into
api/app.py's route handlers, same "no service layer indirection" convention every other
`*_api.py` module in this codebase follows.

Role rule: alerts are visible to ADMIN/OPERATIONS (core/permissions.py's
COMPLIANCE_ALERT tier) -- the specific manager/executive notified about a given alert
can still act on it through the DM they received regardless of dashboard access, same
"read access vs. who gets notified" split ASSET/CAMPAIGN/WEBSITE already draw between
general visibility and approval routing. Overriding a block (bypassing without fixing
the underlying issue) is ADMIN-only -- narrower than resolving one, since an override
is a conscious, audited decision to let something through anyway.
"""

from core.permissions import ADMIN, OPERATIONS
from core.compliance import (
    list_alerts,
    get_alert,
    resolve_alert,
    override_alert,
    run_full_scan,
)
from core.compliance_rules import all_rules, NOT_LEGAL_ADVICE_NOTICE
from core.contracting_readiness import contracting_readiness
from core.workflow_readiness import workflow_readiness


COMPLIANCE_ROLES = (ADMIN, OPERATIONS)

_FORBIDDEN = {
    "error": "You don't have access to compliance alerts with your current role -- "
    "Admin or Operations can review them."
}


def _serialize(alert):
    return {"id": alert.id, **alert.attributes}


def list_rules_api():
    """The rule catalog itself (law/citation/category/severity/applies_to) -- open to
    any authenticated role, same "read the policy" reasoning as list_templates_api()/
    list_campaign_types_api() elsewhere in this codebase. No violations here, just what
    gets checked and why."""

    return {
        "contracting_readiness": contracting_readiness(),
        "workflow_readiness": workflow_readiness(),
        "rules": [
            {
                "id": r["id"],
                "law": r["law"],
                "citation": r["citation"],
                "category": r["category"],
                "severity": r["severity"],
                "applies_to": r["applies_to"],
            }
            for r in all_rules()
        ],
        "notice": NOT_LEGAL_ADVICE_NOTICE,
    }


def list_alerts_api(role, status=None):

    if role not in COMPLIANCE_ROLES:
        return _FORBIDDEN

    return {"alerts": [_serialize(a) for a in list_alerts(status)], "notice": NOT_LEGAL_ADVICE_NOTICE}


def get_alert_api(role, alert_id):

    if role not in COMPLIANCE_ROLES:
        return _FORBIDDEN

    alert = get_alert(alert_id)

    if not alert:
        return {"error": "Compliance alert not found"}

    return _serialize(alert)


def resolve_alert_api(role, resolved_by, alert_id, notes=None):

    if role not in COMPLIANCE_ROLES:
        return _FORBIDDEN

    result = resolve_alert(alert_id, resolved_by, notes)

    if isinstance(result, dict) and "error" in result:
        return result

    return _serialize(result)


def override_alert_api(role, overridden_by, alert_id, notes):

    if role != ADMIN:
        return {"error": "Only an admin can override a compliance block -- Operations can resolve one once it's actually fixed."}

    result = override_alert(alert_id, overridden_by, notes)

    if isinstance(result, dict) and "error" in result:
        return result

    return _serialize(result)


def run_scan_api(role):
    """Manual "run the twice-daily scan right now" trigger -- same tier as viewing
    alerts, doesn't wait for core/compliance_scheduler.py's next scheduled tick."""

    if role not in COMPLIANCE_ROLES:
        return _FORBIDDEN

    return run_full_scan()
