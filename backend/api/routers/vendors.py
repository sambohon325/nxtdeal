"""Vendor Management router -- part of Administration Control Center
(core/vendor_management.py / core/vendor_management_api.py).

Real Vendor entities -- back-office software/contract management,
ADMIN/OPERATIONS-only throughout. Static "/vendors/dashboard" registered
before the dynamic "/vendors/{vendor_id}" path.

Extracted verbatim out of api/app.py (CAF-00120, god_file_app_py -- splitting
the 13,000+-line monolith into domain-scoped FastAPI routers). Behavior is
unchanged from the original inline routes -- same paths, same request/
response shapes, same auth flow.
"""

from fastapi import APIRouter, Header
from pydantic import BaseModel

from api.deps import _authenticate

from core.vendor_management_api import (
    create_vendor_api,
    update_vendor_api,
    set_vendor_status_api,
    get_vendor_api,
    list_vendors_api,
    get_vendor_dashboard_api,
)


router = APIRouter()


class CreateVendorRequest(BaseModel):
    """Body for POST /vendors. See core/vendor_management.py's create_vendor() for
    the real editable field set."""

    name: str
    category: str
    contact_name: str = ""
    contact_email: str = ""
    contact_phone: str = ""
    monthly_cost: float = None
    contract_start_date: str = None
    contract_end_date: str = None
    auto_renew: bool = False
    notes: str = ""


class UpdateVendorRequest(BaseModel):
    """Body for PUT /vendors/{vendor_id} -- a partial patch, only the fields
    actually sent are applied (see core/vendor_management.py's update_vendor())."""

    name: str = None
    category: str = None
    contact_name: str = None
    contact_email: str = None
    contact_phone: str = None
    monthly_cost: float = None
    contract_start_date: str = None
    contract_end_date: str = None
    auto_renew: bool = None
    notes: str = None


class SetVendorStatusRequest(BaseModel):

    status: str


@router.post("/vendors")
def vendors_create(request: CreateVendorRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return create_vendor_api(
        payload["role"],
        payload["employee_id"],
        request.name,
        request.category,
        contact_name=request.contact_name,
        contact_email=request.contact_email,
        contact_phone=request.contact_phone,
        monthly_cost=request.monthly_cost,
        contract_start_date=request.contract_start_date,
        contract_end_date=request.contract_end_date,
        auto_renew=request.auto_renew,
        notes=request.notes,
    )


@router.get("/vendors")
def vendors_list(category: str = None, status: str = None, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_vendors_api(payload["role"], category=category, status=status)


@router.get("/vendors/dashboard")
def vendors_dashboard(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_vendor_dashboard_api(payload["role"])


@router.get("/vendors/{vendor_id}")
def vendors_get(vendor_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_vendor_api(payload["role"], vendor_id)


@router.put("/vendors/{vendor_id}")
def vendors_update(vendor_id: str, request: UpdateVendorRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    fields = {k: v for k, v in request.model_dump().items() if v is not None}

    return update_vendor_api(payload["role"], payload["employee_id"], vendor_id, **fields)


@router.post("/vendors/{vendor_id}/status")
def vendors_set_status(vendor_id: str, request: SetVendorStatusRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return set_vendor_status_api(payload["role"], payload["employee_id"], vendor_id, request.status)
