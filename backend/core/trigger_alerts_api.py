"""
Thin ACL layer for core/trigger_alerts.py (session 84), imported directly into
api/app.py's route handlers.

Role rule: any authenticated role can read the Timeline feed (TRIGGER_ALERT is
broadly readable per core/permissions.py's ENTITY_ACCESS). Promoting/dismissing an
alert is scoped to ADMIN/MARKETING/SALES specifically -- not the narrower
MARKETING/ADMIN-only split used elsewhere in this codebase (assets/campaigns/
websites) -- because a trigger alert is explicitly a sales-facing signal as much as a
marketing one (AutoAlert/automotiveMastermind are sold as sales tools), and SALES is
exactly who needs to act on a hot alert directly rather than wait on marketing.
"""

from core.trigger_alerts import (
    run_scan,
    get_alert,
    list_alerts,
    dismiss_alert,
    promote_alert,
    ALERT_TYPES,
)
from core.permissions import ADMIN, MARKETING, SALES


def _can_act(role):
    return role in (ADMIN, MARKETING, SALES)


def _serialize(entity):
    return {"id": entity.id, **entity.attributes}


def list_alert_types_api():
    return ALERT_TYPES


def get_alert_feed_api(role, alert_type=None, status=None, target_entity_type=None):
    """Re-scans the live graph, then returns the (now up to date) feed -- see
    core/trigger_alerts.py's run_scan() docstring for why this happens on every fetch
    rather than a background scheduler."""

    run_scan()

    alerts = list_alerts(alert_type=alert_type, status=status, target_entity_type=target_entity_type)

    return [_serialize(a) for a in alerts]


def get_alert_api(role, alert_id):

    alert = get_alert(alert_id)

    if not alert:
        return {"error": "Alert not found"}

    return _serialize(alert)


def dismiss_alert_api(role, employee_id, alert_id, notes=None):

    if not _can_act(role):
        return {"error": "Only admin/marketing/sales can dismiss a trigger alert"}

    result = dismiss_alert(alert_id, employee_id, notes)

    if isinstance(result, dict) and "error" in result:
        return result

    return _serialize(result)


def promote_alert_api(role, employee_id, alert_id, assign_to_employee_id=None):

    if not _can_act(role):
        return {"error": "Only admin/marketing/sales can promote a trigger alert"}

    result = promote_alert(alert_id, employee_id, assign_to_employee_id)

    if isinstance(result, dict) and "error" in result:
        return result

    return _serialize(result)
