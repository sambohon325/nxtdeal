"""
Connections router (Track B, 2026-07-25): the provider-integration status + credential
store. GET /connections shows each capability live/simulated, the stored (masked)
credentials, and the provider slots per capability. Configuring/removing a credential is
ADMIN-only and can flip a capability live via the adapter factory.
"""

from fastapi import APIRouter, Header
from pydantic import BaseModel

from api.deps import _authenticate

from core.provider_credentials_api import (
    get_connections_api,
    configure_credential_api,
    remove_credential_api,
)


router = APIRouter()


class ConfigureCredentialRequest(BaseModel):

    provider: str
    config: dict = {}
    secrets: dict = {}


@router.get("/connections")
def connections_status(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_connections_api(payload["role"])


@router.post("/connections/{capability}")
def connections_configure(
    capability: str,
    request: ConfigureCredentialRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return configure_credential_api(
        payload["role"], payload["employee_id"], capability, request.provider, request.config, request.secrets
    )


@router.delete("/connections/{capability}")
def connections_remove(
    capability: str,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return remove_credential_api(payload["role"], payload["employee_id"], capability)
