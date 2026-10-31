"""
core/appointment_scheduling_api.py -- ACL layer for
core/appointment_scheduling.py. Viewing capacity/matching is broad
(ADMIN/OPERATIONS/SALES/SERVICE/FINANCE, matching the RO Workflow Engine's
own view set). Mutating (sending a reminder, generating/revoking a
check-in link) is ADMIN/OPERATIONS/SALES/SERVICE -- either department's own
staff manage their own appointments. The public check-in read/write
functions have NO ACL wrapper -- genuinely unauthenticated, same convention
as core/approval_center_api.py.
"""

from core.permissions import ADMIN, OPERATIONS, SALES, SERVICE, FINANCE
from core.appointment_scheduling import (
    get_capacity_planning,
    suggest_assignee,
    send_appointment_reminder,
    get_reminder_history,
    generate_checkin_link,
    get_checkin_link_status,
    revoke_checkin_link,
)

_VIEW_ROLES = (ADMIN, OPERATIONS, SALES, SERVICE, FINANCE)
_MUTATE_ROLES = (ADMIN, OPERATIONS, SALES, SERVICE)


def _denied():
    return {"error": "You don't have access to Appointment Scheduling"}


def get_capacity_planning_api(role, department, date=None):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_capacity_planning(department, date=date)


def suggest_assignee_api(role, department, date=None):
    if role not in _VIEW_ROLES:
        return _denied()
    return suggest_assignee(department, date=date)


def send_appointment_reminder_api(role, sent_by, appointment_id, channel):
    if role not in _MUTATE_ROLES:
        return _denied()
    return send_appointment_reminder(appointment_id, channel, sent_by)


def get_reminder_history_api(role, appointment_id):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_reminder_history(appointment_id)


def generate_checkin_link_api(role, created_by, appointment_id):
    if role not in _MUTATE_ROLES:
        return _denied()
    return generate_checkin_link(appointment_id, created_by)


def get_checkin_link_status_api(role, appointment_id):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_checkin_link_status(appointment_id)


def revoke_checkin_link_api(role, revoked_by, appointment_id):
    if role not in _MUTATE_ROLES:
        return _denied()
    return revoke_checkin_link(appointment_id, revoked_by)
