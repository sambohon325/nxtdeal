"""
Tests for core/system_config.py / core/system_config_api.py -- Administration's
combined Organization/System Configuration singleton (create-on-first-read,
backfill-on-read, Business Hours, feature flags, Performance Readiness's real
department Goal Tracking), plus the ACL layer.

Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import SYSTEM_CONFIG
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE

import core.system_config as system_config
from core.system_config import (
    get_system_config,
    update_organization_profile,
    add_location,
    remove_location,
    update_business_hours,
    update_defaults,
    set_feature_flag,
    get_department_goals,
    set_department_goal,
    clear_department_goal,
    FEATURE_FLAGS,
    GOAL_TRACKED_DEPARTMENTS,
    _CONFIG_ID,
)
from core.system_config_api import (
    get_system_config_api,
    update_organization_profile_api,
    add_location_api,
    remove_location_api,
    update_business_hours_api,
    update_defaults_api,
    set_feature_flag_api,
    get_department_goals_api,
    set_department_goal_api,
    clear_department_goal_api,
)


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    monkeypatch.setattr(system_config, "save_graph", lambda filepath: None)


# ---------------------------------------------------------------------------
# get_system_config() / _get_or_create()
# ---------------------------------------------------------------------------

class TestGetSystemConfig:

    def test_creates_singleton_on_first_read(self):
        assert ledger.get_entity(_CONFIG_ID) is None
        result = get_system_config()
        assert result["id"] == _CONFIG_ID
        assert ledger.get_entity(_CONFIG_ID) is not None

    def test_default_organization_fields_are_empty(self):
        result = get_system_config()
        assert result["dealership_name"] == ""
        assert result["locations"] == []

    def test_default_business_hours_cover_every_day(self):
        result = get_system_config()
        for day in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"):
            assert day in result["business_hours"]
        assert result["business_hours"]["sunday"] == "Closed"

    def test_default_currency_and_timezone(self):
        result = get_system_config()
        assert result["default_currency"] == "USD"
        assert result["default_timezone"] == "America/Chicago"

    def test_default_feature_flags_all_true(self):
        result = get_system_config()
        for flag in FEATURE_FLAGS:
            assert result["feature_flags"][flag] is True

    def test_default_department_goals_empty(self):
        result = get_system_config()
        assert result["department_goals"] == {}

    def test_repeated_reads_return_the_same_singleton(self):
        first = get_system_config()
        second = get_system_config()
        assert first["id"] == second["id"] == _CONFIG_ID
        assert len(ledger.get_all()) == 1

    def test_backfills_missing_top_level_key_on_a_stale_entity(self):
        # Simulate a SystemConfig entity that predates a newer default key.
        entity = Entity(id=_CONFIG_ID, entity_type=SYSTEM_CONFIG, attributes={
            "dealership_name": "Existing Dealer",
            "feature_flags": {},
            "updated_by": None,
            "updated_at": "2020-01-01T00:00:00+00:00",
        })
        ledger.add_entity(entity)

        result = get_system_config()

        assert result["dealership_name"] == "Existing Dealer"  # untouched
        assert "business_hours" in result  # backfilled
        assert "department_goals" in result  # backfilled

    def test_backfills_missing_feature_flags_inside_an_already_present_dict(self):
        entity = Entity(id=_CONFIG_ID, entity_type=SYSTEM_CONFIG, attributes={
            "feature_flags": {"ai_assistant_enabled": False},
            "updated_by": None,
            "updated_at": "2020-01-01T00:00:00+00:00",
            "dealership_name": "",
            "dba_name": "", "ein": "", "address_line1": "", "address_line2": "",
            "city": "", "state": "", "zip_code": "", "phone": "", "website_url": "",
            "locations": [], "business_hours": {}, "default_currency": "USD",
            "default_timezone": "America/Chicago", "department_goals": {},
        })
        ledger.add_entity(entity)

        result = get_system_config()

        # Explicitly-set flag is preserved, not clobbered back to True.
        assert result["feature_flags"]["ai_assistant_enabled"] is False
        # Every other real flag gets backfilled to the honest default (True).
        for flag in FEATURE_FLAGS:
            if flag != "ai_assistant_enabled":
                assert result["feature_flags"][flag] is True


# ---------------------------------------------------------------------------
# update_organization_profile()
# ---------------------------------------------------------------------------

class TestUpdateOrganizationProfile:

    def test_updates_editable_fields(self):
        result = update_organization_profile("EMP-1", dealership_name="Acme Motors", city="Springfield")
        assert result["dealership_name"] == "Acme Motors"
        assert result["city"] == "Springfield"
        assert result["updated_by"] == "EMP-1"

    def test_none_values_are_ignored(self):
        update_organization_profile("EMP-1", dealership_name="Acme Motors")
        result = update_organization_profile("EMP-1", dealership_name=None)
        assert result["dealership_name"] == "Acme Motors"

    def test_non_editable_keys_are_ignored(self):
        result = update_organization_profile("EMP-1", locations=["should not apply"], id="FAKE-ID")
        assert result["locations"] == []
        assert result["id"] == _CONFIG_ID


# ---------------------------------------------------------------------------
# add_location() / remove_location()
# ---------------------------------------------------------------------------

class TestLocations:

    def test_empty_name_rejected(self):
        result = add_location("", "123 Main St", "EMP-1")
        assert result == {"error": "A location name is required"}

    def test_whitespace_only_name_rejected(self):
        result = add_location("   ", "123 Main St", "EMP-1")
        assert result == {"error": "A location name is required"}

    def test_add_location_appends(self):
        result = add_location("Main Store", "123 Main St", "EMP-1", is_primary=True)
        assert len(result["locations"]) == 1
        assert result["locations"][0]["name"] == "Main Store"
        assert result["locations"][0]["is_primary"] is True

    def test_setting_a_new_primary_clears_old_primary(self):
        add_location("Main Store", "123 Main St", "EMP-1", is_primary=True)
        result = add_location("Second Store", "456 Oak Ave", "EMP-1", is_primary=True)
        assert result["locations"][0]["is_primary"] is False
        assert result["locations"][1]["is_primary"] is True

    def test_remove_location_out_of_range(self):
        result = remove_location(0, "EMP-1")
        assert result == {"error": "Location index out of range"}

    def test_remove_location_negative_index(self):
        add_location("Main Store", "123 Main St", "EMP-1")
        result = remove_location(-1, "EMP-1")
        assert result == {"error": "Location index out of range"}

    def test_remove_location_succeeds(self):
        add_location("Main Store", "123 Main St", "EMP-1")
        add_location("Second Store", "456 Oak Ave", "EMP-1")
        result = remove_location(0, "EMP-1")
        assert len(result["locations"]) == 1
        assert result["locations"][0]["name"] == "Second Store"


# ---------------------------------------------------------------------------
# update_business_hours()
# ---------------------------------------------------------------------------

class TestBusinessHours:

    def test_unknown_day_rejected(self):
        result = update_business_hours("someday", "9-5", "EMP-1")
        assert result == {"error": "Unknown day 'someday'"}

    def test_updates_a_real_day_case_insensitively(self):
        result = update_business_hours("MONDAY", "10:00 AM - 8:00 PM", "EMP-1")
        assert result["business_hours"]["monday"] == "10:00 AM - 8:00 PM"

    def test_none_day_rejected(self):
        result = update_business_hours(None, "9-5", "EMP-1")
        assert result == {"error": "Unknown day ''"}


# ---------------------------------------------------------------------------
# update_defaults()
# ---------------------------------------------------------------------------

class TestUpdateDefaults:

    def test_updates_currency_only(self):
        result = update_defaults("EMP-1", default_currency="CAD")
        assert result["default_currency"] == "CAD"
        assert result["default_timezone"] == "America/Chicago"

    def test_updates_timezone_only(self):
        result = update_defaults("EMP-1", default_timezone="America/New_York")
        assert result["default_timezone"] == "America/New_York"
        assert result["default_currency"] == "USD"

    def test_updates_both(self):
        result = update_defaults("EMP-1", default_currency="EUR", default_timezone="Europe/Berlin")
        assert result["default_currency"] == "EUR"
        assert result["default_timezone"] == "Europe/Berlin"


# ---------------------------------------------------------------------------
# set_feature_flag()
# ---------------------------------------------------------------------------

class TestSetFeatureFlag:

    def test_unknown_flag_rejected(self):
        result = set_feature_flag("not_a_real_flag", False, "EMP-1")
        assert "error" in result

    def test_toggles_a_real_flag_off(self):
        result = set_feature_flag("ai_assistant_enabled", False, "EMP-1")
        assert result["feature_flags"]["ai_assistant_enabled"] is False

    def test_toggles_a_real_flag_back_on(self):
        set_feature_flag("ai_assistant_enabled", False, "EMP-1")
        result = set_feature_flag("ai_assistant_enabled", True, "EMP-1")
        assert result["feature_flags"]["ai_assistant_enabled"] is True

    def test_enabled_coerced_to_bool(self):
        result = set_feature_flag("ai_assistant_enabled", 0, "EMP-1")
        assert result["feature_flags"]["ai_assistant_enabled"] is False


# ---------------------------------------------------------------------------
# get_department_goals() / set_department_goal() / clear_department_goal()
# ---------------------------------------------------------------------------

class TestDepartmentGoals:

    def test_default_goals_empty(self):
        assert get_department_goals() == {}

    def test_unknown_department_rejected_on_set(self):
        result = set_department_goal("inventory", 100, "EMP-1")
        assert "error" in result

    def test_non_numeric_target_rejected(self):
        result = set_department_goal("sales", "not-a-number", "EMP-1")
        assert result == {"error": "monthly_target must be a positive number."}

    def test_non_positive_target_rejected(self):
        result = set_department_goal("sales", 0, "EMP-1")
        assert result == {"error": "monthly_target must be a positive number."}

    def test_negative_target_rejected(self):
        result = set_department_goal("sales", -50, "EMP-1")
        assert result == {"error": "monthly_target must be a positive number."}

    def test_valid_goal_is_set(self):
        set_department_goal("sales", 120, "EMP-1")
        assert get_department_goals() == {"sales": 120.0}

    def test_department_lowercased(self):
        set_department_goal("SALES", 120, "EMP-1")
        assert get_department_goals() == {"sales": 120.0}

    def test_only_tracked_departments_settable(self):
        for dept in GOAL_TRACKED_DEPARTMENTS:
            result = set_department_goal(dept, 50, "EMP-1")
            assert "error" not in result

    def test_clear_unknown_department_rejected(self):
        result = clear_department_goal("finance", "EMP-1")
        assert "error" in result

    def test_clear_removes_a_set_goal(self):
        set_department_goal("marketing", 900, "EMP-1")
        clear_department_goal("marketing", "EMP-1")
        assert get_department_goals() == {}

    def test_clear_on_never_set_goal_is_a_harmless_no_op(self):
        result = clear_department_goal("service", "EMP-1")
        assert "error" not in result
        assert get_department_goals() == {}


# ---------------------------------------------------------------------------
# ACL layer
# ---------------------------------------------------------------------------

class TestGetSystemConfigApi:

    def test_unknown_role_denied(self):
        result = get_system_config_api("NOT_A_ROLE")
        assert result == {"error": "You don't have access to this action."}

    @pytest.mark.parametrize("role", [ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE])
    def test_all_real_roles_can_view(self, role):
        result = get_system_config_api(role)
        assert "error" not in result


class TestGetDepartmentGoalsApi:

    @pytest.mark.parametrize("role", [ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE])
    def test_all_real_roles_can_view(self, role):
        result = get_department_goals_api(role)
        assert result["tracked_departments"] == list(GOAL_TRACKED_DEPARTMENTS)


class TestMutatingRoutesAreAdminOnly:

    @pytest.mark.parametrize("role", [SALES, MARKETING, SERVICE, FINANCE])
    def test_update_organization_profile_denied(self, role):
        result = update_organization_profile_api(role, "EMP-1", dealership_name="Nope")
        assert result == {"error": "Admin/Operations role required."}

    @pytest.mark.parametrize("role", [SALES, MARKETING, SERVICE, FINANCE])
    def test_add_location_denied(self, role):
        result = add_location_api(role, "EMP-1", "Store", "Address")
        assert result == {"error": "Admin/Operations role required."}

    @pytest.mark.parametrize("role", [SALES, MARKETING, SERVICE, FINANCE])
    def test_remove_location_denied(self, role):
        result = remove_location_api(role, "EMP-1", 0)
        assert result == {"error": "Admin/Operations role required."}

    @pytest.mark.parametrize("role", [SALES, MARKETING, SERVICE, FINANCE])
    def test_update_business_hours_denied(self, role):
        result = update_business_hours_api(role, "EMP-1", "monday", "closed")
        assert result == {"error": "Admin/Operations role required."}

    @pytest.mark.parametrize("role", [SALES, MARKETING, SERVICE, FINANCE])
    def test_update_defaults_denied(self, role):
        result = update_defaults_api(role, "EMP-1", default_currency="CAD")
        assert result == {"error": "Admin/Operations role required."}

    @pytest.mark.parametrize("role", [SALES, MARKETING, SERVICE, FINANCE])
    def test_set_feature_flag_denied(self, role):
        result = set_feature_flag_api(role, "EMP-1", "ai_assistant_enabled", False)
        assert result == {"error": "Admin/Operations role required."}

    @pytest.mark.parametrize("role", [SALES, MARKETING, SERVICE, FINANCE])
    def test_set_department_goal_denied(self, role):
        result = set_department_goal_api(role, "EMP-1", "sales", 100)
        assert result == {"error": "Admin/Operations role required."}

    @pytest.mark.parametrize("role", [SALES, MARKETING, SERVICE, FINANCE])
    def test_clear_department_goal_denied(self, role):
        result = clear_department_goal_api(role, "EMP-1", "sales")
        assert result == {"error": "Admin/Operations role required."}

    @pytest.mark.parametrize("role", [ADMIN, OPERATIONS])
    def test_admin_and_operations_can_mutate(self, role):
        result = update_organization_profile_api(role, "EMP-1", dealership_name="Acme")
        assert result["dealership_name"] == "Acme"

        result = set_department_goal_api(role, "EMP-1", "sales", 200)
        assert result["department_goals"]["sales"] == 200.0

        result = clear_department_goal_api(role, "EMP-1", "sales")
        assert result["department_goals"] == {}

        result = add_location_api(role, "EMP-1", "Store", "Addr")
        assert len(result["locations"]) == 1

        result = remove_location_api(role, "EMP-1", 0)
        assert result["locations"] == []

        result = update_business_hours_api(role, "EMP-1", "monday", "Closed")
        assert result["business_hours"]["monday"] == "Closed"

        result = update_defaults_api(role, "EMP-1", default_currency="GBP")
        assert result["default_currency"] == "GBP"

        result = set_feature_flag_api(role, "EMP-1", "ai_assistant_enabled", False)
        assert result["feature_flags"]["ai_assistant_enabled"] is False
