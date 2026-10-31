"""Inventory: Wholesale Desk routes, extracted from api/app.py (CAF-00120,
god_file_app_py -- splitting the monolithic app.py into per-domain routers).

Wholesale Candidates/Auction Queue/Title Status were already real (Inventory
rebuild, earlier sessions); this slice (seventh) added Open Offers, Sold
Wholesale Units, and Fund Collection as the three remaining internal-
tracking gaps -- a real WholesaleOffer entity + lifecycle
(submit/accept/reject/counter/withdraw), a real disposition-channel flag on
sale, and a real append-only funds-collected settlement record. See
core/wholesale_desk.py's own module docstring for the full design.

Static /wholesale-desk/catalog, /wholesale-desk/summary, /wholesale-desk/offers,
/wholesale-desk/sold, /wholesale-desk/funds registered before the dynamic
/wholesale-desk/{vehicle_id}/* paths, same route-shadowing-avoidance precedent
as /acquisitions/*, /pricing-desk/*, /lot-control/*, /merchandising/* -- order
preserved exactly as it was in app.py.
"""

from fastapi import APIRouter, Header
from pydantic import BaseModel

from api.deps import _authenticate

from core.wholesale_desk_api import (
    get_catalog_api as wholesale_catalog_api,
    submit_offer_api,
    accept_offer_api,
    reject_offer_api,
    counter_offer_api,
    withdraw_offer_api,
    list_offers_api,
    mark_wholesale_sold_api,
    get_sold_wholesale_units_api,
    record_funds_collected_api,
    get_fund_collection_status_api,
    get_wholesale_desk_summary_api,
)

router = APIRouter()


class SubmitOfferRequest(BaseModel):

    buyer_name: str
    offer_amount: float
    notes: str = ""


class RejectOfferRequest(BaseModel):

    notes: str = ""


class CounterOfferRequest(BaseModel):

    counter_amount: float


class MarkWholesaleSoldRequest(BaseModel):

    buyer_name: str
    sale_price: float
    offer_id: str = None
    notes: str = ""


class RecordFundsCollectedRequest(BaseModel):

    amount: float
    method: str = ""
    notes: str = ""


@router.get("/wholesale-desk/catalog")
def wholesale_desk_catalog():
    return wholesale_catalog_api()


@router.get("/wholesale-desk/summary")
def wholesale_desk_summary(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_wholesale_desk_summary_api(payload["role"])


@router.get("/wholesale-desk/offers")
def wholesale_desk_list_offers(vehicle_id: str = None, status: str = None, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_offers_api(payload["role"], vehicle_id=vehicle_id, status=status)


@router.post("/wholesale-desk/offers/{vehicle_id}")
def wholesale_desk_submit_offer(vehicle_id: str, request: SubmitOfferRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return submit_offer_api(payload["role"], payload["employee_id"], vehicle_id, request.buyer_name, request.offer_amount, notes=request.notes)


@router.post("/wholesale-desk/offers/{offer_id}/accept")
def wholesale_desk_accept_offer(offer_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return accept_offer_api(payload["role"], payload["employee_id"], offer_id)


@router.post("/wholesale-desk/offers/{offer_id}/reject")
def wholesale_desk_reject_offer(offer_id: str, request: RejectOfferRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return reject_offer_api(payload["role"], payload["employee_id"], offer_id, notes=request.notes)


@router.post("/wholesale-desk/offers/{offer_id}/counter")
def wholesale_desk_counter_offer(offer_id: str, request: CounterOfferRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return counter_offer_api(payload["role"], payload["employee_id"], offer_id, request.counter_amount)


@router.post("/wholesale-desk/offers/{offer_id}/withdraw")
def wholesale_desk_withdraw_offer(offer_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return withdraw_offer_api(payload["role"], payload["employee_id"], offer_id)


@router.get("/wholesale-desk/sold")
def wholesale_desk_sold_units(limit: int = 50, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_sold_wholesale_units_api(payload["role"], limit=limit)


@router.post("/wholesale-desk/sold/{vehicle_id}")
def wholesale_desk_mark_sold(vehicle_id: str, request: MarkWholesaleSoldRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return mark_wholesale_sold_api(payload["role"], payload["employee_id"], vehicle_id, request.buyer_name, request.sale_price, offer_id=request.offer_id, notes=request.notes)


@router.get("/wholesale-desk/funds")
def wholesale_desk_fund_status(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_fund_collection_status_api(payload["role"])


@router.post("/wholesale-desk/funds/{vehicle_id}")
def wholesale_desk_record_funds(vehicle_id: str, request: RecordFundsCollectedRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return record_funds_collected_api(payload["role"], payload["employee_id"], vehicle_id, request.amount, method=request.method, notes=request.notes)
