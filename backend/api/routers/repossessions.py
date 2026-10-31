"""Repossessions routes, extracted from api/app.py (CAF-00120, god_file_app_py).

Finance's Retail Lending Platform expansion, "Repossessions" -- the fourth
slice of that arc, closing Sam's own stated loan-lifecycle sequencing
(...Collections -> Repossession -> Recovery -> Payoff). A real, first-class
RepossessionCase entity/lifecycle (referred -> assigned -> located ->
recovered -> stored -> disposed, with redeemed/cancelled off-ramps), a real
Deficiency Balance computation, and the Referral Queue drawn directly from
Collections' own repossession_referral stage.

Static paths (/repossessions/referral-queue, /repossessions/dashboard,
/repossessions/cases) are registered before the dynamic
/repossessions/cases/{case_id}/* paths.
"""

from fastapi import APIRouter, Header
from pydantic import BaseModel

from api.deps import _authenticate
from core.repossessions_api import (
    get_referral_queue_api,
    create_case_api,
    assign_agent_api,
    record_location_api,
    record_recovery_api,
    record_storage_api,
    record_disposition_api,
    redeem_case_api,
    cancel_case_api,
    compute_deficiency_balance_api,
    get_case_api,
    list_cases_api,
    get_repossessions_dashboard_api,
)

router = APIRouter()


class CreateRepossessionCaseRequest(BaseModel):

    loan_id: str
    reason: str = ""


class AssignRepoAgentRequest(BaseModel):

    agent_name: str
    agency: str = ""
    phone: str = ""


class RecordRepoLocationRequest(BaseModel):

    location: str
    notes: str = ""


class RecordRepoRecoveryRequest(BaseModel):

    recovered_date: str | None = None
    condition: str = ""
    odometer: int | None = None


class RecordRepoStorageRequest(BaseModel):

    storage_facility: str
    storage_start_date: str | None = None
    daily_rate: float = 0.0
    transport_cost: float = 0.0


class RecordRepoDispositionRequest(BaseModel):

    disposition_type: str
    sale_price: float
    sale_date: str | None = None
    buyer: str = ""
    notes: str = ""


class RedeemRepoCaseRequest(BaseModel):

    redemption_amount: float
    notes: str = ""


class CancelRepoCaseRequest(BaseModel):

    reason: str = ""


@router.get("/repossessions/referral-queue")
def repossessions_referral_queue(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_referral_queue_api(payload["role"])


@router.get("/repossessions/dashboard")
def repossessions_dashboard(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_repossessions_dashboard_api(payload["role"])


@router.get("/repossessions/cases")
def repossessions_list_cases(status: str | None = None, loan_id: str | None = None, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_cases_api(payload["role"], status=status, loan_id=loan_id)


@router.post("/repossessions/cases")
def repossessions_create_case(body: CreateRepossessionCaseRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return create_case_api(payload["role"], payload["employee_id"], body.loan_id, reason=body.reason)


@router.get("/repossessions/cases/{case_id}")
def repossessions_get_case(case_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_case_api(payload["role"], case_id)


@router.post("/repossessions/cases/{case_id}/assign-agent")
def repossessions_assign_agent(case_id: str, body: AssignRepoAgentRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return assign_agent_api(payload["role"], payload["employee_id"], case_id, body.agent_name, agency=body.agency, phone=body.phone)


@router.post("/repossessions/cases/{case_id}/location")
def repossessions_record_location(case_id: str, body: RecordRepoLocationRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return record_location_api(payload["role"], payload["employee_id"], case_id, body.location, notes=body.notes)


@router.post("/repossessions/cases/{case_id}/recovery")
def repossessions_record_recovery(case_id: str, body: RecordRepoRecoveryRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return record_recovery_api(payload["role"], payload["employee_id"], case_id, recovered_date=body.recovered_date, condition=body.condition, odometer=body.odometer)


@router.post("/repossessions/cases/{case_id}/storage")
def repossessions_record_storage(case_id: str, body: RecordRepoStorageRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return record_storage_api(payload["role"], payload["employee_id"], case_id, body.storage_facility, storage_start_date=body.storage_start_date, daily_rate=body.daily_rate, transport_cost=body.transport_cost)


@router.post("/repossessions/cases/{case_id}/disposition")
def repossessions_record_disposition(case_id: str, body: RecordRepoDispositionRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return record_disposition_api(payload["role"], payload["employee_id"], case_id, body.disposition_type, body.sale_price, sale_date=body.sale_date, buyer=body.buyer, notes=body.notes)


@router.post("/repossessions/cases/{case_id}/redeem")
def repossessions_redeem_case(case_id: str, body: RedeemRepoCaseRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return redeem_case_api(payload["role"], payload["employee_id"], case_id, body.redemption_amount, notes=body.notes)


@router.post("/repossessions/cases/{case_id}/cancel")
def repossessions_cancel_case(case_id: str, body: CancelRepoCaseRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return cancel_case_api(payload["role"], payload["employee_id"], case_id, reason=body.reason)


@router.get("/repossessions/cases/{case_id}/deficiency")
def repossessions_deficiency(case_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return compute_deficiency_balance_api(payload["role"], case_id)
