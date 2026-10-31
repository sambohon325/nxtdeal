"""Hub-facing ACL for the onboarding-signals snapshot (Freemium roadmap, Phase 2, 2026-08-03).

Server-to-server: the NXTDeal Hub reads this to replace its manual 7-step Setup Wizard checkboxes
with the tenant's real, auto-detected onboarding state. Gated by the same DEALEROS_NETWORK_KEY
shared secret as every other /network/*-snapshot, via check_network_key(). Dealer-identified on the
Hub side (like the AI-management snapshot). Returns only aggregate counts + boolean step state --
no PII, no entity content."""

from core.network_snapshot_api import check_network_key
from core.onboarding_signals import build_onboarding_signals_snapshot


def get_onboarding_signals_snapshot_api(network_key):
    error = check_network_key(network_key)
    if error:
        return error
    return build_onboarding_signals_snapshot()
