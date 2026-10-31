"""
NXTDeal Hub -- real, lightweight, in-process request/error/latency
instrumentation for the Hub's OWN routes. Infrastructure & Platform
Operations rebuild, slice 1 of 4.

Mirrors backend/core/platform_metrics.py's exact shape and honesty posture
(in-memory only, resets on restart, real route-group mapping, no fabricated
telemetry) -- kept as a SEPARATE module rather than imported directly
because the Hub and the tenant backend each have their own same-named
`core` package on `sys.path` (see CLAUDE.md's NXTDeal Hub section for the
established "run from within hub/, not backend/" import-collision lesson).

Every Hub route lives under /hub/{segment}/... (with the sole exception of
the root "/" health-check), so the group is derived from the first TWO
path segments rather than one, e.g. "/hub/dealer-management/modules/..."
groups as "dealer_management", "/hub/network/overview" groups as
"network_aggregation".
"""

import time
from collections import defaultdict, deque
from threading import Lock
from datetime import datetime, timezone


PROCESS_START_TIME = time.time()

_MAX_LATENCY_SAMPLES = 200


ROUTE_GROUP_CATALOG = {
    "root": "Hub Root / Health Check",
    "dealer_management": "Dealer Management Console",
    "hub_dealers": "Dealer Provisioning & Registry",
    "network_aggregation": "Network Aggregation & Anonymized Analytics",
    "noc": "Network Operations Center",
    "server_health": "Server Health (Legacy Reachability Checks)",
    "infra": "Infrastructure & Platform Operations",
    "other": "Other / Uncategorized",
}


_PREFIX_TO_GROUP = {
    ("hub", "dealer-management"): "dealer_management",
    ("hub", "dealers"): "hub_dealers",
    ("hub", "network"): "network_aggregation",
    ("hub", "noc"): "noc",
    ("hub", "health"): "server_health",
    ("hub", "infra"): "infra",
}


def _group_for_path(path):
    segments = [s for s in path.split("/") if s]
    if not segments:
        return "root"
    if len(segments) == 1:
        return _PREFIX_TO_GROUP.get((segments[0],), "other")
    return _PREFIX_TO_GROUP.get((segments[0], segments[1]), "other")


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
    return datetime.now(timezone.utc).isoformat()


def record_request(path, status_code, latency_ms):
    """Called once per real HTTP request by app.py's @app.middleware("http")
    hook -- increments the real in-memory counters for whichever Hub
    service group this path belongs to. Never raises."""

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


def get_hub_platform_metrics_snapshot():
    """Real per-service-group request/error/latency metrics for the Hub
    process itself, since it started. In-memory only -- resets on restart."""

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
        "note": (
            "Real, in-process request/error/latency counters for the Hub's "
            "own routes, grouped by Hub subsystem -- IN-MEMORY ONLY, resets "
            "to zero on every Hub process restart. Mirrors backend/core/"
            "platform_metrics.py's exact honesty posture for the tenant "
            "side."
        ),
    }
