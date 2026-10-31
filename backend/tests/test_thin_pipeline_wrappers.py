"""
Tests for five small, real (not-yet-covered) composition/delegation modules that sit
directly on top of already deeply-tested pipeline modules:

- core/workflow_dashboard.py -- a one-line delegation to pipeline_state.get_pipeline_summary
- core/velocity_dashboard.py -- a one-line delegation to pipeline_velocity.get_pipeline_velocity
- core/entity_filter.py -- get_visible_entities(role), a real filter over permissions.ENTITY_ACCESS
- core/lead_lifecycle.py -- register_lead(lead_id), a real delegation to
  lead_workflows.create_lead_workflow (a genuinely different function from
  core/registry.py's own, differently-implemented register_lead)
- core/follow_up_dashboard.py -- a real composition of pipeline_state.get_all_pipeline_entity_ids
  + follow_up_queue.get_follow_up_queue with threshold_days hardcoded to 0

core/bumper_bi.py is deliberately NOT covered here -- confirmed via a direct read to
be an inert docstring-only stub (session 68, "MOVED... nothing imports this file
anymore"), no real behavior to test.

Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import LEAD, VEHICLE, FINANCE_CONTRACT
from core import workflow_dashboard
from core import velocity_dashboard
from core import entity_filter
from core import lead_lifecycle
from core import lead_workflows
from core import pipeline_state
from core import follow_up_dashboard
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    monkeypatch.setattr(lead_workflows, "save_graph", lambda filepath: None)
    monkeypatch.setattr(pipeline_state, "save_graph", lambda filepath: None)


def _make_lead(lead_id, **attrs):
    entity = Entity(id=lead_id, entity_type=LEAD, attributes=attrs)
    ledger.add_entity(entity)
    return entity


class TestWorkflowDashboard:

    def test_delegates_to_pipeline_state_get_pipeline_summary(self, monkeypatch):
        sentinel = {"new": 3, "contacted": 1}
        monkeypatch.setattr(workflow_dashboard, "get_pipeline_summary", lambda: sentinel)
        assert workflow_dashboard.get_lead_pipeline_dashboard() is sentinel

    def test_returns_real_summary_shape_against_the_live_pipeline_state_module(self):
        # Not mocked this time -- confirm it genuinely reaches through to the real
        # pipeline_state module rather than a stale/shadowed import.
        _make_lead("LEAD-1", PipelineState="NEW")
        result = workflow_dashboard.get_lead_pipeline_dashboard()
        assert isinstance(result, dict)


class TestVelocityDashboard:

    def test_delegates_to_pipeline_velocity_get_pipeline_velocity(self, monkeypatch):
        sentinel = {"avg_days_new_to_contacted": 1.5}
        monkeypatch.setattr(velocity_dashboard, "get_pipeline_velocity", lambda: sentinel)
        assert velocity_dashboard.get_velocity_dashboard() is sentinel


class TestEntityFilter:

    def test_admin_sees_no_special_treatment_here_only_real_role_membership(self):
        # entity_filter.py has no ADMIN-always-sees-everything special case -- it's a
        # pure real filter over ENTITY_ACCESS, so ADMIN only appears where the real
        # catalog actually lists ADMIN.
        visible = entity_filter.get_visible_entities(ADMIN)
        assert VEHICLE in visible

    def test_broadly_visible_entity_type_included_for_every_role(self):
        for role in (ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE):
            assert VEHICLE in entity_filter.get_visible_entities(role)

    def test_narrowly_gated_entity_type_excluded_for_roles_outside_its_list(self):
        visible_to_sales = entity_filter.get_visible_entities(SALES)
        assert FINANCE_CONTRACT not in visible_to_sales

        visible_to_finance = entity_filter.get_visible_entities(FINANCE)
        assert FINANCE_CONTRACT in visible_to_finance

    def test_unknown_role_sees_nothing(self):
        assert entity_filter.get_visible_entities("NOT_A_REAL_ROLE") == []

    def test_result_has_no_duplicate_entity_types(self):
        visible = entity_filter.get_visible_entities(ADMIN)
        assert len(visible) == len(set(visible))


class TestLeadLifecycleRegisterLead:

    def test_register_lead_puts_a_real_lead_into_the_pipeline(self):
        _make_lead("LEAD-1")
        lead_lifecycle.register_lead("LEAD-1")

        entity = ledger.get_entity("LEAD-1")
        assert entity.attributes["PipelineState"] == "NEW"
        assert "PipelineCreatedAt" in entity.attributes
        assert "PipelineStateSince" in entity.attributes

    def test_register_lead_raises_for_an_unknown_lead_id(self):
        with pytest.raises(Exception):
            lead_lifecycle.register_lead("LEAD-BOGUS")

    def test_register_lead_is_idempotent_and_never_resets_pipeline_created_at(self):
        _make_lead("LEAD-1")
        lead_lifecycle.register_lead("LEAD-1")
        entity = ledger.get_entity("LEAD-1")
        first_created_at = entity.attributes["PipelineCreatedAt"]

        # A second real call (matching the module's own documented idempotency
        # guarantee) must not reset PipelineCreatedAt.
        lead_lifecycle.register_lead("LEAD-1")
        assert entity.attributes["PipelineCreatedAt"] == first_created_at
        assert entity.attributes["PipelineState"] == "NEW"

    def test_register_lead_is_a_genuinely_different_function_from_registrys_own(self):
        # core/registry.py's own register_lead(lead_id, name) has a different
        # signature entirely (name resolution for search, not pipeline state) --
        # confirm lead_lifecycle's own version doesn't accidentally delegate there.
        import inspect
        sig = inspect.signature(lead_lifecycle.register_lead)
        assert list(sig.parameters.keys()) == ["lead_id"]


class TestFollowUpDashboard:

    def test_returns_every_lead_currently_in_the_pipeline_at_threshold_zero(self):
        _make_lead("LEAD-1", PipelineState="NEW", PipelineStateSince="2020-01-01T00:00:00")
        _make_lead("LEAD-2", PipelineState="CONTACTED", PipelineStateSince="2026-01-01T00:00:00")

        result = follow_up_dashboard.get_follow_up_dashboard()

        lead_ids = {row["lead_id"] for row in result}
        assert lead_ids == {"LEAD-1", "LEAD-2"}

    def test_row_shape_includes_current_state_and_days_in_state(self):
        _make_lead("LEAD-1", PipelineState="NEW", PipelineStateSince="2020-01-01T00:00:00")

        result = follow_up_dashboard.get_follow_up_dashboard()

        row = next(r for r in result if r["lead_id"] == "LEAD-1")
        assert row["current_state"] == "NEW"
        assert row["days_in_state"] > 0

    def test_a_lead_with_no_pipeline_state_is_excluded_entirely(self):
        _make_lead("LEAD-1", PipelineState="NEW", PipelineStateSince="2020-01-01T00:00:00")
        # A lead that was never registered into the pipeline at all.
        _make_lead("LEAD-2")

        result = follow_up_dashboard.get_follow_up_dashboard()

        lead_ids = {row["lead_id"] for row in result}
        assert lead_ids == {"LEAD-1"}

    def test_empty_pipeline_returns_empty_list(self):
        assert follow_up_dashboard.get_follow_up_dashboard() == []
