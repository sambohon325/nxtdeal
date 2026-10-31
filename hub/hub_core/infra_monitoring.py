"""
NXTDeal Hub -- Infrastructure & Platform Operations rebuild, slice 4 of 4
(closing): Monitoring.

Sam's original 12-item menu named "Monitoring" with no further detail
attached before his message was cut off (see CLAUDE.md's slice-1 kickoff
entry for the full 12-item list). Deliberately NOT a new computation
engine, per this whole rebuild's own standing instruction never to
fabricate infrastructure telemetry -- every real monitoring signal this
platform has already exists somewhere else in this same rebuild:

  - hub/hub_core/noc.py's real, transparent Alerts feed (reachability/
    configuration/network-coverage) -- the Hub's own existing "is anything
    on fire right now" board, already its own separately-tabbed screen.
  - hub/hub_core/platform_status.py's real request/error/latency Platform
    Status Board (Hub + every tenant's route groups).
  - hub/hub_core/infra_ai.py's real AI usage/reachability summary (+ its 4
    confirmed gaps).
  - hub/hub_core/infra_network_health.py's real Network Members/Anonymous
    Datasets counts + the re-runnable Privacy Audit pass/fail.

This module is a genuine "single pane of glass" -- it composes all four of
the above into ONE call so a NXTDeal employee doesn't have to open four
separate tabs to answer "is the platform healthy right now," but it never
recomputes any of their underlying logic itself: every field below is
either taken directly from one of those four functions' own real output,
or a small, transparent rollup OVER their own already-real fields (e.g.
"how many of the 4 subsystems report a problem right now"). Clearly
labeled throughout as composing already-real data, not a 4th independent
monitoring system with its own alert logic.

overall_status is a real, transparent rollup -- "attention_needed" if
either NOC or the Platform Status Board itself reports anything other than
its own healthy/operational state, else "healthy" -- matching
hub/hub_core/noc.py's and hub/hub_core/platform_status.py's own established "never
a fabricated composite score" precedent, one level up.
"""

from hub_core.noc import get_noc_status_board
from hub_core.platform_status import get_platform_status_board
from hub_core.infra_ai import get_ai_infrastructure_overview
from hub_core.infra_network_health import get_network_health_overview


def get_monitoring_overview():

    noc = get_noc_status_board()
    platform_status = get_platform_status_board()
    ai_infra = get_ai_infrastructure_overview()
    network_health = get_network_health_overview()

    noc_healthy = noc["overall_status"] == "healthy"
    platform_healthy = platform_status["overall_status"] == "operational"
    privacy_audit_passed = network_health["privacy_audit"]["passed"]

    subsystems_needing_attention = []
    if not noc_healthy:
        subsystems_needing_attention.append("noc")
    if not platform_healthy:
        subsystems_needing_attention.append("platform_status")
    if not privacy_audit_passed:
        subsystems_needing_attention.append("network_health_privacy_audit")

    overall_status = "attention_needed" if subsystems_needing_attention else "healthy"

    return {
        "overall_status": overall_status,
        "subsystems_needing_attention": subsystems_needing_attention,
        "noc_summary": {
            "overall_status": noc["overall_status"],
            "alert_counts": noc["alert_counts"],
            "top_alerts": noc["alerts"][:5],
            "see_full_view": "NOC tab (hub/hub_core/noc.py, GET /hub/noc/overview)",
        },
        "platform_status_summary": {
            "overall_status": platform_status["overall_status"],
            "counts": platform_status["counts"],
            "worst_entries": platform_status["entries"][:5],
            "see_full_view": (
                "Infrastructure -> Overview / Services tabs "
                "(GET /hub/infra/platform-status)"
            ),
        },
        "ai_infrastructure_summary": {
            "dealers_checked": ai_infra["dealers_checked"],
            "dealers_reachable": ai_infra["dealers_reachable"],
            "dealers_total": ai_infra["dealers_total"],
            "confirmed_gaps": [
                "response_time", "accuracy", "cost", "training_jobs",
            ],
            "see_full_view": "Infrastructure -> AI Infrastructure tab (GET /hub/infra/ai-infrastructure)",
        },
        "network_health_summary": {
            "network_members": network_health["network_members"],
            "active_snapshots": network_health["active_snapshots"],
            "privacy_audit_passed": privacy_audit_passed,
            "see_full_view": "Infrastructure -> Network Health tab (GET /hub/infra/network-health)",
        },
        "note": (
            "A genuine single-pane-of-glass composition, not a 4th "
            "independent monitoring engine -- every field above is taken "
            "directly from (or a small, transparent rollup over) hub/hub_core/"
            "noc.py's, hub/hub_core/platform_status.py's, hub/hub_core/infra_ai.py's, "
            "and hub/hub_core/infra_network_health.py's own already-real output. "
            "See each field's 'see_full_view' pointer for the underlying "
            "tab with full detail. overall_status is a real, transparent "
            "rollup ('attention_needed' if NOC, the Platform Status Board, "
            "or the Privacy Audit itself reports anything other than its "
            "own healthy/operational/passed state, else 'healthy') -- "
            "never a fabricated composite score."
        ),
    }
