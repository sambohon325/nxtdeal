"""
Phase 6 (2026-08-03): MySales adoption signal — rep usage tracking + Readiness conversion
signals (warm targets = active MySales reps at dealerships not yet on NXTDeal). Run from
backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core import mysales_adoption as ma
from core import mysales_adoption_api as ma_api


@pytest.fixture(autouse=True)
def fresh():
    ledger.reset()
    yield
    ledger.reset()


def test_record_activity_maintains_one_record_per_rep():
    ma.record_activity("REP-1", dealership_id="D-1", action="open")
    ma.record_activity("REP-1", dealership_id="D-1", action="inventory")
    ma.record_activity("REP-1", dealership_id="D-1", action="open")
    summary = ma.get_adoption_summary()
    assert summary["active_reps"] == 1
    assert summary["total_activity"] == 3


def test_conversion_signals_flag_warm_non_dealeros_dealers():
    # D-WARM has two active reps, not on NXTDeal -> warm target.
    ma.record_activity("REP-1", dealership_id="D-WARM", dealership_on_dealeros=False)
    ma.record_activity("REP-2", dealership_id="D-WARM", dealership_on_dealeros=False)
    # D-ON is already on NXTDeal -> not a warm target.
    ma.record_activity("REP-3", dealership_id="D-ON", dealership_on_dealeros=True)

    signals = ma.get_conversion_signals()
    assert signals["warm_count"] == 1
    warm = signals["warm_conversion_targets"][0]
    assert warm["dealership_id"] == "D-WARM" and warm["rep_count"] == 2
    # D-ON appears in dealers but not in warm targets.
    assert any(d["dealership_id"] == "D-ON" for d in signals["dealers"])
    assert all(d["dealership_id"] != "D-ON" for d in signals["warm_conversion_targets"])


def test_min_reps_filter():
    ma.record_activity("REP-1", dealership_id="D-1", dealership_on_dealeros=False)
    assert ma.get_conversion_signals(min_reps=2)["warm_count"] == 0
    ma.record_activity("REP-2", dealership_id="D-1", dealership_on_dealeros=False)
    assert ma.get_conversion_signals(min_reps=2)["warm_count"] == 1


def test_api_signals_require_readiness_role():
    from core.permissions import ADMIN, SALES
    ma.record_activity("REP-1", dealership_id="D-1", dealership_on_dealeros=False)
    assert "error" in ma_api.get_conversion_signals_api(SALES)
    assert "warm_count" in ma_api.get_conversion_signals_api(ADMIN)
    # Recording is self-service (any role records their own usage).
    assert "activity_count" in ma_api.record_activity_api(SALES, "REP-9", dealership_id="D-2")


def test_record_activity_requires_rep():
    assert "error" in ma.record_activity("")
