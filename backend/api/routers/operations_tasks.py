"""Operations: Universal Operations Work Queue routes, extracted from
api/app.py (CAF-00120, god_file_app_py -- splitting the monolithic app.py
into per-domain routers).

Sam's spec: "Assign Owner, SLA Tracking with auto-escalation, Bulk Actions,
Workflow Actions." A real first-class OperationsTask entity (open ->
in_progress -> closed), with SLA fields (hours_open/is_overdue) computed
live on every read/list, same "compute live" convention as VehicleHold's
expires_at. See core/operations_tasks.py's module docstring for the full
design rationale, including why "auto-escalation" here is a human-triggered
action (escalate_task) rather than a background job -- no scheduler
infrastructure exists for that beyond the two narrow precedents
(bot_scheduler/compliance_scheduler) this codebase already has, and a third
was judged out of scope for one autonomous slice.

Static paths (/catalog, /stats, /sync, /bulk/*) are registered before the
dynamic /{task_id} path to avoid Starlette route-shadowing, same precedent
as /vehicle-lifecycle/* -- order preserved exactly as it was in app.py.
"""

from fastapi import APIRouter, Header
from pydantic import BaseModel

from api.deps import _authenticate

from core.operations_tasks_api import (
    get_catalog_api as get_operations_task_catalog_api,
    create_task_api as create_operations_task_api,
    get_task_api as get_operations_task_api,
    update_task_api as update_operations_task_api,
    close_task_api as close_operations_task_api,
    escalate_task_api as escalate_operations_task_api,
    list_tasks_api as list_operations_tasks_api,
    get_stats_api as get_operations_tasks_stats_api,
    bulk_assign_api as bulk_assign_operations_tasks_api,
    bulk_close_api as bulk_close_operations_tasks_api,
    bulk_reprioritize_api as bulk_reprioritize_operations_tasks_api,
    sync_derived_tasks_api as sync_operations_tasks_api,
)

router = APIRouter()


class CreateOperationsTaskRequest(BaseModel):

    task_type: str
    detail: str = ""
    priority: str = "normal"
    owner_bucket: str = "Unassigned"
    assigned_to: str | None = None
    linked_entity_id: str | None = None


class UpdateOperationsTaskRequest(BaseModel):

    status: str | None = None
    priority: str | None = None
    owner_bucket: str | None = None
    assigned_to: str | None = None


class CloseOperationsTaskRequest(BaseModel):

    resolution_notes: str = ""


class EscalateOperationsTaskRequest(BaseModel):

    notes: str = ""


class BulkAssignOperationsTasksRequest(BaseModel):

    task_ids: list[str]
    assigned_to: str | None = None
    owner_bucket: str


class BulkCloseOperationsTasksRequest(BaseModel):

    task_ids: list[str]
    resolution_notes: str = ""


class BulkReprioritizeOperationsTasksRequest(BaseModel):

    task_ids: list[str]
    priority: str


@router.get("/operations-tasks/catalog")
def operations_tasks_catalog():
    """Open, unauthenticated vocabulary lookup -- same treatment as
    /vehicle-lifecycle/catalog -- task types/statuses/priorities/owner buckets
    aren't sensitive."""

    return get_operations_task_catalog_api()


@router.get("/operations-tasks/stats")
def operations_tasks_stats(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_operations_tasks_stats_api(payload["role"])


@router.post("/operations-tasks/sync")
def operations_tasks_sync(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return sync_operations_tasks_api(payload["role"])


@router.post("/operations-tasks/bulk/assign")
def operations_tasks_bulk_assign(request: BulkAssignOperationsTasksRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return bulk_assign_operations_tasks_api(payload["role"], payload["employee_id"], request.task_ids, request.assigned_to, request.owner_bucket)


@router.post("/operations-tasks/bulk/close")
def operations_tasks_bulk_close(request: BulkCloseOperationsTasksRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return bulk_close_operations_tasks_api(payload["role"], payload["employee_id"], request.task_ids, resolution_notes=request.resolution_notes)


@router.post("/operations-tasks/bulk/reprioritize")
def operations_tasks_bulk_reprioritize(request: BulkReprioritizeOperationsTasksRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return bulk_reprioritize_operations_tasks_api(payload["role"], payload["employee_id"], request.task_ids, request.priority)


@router.get("/operations-tasks")
def operations_tasks_list(status: str = None, owner_bucket: str = None, assigned_to: str = None,
                           priority: str = None, overdue_only: bool = False, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_operations_tasks_api(payload["role"], status=status, owner_bucket=owner_bucket,
                                      assigned_to=assigned_to, priority=priority, overdue_only=overdue_only)


@router.post("/operations-tasks")
def operations_tasks_create(request: CreateOperationsTaskRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return create_operations_task_api(
        payload["role"], payload["employee_id"], request.task_type, request.detail,
        priority=request.priority, owner_bucket=request.owner_bucket,
        assigned_to=request.assigned_to, linked_entity_id=request.linked_entity_id,
    )


@router.get("/operations-tasks/{task_id}")
def operations_tasks_get(task_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_operations_task_api(payload["role"], task_id)


@router.post("/operations-tasks/{task_id}/update")
def operations_tasks_update(task_id: str, request: UpdateOperationsTaskRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return update_operations_task_api(
        payload["role"], payload["employee_id"], task_id,
        status=request.status, priority=request.priority,
        owner_bucket=request.owner_bucket, assigned_to=request.assigned_to,
    )


@router.post("/operations-tasks/{task_id}/close")
def operations_tasks_close(task_id: str, request: CloseOperationsTaskRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return close_operations_task_api(payload["role"], payload["employee_id"], task_id, resolution_notes=request.resolution_notes)


@router.post("/operations-tasks/{task_id}/escalate")
def operations_tasks_escalate(task_id: str, request: EscalateOperationsTaskRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return escalate_operations_task_api(payload["role"], payload["employee_id"], task_id, notes=request.notes)
