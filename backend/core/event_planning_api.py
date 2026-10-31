"""
Thin ACL layer for core/event_planning.py, imported directly into api/app.py's route
handlers. Same role split as core/dealership_events_api.py: any authenticated role can
view (broad EVENT_TASK access per core/permissions.py), but creating/editing/
completing a task -- and viewing the War Room's own operational detail -- is scoped to
ADMIN/MARKETING/SALES, matching this dash's established "Sales tool as much as
Marketing" precedent.
"""

from core.event_planning import (
    create_task,
    get_task,
    update_task,
    update_task_status,
    delete_task,
    list_tasks_for_event,
    get_project_management_summary,
    get_event_war_room,
    TASK_STATUSES,
)
from core.permissions import ADMIN, MARKETING, SALES


def _can_act(role):
    return role in (ADMIN, MARKETING, SALES)


def _serialize(entity):
    return {"id": entity.id, **entity.attributes}


def list_task_statuses_api():
    return list(TASK_STATUSES)


def create_task_api(role, employee_id, event_id, title, assignee_employee_id=None, due_date=None, notes=""):

    if not _can_act(role):
        return {"error": "Only admin/marketing/sales can create event planning tasks"}

    result = create_task(event_id, employee_id, title, assignee_employee_id, due_date, notes)

    if isinstance(result, dict) and "error" in result:
        return result

    return _serialize(result)


def update_task_api(role, employee_id, task_id, patch):

    if not _can_act(role):
        return {"error": "Only admin/marketing/sales can edit event planning tasks"}

    result = update_task(task_id, patch)

    if isinstance(result, dict) and "error" in result:
        return result

    return _serialize(result)


def update_task_status_api(role, employee_id, task_id, status):

    if not _can_act(role):
        return {"error": "Only admin/marketing/sales can update a task's status"}

    result = update_task_status(task_id, status)

    if isinstance(result, dict) and "error" in result:
        return result

    return _serialize(result)


def delete_task_api(role, employee_id, task_id):

    if not _can_act(role):
        return {"error": "Only admin/marketing/sales can delete an event planning task"}

    return delete_task(task_id)


def list_tasks_for_event_api(role, event_id, status=None):

    tasks = list_tasks_for_event(event_id, status)

    return [_serialize(t) for t in tasks]


def get_project_management_summary_api(role, event_id):
    return get_project_management_summary(event_id)


def get_event_war_room_api(role, event_id):
    return get_event_war_room(event_id)
