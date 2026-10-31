"""
ACL wrapper for GET /network/operational-health-snapshot, matching
core/ai_management_network_api.py's exact shape (session/slice precedent) --
reuses core/network_snapshot_api.py's check_network_key() so this route is
gated by the identical DEALEROS_NETWORK_KEY shared secret every other
server-to-server Hub<->tenant route already uses.
"""

from core.network_snapshot_api import check_network_key
from core.audit_network_snapshot import build_operational_health_snapshot


def get_operational_health_snapshot_api(network_key):

    error = check_network_key(network_key)
    if error:
        return error

    return build_operational_health_snapshot()
