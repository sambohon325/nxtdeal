"""
ACL layer for the Network intelligence layer (2026-07-13, session 38) -- imported
directly into api/app.py's route handlers, same "no service layer indirection"
convention every other `*_api.py` module in this codebase follows.

Role rule: reuses Department Intelligence's exact ACL tier (ADMIN/OPERATIONS/FINANCE,
core/department_intelligence_api.py's DEPT_INTEL_ROLES) since this is built directly on
top of the same cross-department profit/margin data, just benchmarked against
(simulated) peers.

Enriched 2026-07-18 (Network's "NXTDeal Intelligence Network" reframe, slice 2 --
Peer Groups + Benchmarks): get_network_benchmark_api()/get_network_benchmarks_api()
now accept an optional peer_pool (default "default", fully backward compatible --
every existing caller that doesn't pass one gets the exact same peer set as before),
and get_network_benchmarks_api() also returns the real peer-pool catalog
(core/network_benchmark.py's get_peer_pool_catalog()) alongside the department list.
DEPARTMENTS below is extended with the new real "bhph" benchmark entry for the
department-not-found check only -- core/network_benchmark.py's own DEPARTMENTS
constant (department_intelligence's 5 keys) is left untouched, since seed_peer_
snapshots()/all_departments_benchmark() both handle "bhph" as a special case
internally, not a 6th entry in that list.
"""

from core.permissions import ADMIN, OPERATIONS, FINANCE
from core.department_intelligence import list_departments as list_intelligence_departments
from core.network_benchmark import (
    DEPARTMENTS,
    BHPH_DEPARTMENT_KEY,
    DEFAULT_PEER_POOL,
    benchmark_department,
    all_departments_benchmark,
    get_peer_pool_catalog,
)
from core.network_audit import run_audit


NETWORK_ROLES = (ADMIN, OPERATIONS, FINANCE)

_FORBIDDEN = {
    "error": "You don't have access to the network with your current role -- Admin, "
    "Operations, or Finance can open it."
}

_ALL_BENCHMARK_DEPARTMENTS = list(DEPARTMENTS) + [BHPH_DEPARTMENT_KEY]


def list_network_departments_api(role):

    if role not in NETWORK_ROLES:
        return _FORBIDDEN

    all_titles = {d["key"]: d for d in list_intelligence_departments()}

    entries = [all_titles[key] for key in DEPARTMENTS if key in all_titles]
    entries.append({
        "key": BHPH_DEPARTMENT_KEY,
        "title": "BHPH / Loan Portfolio",
        "subtitle": "Real portfolio delinquency, repossession, recovery, and yield performance.",
    })

    return entries


def get_network_benchmark_api(role, department, peer_pool=DEFAULT_PEER_POOL):

    if role not in NETWORK_ROLES:
        return _FORBIDDEN

    if department not in _ALL_BENCHMARK_DEPARTMENTS:
        return {"error": f"Unknown department '{department}'"}

    return benchmark_department(department, role=role, peer_pool=peer_pool)


def get_network_benchmarks_api(role, peer_pool=DEFAULT_PEER_POOL):

    if role not in NETWORK_ROLES:
        return _FORBIDDEN

    return {
        "departments": all_departments_benchmark(role=role, peer_pool=peer_pool),
        "peer_pool": peer_pool if peer_pool in {p["key"] for p in get_peer_pool_catalog()} else DEFAULT_PEER_POOL,
        "peer_pools": get_peer_pool_catalog(),
    }


def get_network_audit_api(role):

    if role not in NETWORK_ROLES:
        return _FORBIDDEN

    return run_audit()
