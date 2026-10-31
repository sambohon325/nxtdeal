"""SSO / OIDC router (security-hardening pass, 2026-07-20).

Real authorization-code-flow SSO against any standards-compliant OIDC
provider (Entra ID, Okta, Google Workspace, Auth0, generic OIDC) -- see
core/sso.py's own module docstring for the full design (no JIT
provisioning, SSO bypasses local MFA, RS256-only signature verification,
IP allowlist/lockout still enforced) and its stated honest gap (real,
wired code that has never been round-tripped against a live IdP tenant).

GET /sso/login-options, GET /sso/begin, GET /sso/callback, and
POST /sso/callback are all deliberately UNAUTHENTICATED -- there is no
bearer token to present before a login has actually completed, the exact
same reasoning every other public/*-style route in this codebase already
follows (see e.g. core/purls.py's public functions). GET /sso/callback is
the real redirect_uri target a browser lands on after the IdP finishes;
POST /sso/callback exists for a frontend that intercepts that redirect
client-side and forwards code/state itself instead.

GET/POST /security/sso/* are the ADMIN-only configuration screen's own
routes -- see core/sso_config_api.py's own docstring for why this is
ADMIN-only rather than this codebase's more common ADMIN/OPERATIONS.

Extracted verbatim out of api/app.py (CAF-00120, god_file_app_py --
splitting the 13,000+-line monolith into domain-scoped FastAPI routers).
Behavior is unchanged from the original inline routes -- same paths, same
request/response shapes, same auth flow.
"""

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel

from api.deps import _authenticate

from core.sso import (
    begin_sso_login,
    complete_sso_login,
)

from core.sso_config_api import (
    get_sso_login_options_api,
    get_sso_config_api,
    update_sso_config_api,
    set_sso_enabled_api,
    discover_oidc_configuration_api,
)


router = APIRouter()


class CompleteSsoLoginRequest(BaseModel):
    """Body for POST /sso/callback, for a frontend that intercepts the IdP's
    redirect client-side and forwards code/state to us as a POST rather than
    letting the browser hit GET /sso/callback natively. Both routes call the
    same core/sso.py complete_sso_login() -- see that route's own docstring."""

    state: str
    code: str


class UpdateSsoConfigRequest(BaseModel):
    """Every field optional -- only a field that was actually sent overwrites
    the stored value (None means "leave it alone"), matching
    core/system_config.py's own partial-update convention. See
    core/sso_config.py's update_sso_config()."""

    provider: str = None
    issuer: str = None
    client_id: str = None
    client_secret: str = None
    authorization_endpoint: str = None
    token_endpoint: str = None
    jwks_uri: str = None
    userinfo_endpoint: str = None
    redirect_uri: str = None
    scopes: list[str] = None
    require_verified_email: bool = None


class SetSsoEnabledRequest(BaseModel):

    enabled: bool


class DiscoverOidcConfigurationRequest(BaseModel):

    issuer: str


@router.get("/sso/login-options")
def sso_login_options():
    """Public. Only enabled/provider -- called by the login page before
    anyone has a token, to decide whether to render a "Sign in with SSO"
    button at all."""

    return get_sso_login_options_api()


@router.get("/sso/begin")
def sso_begin():
    """Public. Returns {"authorization_url": ..., "state": ...} -- the
    frontend redirects the browser to authorization_url. An honest
    {"error": ...} if SSO isn't enabled/fully configured for this dealer."""

    return begin_sso_login()


@router.get("/sso/callback")
def sso_callback_get(
    code: str,
    state: str,
    http_request: Request = None
):
    """The real OIDC redirect_uri target -- this is the URL a real IdP
    redirects the browser back to with ?code=...&state=... once the
    employee finishes signing in there. See core/sso.py's
    complete_sso_login() for the full flow."""

    client_ip = http_request.client.host if http_request and http_request.client else None

    return complete_sso_login(state, code, client_ip=client_ip)


@router.post("/sso/callback")
def sso_callback_post(
    request: CompleteSsoLoginRequest,
    http_request: Request = None
):
    """Same real flow as GET /sso/callback, for a frontend that intercepts
    the IdP's redirect client-side and forwards code/state as a POST body
    instead of letting the browser hit the GET route natively."""

    client_ip = http_request.client.host if http_request and http_request.client else None

    return complete_sso_login(request.state, request.code, client_ip=client_ip)


@router.get("/security/sso/config")
def security_get_sso_config(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_sso_config_api(payload["role"])


@router.post("/security/sso/config")
def security_update_sso_config(
    request: UpdateSsoConfigRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    fields = {k: v for k, v in request.dict().items() if v is not None}

    return update_sso_config_api(payload["role"], payload["employee_id"], **fields)


@router.post("/security/sso/config/enabled")
def security_set_sso_enabled(
    request: SetSsoEnabledRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return set_sso_enabled_api(payload["role"], payload["employee_id"], request.enabled)


@router.post("/security/sso/discover")
def security_discover_oidc_configuration(
    request: DiscoverOidcConfigurationRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return discover_oidc_configuration_api(payload["role"], payload["employee_id"], request.issuer)
