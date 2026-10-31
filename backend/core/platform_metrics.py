"""
Real, lightweight, in-process request/error/latency instrumentation --
Infrastructure & Platform Operations rebuild, slice 1 of 4 (Overview /
Platform Status Board / Services).

Sam's ask for the Hub's "Server Health" tab (renamed "Infrastructure &
Platform Operations"): a real Services board -- "think Azure Status Page,"
e.g. "NXTDeal Core: Operational, NXTDeal Marketing: Operational, NXTDeal
Finance: Performance Warning." Checked honestly before building anything:
this sandbox runs ONE tenant process serving ONE dealer, with no real
multi-node/multi-region infrastructure to report on. Fabricating CPU%, node
counts, or region latency would be a materially different (and riskier)
kind of dishonesty than this codebase's established "simulate a real market/
peer-data gap, disclose it" policy (session 110) -- that policy covers
external data this system genuinely can't obtain; infrastructure telemetry
that could mislead a real operational decision is deliberately NOT
simulated here. What IS real and buildable: actual request/error/latency
counters over this process's own real HTTP traffic, grouped by which real
NXTDeal subsystem each route belongs to.

SERVICE-GROUP MAPPING, the judgment call this module makes explicit rather
than guesses at silently: each FastAPI route's first path segment is
attributed to the ONE NXTDeal department/subsystem its own backing module
most directly belongs to, per this codebase's own build history (documented
extensively across CLAUDE.md's session-by-session entries). This is a real
signal (actual traffic against real, already-existing route groups), not a
fabricated pseudo-service -- unlike Sam's own illustrative "NXTDeal
Marketing" example, every group here maps onto a route prefix that
genuinely exists and genuinely belongs to that department's own module set.
A few routes are honestly shared across two departments (e.g. Appointment
is a deliberately department-agnostic entity used by both Sales and
Service, session 96) -- those are bucketed into "core_platform" rather than
arbitrarily assigned to one department. Anything not explicitly mapped
falls into "other" rather than being guessed into the wrong department.

HONESTY, restated plainly (same convention as core/ai_management.py's
call-attempt counters and core/ws_manager.py's ConnectionManager): every
counter below is IN-MEMORY ONLY. It resets to zero the moment this process
restarts. This is real, live telemetry for the current process's uptime,
not a historical record -- there is no persistence layer for it, by design
(a lightweight instrumentation layer, not a time-series metrics database).

MESSAGING SUBSYSTEM (added Infrastructure & Platform Operations rebuild,
slice 4 of 4, closing) -- the NXTDeal Hub's Messaging menu item needed a
real, non-PII, structural liveness signal for this tenant's per-employee
real-time chat (core/ws_manager.py's ConnectionManager, core/messaging.py),
and this route was already the established, tested fetch mechanism the
Hub's Services panel pulls (rather than adding a 4th narrowly-scoped
tenant route for one small addition). `_messaging_subsystem_snapshot()`
below is deliberately coarse: how many employees currently have an open
websocket connection, how many total open sockets exist (an employee can
have more than one tab/device open), and how many fixed department
channels are configured -- real counts and a fixed structural catalog size,
never an employee id, name, or any message content. This module makes NO
claim about cross-tenant/Hub-to-tenant messaging (no such system exists
anywhere in this codebase) -- see hub/core/infra_messaging.py's own
docstring for that honest gap.
"""

import time
from collections import defaultdict, deque
from threading import Lock


PROCESS_START_TIME = time.time()

_MAX_LATENCY_SAMPLES = 200


ROUTE_GROUP_CATALOG = {
    "core_platform": "Core Platform (Auth, Search, AI Assistant, Messaging, Dashboards, Shared Entities)",
    "sales": "Sales & Deal Desk",
    "service": "Service & Repair Orders",
    "finance": "Finance & Retail Lending Platform",
    "marketing": "Marketing Growth Platform",
    "inventory": "Inventory",
    "operations": "Operations",
    "administration": "Administration Control Center",
    "readiness_network": "Readiness & Network Intelligence",
    "public": "Public / Customer-Facing Pages",
    "other": "Other / Uncategorized",
}


# First real URL path segment -> logical service group. Built directly off a
# grep of every @app.get/post/put/delete decorator in this file -- see this
# module's own docstring for the mapping philosophy. Where a real prefix
# genuinely belongs to more than one department's own module set, it's
# assigned to whichever department's session history in CLAUDE.md most
# directly attributes it to (stated inline below only where non-obvious).
_SEGMENT_TO_GROUP = {
    # Core Platform -- auth, generic dashboards, search/entity, AI assistant,
    # messaging, shared cross-department entities/engines.
    "": "core_platform",
    "auth": "core_platform",
    "dashboard": "core_platform",
    "entity": "core_platform",
    "search": "core_platform",
    "profile": "core_platform",
    "question": "core_platform",
    "me": "core_platform",
    "ai": "core_platform",
    "messaging": "core_platform",
    "notes": "core_platform",
    "notification-preferences": "core_platform",
    "workspace-board": "core_platform",
    "dashboard-layout": "core_platform",
    "knowledge": "core_platform",
    "menu": "core_platform",
    "bot": "core_platform",
    "workflows": "core_platform",
    "report-modules": "core_platform",
    "overview-modules": "core_platform",
    "tasks": "core_platform",
    "documents": "core_platform",
    "appointments": "core_platform",
    "appointment-scheduling": "core_platform",

    # Sales & Deal Desk
    "sales": "sales",
    "deals": "sales",
    "credit-apps": "sales",
    "esignature": "sales",
    "fi-products": "sales",
    "demo-drives": "sales",
    "up-system": "sales",
    "bdc": "sales",
    "manager-to": "sales",
    "lost-sale-recovery": "sales",
    "orphan-owners": "sales",
    "leads": "sales",
    "lead": "sales",
    "customers": "sales",
    "vehicle-holds": "sales",

    # Service & Repair Orders
    "repair-orders": "service",
    "service": "service",
    "service-customers": "service",
    "service-sales-handoff": "service",
    "shop-control": "service",
    "parts-desk": "service",
    "warranty-desk": "service",
    "dvi": "service",
    "service-records": "service",
    "loaner-fleet": "service",
    "loaner-assignments": "service",
    "shuttle-requests": "service",

    # Finance & Retail Lending Platform
    "loan-servicing": "finance",
    "repossessions": "finance",
    "collateral": "finance",
    "devices": "finance",
    "loan-accounting": "finance",
    "general-ledger": "finance",
    "bank-reconciliation": "finance",
    "lending-compliance": "finance",
    "payments": "finance",
    "collections": "finance",
    "auto-drafts": "finance",
    "promises": "finance",
    "payoff-requests": "finance",

    # Marketing Growth Platform
    "websites": "marketing",
    "website-templates": "marketing",
    "events": "marketing",
    "event-tasks": "marketing",
    "rsvps": "marketing",
    "campaigns": "marketing",
    "email-templates": "marketing",
    "social": "marketing",
    "advertising": "marketing",
    "reputation": "marketing",
    "purls": "marketing",
    "personal-sites": "marketing",
    "lists": "marketing",
    "smart-audiences": "marketing",
    "opportunities": "marketing",
    "marketing-attribution": "marketing",
    "assets": "marketing",
    "lead-scoring": "marketing",
    "customer-360": "marketing",
    "chat": "marketing",
    "alerts": "marketing",

    # Inventory
    "vehicle-lifecycle": "inventory",
    "lot-control": "inventory",
    "acquisitions": "inventory",
    "wholesale-desk": "inventory",
    "merchandising": "inventory",
    "inventory-aging": "inventory",
    "pricing-desk": "inventory",
    "inventory": "inventory",
    "vehicles": "inventory",

    # Operations
    "operations-tasks": "operations",
    "operations-alerts": "operations",
    "operations-scheduling": "operations",
    "document-workflows": "operations",
    "operations": "operations",

    # Administration Control Center
    "system-config": "administration",
    "permissions": "administration",
    "approval-requests": "administration",
    "automation-rules": "administration",
    "automation-executions": "administration",
    "automation": "administration",
    "audit-center": "administration",
    "governance": "administration",
    "vendors": "administration",
    "data-management": "administration",
    "compliance": "administration",
    "connections": "administration",
    "ai-management": "administration",
    "api-keys": "administration",
    "audit": "administration",
    "employees": "administration",

    # Readiness & Network Intelligence
    "readiness": "readiness_network",
    "readiness-scenarios": "readiness_network",
    "readiness-timeline": "readiness_network",
    "readiness-recommendations": "readiness_network",
    "readiness-overview": "readiness_network",
    "readiness-forecasts": "readiness_network",
    "performance-readiness": "readiness_network",
    "strategic-planning": "readiness_network",
    "business-health": "readiness_network",
    "enterprise-risk": "readiness_network",
    "data-health": "readiness_network",
    "network": "readiness_network",
    "network-overview": "readiness_network",
    "network-advisors": "readiness_network",
    "intelligence": "readiness_network",
    "ai-business-analyst": "readiness_network",

    # Public / customer-facing (no employee session at all)
    "public": "public",
}


def _group_for_path(path):
    segments = [s for s in path.split("/") if s]
    if not segments:
        return "core_platform"
    return _SEGMENT_TO_GROUP.get(segments[0], "other")


class _GroupMetrics:
    __slots__ = (
        "request_count",
        "error_count",
        "latency_samples",
        "last_request_at",
        "last_error_at",
    )

    def __init__(self):
        self.request_count = 0
        self.error_count = 0
        self.latency_samples = deque(maxlen=_MAX_LATENCY_SAMPLES)
        self.last_request_at = None
        self.last_error_at = None


_metrics = defaultdict(_GroupMetrics)
_lock = Lock()


def _now_iso():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def record_request(path, status_code, latency_ms):
    """Called once per real HTTP request by the @app.middleware("http") hook in
    api/app.py (tenant) / app.py (Hub) -- increments the real in-memory counters
    for whichever service group this path belongs to. Never raises."""

    group = _group_for_path(path)
    now = _now_iso()

    with _lock:
        m = _metrics[group]
        m.request_count += 1
        m.latency_samples.append(latency_ms)
        m.last_request_at = now
        if status_code >= 400:
            m.error_count += 1
            m.last_error_at = now


def _derive_status(request_count, error_count):
    """Real, transparent thresholds -- never a fabricated composite score.
    no_traffic_yet is a distinct, honest state from operational (this
    process genuinely hasn't served a request in this group since it
    started, not "confirmed healthy")."""

    if request_count == 0:
        return "no_traffic_yet"

    error_rate = (error_count / request_count) * 100

    if error_rate == 0:
        return "operational"
    if error_rate <= 10:
        return "performance_warning"
    return "degraded"


_STATUS_LABELS = {
    "operational": "Operational",
    "performance_warning": "Performance Warning",
    "degraded": "Degraded",
    "no_traffic_yet": "No Traffic Yet",
    "unreachable": "Unreachable",
}


def _messaging_subsystem_snapshot():
    """Real, coarse, non-PII structural snapshot of this tenant process's
    own real-time employee chat subsystem -- deferred imports to avoid
    adding a top-level dependency to this otherwise self-contained module
    (matches this file's own light-footprint design). Never raises: a
    missing/uninitialized subsystem is reported as zero, not an error."""

    try:
        from core.ws_manager import manager as _ws_manager
        from core.messaging import CHANNEL_DEFS as _channel_defs
    except Exception:
        return {
            "employees_with_open_connection": 0,
            "open_socket_count": 0,
            "channels_configured": 0,
            "note": "Messaging subsystem modules could not be loaded in this process.",
        }

    employees_connected = len(_ws_manager.connections)
    open_sockets = sum(len(sockets) for sockets in _ws_manager.connections.values())

    return {
        "employees_with_open_connection": employees_connected,
        "open_socket_count": open_sockets,
        "channels_configured": len(_channel_defs),
        "note": (
            "Real, in-process counts off core/ws_manager.py's own "
            "ConnectionManager (live websocket connections) and core/"
            "messaging.py's fixed CHANNEL_DEFS catalog -- IN-MEMORY ONLY, "
            "resets on restart, same convention as the route-group "
            "counters above. No employee id, name, or message content is "
            "ever included."
        ),
    }


def get_platform_metrics_snapshot():
    """Real per-service-group request/error/latency metrics for THIS process,
    since it started (PROCESS_START_TIME). In-memory only -- resets on
    restart, see this module's own docstring."""

    with _lock:
        groups = {}
        for key, label in ROUTE_GROUP_CATALOG.items():
            m = _metrics.get(key)

            if m is None or m.request_count == 0:
                groups[key] = {
                    "label": label,
                    "request_count": 0,
                    "error_count": 0,
                    "error_rate_pct": 0.0,
                    "avg_latency_ms": None,
                    "sample_size": 0,
                    "last_request_at": None,
                    "last_error_at": None,
                    "status": "no_traffic_yet",
                    "status_label": _STATUS_LABELS["no_traffic_yet"],
                }
                continue

            avg_latency = (
                round(sum(m.latency_samples) / len(m.latency_samples), 1)
                if m.latency_samples
                else None
            )
            error_rate = round((m.error_count / m.request_count) * 100, 2)
            status = _derive_status(m.request_count, m.error_count)

            groups[key] = {
                "label": label,
                "request_count": m.request_count,
                "error_count": m.error_count,
                "error_rate_pct": error_rate,
                "avg_latency_ms": avg_latency,
                "sample_size": len(m.latency_samples),
                "last_request_at": m.last_request_at,
                "last_error_at": m.last_error_at,
                "status": status,
                "status_label": _STATUS_LABELS[status],
            }

    uptime_seconds = round(time.time() - PROCESS_START_TIME, 1)

    return {
        "process_start_time": PROCESS_START_TIME,
        "uptime_seconds": uptime_seconds,
        "groups": groups,
        "messaging_subsystem": _messaging_subsystem_snapshot(),
        "note": (
            "Real, in-process request/error/latency counters grouped by "
            "which real NXTDeal subsystem each route belongs to -- IN-"
            "MEMORY ONLY, resets to zero on every process restart. This is "
            "live telemetry for this process's current uptime, not a "
            "historical record. 'no_traffic_yet' means this group genuinely "
            "hasn't been hit since this process started, not 'confirmed "
            "healthy.' See core/platform_metrics.py's own module docstring "
            "for the service-group mapping's full reasoning."
        ),
    }
