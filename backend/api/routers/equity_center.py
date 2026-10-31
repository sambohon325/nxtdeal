"""Equity Center router -- core/equity_center.py's graph-native equity /
trade-up opportunity engine (estimated equity position, lease-maturity + trade
opportunities, recorded upgrade offers, and a real AI upgrade-offer draft). See
that module's own docstring for the full real-vs-estimated disclosure.

Follows api/routers/communications_hub.py's own established pattern exactly: a
self-contained api/routers/<domain>.py module with its own APIRouter(),
importing the shared _authenticate helper from api/deps.py.
"""

from fastapi import APIRouter, Header
from pydantic import BaseModel

from api.deps import _authenticate

from core.equity_center_api import (
    create_upgrade_offer_api,
    generate_upgrade_offer_api,
    get_equity_overview_api,
    get_equity_position_api,
    list_equity_opportunities_api,
)


router = APIRouter()


class UpgradeOfferRequest(BaseModel):

    note: str = ""


@router.get("/equity-center/overview")
def equity_center_overview_route(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_equity_overview_api(payload["role"])


@router.get("/equity-center/opportunities")
def equity_center_opportunities_route(horizon_days: int = None, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_equity_opportunities_api(payload["role"], horizon_days=horizon_days)


@router.get("/equity-center/customer/{customer_id}")
def equity_center_customer_route(customer_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_equity_position_api(payload["role"], customer_id)


@router.post("/equity-center/customer/{customer_id}/offer")
def equity_center_create_offer_route(
    customer_id: str, request: UpgradeOfferRequest = UpgradeOfferRequest(), authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return create_upgrade_offer_api(payload["role"], customer_id, note=request.note)


@router.post("/equity-center/customer/{customer_id}/upgrade-offer")
def equity_center_upgrade_offer_route(customer_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return generate_upgrade_offer_api(payload["role"], customer_id)
