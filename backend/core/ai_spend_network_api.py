"""Hub-facing ACL for the AI-spend snapshot (Freemium roadmap, Phase 5, 2026-08-03).

Server-to-server: the NXTDeal Hub reads this to meter AI Workforce consumption per dealer later.
Gated by the same DEALEROS_NETWORK_KEY shared secret via check_network_key(). Returns only aggregate
AI-action counts + BYO-key posture -- no PII, no prompt/response content, no user-level detail beyond
which user ids are over their limit."""

from core.network_snapshot_api import check_network_key
from core.ai_spend import build_ai_spend_network_snapshot


def get_ai_spend_snapshot_api(network_key):
    error = check_network_key(network_key)
    if error:
        return error
    return build_ai_spend_network_snapshot()
