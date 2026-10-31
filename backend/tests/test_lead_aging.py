"""
Tests for core/lead_aging.py -- get_lead_age_days() reads "days since the
entity's PipelineStateSince timestamp" straight off the graph (rewritten
2026-07-13, see the module's own docstring and CLAUDE.md's "one graph"
note). Added per BUILD_QUEUE.md's standing "convert to a real pytest suite
as each module gets touched" rule (CAF-00123 missing_test_coverage work).

No save_graph stubbing is needed here -- same precedent tests/
test_pipeline_state.py already establishes: conftest.py points
DEALEROS_STORAGE_DIR at an isolated tempdir for the whole test session, so
letting core.pipeline_state.start_pipeline()/set_pipeline_state() write for
real is harmless and fully deterministic.
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

from core.pipeline_state import start_pipeline
from core.lead_aging import get_lead_age_days


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield
    ledger.reset()


def _add_lead(entity_id):
    ledger.add_entity(Entity(id=entity_id, entity_type=LEAD, attributes={}))


class TestGetLeadAgeDays:
    def test_entity_never_entered_the_pipeline_returns_zero(self):
        _add_lead("LEAD-1")
        assert get_lead_age_days("LEAD-1") == 0

    def test_unknown_entity_returns_zero(self):
        assert get_lead_age_days("LEAD-DOES-NOT-EXIST") == 0

    def test_entity_that_just_entered_its_state_is_zero_days_old(self):
        _add_lead("LEAD-1")
        start_pipeline("LEAD-1", initial_state="NEW", timestamp=datetime.now().isoformat())

        assert get_lead_age_days("LEAD-1") == 0

    def test_entity_ten_days_in_current_state(self):
        _add_lead("LEAD-1")
        ten_days_ago = (datetime.now() - timedelta(days=10)).isoformat()
        start_pipeline("LEAD-1", initial_state="CONTACTED", timestamp=ten_days_ago)

        assert get_lead_age_days("LEAD-1") == 10

    def test_age_measures_time_since_current_state_not_since_creation(self):
        # PipelineCreatedAt is set once and never changes; PipelineStateSince moves on
        # every transition -- get_lead_age_days() reads the latter, not the former.
        _add_lead("LEAD-1")
        thirty_days_ago = (datetime.now() - timedelta(days=30)).isoformat()
        start_pipeline("LEAD-1", initial_state="NEW", timestamp=thirty_days_ago)

        two_days_ago = (datetime.now() - timedelta(days=2)).isoformat()
        start_pipeline("LEAD-1", initial_state="CONTACTED", timestamp=two_days_ago)

        assert get_lead_age_days("LEAD-1") == 2
