"""
ACL wrapper for GET /network/storage-snapshot, matching
core/platform_metrics_network_api.py's exact shape -- reuses
core/network_snapshot_api.py's check_network_key() so this route is gated
by the identical DEALEROS_NETWORK_KEY shared secret every other
server-to-server Hub<->tenant route already uses.

Backs the NXTDeal Hub's "Infrastructure & Platform Operations" -> Databases
and Storage panels (hub/core/tenant_storage_metrics.py) -- real file sizes
and real entity/relationship/event/credential COUNTS only, no PII, no
entity content, no raw credential data. Same "coarse aggregate, safe to
expose under this key" reasoning as every prior /network/*-snapshot route.
"""

from core.network_snapshot_api import check_network_key
from core.storage_snapshot import get_storage_snapshot


def get_storage_snapshot_api(network_key):

    error = check_network_key(network_key)
    if error:
        return error

    return get_storage_snapshot()
