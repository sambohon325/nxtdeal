"""Identity & Access router -- Administration Control Center's "Identity &
Access" Top Menu item: real per-employee API keys for programmatic access
(core/api_keys.py), already wired into api/deps.py's _authenticate()
bearer-token fallback (verify_api_key) -- unaffected by this extraction,
since that wiring lives in api/deps.py, not here.

Extracted verbatim out of api/app.py (CAF-00120, god_file_app_py -- splitting
the 14,000+-line monolith into domain-scoped FastAPI routers). Behavior is
unchanged from the original inline routes -- same paths, same request/response
shapes, same auth flow.

An employee can issue their own keys; issuing another employee's requires
ADMIN. ADMIN/OPERATIONS may inspect and revoke keys.
"""

import time

from core.auth import credential_store
from fastapi import APIRouter, Header
from pydantic import BaseModel

from api.deps import _authenticate

from core.api_keys_api import (
    generate_api_key_api,
    revoke_api_key_api,
    list_api_keys_for_employee_api,
    list_all_api_keys_api,
)


router = APIRouter()


class GenerateApiKeyRequest(BaseModel):
    """Body for POST /api-keys -- target_employee_id defaults to the caller's own
    id (self-service); an ADMIN caller may pass a different
    target_employee_id to issue a key on another employee's behalf. See
    core/api_keys_api.py's generate_api_key_api()."""

    target_employee_id: str = None
    label: str = ""


@router.post("/api-keys")
def api_keys_generate(request: GenerateApiKeyRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    # An existing API key must never mint replacement credentials. Only a recent
    # interactive login supplies authenticated_at; honor enrolled local MFA too.
    record = credential_store.get_record(payload["employee_id"])
    authenticated_at = payload.get("authenticated_at")
    if (not record or record.get("must_change_password")
            or type(authenticated_at) is not int
            or not 0 <= time.time() - authenticated_at <= 300
            or (credential_store.is_mfa_enabled(payload["employee_id"])
                and payload.get("mfa_authenticated") is not True)):
        return {"error": "Sign in again, complete any required password change and MFA, then create the API key within five minutes.",
                "code": "fresh_login_required"}

    return generate_api_key_api(
        payload["role"], payload["employee_id"], target_employee_id=request.target_employee_id, label=request.label
    )


@router.get("/api-keys/mine")
def api_keys_mine(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_api_keys_for_employee_api(payload["role"], payload["employee_id"])


@router.get("/api-keys/all")
def api_keys_all(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_all_api_keys_api(payload["role"])


@router.get("/api-keys/employee/{employee_id}")
def api_keys_for_employee(employee_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_api_keys_for_employee_api(payload["role"], payload["employee_id"], target_employee_id=employee_id)


@router.post("/api-keys/{key_id}/revoke")
def api_keys_revoke(key_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return revoke_api_key_api(payload["role"], payload["employee_id"], key_id)
