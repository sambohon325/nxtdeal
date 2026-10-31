"""
Tests for core/escalation_dashboard.py / core/escalation_dashboard_api.py -- a real,
thin composition wrapper: every entity currently in the pipeline
(core/pipeline_state.py's get_all_pipeline_entity_ids), run through
core/escalation.py's own already-tested get_escalated_leads() at a fixed 14-day
threshold. Both core/escalation.py's escalation logic and
core/pipeline_state.py's/core/lead_aging.py's underlying state/age computation
already have direct coverage elsewhere (test_lead_routing_escalation.py,
test_pipeline_state.py) -- this file exists to give the composition itself (the
"gather every real pipeline entity, apply the fixed 14-day threshold" wiring) its
own direct import-level coverage, not to re-derive escalation logic from scratch.

Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import LEAD
from core import pipeline_state
from core import escalation_dashboard
from core import escalation_dashboard_api


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    monkeypatch.setattr(pipeline_state, "save_graph", lambda filepath: None)


def _add_lead(lead_id, since_days_ago, state="CONTACTED"):
    ledger.add_entity(Entity(id=lead_id, entity_type=LEAD, attributes={}))
    since = (datetime.now() - timedelta(days=since_days_ago)).isoformat()
    pipeline_state.start_pipeline(lead_id, initial_state=state, timestamp=since)
    return lead_id


class TestGetEscalationDashboard:

    def test_an_empty_pipeline_returns_an_empty_list(self):
        assert escalation_dashboard.get_escalation_dashboard() == []

    def test_a_lead_past_the_fixed_14_day_threshold_is_escalated(self):
        _add_lead("LEAD-1", since_days_ago=20)

        result = escalation_dashboard.get_escalation_dashboard()

        assert len(result) == 1
        assert result[0]["lead_id"] == "LEAD-1"
        assert result[0]["status"] == "ESCALATED"

    def test_a_lead_under_the_fixed_14_day_threshold_is_not_escalated(self):
        _add_lead("LEAD-1", since_days_ago=5)

        assert escalation_dashboard.get_escalation_dashboard() == []

    def test_a_lead_not_in_the_pipeline_at_all_is_never_considered(self):
        ledger.add_entity(Entity(id="LEAD-1", entity_type=LEAD, attributes={}))

        assert escalation_dashboard.get_escalation_dashboard() == []

    def test_sold_and_lost_leads_are_never_escalated_regardless_of_age(self):
        _add_lead("LEAD-1", since_days_ago=30, state="SOLD")
        _add_lead("LEAD-2", since_days_ago=30, state="LOST")

        assert escalation_dashboard.get_escalation_dashboard() == []

    def test_multiple_real_pipeline_entities_are_all_considered(self):
        _add_lead("LEAD-1", since_days_ago=20)
        _add_lead("LEAD-2", since_days_ago=3)
        _add_lead("LEAD-3", since_days_ago=15)

        result = escalation_dashboard.get_escalation_dashboard()

        escalated_ids = {r["lead_id"] for r in result}
        assert escalated_ids == {"LEAD-1", "LEAD-3"}


class TestEscalationDashboardApi:

    def test_get_dashboard_returns_the_same_real_result_as_the_underlying_function(self):
        _add_lead("LEAD-1", since_days_ago=20)

        assert escalation_dashboard_api.get_dashboard() == escalation_dashboard.get_escalation_dashboard()

    def test_get_dashboard_on_an_empty_pipeline_returns_an_empty_list(self):
        assert escalation_dashboard_api.get_dashboard() == []
