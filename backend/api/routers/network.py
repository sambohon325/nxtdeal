"""Network routes, extracted from api/app.py (CAF-00120, god_file_app_py --
splitting the monolithic app.py into per-domain routers).

Two distinct auth patterns live side by side in this one router, matching
how they were split in the original monolith:

1. Five Hub-facing "snapshot" routes (/network/anonymous-snapshot,
   /network/ai-management-snapshot, /network/operational-health-snapshot,
   /network/platform-metrics-snapshot, /network/storage-snapshot) are
   called server-to-server by the NXTDeal Hub, not by an employee session --
   gated by an X-Dealeros-Network-Key header (DEALEROS_NETWORK_KEY shared
   secret) checked INSIDE each underlying core/*_network_api.py function via
   check_network_key(), not by api.deps._authenticate(). No Authorization
   header is involved for these five at all.

2. The remaining eight routes (departments/benchmark/benchmark/{department}/
   peer-pools/audit, network-overview/regenerate-summary, network-advisors/
   catalog+ask) are normal employee-session routes, gated the usual way via
   Authorization: Bearer <token> + api.deps._authenticate().

These routes are NOT contiguous in the original app.py -- they were
interleaved with unrelated /compliance/*, /employees/*/value, and
/intelligence/* routes (a different domain, left in place in app.py).
"""

from fastapi import APIRouter, Header
from pydantic import BaseModel

from api.deps import _authenticate

from core.network_snapshot_api import get_anonymous_snapshot_api
from core.ai_management_network_api import get_ai_management_network_snapshot_api
from core.audit_network_api import get_operational_health_snapshot_api
from core.platform_metrics_network_api import get_platform_metrics_snapshot_api
from core.storage_snapshot_network_api import get_storage_snapshot_api
from core.onboarding_signals_network_api import get_onboarding_signals_snapshot_api
from core.module_adoption_network_api import get_module_adoption_snapshot_api
from core.ai_spend_network_api import get_ai_spend_snapshot_api

from core.network_benchmark import get_peer_pool_catalog

from core.network_api import (
    list_network_departments_api,
    get_network_benchmark_api,
    get_network_benchmarks_api,
    get_network_audit_api,
    NETWORK_ROLES
)

from core.network_overview_api import regenerate_network_summary_api

from core.network_advisors import ask_department_advisor, list_advisors

router = APIRouter()


class RegenerateNetworkSummaryRequest(BaseModel):

    polish: bool = True


class AskNetworkAdvisorRequest(BaseModel):

    department: str
    question: str


@router.get("/network/anonymous-snapshot")
def network_anonymous_snapshot(
    x_dealeros_network_key: str = Header(None)
):
    """Called by the NXTDeal Hub (hub/core/network_collector.py), server-to-server --
    not an employee session, so this is gated by a shared network key header rather
    than the usual Authorization: Bearer <token> + role check every other route in
    this file uses. See core/network_snapshot_api.py's module docstring for why this
    is a separate secret from both employee auth and the Hub's own admin key, and
    core/network_snapshot.py for the real KPI + privacy-bucketing + pseudonym
    mechanism behind the response itself."""

    return get_anonymous_snapshot_api(x_dealeros_network_key)


@router.get("/network/ai-management-snapshot")
def network_ai_management_snapshot(
    x_dealeros_network_key: str = Header(None)
):
    """Called by the NXTDeal Hub (hub/core/dealer_ai_management.py), server-to-
    server -- same DEALEROS_NETWORK_KEY shared secret as /network/anonymous-
    snapshot above, reused via core/network_snapshot_api.py's check_network_key().
    Unlike that route, this one is deliberately dealer-identified on the Hub side
    (Sam's own "AI Management... per dealer" ask, Dealer Management rebuild slice
    4 of 5) -- the same way hub/core/server_health.py's reachability check already
    ties directly back to one dealer_id. See core/ai_management_network_api.py's
    module docstring for the full reasoning. Returns only real, aggregate, non-PII
    per-feature enabled state + call-attempt counters (core/ai_management.py's
    build_ai_management_network_snapshot())."""

    return get_ai_management_network_snapshot_api(x_dealeros_network_key)


@router.get("/network/operational-health-snapshot")
def network_operational_health_snapshot(
    x_dealeros_network_key: str = Header(None)
):
    """Called by the NXTDeal Hub (hub/core/dealer_support.py), server-to-server --
    same DEALEROS_NETWORK_KEY shared secret as the two routes above, reused via
    core/network_snapshot_api.py's check_network_key(). Dealer Management rebuild
    slice 5 of 5 (Support Center). Returns ONLY coarse, aggregate, non-PII login/
    lockout counts over a trailing + prior 30-day window (core/
    audit_network_snapshot.py's build_operational_health_snapshot()) -- no employee
    id, name, IP, or per-event timestamp anywhere in the response."""

    return get_operational_health_snapshot_api(x_dealeros_network_key)


@router.get("/network/platform-metrics-snapshot")
def network_platform_metrics_snapshot(
    x_dealeros_network_key: str = Header(None)
):
    """Called by the NXTDeal Hub (hub/core/infra_services.py), server-to-
    server -- same DEALEROS_NETWORK_KEY shared secret as the three routes
    above, reused via core/network_snapshot_api.py's check_network_key().
    Infrastructure & Platform Operations rebuild, slice 1 of 4. Returns
    real, in-process request/error/latency counters per real NXTDeal
    service group (core/platform_metrics.py's get_platform_metrics_
    snapshot()) -- no PII, no endpoint URLs, no freeform text, IN-MEMORY
    ONLY (resets on this tenant process's own restart)."""

    return get_platform_metrics_snapshot_api(x_dealeros_network_key)


@router.get("/network/storage-snapshot")
def network_storage_snapshot(
    x_dealeros_network_key: str = Header(None)
):
    """Called by the NXTDeal Hub (hub/core/tenant_storage_metrics.py),
    server-to-server -- same DEALEROS_NETWORK_KEY shared secret as the four
    routes above, reused via core/network_snapshot_api.py's
    check_network_key(). Infrastructure & Platform Operations rebuild,
    slice 2 of 4 (Databases/Storage/Backups). Returns real file sizes and
    real entity/relationship/event/credential COUNTS for this tenant's own
    storage directory (core/storage_snapshot.py's get_storage_snapshot()) --
    no PII, no entity content, no raw credential data."""

    return get_storage_snapshot_api(x_dealeros_network_key)


@router.get("/network/onboarding-signals-snapshot")
def network_onboarding_signals_snapshot(x_dealeros_network_key: str = Header(None)):
    """Called by the NXTDeal Hub, server-to-server (Freemium roadmap, Phase 2). Replaces the Hub's
    manual Setup Wizard checkboxes with the tenant's real, auto-detected onboarding state -- same
    DEALEROS_NETWORK_KEY shared secret, reused via check_network_key(). Aggregate counts + boolean
    step state only (core/onboarding_signals.py). No PII."""

    return get_onboarding_signals_snapshot_api(x_dealeros_network_key)


@router.get("/network/module-adoption-snapshot")
def network_module_adoption_snapshot(x_dealeros_network_key: str = Header(None)):
    """Called by the NXTDeal Hub, server-to-server (Freemium roadmap, Phase 4). Places the dealer in
    the extended Dealer Lifecycle Funnel (Foundation Signup -> Foundation Active -> Module Adoption)
    from the tenant's own entitlement + data signal -- same DEALEROS_NETWORK_KEY shared secret via
    check_network_key(). No PII (core/module_adoption.py)."""

    return get_module_adoption_snapshot_api(x_dealeros_network_key)


@router.get("/network/ai-spend-snapshot")
def network_ai_spend_snapshot(x_dealeros_network_key: str = Header(None)):
    """Called by the NXTDeal Hub, server-to-server (Freemium roadmap, Phase 5). Aggregate AI-action
    consumption + BYO-key posture for metering an AI Workforce Module later -- same
    DEALEROS_NETWORK_KEY shared secret via check_network_key(). No PII, no prompt/response content
    (core/ai_spend.py)."""

    return get_ai_spend_snapshot_api(x_dealeros_network_key)


@router.get("/network/departments")
def network_departments(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_network_departments_api(payload["role"])


@router.get("/network/benchmark")
def network_benchmark_all(peer_pool: str = "default", authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_network_benchmarks_api(payload["role"], peer_pool=peer_pool)


@router.get("/network/benchmark/{department}")
def network_benchmark_one(
    department: str,
    peer_pool: str = "default",
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_network_benchmark_api(payload["role"], department, peer_pool=peer_pool)


@router.get("/network/peer-pools")
def network_peer_pools_route(authorization: str = Header(None)):
    """Real peer-pool catalog (core/network_benchmark.py's get_peer_pool_catalog(),
    2026-07-18 Peer Groups slice) -- backs the frontend's pool selector dropdown
    without needing a full benchmark fetch just to list the options."""

    payload, error = _authenticate(authorization)
    if error:
        return error

    if payload["role"] not in NETWORK_ROLES:
        return {"error": "You don't have access to the network with your current role -- Admin, Operations, or Finance can open it."}

    return get_peer_pool_catalog()


@router.get("/network/audit")
def network_audit(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_network_audit_api(payload["role"])


# ---------------------------------------------------------------------------
# Network Overview / Opportunities -- Intelligence Network reframe, slice 1
# (core/network_opportunity_value.py / core/network_overview_api.py). No new
# route was needed for the base overview()/opportunities() views themselves
# (both are served by the existing generic GET /menu/data?department=Network&
# item_key=overview|opportunities path via core/menu_data.py's unchanged
# network_overview/network_opportunities aliases, which now return the real
# dollar-denominated opportunity layer alongside the existing content) -- this
# one route backs the dedicated board's own on-demand "regenerate the
# Executive Summary" action (POST because the optional AI-polish path makes a
# real outbound call, even though nothing is ever mutated on the graph).
# Deliberately reuses the same NETWORK_ROLES tier (ADMIN/OPERATIONS/FINANCE)
# every other Network route already uses.
# ---------------------------------------------------------------------------

@router.post("/network-overview/regenerate-summary")
def network_overview_regenerate_summary_route(request: RegenerateNetworkSummaryRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return regenerate_network_summary_api(payload["role"], polish=request.polish)


# ---------------------------------------------------------------------------
# Network AI Advisors -- Intelligence Network reframe, slice 6
# (core/network_advisors.py). 5 real, department-specific Q&A advisors
# (Sales/Service/Parts/F&I/BHPH). No hard role gate at the route level, same
# convention every other Network menu-item function already follows -- role
# is passed straight through to the real sub-calls this module composes
# (get_network_benchmark_api/gap_analysis/get_root_causes), each of which
# already enforces its own real ACL and degrades gracefully per field for an
# insufficient role rather than failing the whole response.
# ---------------------------------------------------------------------------

@router.get("/network-advisors/catalog")
def network_advisors_catalog(authorization: str = Header(None)):

    _, error = _authenticate(authorization)
    if error:
        return error

    return {"advisors": list_advisors()}


@router.post("/network-advisors/ask")
def network_advisors_ask(request: AskNetworkAdvisorRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return ask_department_advisor(
        request.department,
        request.question,
        payload["role"],
        employee_id=payload.get("employee_id"),
    )
