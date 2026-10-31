"""Staff loyalty operations. Tenant isolation follows the per-dealer backend.

Public endpoints stay fail-closed alongside the existing My Garage identity gate.
"""
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictInt

from api.deps import _authenticate
from core import loyalty_program as service
from core.dealeros import ledger
from core.entity_types import CUSTOMER

router = APIRouter()
READ = {"ADMIN", "OPERATIONS", "MARKETING", "SALES", "SERVICE", "FINANCE"}
MANAGE = {"ADMIN", "OPERATIONS", "MARKETING"}
ADJUST = {"ADMIN", "OPERATIONS"}
FULFILL = {"ADMIN", "OPERATIONS", "SERVICE", "SALES"}


def staff(authorization: str | None = Header(None)):
    payload, error = _authenticate(authorization)
    if error:
        raise HTTPException(401, detail=error["error"])
    if payload.get("role") not in READ:
        raise HTTPException(403, detail="Loyalty access is not permitted.")
    return payload


def authorize(user, roles):
    if user.get("role") not in roles:
        raise HTTPException(403, detail="Your role cannot perform this loyalty action.")
    return user.get("employee_id") or user.get("sub") or user.get("role")


def invoke(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except service.LoyaltyError as exc:
        raise HTTPException(409, detail=str(exc)) from exc


class Request(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_key: str = Field(min_length=1, max_length=200)


class Enroll(Request):
    terms_version: str


class Adjustment(Request):
    points: StrictInt
    reason: str = Field(min_length=1, max_length=1000)


class Reservation(Request):
    reward_id: str
    appointment_id: str = Field(min_length=1)
    location: str = Field(min_length=1)


class Resolution(Request):
    source: str = ""
    reason: str = ""


class Reversal(Adjustment):
    entry_id: str


class Purchase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_system: str = Field(min_length=1, max_length=100)
    source_id: str = Field(min_length=1, max_length=100)
    customer_id: str
    kind: str
    eligible_cents: StrictInt = Field(ge=0, le=1000000000)
    location: str = Field(min_length=1)
    status: str
    occurred_at: str
    campaign_id: str | None = None
    confirmation: str = Field(min_length=1, max_length=1000)


@router.get("/loyalty/program/workspace")
def workspace(user=Depends(staff)):
    return service.workspace() | {"permissions": {"manage": user["role"] in MANAGE,
             "adjust": user["role"] in ADJUST, "fulfill": user["role"] in FULFILL}}


@router.post("/loyalty/program/config/{kind}")
def save_config(kind: str, data: dict, user=Depends(staff)):
    return invoke(service.save_document, kind, data, authorize(user, MANAGE))


@router.get("/loyalty/program/members/{customer_id}")
def get_member(customer_id: str, user=Depends(staff)):
    return invoke(service.get_member, customer_id)


@router.post("/loyalty/program/members/{customer_id}/enroll")
def enroll(customer_id: str, data: Enroll, user=Depends(staff)):
    actor = authorize(user, MANAGE | FULFILL)
    customer = ledger.get_entity(customer_id)
    if not customer or customer.entity_type != CUSTOMER:
        raise HTTPException(404, detail="Customer not found in this dealership.")
    attrs = customer.attributes
    name = attrs.get("Name") or " ".join([attrs.get("FirstName", ""), attrs.get("LastName", "")]).strip() or customer_id
    return invoke(service.enroll, customer_id, name, actor, data.request_key, data.terms_version,
                  legacy_points=attrs.get("loyalty_points_balance", 0))


@router.post("/loyalty/program/members/{customer_id}/adjust")
def adjust(customer_id: str, data: Adjustment, user=Depends(staff)):
    return invoke(service.adjust, customer_id, data.points, data.reason, authorize(user, ADJUST), data.request_key)


@router.post("/loyalty/program/members/{customer_id}/reserve")
def reserve(customer_id: str, data: Reservation, user=Depends(staff)):
    actor = authorize(user, FULFILL)
    # A reservation must reference a real appointment owned by this customer.
    from core.appointments import get_appointment
    appointment = get_appointment(data.appointment_id)
    if not appointment or appointment.attributes.get("customer_id") != customer_id:
        raise HTTPException(409, detail="Choose an appointment belonging to this customer.")
    if appointment.attributes.get("status") in {"cancelled", "canceled", "completed", "no_show"}:
        raise HTTPException(409, detail="This appointment cannot accept a reward.")
    return invoke(service.reserve, customer_id, data.reward_id, data.appointment_id,
                  data.location, actor, data.request_key)


@router.post("/loyalty/program/members/{customer_id}/reservations/{hold_id}/{action}")
def resolve(customer_id: str, hold_id: str, action: str, data: Resolution, user=Depends(staff)):
    return invoke(service.resolve_hold, customer_id, hold_id, action, authorize(user, FULFILL),
                  data.request_key, data.source, data.reason)


@router.post("/loyalty/program/members/{customer_id}/reverse")
def reverse(customer_id: str, data: Reversal, user=Depends(staff)):
    return invoke(service.reverse, customer_id, data.entry_id, data.points, data.reason,
                  authorize(user, ADJUST), data.request_key)


@router.post("/loyalty/program/preview")
def preview(data: Purchase, user=Depends(staff)):
    return invoke(service.preview, data.model_dump())


@router.post("/loyalty/program/purchases")
def purchase(data: Purchase, user=Depends(staff)):
    # Explicit staff-attested fallback until provider-specific adapters are connected.
    actor = authorize(user, ADJUST)
    try:
        parsed = service.datetime.fromisoformat(data.occurred_at)
        if parsed.tzinfo is None or parsed > service.datetime.now(service.timezone.utc):
            raise ValueError()
    except ValueError:
        raise HTTPException(422, detail="Purchase time must be a past timestamp with timezone.")
    return invoke(service.process_purchase, data.model_dump(), actor)


@router.post("/loyalty/program/events/retry")
def retry(data: dict, user=Depends(staff)):
    return invoke(service.retry_event, str(data.get("event_id", "")), authorize(user, ADJUST))


@router.api_route("/public/garage/loyalty", methods=["GET", "POST"])
@router.api_route("/public/garage/loyalty/{path:path}", methods=["GET", "POST"])
def customer_unavailable(path: str = ""):
    raise HTTPException(503, detail="Secure customer verification is not available yet. Contact your dealership for loyalty assistance.")
