"""AI Consulting Engine router -- core/consulting_engine.py's four-part
(Analysis / Root Cause / Opportunity / Action Plan) strategic consultation
that composes NXTDeal's own already-real analysis. See that module's own
docstring for the full "compose already-real modules, never fabricate a
number" design and its relationship to Network's per-department AI Advisors.

Follows api/routers/communications_hub.py's own established pattern exactly: a
self-contained router module with its own APIRouter(), importing the shared
_authenticate helper from api/deps.py.
"""

from fastapi import APIRouter, Header
from pydantic import BaseModel

from api.deps import _authenticate

from core.consulting_engine_api import (
    get_consulting_overview_api,
    run_consultation_api,
)


router = APIRouter()


class ConsultationRequest(BaseModel):

    question: str
    department: str | None = None


@router.post("/consulting-engine/ask")
def consulting_engine_ask_route(request: ConsultationRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return run_consultation_api(
        payload["role"],
        request.question,
        department=request.department,
    )


@router.get("/consulting-engine/overview")
def consulting_engine_overview_route(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_consulting_overview_api(payload["role"])
