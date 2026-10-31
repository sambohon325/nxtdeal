"""
NXTDeal Hub -- Infrastructure & Platform Operations rebuild, slice 4 of 4
(closing): Messaging.

Sam's original 12-item menu named "Messaging" with no further detail
attached before his message was cut off (see CLAUDE.md's slice-1 kickoff
entry for the full 12-item list). Investigated honestly before writing
anything, same discipline every other item in this whole rebuild followed:

WHAT "MESSAGING" COULD HONESTLY MEAN HERE, and what it does NOT mean:
this is NOT a Hub-to-tenant or cross-tenant messaging/notification system
-- no such thing exists anywhere in this codebase (confirmed via grep --
zero matches for "messaging"/"websocket"/"ConnectionManager" anywhere
under hub/). The only real messaging subsystem in this entire platform is
backend/core/ws_manager.py's ConnectionManager + backend/core/messaging.py
-- per-tenant, real-time, EMPLOYEE-to-employee chat (channels + DMs) inside
one dealership. That subsystem is intentionally NOT Hub-visible in any
identifying way: reading actual message content, sender/recipient names,
or channel membership from the Hub would be a real PII violation, the
exact class of thing this whole rebuild (and the Hub's Network Health
Privacy Audit) is built to prevent.

THE HONEST GAP, stated as the PRIMARY answer: there is no cross-tenant or
Hub-to-tenant messaging/notification system anywhere in this platform.
This screen is not a placeholder for one -- it doesn't exist by design,
same as hub_core/infra_network_health.py's Prediction Runs/Benchmark Jobs
"not applicable" framing.

THE ONE GENUINELY SAFE SIGNAL, added alongside the gap rather than instead
of it: whether each tenant's OWN per-employee chat subsystem is
structurally alive right now -- a real, coarse, non-PII connection-count
and channel-count snapshot, NOT message content, sender identity, or
channel membership. This reuses hub/hub_core/infra_services.py's ALREADY-
fetched per-dealer platform-metrics snapshot directly (this slice extended
backend/core/platform_metrics.py's existing /network/platform-metrics-
snapshot response with a new `messaging_subsystem` block -- see that
module's own docstring) rather than adding a 4th narrowly-scoped tenant
route for one small addition. No new fetch, no new Recheck action -- the
Services panel's own existing Recheck already refreshes this.
"""

from hub_core.dealer_registry import registry as dealer_registry
from hub_core.infra_services import registry as services_registry


CROSS_TENANT_MESSAGING_GAP_NOTE = (
    "CONFIRMED GAP, not a 'coming soon' placeholder: no Hub-to-tenant or "
    "cross-tenant messaging/notification system exists anywhere in this "
    "platform (a full grep for 'messaging'/'websocket'/'ConnectionManager' "
    "across hub/ returned zero matches). The only real messaging subsystem "
    "anywhere in NXTDeal is per-tenant, real-time employee chat "
    "(backend/core/ws_manager.py + backend/core/messaging.py) -- "
    "intentionally NOT Hub-visible beyond the coarse, non-PII structural "
    "liveness signal below, since reading actual message content or "
    "sender/recipient identity from the Hub would be a real PII "
    "violation."
)


def _dealer_messaging_entry(dealer):

    snapshot = services_registry.get(dealer.dealer_id)

    if not snapshot or not snapshot.reachable or not snapshot.data.get("groups"):
        return {
            "dealer_id": dealer.dealer_id,
            "dealer_name": dealer.name,
            "checked": snapshot is not None,
            "reachable": snapshot.reachable if snapshot else None,
            "fetched_at": snapshot.fetched_at if snapshot else None,
            "messaging_subsystem": None,
        }

    return {
        "dealer_id": dealer.dealer_id,
        "dealer_name": dealer.name,
        "checked": True,
        "reachable": True,
        "fetched_at": snapshot.fetched_at,
        "messaging_subsystem": snapshot.data.get("messaging_subsystem"),
    }


def get_messaging_overview():
    """Composes: (1) the honest, primary gap statement above, and (2) a
    real, per-dealer, non-PII structural liveness check of each tenant's
    own per-employee chat subsystem, reusing hub/hub_core/infra_services.py's
    already-fetched snapshot registry directly -- no new tenant route, no
    new Recheck action."""

    dealers = dealer_registry.list_all()
    entries = [_dealer_messaging_entry(d) for d in dealers]

    checked = [e for e in entries if e["messaging_subsystem"]]
    total_open_sockets = sum(
        e["messaging_subsystem"]["open_socket_count"] for e in checked
    )
    total_connected_employees = sum(
        e["messaging_subsystem"]["employees_with_open_connection"] for e in checked
    )

    return {
        "cross_tenant_messaging": {
            "applicable": False,
            "note": CROSS_TENANT_MESSAGING_GAP_NOTE,
        },
        "per_dealer_chat_liveness": entries,
        "aggregate": {
            "dealers_checked": len(checked),
            "dealers_total": len(dealers),
            "total_open_socket_count": total_open_sockets,
            "total_employees_with_open_connection": total_connected_employees,
        },
        "note": (
            "'per_dealer_chat_liveness' REUSES hub/hub_core/infra_services.py's "
            "already-fetched Services-panel snapshot (GET /network/"
            "platform-metrics-snapshot, extended this slice with a real "
            "`messaging_subsystem` block) -- no new tenant route, no "
            "separate Recheck action. Use the Services panel's own Recheck "
            "to refresh a dealer's messaging liveness too. Real, aggregate, "
            "non-PII counts only -- no employee id, name, or message "
            "content is ever included."
        ),
    }
