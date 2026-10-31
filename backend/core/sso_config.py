"""
Per-dealer SSO/OIDC identity-provider configuration -- security-hardening pass
(2026-07-20), Task #14 "SSO scaffolding (SAML/OIDC-ready)."

A real, fixed-id, per-dealer SINGLETON -- modeled directly on
core/system_config.py's own _CONFIG_ID/_get_or_create()/additive-backfill
pattern, since this codebase is one NXTDeal instance per dealer (see the
"NXTDeal Hub / Multi-Tenant Architecture" section of CLAUDE.md): exactly one
IdP configuration record per tenant, not a dict keyed by dealer_id.

Kept as its own entity type (SSO_CONFIG, not folded onto SystemConfig) for one
concrete reason: client_secret is a meaningfully more sensitive value than
anything already on SystemConfig (business hours, feature flags, department
goals), and this module's own ACL layer (core/sso_config_api.py) is
deliberately ADMIN-only for both viewing and editing -- narrower than
SystemConfig's own ADMIN/OPERATIONS-viewable convention -- so folding these
fields onto that broader-read record would accidentally widen who can see an
OAuth client secret.

Real, working OIDC discovery (discover_oidc_configuration()) fetches a live
provider's /.well-known/openid-configuration document via plain urllib (no
requests/httpx dependency, matching core/data_connections.py's own established
no-extra-HTTP-library convention) and returns the real authorization_endpoint/
token_endpoint/jwks_uri/userinfo_endpoint it finds -- this part genuinely works
against any real, reachable OIDC-compliant issuer (Entra ID, Okta, Google
Workspace, Auth0, etc.) the moment a real issuer URL is supplied.

Honest, stated gap: no live IdP client_id/secret/issuer exists in this sandbox
to complete a real end-to-end login round-trip against -- this configuration
layer, and core/sso.py's login-flow logic built on top of it, ship as real,
wired code that has never been exercised against a live Entra/Okta/Google/
Auth0 tenant, not as a live-verified integration. See core/sso.py's own module
docstring for the full picture of what "real but never round-tripped" means
here.

client_secret storage note, stated plainly rather than glossed over: unlike a
password (core/auth.py, PBKDF2-hashed, never retrievable), an OAuth client
secret must remain retrievable in plaintext -- the token-exchange step
(core/sso.py's exchange_code_for_tokens()) has to present it back to the IdP
verbatim on every login. It is stored as a plain attribute on this entity, the
same way core/data_connections.py already stores connection credentials/
endpoint URLs on a Connection entity -- no separate encryption-at-rest layer
exists anywhere in this codebase for any stored credential today (a real,
already-flagged gap, not unique to this module). This module's own ACL
(ADMIN-only) and the platform's existing graph.json file-system permissions
are the only real access controls on it right now.
"""

import json
import urllib.error
import urllib.request

from datetime import datetime, timezone

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import SSO_CONFIG
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH

_CONFIG_ID = "SSOCFG-00001"

_DISCOVERY_TIMEOUT_SECONDS = 8

_VALID_PROVIDERS = ("entra_id", "okta", "google_workspace", "auth0", "generic_oidc")

_EDITABLE_MANUAL_FIELDS = (
    "provider",
    "issuer",
    "client_id",
    "client_secret",
    "authorization_endpoint",
    "token_endpoint",
    "jwks_uri",
    "userinfo_endpoint",
    "redirect_uri",
    "scopes",
    "require_verified_email",
)


def _now():
    return datetime.now(timezone.utc).isoformat()


def _default_attributes():
    return {
        "enabled": False,
        "provider": None,
        "issuer": None,
        "client_id": None,
        "client_secret": None,
        "authorization_endpoint": None,
        "token_endpoint": None,
        "jwks_uri": None,
        "userinfo_endpoint": None,
        "redirect_uri": None,
        # A real default scope list matching every mainstream OIDC provider's
        # own minimum viable set -- "openid" is mandatory per the OIDC spec
        # itself, "email"/"profile" are what verify_id_token()'s
        # require_verified_email check and complete_sso_login()'s
        # email-based employee lookup both actually need.
        "scopes": ["openid", "email", "profile"],
        "require_verified_email": True,
        "discovered_at": None,
        "updated_by": None,
        "updated_at": _now(),
    }


def _get_or_create():
    entity = ledger.get_entity(_CONFIG_ID)
    if entity and entity.entity_type == SSO_CONFIG:
        defaults = _default_attributes()
        changed = False
        for key, value in defaults.items():
            if key not in entity.attributes:
                entity.attributes[key] = value
                changed = True
        if changed:
            save_graph(GRAPH_PATH)
        return entity

    entity = Entity(id=_CONFIG_ID, entity_type=SSO_CONFIG, attributes=_default_attributes())
    ledger.add_entity(entity)
    save_graph(GRAPH_PATH)
    return entity


def get_sso_config():
    entity = _get_or_create()
    return {"id": entity.id, **entity.attributes}


def is_sso_enabled():
    """A small, dependency-light helper for core/sso.py/core/sso_api.py to
    check readiness without pulling in the full config dict -- true only when
    the dealer has actually turned SSO on AND supplied the minimum real fields
    a login attempt needs (client_id/issuer/authorization_endpoint/
    token_endpoint/jwks_uri/redirect_uri)."""

    config = get_sso_config()
    if not config.get("enabled"):
        return False
    required = (
        "client_id",
        "issuer",
        "authorization_endpoint",
        "token_endpoint",
        "jwks_uri",
        "redirect_uri",
    )
    return all(config.get(field) for field in required)


def update_sso_config(updated_by, **fields):
    entity = _get_or_create()

    if "provider" in fields and fields["provider"] is not None:
        if fields["provider"] not in _VALID_PROVIDERS:
            return {"error": f"provider must be one of {list(_VALID_PROVIDERS)}."}

    if "scopes" in fields and fields["scopes"] is not None:
        if not isinstance(fields["scopes"], list) or not all(isinstance(s, str) for s in fields["scopes"]):
            return {"error": "scopes must be a list of strings."}
        if "openid" not in fields["scopes"]:
            return {"error": "scopes must include 'openid' -- required by the OIDC spec itself."}

    for key, value in fields.items():
        if key in _EDITABLE_MANUAL_FIELDS and value is not None:
            entity.attributes[key] = value

    entity.attributes["updated_by"] = updated_by
    entity.attributes["updated_at"] = _now()
    save_graph(GRAPH_PATH)
    return {"id": entity.id, **entity.attributes}


def set_sso_enabled(enabled, updated_by):
    entity = _get_or_create()

    if enabled:
        # Refuse to flip the switch on without the minimum real fields a
        # login attempt would actually need -- an "enabled" toggle with no
        # real client_id/issuer/endpoints behind it would silently break
        # every login attempt against it rather than fail loudly here, at
        # the one point a human is actually looking at the form.
        missing = [
            field
            for field in ("client_id", "issuer", "authorization_endpoint", "token_endpoint", "jwks_uri", "redirect_uri")
            if not entity.attributes.get(field)
        ]
        if missing:
            return {
                "error": (
                    "Cannot enable SSO -- missing required field(s): "
                    + ", ".join(missing)
                    + ". Run discovery or fill them in manually first."
                )
            }

    entity.attributes["enabled"] = bool(enabled)
    entity.attributes["updated_by"] = updated_by
    entity.attributes["updated_at"] = _now()
    save_graph(GRAPH_PATH)
    return {"id": entity.id, **entity.attributes}


def discover_oidc_configuration(issuer, updated_by=None):
    """Real, live OIDC discovery -- GETs {issuer}/.well-known/openid-configuration
    over plain urllib and, on success, stores the real authorization_endpoint/
    token_endpoint/jwks_uri/userinfo_endpoint it finds directly onto this
    dealer's SsoConfig, stamping discovered_at. Returns an honest {"error": ...}
    dict on any failure (unreachable issuer, non-200 response, invalid JSON,
    or a response missing one of the fields this module actually needs) --
    never a fabricated endpoint guess.

    This is the one piece of core/sso_config.py that is genuinely, fully
    live-verifiable today against any real, reachable OIDC issuer on the
    public internet -- it just has none configured in this sandbox to point
    at by default.
    """

    if not issuer or not isinstance(issuer, str):
        return {"error": "issuer is required and must be a non-empty string."}

    issuer = issuer.rstrip("/")
    if not issuer.startswith("https://"):
        return {"error": "issuer must be a full URL, e.g. https://login.microsoftonline.com/{tenant}/v2.0"}

    discovery_url = issuer + "/.well-known/openid-configuration"

    try:
        from core.outbound_http import public_https_json
        document = public_https_json(discovery_url, timeout=_DISCOVERY_TIMEOUT_SECONDS)
    except (ValueError, OSError):
        return {"error": "Could not read a valid public HTTPS discovery document."}

    required_keys = ("authorization_endpoint", "token_endpoint", "jwks_uri")
    missing_keys = [key for key in required_keys if not document.get(key)]
    if missing_keys:
        return {
            "error": (
                f"discovery response was missing required field(s): {', '.join(missing_keys)} "
                f"-- this does not look like a real OIDC discovery document."
            )
        }

    real_issuer_in_doc = document.get("issuer")
    if real_issuer_in_doc != issuer:
        return {"error": "Discovery issuer must exactly match the requested issuer."}
    entity = _get_or_create()
    entity.attributes["issuer"] = issuer
    entity.attributes["authorization_endpoint"] = document["authorization_endpoint"]
    entity.attributes["token_endpoint"] = document["token_endpoint"]
    entity.attributes["jwks_uri"] = document["jwks_uri"]
    entity.attributes["userinfo_endpoint"] = document.get("userinfo_endpoint")
    entity.attributes["discovered_at"] = _now()
    if updated_by is not None:
        entity.attributes["updated_by"] = updated_by
    entity.attributes["updated_at"] = _now()
    save_graph(GRAPH_PATH)

    result = {"id": entity.id, **entity.attributes}
    return result
