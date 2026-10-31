"""Success Center router -- NXTDeal-INTERNAL client-success / account-management
platform over a portfolio of dealer accounts (see core/success_center.py's own
module docstring for the full "why a new dealer entity, not a dealership
department" reasoning and the graph-native linked-entity model).

Follows api/routers/communications_hub.py's / api/routers/customer_journey.py's
own established pattern exactly: a self-contained api/routers/<domain>.py module
with its own APIRouter(), importing the shared _authenticate helper from
api/deps.py.
"""

from fastapi import APIRouter, Header
from pydantic import BaseModel

from api.deps import _authenticate

from core.success_center_api import (
    add_initiative_api,
    add_objective_api,
    add_recommendation_api,
    create_qbr_api,
    generate_qbr_insights_api,
    get_success_overview_api,
    list_dealers_api,
    resolve_recommendation_api,
)


router = APIRouter()


class CreateQBRRequest(BaseModel):

    period: str
    notes: str = ""


class AddObjectiveRequest(BaseModel):

    title: str
    target: str = ""


class AddInitiativeRequest(BaseModel):

    title: str
    status: str = "planned"


class AddRecommendationRequest(BaseModel):

    text: str
    priority: str = "medium"


@router.get("/success-center/dealers")
def success_center_dealers_route(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_dealers_api(payload["role"])


@router.get("/success-center/dealer/{dealer_id}")
def success_center_overview_route(dealer_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_success_overview_api(payload["role"], dealer_id)


@router.post("/success-center/dealer/{dealer_id}/qbr")
def success_center_create_qbr_route(
    dealer_id: str, request: CreateQBRRequest, authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return create_qbr_api(payload["role"], dealer_id, request.period, notes=request.notes)


@router.post("/success-center/dealer/{dealer_id}/objective")
def success_center_add_objective_route(
    dealer_id: str, request: AddObjectiveRequest, authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return add_objective_api(payload["role"], dealer_id, request.title, target=request.target)


@router.post("/success-center/dealer/{dealer_id}/initiative")
def success_center_add_initiative_route(
    dealer_id: str, request: AddInitiativeRequest, authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return add_initiative_api(payload["role"], dealer_id, request.title, status=request.status)


@router.post("/success-center/dealer/{dealer_id}/recommendation")
def success_center_add_recommendation_route(
    dealer_id: str, request: AddRecommendationRequest, authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return add_recommendation_api(payload["role"], dealer_id, request.text, priority=request.priority)


@router.post("/success-center/dealer/{dealer_id}/recommendation/{rec_id}/resolve")
def success_center_resolve_recommendation_route(
    dealer_id: str, rec_id: str, authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return resolve_recommendation_api(
        payload["role"], dealer_id, rec_id, resolved_by=payload["employee_id"]
    )


@router.post("/success-center/dealer/{dealer_id}/qbr-insights")
def success_center_qbr_insights_route(dealer_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return generate_qbr_insights_api(payload["role"], dealer_id)
