"""
Tests for core/opportunities_api.py -- the thin ACL layer over
core/opportunities_actions.py (already directly tested in
test_opportunities_actions.py). This file exercises only the ACL/validation layer
itself via monkeypatched delegates.

Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.permissions import ADMIN, MARKETING, SALES, SERVICE, FINANCE, OPERATIONS

import core.opportunities_api as opportunities_api
from core.opportunities_api import (
    list_sales_employees_api,
    save_opportunity_pool_as_list_api,
    assign_opportunity_to_sales_api,
)


class TestListSalesEmployeesApi:

    def test_no_role_gate_delegates_directly(self, monkeypatch):
        monkeypatch.setattr(opportunities_api, "list_sales_employees", lambda: [{"id": "EMP-1"}])
        result = list_sales_employees_api()
        assert result == [{"id": "EMP-1"}]


class TestSaveOpportunityPoolAsListApi:

    @pytest.mark.parametrize("role", [ADMIN, MARKETING])
    def test_allowed_roles_can_save(self, monkeypatch, role):
        monkeypatch.setattr(
            opportunities_api, "save_opportunity_pool_as_list",
            lambda name, emp, campaign_type_key, params, description: {
                "name": name, "employee_id": emp, "campaign_type_key": campaign_type_key,
                "params": params, "description": description,
            },
        )
        result = save_opportunity_pool_as_list_api(role, "EMP-1", "My List", "retention", {"a": 1}, "desc")
        assert result["name"] == "My List"
        assert result["campaign_type_key"] == "retention"

    @pytest.mark.parametrize("role", [SALES, SERVICE, FINANCE, OPERATIONS])
    def test_disallowed_roles_denied(self, role):
        result = save_opportunity_pool_as_list_api(role, "EMP-1", "My List", "retention", {})
        assert "error" in result
        assert "Only marketing/admin" in result["error"]

    def test_empty_name_rejected(self):
        result = save_opportunity_pool_as_list_api(ADMIN, "EMP-1", "", "retention", {})
        assert "error" in result
        assert "needs a name" in result["error"]

    def test_whitespace_only_name_rejected(self):
        result = save_opportunity_pool_as_list_api(ADMIN, "EMP-1", "   ", "retention", {})
        assert "error" in result

    def test_none_name_rejected(self):
        result = save_opportunity_pool_as_list_api(ADMIN, "EMP-1", None, "retention", {})
        assert "error" in result

    def test_name_is_stripped_before_delegating(self, monkeypatch):
        captured = {}

        def fake_save(name, emp, campaign_type_key, params, description):
            captured["name"] = name
            return {"ok": True}

        monkeypatch.setattr(opportunities_api, "save_opportunity_pool_as_list", fake_save)
        save_opportunity_pool_as_list_api(ADMIN, "EMP-1", "  Padded Name  ", "retention", {})
        assert captured["name"] == "Padded Name"

    def test_none_params_defaults_to_empty_dict(self, monkeypatch):
        captured = {}

        def fake_save(name, emp, campaign_type_key, params, description):
            captured["params"] = params
            return {"ok": True}

        monkeypatch.setattr(opportunities_api, "save_opportunity_pool_as_list", fake_save)
        save_opportunity_pool_as_list_api(ADMIN, "EMP-1", "Name", "retention", None)
        assert captured["params"] == {}

    def test_none_description_defaults_to_empty_string(self, monkeypatch):
        captured = {}

        def fake_save(name, emp, campaign_type_key, params, description):
            captured["description"] = description
            return {"ok": True}

        monkeypatch.setattr(opportunities_api, "save_opportunity_pool_as_list", fake_save)
        save_opportunity_pool_as_list_api(ADMIN, "EMP-1", "Name", "retention", {}, description=None)
        assert captured["description"] == ""

    def test_role_check_happens_before_name_validation(self):
        # a disallowed role with an also-invalid (empty) name should still surface the
        # role-denial message, not the name-validation one -- confirms gate ordering.
        result = save_opportunity_pool_as_list_api(SALES, "EMP-1", "", "retention", {})
        assert "Only marketing/admin" in result["error"]


class TestAssignOpportunityToSalesApi:

    @pytest.mark.parametrize("role", [ADMIN, MARKETING])
    def test_allowed_roles_can_assign(self, monkeypatch, role):
        monkeypatch.setattr(
            opportunities_api, "assign_opportunity_to_sales",
            lambda lead_id, assign_to: {"lead_id": lead_id, "assigned_to": assign_to},
        )
        result = assign_opportunity_to_sales_api(role, "LEAD-1", "EMP-2")
        assert result == {"lead_id": "LEAD-1", "assigned_to": "EMP-2"}

    @pytest.mark.parametrize("role", [SALES, SERVICE, FINANCE, OPERATIONS])
    def test_disallowed_roles_denied(self, role):
        result = assign_opportunity_to_sales_api(role, "LEAD-1", "EMP-2")
        assert "error" in result
        assert "Only marketing/admin" in result["error"]
