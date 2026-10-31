"""
Tests for the Department Intelligence reporting layer (core/department_intelligence.py,
core/kpi_snapshots.py, core/department_intelligence_api.py) -- session 35, renamed from
tests/test_bumper_bi.py session 68 as part of dropping the "Bumper BI" branding. Run
from backend/ with `pytest`.
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
from core.entity_types import (
    VEHICLE,
    SERVICE_RECORD,
    FINANCE_CONTRACT,
    PART,
    PART_SALE,
    DEPARTMENT_SNAPSHOT
)
from core import department_intelligence
from core import kpi_snapshots
from core import department_intelligence_api
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE


TODAY = date.today()


@pytest.fixture(autouse=True)
def fresh_ledger():

    ledger.reset()

    yield

    ledger.reset()


def _add_vehicle(vehicle_id, price, cost, date_sold):

    ledger.add_entity(Entity(
        id=vehicle_id,
        entity_type=VEHICLE,
        attributes={
            "Price": str(price),
            "Cost": str(cost),
            "DateSold": date_sold.isoformat() if date_sold else ""
        }
    ))


def _add_service_record(record_id, cost, parts_cost, labor_hours, pay_type):

    ledger.add_entity(Entity(
        id=record_id,
        entity_type=SERVICE_RECORD,
        attributes={
            "Cost": str(cost),
            "PartsCost": str(parts_cost),
            "LaborHours": str(labor_hours),
            "PayType": pay_type
        }
    ))


def _add_part(part_id, part_number, quantity_on_hand, unit_cost, received_date):

    ledger.add_entity(Entity(
        id=part_id,
        entity_type=PART,
        attributes={
            "PartNumber": part_number,
            "QuantityOnHand": str(quantity_on_hand),
            "UnitCost": str(unit_cost),
            "ReceivedDate": received_date.isoformat()
        }
    ))


def _add_part_sale(sale_id, part_number, sale_date, quantity_sold, sale_price, cost, gross_profit):

    ledger.add_entity(Entity(
        id=sale_id,
        entity_type=PART_SALE,
        attributes={
            "PartNumber": part_number,
            "SaleDate": sale_date.isoformat(),
            "QuantitySold": str(quantity_sold),
            "SalePrice": str(sale_price),
            "Cost": str(cost),
            "GrossProfit": str(gross_profit)
        }
    ))


def _add_finance_contract(contract_id, amount_financed, apr, term_months, funding_status):

    ledger.add_entity(Entity(
        id=contract_id,
        entity_type=FINANCE_CONTRACT,
        attributes={
            "AmountFinanced": str(amount_financed),
            "APR": str(apr),
            "TermMonths": str(term_months),
            "FundingStatus": funding_status
        }
    ))


# --- Sales ---


def test_sales_kpis_only_count_sold_vehicles():

    _add_vehicle("VEH-1", 30000, 25000, TODAY)
    _add_vehicle("VEH-2", 40000, 34000, TODAY)
    _add_vehicle("VEH-3", 50000, 45000, None)

    result = department_intelligence.compute_sales_kpis()
    kpis = result["kpis"]

    assert kpis["units_sold"]["value"] == 2
    assert kpis["total_gross_profit"]["value"] == pytest.approx(11000)
    assert kpis["gross_profit_per_unit"]["value"] == pytest.approx(5500)
    assert kpis["avg_sale_price"]["value"] == pytest.approx(35000)


def test_sales_projected_month_end_units_uses_real_pace():

    _add_vehicle("VEH-1", 30000, 25000, TODAY)
    _add_vehicle("VEH-2", 40000, 34000, TODAY)

    result = department_intelligence.compute_sales_kpis()

    days_elapsed = TODAY.day
    days_in_month = department_intelligence._days_in_month(TODAY)
    expected = round(2 / days_elapsed * days_in_month, 1)

    assert result["kpis"]["projected_month_end_units"]["value"] == pytest.approx(expected)


# --- Service ---


def test_service_kpis_computed_from_real_fields():

    _add_service_record("SRV-1", cost=100, parts_cost=40, labor_hours=1.0, pay_type="Customer Pay")
    _add_service_record("SRV-2", cost=200, parts_cost=50, labor_hours=2.0, pay_type="Warranty")

    result = department_intelligence.compute_service_kpis()
    kpis = result["kpis"]

    assert kpis["ro_count"]["value"] == 2
    assert kpis["total_gross"]["value"] == pytest.approx(210)
    assert kpis["avg_repair_order"]["value"] == pytest.approx(150)
    assert kpis["customer_pay_pct"]["value"] == pytest.approx(50.0)
    assert kpis["effective_labor_rate"]["value"] == pytest.approx(70.0)


def test_service_kpis_handle_zero_records():

    result = department_intelligence.compute_service_kpis()
    kpis = result["kpis"]

    assert kpis["ro_count"]["value"] == 0
    assert kpis["avg_repair_order"]["value"] == 0.0
    assert kpis["customer_pay_pct"]["value"] == 0.0
    assert kpis["effective_labor_rate"]["value"] == 0.0


# --- Parts ---


def test_parts_kpis_obsolescence_and_turns():

    _add_part("PART-1", "PN-1", quantity_on_hand=10, unit_cost=5, received_date=TODAY - timedelta(days=250))
    _add_part("PART-2", "PN-2", quantity_on_hand=5, unit_cost=20, received_date=TODAY - timedelta(days=10))

    # PN-1 has never been sold and was received 250 days ago -> obsolete.
    # PN-2 was sold 5 days ago -> not obsolete regardless of receive date.
    _add_part_sale(
        "PSALE-1", "PN-2", sale_date=TODAY - timedelta(days=5),
        quantity_sold=2, sale_price=100, cost=40, gross_profit=60
    )

    result = department_intelligence.compute_parts_kpis()
    kpis = result["kpis"]

    assert kpis["net_profit"]["value"] == pytest.approx(60)
    assert kpis["gross_profit_per_unit"]["value"] == pytest.approx(30)
    assert kpis["parts_sales"]["value"] == pytest.approx(100)

    # inventory_value = 10*5 + 5*20 = 150; obsolete_value = 10*5 = 50 (PN-1 only)
    assert result["raw"]["obsolete_value"] == pytest.approx(50)
    assert kpis["obsolete_inventory_pct"]["value"] == pytest.approx(33.3, abs=0.1)

    # annualized_cogs = 40 * (365/150) ~= 97.33; turns = 97.33 / 150 ~= 0.65
    assert kpis["inventory_turns"]["value"] == pytest.approx(0.6, abs=0.1)


def test_parts_kpis_handle_zero_inventory():

    result = department_intelligence.compute_parts_kpis()
    kpis = result["kpis"]

    assert kpis["net_profit"]["value"] == 0.0
    assert kpis["obsolete_inventory_pct"]["value"] == 0.0
    assert kpis["inventory_turns"]["value"] == 0.0


# --- F&I ---


def test_fi_kpis_reserve_and_deals_financed():

    _add_finance_contract("FIN-1", amount_financed=20000, apr=5.0, term_months=60, funding_status="Funded")
    _add_finance_contract("FIN-2", amount_financed=10000, apr=7.0, term_months=36, funding_status="Pending")

    _add_vehicle("VEH-1", 30000, 25000, TODAY)
    _add_vehicle("VEH-2", 40000, 34000, TODAY)
    _add_vehicle("VEH-3", 50000, 45000, TODAY)
    _add_vehicle("VEH-4", 45000, 40000, TODAY)

    result = department_intelligence.compute_fi_kpis()
    kpis = result["kpis"]

    # reserve1 = 20000 * 0.02 * (60/24) = 1000; reserve2 = 10000 * 0.02 * (36/24) = 300
    assert kpis["reserve_income"]["value"] == pytest.approx(1300)
    assert kpis["income_per_contract"]["value"] == pytest.approx(650)
    assert kpis["reserve_per_vehicle"]["value"] == pytest.approx(325)
    assert kpis["deals_financed"]["value"] == 1
    assert kpis["avg_apr"]["value"] == pytest.approx(6.0)


def test_fi_kpis_handle_zero_contracts():

    result = department_intelligence.compute_fi_kpis()
    kpis = result["kpis"]

    assert kpis["reserve_income"]["value"] == 0.0
    assert kpis["deals_financed"]["value"] == 0
    assert kpis["avg_apr"]["value"] == 0.0


# --- Executive rollup ---


def test_executive_kpis_roll_up_all_departments():

    _add_vehicle("VEH-1", 30000, 25000, TODAY)
    _add_service_record("SRV-1", cost=100, parts_cost=40, labor_hours=1.0, pay_type="Customer Pay")
    _add_part("PART-1", "PN-1", quantity_on_hand=10, unit_cost=5, received_date=TODAY - timedelta(days=250))
    _add_finance_contract("FIN-1", amount_financed=20000, apr=5.0, term_months=60, funding_status="Funded")

    result = department_intelligence.compute_executive_kpis()
    kpis = result["kpis"]

    sales_gross = 30000 - 25000
    service_gross = 100 - 40
    parts_gross = 0.0  # no part sales in this test
    fi_income = 20000 * 0.02 * (60 / 24)

    expected_total = sales_gross + service_gross + parts_gross + fi_income

    assert kpis["total_gross_profit"]["value"] == pytest.approx(expected_total)

    contribution_sum = (
        kpis["sales_contribution_pct"]["value"]
        + kpis["service_contribution_pct"]["value"]
        + kpis["parts_contribution_pct"]["value"]
        + kpis["fi_contribution_pct"]["value"]
    )

    assert contribution_sum == pytest.approx(100, abs=0.5)

    # PN-1 has no sales and was received 250 days ago -> counts as obsolete/recoverable.
    assert result["raw"]["recoverable_profit"] == pytest.approx(50)
    assert result["alert"]["value"] == pytest.approx(50)


def test_compute_department_unknown_key_returns_none():

    assert department_intelligence.compute_department("not-a-real-department") is None


def test_compute_department_includes_capabilities_and_title():

    payload = department_intelligence.compute_department("sales")

    assert payload["department"] == "sales"
    assert payload["title"] == "Sales Intelligence"
    assert len(payload["capabilities"]) == 4
    assert "kpis" in payload


# --- Snapshots / trend deltas ---


def test_record_snapshot_idempotent_same_day():

    kpis = {"total_gross_profit": {"key": "total_gross_profit", "value": 100.0}}

    first = kpi_snapshots.record_snapshot("sales", kpis)
    second = kpi_snapshots.record_snapshot("sales", kpis)

    assert first.id == second.id

    snapshot_count = sum(
        1 for e in ledger.get_all().values()
        if e.entity_type == DEPARTMENT_SNAPSHOT and e.attributes.get("department") == "sales"
    )

    assert snapshot_count == 1


def test_most_recent_prior_snapshot_none_when_no_history():

    assert kpi_snapshots.most_recent_prior_snapshot("sales") is None


def test_with_trend_no_history_yet():

    kpis = {"total_gross_profit": {"key": "total_gross_profit", "value": 100.0}}

    enriched = kpi_snapshots.with_trend("sales", kpis)

    assert enriched["total_gross_profit"]["has_history"] is False
    assert enriched["total_gross_profit"]["delta_pct"] is None

    # A snapshot should now exist for today.
    assert kpi_snapshots.find_snapshot("sales") is not None


def test_with_trend_computes_real_delta_against_prior_day():

    yesterday = (TODAY - timedelta(days=1)).isoformat()

    ledger.add_entity(Entity(
        id="SNAP-YESTERDAY",
        entity_type=DEPARTMENT_SNAPSHOT,
        attributes={
            "department": "sales",
            "snapshot_date": yesterday,
            "kpis": {"total_gross_profit": 80.0},
            "recorded_at": "2026-01-01T00:00:00+00:00"
        }
    ))

    kpis = {"total_gross_profit": {"key": "total_gross_profit", "value": 100.0}}

    enriched = kpi_snapshots.with_trend("sales", kpis)

    assert enriched["total_gross_profit"]["has_history"] is True
    assert enriched["total_gross_profit"]["delta_pct"] == pytest.approx(25.0)
    assert enriched["total_gross_profit"]["compared_to"] == yesterday


def test_with_trend_handles_zero_prior_value():

    yesterday = (TODAY - timedelta(days=1)).isoformat()

    ledger.add_entity(Entity(
        id="SNAP-YESTERDAY",
        entity_type=DEPARTMENT_SNAPSHOT,
        attributes={
            "department": "sales",
            "snapshot_date": yesterday,
            "kpis": {"total_gross_profit": 0.0},
            "recorded_at": "2026-01-01T00:00:00+00:00"
        }
    ))

    kpis = {"total_gross_profit": {"key": "total_gross_profit", "value": 50.0}}

    enriched = kpi_snapshots.with_trend("sales", kpis)

    # Zero -> something is an undefined percent change, not a real number.
    assert enriched["total_gross_profit"]["delta_pct"] is None
    assert enriched["total_gross_profit"]["has_history"] is True


# --- ACL (core/department_intelligence_api.py) ---


def test_get_department_denied_for_sales_role():

    result = department_intelligence_api.get_department_api(SALES, "sales")

    assert "error" in result


def test_get_department_denied_for_marketing_and_service():

    assert "error" in department_intelligence_api.get_department_api(MARKETING, "sales")
    assert "error" in department_intelligence_api.get_department_api(SERVICE, "sales")


def test_get_department_allowed_for_admin_operations_finance():

    for role in (ADMIN, OPERATIONS, FINANCE):

        result = department_intelligence_api.get_department_api(role, "sales")

        assert "error" not in result
        assert result["department"] == "sales"
        assert isinstance(result["kpis"], list)


def test_get_department_unknown_key():

    result = department_intelligence_api.get_department_api(ADMIN, "not-a-department")

    assert "error" in result


def test_list_departments_denied_for_sales():

    assert "error" in department_intelligence_api.list_departments_api(SALES)


def test_list_departments_allowed_for_finance():

    result = department_intelligence_api.list_departments_api(FINANCE)

    assert "error" not in result
    assert len(result) == 5
