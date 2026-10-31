"""
Tests for the graph-backed lead-pipeline analytics helpers that read pipeline state
(the three Pipeline* attributes core/pipeline_state.py writes onto a Lead entity) and
derive aging / stall / follow-up / time-to-close figures from it:

    core/lead_aging.py        - get_lead_age_days
    core/stalled_leads.py     - get_stalled_leads
    core/follow_up_queue.py   - get_follow_up_queue
    core/time_to_close.py     - get_time_to_close_days, get_average_time_to_close

These four modules were rewritten 2026-07-13 to read pipeline state straight off the
graph (see CLAUDE.md's "one graph" note) but had no committed regression coverage — this
file is that coverage, added per BUILD_QUEUE.md's "convert tests incrementally as modules
get touched" standing item. Everything here seeds Lead entities directly into the ledger
with explicit pipeline timestamps, so it's fully deterministic and seed-independent (no
dependency on generate_seed_data.py, and no import of the FUSE-truncated *_menu/api.app
chain). Run from backend/ with `pytest`.
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
from core.entity_types import LEAD

from core.pipeline_state import (
    start_pipeline,
    set_pipeline_state,
)

from core.lead_aging import get_lead_age_days
from core.stalled_leads import get_stalled_leads
from core.follow_up_queue import get_follow_up_queue
from core.time_to_close import (
    get_time_to_close_days,
    get_average_time_to_close,
)


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
    """ISO timestamp exactly n days before now. Because lead_aging computes
    datetime.now() - since a fraction of a second later, (now - since).days == n."""

    return (datetime.now() - timedelta(days=n)).isoformat()


# ---------------------------------------------------------------------------
# lead_aging.get_lead_age_days
# ---------------------------------------------------------------------------

def test_age_is_zero_for_entity_not_in_pipeline():

    _add_lead("LEAD-1")
    # never entered the pipeline -> no PipelineStateSince -> since is None -> 0
    assert get_lead_age_days("LEAD-1") == 0


def test_age_is_zero_for_unknown_entity():

    assert get_lead_age_days("DOES-NOT-EXIST") == 0


def test_age_counts_days_since_current_state_began():

    _add_lead("LEAD-2")
    start_pipeline("LEAD-2", initial_state="NEW", timestamp=_days_ago(10))

    assert get_lead_age_days("LEAD-2") == 10


def test_age_resets_on_state_transition():

    _add_lead("LEAD-3")
    start_pipeline("LEAD-3", initial_state="NEW", timestamp=_days_ago(30))
    # advancing state moves PipelineStateSince to now -> age drops back near 0
    set_pipeline_state("LEAD-3", "CONTACTED", timestamp=_days_ago(2))

    assert get_lead_age_days("LEAD-3") == 2


# ---------------------------------------------------------------------------
# stalled_leads.get_stalled_leads
# ---------------------------------------------------------------------------

def test_stalled_uses_default_threshold_of_seven_days_inclusive():

    _add_lead("FRESH")
    _add_lead("EDGE")
    _add_lead("OLD")
    start_pipeline("FRESH", timestamp=_days_ago(3))
    start_pipeline("EDGE", timestamp=_days_ago(7))   # exactly at threshold -> included
    start_pipeline("OLD", timestamp=_days_ago(20))

    stalled = get_stalled_leads(["FRESH", "EDGE", "OLD"])

    assert stalled == ["EDGE", "OLD"]


def test_stalled_respects_custom_threshold():

    _add_lead("A")
    _add_lead("B")
    start_pipeline("A", timestamp=_days_ago(10))
    start_pipeline("B", timestamp=_days_ago(20))

    assert get_stalled_leads(["A", "B"], threshold_days=15) == ["B"]


def test_stalled_empty_when_none_aged():

    _add_lead("A")
    start_pipeline("A", timestamp=_days_ago(1))

    assert get_stalled_leads(["A"]) == []


def test_stalled_treats_out_of_pipeline_lead_as_age_zero():

    _add_lead("NO_STATE")
    # in the list but never entered the pipeline -> age 0 -> never stalled
    assert get_stalled_leads(["NO_STATE"]) == []


# ---------------------------------------------------------------------------
# follow_up_queue.get_follow_up_queue
# ---------------------------------------------------------------------------

def test_follow_up_queue_returns_state_and_days_for_aged_leads():

    _add_lead("FRESH")
    _add_lead("STALE")
    start_pipeline("FRESH", initial_state="NEW", timestamp=_days_ago(2))
    start_pipeline("STALE", initial_state="CONTACTED", timestamp=_days_ago(9))

    queue = get_follow_up_queue(["FRESH", "STALE"])

    assert queue == [
        {
            "lead_id": "STALE",
            "current_state": "CONTACTED",
            "days_in_state": 9,
        }
    ]


def test_follow_up_queue_respects_custom_threshold():

    _add_lead("A")
    start_pipeline("A", initial_state="NEW", timestamp=_days_ago(5))

    assert get_follow_up_queue(["A"], threshold_days=3) == [
        {"lead_id": "A", "current_state": "NEW", "days_in_state": 5}
    ]
    assert get_follow_up_queue(["A"], threshold_days=10) == []


# ---------------------------------------------------------------------------
# time_to_close.get_time_to_close_days
# ---------------------------------------------------------------------------

def test_time_to_close_none_for_lead_not_sold():

    _add_lead("OPEN")
    start_pipeline("OPEN", initial_state="CONTACTED", timestamp=_days_ago(5))

    assert get_time_to_close_days("OPEN") is None


def test_time_to_close_measures_created_to_sold():

    _add_lead("WON")
    start_pipeline("WON", initial_state="NEW", timestamp="2026-06-01T00:00:00")
    set_pipeline_state("WON", "SOLD", timestamp="2026-06-15T00:00:00")

    # PipelineCreatedAt stays at 2026-06-01, PipelineStateSince moved to the SOLD date
    assert get_time_to_close_days("WON") == 14


def test_time_to_close_none_for_unknown_entity():

    assert get_time_to_close_days("DOES-NOT-EXIST") is None


# ---------------------------------------------------------------------------
# time_to_close.get_average_time_to_close
# ---------------------------------------------------------------------------

def test_average_time_to_close_ignores_unsold_leads():

    _add_lead("SOLD-A")
    _add_lead("SOLD-B")
    _add_lead("OPEN")

    start_pipeline("SOLD-A", initial_state="NEW", timestamp="2026-06-01T00:00:00")
    set_pipeline_state("SOLD-A", "SOLD", timestamp="2026-06-11T00:00:00")  # 10 days

    start_pipeline("SOLD-B", initial_state="NEW", timestamp="2026-06-01T00:00:00")
    set_pipeline_state("SOLD-B", "SOLD", timestamp="2026-06-21T00:00:00")  # 20 days

    start_pipeline("OPEN", initial_state="CONTACTED", timestamp="2026-06-01T00:00:00")

    assert get_average_time_to_close(["SOLD-A", "SOLD-B", "OPEN"]) == 15.0


def test_average_time_to_close_zero_when_no_sold_leads():

    _add_lead("OPEN")
    start_pipeline("OPEN", initial_state="NEW", timestamp="2026-06-01T00:00:00")

    assert get_average_time_to_close(["OPEN"]) == 0
