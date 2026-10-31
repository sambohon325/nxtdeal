"""Workflow Automation router -- Administration Control Center's "Workflow
Automation" Top Menu item (core/workflow_automation.py). A real,
ADMIN-configurable "if this real condition, then this real action" rule
engine, platform-wide -- distinct from core/bot_tasks.py's per-employee
suggested-task layer and core/compliance.py's point-in-time mutation gate.

Rule evaluation is ON-DEMAND (evaluate_rules(), called via "Run Rules Now"
or implicitly on every dashboard fetch), NOT a third live background
scheduler -- see that module's own docstring for the full reasoning.

Extracted verbatim out of api/app.py (CAF-00120, god_file_app_py -- splitting
the 14,000+-line monolith into domain-scoped FastAPI routers). Behavior is
unchanged from the original inline routes -- same paths, same request/response
shapes, same auth flow. Static /automation/* and /automation-rules paths
registered before the dynamic /automation-rules/{rule_id}* paths, matching
the original file's own route-shadowing-avoidance ordering.

ADMIN/OPERATIONS-only throughout, matching this whole department's
established gate.
"""

from fastapi import APIRouter, Header
from pydantic import BaseModel

from api.deps import _authenticate

from core.workflow_automation_api import (
    get_automation_dashboard_api,
    get_automation_catalog_api,
    list_rules_api as list_automation_rules_api,
    create_rule_api as create_automation_rule_api,
    get_rule_api as get_automation_rule_api,
    set_rule_active_api as set_automation_rule_active_api,
    update_rule_api as update_automation_rule_api,
    delete_rule_api as delete_automation_rule_api,
    list_executions_api as list_automation_executions_api,
    run_rules_now_api,
)


router = APIRouter()


class CreateAutomationRuleRequest(BaseModel):

    name: str
    trigger_type: str
    trigger_params: dict = {}
    action_type: str
    action_params: dict = {}
    description: str = ""


class UpdateAutomationRuleRequest(BaseModel):

    name: str = None
    description: str = None
    trigger_params: dict = None
    action_params: dict = None


class SetAutomationRuleActiveRequest(BaseModel):

    is_active: bool


@router.get("/automation/dashboard")
def automation_dashboard_route(run_now: bool = True, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_automation_dashboard_api(payload["role"], run_now=run_now)


@router.get("/automation/catalog")
def automation_catalog_route(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_automation_catalog_api(payload["role"])


@router.post("/automation/run-now")
def automation_run_now_route(rule_id: str = None, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return run_rules_now_api(payload["role"], rule_id=rule_id)


@router.get("/automation-rules")
def list_automation_rules_route(active_only: bool = False, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_automation_rules_api(payload["role"], active_only=active_only)


@router.post("/automation-rules")
def create_automation_rule_route(request: CreateAutomationRuleRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return create_automation_rule_api(
        payload["role"], payload["employee_id"], request.name, request.trigger_type,
        request.trigger_params, request.action_type, request.action_params,
        description=request.description,
    )


@router.get("/automation-rules/{rule_id}")
def get_automation_rule_route(rule_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_automation_rule_api(payload["role"], rule_id)


@router.post("/automation-rules/{rule_id}/active")
def set_automation_rule_active_route(rule_id: str, request: SetAutomationRuleActiveRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return set_automation_rule_active_api(payload["role"], payload["employee_id"], rule_id, request.is_active)


@router.post("/automation-rules/{rule_id}/update")
def update_automation_rule_route(rule_id: str, request: UpdateAutomationRuleRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return update_automation_rule_api(
        payload["role"], payload["employee_id"], rule_id,
        name=request.name, description=request.description,
        trigger_params=request.trigger_params, action_params=request.action_params,
    )


@router.delete("/automation-rules/{rule_id}")
def delete_automation_rule_route(rule_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return delete_automation_rule_api(payload["role"], rule_id)


@router.post("/automation-rules/{rule_id}/run-now")
def run_single_automation_rule_route(rule_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return run_rules_now_api(payload["role"], rule_id=rule_id)


@router.get("/automation-executions")
def list_automation_executions_route(rule_id: str = None, limit: int = 100, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_automation_executions_api(payload["role"], rule_id=rule_id, limit=limit)
