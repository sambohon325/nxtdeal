"""
API layer for the provider-credential store + adapter factory (Track B, 2026-07-25).
Viewing integration status and the provider slots is open to any authenticated role;
storing/removing credentials (which can flip a capability live) is ADMIN-only. Secrets are
never returned unmasked.
"""

from core.permissions import ADMIN
from core import provider_credentials as pc
from core.integrations_registry import provider_status


def get_connections_api(role):
    """Combined view for the Connections screen: per-capability live/simulated status, the
    stored (masked) credentials, and the provider slots offered per capability."""
    return {
        "status": provider_status(),
        "credentials": pc.list_credentials(),
        "slots": pc.provider_slots(),
    }


def configure_credential_api(role, admin_id, capability, provider, config=None, secrets=None):
    if role != ADMIN:
        return {"error": "Admin role required to configure provider credentials"}
    return pc.configure_credential(capability, provider, config or {}, secrets or {}, admin_id)


def remove_credential_api(role, admin_id, capability):
    if role != ADMIN:
        return {"error": "Admin role required to remove provider credentials"}
    return pc.remove_credential(capability)
