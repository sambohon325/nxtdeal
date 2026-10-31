"""
Tests for core/employee_value.py / core/employee_value_api.py -- per-employee $ value/
effectiveness scoring (session 37). Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

from datetime import date, timedelta

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import EMPLOYEE, DEAL, VEHICLE, SERVICE_RECORD, BOT_TASK_EVENT
from core.permissions import ADMIN, OPERATIONS, SALES

from core import employee_value
from core import employee_value_api


TODAY = date.today()


@pytest.fixture(autouse=True)
def fresh_ledger():

    ledger.reset()

    yield

    ledger.reset()


def _add_employee(employee_id, department, title):

    ledger.add_entity(Entity(
        id=employee_id,
        entity_type=EMPLOYEE,
        attributes={"Department": department, "Title": title, "FirstName": "Test", "LastName": employee_id}
    ))


def _add_vehicle(vehicle_id, price, cost):

    ledger.add_entity(Entity(
        id=vehicle_id,
        entity_type=VEHICLE,
        attributes={"Price": str(price), "Cost": str(cost)}
    ))


def _add_funded_deal(deal_id, employee_id, vehicle_id, days_ago=0):

    ledger.add_entity(Entity(
        id=deal_id,
        entity_type=DEAL,
        attributes={
            "created_by": employee_id,
            "vehicle_id": vehicle_id,
            "status": "funded",
            "updated_at": (TODAY - timedelta(days=days_ago)).isoformat(),
        }
    ))


def _add_service_record(record_id, employee_id, cost, parts_cost, days_ago=0):

    ledger.add_entity(Entity(
        id=record_id,
        entity_type=SERVICE_RECORD,
        attributes={
            "Technician": employee_id,
            "Cost": str(cost),
            "PartsCost": str(parts_cost),
            "ServiceDate": (TODAY - timedelta(days=days_ago)).isoformat(),
        }
    ))


def _add_bot_event(employee_id, task_key, event_type):

    ledger.add_entity(Entity(
        id=f"BOTEVT-{employee_id}-{task_key}-{event_type}",
        entity_type=BOT_TASK_EVENT,
        attributes={"employee_id": employee_id, "task_key": task_key, "event_type": event_type}
    ))


def test_compute_value_unknown_employee_returns_none():
    assert employee_value.compute_employee_value("EMP-NOPE") is None


def test_compute_value_no_real_data_is_industry_estimate():

    _add_employee("EMP-00001", "Sales", "Sales Consultant")

    result = employee_value.compute_employee_value("EMP-00001")

    assert result["basis"] == "industry_estimate"
    assert result["sample_size"] == 0
    assert result["monthly_value_estimate"] == employee_value.INDUSTRY_MONTHLY_VALUE[
        ("sales", "staff")
    ]


def test_compute_value_real_sales_data_moves_toward_ledger():

    _add_employee("EMP-00002", "Sales", "Sales Consultant")

    for i in range(10):
        _add_vehicle(f"VEH-{i:05}", price=30000, cost=27000)
        _add_funded_deal(f"DEAL-{i:05}", "EMP-00002", f"VEH-{i:05}", days_ago=i)

    result = employee_value.compute_employee_value("EMP-00002")

    assert result["sample_size"] == 10
    assert result["basis"] == "ledger"
    # 10 deals * (30000-27000) = 30000 real gross this month, volume >= 0.9 -> mostly real
    assert result["monthly_value_estimate"] > 25000


def test_compute_value_ignores_unfunded_deals():

    _add_employee("EMP-00003", "Sales", "Sales Consultant")
    _add_vehicle("VEH-00001", price=30000, cost=27000)

    ledger.add_entity(Entity(
        id="DEAL-00001",
        entity_type=DEAL,
        attributes={
            "created_by": "EMP-00003",
            "vehicle_id": "VEH-00001",
            "status": "financing",
            "updated_at": TODAY.isoformat(),
        }
    ))

    result = employee_value.compute_employee_value("EMP-00003")
    assert result["sample_size"] == 0


def test_compute_value_service_attribution_via_technician_field():

    _add_employee("EMP-00004", "Service", "Service Advisor")

    for i in range(12):
        _add_service_record(f"SRV-{i:05}", "EMP-00004", cost=300, parts_cost=100, days_ago=i)

    result = employee_value.compute_employee_value("EMP-00004")

    assert result["sample_size"] == 12
    assert result["basis"] == "ledger"


def test_compute_value_no_real_attribution_path_for_marketing():

    _add_employee("EMP-00005", "Marketing", "Marketing Coordinator")

    result = employee_value.compute_employee_value("EMP-00005")

    assert result["basis"] == "industry_estimate"
    assert "No direct per-employee" in result["note"]


def test_automation_coverage_none_with_no_history():

    assert employee_value.automation_coverage("EMP-NOHISTORY") is None


def test_automation_coverage_computed_from_real_events():

    _add_bot_event("EMP-00006", "sales_followup_leads", "acted")  # whitelisted
    _add_bot_event("EMP-00006", "sales_check_pipeline", "dismissed")  # not whitelisted

    coverage = employee_value.automation_coverage("EMP-00006")

    assert coverage["distinct_task_types"] == 2
    assert coverage["automatable_task_types"] == 1
    assert coverage["automation_pct"] == 50.0


def test_list_employee_values_sorted_descending():

    _add_employee("EMP-00007", "Sales", "Sales Consultant")
    _add_employee("EMP-00008", "Sales", "General Manager")

    values = employee_value.list_employee_values()

    amounts = [v["monthly_value_estimate"] for v in values]
    assert amounts == sorted(amounts, reverse=True)


def test_list_employee_values_filters_by_department():

    _add_employee("EMP-00009", "Sales", "Sales Consultant")
    _add_employee("EMP-00010", "Service", "Service Advisor")

    sales_only = employee_value.list_employee_values(department="sales")
    assert all(v["department"] == "sales" for v in sales_only)


def test_effectiveness_disclaimer_present_on_every_result():

    _add_employee("EMP-00011", "Sales", "Sales Consultant")

    result = employee_value.compute_employee_value("EMP-00011")
    assert result["disclaimer"] == employee_value.EFFECTIVENESS_DISCLAIMER


# ---------------------------------------------------------------------------
# ACL
# ---------------------------------------------------------------------------

def test_list_employee_values_api_denied_for_sales_role():

    result = employee_value_api.list_employee_values_api(SALES)
    assert "error" in result


def test_list_employee_values_api_allowed_for_admin_and_operations():

    for role in (ADMIN, OPERATIONS):
        result = employee_value_api.list_employee_values_api(role)
        assert "employees" in result


def test_get_employee_value_api_denied_for_sales_role():

    _add_employee("EMP-00012", "Sales", "Sales Consultant")

    result = employee_value_api.get_employee_value_api(SALES, "EMP-00012")
    assert "error" in result


def test_get_employee_value_api_unknown_employee():

    result = employee_value_api.get_employee_value_api(ADMIN, "EMP-NOPE")
    assert "error" in result
