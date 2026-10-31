"""
Batch 5 of thin `_api.py` ACL-wrapper coverage -- the last handful of `_api.py`
modules with no dedicated test file (see the CLAUDE.md missing_test_coverage /
CAF-00123 effort). Covers: leaderboard_api, strategic_planning_api,
advertising_api, dealership_events_api, email_templates_api, website_chat_api.

Every module's own delegate functions are monkeypatched at the *importing*
module's own namespace (the "from X import Y" top-level-import monkeypatch
rule established across every prior thin-wrapper batch in this suite) --
never at the source module's namespace.

NOTE on cross-module name collisions (a real bug class found in batch 4):
`strategic_planning_api.list_objectives_api` and `advertising_api.list_objectives_api`
are two different functions sharing the exact same name. The advertising_api one is
imported under an alias (`adv_list_objectives_api`) to avoid silently shadowing the
strategic_planning_api one, which is imported first.

Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield
    ledger.reset()


# ---------------------------------------------------------------------------
# leaderboard_api.py
# ---------------------------------------------------------------------------

import core.leaderboard_api as leaderboard_api
from core.leaderboard_api import get_dashboard


class TestLeaderboardApi:

    def test_no_gate_pure_delegate(self, monkeypatch):
        monkeypatch.setattr(leaderboard_api, "get_sales_leaderboard", lambda: {"rows": [1, 2, 3]})
        assert get_dashboard() == {"rows": [1, 2, 3]}


# ---------------------------------------------------------------------------
# strategic_planning_api.py
# ---------------------------------------------------------------------------

import core.strategic_planning_api as strategic_planning_api
from core.strategic_planning_api import (
    get_strategic_planning_overview_api,
    get_strategic_planning_catalog_api,
    get_quarterly_rollup_api,
    create_objective_api,
    get_objective_api,
    list_objectives_api,
    update_objective_api,
    update_objective_progress_api,
    update_objective_budget_api,
    cancel_objective_api,
    reopen_objective_api,
    sync_objective_to_monthly_goal_api,
    create_initiative_api,
    get_initiative_api,
    list_initiatives_api,
    update_initiative_status_api,
    update_initiative_progress_api,
    update_initiative_budget_api,
)

_SP_DENIED = {"error": "You don't have access to Strategic Planning data."}
_SP_MUTATE_DENIED = {"error": "Admin/Operations role required to edit Strategic Planning data."}
_SP_VIEW_ROLES = [ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE]
_SP_MUTATE_DENIED_ROLES = [SALES, MARKETING, SERVICE, FINANCE]


class TestStrategicPlanningApi:

    def test_overview_denied_for_unknown_role(self):
        assert get_strategic_planning_overview_api("UNKNOWN") == _SP_DENIED

    @pytest.mark.parametrize("role", _SP_VIEW_ROLES)
    def test_overview_allowed_for_every_real_role(self, monkeypatch, role):
        monkeypatch.setattr(
            strategic_planning_api, "get_strategic_planning_overview",
            lambda quarter, year: {"quarter": quarter, "year": year},
        )
        result = get_strategic_planning_overview_api(role, quarter="Q3", year=2026)
        assert result == {"quarter": "Q3", "year": 2026}

    def test_catalog_denied_for_unknown_role(self):
        assert get_strategic_planning_catalog_api("UNKNOWN") == _SP_DENIED

    def test_catalog_returns_departments_and_tracking_types(self, monkeypatch):
        monkeypatch.setattr(strategic_planning_api, "STRATEGIC_DEPARTMENTS", ["sales", "service"])
        monkeypatch.setattr(strategic_planning_api, "TRACKING_TYPE_CATALOG", {"manual": {}})
        result = get_strategic_planning_catalog_api(ADMIN)
        assert result == {"departments": ["sales", "service"], "tracking_type_catalog": {"manual": {}}}

    def test_quarterly_rollup_denied_for_unknown_role(self):
        assert get_quarterly_rollup_api("UNKNOWN") == _SP_DENIED

    def test_quarterly_rollup_delegates(self, monkeypatch):
        monkeypatch.setattr(
            strategic_planning_api, "get_quarterly_rollup",
            lambda quarter, year: {"quarter": quarter, "year": year, "count": 3},
        )
        result = get_quarterly_rollup_api(SALES, quarter="Q2", year=2026)
        assert result == {"quarter": "Q2", "year": 2026, "count": 3}

    @pytest.mark.parametrize("role", _SP_MUTATE_DENIED_ROLES)
    def test_create_objective_denied(self, role):
        assert create_objective_api(role, "EMP-1", "Q3", 2026, "sales", "Grow units") == _SP_MUTATE_DENIED

    @pytest.mark.parametrize("role", [ADMIN, OPERATIONS])
    def test_create_objective_allowed(self, monkeypatch, role):
        monkeypatch.setattr(
            strategic_planning_api, "create_objective",
            lambda quarter, year, department, title, employee_id, **fields: {
                "quarter": quarter, "department": department, "title": title, "created_by": employee_id,
            },
        )
        result = create_objective_api(role, "EMP-1", "Q3", 2026, "sales", "Grow units", target_value=100)
        assert result == {"quarter": "Q3", "department": "sales", "title": "Grow units", "created_by": "EMP-1"}

    def test_get_objective_denied_for_unknown_role(self):
        assert get_objective_api("UNKNOWN", "OBJ-1") == _SP_DENIED

    def test_get_objective_delegates(self, monkeypatch):
        monkeypatch.setattr(strategic_planning_api, "get_objective", lambda objective_id: {"id": objective_id})
        assert get_objective_api(FINANCE, "OBJ-1") == {"id": "OBJ-1"}

    def test_list_objectives_denied_for_unknown_role(self):
        assert list_objectives_api("UNKNOWN") == _SP_DENIED

    def test_list_objectives_delegates(self, monkeypatch):
        monkeypatch.setattr(
            strategic_planning_api, "list_objectives",
            lambda quarter, year, department: [{"quarter": quarter, "year": year, "department": department}],
        )
        result = list_objectives_api(SERVICE, quarter="Q4", year=2026, department="service")
        assert result == [{"quarter": "Q4", "year": 2026, "department": "service"}]

    @pytest.mark.parametrize("role", _SP_MUTATE_DENIED_ROLES)
    def test_update_objective_denied(self, role):
        assert update_objective_api(role, "EMP-1", "OBJ-1") == _SP_MUTATE_DENIED

    def test_update_objective_allowed(self, monkeypatch):
        monkeypatch.setattr(
            strategic_planning_api, "update_objective",
            lambda objective_id, employee_id, **fields: {"id": objective_id, "by": employee_id, **fields},
        )
        result = update_objective_api(ADMIN, "EMP-1", "OBJ-1", title="New title")
        assert result == {"id": "OBJ-1", "by": "EMP-1", "title": "New title"}

    @pytest.mark.parametrize("role", _SP_MUTATE_DENIED_ROLES)
    def test_update_objective_progress_denied(self, role):
        assert update_objective_progress_api(role, "EMP-1", "OBJ-1", 50) == _SP_MUTATE_DENIED

    def test_update_objective_progress_allowed(self, monkeypatch):
        monkeypatch.setattr(
            strategic_planning_api, "update_objective_progress",
            lambda objective_id, progress_pct, employee_id: {"id": objective_id, "progress_pct": progress_pct},
        )
        result = update_objective_progress_api(OPERATIONS, "EMP-1", "OBJ-1", 75)
        assert result == {"id": "OBJ-1", "progress_pct": 75}

    @pytest.mark.parametrize("role", _SP_MUTATE_DENIED_ROLES)
    def test_update_objective_budget_denied(self, role):
        assert update_objective_budget_api(role, "EMP-1", "OBJ-1") == _SP_MUTATE_DENIED

    def test_update_objective_budget_allowed(self, monkeypatch):
        monkeypatch.setattr(
            strategic_planning_api, "update_objective_budget",
            lambda objective_id, employee_id, budget_allocated, budget_spent: {
                "id": objective_id, "budget_allocated": budget_allocated, "budget_spent": budget_spent,
            },
        )
        result = update_objective_budget_api(ADMIN, "EMP-1", "OBJ-1", budget_allocated=5000, budget_spent=1200)
        assert result == {"id": "OBJ-1", "budget_allocated": 5000, "budget_spent": 1200}

    @pytest.mark.parametrize("role", _SP_MUTATE_DENIED_ROLES)
    def test_cancel_objective_denied(self, role):
        assert cancel_objective_api(role, "EMP-1", "OBJ-1") == _SP_MUTATE_DENIED

    def test_cancel_objective_allowed(self, monkeypatch):
        monkeypatch.setattr(
            strategic_planning_api, "cancel_objective",
            lambda objective_id, employee_id: {"id": objective_id, "status": "cancelled"},
        )
        assert cancel_objective_api(OPERATIONS, "EMP-1", "OBJ-1") == {"id": "OBJ-1", "status": "cancelled"}

    @pytest.mark.parametrize("role", _SP_MUTATE_DENIED_ROLES)
    def test_reopen_objective_denied(self, role):
        assert reopen_objective_api(role, "EMP-1", "OBJ-1") == _SP_MUTATE_DENIED

    def test_reopen_objective_allowed(self, monkeypatch):
        monkeypatch.setattr(
            strategic_planning_api, "reopen_objective",
            lambda objective_id, employee_id: {"id": objective_id, "status": "in_progress"},
        )
        assert reopen_objective_api(ADMIN, "EMP-1", "OBJ-1") == {"id": "OBJ-1", "status": "in_progress"}

    @pytest.mark.parametrize("role", _SP_MUTATE_DENIED_ROLES)
    def test_sync_objective_to_monthly_goal_denied(self, role):
        assert sync_objective_to_monthly_goal_api(role, "EMP-1", "OBJ-1") == _SP_MUTATE_DENIED

    def test_sync_objective_to_monthly_goal_allowed(self, monkeypatch):
        monkeypatch.setattr(
            strategic_planning_api, "sync_objective_to_monthly_goal",
            lambda objective_id, employee_id: {"synced_monthly_target": 40.0},
        )
        result = sync_objective_to_monthly_goal_api(OPERATIONS, "EMP-1", "OBJ-1")
        assert result == {"synced_monthly_target": 40.0}

    @pytest.mark.parametrize("role", _SP_MUTATE_DENIED_ROLES)
    def test_create_initiative_denied(self, role):
        assert create_initiative_api(role, "EMP-1", "Website Launch", "marketing", "website_launch") == _SP_MUTATE_DENIED

    def test_create_initiative_allowed(self, monkeypatch):
        monkeypatch.setattr(
            strategic_planning_api, "create_initiative",
            lambda name, department, tracking_type, employee_id, **fields: {
                "name": name, "department": department, "tracking_type": tracking_type,
            },
        )
        result = create_initiative_api(ADMIN, "EMP-1", "Website Launch", "marketing", "website_launch")
        assert result == {"name": "Website Launch", "department": "marketing", "tracking_type": "website_launch"}

    def test_get_initiative_denied_for_unknown_role(self):
        assert get_initiative_api("UNKNOWN", "INIT-1") == _SP_DENIED

    def test_get_initiative_delegates(self, monkeypatch):
        monkeypatch.setattr(strategic_planning_api, "get_initiative", lambda initiative_id: {"id": initiative_id})
        assert get_initiative_api(SALES, "INIT-1") == {"id": "INIT-1"}

    def test_list_initiatives_denied_for_unknown_role(self):
        assert list_initiatives_api("UNKNOWN") == _SP_DENIED

    def test_list_initiatives_delegates(self, monkeypatch):
        monkeypatch.setattr(
            strategic_planning_api, "list_initiatives",
            lambda department, status, tracking_type: [{"department": department, "status": status}],
        )
        result = list_initiatives_api(MARKETING, department="marketing", status="in_progress")
        assert result == [{"department": "marketing", "status": "in_progress"}]

    @pytest.mark.parametrize("role", _SP_MUTATE_DENIED_ROLES)
    def test_update_initiative_status_denied(self, role):
        assert update_initiative_status_api(role, "EMP-1", "INIT-1", "completed") == _SP_MUTATE_DENIED

    def test_update_initiative_status_allowed(self, monkeypatch):
        monkeypatch.setattr(
            strategic_planning_api, "update_initiative_status",
            lambda initiative_id, status, employee_id: {"id": initiative_id, "status": status},
        )
        result = update_initiative_status_api(ADMIN, "EMP-1", "INIT-1", "completed")
        assert result == {"id": "INIT-1", "status": "completed"}

    @pytest.mark.parametrize("role", _SP_MUTATE_DENIED_ROLES)
    def test_update_initiative_progress_denied(self, role):
        assert update_initiative_progress_api(role, "EMP-1", "INIT-1", 60) == _SP_MUTATE_DENIED

    def test_update_initiative_progress_allowed(self, monkeypatch):
        monkeypatch.setattr(
            strategic_planning_api, "update_initiative_progress",
            lambda initiative_id, progress_pct, employee_id: {"id": initiative_id, "progress_pct": progress_pct},
        )
        result = update_initiative_progress_api(OPERATIONS, "EMP-1", "INIT-1", 60)
        assert result == {"id": "INIT-1", "progress_pct": 60}

    @pytest.mark.parametrize("role", _SP_MUTATE_DENIED_ROLES)
    def test_update_initiative_budget_denied(self, role):
        assert update_initiative_budget_api(role, "EMP-1", "INIT-1") == _SP_MUTATE_DENIED

    def test_update_initiative_budget_allowed(self, monkeypatch):
        monkeypatch.setattr(
            strategic_planning_api, "update_initiative_budget",
            lambda initiative_id, employee_id, budget_allocated, budget_spent: {
                "id": initiative_id, "budget_allocated": budget_allocated,
            },
        )
        result = update_initiative_budget_api(ADMIN, "EMP-1", "INIT-1", budget_allocated=9000)
        assert result == {"id": "INIT-1", "budget_allocated": 9000}


# ---------------------------------------------------------------------------
# advertising_api.py
# ---------------------------------------------------------------------------

import core.advertising_api as advertising_api
from core.advertising_api import (
    list_platforms_api,
    list_objectives_api as adv_list_objectives_api,
    generate_ad_recommendation_api,
    create_ad_campaign_api,
    get_ad_campaign_api,
    update_ad_campaign_api,
    launch_ad_campaign_api,
    pause_ad_campaign_api,
    complete_ad_campaign_api,
    cancel_ad_campaign_api,
    list_ad_campaigns_api,
)


class _FakeAdCampaign:
    def __init__(self, id, **attrs):
        self.id = id
        self.attributes = attrs


class TestAdvertisingApi:

    def test_list_platforms_no_gate(self, monkeypatch):
        monkeypatch.setattr(advertising_api, "list_platforms", lambda: ["meta", "google"])
        assert list_platforms_api() == ["meta", "google"]

    def test_list_objectives_no_gate(self, monkeypatch):
        monkeypatch.setattr(advertising_api, "list_objectives", lambda: ["awareness", "leads"])
        assert adv_list_objectives_api() == ["awareness", "leads"]

    def test_generate_recommendation_real_result_marks_ai_generated_true(self, monkeypatch):
        monkeypatch.setattr(
            advertising_api, "generate_ad_recommendation",
            lambda brief: {"headline": "Great deals", "budget": 500},
        )
        result = generate_ad_recommendation_api(SALES, {"vehicle": "Truck"})
        assert result == {"headline": "Great deals", "budget": 500, "ai_generated": True}

    def test_generate_recommendation_error_falls_back(self, monkeypatch):
        monkeypatch.setattr(
            advertising_api, "generate_ad_recommendation",
            lambda brief: {"error": "no network"},
        )
        monkeypatch.setattr(
            advertising_api, "fallback_recommendation",
            lambda brief: {"headline": "Fallback headline"},
        )
        result = generate_ad_recommendation_api(SALES, {})
        assert result["ai_generated"] is False
        assert result["ai_error"] == "no network"
        assert result["headline"] == "Fallback headline"

    def test_generate_recommendation_handles_none_brief(self, monkeypatch):
        captured = {}

        def fake_generate(brief):
            captured["brief"] = brief
            return {"ok": True}

        monkeypatch.setattr(advertising_api, "generate_ad_recommendation", fake_generate)
        generate_ad_recommendation_api(SALES, None)
        assert captured["brief"] == {}

    def test_create_ad_campaign_real_error_passes_through(self, monkeypatch):
        monkeypatch.setattr(
            advertising_api, "create_ad_campaign",
            lambda employee_id, platform, objective, name, fields, linked_vehicle_ids: {"error": "bad platform"},
        )
        result = create_ad_campaign_api(SALES, "EMP-1", "bogus", "leads", "Campaign", {})
        assert result == {"error": "bad platform"}

    def test_create_ad_campaign_success_serializes_with_performance_note(self, monkeypatch):
        monkeypatch.setattr(
            advertising_api, "create_ad_campaign",
            lambda employee_id, platform, objective, name, fields, linked_vehicle_ids: _FakeAdCampaign(
                "AD-1", platform=platform, name=name,
            ),
        )
        result = create_ad_campaign_api(SALES, "EMP-1", "meta", "leads", "Spring Sale", {})
        assert result["id"] == "AD-1"
        assert result["platform"] == "meta"
        assert "performance_note" in result

    def test_get_ad_campaign_not_found(self, monkeypatch):
        monkeypatch.setattr(advertising_api, "get_ad_campaign", lambda ad_id: None)
        assert get_ad_campaign_api(SALES, "EMP-1", "AD-missing") == {"error": "Ad campaign not found"}

    def test_get_ad_campaign_found_resolves_vehicles(self, monkeypatch):
        monkeypatch.setattr(advertising_api, "get_ad_campaign", lambda ad_id: _FakeAdCampaign(ad_id, platform="google"))
        monkeypatch.setattr(advertising_api, "resolve_linked_vehicles", lambda ad_id: [{"id": "VEH-1"}])
        result = get_ad_campaign_api(SALES, "EMP-1", "AD-1")
        assert result["id"] == "AD-1"
        assert result["linked_vehicles"] == [{"id": "VEH-1"}]

    def test_update_ad_campaign_not_found(self, monkeypatch):
        monkeypatch.setattr(advertising_api, "get_ad_campaign", lambda ad_id: None)
        assert update_ad_campaign_api(SALES, "EMP-1", "AD-missing", {}) == {"error": "Ad campaign not found"}

    def test_update_ad_campaign_denied_for_non_creator_non_manager(self, monkeypatch):
        monkeypatch.setattr(
            advertising_api, "get_ad_campaign",
            lambda ad_id: _FakeAdCampaign(ad_id, created_by="EMP-OTHER"),
        )
        result = update_ad_campaign_api(SALES, "EMP-1", "AD-1", {"name": "New"})
        assert "Only the creator" in result["error"]

    def test_update_ad_campaign_allowed_for_creator(self, monkeypatch):
        monkeypatch.setattr(
            advertising_api, "get_ad_campaign",
            lambda ad_id: _FakeAdCampaign(ad_id, created_by="EMP-1"),
        )
        monkeypatch.setattr(
            advertising_api, "update_ad_campaign",
            lambda ad_id, patch: _FakeAdCampaign(ad_id, **patch),
        )
        result = update_ad_campaign_api(SALES, "EMP-1", "AD-1", {"name": "Updated"})
        assert result["name"] == "Updated"

    def test_update_ad_campaign_allowed_for_marketing_non_creator(self, monkeypatch):
        monkeypatch.setattr(
            advertising_api, "get_ad_campaign",
            lambda ad_id: _FakeAdCampaign(ad_id, created_by="EMP-OTHER"),
        )
        monkeypatch.setattr(
            advertising_api, "update_ad_campaign",
            lambda ad_id, patch: _FakeAdCampaign(ad_id, **patch),
        )
        result = update_ad_campaign_api(MARKETING, "EMP-1", "AD-1", {"name": "Updated"})
        assert result["name"] == "Updated"

    def test_launch_ad_campaign_denied_for_non_manager(self):
        result = launch_ad_campaign_api(SALES, "EMP-1", "AD-1")
        assert "Only marketing/admin" in result["error"]

    def test_launch_ad_campaign_not_found(self, monkeypatch):
        monkeypatch.setattr(advertising_api, "get_ad_campaign", lambda ad_id: None)
        result = launch_ad_campaign_api(MARKETING, "EMP-1", "AD-missing")
        assert result == {"error": "Ad campaign not found"}

    def test_launch_ad_campaign_allowed(self, monkeypatch):
        monkeypatch.setattr(advertising_api, "get_ad_campaign", lambda ad_id: _FakeAdCampaign(ad_id))
        monkeypatch.setattr(
            advertising_api, "launch_ad_campaign",
            lambda ad_id: _FakeAdCampaign(ad_id, status="active"),
        )
        result = launch_ad_campaign_api(ADMIN, "EMP-1", "AD-1")
        assert result["status"] == "active"

    def test_pause_ad_campaign_denied_for_non_manager(self):
        result = pause_ad_campaign_api(SALES, "EMP-1", "AD-1")
        assert "Only marketing/admin" in result["error"]

    def test_pause_ad_campaign_not_found_via_none_result(self, monkeypatch):
        monkeypatch.setattr(advertising_api, "pause_ad_campaign", lambda ad_id: None)
        result = pause_ad_campaign_api(ADMIN, "EMP-1", "AD-missing")
        assert result == {"error": "Ad campaign not found"}

    def test_pause_ad_campaign_allowed(self, monkeypatch):
        monkeypatch.setattr(
            advertising_api, "pause_ad_campaign",
            lambda ad_id: _FakeAdCampaign(ad_id, status="paused"),
        )
        result = pause_ad_campaign_api(MARKETING, "EMP-1", "AD-1")
        assert result["status"] == "paused"

    def test_complete_ad_campaign_denied_for_non_manager(self):
        result = complete_ad_campaign_api(SALES, "EMP-1", "AD-1")
        assert "Only marketing/admin" in result["error"]

    def test_complete_ad_campaign_not_found_via_none_result(self, monkeypatch):
        monkeypatch.setattr(advertising_api, "complete_ad_campaign", lambda ad_id: None)
        result = complete_ad_campaign_api(ADMIN, "EMP-1", "AD-missing")
        assert result == {"error": "Ad campaign not found"}

    def test_complete_ad_campaign_allowed(self, monkeypatch):
        monkeypatch.setattr(
            advertising_api, "complete_ad_campaign",
            lambda ad_id: _FakeAdCampaign(ad_id, status="completed"),
        )
        result = complete_ad_campaign_api(ADMIN, "EMP-1", "AD-1")
        assert result["status"] == "completed"

    def test_cancel_ad_campaign_not_found(self, monkeypatch):
        monkeypatch.setattr(advertising_api, "get_ad_campaign", lambda ad_id: None)
        assert cancel_ad_campaign_api(SALES, "EMP-1", "AD-missing") == {"error": "Ad campaign not found"}

    def test_cancel_ad_campaign_denied_for_non_creator_non_manager(self, monkeypatch):
        monkeypatch.setattr(
            advertising_api, "get_ad_campaign",
            lambda ad_id: _FakeAdCampaign(ad_id, created_by="EMP-OTHER"),
        )
        result = cancel_ad_campaign_api(SALES, "EMP-1", "AD-1")
        assert "Only the creator" in result["error"]

    def test_cancel_ad_campaign_allowed_for_creator(self, monkeypatch):
        monkeypatch.setattr(
            advertising_api, "get_ad_campaign",
            lambda ad_id: _FakeAdCampaign(ad_id, created_by="EMP-1"),
        )
        monkeypatch.setattr(
            advertising_api, "cancel_ad_campaign",
            lambda ad_id: _FakeAdCampaign(ad_id, status="cancelled"),
        )
        result = cancel_ad_campaign_api(SALES, "EMP-1", "AD-1")
        assert result["status"] == "cancelled"

    def test_list_ad_campaigns_mine_only_filters_by_created_by(self, monkeypatch):
        captured = {}

        def fake_list(platform=None, status=None, created_by=None):
            captured["created_by"] = created_by
            return [_FakeAdCampaign("AD-1")]

        monkeypatch.setattr(advertising_api, "list_ad_campaigns", fake_list)
        list_ad_campaigns_api(SALES, "EMP-1", mine_only=True)
        assert captured["created_by"] == "EMP-1"

    def test_list_ad_campaigns_not_mine_only_passes_none(self, monkeypatch):
        captured = {}

        def fake_list(platform=None, status=None, created_by=None):
            captured["created_by"] = created_by
            return []

        monkeypatch.setattr(advertising_api, "list_ad_campaigns", fake_list)
        list_ad_campaigns_api(SALES, "EMP-1", mine_only=False)
        assert captured["created_by"] is None


# ---------------------------------------------------------------------------
# dealership_events_api.py
# ---------------------------------------------------------------------------

import core.dealership_events_api as dealership_events_api
from core.dealership_events_api import (
    list_event_types_api,
    list_rsvp_statuses_api,
    create_event_api,
    get_event_api,
    update_event_api,
    publish_event_api,
    start_event_api,
    complete_event_api,
    cancel_event_api,
    list_events_api,
    create_rsvp_api,
    update_rsvp_status_api,
    list_event_rsvps_api,
    promote_rsvp_to_lead_api,
)


class _FakeDealerEvent:
    def __init__(self, id, **attrs):
        self.id = id
        self.attributes = attrs


class _FakeRsvp:
    def __init__(self, id, **attrs):
        self.id = id
        self.attributes = attrs


class TestDealershipEventsApi:

    def test_list_event_types_no_gate(self, monkeypatch):
        monkeypatch.setattr(dealership_events_api, "list_event_types", lambda: ["test_drive_event"])
        assert list_event_types_api() == ["test_drive_event"]

    def test_list_rsvp_statuses_no_gate(self, monkeypatch):
        monkeypatch.setattr(dealership_events_api, "RSVP_STATUSES", ("invited", "attended"))
        assert list_rsvp_statuses_api() == ["invited", "attended"]

    def test_create_event_no_role_gate_but_real_error_passes_through(self, monkeypatch):
        monkeypatch.setattr(
            dealership_events_api, "create_event",
            lambda employee_id, name, event_type, start_time, end_time, location, capacity, description, linked_list_id: {
                "error": "Unknown event type",
            },
        )
        result = create_event_api(SALES, "EMP-1", "Launch", "bogus", "2026-08-01")
        assert result == {"error": "Unknown event type"}

    def test_create_event_success_serializes(self, monkeypatch):
        monkeypatch.setattr(
            dealership_events_api, "create_event",
            lambda employee_id, name, event_type, start_time, end_time, location, capacity, description, linked_list_id: _FakeDealerEvent(
                "EVT-1", name=name,
            ),
        )
        result = create_event_api(SALES, "EMP-1", "Launch", "test_drive_event", "2026-08-01")
        assert result == {"id": "EVT-1", "name": "Launch"}

    def test_get_event_always_delegates_to_detail_no_gate(self, monkeypatch):
        monkeypatch.setattr(dealership_events_api, "get_event_detail", lambda event_id: {"id": event_id, "rsvp_count": 3})
        result = get_event_api(SERVICE, "EMP-1", "EVT-1")
        assert result == {"id": "EVT-1", "rsvp_count": 3}

    def test_update_event_not_found(self, monkeypatch):
        monkeypatch.setattr(dealership_events_api, "get_event", lambda event_id: None)
        assert update_event_api(SALES, "EMP-1", "EVT-missing", {}) == {"error": "Event not found"}

    def test_update_event_denied_for_non_creator_non_actor(self, monkeypatch):
        monkeypatch.setattr(
            dealership_events_api, "get_event",
            lambda event_id: _FakeDealerEvent(event_id, created_by="EMP-OTHER"),
        )
        result = update_event_api(SERVICE, "EMP-1", "EVT-1", {"name": "New"})
        assert "Only the creator" in result["error"]

    def test_update_event_allowed_for_creator(self, monkeypatch):
        monkeypatch.setattr(
            dealership_events_api, "get_event",
            lambda event_id: _FakeDealerEvent(event_id, created_by="EMP-1"),
        )
        monkeypatch.setattr(
            dealership_events_api, "update_event",
            lambda event_id, patch: _FakeDealerEvent(event_id, **patch),
        )
        result = update_event_api(SERVICE, "EMP-1", "EVT-1", {"name": "Updated"})
        assert result["name"] == "Updated"

    def test_publish_event_denied_for_non_actor(self):
        result = publish_event_api(SERVICE, "EMP-1", "EVT-1")
        assert "Only admin/marketing/sales" in result["error"]

    def test_publish_event_real_error_passes_through(self, monkeypatch):
        monkeypatch.setattr(dealership_events_api, "publish_event", lambda event_id: {"error": "Already published"})
        result = publish_event_api(SALES, "EMP-1", "EVT-1")
        assert result == {"error": "Already published"}

    def test_publish_event_success_shape(self, monkeypatch):
        monkeypatch.setattr(
            dealership_events_api, "publish_event",
            lambda event_id: {"event": _FakeDealerEvent(event_id, status="published"), "invited_count": 12},
        )
        result = publish_event_api(MARKETING, "EMP-1", "EVT-1")
        assert result == {"event": {"id": "EVT-1", "status": "published"}, "invited_count": 12}

    def test_start_event_denied_for_non_actor(self):
        result = start_event_api(SERVICE, "EMP-1", "EVT-1")
        assert "Only admin/marketing/sales" in result["error"]

    def test_start_event_allowed(self, monkeypatch):
        monkeypatch.setattr(
            dealership_events_api, "start_event",
            lambda event_id: _FakeDealerEvent(event_id, status="in_progress"),
        )
        assert start_event_api(SALES, "EMP-1", "EVT-1") == {"id": "EVT-1", "status": "in_progress"}

    def test_complete_event_denied_for_non_actor(self):
        result = complete_event_api(SERVICE, "EMP-1", "EVT-1")
        assert "Only admin/marketing/sales" in result["error"]

    def test_complete_event_allowed(self, monkeypatch):
        monkeypatch.setattr(
            dealership_events_api, "complete_event",
            lambda event_id: _FakeDealerEvent(event_id, status="completed"),
        )
        assert complete_event_api(ADMIN, "EMP-1", "EVT-1") == {"id": "EVT-1", "status": "completed"}

    def test_cancel_event_not_found(self, monkeypatch):
        monkeypatch.setattr(dealership_events_api, "get_event", lambda event_id: None)
        assert cancel_event_api(SALES, "EMP-1", "EVT-missing") == {"error": "Event not found"}

    def test_cancel_event_denied_for_non_creator_non_actor(self, monkeypatch):
        monkeypatch.setattr(
            dealership_events_api, "get_event",
            lambda event_id: _FakeDealerEvent(event_id, created_by="EMP-OTHER"),
        )
        result = cancel_event_api(SERVICE, "EMP-1", "EVT-1")
        assert "Only the creator" in result["error"]

    def test_cancel_event_allowed_for_creator(self, monkeypatch):
        monkeypatch.setattr(
            dealership_events_api, "get_event",
            lambda event_id: _FakeDealerEvent(event_id, created_by="EMP-1"),
        )
        monkeypatch.setattr(
            dealership_events_api, "cancel_event",
            lambda event_id: _FakeDealerEvent(event_id, status="cancelled"),
        )
        result = cancel_event_api(SERVICE, "EMP-1", "EVT-1")
        assert result["status"] == "cancelled"

    def test_list_events_mine_only_filters(self, monkeypatch):
        captured = {}

        def fake_list(status=None, event_type=None, created_by=None):
            captured["created_by"] = created_by
            return [_FakeDealerEvent("EVT-1")]

        monkeypatch.setattr(dealership_events_api, "list_events", fake_list)
        list_events_api(SALES, "EMP-1", mine_only=True)
        assert captured["created_by"] == "EMP-1"

    def test_create_rsvp_no_gate_real_error_passes_through(self, monkeypatch):
        monkeypatch.setattr(
            dealership_events_api, "create_rsvp",
            lambda event_id, name, phone, email, customer_id, lead_id, source: {"error": "Event not published"},
        )
        result = create_rsvp_api(SERVICE, "EMP-1", "EVT-1", "Jane Doe")
        assert result == {"error": "Event not published"}

    def test_create_rsvp_no_gate_success(self, monkeypatch):
        monkeypatch.setattr(
            dealership_events_api, "create_rsvp",
            lambda event_id, name, phone, email, customer_id, lead_id, source: _FakeRsvp("RSVP-1", name=name),
        )
        result = create_rsvp_api(SERVICE, "EMP-1", "EVT-1", "Jane Doe")
        assert result == {"id": "RSVP-1", "name": "Jane Doe"}

    def test_update_rsvp_status_denied_for_non_actor(self):
        result = update_rsvp_status_api(SERVICE, "EMP-1", "RSVP-1", "attended")
        assert "Only admin/marketing/sales" in result["error"]

    def test_update_rsvp_status_allowed(self, monkeypatch):
        monkeypatch.setattr(
            dealership_events_api, "update_rsvp_status",
            lambda rsvp_id, status: _FakeRsvp(rsvp_id, status=status),
        )
        result = update_rsvp_status_api(SALES, "EMP-1", "RSVP-1", "attended")
        assert result == {"id": "RSVP-1", "status": "attended"}

    def test_list_event_rsvps_no_gate(self, monkeypatch):
        monkeypatch.setattr(
            dealership_events_api, "list_event_rsvps",
            lambda event_id, status=None: [_FakeRsvp("RSVP-1", status="invited")],
        )
        result = list_event_rsvps_api(SERVICE, "EMP-1", "EVT-1")
        assert result == [{"id": "RSVP-1", "status": "invited"}]

    def test_promote_rsvp_to_lead_denied_for_non_actor(self):
        result = promote_rsvp_to_lead_api(SERVICE, "EMP-1", "RSVP-1")
        assert "Only admin/marketing/sales" in result["error"]

    def test_promote_rsvp_to_lead_real_error_passes_through(self, monkeypatch):
        monkeypatch.setattr(
            dealership_events_api, "promote_rsvp_to_lead",
            lambda rsvp_id, employee_id, assign_to_employee_id: {"error": "RSVP not found"},
        )
        result = promote_rsvp_to_lead_api(SALES, "EMP-1", "RSVP-missing")
        assert result == {"error": "RSVP not found"}

    def test_promote_rsvp_to_lead_success_shape(self, monkeypatch):
        monkeypatch.setattr(
            dealership_events_api, "promote_rsvp_to_lead",
            lambda rsvp_id, employee_id, assign_to_employee_id: {
                "rsvp": _FakeRsvp(rsvp_id, status="converted"),
                "lead": _FakeDealerEvent("LEAD-1", Source="Event"),
            },
        )
        result = promote_rsvp_to_lead_api(MARKETING, "EMP-1", "RSVP-1")
        assert result == {
            "rsvp": {"id": "RSVP-1", "status": "converted"},
            "lead": {"id": "LEAD-1", "Source": "Event"},
        }


# ---------------------------------------------------------------------------
# email_templates_api.py
# ---------------------------------------------------------------------------

import core.email_templates_api as email_templates_api
from core.email_templates_api import (
    list_block_types_api,
    list_channels_api,
    create_template_api,
    get_template_api,
    update_template_api,
    list_my_templates_api,
    list_templates_api,
    preview_template_api,
    create_from_wizard_api,
)


class _FakeTemplate:
    def __init__(self, id, **attrs):
        self.id = id
        self.attributes = attrs


class TestEmailTemplatesApi:

    def test_list_block_types_no_gate(self, monkeypatch):
        monkeypatch.setattr(email_templates_api, "list_block_types", lambda: ["heading", "paragraph"])
        assert list_block_types_api() == ["heading", "paragraph"]

    def test_list_channels_no_gate(self, monkeypatch):
        monkeypatch.setattr(email_templates_api, "list_channels", lambda: ["email", "sms"])
        assert list_channels_api() == ["email", "sms"]

    def test_create_template_unknown_channel_rejected(self, monkeypatch):
        monkeypatch.setattr(email_templates_api, "list_channels", lambda: ["email", "sms"])
        result = create_template_api("EMP-1", "carrier_pigeon", "My Template")
        assert result == {"error": "Unknown channel 'carrier_pigeon'"}

    def test_create_template_no_role_param_any_caller(self, monkeypatch):
        monkeypatch.setattr(email_templates_api, "list_channels", lambda: ["email", "sms"])
        monkeypatch.setattr(
            email_templates_api, "create_template",
            lambda channel, name, employee_id: _FakeTemplate("TMPL-1", channel=channel, name=name),
        )
        result = create_template_api("EMP-1", "email", "Welcome Email")
        assert result == {"id": "TMPL-1", "channel": "email", "name": "Welcome Email"}

    def test_get_template_not_found(self, monkeypatch):
        monkeypatch.setattr(email_templates_api, "get_template", lambda template_id: None)
        assert get_template_api(SALES, "EMP-1", "TMPL-missing") == {"error": "Template not found"}

    def test_get_template_denied_for_non_owner_non_manager(self, monkeypatch):
        monkeypatch.setattr(
            email_templates_api, "get_template",
            lambda template_id: _FakeTemplate(template_id, created_by="EMP-OTHER"),
        )
        result = get_template_api(SALES, "EMP-1", "TMPL-1")
        assert "You don't have access" in result["error"]

    def test_get_template_allowed_for_owner(self, monkeypatch):
        monkeypatch.setattr(
            email_templates_api, "get_template",
            lambda template_id: _FakeTemplate(template_id, created_by="EMP-1"),
        )
        result = get_template_api(SALES, "EMP-1", "TMPL-1")
        assert result["id"] == "TMPL-1"

    def test_get_template_allowed_for_marketing_non_owner(self, monkeypatch):
        monkeypatch.setattr(
            email_templates_api, "get_template",
            lambda template_id: _FakeTemplate(template_id, created_by="EMP-OTHER"),
        )
        result = get_template_api(MARKETING, "EMP-1", "TMPL-1")
        assert result["id"] == "TMPL-1"

    def test_update_template_not_found(self, monkeypatch):
        monkeypatch.setattr(email_templates_api, "get_template", lambda template_id: None)
        assert update_template_api(SALES, "EMP-1", "TMPL-missing", {}) == {"error": "Template not found"}

    def test_update_template_denied_for_non_owner_non_manager(self, monkeypatch):
        monkeypatch.setattr(
            email_templates_api, "get_template",
            lambda template_id: _FakeTemplate(template_id, created_by="EMP-OTHER"),
        )
        result = update_template_api(SALES, "EMP-1", "TMPL-1", {"name": "New"})
        assert "You don't have access to edit" in result["error"]

    def test_update_template_allowed_for_owner(self, monkeypatch):
        monkeypatch.setattr(
            email_templates_api, "get_template",
            lambda template_id: _FakeTemplate(template_id, created_by="EMP-1"),
        )
        monkeypatch.setattr(
            email_templates_api, "update_template",
            lambda template_id, patch, by: _FakeTemplate(template_id, **patch),
        )
        result = update_template_api(SALES, "EMP-1", "TMPL-1", {"name": "Updated"})
        assert result["name"] == "Updated"

    def test_list_my_templates_no_gate(self, monkeypatch):
        monkeypatch.setattr(
            email_templates_api, "list_templates",
            lambda created_by=None, channel=None: [_FakeTemplate("TMPL-1", created_by=created_by)],
        )
        result = list_my_templates_api("EMP-1")
        assert result == [{"id": "TMPL-1", "created_by": "EMP-1"}]

    def test_list_templates_manager_sees_everyone(self, monkeypatch):
        monkeypatch.setattr(
            email_templates_api, "list_templates",
            lambda created_by=None, channel=None: [_FakeTemplate("TMPL-1"), _FakeTemplate("TMPL-2")],
        )
        result = list_templates_api(MARKETING, "EMP-1")
        assert len(result) == 2

    def test_list_templates_non_manager_sees_only_own(self, monkeypatch):
        captured = {}

        def fake_list(created_by=None, channel=None):
            captured["created_by"] = created_by
            return [_FakeTemplate("TMPL-1")]

        monkeypatch.setattr(email_templates_api, "list_templates", fake_list)
        list_templates_api(SALES, "EMP-1")
        assert captured["created_by"] == "EMP-1"

    def test_preview_template_not_found(self, monkeypatch):
        monkeypatch.setattr(email_templates_api, "get_template", lambda template_id: None)
        assert preview_template_api(SALES, "EMP-1", "TMPL-missing") == {"error": "Template not found"}

    def test_preview_template_denied_for_non_owner_non_manager(self, monkeypatch):
        monkeypatch.setattr(
            email_templates_api, "get_template",
            lambda template_id: _FakeTemplate(template_id, created_by="EMP-OTHER"),
        )
        result = preview_template_api(SALES, "EMP-1", "TMPL-1")
        assert "You don't have access" in result["error"]

    def test_preview_template_sms_shape(self, monkeypatch):
        monkeypatch.setattr(
            email_templates_api, "get_template",
            lambda template_id: _FakeTemplate(template_id, created_by="EMP-1", channel="sms", sms_body="Hi there"),
        )
        monkeypatch.setattr(email_templates_api, "sms_segment_info", lambda body: {"segments": 1})
        result = preview_template_api(SALES, "EMP-1", "TMPL-1")
        assert result == {"channel": "sms", "sms_body": "Hi there", "segment_info": {"segments": 1}}

    def test_preview_template_email_shape(self, monkeypatch):
        monkeypatch.setattr(
            email_templates_api, "get_template",
            lambda template_id: _FakeTemplate(
                template_id, created_by="EMP-1", channel="email", subject="Hello", preheader="preview",
            ),
        )
        monkeypatch.setattr(email_templates_api, "render_email_html", lambda template: "<p>Hi</p>")
        monkeypatch.setattr(email_templates_api, "render_email_text", lambda template: "Hi")
        result = preview_template_api(SALES, "EMP-1", "TMPL-1")
        assert result == {
            "channel": "email", "subject": "Hello", "preheader": "preview", "html": "<p>Hi</p>", "text": "Hi",
        }

    def test_create_from_wizard_unknown_channel_rejected(self, monkeypatch):
        monkeypatch.setattr(email_templates_api, "list_channels", lambda: ["email", "sms"])
        result = create_from_wizard_api("EMP-1", "carrier_pigeon", "goal", "audience", "friendly")
        assert result == {"error": "Unknown channel 'carrier_pigeon'"}

    def test_create_from_wizard_sms_uses_fallback_on_ai_error(self, monkeypatch):
        monkeypatch.setattr(email_templates_api, "list_channels", lambda: ["email", "sms"])
        monkeypatch.setattr(email_templates_api, "generate_sms_copy", lambda brief: {"error": "no network"})
        monkeypatch.setattr(email_templates_api, "fallback_copy", lambda brief, channel: {"sms_body": "Fallback text"})
        monkeypatch.setattr(
            email_templates_api, "create_template",
            lambda channel, name, employee_id, ai_generated=False: _FakeTemplate("TMPL-1", channel=channel, name=name),
        )
        captured = {}

        def fake_update(template_id, patch, by):
            captured["patch"] = patch

        monkeypatch.setattr(email_templates_api, "update_template", fake_update)
        monkeypatch.setattr(
            email_templates_api, "get_template",
            lambda template_id: _FakeTemplate(template_id, sms_body=captured["patch"]["sms_body"]),
        )
        result = create_from_wizard_api("EMP-1", "sms", "Sale", "Truck buyers", "friendly")
        assert result["sms_body"] == "Fallback text"

    def test_create_from_wizard_email_assembles_blocks(self, monkeypatch):
        monkeypatch.setattr(email_templates_api, "list_channels", lambda: ["email", "sms"])
        monkeypatch.setattr(
            email_templates_api, "generate_email_copy",
            lambda brief: {
                "subject": "Big Sale", "preheader": "Don't miss it", "heading": "Save Now",
                "body": "Come on down", "cta_text": "Shop Now",
            },
        )
        monkeypatch.setattr(
            email_templates_api, "create_template",
            lambda channel, name, employee_id, ai_generated=False: _FakeTemplate("TMPL-1", channel=channel, name=name),
        )
        monkeypatch.setattr(email_templates_api, "BLOCK_TYPES", {"footer": {"fields": [{"default": "© NXTDeal"}]}})
        captured = {}

        def fake_update(template_id, patch, by):
            captured["patch"] = patch

        monkeypatch.setattr(email_templates_api, "update_template", fake_update)
        monkeypatch.setattr(
            email_templates_api, "get_template",
            lambda template_id: _FakeTemplate(template_id, subject=captured["patch"]["subject"], blocks=captured["patch"]["blocks"]),
        )
        result = create_from_wizard_api("EMP-1", "email", "Sale", "Truck buyers", "friendly")
        assert result["subject"] == "Big Sale"
        assert len(result["blocks"]) == 4
        assert result["blocks"][0]["block_key"] == "heading"
        assert result["blocks"][0]["fields"]["text"] == "Save Now"


# ---------------------------------------------------------------------------
# website_chat_api.py
# ---------------------------------------------------------------------------

import core.website_chat_api as website_chat_api
from core.website_chat_api import (
    start_chat_session_api,
    list_departments_api,
    send_visitor_message_api,
    list_messages_api,
    get_session_api,
    list_open_sessions_api,
    send_employee_reply_api,
    claim_session_api,
    close_session_api,
    promote_session_api,
    list_unified_inbox_api,
    generate_ai_reply_api,
)


class _FakeChatSession:
    def __init__(self, id, **attrs):
        self.id = id
        self.attributes = attrs


class _FakeChatMessage:
    def __init__(self, id, **attrs):
        self.id = id
        self.attributes = attrs


class _FakeWebsite:
    def __init__(self, id, **attrs):
        self.id = id
        self.attributes = attrs


class TestWebsiteChatApi:

    def test_start_chat_session_public_real_error_passes_through(self, monkeypatch):
        monkeypatch.setattr(
            website_chat_api, "start_chat_session",
            lambda website_id, visitor_name, visitor_email, initial_message, department: {"error": "Website not found"},
        )
        result = start_chat_session_api("SITE-missing")
        assert result == {"error": "Website not found"}

    def test_start_chat_session_public_success(self, monkeypatch):
        monkeypatch.setattr(
            website_chat_api, "start_chat_session",
            lambda website_id, visitor_name, visitor_email, initial_message, department: _FakeChatSession(
                "CHAT-1", website_id=website_id,
            ),
        )
        result = start_chat_session_api("SITE-1", visitor_name="Jane")
        assert result == {"id": "CHAT-1", "website_id": "SITE-1"}

    def test_list_departments_public_no_gate(self, monkeypatch):
        monkeypatch.setattr(website_chat_api, "list_departments", lambda: ["sales", "service"])
        assert list_departments_api() == ["sales", "service"]

    def test_send_visitor_message_public_real_error_passes_through(self, monkeypatch):
        monkeypatch.setattr(
            website_chat_api, "send_visitor_message",
            lambda session_id, body: {"error": "Session closed"},
        )
        result = send_visitor_message_api("CHAT-1", "Hello?")
        assert result == {"error": "Session closed"}

    def test_send_visitor_message_public_success(self, monkeypatch):
        monkeypatch.setattr(
            website_chat_api, "send_visitor_message",
            lambda session_id, body: _FakeChatMessage("MSG-1", body=body, sender="visitor"),
        )
        result = send_visitor_message_api("CHAT-1", "Hello?")
        assert result == {"id": "MSG-1", "body": "Hello?", "sender": "visitor"}

    def test_list_messages_session_not_found(self, monkeypatch):
        monkeypatch.setattr(website_chat_api, "get_session", lambda session_id: None)
        assert list_messages_api("CHAT-missing") == {"error": "Chat session not found"}

    def test_list_messages_found_delegates(self, monkeypatch):
        monkeypatch.setattr(website_chat_api, "get_session", lambda session_id: _FakeChatSession(session_id))
        monkeypatch.setattr(
            website_chat_api, "list_messages",
            lambda session_id, since=None: [_FakeChatMessage("MSG-1", body="Hi")],
        )
        result = list_messages_api("CHAT-1")
        assert result == [{"id": "MSG-1", "body": "Hi"}]

    def test_get_session_public_not_found(self, monkeypatch):
        monkeypatch.setattr(website_chat_api, "get_session", lambda session_id: None)
        assert get_session_api("CHAT-missing") == {"error": "Chat session not found"}

    def test_get_session_public_found(self, monkeypatch):
        monkeypatch.setattr(website_chat_api, "get_session", lambda session_id: _FakeChatSession(session_id, status="open"))
        assert get_session_api("CHAT-1") == {"id": "CHAT-1", "status": "open"}

    def test_list_open_sessions_denied_for_non_manager_non_owner(self, monkeypatch):
        monkeypatch.setattr(website_chat_api, "get_website", lambda website_id: _FakeWebsite(website_id, requested_by="EMP-OTHER"))
        monkeypatch.setattr(website_chat_api, "is_owner", lambda website, employee_id: False)
        result = list_open_sessions_api(SALES, "EMP-1", "SITE-1")
        assert "You don't have access" in result["error"]

    def test_list_open_sessions_allowed_for_admin_regardless_of_site(self, monkeypatch):
        monkeypatch.setattr(website_chat_api, "list_sessions", lambda website_id=None: [_FakeChatSession("CHAT-1")])
        result = list_open_sessions_api(ADMIN, "EMP-1", "SITE-1")
        assert result == [{"id": "CHAT-1"}]

    def test_list_open_sessions_allowed_for_site_owner(self, monkeypatch):
        monkeypatch.setattr(website_chat_api, "get_website", lambda website_id: _FakeWebsite(website_id, requested_by="EMP-1"))
        monkeypatch.setattr(website_chat_api, "list_sessions", lambda website_id=None: [_FakeChatSession("CHAT-1")])
        result = list_open_sessions_api(SALES, "EMP-1", "SITE-1")
        assert result == [{"id": "CHAT-1"}]

    def test_send_employee_reply_session_not_found(self, monkeypatch):
        monkeypatch.setattr(website_chat_api, "get_session", lambda session_id: None)
        result = send_employee_reply_api(ADMIN, "EMP-1", "CHAT-missing", "Hi there")
        assert result == {"error": "Chat session not found"}

    def test_send_employee_reply_denied_for_non_manager_non_owner(self, monkeypatch):
        monkeypatch.setattr(
            website_chat_api, "get_session",
            lambda session_id: _FakeChatSession(session_id, website_id="SITE-1"),
        )
        monkeypatch.setattr(website_chat_api, "get_website", lambda website_id: _FakeWebsite(website_id, requested_by="EMP-OTHER"))
        monkeypatch.setattr(website_chat_api, "is_owner", lambda website, employee_id: False)
        result = send_employee_reply_api(SALES, "EMP-1", "CHAT-1", "Hi there")
        assert "You don't have access" in result["error"]

    def test_send_employee_reply_allowed_for_admin(self, monkeypatch):
        monkeypatch.setattr(
            website_chat_api, "get_session",
            lambda session_id: _FakeChatSession(session_id, website_id="SITE-1"),
        )
        monkeypatch.setattr(
            website_chat_api, "send_employee_message",
            lambda session_id, employee_id, body: _FakeChatMessage("MSG-1", body=body, sender="employee"),
        )
        result = send_employee_reply_api(ADMIN, "EMP-1", "CHAT-1", "Hi there")
        assert result == {"id": "MSG-1", "body": "Hi there", "sender": "employee"}

    def test_claim_session_not_found(self, monkeypatch):
        monkeypatch.setattr(website_chat_api, "get_session", lambda session_id: None)
        assert claim_session_api(ADMIN, "EMP-1", "CHAT-missing") == {"error": "Chat session not found"}

    def test_claim_session_denied_for_non_manager_non_owner(self, monkeypatch):
        monkeypatch.setattr(
            website_chat_api, "get_session",
            lambda session_id: _FakeChatSession(session_id, website_id="SITE-1"),
        )
        monkeypatch.setattr(website_chat_api, "get_website", lambda website_id: _FakeWebsite(website_id, requested_by="EMP-OTHER"))
        monkeypatch.setattr(website_chat_api, "is_owner", lambda website, employee_id: False)
        result = claim_session_api(SALES, "EMP-1", "CHAT-1")
        assert "You don't have access" in result["error"]

    def test_claim_session_allowed_for_admin(self, monkeypatch):
        monkeypatch.setattr(
            website_chat_api, "get_session",
            lambda session_id: _FakeChatSession(session_id, website_id="SITE-1"),
        )
        monkeypatch.setattr(
            website_chat_api, "claim_session",
            lambda session_id, employee_id: _FakeChatSession(session_id, claimed_by=employee_id),
        )
        result = claim_session_api(ADMIN, "EMP-1", "CHAT-1")
        assert result == {"id": "CHAT-1", "claimed_by": "EMP-1"}

    def test_close_session_not_found(self, monkeypatch):
        monkeypatch.setattr(website_chat_api, "get_session", lambda session_id: None)
        assert close_session_api(ADMIN, "EMP-1", "CHAT-missing") == {"error": "Chat session not found"}

    def test_close_session_allowed_for_admin(self, monkeypatch):
        monkeypatch.setattr(
            website_chat_api, "get_session",
            lambda session_id: _FakeChatSession(session_id, website_id="SITE-1"),
        )
        monkeypatch.setattr(
            website_chat_api, "close_session",
            lambda session_id, by: _FakeChatSession(session_id, status="closed"),
        )
        result = close_session_api(ADMIN, "EMP-1", "CHAT-1")
        assert result == {"id": "CHAT-1", "status": "closed"}

    def test_promote_session_not_found(self, monkeypatch):
        monkeypatch.setattr(website_chat_api, "get_session", lambda session_id: None)
        assert promote_session_api(ADMIN, "EMP-1", "CHAT-missing") == {"error": "Chat session not found"}

    def test_promote_session_denied_for_non_manager_non_owner(self, monkeypatch):
        monkeypatch.setattr(
            website_chat_api, "get_session",
            lambda session_id: _FakeChatSession(session_id, website_id="SITE-1"),
        )
        monkeypatch.setattr(website_chat_api, "get_website", lambda website_id: _FakeWebsite(website_id, requested_by="EMP-OTHER"))
        monkeypatch.setattr(website_chat_api, "is_owner", lambda website, employee_id: False)
        result = promote_session_api(SALES, "EMP-1", "CHAT-1")
        assert "You don't have access" in result["error"]

    def test_promote_session_allowed_delegates_directly(self, monkeypatch):
        monkeypatch.setattr(
            website_chat_api, "get_session",
            lambda session_id: _FakeChatSession(session_id, website_id="SITE-1"),
        )
        monkeypatch.setattr(
            website_chat_api, "promote_session_to_lead",
            lambda session_id, employee_id, name, email, phone: {"lead_id": "LEAD-1"},
        )
        result = promote_session_api(ADMIN, "EMP-1", "CHAT-1", name="Jane")
        assert result == {"lead_id": "LEAD-1"}

    def test_managed_website_ids_admin_gets_none_no_filter(self):
        assert website_chat_api._managed_website_ids(ADMIN, "EMP-1") is None
        assert website_chat_api._managed_website_ids(MARKETING, "EMP-1") is None

    def test_managed_website_ids_non_manager_filters_by_ownership(self, monkeypatch):
        monkeypatch.setattr(
            website_chat_api, "list_websites",
            lambda: [
                _FakeWebsite("SITE-1", requested_by="EMP-1"),
                _FakeWebsite("SITE-2", requested_by="EMP-OTHER"),
            ],
        )
        monkeypatch.setattr(website_chat_api, "is_owner", lambda website, employee_id: False)
        result = website_chat_api._managed_website_ids(SALES, "EMP-1")
        assert result == ["SITE-1"]

    def test_list_unified_inbox_returns_empty_list_when_no_managed_sites(self, monkeypatch):
        monkeypatch.setattr(website_chat_api, "list_websites", lambda: [])
        monkeypatch.setattr(website_chat_api, "is_owner", lambda website, employee_id: False)
        result = list_unified_inbox_api(SALES, "EMP-1")
        assert result == []

    def test_list_unified_inbox_enriches_with_website_name(self, monkeypatch):
        monkeypatch.setattr(
            website_chat_api, "list_unified_inbox",
            lambda website_ids=None, status=None, department=None: [_FakeChatSession("CHAT-1", website_id="SITE-1")],
        )
        monkeypatch.setattr(website_chat_api, "get_website", lambda website_id: _FakeWebsite(website_id, name="Main Site"))
        result = list_unified_inbox_api(ADMIN, "EMP-1")
        assert result == [{"id": "CHAT-1", "website_id": "SITE-1", "website_name": "Main Site"}]

    def test_list_unified_inbox_handles_missing_website(self, monkeypatch):
        monkeypatch.setattr(
            website_chat_api, "list_unified_inbox",
            lambda website_ids=None, status=None, department=None: [_FakeChatSession("CHAT-1", website_id="SITE-gone")],
        )
        monkeypatch.setattr(website_chat_api, "get_website", lambda website_id: None)
        result = list_unified_inbox_api(ADMIN, "EMP-1")
        assert result[0]["website_name"] is None

    def test_generate_ai_reply_not_found(self, monkeypatch):
        monkeypatch.setattr(website_chat_api, "get_session", lambda session_id: None)
        assert generate_ai_reply_api(ADMIN, "EMP-1", "CHAT-missing") == {"error": "Chat session not found"}

    def test_generate_ai_reply_denied_for_non_manager_non_owner(self, monkeypatch):
        monkeypatch.setattr(
            website_chat_api, "get_session",
            lambda session_id: _FakeChatSession(session_id, website_id="SITE-1"),
        )
        monkeypatch.setattr(website_chat_api, "get_website", lambda website_id: _FakeWebsite(website_id, requested_by="EMP-OTHER"))
        monkeypatch.setattr(website_chat_api, "is_owner", lambda website, employee_id: False)
        result = generate_ai_reply_api(SALES, "EMP-1", "CHAT-1")
        assert "You don't have access" in result["error"]

    def test_generate_ai_reply_real_error_passes_through(self, monkeypatch):
        monkeypatch.setattr(
            website_chat_api, "get_session",
            lambda session_id: _FakeChatSession(session_id, website_id="SITE-1"),
        )
        monkeypatch.setattr(website_chat_api, "ai_respond_to_session", lambda session_id: {"error": "AI disabled"})
        result = generate_ai_reply_api(ADMIN, "EMP-1", "CHAT-1")
        assert result == {"error": "AI disabled"}

    def test_generate_ai_reply_success(self, monkeypatch):
        monkeypatch.setattr(
            website_chat_api, "get_session",
            lambda session_id: _FakeChatSession(session_id, website_id="SITE-1"),
        )
        monkeypatch.setattr(
            website_chat_api, "ai_respond_to_session",
            lambda session_id: _FakeChatMessage("MSG-1", body="AI reply", sender="ai"),
        )
        result = generate_ai_reply_api(ADMIN, "EMP-1", "CHAT-1")
        assert result == {"id": "MSG-1", "body": "AI reply", "sender": "ai"}
