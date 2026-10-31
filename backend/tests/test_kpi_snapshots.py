"""
Tests for core/kpi_snapshots.py — the daily KPI trend-delta engine behind Department
Intelligence's Reporting tabs and the Network layer's Trends screen (session 35;
renamed from bumper_snapshots session 68/70). A DepartmentSnapshot is an ordinary graph
entity, so this module reads/writes the singleton ledger directly
(`from core.dealeros import ledger, id_generator`). Every test seeds Entity objects into
that ledger by hand and resets it (plus the SNAP id counter) around each test — fully
deterministic and seed-independent, nothing here depends on storage/graph.json and no
disk is touched (record_snapshot only calls ledger.add_entity, never save_graph).

The one thing this module reads from the real clock is `date.today()` (via _today_iso()),
used to key/find "today's" snapshot and to EXCLUDE today's from the "prior" lookup. Rather
than freeze the clock, every test seeds "prior" snapshots with fixed, clearly-in-the-past
snapshot_dates ("2020-01-01" etc.) so they can never collide with whatever the real today
is — the exact property most_recent_prior_snapshot() relies on. Run from backend/ with
`pytest`.
"""

import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

import pytest

from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.entity_types import DEPARTMENT_SNAPSHOT

from core import kpi_snapshots


# ---------------------------------------------------------------------------
# helpers / fixture
# ---------------------------------------------------------------------------

def _seed_snapshot(department, snapshot_date, kpis, entity_id=None):
    """Seed a DepartmentSnapshot directly (bypassing record_snapshot so we can control
    snapshot_date, e.g. to plant a fixed 'prior' day). `kpis` here is already the
    persisted {key: numeric_value} shape, matching what record_snapshot writes."""
    entity_id = entity_id or id_generator.generate("SNAP")
    ledger.add_entity(
        Entity(
            entity_id,
            DEPARTMENT_SNAPSHOT,
            {
                "department": department,
                "snapshot_date": snapshot_date,
                "kpis": kpis,
                "recorded_at": snapshot_date + "T00:00:00+00:00",
            },
        )
    )
    return entity_id


def _kpi(value, **extra):
    """A KPI dict of the compute_department() shape — value plus arbitrary display
    fields (label, unit, etc.) that must survive with_trend() untouched."""
    d = {"value": value}
    d.update(extra)
    return d


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    id_generator.counters["SNAP"] = 0
    yield
    ledger.reset()
    id_generator.counters["SNAP"] = 0


# ---------------------------------------------------------------------------
# find_snapshot
# ---------------------------------------------------------------------------

def test_find_snapshot_returns_none_when_no_snapshots_exist():
    assert kpi_snapshots.find_snapshot("sales") is None


def test_find_snapshot_matches_department_and_explicit_date():
    _seed_snapshot("sales", "2020-01-01", {"total_sales": 100})

    got = kpi_snapshots.find_snapshot("sales", "2020-01-01")
    assert got is not None
    assert got.attributes["department"] == "sales"
    assert got.attributes["snapshot_date"] == "2020-01-01"


def test_find_snapshot_filters_by_department():
    _seed_snapshot("sales", "2020-01-01", {"total_sales": 100})

    assert kpi_snapshots.find_snapshot("service", "2020-01-01") is None


def test_find_snapshot_filters_by_date():
    _seed_snapshot("sales", "2020-01-01", {"total_sales": 100})

    assert kpi_snapshots.find_snapshot("sales", "2020-01-02") is None


def test_find_snapshot_ignores_non_snapshot_entities():
    # A same-department, same-date attribute set on a NON-snapshot entity must not match.
    ledger.add_entity(
        Entity(
            "CUST-1",
            "Customer",
            {"department": "sales", "snapshot_date": "2020-01-01"},
        )
    )

    assert kpi_snapshots.find_snapshot("sales", "2020-01-01") is None


def test_find_snapshot_defaults_to_today():
    # record_snapshot stamps today's date; find_snapshot() with no date should locate it.
    kpi_snapshots.record_snapshot("sales", {"total_sales": _kpi(100)})

    got = kpi_snapshots.find_snapshot("sales")
    assert got is not None
    assert got.attributes["snapshot_date"] == kpi_snapshots._today_iso()


# ---------------------------------------------------------------------------
# record_snapshot
# ---------------------------------------------------------------------------

def test_record_snapshot_creates_entity_with_todays_date_and_numeric_kpis():
    entity = kpi_snapshots.record_snapshot(
        "sales",
        {"total_sales": _kpi(120, label="Total Sales"), "units": _kpi(4)},
    )

    assert entity.entity_type == DEPARTMENT_SNAPSHOT
    assert entity.attributes["department"] == "sales"
    assert entity.attributes["snapshot_date"] == kpi_snapshots._today_iso()
    # Only the raw numeric value is persisted, not the whole kpi dict.
    assert entity.attributes["kpis"] == {"total_sales": 120, "units": 4}
    assert "recorded_at" in entity.attributes
    # It's actually in the ledger.
    assert ledger.get_entity(entity.id) is entity


def test_record_snapshot_is_idempotent_per_department_per_day():
    first = kpi_snapshots.record_snapshot("sales", {"total_sales": _kpi(100)})
    # A second call the same day (even with different numbers) returns the ORIGINAL,
    # untouched, and does not create a duplicate.
    second = kpi_snapshots.record_snapshot("sales", {"total_sales": _kpi(999)})

    assert second is first
    assert second.attributes["kpis"] == {"total_sales": 100}

    snaps = [
        e for e in ledger.get_all().values()
        if e.entity_type == DEPARTMENT_SNAPSHOT
    ]
    assert len(snaps) == 1


def test_record_snapshot_separate_departments_same_day_coexist():
    kpi_snapshots.record_snapshot("sales", {"total_sales": _kpi(100)})
    kpi_snapshots.record_snapshot("service", {"ros": _kpi(50)})

    snaps = [
        e for e in ledger.get_all().values()
        if e.entity_type == DEPARTMENT_SNAPSHOT
    ]
    assert len(snaps) == 2
    assert kpi_snapshots.find_snapshot("sales") is not None
    assert kpi_snapshots.find_snapshot("service") is not None


# ---------------------------------------------------------------------------
# most_recent_prior_snapshot
# ---------------------------------------------------------------------------

def test_most_recent_prior_returns_none_with_no_history():
    assert kpi_snapshots.most_recent_prior_snapshot("sales") is None


def test_most_recent_prior_excludes_todays_snapshot():
    # Only today's snapshot exists — there is no PRIOR one.
    kpi_snapshots.record_snapshot("sales", {"total_sales": _kpi(100)})

    assert kpi_snapshots.most_recent_prior_snapshot("sales") is None


def test_most_recent_prior_returns_latest_by_date():
    _seed_snapshot("sales", "2020-01-01", {"total_sales": 100})
    _seed_snapshot("sales", "2020-03-15", {"total_sales": 300})
    _seed_snapshot("sales", "2020-02-10", {"total_sales": 200})

    prior = kpi_snapshots.most_recent_prior_snapshot("sales")
    assert prior is not None
    assert prior.attributes["snapshot_date"] == "2020-03-15"


def test_most_recent_prior_filters_by_department():
    _seed_snapshot("service", "2020-01-01", {"ros": 50})

    assert kpi_snapshots.most_recent_prior_snapshot("sales") is None


def test_most_recent_prior_ignores_non_snapshot_entities():
    ledger.add_entity(
        Entity(
            "CUST-1",
            "Customer",
            {"department": "sales", "snapshot_date": "2020-01-01"},
        )
    )

    assert kpi_snapshots.most_recent_prior_snapshot("sales") is None


# ---------------------------------------------------------------------------
# with_trend
# ---------------------------------------------------------------------------

def test_with_trend_no_history_marks_every_kpi_as_such():
    current = {"total_sales": _kpi(120, label="Total Sales")}

    enriched = kpi_snapshots.with_trend("sales", current)

    kpi = enriched["total_sales"]
    assert kpi["delta_pct"] is None
    assert kpi["has_history"] is False
    assert kpi["compared_to"] is None
    # Display fields survive.
    assert kpi["label"] == "Total Sales"
    assert kpi["value"] == 120


def test_with_trend_records_todays_snapshot_as_side_effect():
    assert kpi_snapshots.find_snapshot("sales") is None

    kpi_snapshots.with_trend("sales", {"total_sales": _kpi(120)})

    assert kpi_snapshots.find_snapshot("sales") is not None


def test_with_trend_computes_positive_delta_against_prior():
    _seed_snapshot("sales", "2020-01-01", {"total_sales": 100})

    enriched = kpi_snapshots.with_trend("sales", {"total_sales": _kpi(120)})

    kpi = enriched["total_sales"]
    assert kpi["delta_pct"] == 20.0
    assert kpi["has_history"] is True
    assert kpi["compared_to"] == "2020-01-01"


def test_with_trend_computes_negative_delta():
    _seed_snapshot("sales", "2020-01-01", {"total_sales": 200})

    enriched = kpi_snapshots.with_trend("sales", {"total_sales": _kpi(150)})

    assert enriched["total_sales"]["delta_pct"] == -25.0


def test_with_trend_uses_absolute_prior_value_for_denominator():
    # Prior negative value: delta is computed against abs(prior), so a move from -50 to
    # -25 is a +50% change, not -50%.
    _seed_snapshot("finance", "2020-01-01", {"net": -50})

    enriched = kpi_snapshots.with_trend("finance", {"net": _kpi(-25)})

    assert enriched["net"]["delta_pct"] == 50.0


def test_with_trend_prior_zero_current_nonzero_is_undefined_not_zero():
    _seed_snapshot("sales", "2020-01-01", {"total_sales": 0})

    enriched = kpi_snapshots.with_trend("sales", {"total_sales": _kpi(80)})

    kpi = enriched["total_sales"]
    assert kpi["delta_pct"] is None          # undefined percent change
    assert kpi["has_history"] is True        # but there IS a prior snapshot
    assert kpi["compared_to"] == "2020-01-01"


def test_with_trend_prior_zero_current_zero_is_flat():
    _seed_snapshot("sales", "2020-01-01", {"total_sales": 0})

    enriched = kpi_snapshots.with_trend("sales", {"total_sales": _kpi(0)})

    kpi = enriched["total_sales"]
    assert kpi["delta_pct"] == 0.0
    assert kpi["has_history"] is True


def test_with_trend_new_key_absent_from_prior_treated_as_no_history():
    # Prior snapshot has total_sales only; current adds a brand-new 'units' KPI.
    _seed_snapshot("sales", "2020-01-01", {"total_sales": 100})

    enriched = kpi_snapshots.with_trend(
        "sales",
        {"total_sales": _kpi(150), "units": _kpi(5)},
    )

    # Known key gets a real delta...
    assert enriched["total_sales"]["delta_pct"] == 50.0
    assert enriched["total_sales"]["has_history"] is True
    # ...the new key, having no prior value, is flagged no-history.
    assert enriched["units"]["delta_pct"] is None
    assert enriched["units"]["has_history"] is False
    assert enriched["units"]["compared_to"] is None


def test_with_trend_does_not_mutate_the_input_dicts():
    _seed_snapshot("sales", "2020-01-01", {"total_sales": 100})
    current = {"total_sales": _kpi(120)}

    kpi_snapshots.with_trend("sales", current)

    # The caller's original kpi dict must be untouched (with_trend copies each dict).
    assert current["total_sales"] == {"value": 120}
    assert "delta_pct" not in current["total_sales"]
