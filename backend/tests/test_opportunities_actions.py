"""
Tests for core/opportunities_actions.py -- the real Marketing -> Sales handoff for
CRM Opportunities (session 82): list_sales_employees() (the "Assign to Sales"
picker), save_opportunity_pool_as_list() (a real MarketingList seeded from
core/campaigns.py's build_audience()), and assign_opportunity_to_sales() (a real
core/lead_assignment.py ASSIGNED_TO handoff, restricted to Lead-typed opportunities
only).

"general" is used as the campaign_type_key throughout for save_opportunity_pool_as_list
tests -- its real audience builder (_build_general_audience) is simply "every real
Customer entity," the least fixture-heavy real pool to exercise build_audience()
against end to end without needing to fabricate service/finance/vehicle history.

Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import EMPLOYEE, LEAD, CUSTOMER
from core import opportunities_actions
from core import marketing_lists
from core import lead_assignment


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    monkeypatch.setattr(marketing_lists, "save_graph", lambda filepath: None)
    monkeypatch.setattr(lead_assignment, "save_graph", lambda filepath: None)


def _make_employee(employee_id, department="Sales", first="Jane", last="Doe", title=None):
    entity = Entity(
        id=employee_id,
        entity_type=EMPLOYEE,
        attributes={
            "Department": department,
            "FirstName": first,
            "LastName": last,
            "Title": title,
        },
    )
    ledger.add_entity(entity)
    return entity


def _make_lead(lead_id, **attrs):
    entity = Entity(id=lead_id, entity_type=LEAD, attributes=attrs)
    ledger.add_entity(entity)
    return entity


def _make_customer(customer_id, **attrs):
    entity = Entity(id=customer_id, entity_type=CUSTOMER, attributes=attrs)
    ledger.add_entity(entity)
    return entity


class TestListSalesEmployees:

    def test_returns_employees_in_the_sales_department(self):
        _make_employee("EMP-1", department="Sales", first="Ann", last="Zed")

        result = opportunities_actions.list_sales_employees()

        assert len(result) == 1
        assert result[0]["id"] == "EMP-1"
        assert result[0]["name"] == "Ann Zed"

    def test_department_match_is_case_insensitive(self):
        _make_employee("EMP-1", department="SALES")
        _make_employee("EMP-2", department="sales")

        result = opportunities_actions.list_sales_employees()

        ids = {e["id"] for e in result}
        assert ids == {"EMP-1", "EMP-2"}

    def test_non_sales_employees_are_excluded(self):
        _make_employee("EMP-1", department="Sales")
        _make_employee("EMP-2", department="Service")
        _make_employee("EMP-3", department="Finance")

        result = opportunities_actions.list_sales_employees()

        assert [e["id"] for e in result] == ["EMP-1"]

    def test_employee_with_no_department_is_excluded(self):
        _make_employee("EMP-1", department=None)

        result = opportunities_actions.list_sales_employees()

        assert result == []

    def test_result_is_sorted_by_name(self):
        _make_employee("EMP-1", department="Sales", first="Zed", last="Zephyr")
        _make_employee("EMP-2", department="Sales", first="Ann", last="Adams")

        result = opportunities_actions.list_sales_employees()

        assert [e["id"] for e in result] == ["EMP-2", "EMP-1"]

    def test_name_falls_back_to_the_id_when_no_first_or_last_name_is_set(self):
        _make_employee("EMP-1", department="Sales", first="", last="")

        result = opportunities_actions.list_sales_employees()

        assert result[0]["name"] == "EMP-1"

    def test_title_is_included_when_present(self):
        _make_employee("EMP-1", department="Sales", title="Sales Manager")

        result = opportunities_actions.list_sales_employees()

        assert result[0]["title"] == "Sales Manager"


class TestSaveOpportunityPoolAsList:

    def test_unknown_campaign_type_returns_an_error(self):
        result = opportunities_actions.save_opportunity_pool_as_list(
            "My List", "EMP-1", "not_a_real_type", {}
        )
        assert "error" in result
        assert "not_a_real_type" in result["error"]

    def test_builds_a_real_marketing_list_from_the_real_audience_pool(self):
        _make_customer("CUST-1")
        _make_customer("CUST-2")

        result = opportunities_actions.save_opportunity_pool_as_list(
            "General Broadcast Pool", "EMP-MKT", "general", {}
        )

        assert "error" not in result
        assert set(result["member_ids"]) == {"CUST-1", "CUST-2"}
        assert result["name"] == "General Broadcast Pool"
        assert result["source"] == "pool:general"
        assert result["created_by"] == "EMP-MKT"

    def test_the_saved_list_is_a_real_persisted_entity_readable_afterward(self):
        _make_customer("CUST-1")

        result = opportunities_actions.save_opportunity_pool_as_list(
            "Real Pool", "EMP-MKT", "general", {}
        )

        stored = ledger.get_entity(result["id"])
        assert stored is not None
        assert stored.attributes["member_ids"] == ["CUST-1"]

    def test_none_params_does_not_raise(self):
        result = opportunities_actions.save_opportunity_pool_as_list(
            "Empty Params Pool", "EMP-MKT", "general", None
        )
        assert "error" not in result

    def test_description_is_passed_through(self):
        result = opportunities_actions.save_opportunity_pool_as_list(
            "Described Pool", "EMP-MKT", "general", {}, description="a real description"
        )
        assert result["description"] == "a real description"


class TestAssignOpportunityToSales:

    def test_assigning_a_lead_to_a_sales_employee_succeeds(self):
        _make_lead("LEAD-1")
        _make_employee("EMP-1", department="Sales")

        result = opportunities_actions.assign_opportunity_to_sales("LEAD-1", "EMP-1")

        assert result == {"lead_id": "LEAD-1", "assigned_to": "EMP-1"}
        assert lead_assignment.get_assigned_employee("LEAD-1") == "EMP-1"

    def test_a_non_lead_entity_id_is_rejected(self):
        _make_customer("CUST-1")
        _make_employee("EMP-1", department="Sales")

        result = opportunities_actions.assign_opportunity_to_sales("CUST-1", "EMP-1")

        assert "error" in result
        assert "not a Lead" in result["error"]

    def test_a_nonexistent_lead_id_is_rejected(self):
        _make_employee("EMP-1", department="Sales")

        result = opportunities_actions.assign_opportunity_to_sales("LEAD-BOGUS", "EMP-1")

        assert "error" in result
        assert "not a Lead" in result["error"]

    def test_a_nonexistent_employee_id_is_rejected(self):
        _make_lead("LEAD-1")

        result = opportunities_actions.assign_opportunity_to_sales("LEAD-1", "EMP-BOGUS")

        assert "error" in result
        assert "not a Sales-department employee" in result["error"]

    def test_a_non_sales_department_employee_is_rejected(self):
        _make_lead("LEAD-1")
        _make_employee("EMP-1", department="Service")

        result = opportunities_actions.assign_opportunity_to_sales("LEAD-1", "EMP-1")

        assert "error" in result
        assert "not a Sales-department employee" in result["error"]

    def test_a_customer_id_passed_as_the_employee_id_is_rejected(self):
        _make_lead("LEAD-1")
        _make_customer("CUST-1")

        result = opportunities_actions.assign_opportunity_to_sales("LEAD-1", "CUST-1")

        assert "error" in result
        assert "not a Sales-department employee" in result["error"]

    def test_reassigning_the_same_lead_updates_who_it_currently_resolves_to(self):
        _make_lead("LEAD-1")
        _make_employee("EMP-1", department="Sales")
        _make_employee("EMP-2", department="Sales")

        opportunities_actions.assign_opportunity_to_sales("LEAD-1", "EMP-1")
        opportunities_actions.assign_opportunity_to_sales("LEAD-1", "EMP-2")

        assert lead_assignment.get_assigned_employee("LEAD-1") == "EMP-2"
