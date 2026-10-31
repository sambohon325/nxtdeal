"""Hub-facing ACL for the module-adoption snapshot (Freemium roadmap, Phase 4, 2026-08-03).

Server-to-server: the NXTDeal Hub reads this to place the dealer in its extended Dealer Lifecycle
Funnel (Foundation Signup -> Foundation Active -> Module Adoption -> Expansion -> Churn Risk). Gated
by the same DEALEROS_NETWORK_KEY shared secret via check_network_key(). Returns only the tenant's own
module-attach state + derived funnel stage -- no PII."""

from core.network_snapshot_api import check_network_key
from core.module_adoption import build_module_adoption_snapshot


def get_module_adoption_snapshot_api(network_key):
    error = check_network_key(network_key)
    if error:
        return error
    return build_module_adoption_snapshot()
