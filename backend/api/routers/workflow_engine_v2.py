"""
CAF-00120 router extraction for core/workflow_engine_v2.py -- the richer "real workflow
engine" (Purpose/Steps/Owners/Automation-Tier/AI-State-Machine) built alongside, not in
place of, the existing generic v1 workflow_tracking system every other department's
job-workflow buttons still use. Started as an Operations-only pilot; now also covers
Sales (Prospecting/Engagement/Deals/Finance/Retention) -- each workflow's department is
derived from its own key prefix ("operations."/"sales."), so this router itself needed
no changes to support a second department.

Every route here lives under a distinct "/workflows-v2" prefix specifically to avoid
colliding with (or shadowing) the pre-existing v1 routes already registered directly on
`app` at "/workflows", "/workflows/catalog", "/workflows/start",
"/workflows/{instance_id}/advance", "/workflows/{instance_id}/cancel", and
"/workflows/tab-data" -- confirmed via a direct grep of api/app.py before choosing this
prefix, not assumed.

Same static-routes-before-dynamic-routes ordering discipline every other router in this
directory follows (api/routers/operations_tasks.py's own docstring is the clearest
precedent): /workflows-v2/catalog, /workflows-v2/dashboard, /workflows-v2/stalled, and the
bare /workflows-v2 list route are all registered before the dynamic
/workflows-v2/{instance_id}... routes at the bottom of this file.
"""

from typing import Optional

from fastapi import APIRouter, Header
from pydantic import BaseModel

from api.deps import _authenticate
from core.workflow_engine_v2_api import (
    get_catalog_v2_api,
    get_workflow_def_v2_api,
    get_dashboard_v2_api,
    get_stalled_instances_v2_api,
    list_instances_v2_api,
    get_instance_v2_api,
    get_instance_ai_state_api,
    start_workflow_instance_v2_api,
    advance_step_api,
    add_step_task_api,
    complete_step_task_api,
    add_step_evidence_api,
    add_step_comment_api,
    block_step_api,
    unblock_step_api,
    request_step_approval_api,
    decide_step_approval_api,
    escalate_instance_api,
    resolve_escalation_api,
    force_close_instance_api,
)

router = APIRouter()


class StartWorkflowInstanceV2Request(BaseModel):
    workflow_key: str
    linked_entity_id: Optional[str] = None
    notes: Optional[str] = None


class AdvanceStepRequest(BaseModel):
    notes: Optional[str] = None


class AddStepTaskRequest(BaseModel):
    step_key: str
    description: str
    assigned_to: Optional[str] = None


class CompleteStepTaskRequest(BaseModel):
    step_key: str
    task_id: str


class AddStepEvidenceRequest(BaseModel):
    step_key: str
    description: str
    url: Optional[str] = None


class AddStepCommentRequest(BaseModel):
    step_key: str
    text: str


class BlockStepRequest(BaseModel):
    step_key: str
    reason: str


class UnblockStepRequest(BaseModel):
    step_key: str
    notes: Optional[str] = None


class RequestStepApprovalRequest(BaseModel):
    step_key: str
    note: Optional[str] = None


class DecideStepApprovalRequest(BaseModel):
    step_key: str
    approval_id: str
    approved: bool
    note: Optional[str] = None


class EscalateInstanceRequest(BaseModel):
    reason: str


class ResolveEscalationRequest(BaseModel):
    notes: Optional[str] = None


class ForceCloseInstanceRequest(BaseModel):
    reason: str


# --- Static / catalog routes (registered before any dynamic {instance_id} route) ---

@router.get("/workflows-v2/catalog")
def workflows_v2_catalog(authorization: str = Header(None)):
    payload, error = _authenticate(authorization)
    if error:
        return error
    return get_catalog_v2_api(payload["role"])


@router.get("/workflows-v2/catalog/{workflow_key}")
def workflows_v2_catalog_detail(workflow_key: str, authorization: str = Header(None)):
    payload, error = _authenticate(authorization)
    if error:
        return error
    return get_workflow_def_v2_api(payload["role"], workflow_key)


@router.get("/workflows-v2/dashboard")
def workflows_v2_dashboard(department: str = None, authorization: str = Header(None)):
    payload, error = _authenticate(authorization)
    if error:
        return error
    return get_dashboard_v2_api(payload["role"], department=department)


@router.get("/workflows-v2/stalled")
def workflows_v2_stalled(department: str = None, authorization: str = Header(None)):
    payload, error = _authenticate(authorization)
    if error:
        return error
    return get_stalled_instances_v2_api(payload["role"], department=department)


@router.get("/workflows-v2")
def workflows_v2_list(
    department: str = None,
    workflow_key: str = None,
    status: str = None,
    category: str = None,
    linked_entity_id: str = None,
    limit: int = 100,
    authorization: str = Header(None),
):
    payload, error = _authenticate(authorization)
    if error:
        return error
    return list_instances_v2_api(
        payload["role"],
        department=department,
        workflow_key=workflow_key,
        status=status,
        category=category,
        linked_entity_id=linked_entity_id,
        limit=limit,
    )


@router.post("/workflows-v2/start")
def workflows_v2_start(body: StartWorkflowInstanceV2Request, authorization: str = Header(None)):
    payload, error = _authenticate(authorization)
    if error:
        return error
    return start_workflow_instance_v2_api(
        payload["role"],
        payload["employee_id"],
        body.workflow_key,
        linked_entity_id=body.linked_entity_id,
        notes=body.notes,
    )


# --- Dynamic /{instance_id}... routes ---

@router.get("/workflows-v2/{instance_id}")
def workflows_v2_detail(instance_id: str, authorization: str = Header(None)):
    payload, error = _authenticate(authorization)
    if error:
        return error
    return get_instance_v2_api(payload["role"], instance_id)


@router.get("/workflows-v2/{instance_id}/ai-state")
def workflows_v2_ai_state(instance_id: str, authorization: str = Header(None)):
    payload, error = _authenticate(authorization)
    if error:
        return error
    return get_instance_ai_state_api(payload["role"], instance_id)


@router.post("/workflows-v2/{instance_id}/advance")
def workflows_v2_advance(instance_id: str, body: AdvanceStepRequest, authorization: str = Header(None)):
    payload, error = _authenticate(authorization)
    if error:
        return error
    return advance_step_api(payload["role"], payload["employee_id"], instance_id, notes=body.notes)


@router.post("/workflows-v2/{instance_id}/tasks")
def workflows_v2_add_task(instance_id: str, body: AddStepTaskRequest, authorization: str = Header(None)):
    payload, error = _authenticate(authorization)
    if error:
        return error
    return add_step_task_api(
        payload["role"],
        payload["employee_id"],
        instance_id,
        body.step_key,
        body.description,
        assigned_to=body.assigned_to,
    )


@router.post("/workflows-v2/{instance_id}/tasks/complete")
def workflows_v2_complete_task(instance_id: str, body: CompleteStepTaskRequest, authorization: str = Header(None)):
    payload, error = _authenticate(authorization)
    if error:
        return error
    return complete_step_task_api(
        payload["role"], payload["employee_id"], instance_id, body.step_key, body.task_id
    )


@router.post("/workflows-v2/{instance_id}/evidence")
def workflows_v2_add_evidence(instance_id: str, body: AddStepEvidenceRequest, authorization: str = Header(None)):
    payload, error = _authenticate(authorization)
    if error:
        return error
    return add_step_evidence_api(
        payload["role"],
        payload["employee_id"],
        instance_id,
        body.step_key,
        body.description,
        url=body.url,
    )


@router.post("/workflows-v2/{instance_id}/comments")
def workflows_v2_add_comment(instance_id: str, body: AddStepCommentRequest, authorization: str = Header(None)):
    payload, error = _authenticate(authorization)
    if error:
        return error
    return add_step_comment_api(
        payload["role"], payload["employee_id"], instance_id, body.step_key, body.text
    )


@router.post("/workflows-v2/{instance_id}/block")
def workflows_v2_block_step(instance_id: str, body: BlockStepRequest, authorization: str = Header(None)):
    payload, error = _authenticate(authorization)
    if error:
        return error
    return block_step_api(
        payload["role"], payload["employee_id"], instance_id, body.step_key, body.reason
    )


@router.post("/workflows-v2/{instance_id}/unblock")
def workflows_v2_unblock_step(instance_id: str, body: UnblockStepRequest, authorization: str = Header(None)):
    payload, error = _authenticate(authorization)
    if error:
        return error
    return unblock_step_api(
        payload["role"], payload["employee_id"], instance_id, body.step_key, notes=body.notes
    )


@router.post("/workflows-v2/{instance_id}/approvals/request")
def workflows_v2_request_approval(instance_id: str, body: RequestStepApprovalRequest, authorization: str = Header(None)):
    payload, error = _authenticate(authorization)
    if error:
        return error
    return request_step_approval_api(
        payload["role"], payload["employee_id"], instance_id, body.step_key, note=body.note
    )


@router.post("/workflows-v2/{instance_id}/approvals/decide")
def workflows_v2_decide_approval(instance_id: str, body: DecideStepApprovalRequest, authorization: str = Header(None)):
    payload, error = _authenticate(authorization)
    if error:
        return error
    return decide_step_approval_api(
        payload["role"],
        payload["employee_id"],
        instance_id,
        body.step_key,
        body.approval_id,
        approved=body.approved,
        note=body.note,
    )


@router.post("/workflows-v2/{instance_id}/escalate")
def workflows_v2_escalate(instance_id: str, body: EscalateInstanceRequest, authorization: str = Header(None)):
    payload, error = _authenticate(authorization)
    if error:
        return error
    return escalate_instance_api(payload["role"], payload["employee_id"], instance_id, body.reason)


@router.post("/workflows-v2/{instance_id}/resolve-escalation")
def workflows_v2_resolve_escalation(instance_id: str, body: ResolveEscalationRequest, authorization: str = Header(None)):
    payload, error = _authenticate(authorization)
    if error:
        return error
    return resolve_escalation_api(
        payload["role"], payload["employee_id"], instance_id, notes=body.notes
    )


@router.post("/workflows-v2/{instance_id}/force-close")
def workflows_v2_force_close(instance_id: str, body: ForceCloseInstanceRequest, authorization: str = Header(None)):
    payload, error = _authenticate(authorization)
    if error:
        return error
    return force_close_instance_api(
        payload["role"], payload["employee_id"], instance_id, body.reason
    )
