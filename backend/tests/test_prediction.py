"""
Tests for core/prediction.py -- the shared prediction/confidence engine (session 37).
Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

from datetime import date, timedelta

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import VEHICLE

from core import prediction


@pytest.fixture(autouse=True)
def fresh_ledger():

    ledger.reset()

    yield

    ledger.reset()


def _add_vehicle(vehicle_id, date_sold):

    ledger.add_entity(Entity(
        id=vehicle_id,
        entity_type=VEHICLE,
        attributes={"DateSold": date_sold.isoformat() if date_sold else ""}
    ))


def test_predict_unknown_department_returns_none():
    assert prediction.predict("not-a-real-department", "week") is None


def test_predict_unknown_horizon_returns_none():
    assert prediction.predict("sales", "not-a-real-horizon") is None


def test_predict_no_data_is_industry_estimate():

    result = prediction.predict("sales", "week")

    assert result["sample_size"] == 0
    assert result["basis"] == "industry_estimate"
    assert result["confidence_pct"] < 50


def test_predict_rich_recent_data_is_ledger_basis():

    today = date.today()

    for i in range(40):
        _add_vehicle(f"VEH-{i:05}", today - timedelta(days=i % 30))

    result = prediction.predict("sales", "week")

    assert result["sample_size"] >= 30
    assert result["basis"] == "ledger"
    assert result["confidence_pct"] > 70


def test_predict_sparse_old_data_is_low_confidence():

    old_date = date.today() - timedelta(days=200)
    _add_vehicle("VEH-00001", old_date)

    result = prediction.predict("sales", "tomorrow")

    assert result["sample_size"] == 0  # outside the lookback window entirely
    assert result["basis"] == "industry_estimate"


def test_predict_blended_basis_with_partial_data():

    today = date.today()

    for i in range(10):
        _add_vehicle(f"VEH-{i:05}", today - timedelta(days=i))

    result = prediction.predict("sales", "week")

    assert result["basis"] == "blended"
    assert 0 < result["sample_size"] < 30


def test_predicted_value_is_nonnegative():

    result = prediction.predict("sales", "month")
    assert result["predicted_value"] >= 0


def test_predict_all_horizons_returns_four_results():

    results = prediction.predict_all_horizons("sales")
    assert len(results) == 4
    assert {r["horizon"] for r in results} == set(prediction.HORIZONS.keys())


def test_department_readiness_uses_tomorrow_horizon():

    today = date.today()
    for i in range(40):
        _add_vehicle(f"VEH-{i:05}", today - timedelta(days=i % 5))

    readiness = prediction.department_readiness("sales")

    assert readiness["department"] == "sales"
    assert readiness["threshold"] == prediction.GO_LIVE_CONFIDENCE_THRESHOLD
    assert isinstance(readiness["ready"], bool)


def test_department_readiness_unknown_department_returns_none():
    assert prediction.department_readiness("not-a-real-department") is None


def test_all_departments_readiness_covers_every_department():

    results = prediction.all_departments_readiness()
    assert len(results) == len(prediction.DEPARTMENTS)
