"""
core/operations_alerts_api.py -- ACL layer for core/operations_alerts.py.
Viewing the feed is broad (every department this codebase's other Operations
modules already treat as broadly-interested gets it here too). Acknowledging
an alert creates a real OperationsTask, so it uses the exact same mutate set
core/operations_tasks_api.py already established (ADMIN/OPERATIONS/SERVICE)
rather than inventing a third variant.
"""

from core.permissions import ADMIN, OPERATIONS, SALES, SERVICE, MARKETING, FINANCE
from core.operations_alerts import get_alert_feed, get_alert_stats, acknowledge_alert

_VIEW_ROLES = (ADMIN, OPERATIONS, SALES, SERVICE, MARKETING, FINANCE)
_MUTATE_ROLES = (ADMIN, OPERATIONS, SERVICE)


def _denied():
    return {"error": "You don't have access to the Alerts nervous system"}


def get_alert_feed_api(role):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_alert_feed(role)


def get_alert_stats_api(role):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_alert_stats(role)


def acknowledge_alert_api(role, employee_id, alert_type, source_id, notes=""):
    if role not in _MUTATE_ROLES:
        return _denied()
    return acknowledge_alert(alert_type, source_id, employee_id, notes=notes)
