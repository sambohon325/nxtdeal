"""Credit Application routes, extracted from api/app.py (CAF-00120, god_file_app_py
-- splitting the monolithic app.py into domain-scoped routers).

Session 104 follow-up: the fifth of Sam's ~10 "completely missing" dealership
workflows -- a real applicant-level record (employment/income, FCRA consent, a
simulated decision), tied to a Customer and optionally a Deal. See
core/credit_app.py's own module docstring for the full honest scope note on
what "decision" means here.

Same 13 routes, same behavior, same auth/ACL, just moved out of app.py.
"""

from fastapi import APIRouter, Header
from pydantic import BaseModel

from api.deps import _authenticate

from core.credit_app_api import (
    list_credit_app_statuses_api,
    list_credit_app_decisions_api,
    list_credit_app_field_options_api,
    create_credit_application_api,
    update_applicant_api,
    set_ssn_last4_api,
    give_fcra_consent_api,
    submit_credit_application_api,
    withdraw_credit_application_api,
    link_credit_application_to_deal_api,
    get_credit_application_api,
    list_credit_applications_api,
    get_credit_app_dashboard_api,
)

router = APIRouter()


class CreateCreditApplicationRequest(BaseModel):

    customer_id: str
    linked_deal_id: str | None = None
    requested_amount: float | None = None


class UpdateCreditApplicantRequest(BaseModel):

    applicant_patch: dict | None = None
    co_applicant_patch: dict | None = None
    requested_amount: float | None = None


class SetCreditAppSsnRequest(BaseModel):

    ssn_last4: str


class LinkCreditAppToDealRequest(BaseModel):

    deal_id: str


@router.get("/credit-apps/statuses")
def credit_app_statuses(authorization: str = Header(None)):

    _, error = _authenticate(authorization)
    if error:
        return error

    return list_credit_app_statuses_api()


@router.get("/credit-apps/decisions")
def credit_app_decisions(authorization: str = Header(None)):

    _, error = _authenticate(authorization)
    if error:
        return error

    return list_credit_app_decisions_api()


@router.get("/credit-apps/field-options")
def credit_app_field_options(authorization: str = Header(None)):

    _, error = _authenticate(authorization)
    if error:
        return error

    return list_credit_app_field_options_api()


@router.get("/credit-apps/dashboard")
def credit_app_dashboard(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_credit_app_dashboard_api(payload["role"])


@router.post("/credit-apps")
def credit_app_create(request: CreateCreditApplicationRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return create_credit_application_api(
        payload["role"], payload["employee_id"],
        request.customer_id,
        linked_deal_id=request.linked_deal_id,
        requested_amount=request.requested_amount,
    )


@router.get("/credit-apps")
def credit_app_list(customer_id: str = None, status: str = None, linked_deal_id: str = None,
                    authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_credit_applications_api(payload["role"], customer_id=customer_id, status=status, linked_deal_id=linked_deal_id)


@router.get("/credit-apps/{app_id}")
def credit_app_get(app_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_credit_application_api(payload["role"], app_id, employee_id=payload.get("employee_id"))


@router.post("/credit-apps/{app_id}/applicant")
def credit_app_update_applicant(app_id: str, request: UpdateCreditApplicantRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return update_applicant_api(
        payload["role"], app_id,
        applicant_patch=request.applicant_patch,
        co_applicant_patch=request.co_applicant_patch,
        requested_amount=request.requested_amount,
    )


@router.post("/credit-apps/{app_id}/ssn")
def credit_app_set_ssn(app_id: str, request: SetCreditAppSsnRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return set_ssn_last4_api(payload["role"], app_id, request.ssn_last4)


@router.post("/credit-apps/{app_id}/consent")
def credit_app_consent(app_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return give_fcra_consent_api(payload["role"], app_id)


@router.post("/credit-apps/{app_id}/submit")
def credit_app_submit(app_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return submit_credit_application_api(payload["role"], app_id)


@router.post("/credit-apps/{app_id}/withdraw")
def credit_app_withdraw(app_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return withdraw_credit_application_api(payload["role"], app_id)


@router.post("/credit-apps/{app_id}/link-deal")
def credit_app_link_deal(app_id: str, request: LinkCreditAppToDealRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return link_credit_application_to_deal_api(payload["role"], app_id, request.deal_id)
