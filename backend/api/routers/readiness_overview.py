"""Readiness Overview router -- Readiness' rebuilt "Overview" Top Menu item
(core/readiness_overview.py / _api.py), which is ALSO Sam's separately-named
"Readiness Heatmap" capstone feature ("show every department % with
drill-down capability") -- confirmed the same real feature before building,
so built once, not twice. Deliberately open to every real role (see
core/readiness_overview_api.py's own docstring).

No route is needed here for the base overview itself (it's served by the
existing generic GET /menu/data?department=Readiness&item_key=overview path
via core/menu_data.py's unchanged readiness_overview alias) -- these 2
routes back the dedicated board's own on-demand actions: a direct fetch
(used by the board on mount, bypassing the generic dispatcher same as every
other bespoke board) and a real "regenerate" action (re-runs the real
template, with an optional isolated-OpenAI phrasing polish toggle -- POST
because the AI polish path makes a real outbound call, even though nothing
is mutated on the graph).

Extracted verbatim out of api/app.py (CAF-00120, god_file_app_py -- splitting
the 14,000+-line monolith into domain-scoped FastAPI routers). Behavior is
unchanged from the original inline routes -- same paths, same request/response
shapes, same auth flow.
"""

from fastapi import APIRouter, Header
from pydantic import BaseModel

from api.deps import _authenticate

from core.readiness_overview_api import (
    get_enterprise_readiness_overview_api,
    regenerate_executive_summary_api,
)


router = APIRouter()


class RegenerateReadinessSummaryRequest(BaseModel):

    polish: bool = True


@router.get("/readiness-overview/overview")
def readiness_overview_route(authorization: str = Header(None), polish_summary: bool = True):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_enterprise_readiness_overview_api(payload["role"], polish_summary=polish_summary)


@router.post("/readiness-overview/regenerate-summary")
def readiness_overview_regenerate_summary_route(request: RegenerateReadinessSummaryRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return regenerate_executive_summary_api(payload["role"], polish=request.polish)
