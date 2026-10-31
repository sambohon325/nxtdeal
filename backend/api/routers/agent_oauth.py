"""Native assistant OAuth endpoints; never accepts passwords or API keys in URLs."""
from urllib.parse import parse_qsl, urlencode
from collections import deque
from threading import Lock
import time
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, Field
from api.routers.agent_fabric import employee, call
from core import agent_oauth as oauth

router = APIRouter(tags=["Assistant connections"])
NO_STORE = {"Cache-Control": "no-store", "Pragma": "no-cache", "Referrer-Policy": "no-referrer", "X-Frame-Options": "DENY"}
_requests = deque()
_rate_lock = Lock()


def rate_limit():
    # Bounded, process-wide public auth budget; never trusts forwarded client IPs.
    with _rate_lock:
        now = time.monotonic()
        while _requests and _requests[0] < now - 60:
            _requests.popleft()
        if len(_requests) >= 300:
            raise HTTPException(429, "Connection request limit reached", headers={**NO_STORE, "Retry-After": "60"})
        _requests.append(now)


@router.get("/.well-known/oauth-protected-resource")
@router.get("/.well-known/oauth-protected-resource/agent-fabric/mcp")
def protected_resource():
    return {"resource": oauth.resource(), "authorization_servers": [oauth.issuer()], "scopes_supported": sorted(oauth.SCOPES), "bearer_methods_supported": ["header"]}


@router.get("/.well-known/oauth-authorization-server")
def metadata():
    base = oauth.issuer()
    return {"issuer": base, "authorization_endpoint": base + "/agent-oauth/authorize", "token_endpoint": base + "/agent-oauth/token",
            "revocation_endpoint": base + "/agent-oauth/revoke", "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code", "refresh_token"], "code_challenge_methods_supported": ["S256"],
            "token_endpoint_auth_methods_supported": ["none"], "scopes_supported": sorted(oauth.SCOPES)}


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate parameter")
        result[key] = value
    return result


@router.get("/agent-oauth/authorize", dependencies=[Depends(rate_limit)])
def authorize(request: Request):
    try:
        if len(request.url.query) > 8192:
            raise ValueError("Request too large")
        request_id = oauth.begin(unique_pairs(request.query_params.multi_items()))
        return RedirectResponse(oauth.frontend() + "/agents/connections?" + urlencode({"request": request_id}), status_code=303, headers=NO_STORE)
    except ValueError as exc:
        return JSONResponse({"error": "invalid_request", "error_description": str(exc)}, status_code=400, headers=NO_STORE)


async def form(request):
    if request.headers.get("content-type", "").split(";")[0] != "application/x-www-form-urlencoded":
        raise ValueError("Form encoding required")
    raw = b""
    async for chunk in request.stream():
        raw += chunk
        if len(raw) > 8192:
            raise ValueError("Request too large")
    return unique_pairs(parse_qsl(raw.decode(), keep_blank_values=True, max_num_fields=20))


@router.post("/agent-oauth/token", dependencies=[Depends(rate_limit)])
async def token(request: Request):
    try:
        return JSONResponse(oauth.exchange(await form(request)), headers=NO_STORE)
    except (ValueError, PermissionError):
        return JSONResponse({"error": "invalid_grant"}, status_code=400, headers=NO_STORE)


@router.post("/agent-oauth/revoke", dependencies=[Depends(rate_limit)])
async def revoke_token(request: Request):
    try:
        data = await form(request)
        oauth.revoke_token(data.get("token", ""), data.get("client_id", ""))
        return JSONResponse({}, headers=NO_STORE)
    except ValueError:
        return JSONResponse({"error": "invalid_request"}, status_code=400, headers=NO_STORE)


class Client(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    name: str = Field(min_length=1, max_length=100)
    redirect_uris: list[str] = Field(min_length=1, max_length=5)


class Consent(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    request_id: str = Field(min_length=1, max_length=100)
    departments: list[str] = Field(default_factory=list, max_length=12)
    approve: bool


@router.get("/agent-oauth/connections")
def connections(actor=Depends(employee)):
    result = call(oauth.connections, actor)
    if actor["role"] == "ADMIN":
        from intelligence.chrono_remote import configuration
        result["chrono"] = configuration()
    return JSONResponse(result, headers=NO_STORE)


@router.post("/agent-oauth/chrono/check")
def chrono_check(actor=Depends(employee)):
    call(oauth.interactive, actor, True)
    from intelligence.chrono_remote import read
    result = read(actor, "workspace-summary")
    return JSONResponse({k: result[k] for k in ("status", "mode", "reason", "retrieved_at") if k in result}, headers=NO_STORE)


@router.post("/agent-oauth/clients")
def register(body: Client, actor=Depends(employee)):
    return JSONResponse(call(oauth.register_client, actor, body.name, body.redirect_uris), headers=NO_STORE)


@router.delete("/agent-oauth/clients/{client_id}")
def disable(client_id: str, actor=Depends(employee)):
    call(oauth.disable_client, actor, client_id)
    return {"disabled": True}


@router.get("/agent-oauth/requests/{request_id}")
def review(request_id: str, actor=Depends(employee)):
    return JSONResponse(call(oauth.review, actor, request_id), headers=NO_STORE)


@router.post("/agent-oauth/consent")
def consent(body: Consent, actor=Depends(employee)):
    return JSONResponse(call(oauth.consent, actor, body.request_id, body.departments, body.approve), headers=NO_STORE)


@router.delete("/agent-oauth/connections/{grant_id}")
def revoke(grant_id: str, actor=Depends(employee)):
    call(oauth.revoke, actor, grant_id)
    return {"revoked": True}
