"""
Tests for the graph-backed pipeline-analytics cluster that turns each Lead's pipeline
state (the Pipeline* attributes core/pipeline_state.py writes onto the Lead entity, plus
ASSIGNED_TO relationships from core/lead_assignment.py) into pipeline/velocity/manager
figures:

    core/pipeline_metrics.py    - get_conversion_rate, get_loss_rate,
                                  get_active_leads, get_closed_leads (pure dict fns)
    core/pipeline_velocity.py   - get_pipeline_velocity (avg days-in-state, grouped)
    core/pipeline_analytics.py  - get_pipeline_metrics (the composed summary)
    core/manager_analytics.py   - get_employee_metrics (per-employee rollup)

These four modules were rewritten 2026-07-13 in the "one graph" unification (see
CLAUDE.md) but had no committed regression coverage — this file is that coverage, added
per BUILD_QUEUE.md's "convert tests incrementally as modules get touched" standing item.
It complements sessions 76/77's coverage of the sibling aging/stall/follow-up/routing
readers. Everything here seeds Lead entities + ASSIGNED_TO relationships directly into the
ledger with explicit pipeline timestamps, so it's fully deterministic and seed-independent
(no dependency on generate_seed_data.py, and no import of the FUSE-truncated *_menu/api.app
chain). ASSIGNED_TO relationships are added straight to the ledger rather than via
assign_lead() so no save_graph()/disk write ever happens. Run from backend/ with `pytest`.
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
from core.relationships import Relationship
from core.entity_types import LEAD
from core.relationship_types import ASSIGNED_TO

from core.pipeline_state import start_pipeline, set_pipeline_state

from core.pipeline_metrics import (
    get_conversion_rate,
    get_loss_rate,
    get_active_leads,
    get_closed_leads,
)
from core.pipeline_velocity import get_pipeline_velocity
from core.pipeline_analytics import get_pipeline_metrics
from core.manager_analytics import get_employee_metrics


@pytest.fixture(autouse=True)
def fresh_ledger():

    ledger.reset()

    yield

    ledger.reset()


def _add_lead(entity_id):

    ledger.add_entity(
        Entity(id=entity_id, entity_type=LEAD, attributes={})
    )


def _days_ago(n):
    """ISO timestamp exactly n days before now — so (now - since).days == n."""

    return (datetime.now() - timedelta(days=n)).isoformat()


def _seed_lead(entity_id, state, days_ago=0):
    """Add a lead already in the pipeline in `state`, having entered it `days_ago` days
    ago (so get_lead_age_days(entity_id) == days_ago)."""

    _add_lead(entity_id)
    start_pipeline(entity_id, initial_state=state, timestamp=_days_ago(days_ago))


def _assign(employee_id, lead_id):
    """Assign a lead to an employee by adding the ASSIGNED_TO relationship directly to the
    ledger (avoids assign_lead()'s save_graph disk write)."""

    ledger.add_relationship(
        Relationship(
            source_id=employee_id,
            target_id=lead_id,
            relationship_type=ASSIGNED_TO,
        )
    )


# ---------------------------------------------------------------------------
# pipeline_metrics — pure dict functions, no ledger
# ---------------------------------------------------------------------------

def test_conversion_rate_empty_pipeline_is_zero():

    assert get_conversion_rate({}) == 0


def test_conversion_rate_all_zero_counts_is_zero():

    assert get_conversion_rate({"NEW": 0, "SOLD": 0}) == 0


def test_conversion_rate_is_sold_over_total_percent_rounded():

    # 1 SOLD out of 4 total = 25.0
    assert get_conversion_rate({"SOLD": 1, "LOST": 1, "NEW": 2}) == 25.0


def test_conversion_rate_rounds_to_two_places():

    # 1 of 3 = 33.333... -> 33.33
    assert get_conversion_rate({"SOLD": 1, "NEW": 1, "LOST": 1}) == 33.33


def test_loss_rate_empty_pipeline_is_zero():

    assert get_loss_rate({}) == 0


def test_loss_rate_is_lost_over_total_percent_rounded():

    # 2 LOST of 5 total = 40.0
    assert get_loss_rate({"LOST": 2, "SOLD": 1, "NEW": 2}) == 40.0


def test_active_leads_sums_only_the_six_active_states():

    pipeline = {
        "NEW": 1,
        "CONTACTED": 2,
        "APPOINTMENT_SET": 1,
        "VISITED": 1,
        "PROPOSAL": 1,
        "NEGOTIATION": 1,
        # non-active — must be ignored
        "SOLD": 5,
        "LOST": 4,
        "UNKNOWN_STATE": 9,
    }

    assert get_active_leads(pipeline) == 7


def test_active_leads_missing_states_default_to_zero():

    assert get_active_leads({"NEW": 3}) == 3
    assert get_active_leads({}) == 0


def test_closed_leads_is_sold_plus_lost():

    assert get_closed_leads({"SOLD": 3, "LOST": 2, "NEW": 10}) == 5


def test_closed_leads_missing_keys_default_to_zero():

    assert get_closed_leads({}) == 0
    assert get_closed_leads({"SOLD": 4}) == 4


# ---------------------------------------------------------------------------
# pipeline_velocity — reads the ledger
# ---------------------------------------------------------------------------

def test_velocity_empty_ledger_is_empty_dict():

    assert get_pipeline_velocity() == {}


def test_velocity_averages_age_grouped_by_state():

    _seed_lead("LEAD-1", "NEW", days_ago=2)
    _seed_lead("LEAD-2", "NEW", days_ago=4)
    _seed_lead("LEAD-3", "CONTACTED", days_ago=10)

    velocity = get_pipeline_velocity()

    assert velocity == {"NEW": 3.0, "CONTACTED": 10.0}


def test_velocity_rounds_average_to_two_places():

    _seed_lead("LEAD-1", "NEW", days_ago=1)
    _seed_lead("LEAD-2", "NEW", days_ago=1)
    _seed_lead("LEAD-3", "NEW", days_ago=2)

    # (1 + 1 + 2) / 3 = 1.333... -> 1.33
    assert get_pipeline_velocity()["NEW"] == 1.33


# ---------------------------------------------------------------------------
# pipeline_analytics — the composed summary
# ---------------------------------------------------------------------------

def test_pipeline_metrics_composes_the_full_summary():

    # 2 active (NEW), 1 SOLD, 1 LOST -> 4 total
    _seed_lead("LEAD-1", "NEW", days_ago=1)
    _seed_lead("LEAD-2", "NEW", days_ago=2)
    _seed_lead("LEAD-4", "LOST", days_ago=3)

    # A SOLD lead with a real created->sold window for time-to-close
    _add_lead("LEAD-3")
    start_pipeline("LEAD-3", initial_state="NEW", timestamp="2026-01-01T00:00:00")
    set_pipeline_state("LEAD-3", "SOLD", timestamp="2026-01-11T00:00:00")

    metrics = get_pipeline_metrics()

    assert metrics["pipeline"] == {"NEW": 2, "LOST": 1, "SOLD": 1}
    assert metrics["conversion_rate"] == 25.0   # 1 SOLD of 4
    assert metrics["loss_rate"] == 25.0         # 1 LOST of 4
    assert metrics["active_leads"] == 2         # 2 NEW
    assert metrics["closed_leads"] == 2         # SOLD + LOST
    assert metrics["average_time_to_close_days"] == 10  # Jan 1 -> Jan 11


def test_pipeline_metrics_empty_graph_is_all_zero():

    metrics = get_pipeline_metrics()

    assert metrics["pipeline"] == {}
    assert metrics["conversion_rate"] == 0
    assert metrics["loss_rate"] == 0
    assert metrics["active_leads"] == 0
    assert metrics["closed_leads"] == 0
    assert metrics["average_time_to_close_days"] == 0


# ---------------------------------------------------------------------------
# manager_analytics.get_employee_metrics
# ---------------------------------------------------------------------------

def test_employee_metrics_no_leads_is_all_zero():

    metrics = get_employee_metrics("EMP-1")

    assert metrics == {
        "employee_id": "EMP-1",
        "assigned_leads": 0,
        "active_leads": 0,
        "closed_leads": 0,
        "stalled_leads": 0,
        "conversion_rate": 0,
    }


def test_employee_metrics_counts_active_closed_and_conversion():

    # 3 leads: 1 SOLD, 1 LOST (both closed), 1 NEW (active). None stalled (all fresh).
    _seed_lead("LEAD-1", "SOLD", days_ago=1)
    _seed_lead("LEAD-2", "LOST", days_ago=1)
    _seed_lead("LEAD-3", "NEW", days_ago=1)
    for lid in ("LEAD-1", "LEAD-2", "LEAD-3"):
        _assign("EMP-1", lid)

    metrics = get_employee_metrics("EMP-1")

    assert metrics["employee_id"] == "EMP-1"
    assert metrics["assigned_leads"] == 3
    assert metrics["active_leads"] == 1
    assert metrics["closed_leads"] == 2
    assert metrics["stalled_leads"] == 0
    assert metrics["conversion_rate"] == 33.33   # 1 SOLD of 3


def test_employee_metrics_flags_stalled_leads_at_seven_days():

    # An active lead sitting 8 days in state is stalled; a 2-day one is not.
    _seed_lead("LEAD-1", "NEW", days_ago=8)
    _seed_lead("LEAD-2", "CONTACTED", days_ago=2)
    _assign("EMP-1", "LEAD-1")
    _assign("EMP-1", "LEAD-2")

    metrics = get_employee_metrics("EMP-1")

    assert metrics["assigned_leads"] == 2
    assert metrics["active_leads"] == 2
    assert metrics["stalled_leads"] == 1


def test_employee_metrics_assigned_lead_without_pipeline_state_is_skipped_in_rollup():

    # Assigned but never entered the pipeline: counts toward assigned_leads (len of the
    # assignment list) but is skipped by the state loop (get_pipeline_state is None).
    _add_lead("LEAD-1")            # no start_pipeline -> no PipelineState
    _seed_lead("LEAD-2", "NEW", days_ago=1)
    _assign("EMP-1", "LEAD-1")
    _assign("EMP-1", "LEAD-2")

    metrics = get_employee_metrics("EMP-1")

    assert metrics["assigned_leads"] == 2   # both assignments counted
    assert metrics["active_leads"] == 1     # only the pipelined one
    assert metrics["closed_leads"] == 0
    assert metrics["stalled_leads"] == 0


def test_employee_metrics_only_counts_this_employees_leads():

    _seed_lead("LEAD-1", "SOLD", days_ago=1)
    _seed_lead("LEAD-2", "NEW", days_ago=1)
    _assign("EMP-1", "LEAD-1")
    _assign("EMP-2", "LEAD-2")   # belongs to a different employee

    metrics = get_employee_metrics("EMP-1")

    assert metrics["assigned_leads"] == 1
    assert metrics["closed_leads"] == 1
    assert metrics["conversion_rate"] == 100.0
