"""Shop Control router -- third slice of Service's rebuild
(core/shop_control.py / core/shop_control_api.py).

Sam's spec: a Technician Dispatch Board, Technician Utilization, Stalled RO
Detection, and Shop Bottlenecks. The Shop Workflow Board itself is NOT
duplicated here -- it's the same real board GET /repair-orders/board already
provides.

Extracted verbatim out of api/app.py (CAF-00120, god_file_app_py -- splitting
the 13,000+-line monolith into domain-scoped FastAPI routers). Behavior is
unchanged from the original inline routes -- same paths, same request/
response shapes, same auth flow.
"""

from fastapi import APIRouter, Header

from api.deps import _authenticate

from core.shop_control_api import (
    get_dispatch_board_api,
    get_technician_utilization_api,
    get_stalled_ros_api,
    get_bottlenecks_api,
)


router = APIRouter()


@router.get("/shop-control/dispatch-board")
def shop_control_dispatch_board(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_dispatch_board_api(payload["role"])


@router.get("/shop-control/utilization")
def shop_control_utilization(date: str | None = None, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_technician_utilization_api(payload["role"], date=date)


@router.get("/shop-control/stalled")
def shop_control_stalled(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_stalled_ros_api(payload["role"])


@router.get("/shop-control/bottlenecks")
def shop_control_bottlenecks(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_bottlenecks_api(payload["role"])
