"""
Tests for the Network intelligence layer (core/network_benchmark.py,
core/network_audit.py, core/network_api.py) -- session 38. Run from backend/ with
`pytest`.
"""

import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

from datetime import date

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import VEHICLE, PART, NETWORK_PEER_SNAPSHOT
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, FINANCE

from core import network_benchmark
from core import network_audit
from core import network_api


TODAY = date.today()


@pytest.fixture(autouse=True)
def fresh_ledger():

    ledger.reset()

    yield

    ledger.reset()


def _add_sold_vehicle(vehicle_id, price, cost):

    ledger.add_entity(Entity(
        id=vehicle_id,
        entity_type=VEHICLE,
        attributes={"Price": str(price), "Cost": str(cost), "DateSold": TODAY.isoformat()},
    ))


# ---------------------------------------------------------------------------
# seed_peer_snapshots / benchmark_department
# ---------------------------------------------------------------------------

def test_seed_peer_snapshots_creates_one_per_peer_per_department():

    network_benchmark.seed_peer_snapshots()

    all_snapshots = [
        e for e in ledger.get_all().values()
        if e.entity_type == NETWORK_PEER_SNAPSHOT
    ]

    assert len(all_snapshots) == len(network_benchmark.DEPARTMENTS) * sum(len(pool["profiles"]) for pool in network_benchmark.PEER_POOLS.values())


def test_seed_peer_snapshots_is_idempotent():

    network_benchmark.seed_peer_snapshots()
    first_count = len(ledger.get_all())

    network_benchmark.seed_peer_snapshots()
    second_count = len(ledger.get_all())

    assert first_count == second_count


def test_benchmark_department_unknown_returns_none():

    assert network_benchmark.benchmark_department("not-a-department") is None


def test_benchmark_department_percentile_independent_of_own_value():
    """The bug this module's docstring calls out: percentile must NOT be a tautology
    where a dealer always beats exactly the peers whose multiplier is below 1.0
    regardless of its own real performance. Verifies a small dealer (well below the
    fixed baseline anchor) scores near the bottom, not automatically at 50%."""

    _add_sold_vehicle("VEH-00001", price=21000, cost=20000)  # $1,000 real gross profit

    result = network_benchmark.benchmark_department("sales")

    assert result is not None
    assert result["percentile_rank"] == 0.0  # $1k is nowhere near the $150k+ peer anchors


def test_benchmark_department_percentile_improves_with_real_performance():

    _add_sold_vehicle("VEH-00002", price=250000, cost=50000)  # $200k real gross profit

    result = network_benchmark.benchmark_department("sales")

    # $200k beats the Dealer C (135k) and Dealer D (153k) fixed targets, at minimum.
    assert result["percentile_rank"] >= 50.0


def test_benchmark_department_peers_are_blind_labeled():

    result = network_benchmark.benchmark_department("sales")

    labels = [p["label"] for p in result["peers"]]

    assert set(labels) == set(network_benchmark.PEER_LABELS)

    for label in labels:
        assert label.startswith("Dealer ")


def test_benchmark_department_basis_notice_present():

    result = network_benchmark.benchmark_department("sales")

    assert "SIMULATED" in result["basis_notice"]


def test_all_departments_benchmark_covers_every_department():

    results = network_benchmark.all_departments_benchmark()

    assert {r["department"] for r in results} == set(network_benchmark.DEPARTMENTS) | {"bhph"}
    assert all(r is not None for r in results)


# ---------------------------------------------------------------------------
# network_audit.run_audit
# ---------------------------------------------------------------------------

def test_run_audit_flags_low_percentile_department():

    _add_sold_vehicle("VEH-00003", price=21000, cost=20000)  # tiny gross -> low percentile

    result = network_audit.run_audit()

    benchmark_recs = [r for r in result["recommendations"] if r["category"] == "network_benchmark"]

    assert any(r["department"] == "sales" for r in benchmark_recs)


def test_run_audit_flags_obsolete_parts():

    ledger.add_entity(Entity(
        id="PART-00001",
        entity_type=PART,
        attributes={"PartNumber": "P1", "QuantityOnHand": "10", "UnitCost": "50", "ReceivedDate": "2020-01-01"},
    ))

    result = network_audit.run_audit()

    profit_leak_recs = [r for r in result["recommendations"] if r["category"] == "profit_leak"]

    assert any(r["department"] == "parts" for r in profit_leak_recs)


def test_run_audit_flags_high_automation_employee(monkeypatch):

    fake_employee = {
        "employee_id": "EMP-00001",
        "name": "Test Employee",
        "department": "sales",
        "basis": "ledger",
        "automation_coverage": {"distinct_task_types": 2, "automatable_task_types": 2, "automation_pct": 100.0},
    }

    monkeypatch.setattr(network_audit, "list_employee_values", lambda: [fake_employee])

    result = network_audit.run_audit()

    automation_recs = [r for r in result["recommendations"] if r["category"] == "automation_opportunity"]

    assert len(automation_recs) == 1
    assert "not a headcount recommendation" in automation_recs[0]["recommendation"]


def test_run_audit_recommendations_sorted_by_severity():

    _add_sold_vehicle("VEH-00004", price=21000, cost=20000)

    ledger.add_entity(Entity(
        id="PART-00002",
        entity_type=PART,
        attributes={"PartNumber": "P2", "QuantityOnHand": "10", "UnitCost": "50", "ReceivedDate": "2020-01-01"},
    ))

    result = network_audit.run_audit()

    severities = [r["severity"] for r in result["recommendations"]]
    order = {"high": 0, "medium": 1, "low": 2}

    assert severities == sorted(severities, key=lambda s: order.get(s, 3))


def test_run_audit_has_generated_at_and_count():

    result = network_audit.run_audit()

    assert "generated_at" in result
    assert result["recommendation_count"] == len(result["recommendations"])


# ---------------------------------------------------------------------------
# ACL (network_api.py)
# ---------------------------------------------------------------------------

def test_get_network_benchmark_api_denied_for_sales():

    result = network_api.get_network_benchmark_api(SALES, "sales")
    assert "error" in result


def test_get_network_benchmark_api_allowed_for_finance():

    result = network_api.get_network_benchmark_api(FINANCE, "sales")
    assert "percentile_rank" in result


def test_get_network_audit_api_denied_for_marketing():

    result = network_api.get_network_audit_api(MARKETING)
    assert "error" in result


def test_get_network_audit_api_allowed_for_admin():

    result = network_api.get_network_audit_api(ADMIN)
    assert "recommendations" in result


def test_list_network_departments_api_allowed_for_operations():

    result = network_api.list_network_departments_api(OPERATIONS)
    assert isinstance(result, list)
    assert {r["key"] for r in result} == set(network_benchmark.DEPARTMENTS) | {"bhph"}
