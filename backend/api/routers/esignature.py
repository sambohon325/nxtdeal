"""eSignature routes -- extracted from api/app.py (CAF-00120, god_file_app_py).

The sixth of Sam's ~10 "completely missing" dealership workflows -- a real
signing envelope against a snapshot of a Deal's generated contract, with a
real ESIGN-Act-style consent gate per signer before they can sign. See
core/esignature.py's module docstring for the full honest scope note.
"""

from fastapi import APIRouter, Header
from pydantic import BaseModel

from api.deps import _authenticate
from core.esignature_api import (
    list_esignature_statuses_api,
    list_esignature_signer_statuses_api,
    list_esignature_signer_roles_api,
    create_signature_request_api,
    add_signer_api,
    remove_signer_api,
    send_signature_request_api,
    capture_signer_consent_api,
    sign_api,
    decline_signer_api,
    void_signature_request_api,
    get_signature_request_api,
    list_signature_requests_api,
    get_esignature_dashboard_api,
)


router = APIRouter()


class CreateSignatureRequestRequest(BaseModel):

    linked_deal_id: str
    signers: list[dict]


class AddSignerRequest(BaseModel):

    name: str
    role: str
    email: str | None = None
    phone: str | None = None


class SignRequest(BaseModel):

    typed_signature: str


class DeclineSignerRequest(BaseModel):

    reason: str


@router.get("/esignature/statuses")
def esignature_statuses(authorization: str = Header(None)):

    _, error = _authenticate(authorization)
    if error:
        return error

    return list_esignature_statuses_api()


@router.get("/esignature/signer-statuses")
def esignature_signer_statuses(authorization: str = Header(None)):

    _, error = _authenticate(authorization)
    if error:
        return error

    return list_esignature_signer_statuses_api()


@router.get("/esignature/signer-roles")
def esignature_signer_roles(authorization: str = Header(None)):

    _, error = _authenticate(authorization)
    if error:
        return error

    return list_esignature_signer_roles_api()


@router.get("/esignature/dashboard")
def esignature_dashboard(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_esignature_dashboard_api(payload["role"])


@router.post("/esignature")
def esignature_create(request: CreateSignatureRequestRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return create_signature_request_api(payload["role"], payload["employee_id"], request.linked_deal_id, request.signers)


@router.get("/esignature")
def esignature_list(linked_deal_id: str = None, status: str = None, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_signature_requests_api(payload["role"], linked_deal_id=linked_deal_id, status=status)


@router.get("/esignature/{request_id}")
def esignature_get(request_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_signature_request_api(payload["role"], request_id)


@router.post("/esignature/{request_id}/signers")
def esignature_add_signer(request_id: str, request: AddSignerRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return add_signer_api(payload["role"], request_id, request.name, request.role, email=request.email, phone=request.phone)


@router.post("/esignature/{request_id}/signers/{signer_index}/remove")
def esignature_remove_signer(request_id: str, signer_index: int, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return remove_signer_api(payload["role"], request_id, signer_index)


@router.post("/esignature/{request_id}/send")
def esignature_send(request_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return send_signature_request_api(payload["role"], request_id)


@router.post("/esignature/{request_id}/signers/{signer_index}/consent")
def esignature_consent(request_id: str, signer_index: int, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return capture_signer_consent_api(payload["role"], request_id, signer_index)


@router.post("/esignature/{request_id}/signers/{signer_index}/sign")
def esignature_sign(request_id: str, signer_index: int, request: SignRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return sign_api(payload["role"], request_id, signer_index, request.typed_signature)


@router.post("/esignature/{request_id}/signers/{signer_index}/decline")
def esignature_decline(request_id: str, signer_index: int, request: DeclineSignerRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return decline_signer_api(payload["role"], request_id, signer_index, request.reason)


@router.post("/esignature/{request_id}/void")
def esignature_void(request_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return void_signature_request_api(payload["role"], request_id)
