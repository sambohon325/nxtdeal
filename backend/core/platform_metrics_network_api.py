"""
ACL wrapper for GET /network/platform-metrics-snapshot, matching
core/ai_management_network_api.py's / core/audit_network_api.py's exact
shape -- reuses core/network_snapshot_api.py's check_network_key() so this
route is gated by the identical DEALEROS_NETWORK_KEY shared secret every
other server-to-server Hub<->tenant route already uses.

Backs the NXTDeal Hub's "Infrastructure & Platform Operations" -> Services
panel (hub/core/infra_services.py) -- real, in-process request/error/
latency counters per service group (core/platform_metrics.py), no PII, no
endpoint URLs, no freeform text. Same "coarse aggregate, safe to expose
under this key" reasoning as every prior /network/*-snapshot route.
"""

from core.network_snapshot_api import check_network_key
from core.platform_metrics import get_platform_metrics_snapshot


def get_platform_metrics_snapshot_api(network_key):

    error = check_network_key(network_key)
    if error:
        return error

    return get_platform_metrics_snapshot()
