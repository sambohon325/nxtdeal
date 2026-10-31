"""
Thin ACL layer for core/sso_config.py -- deliberately ADMIN-only for both
viewing and editing (narrower than core/system_config_api.py's own
ADMIN/OPERATIONS-viewable convention), since a client_secret is a meaningfully
more sensitive value than anything else on that broader-read record. Matches
core/auth.py's own set_ip_allowlist_api-class precedent of a narrower-than-
usual gate for a specifically sensitive security control.

get_sso_login_options_api() is the one deliberate exception -- it is called
from an UNAUTHENTICATED context (the public login page needs to know whether
to render an "Sign in with SSO" button before anyone has a token at all), so it
takes no role argument and returns only the minimum non-sensitive fields a
login page needs (enabled/provider) -- never client_secret, never even
client_id.
"""

from core.sso_config import (
    get_sso_config,
    update_sso_config,
    set_sso_enabled,
    discover_oidc_configuration,
)
from core.permissions import ADMIN

_ADMIN_ONLY_ERROR = {"error": "Admin role required."}


def get_sso_login_options_api():
    """Public, unauthenticated. Only enabled/provider -- never a secret, never
    even client_id, since this is read by anyone who loads the login page."""

    config = get_sso_config()
    return {
        "enabled": bool(config.get("enabled")),
        "provider": config.get("provider") if config.get("enabled") else None,
    }


def get_sso_config_api(role):
    if role != ADMIN:
        return _ADMIN_ONLY_ERROR
    return get_sso_config()


def update_sso_config_api(role, employee_id, **fields):
    if role != ADMIN:
        return _ADMIN_ONLY_ERROR
    return update_sso_config(employee_id, **fields)


def set_sso_enabled_api(role, employee_id, enabled):
    if role != ADMIN:
        return _ADMIN_ONLY_ERROR
    return set_sso_enabled(enabled, employee_id)


def discover_oidc_configuration_api(role, employee_id, issuer):
    if role != ADMIN:
        return _ADMIN_ONLY_ERROR
    return discover_oidc_configuration(issuer, updated_by=employee_id)
