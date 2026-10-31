"""AI Kill Switch router -- security-hardening pass (2026-07-20), Task #6
"Expand AI kill switch to dealer/department/bot/workflow scope." Real,
layered, ADMIN/OPERATIONS-only emergency stops on top of
core/ai_management.py's existing per-feature switches -- see
core/ai_kill_switch.py's own module docstring for the full 4-scope design
(dealer-wide/department/bot/workflow-automation).

Follows api/routers/ai_management.py's own established pattern exactly: a
self-contained api/routers/<domain>.py module with its own APIRouter(),
importing the shared _authenticate helper from api/deps.py.
"""

from fastapi import APIRouter, Header
from pydantic import BaseModel

from api.deps import _authenticate

from core.ai_kill_switch_api import (
    get_kill_switch_overview_api,
    explain_ai_gate_api,
    set_dealer_wide_kill_switch_api,
    set_department_kill_switch_api,
    set_bot_kill_switch_api,
    set_workflow_automation_kill_switch_api,
)
from core.ai_kill_switch_network_api import (
    get_ai_kill_switch_status_network_api,
    push_ai_kill_switch_api,
)


router = APIRouter()


class SetKillSwitchRequest(BaseModel):

    active: bool
    reason: str | None = None


class HubKillSwitchPushRequest(BaseModel):

    scope: str
    active: bool
    reason: str | None = None
    department: str | None = None


@router.get("/ai-kill-switch/overview")
def ai_kill_switch_overview_route(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_kill_switch_overview_api(payload["role"])


@router.get("/ai-kill-switch/explain/{feature_key}")
def ai_kill_switch_explain_route(feature_key: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return explain_ai_gate_api(payload["role"], feature_key)


@router.post("/ai-kill-switch/dealer-wide")
def ai_kill_switch_dealer_wide_route(request: SetKillSwitchRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return set_dealer_wide_kill_switch_api(
        payload["role"], request.active, payload["employee_id"], reason=request.reason
    )


@router.post("/ai-kill-switch/department/{department}")
def ai_kill_switch_department_route(department: str, request: SetKillSwitchRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return set_department_kill_switch_api(
        payload["role"], department, request.active, payload["employee_id"], reason=request.reason
    )


@router.post("/ai-kill-switch/bot")
def ai_kill_switch_bot_route(request: SetKillSwitchRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return set_bot_kill_switch_api(
        payload["role"], request.active, payload["employee_id"], reason=request.reason
    )


@router.post("/ai-kill-switch/workflow-automation")
def ai_kill_switch_workflow_automation_route(request: SetKillSwitchRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return set_workflow_automation_kill_switch_api(
        payload["role"], request.active, payload["employee_id"], reason=request.reason
    )


# ---------------------------------------------------------------------------
# Hub<->tenant, server-to-server -- gated by DEALEROS_NETWORK_KEY (a shared
# secret), not an employee Bearer token. See core/ai_kill_switch_network_api.py's
# module docstring and hub/hub_core/dealer_ai_kill_switch.py for the full
# emergency-push design (a NXTDeal staffer triggering a real, remote AI stop
# on one reachable dealer directly from the Hub console, without needing
# that dealer's own employee credentials).
# ---------------------------------------------------------------------------


@router.get("/network/ai-kill-switch-status")
def network_ai_kill_switch_status_route(x_dealeros_network_key: str = Header(None)):
    """Called by the NXTDeal Hub (hub/hub_core/dealer_ai_kill_switch.py),
    server-to-server -- same DEALEROS_NETWORK_KEY shared secret as
    /network/anonymous-snapshot and /network/ai-management-snapshot, reused
    via core/network_snapshot_api.py's check_network_key(). A plain,
    read-only reuse of core/ai_kill_switch.py's get_kill_switch_overview()
    -- the same real 4-scope state an authenticated ADMIN/OPERATIONS
    employee sees via GET /ai-kill-switch/overview, just reachable without
    an employee session for the Hub's own incident-response console."""

    return get_ai_kill_switch_status_network_api(x_dealeros_network_key)


@router.post("/network/ai-kill-switch-push")
def network_ai_kill_switch_push_route(
    request: HubKillSwitchPushRequest, x_dealeros_network_key: str = Header(None)
):
    """Called by the NXTDeal Hub (hub/hub_core/dealer_ai_kill_switch.py),
    server-to-server -- same DEALEROS_NETWORK_KEY shared secret as the route
    above. Lets a NXTDeal staffer trigger a real emergency AI stop on this
    dealer directly from the Hub console. Reuses core/ai_kill_switch.py's
    own 4 scope-specific setters verbatim -- a network-key holder can flip
    exactly the same 4 switches a local ADMIN/OPERATIONS employee already
    can through the Bearer-token-gated routes above, nothing more. Every
    push is recorded with updated_by="hub_emergency_push"
    (core/ai_kill_switch_network_api.py's HUB_PUSH_ACTOR) so this tenant's
    own kill-switch state and audit trail always distinguish a Hub-initiated
    stop from a local admin's own action."""

    return push_ai_kill_switch_api(
        x_dealeros_network_key, request.scope, request.active,
        reason=request.reason, department=request.department,
    )
