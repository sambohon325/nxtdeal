"""
ACL layer for the AI Management network snapshot route (2026-07-19, Dealer
Management rebuild slice 4 of 5). Reuses core/network_snapshot_api.py's
check_network_key() directly rather than a second copy of the DEALEROS_NETWORK_KEY
check -- same shared secret, same "server-to-server call from the Hub, not a
logged-in employee" reasoning.

See core/ai_management.py's build_ai_management_network_snapshot() for what this
route actually returns and why it's judged safe to expose under this key (real,
aggregate, non-PII feature-catalog + call-count data, dealer-identified on the Hub
side the same way hub/core/server_health.py's and hub/core/dealer_onboarding.py's
existing per-dealer live checks already are -- this key authenticates the Hub as a
legitimate caller, it does not by itself require anonymization).
"""

from core.network_snapshot_api import check_network_key
from core.ai_management import build_ai_management_network_snapshot


def get_ai_management_network_snapshot_api(network_key):

    error = check_network_key(network_key)

    if error:
        return error

    return build_ai_management_network_snapshot()
