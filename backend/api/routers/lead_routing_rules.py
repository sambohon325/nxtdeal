"""
Leads Configuration router (Bumper parity: Distribution Configurations) --
core/lead_routing_rules.py. Named, admin-configurable lead-distribution rules
(match by source/geography -> route to a team via round-robin / least-busy / a
specific rep, with optional ADF/HTTP endpoint config). On-demand evaluation via
route_lead(); no background scheduler, same posture as workflow automation.

Static /lead-routing/* paths and the collection /lead-routing-rules are registered
before the dynamic /lead-routing-rules/{rule_id}* paths to avoid route shadowing.
Managing rules is ADMIN/OPERATIONS; routing/preview are open to any authed role.
"""

from fastapi import APIRouter, Header
from pydantic import BaseModel

from api.deps import _authenticate

from core.lead_routing_rules_api import (
    get_routing_config_api,
    list_routing_rules_api,
    get_routing_rule_api,
    create_routing_rule_api,
    update_routing_rule_api,
    set_routing_rule_active_api,
    delete_routing_rule_api,
    preview_route_api,
    route_lead_api,
)


router = APIRouter()


class CreateRoutingRuleRequest(BaseModel):

    name: str
    strategy: str
    target_department: str | None = None
    target_employee_id: str | None = None
    match_sources: list = []
    match_states: list = []
    match_cities: list = []
    endpoint: dict | None = None
    description: str = ""
    priority: int = 100


class UpdateRoutingRuleRequest(BaseModel):

    patch: dict = {}


class SetRoutingRuleActiveRequest(BaseModel):

    active: bool


class PreviewRouteRequest(BaseModel):

    lead_attrs: dict = {}


class RouteLeadRequest(BaseModel):

    lead_id: str


@router.get("/lead-routing/config")
def lead_routing_config_route(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_routing_config_api(payload["role"])


@router.post("/lead-routing/preview")
def lead_routing_preview_route(request: PreviewRouteRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return preview_route_api(payload["role"], request.lead_attrs)


@router.post("/lead-routing/route")
def lead_routing_route_lead(request: RouteLeadRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return route_lead_api(payload["role"], payload["employee_id"], request.lead_id)


@router.get("/lead-routing-rules")
def list_routing_rules_route(active_only: bool = False, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_routing_rules_api(payload["role"], active_only=active_only)


@router.post("/lead-routing-rules")
def create_routing_rule_route(request: CreateRoutingRuleRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return create_routing_rule_api(
        payload["role"], payload["employee_id"], request.name, request.strategy,
        target_department=request.target_department or "",
        target_employee_id=request.target_employee_id,
        match_sources=request.match_sources, match_states=request.match_states,
        match_cities=request.match_cities, endpoint=request.endpoint,
        description=request.description, priority=request.priority,
    )


@router.get("/lead-routing-rules/{rule_id}")
def get_routing_rule_route(rule_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_routing_rule_api(payload["role"], rule_id)


@router.post("/lead-routing-rules/{rule_id}/update")
def update_routing_rule_route(rule_id: str, request: UpdateRoutingRuleRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return update_routing_rule_api(payload["role"], payload["employee_id"], rule_id, request.patch)


@router.post("/lead-routing-rules/{rule_id}/active")
def set_routing_rule_active_route(rule_id: str, request: SetRoutingRuleActiveRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return set_routing_rule_active_api(payload["role"], payload["employee_id"], rule_id, request.active)


@router.delete("/lead-routing-rules/{rule_id}")
def delete_routing_rule_route(rule_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return delete_routing_rule_api(payload["role"], payload["employee_id"], rule_id)
