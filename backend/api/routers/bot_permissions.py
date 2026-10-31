"""
api/routers/bot_permissions.py -- security-hardening pass (2026-07-20),
Task #7 "Build Bot Permission Layer." Mirrors api/routers/ai_kill_switch.py's
established structure exactly.
"""

from fastapi import APIRouter, Header
from pydantic import BaseModel

from api.deps import _authenticate
from core.bot_permissions_api import (
    list_bot_capability_catalog_api,
    get_effective_bot_capabilities_api,
    list_bot_capability_grants_api,
    list_all_bot_capability_grants_api,
    set_bot_capability_grant_api,
    revoke_bot_capability_grant_api,
)

router = APIRouter()


class SetBotCapabilityGrantRequest(BaseModel):
    capability_key: str
    scope: str
    granted: bool
    scope_target: str | None = None
    reason: str = ""


@router.get("/bot-permissions/catalog")
def bot_permissions_catalog_route(authorization: str = Header(None)):
    payload, error = _authenticate(authorization)
    if error:
        return error
    return list_bot_capability_catalog_api(payload["role"])


@router.get("/bot-permissions/effective")
def bot_permissions_effective_route(
    target_employee_id: str = None,
    department: str = None,
    authorization: str = Header(None),
):
    payload, error = _authenticate(authorization)
    if error:
        return error
    return get_effective_bot_capabilities_api(
        payload["role"], payload["employee_id"], target_employee_id, department
    )


@router.get("/bot-permissions/grants")
def bot_permissions_grants_route(
    scope: str,
    scope_target: str = None,
    authorization: str = Header(None),
):
    payload, error = _authenticate(authorization)
    if error:
        return error
    return list_bot_capability_grants_api(payload["role"], scope, scope_target)


@router.get("/bot-permissions/grants/all")
def bot_permissions_grants_all_route(authorization: str = Header(None)):
    payload, error = _authenticate(authorization)
    if error:
        return error
    return list_all_bot_capability_grants_api(payload["role"])


@router.post("/bot-permissions/grants")
def bot_permissions_set_grant_route(
    body: SetBotCapabilityGrantRequest, authorization: str = Header(None)
):
    payload, error = _authenticate(authorization)
    if error:
        return error
    return set_bot_capability_grant_api(
        payload["role"],
        payload["employee_id"],
        body.capability_key,
        body.scope,
        body.granted,
        scope_target=body.scope_target,
        reason=body.reason,
    )


@router.post("/bot-permissions/grants/{grant_id}/revoke")
def bot_permissions_revoke_grant_route(grant_id: str, authorization: str = Header(None)):
    payload, error = _authenticate(authorization)
    if error:
        return error
    return revoke_bot_capability_grant_api(payload["role"], payload["employee_id"], grant_id)
