"""
Tests for core/vendor_management.py / core/vendor_management_api.py -- the real
Vendor record (contact info, contract term, monthly cost, category) that closed
most of Administration's old vendors() not_yet_tracked list for real.

Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date, timedelta

import pytest

from core.dealeros import ledger
from core.entity_types import VENDOR

from core import vendor_management
from core import vendor_management_api
from core.permissions import ADMIN, OPERATIONS, SALES, FINANCE, MARKETING


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    monkeypatch.setattr(vendor_management, "save_graph", lambda filepath: None)


class TestCreateVendor:

    def test_creates_a_real_vendor_entity_with_defaults(self):
        result = vendor_management.create_vendor("Acme Parts", "parts_supplier", "EMP-1")

        assert "error" not in result
        assert result["id"].startswith("VNDR-")
        assert result["name"] == "Acme Parts"
        assert result["category"] == "parts_supplier"
        assert result["status"] == "active"
        assert result["auto_renew"] is False
        assert result["created_by"] == "EMP-1"

        entity = ledger.get_entity(result["id"])
        assert entity is not None
        assert entity.entity_type == VENDOR

    def test_rejects_a_bad_category(self):
        result = vendor_management.create_vendor("Acme Parts", "bogus_category", "EMP-1")

        assert "error" in result
        assert ledger.get_all() == {}

    def test_rejects_an_empty_name(self):
        result = vendor_management.create_vendor("", "software", "EMP-1")

        assert "error" in result

    def test_rejects_a_whitespace_only_name(self):
        result = vendor_management.create_vendor("   ", "software", "EMP-1")

        assert "error" in result

    def test_strips_surrounding_whitespace_from_a_valid_name(self):
        result = vendor_management.create_vendor("  Acme Parts  ", "software", "EMP-1")

        assert result["name"] == "Acme Parts"

    def test_captures_every_optional_field_when_given(self):
        result = vendor_management.create_vendor(
            "Acme Parts", "software", "EMP-1",
            contact_name="Jane Doe",
            contact_email="jane@acme.com",
            contact_phone="555-1234",
            monthly_cost=499.99,
            contract_start_date="2026-01-01",
            contract_end_date="2027-01-01",
            auto_renew=True,
            notes="Preferred vendor",
        )

        assert result["contact_name"] == "Jane Doe"
        assert result["contact_email"] == "jane@acme.com"
        assert result["contact_phone"] == "555-1234"
        assert result["monthly_cost"] == 499.99
        assert result["contract_start_date"] == "2026-01-01"
        assert result["contract_end_date"] == "2027-01-01"
        assert result["auto_renew"] is True
        assert result["notes"] == "Preferred vendor"

    def test_generates_a_real_unique_id_per_call(self):
        first = vendor_management.create_vendor("Vendor A", "software", "EMP-1")
        second = vendor_management.create_vendor("Vendor B", "software", "EMP-1")

        assert first["id"] != second["id"]


class TestSerializeDaysToRenewal:

    def test_computes_a_real_positive_days_to_renewal_for_a_future_date(self):
        future = (date.today() + timedelta(days=30)).isoformat()
        result = vendor_management.create_vendor(
            "Acme Parts", "software", "EMP-1", contract_end_date=future
        )

        assert result["days_to_renewal"] == 30

    def test_computes_a_real_negative_days_to_renewal_for_a_past_date(self):
        past = (date.today() - timedelta(days=10)).isoformat()
        result = vendor_management.create_vendor(
            "Acme Parts", "software", "EMP-1", contract_end_date=past
        )

        assert result["days_to_renewal"] == -10

    def test_is_none_when_no_contract_end_date_is_set(self):
        result = vendor_management.create_vendor("Acme Parts", "software", "EMP-1")

        assert result["days_to_renewal"] is None

    def test_is_none_when_the_stored_date_string_is_malformed(self):
        result = vendor_management.create_vendor(
            "Acme Parts", "software", "EMP-1", contract_end_date="not-a-real-date"
        )

        assert result["days_to_renewal"] is None


class TestUpdateVendor:

    def test_returns_an_error_for_an_unknown_vendor(self):
        result = vendor_management.update_vendor("VNDR-99999", "EMP-1", name="New Name")

        assert "error" in result

    def test_updates_only_the_real_editable_fields_given(self):
        created = vendor_management.create_vendor("Acme Parts", "software", "EMP-1")

        result = vendor_management.update_vendor(
            created["id"], "EMP-2", name="Acme Parts Inc.", monthly_cost=199.0
        )

        assert result["name"] == "Acme Parts Inc."
        assert result["monthly_cost"] == 199.0
        assert result["updated_by"] == "EMP-2"

    def test_ignores_a_none_value_for_an_editable_field(self):
        created = vendor_management.create_vendor(
            "Acme Parts", "software", "EMP-1", monthly_cost=199.0
        )

        result = vendor_management.update_vendor(
            created["id"], "EMP-2", monthly_cost=None
        )

        assert result["monthly_cost"] == 199.0

    def test_rejects_an_invalid_category_on_update(self):
        created = vendor_management.create_vendor("Acme Parts", "software", "EMP-1")

        result = vendor_management.update_vendor(
            created["id"], "EMP-2", category="not_a_real_category"
        )

        assert "error" in result
        # The real entity's category is left untouched by a rejected update.
        assert ledger.get_entity(created["id"]).attributes["category"] == "software"

    def test_a_field_outside_the_editable_allowlist_is_silently_ignored(self):
        created = vendor_management.create_vendor("Acme Parts", "software", "EMP-1")

        result = vendor_management.update_vendor(
            created["id"], "EMP-2", status="inactive"
        )

        # status isn't in the editable allowlist for update_vendor -- only
        # set_vendor_status can change it -- so it stays "active".
        assert result["status"] == "active"


class TestSetVendorStatus:

    def test_returns_an_error_for_an_unknown_vendor(self):
        result = vendor_management.set_vendor_status("VNDR-99999", "inactive", "EMP-1")

        assert "error" in result

    def test_rejects_an_invalid_status(self):
        created = vendor_management.create_vendor("Acme Parts", "software", "EMP-1")

        result = vendor_management.set_vendor_status(created["id"], "bogus", "EMP-1")

        assert "error" in result

    def test_sets_a_real_valid_status(self):
        created = vendor_management.create_vendor("Acme Parts", "software", "EMP-1")

        result = vendor_management.set_vendor_status(created["id"], "under_review", "EMP-2")

        assert result["status"] == "under_review"
        assert result["updated_by"] == "EMP-2"


class TestGetVendor:

    def test_returns_an_error_for_an_unknown_vendor(self):
        assert "error" in vendor_management.get_vendor("VNDR-99999")

    def test_returns_the_real_serialized_vendor(self):
        created = vendor_management.create_vendor("Acme Parts", "software", "EMP-1")

        result = vendor_management.get_vendor(created["id"])

        assert result["id"] == created["id"]
        assert result["name"] == "Acme Parts"


class TestListVendors:

    def test_an_empty_ledger_returns_an_empty_list(self):
        assert vendor_management.list_vendors() == []

    def test_returns_every_vendor_sorted_by_name(self):
        vendor_management.create_vendor("Zeta Corp", "software", "EMP-1")
        vendor_management.create_vendor("Acme Parts", "parts_supplier", "EMP-1")

        result = vendor_management.list_vendors()

        assert [v["name"] for v in result] == ["Acme Parts", "Zeta Corp"]

    def test_filters_by_category(self):
        vendor_management.create_vendor("Acme Parts", "parts_supplier", "EMP-1")
        vendor_management.create_vendor("Marketing Co", "marketing", "EMP-1")

        result = vendor_management.list_vendors(category="marketing")

        assert len(result) == 1
        assert result[0]["name"] == "Marketing Co"

    def test_filters_by_status(self):
        created = vendor_management.create_vendor("Acme Parts", "software", "EMP-1")
        vendor_management.create_vendor("Zeta Corp", "software", "EMP-1")
        vendor_management.set_vendor_status(created["id"], "inactive", "EMP-2")

        result = vendor_management.list_vendors(status="inactive")

        assert len(result) == 1
        assert result[0]["id"] == created["id"]


class TestGetVendorDashboard:

    def test_an_empty_ledger_returns_real_zeroed_aggregates(self):
        result = vendor_management.get_vendor_dashboard()

        assert result["total_vendors"] == 0
        assert result["active_vendors"] == 0
        assert result["total_monthly_cost"] == 0
        assert result["upcoming_renewals"] == []
        assert result["by_category"] == {}
        assert "usage_analysis" in result["not_yet_tracked"]

    def test_total_monthly_cost_only_counts_active_vendors(self):
        active = vendor_management.create_vendor(
            "Active Co", "software", "EMP-1", monthly_cost=100.0
        )
        inactive = vendor_management.create_vendor(
            "Inactive Co", "software", "EMP-1", monthly_cost=500.0
        )
        vendor_management.set_vendor_status(inactive["id"], "inactive", "EMP-2")

        result = vendor_management.get_vendor_dashboard()

        assert result["total_monthly_cost"] == 100.0
        assert result["active_vendors"] == 1
        assert result["total_vendors"] == 2

    def test_upcoming_renewals_only_includes_the_real_0_to_60_day_window(self):
        soon = (date.today() + timedelta(days=30)).isoformat()
        far = (date.today() + timedelta(days=90)).isoformat()
        already_past = (date.today() - timedelta(days=5)).isoformat()

        renewing_soon = vendor_management.create_vendor(
            "Soon Co", "software", "EMP-1", contract_end_date=soon
        )
        vendor_management.create_vendor(
            "Far Co", "software", "EMP-1", contract_end_date=far
        )
        vendor_management.create_vendor(
            "Past Co", "software", "EMP-1", contract_end_date=already_past
        )

        result = vendor_management.get_vendor_dashboard()

        renewal_ids = [v["id"] for v in result["upcoming_renewals"]]
        assert renewal_ids == [renewing_soon["id"]]

    def test_upcoming_renewals_are_sorted_soonest_first(self):
        later = (date.today() + timedelta(days=45)).isoformat()
        sooner = (date.today() + timedelta(days=5)).isoformat()

        vendor_management.create_vendor(
            "Later Co", "software", "EMP-1", contract_end_date=later
        )
        vendor_management.create_vendor(
            "Sooner Co", "software", "EMP-1", contract_end_date=sooner
        )

        result = vendor_management.get_vendor_dashboard()

        names = [v["name"] for v in result["upcoming_renewals"]]
        assert names == ["Sooner Co", "Later Co"]

    def test_by_category_breaks_down_real_counts_and_costs(self):
        vendor_management.create_vendor(
            "Vendor A", "software", "EMP-1", monthly_cost=100.0
        )
        vendor_management.create_vendor(
            "Vendor B", "software", "EMP-1", monthly_cost=50.0
        )
        vendor_management.create_vendor(
            "Vendor C", "marketing", "EMP-1", monthly_cost=200.0
        )

        result = vendor_management.get_vendor_dashboard()

        assert result["by_category"]["software"] == {"count": 2, "monthly_cost": 150.0}
        assert result["by_category"]["marketing"] == {"count": 1, "monthly_cost": 200.0}


class TestVendorManagementApiAcl:

    @pytest.mark.parametrize("role", [SALES, FINANCE, MARKETING])
    def test_every_mutating_and_read_action_rejects_a_non_admin_ops_role(self, role):
        assert vendor_management_api.create_vendor_api(role, "EMP-1", "Acme", "software") == {
            "error": "Admin/Operations role required."
        }
        assert vendor_management_api.update_vendor_api(role, "EMP-1", "VNDR-1", name="x") == {
            "error": "Admin/Operations role required."
        }
        assert vendor_management_api.set_vendor_status_api(role, "EMP-1", "VNDR-1", "inactive") == {
            "error": "Admin/Operations role required."
        }
        assert vendor_management_api.get_vendor_api(role, "VNDR-1") == {
            "error": "Admin/Operations role required."
        }
        assert vendor_management_api.list_vendors_api(role) == {
            "error": "Admin/Operations role required."
        }
        assert vendor_management_api.get_vendor_dashboard_api(role) == {
            "error": "Admin/Operations role required."
        }

    @pytest.mark.parametrize("role", [ADMIN, OPERATIONS])
    def test_create_and_get_round_trip_for_an_allowed_role(self, role):
        created = vendor_management_api.create_vendor_api(role, "EMP-1", "Acme Parts", "software")

        assert "error" not in created
        assert created["name"] == "Acme Parts"

        fetched = vendor_management_api.get_vendor_api(role, created["id"])
        assert fetched["id"] == created["id"]

    def test_update_api_delegates_to_the_real_core_function(self):
        created = vendor_management_api.create_vendor_api(ADMIN, "EMP-1", "Acme Parts", "software")

        result = vendor_management_api.update_vendor_api(
            OPERATIONS, "EMP-2", created["id"], monthly_cost=250.0
        )

        assert result["monthly_cost"] == 250.0
        assert result["updated_by"] == "EMP-2"

    def test_set_status_api_delegates_to_the_real_core_function(self):
        created = vendor_management_api.create_vendor_api(ADMIN, "EMP-1", "Acme Parts", "software")

        result = vendor_management_api.set_vendor_status_api(
            ADMIN, "EMP-2", created["id"], "under_review"
        )

        assert result["status"] == "under_review"

    def test_list_api_wraps_the_real_result_in_a_vendors_key(self):
        vendor_management_api.create_vendor_api(ADMIN, "EMP-1", "Acme Parts", "software")

        result = vendor_management_api.list_vendors_api(OPERATIONS)

        assert "vendors" in result
        assert len(result["vendors"]) == 1

    def test_dashboard_api_returns_the_real_aggregate(self):
        vendor_management_api.create_vendor_api(
            ADMIN, "EMP-1", "Acme Parts", "software", monthly_cost=100.0
        )

        result = vendor_management_api.get_vendor_dashboard_api(OPERATIONS)

        assert result["total_vendors"] == 1
        assert result["total_monthly_cost"] == 100.0
