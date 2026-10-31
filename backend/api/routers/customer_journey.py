"""Customer Journey Engine router -- slice 1 (2026-07-22): core/
customer_journey.py's graph-native lifecycle stage tracking (Awareness ->
Lead -> Appointment -> Sale -> Service -> Loyalty -> Repeat), stored directly
as attributes on the Customer entity. See that module's own docstring for the
"why graph-native, not a separate store" reasoning.

Follows api/routers/communications_hub.py's own established pattern exactly: a
self-contained api/routers/<domain>.py module with its own APIRouter(),
importing the shared _authenticate helper from api/deps.py.
"""

from fastapi import APIRouter, Header
from pydantic import BaseModel

from api.deps import _authenticate

from core.customer_journey_api import (
    advance_journey_api,
    generate_journey_recommendation_api,
    get_customer_journey_api,
    get_journey_overview_api,
    list_customers_in_stage_api,
    set_journey_stage_api,
)


router = APIRouter()


class AdvanceJourneyRequest(BaseModel):

    note: str = ""


class SetJourneyStageRequest(BaseModel):

    stage: str
    note: str = ""


@router.get("/customer-journey/overview")
def customer_journey_overview_route(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_journey_overview_api(payload["role"])


@router.get("/customer-journey/customer/{customer_id}")
def customer_journey_get_route(customer_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_customer_journey_api(payload["role"], customer_id)


@router.post("/customer-journey/customer/{customer_id}/advance")
def customer_journey_advance_route(
    customer_id: str, request: AdvanceJourneyRequest, authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return advance_journey_api(payload["role"], customer_id, note=request.note)


@router.post("/customer-journey/customer/{customer_id}/stage")
def customer_journey_set_stage_route(
    customer_id: str, request: SetJourneyStageRequest, authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return set_journey_stage_api(payload["role"], customer_id, request.stage, note=request.note)


@router.get("/customer-journey/stage/{stage}")
def customer_journey_stage_route(stage: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_customers_in_stage_api(payload["role"], stage)


@router.post("/customer-journey/customer/{customer_id}/recommendation")
def customer_journey_recommendation_route(customer_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return generate_journey_recommendation_api(payload["role"], customer_id)
