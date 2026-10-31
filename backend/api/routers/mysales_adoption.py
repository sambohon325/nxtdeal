"""
MySales adoption router (Phase 6): rep usage ping + Readiness conversion signals.
"""

from fastapi import APIRouter, Header
from pydantic import BaseModel

from api.deps import _authenticate

from core.mysales_adoption_api import (
    record_activity_api,
    get_adoption_summary_api,
    get_conversion_signals_api,
)


router = APIRouter()


class RecordActivityRequest(BaseModel):

    dealership_id: str | None = None
    action: str = "open"
    dealership_on_dealeros: bool = False
    rep_name: str | None = None


@router.post("/mysales-adoption/activity")
def mysales_adoption_activity(request: RecordActivityRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return record_activity_api(
        payload["role"], payload["employee_id"],
        dealership_id=request.dealership_id, action=request.action,
        dealership_on_dealeros=request.dealership_on_dealeros, rep_name=request.rep_name,
    )


@router.get("/mysales-adoption/summary")
def mysales_adoption_summary(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_adoption_summary_api(payload["role"])


@router.get("/mysales-adoption/conversion-signals")
def mysales_adoption_conversion_signals(min_reps: int = 1, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_conversion_signals_api(payload["role"], min_reps=min_reps)
