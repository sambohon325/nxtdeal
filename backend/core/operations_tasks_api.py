"""
core/operations_tasks_api.py -- ACL layer for core/operations_tasks.py. Viewing is
broad (the same 5-role set core/vehicle_lifecycle_api.py grants for viewing --
every department genuinely cares whether an operations ticket blocking their work
is open or closed); mutating (create/update/close/escalate/bulk actions/sync) is
narrower, ADMIN/OPERATIONS/SERVICE, matching Vehicle Lifecycle's own mutate set --
Operations is the owning department, Service does real recon/vendor work that
routinely spawns or closes these tickets.
"""

from core.permissions import ADMIN, OPERATIONS, SALES, SERVICE, MARKETING, FINANCE
from core.operations_tasks import (
    create_task, get_task, update_task, close_task, escalate_task, list_tasks, get_stats,
    bulk_assign, bulk_close, bulk_reprioritize, sync_derived_tasks,
    TASK_TYPES, STATUSES, PRIORITIES, OWNER_BUCKETS,
)

_VIEW_ROLES = (ADMIN, OPERATIONS, SALES, SERVICE, MARKETING, FINANCE)
_MUTATE_ROLES = (ADMIN, OPERATIONS, SERVICE)


def _denied():
    return {"error": "You don't have access to Operations Tasks"}


def _is_error(result):
    return isinstance(result, dict) and "error" in result


def _serialize(task):
    """Flattens a raw OperationsTask Entity ({id, entity_type, attributes})
    into a plain {id, **attributes} dict before it crosses the API boundary --
    the same _serialize() convention core/manager_to_api.py already
    established. Bug fix: every function below used to return the raw Entity
    straight through, which FastAPI's default JSON encoding serializes as
    {"id", "entity_type", "attributes": {...}} rather than a flat object --
    every field the frontend's OperationsTask type expects at the top level
    (status, priority, owner_bucket, ...) was actually one level deeper and
    came back undefined, crashing OperationsTasksBoard.tsx's task.status.replace()
    the moment any real task existed. Caught live via a real browser render,
    not the direct-Python-call smoke tests this module was originally
    "verified" with -- those never round-trip through FastAPI's JSON encoder,
    so they couldn't have caught this."""

    return {"id": task.id, **task.attributes}


def get_catalog_api():
    return {"task_types": TASK_TYPES, "statuses": STATUSES, "priorities": PRIORITIES, "owner_buckets": OWNER_BUCKETS}


def create_task_api(role, employee_id, task_type, detail, priority="normal", owner_bucket="Unassigned",
                     assigned_to=None, linked_entity_id=None):
    if role not in _MUTATE_ROLES:
        return _denied()
    result = create_task(task_type, detail, employee_id, priority=priority, owner_bucket=owner_bucket,
                          assigned_to=assigned_to, linked_entity_id=linked_entity_id)
    if _is_error(result):
        return result
    return _serialize(result)


def get_task_api(role, task_id):
    if role not in _VIEW_ROLES:
        return _denied()
    task = get_task(task_id)
    if not task:
        return {"error": "Task not found"}
    return _serialize(task)


def update_task_api(role, employee_id, task_id, status=None, priority=None, owner_bucket=None, assigned_to=None):
    if role not in _MUTATE_ROLES:
        return _denied()
    result = update_task(task_id, employee_id, status=status, priority=priority,
                          owner_bucket=owner_bucket, assigned_to=assigned_to)
    if _is_error(result):
        return result
    return _serialize(result)


def close_task_api(role, employee_id, task_id, resolution_notes=""):
    if role not in _MUTATE_ROLES:
        return _denied()
    result = close_task(task_id, employee_id, resolution_notes=resolution_notes)
    if _is_error(result):
        return result
    return _serialize(result)


def escalate_task_api(role, employee_id, task_id, notes=""):
    if role not in _MUTATE_ROLES:
        return _denied()
    result = escalate_task(task_id, employee_id, notes=notes)
    if _is_error(result):
        return result
    return _serialize(result)


def list_tasks_api(role, status=None, owner_bucket=None, assigned_to=None, priority=None, overdue_only=False):
    if role not in _VIEW_ROLES:
        return _denied()
    tasks = list_tasks(status=status, owner_bucket=owner_bucket, assigned_to=assigned_to,
                        priority=priority, overdue_only=overdue_only)
    return {"tasks": [_serialize(t) for t in tasks], "count": len(tasks)}


def get_stats_api(role):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_stats()


def bulk_assign_api(role, employee_id, task_ids, assigned_to, owner_bucket):
    if role not in _MUTATE_ROLES:
        return _denied()
    results = bulk_assign(task_ids, assigned_to, owner_bucket, employee_id)
    return {"results": [r if _is_error(r) else _serialize(r) for r in results]}


def bulk_close_api(role, employee_id, task_ids, resolution_notes=""):
    if role not in _MUTATE_ROLES:
        return _denied()
    results = bulk_close(task_ids, employee_id, resolution_notes=resolution_notes)
    return {"results": [r if _is_error(r) else _serialize(r) for r in results]}


def bulk_reprioritize_api(role, employee_id, task_ids, priority):
    if role not in _MUTATE_ROLES:
        return _denied()
    results = bulk_reprioritize(task_ids, priority, employee_id)
    return {"results": [r if _is_error(r) else _serialize(r) for r in results]}


def sync_derived_tasks_api(role):
    if role not in _MUTATE_ROLES:
        return _denied()
    return sync_derived_tasks(role)
