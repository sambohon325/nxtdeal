"""
Tests for core/manager_analytics.py -- get_employee_metrics(), a real
per-employee composition of assigned/active/closed/stalled lead counts plus
a real conversion rate, off core.lead_assignment/core.pipeline_state/
core.lead_aging/core.employee_performance -- all four already-real,
already-tested modules. Added per BUILD_QUEUE.md's standing "convert to a
real pytest suite as each module gets touched" rule (CAF-00123
missing_test_coverage work).

No save_graph stubbing needed -- same precedent tests/test_pipeline_state.py/
tests/test_lead_aging.py/tests/test_employee_performance.py already
establish, relying on conftest.py's isolated tempdir DEALEROS_STORAGE_DIR.
"""

import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

from datetime import datetime, timedelta

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import LEAD, EMPLOYEE

from core.pipeline_state import start_pipeline
from core.lead_assignment import assign_lead
from core.manager_analytics import get_employee_metrics


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield
    ledger.reset()


def _add_lead(entity_id, state=None, since=None):
    ledger.add_entity(Entity(id=entity_id, entity_type=LEAD, attributes={}))
    if state:
        start_pipeline(entity_id, initial_state=state, timestamp=since)


def _add_employee(entity_id="EMP-1"):
    ledger.add_entity(Entity(id=entity_id, entity_type=EMPLOYEE, attributes={}))
    return entity_id


def _days_ago(n):
    return (datetime.now() - timedelta(days=n)).isoformat()


class TestGetEmployeeMetrics:
    def test_employee_with_no_leads_returns_all_zeros(self):
        _add_employee("EMP-1")

        result = get_employee_metrics("EMP-1")

        assert result == {
            "employee_id": "EMP-1",
            "assigned_leads": 0,
            "active_leads": 0,
            "closed_leads": 0,
            "stalled_leads": 0,
            "conversion_rate": 0,
        }

    def test_assigned_leads_counts_every_currently_assigned_lead(self):
        _add_employee("EMP-1")
        _add_lead("LEAD-1", state="NEW", since=_days_ago(1))
        _add_lead("LEAD-2", state="CONTACTED", since=_days_ago(1))
        assign_lead("LEAD-1", "EMP-1")
        assign_lead("LEAD-2", "EMP-1")

        result = get_employee_metrics("EMP-1")

        assert result["assigned_leads"] == 2

    def test_sold_and_lost_leads_count_as_closed_not_active(self):
        _add_employee("EMP-1")
        _add_lead("LEAD-1", state="SOLD", since=_days_ago(1))
        _add_lead("LEAD-2", state="LOST", since=_days_ago(1))
        _add_lead("LEAD-3", state="CONTACTED", since=_days_ago(1))
        assign_lead("LEAD-1", "EMP-1")
        assign_lead("LEAD-2", "EMP-1")
        assign_lead("LEAD-3", "EMP-1")

        result = get_employee_metrics("EMP-1")

        assert result["closed_leads"] == 2
        assert result["active_leads"] == 1

    def test_lead_with_no_pipeline_state_is_skipped_entirely(self):
        # a lead assigned but never entered into the pipeline (get_pipeline_state
        # returns None) contributes to neither active nor closed, but is still
        # counted in assigned_leads (the raw assignment count).
        _add_employee("EMP-1")
        _add_lead("LEAD-1")  # no state at all
        assign_lead("LEAD-1", "EMP-1")

        result = get_employee_metrics("EMP-1")

        assert result["assigned_leads"] == 1
        assert result["active_leads"] == 0
        assert result["closed_leads"] == 0

    def test_stalled_leads_counts_leads_seven_or_more_days_in_state(self):
        _add_employee("EMP-1")
        _add_lead("LEAD-1", state="CONTACTED", since=_days_ago(7))
        _add_lead("LEAD-2", state="CONTACTED", since=_days_ago(3))
        assign_lead("LEAD-1", "EMP-1")
        assign_lead("LEAD-2", "EMP-1")

        result = get_employee_metrics("EMP-1")

        assert result["stalled_leads"] == 1

    def test_stalled_count_includes_closed_leads_too(self):
        # get_employee_metrics() computes stalled independently of active/closed --
        # a closed (SOLD) lead that's been in that state 7+ days still counts.
        _add_employee("EMP-1")
        _add_lead("LEAD-1", state="SOLD", since=_days_ago(10))
        assign_lead("LEAD-1", "EMP-1")

        result = get_employee_metrics("EMP-1")

        assert result["closed_leads"] == 1
        assert result["stalled_leads"] == 1

    def test_conversion_rate_reflects_real_sold_percentage(self):
        _add_employee("EMP-1")
        _add_lead("LEAD-1", state="SOLD", since=_days_ago(1))
        _add_lead("LEAD-2", state="CONTACTED", since=_days_ago(1))
        assign_lead("LEAD-1", "EMP-1")
        assign_lead("LEAD-2", "EMP-1")

        result = get_employee_metrics("EMP-1")

        assert result["conversion_rate"] == 50.0

    def test_reassigned_lead_excluded_from_the_new_owners_metrics_source(self):
        _add_employee("EMP-1")
        _add_employee("EMP-2")
        _add_lead("LEAD-1", state="SOLD", since=_days_ago(1))
        assign_lead("LEAD-1", "EMP-1")
        assign_lead("LEAD-1", "EMP-2")

        result_1 = get_employee_metrics("EMP-1")
        result_2 = get_employee_metrics("EMP-2")

        assert result_1["assigned_leads"] == 0
        assert result_2["assigned_leads"] == 1
        assert result_2["closed_leads"] == 1

    def test_employee_id_echoed_back_in_result(self):
        _add_employee("EMP-42")
        result = get_employee_metrics("EMP-42")
        assert result["employee_id"] == "EMP-42"
