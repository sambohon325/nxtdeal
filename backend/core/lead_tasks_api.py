"""
Thin ACL layer for core/lead_tasks.py, imported directly into api/app.py's route
handlers -- same "no service layer indirection" convention every other `*_api.py`
module follows. Role rule matches LEAD's own entity access (core/permissions.py's
ENTITY_ACCESS[LEAD]): any of ADMIN/OPERATIONS/SALES/MARKETING can create, complete, or
list tasks -- same roles that can already see/work a Lead at all.
"""

from core.lead_tasks import create_task, complete_task, list_tasks, get_task
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING

_TASK_ROLES = (ADMIN, OPERATIONS, SALES, MARKETING)


def _serialize(entity):
    return {"id": entity.id, **entity.attributes}


def _is_error(result):
    return isinstance(result, dict) and "error" in result


def create_task_api(role, employee_id, lead_id, task_type, description, due_at, assigned_to=None):

    if role not in _TASK_ROLES:
        return {"error": "You don't have access to create tasks"}

    result = create_task(lead_id, task_type, description, due_at, employee_id, assigned_to)

    if _is_error(result):
        return result

    return _serialize(result)


def complete_task_api(role, employee_id, task_id):

    if role not in _TASK_ROLES:
        return {"error": "You don't have access to complete tasks"}

    result = complete_task(task_id, employee_id)

    if _is_error(result):
        return result

    return _serialize(result)


def list_tasks_api(role, lead_id=None, assigned_to=None, include_completed=True):

    if role not in _TASK_ROLES:
        return {"error": "You don't have access to the task list"}

    return [_serialize(t) for t in list_tasks(lead_id, assigned_to, include_completed)]
