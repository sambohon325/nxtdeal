"""
NXTDeal Hub -- Infrastructure & Platform Operations rebuild, slice 1 of 4:
Overview.

Sam's reframe of the old "Server Health" tab: rename to "Infrastructure &
Platform Operations," since the platform will eventually run thousands of
dealer tenants -- proposed a real 12-item menu (Overview | Clusters |
Services | Databases | AI Infrastructure | Network Health | Messaging |
Storage | Backups | Disaster Recovery | Security | Monitoring), "think
Azure Status Page." Sam's own example numbers ("US East: 340 nodes") are
ILLUSTRATIVE of the eventual multi-region vision, not literal targets to
fabricate here -- this sandbox runs exactly ONE Hub process and (today) ONE
real registered dealer tenant, each its own real process (see CLAUDE.md's
"process-per-tenant, not in-process multi-tenancy" architecture decision).

This module reports that real topology honestly -- 1 Hub process + N real
registered dealer tenants, each with a real, live reachability check
(hub/hub_core/server_health.py) -- rather than inventing a fabricated
multi-region/multi-cluster picture that doesn't exist yet. "Platform
Health" is a real, transparent rollup off that same reachability data
(e.g. "1 of 1 dealer tenant(s) reachable"), never a fabricated uptime
percentage with nothing real behind it.
"""

from hub_core.dealer_registry import registry as dealer_registry
from hub_core.server_health import get_server_health_overview
from hub_core.hub_platform_metrics import get_hub_platform_metrics_snapshot


def get_infra_overview():

    dealers = dealer_registry.list_all()
    health = get_server_health_overview()
    hub_metrics = get_hub_platform_metrics_snapshot()

    # Derived directly from the per-dealer checks, NOT from health's own
    # top-level unreachable_dealers field -- that field is computed as
    # len(dealers) - reachable_count, which silently lumps "not_configured"
    # dealers (never deployed / no api_base_url on file) in with genuinely
    # unreachable ones. Caught live while building this module: with the
    # one real seeded dealer having no api_base_url on file, the top-level
    # field reported it as "1 unreachable" even though server_health.py's
    # OWN per-dealer status for that exact dealer correctly said
    # "not_configured" -- a real, pre-existing inconsistency in that
    # module's own aggregate fields. Not changed here (other established
    # consumers already read those top-level fields) -- worked around
    # locally by recomputing from the real per-dealer list instead, so this
    # Overview's own "honestly distinguished" claim below is actually true.
    reachable = len([c for c in health["dealers"] if c["status"] == "reachable"])
    unreachable = len([c for c in health["dealers"] if c["status"] == "unreachable"])
    not_configured = len(
        [c for c in health["dealers"] if c["status"] == "not_configured"]
    )
    checkable = reachable + unreachable

    if len(dealers) == 0:
        summary = "No dealer tenants are registered with the Hub yet -- nothing to report on."
    elif checkable == 0:
        summary = (
            f"{len(dealers)} dealer tenant(s) registered, but none have a "
            "recorded api_base_url on file yet, so reachability can't be "
            "checked for any of them."
        )
    elif unreachable == 0:
        summary = f"{reachable} of {checkable} checkable dealer tenant(s) reachable -- all clear."
    else:
        summary = f"{reachable} of {checkable} checkable dealer tenant(s) reachable -- {unreachable} unreachable."

    return {
        "topology": {
            "hub_processes": 1,
            "tenant_processes_registered": len(dealers),
            "tenant_processes_reachable": reachable,
            "tenant_processes_unreachable": unreachable,
            "tenant_processes_not_configured": not_configured,
            "deployment_model": (
                "process-per-tenant -- every dealer runs the same NXTDeal "
                "backend as its own isolated process with its own storage "
                "directory (backend/core/storage_paths.py's "
                "DEALEROS_STORAGE_DIR); the Hub is a separate, single "
                "additional process. See CLAUDE.md's NXTDeal Hub section."
            ),
        },
        "hub_uptime_seconds": hub_metrics["uptime_seconds"],
        "platform_health": {
            "summary": summary,
            "basis": "real_live_reachability_check",
            "note": (
                "This is a real, transparent rollup off hub/hub_core/"
                "server_health.py's live reachability checks -- NOT a "
                "fabricated uptime percentage. A dealer with no "
                "api_base_url on file is reported separately as "
                "'not_configured' (never deployed / never recorded), "
                "distinct from a genuinely unreachable one."
            ),
        },
        "dealers": health["dealers"],
        "note": (
            "This deployment is a single Hub process plus however many "
            "real dealer tenant processes are actually registered -- no "
            "fabricated multi-region/multi-cluster infrastructure is "
            "reported here. Sam's own illustrative examples (e.g. 'US "
            "East: 340 nodes') describe the eventual vision at scale, not "
            "today's real, much smaller footprint."
        ),
    }
