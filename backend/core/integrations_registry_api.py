"""
core/integrations_registry_api.py -- API layer for the integration provider seam (2026-07-24).
Viewing which external providers are connected vs simulated is open to any authenticated role
(operational insight); recording the intended provider for a capability is ADMIN.
"""

from core.permissions import ADMIN
from core.integrations_registry import provider_status, configure_provider


def get_integrations_api(role):
    return provider_status()


def configure_provider_api(admin_role, admin_id, capability, provider_name, note=None):
    if admin_role != ADMIN:
        return {"error": "Admin role required to configure an integration provider"}
    return configure_provider(capability, provider_name, admin_id, note=note)
