"""
Test coverage for core/network_trends.py -- Network's real 90-day KPI history +
linear-projection engine, plus the bhph-department analog of Department
Intelligence's own day-over-day with_trend() mechanism.

get_bhph_kpis_with_trend()'s own real dependency, core/network_benchmark.py's
compute_bhph_kpis(), has a deep real chain (Portfolio dashboard -> loan
accounting -> repossessions) -- rather than build fixtures for all of that,
compute_bhph_kpis is monkeypatched directly to a canned, but real-shaped,
payload (confirmed against the actual function's own return statement: a
{"department", "title", "subtitle", "capabilities", "kpis", "raw"} dict whose
"kpis" values are each core/department_intelligence.py's own
kpi(key, label, value, format, suffix) shape). This module's own with_trend()-
wrapping logic is the real target here, not compute_bhph_kpis()'s own math
(which belongs to core/network_benchmark.py's own test file).

Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date, timedelta

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import DEPARTMENT_SNAPSHOT

import core.network_trends as nt
import core.kpi_snapshots as kpi_snapshots_module


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield
    ledger.reset()


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    # with_trend() -> record_snapshot() calls save_graph() at the
    # core.kpi_snapshots module level -- NOT core.network_trends, which never
    # imports save_graph at all.
    monkeypatch.setattr(kpi_snapshots_module, "save_graph", lambda filepath: None)


def _snapshot(sid, department, snapshot_date, kpis):
    ledger.add_entity(Entity(id=sid, entity_type=DEPARTMENT_SNAPSHOT, attributes={
        "department": department,
        "snapshot_date": snapshot_date,
        "kpis": kpis,
        "recorded_at": snapshot_date + "T00:00:00+00:00",
    }))
    return ledger.get_entity(sid)


def _fake_bhph_payload():
    return {
        "department": "bhph",
        "title": "BHPH / Loan Portfolio",
        "subtitle": "Real portfolio delinquency, repossession, recovery, and yield performance.",
        "capabilities": [],
        "kpis": {
            "yield_pct": {"key": "yield_pct", "label": "Portfolio Yield", "value": 5.0, "format": "percent", "suffix": None},
            "delinquency_rate_pct": {"key": "delinquency_rate_pct", "label": "Delinquency Rate", "value": 12.0, "format": "percent", "suffix": None},
        },
        "raw": {"total_loans": 100},
    }


class TestModuleConstants:

    def test_all_trend_departments_includes_bhph(self):
        assert "bhph" in nt.ALL_TREND_DEPARTMENTS

    def test_all_trend_departments_includes_benchmark_departments(self):
        from core.network_benchmark import DEPARTMENTS as BENCHMARK_DEPARTMENTS
        for dept in BENCHMARK_DEPARTMENTS:
            assert dept in nt.ALL_TREND_DEPARTMENTS


class TestGetBhphKpisWithTrend:

    def test_returns_none_when_compute_bhph_kpis_returns_none(self, monkeypatch):
        monkeypatch.setattr(nt, "compute_bhph_kpis", lambda role: None)
        assert nt.get_bhph_kpis_with_trend(role="SALES") is None

    def test_first_ever_call_has_no_history(self, monkeypatch):
        monkeypatch.setattr(nt, "compute_bhph_kpis", lambda role: _fake_bhph_payload())

        result = nt.get_bhph_kpis_with_trend(role="ADMIN")

        assert result is not None
        assert isinstance(result["kpis"], list)

        yield_kpi = next(k for k in result["kpis"] if k["key"] == "yield_pct")
        assert yield_kpi["has_history"] is False
        assert yield_kpi["delta_pct"] is None
        assert yield_kpi["compared_to"] is None

    def test_first_ever_call_creates_a_real_snapshot(self, monkeypatch):
        monkeypatch.setattr(nt, "compute_bhph_kpis", lambda role: _fake_bhph_payload())

        nt.get_bhph_kpis_with_trend(role="ADMIN")

        snap = kpi_snapshots_module.find_snapshot("bhph")
        assert snap is not None
        assert snap.attributes["kpis"]["yield_pct"] == 5.0
        assert snap.attributes["kpis"]["delinquency_rate_pct"] == 12.0

    def test_with_prior_snapshot_computes_real_delta(self, monkeypatch):
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        _snapshot("SNAP-PRIOR", "bhph", yesterday, {"yield_pct": 4.0, "delinquency_rate_pct": 10.0})

        monkeypatch.setattr(nt, "compute_bhph_kpis", lambda role: _fake_bhph_payload())

        result = nt.get_bhph_kpis_with_trend(role="ADMIN")
        kpis = {k["key"]: k for k in result["kpis"]}

        # (5.0 - 4.0) / 4.0 * 100 = 25.0
        assert kpis["yield_pct"]["has_history"] is True
        assert kpis["yield_pct"]["delta_pct"] == 25.0
        assert kpis["yield_pct"]["compared_to"] == yesterday

        # (12.0 - 10.0) / 10.0 * 100 = 20.0
        assert kpis["delinquency_rate_pct"]["delta_pct"] == 20.0

    def test_payload_shape_beyond_kpis_is_preserved(self, monkeypatch):
        monkeypatch.setattr(nt, "compute_bhph_kpis", lambda role: _fake_bhph_payload())
        result = nt.get_bhph_kpis_with_trend(role="ADMIN")
        assert result["department"] == "bhph"
        assert result["title"] == "BHPH / Loan Portfolio"


class TestDepartmentSnapshots:

    def test_filters_by_department(self):
        _snapshot("SNAP-1", "sales", "2026-01-01", {"a": 1})
        _snapshot("SNAP-2", "service", "2026-01-01", {"a": 1})

        result = nt._department_snapshots("sales")

        assert len(result) == 1
        assert result[0].id == "SNAP-1"

    def test_since_date_filters_out_older_snapshots(self):
        _snapshot("SNAP-1", "sales", "2026-01-01", {"a": 1})
        _snapshot("SNAP-2", "sales", "2026-06-01", {"a": 1})

        result = nt._department_snapshots("sales", since_date="2026-03-01")

        assert [s.id for s in result] == ["SNAP-2"]

    def test_since_date_is_inclusive_of_the_boundary(self):
        _snapshot("SNAP-1", "sales", "2026-03-01", {"a": 1})

        result = nt._department_snapshots("sales", since_date="2026-03-01")

        assert [s.id for s in result] == ["SNAP-1"]

    def test_sorted_oldest_first_regardless_of_insertion_order(self):
        _snapshot("SNAP-LATE", "sales", "2026-06-01", {"a": 1})
        _snapshot("SNAP-EARLY", "sales", "2026-01-01", {"a": 1})

        result = nt._department_snapshots("sales")

        assert [s.id for s in result] == ["SNAP-EARLY", "SNAP-LATE"]

    def test_empty_when_no_snapshots_exist(self):
        assert nt._department_snapshots("sales") == []

    def test_ignores_other_entity_types(self):
        ledger.add_entity(Entity(id="VEH-1", entity_type="Vehicle", attributes={"department": "sales"}))
        assert nt._department_snapshots("sales") == []


class TestGetKpiHistory:

    def test_only_includes_snapshots_containing_the_kpi_key(self):
        today = date.today()
        d0 = (today - timedelta(days=10)).isoformat()
        d1 = (today - timedelta(days=5)).isoformat()

        _snapshot("SNAP-1", "sales", d0, {"close_rate": 20.0})
        _snapshot("SNAP-2", "sales", d1, {"show_rate": 60.0})

        history = nt.get_kpi_history("sales", "close_rate", days=90)

        assert history["days_with_data"] == 1
        assert history["points"] == [{"date": d0, "value": 20.0}]

    def test_days_requested_vs_days_with_data_honestly_distinguished(self):
        today = date.today()
        d0 = (today - timedelta(days=5)).isoformat()
        _snapshot("SNAP-1", "sales", d0, {"close_rate": 20.0})

        history = nt.get_kpi_history("sales", "close_rate", days=90)

        assert history["days_requested"] == 90
        assert history["days_with_data"] == 1

    def test_excludes_snapshots_outside_the_window(self):
        today = date.today()
        d_old = (today - timedelta(days=200)).isoformat()
        d_recent = (today - timedelta(days=10)).isoformat()

        _snapshot("SNAP-OLD", "sales", d_old, {"close_rate": 10.0})
        _snapshot("SNAP-RECENT", "sales", d_recent, {"close_rate": 20.0})

        history = nt.get_kpi_history("sales", "close_rate", days=90)

        assert history["days_with_data"] == 1
        assert history["points"][0]["date"] == d_recent

    def test_points_are_date_ordered(self):
        today = date.today()
        d0 = (today - timedelta(days=10)).isoformat()
        d1 = (today - timedelta(days=5)).isoformat()

        _snapshot("SNAP-LATE", "sales", d1, {"close_rate": 25.0})
        _snapshot("SNAP-EARLY", "sales", d0, {"close_rate": 20.0})

        history = nt.get_kpi_history("sales", "close_rate", days=90)

        assert [p["date"] for p in history["points"]] == [d0, d1]

    def test_no_snapshots_at_all_returns_empty_points(self):
        history = nt.get_kpi_history("sales", "close_rate", days=90)
        assert history["points"] == []
        assert history["days_with_data"] == 0

    def test_department_and_kpi_key_are_echoed_back(self):
        history = nt.get_kpi_history("sales", "close_rate", days=90)
        assert history["department"] == "sales"
        assert history["kpi"] == "close_rate"


class TestGetDepartmentTrendHistory:

    def test_unions_kpi_keys_seen_across_snapshots(self):
        today = date.today()
        d0 = (today - timedelta(days=10)).isoformat()
        d1 = (today - timedelta(days=5)).isoformat()

        _snapshot("SNAP-1", "sales", d0, {"close_rate": 20.0})
        _snapshot("SNAP-2", "sales", d1, {"show_rate": 60.0})

        result = nt.get_department_trend_history("sales", days=90)

        assert set(result["kpis"].keys()) == {"close_rate", "show_rate"}

    def test_each_kpi_gets_its_own_real_history(self):
        today = date.today()
        d0 = (today - timedelta(days=10)).isoformat()
        _snapshot("SNAP-1", "sales", d0, {"close_rate": 20.0, "show_rate": 55.0})

        result = nt.get_department_trend_history("sales", days=90)

        assert result["kpis"]["close_rate"]["points"] == [{"date": d0, "value": 20.0}]
        assert result["kpis"]["show_rate"]["points"] == [{"date": d0, "value": 55.0}]

    def test_days_with_data_reflects_snapshot_count_not_kpi_count(self):
        today = date.today()
        d0 = (today - timedelta(days=10)).isoformat()
        _snapshot("SNAP-1", "sales", d0, {"close_rate": 20.0, "show_rate": 55.0})

        result = nt.get_department_trend_history("sales", days=90)

        assert result["days_with_data"] == 1

    def test_no_snapshots_returns_empty_kpi_dict(self):
        result = nt.get_department_trend_history("sales", days=90)
        assert result["kpis"] == {}
        assert result["days_with_data"] == 0


class TestLinearSlope:

    def test_none_when_zero_points(self):
        assert nt._linear_slope([]) is None

    def test_none_when_exactly_one_point(self):
        assert nt._linear_slope([{"date": "2026-01-01", "value": 10.0}]) is None

    def test_none_when_all_points_on_same_day(self):
        points = [
            {"date": "2026-01-01", "value": 10.0},
            {"date": "2026-01-01", "value": 20.0},
        ]
        assert nt._linear_slope(points) is None

    def test_correct_ols_slope_for_a_clean_line(self):
        points = [
            {"date": "2026-01-01", "value": 100.0},
            {"date": "2026-01-11", "value": 110.0},
            {"date": "2026-01-21", "value": 120.0},
        ]
        assert nt._linear_slope(points) == pytest.approx(1.0)

    def test_zero_slope_for_a_constant_series(self):
        points = [
            {"date": "2026-01-01", "value": 25.0},
            {"date": "2026-01-06", "value": 25.0},
            {"date": "2026-01-11", "value": 25.0},
        ]
        assert nt._linear_slope(points) == pytest.approx(0.0)

    def test_ignores_points_with_non_numeric_value(self):
        points = [
            {"date": "2026-01-01", "value": None},
            {"date": "2026-01-11", "value": 110.0},
            {"date": "2026-01-21", "value": 120.0},
        ]
        # only the 2 real numeric points remain -- still computable
        assert nt._linear_slope(points) == pytest.approx(1.0)

    def test_ignores_points_with_missing_date(self):
        points = [
            {"value": 50.0},
            {"date": "2026-01-11", "value": 110.0},
            {"date": "2026-01-21", "value": 120.0},
        ]
        assert nt._linear_slope(points) == pytest.approx(1.0)


class TestProjectKpiForward:

    def test_not_projectable_with_zero_snapshots(self):
        result = nt.project_kpi_forward("sales", "close_rate", days_history=90, project_days=30)

        assert result["projectable"] is False
        assert result["days_with_data"] == 0
        assert result["current_value"] is None
        assert result["projected_value"] is None
        assert "0 real recorded snapshot day(s)" in result["reason"]

    def test_not_projectable_with_exactly_one_snapshot(self):
        today = date.today()
        d0 = (today - timedelta(days=5)).isoformat()
        _snapshot("SNAP-1", "sales", d0, {"close_rate": 22.5})

        result = nt.project_kpi_forward("sales", "close_rate", days_history=90, project_days=30)

        assert result["projectable"] is False
        assert result["days_with_data"] == 1
        assert result["current_value"] == 22.5
        assert result["slope_per_day"] is None
        assert "1 real recorded snapshot day(s)" in result["reason"]

    def test_real_ols_projection_with_a_clean_rising_trend(self):
        today = date.today()
        d0 = today - timedelta(days=10)
        d1 = today - timedelta(days=5)
        d2 = today

        _snapshot("SNAP-1", "sales", d0.isoformat(), {"close_rate": 20.0})
        _snapshot("SNAP-2", "sales", d1.isoformat(), {"close_rate": 25.0})
        _snapshot("SNAP-3", "sales", d2.isoformat(), {"close_rate": 30.0})

        result = nt.project_kpi_forward("sales", "close_rate", days_history=90, project_days=30)

        assert result["projectable"] is True
        assert result["reason"] is None
        assert result["days_with_data"] == 3
        assert result["current_value"] == 30.0
        assert result["current_date"] == d2.isoformat()
        assert result["slope_per_day"] == pytest.approx(1.0)
        assert result["projected_value"] == pytest.approx(60.0)
        assert result["target_date"] == (d2 + timedelta(days=30)).isoformat()
        assert result["project_days"] == 30
        assert result["basis"] == "real_linear_projection"

    def test_zero_slope_projects_flat(self):
        today = date.today()
        d0 = today - timedelta(days=10)
        d1 = today - timedelta(days=5)
        d2 = today

        _snapshot("SNAP-1", "finance", d0.isoformat(), {"funding_delays": 40.0})
        _snapshot("SNAP-2", "finance", d1.isoformat(), {"funding_delays": 40.0})
        _snapshot("SNAP-3", "finance", d2.isoformat(), {"funding_delays": 40.0})

        result = nt.project_kpi_forward("finance", "funding_delays", days_history=90, project_days=30)

        assert result["projectable"] is True
        assert result["slope_per_day"] == pytest.approx(0.0)
        assert result["projected_value"] == pytest.approx(40.0)


class TestProjectGapClosure:

    def _seed_rising_series(self, department="sales", kpi_key="close_rate"):
        today = date.today()
        d0 = today - timedelta(days=10)
        d1 = today - timedelta(days=5)
        d2 = today
        _snapshot("SNAP-1", department, d0.isoformat(), {kpi_key: 20.0})
        _snapshot("SNAP-2", department, d1.isoformat(), {kpi_key: 25.0})
        _snapshot("SNAP-3", department, d2.isoformat(), {kpi_key: 30.0})
        # current_value=30.0, projected_value (30 days out) = 60.0

    def _seed_flat_series(self, department="finance", kpi_key="funding_delays", value=40.0):
        today = date.today()
        d0 = today - timedelta(days=10)
        d1 = today - timedelta(days=5)
        d2 = today
        _snapshot("SNAP-1", department, d0.isoformat(), {kpi_key: value})
        _snapshot("SNAP-2", department, d1.isoformat(), {kpi_key: value})
        _snapshot("SNAP-3", department, d2.isoformat(), {kpi_key: value})

    def test_unknown_when_not_projectable(self):
        result = nt.project_gap_closure("sales", "close_rate", peer_average=50.0, higher_is_better=True)

        assert result["gap_trend"] == "unknown"
        assert "Insufficient real trend history" in result["note"]

    def test_unknown_when_peer_average_not_numeric(self):
        self._seed_rising_series()

        result = nt.project_gap_closure("sales", "close_rate", peer_average=None, higher_is_better=True)

        assert result["gap_trend"] == "unknown"
        assert "No peer average available" in result["note"]

    def test_closing_when_projected_gap_shrinks(self):
        self._seed_rising_series()

        result = nt.project_gap_closure("sales", "close_rate", peer_average=65.0, higher_is_better=True)

        assert result["current_gap"] == pytest.approx(35.0)
        assert result["projected_gap"] == pytest.approx(5.0)
        assert result["gap_trend"] == "closing"
        assert result["peer_average"] == 65.0

    def test_widening_when_projected_gap_grows(self):
        self._seed_rising_series()

        result = nt.project_gap_closure("sales", "close_rate", peer_average=25.0, higher_is_better=True)

        assert result["current_gap"] == pytest.approx(5.0)
        assert result["projected_gap"] == pytest.approx(35.0)
        assert result["gap_trend"] == "widening"

    def test_holding_when_gap_stays_flat(self):
        self._seed_flat_series()

        result = nt.project_gap_closure("finance", "funding_delays", peer_average=50.0, higher_is_better=False)

        assert result["current_gap"] == pytest.approx(10.0)
        assert result["projected_gap"] == pytest.approx(10.0)
        assert result["gap_trend"] == "holding"

    def test_higher_is_better_flag_does_not_change_the_result(self):
        self._seed_rising_series()
        result_true = nt.project_gap_closure("sales", "close_rate", peer_average=65.0, higher_is_better=True)

        ledger.reset()
        self._seed_rising_series()
        result_false = nt.project_gap_closure("sales", "close_rate", peer_average=65.0, higher_is_better=False)

        assert result_true["gap_trend"] == result_false["gap_trend"] == "closing"
        assert result_true["projected_gap"] == result_false["projected_gap"]

    def test_note_discloses_this_is_not_a_real_competitive_forecast(self):
        self._seed_rising_series()

        result = nt.project_gap_closure("sales", "close_rate", peer_average=65.0, higher_is_better=True)

        assert "not a real competitive race" in result["note"]
