"""
Tests for core/employee_performance.py -- get_employee_conversion_rate(),
a real % of an employee's currently-assigned leads that reached PipelineState
"SOLD". Added per BUILD_QUEUE.md's standing "convert to a real pytest suite
as each module gets touched" rule (CAF-00123 missing_test_coverage work).

No save_graph stubbing is needed -- same precedent tests/test_pipeline_state.py/
tests/test_lead_aging.py already establish, relying on conftest.py's isolated
tempdir DEALEROS_STORAGE_DIR.
"""

import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import LEAD, EMPLOYEE

from core.pipeline_state import start_pipeline, set_pipeline_state
from core.lead_assignment import assign_lead
from core.employee_performance import get_employee_conversion_rate


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield
    ledger.reset()


def _add_lead(entity_id, state=None):
    ledger.add_entity(Entity(id=entity_id, entity_type=LEAD, attributes={}))
    if state:
        start_pipeline(entity_id, initial_state=state)


def _add_employee(entity_id="EMP-1"):
    ledger.add_entity(Entity(id=entity_id, entity_type=EMPLOYEE, attributes={}))
    return entity_id


class TestGetEmployeeConversionRate:
    def test_employee_with_no_assigned_leads_returns_zero(self):
        _add_employee("EMP-1")
        assert get_employee_conversion_rate("EMP-1") == 0

    def test_unknown_employee_returns_zero(self):
        assert get_employee_conversion_rate("EMP-DOES-NOT-EXIST") == 0

    def test_all_assigned_leads_sold_is_one_hundred_percent(self):
        _add_employee("EMP-1")
        _add_lead("LEAD-1", state="SOLD")
        _add_lead("LEAD-2", state="SOLD")
        assign_lead("LEAD-1", "EMP-1")
        assign_lead("LEAD-2", "EMP-1")

        assert get_employee_conversion_rate("EMP-1") == 100.0

    def test_no_assigned_leads_sold_is_zero_percent(self):
        _add_employee("EMP-1")
        _add_lead("LEAD-1", state="CONTACTED")
        _add_lead("LEAD-2", state="LOST")
        assign_lead("LEAD-1", "EMP-1")
        assign_lead("LEAD-2", "EMP-1")

        assert get_employee_conversion_rate("EMP-1") == 0.0

    def test_partial_conversion_rounded_to_two_decimals(self):
        _add_employee("EMP-1")
        _add_lead("LEAD-1", state="SOLD")
        _add_lead("LEAD-2", state="CONTACTED")
        _add_lead("LEAD-3", state="CONTACTED")
        assign_lead("LEAD-1", "EMP-1")
        assign_lead("LEAD-2", "EMP-1")
        assign_lead("LEAD-3", "EMP-1")

        # 1 of 3 sold = 33.333...% -> rounded to 33.33
        assert get_employee_conversion_rate("EMP-1") == 33.33

    def test_reassigned_lead_no_longer_counts_toward_old_employee(self):
        _add_employee("EMP-1")
        _add_employee("EMP-2")
        _add_lead("LEAD-1", state="SOLD")
        assign_lead("LEAD-1", "EMP-1")
        assign_lead("LEAD-1", "EMP-2")  # reassigned away from EMP-1

        assert get_employee_conversion_rate("EMP-1") == 0
        assert get_employee_conversion_rate("EMP-2") == 100.0

    def test_leads_with_no_pipeline_state_are_counted_but_not_sold(self):
        # a lead assigned but never entered into the pipeline at all --
        # get_pipeline_state() returns None, which != "SOLD", so it's counted
        # toward the denominator but never the sold numerator.
        _add_employee("EMP-1")
        _add_lead("LEAD-1")  # no state
        assign_lead("LEAD-1", "EMP-1")

        assert get_employee_conversion_rate("EMP-1") == 0.0

    def test_state_transition_to_sold_after_assignment_is_reflected(self):
        _add_employee("EMP-1")
        _add_lead("LEAD-1", state="CONTACTED")
        assign_lead("LEAD-1", "EMP-1")

        assert get_employee_conversion_rate("EMP-1") == 0.0

        set_pipeline_state("LEAD-1", "SOLD")

        assert get_employee_conversion_rate("EMP-1") == 100.0
