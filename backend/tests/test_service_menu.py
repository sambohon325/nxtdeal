"""
Test coverage for core/service_menu.py -- Service & Parts' 8-item Top Menu real-data
functions.

Same composition-layer discipline as test_operations_menu.py: this module reuses many
already-independently-tested modules (core/workflow_tab_data.py, core/compliance_api.py,
core/data_connections_api.py, core/employee_value_api.py, core/ai_tools.py,
core/appointments.py, core/repair_orders_api.py, core/shop_control_api.py,
core/service_customers_api.py, core/parts_desk_api.py, core/warranty_desk_api.py,
core/service_reporting.py, core/department_intelligence_api.py) -- these tests focus on
this module's own real aggregation/filtering/grouping logic (repair-order status/pay-type
breakdowns, parts inventory value math, technician productivity ranking, customer
dedup-by-most-recent-visit) rather than re-verifying every dependency's own internals.

Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity

import core.service_menu as service_menu


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield
    ledger.reset()


def _service_record(sid, **attrs):
    ledger.add_entity(Entity(id=sid, entity_type="ServiceRecord", attributes=attrs))


def _part(pid, **attrs):
    ledger.add_entity(Entity(id=pid, entity_type="Part", attributes=attrs))


def _part_sale(sid, **attrs):
    ledger.add_entity(Entity(id=sid, entity_type="PartSale", attributes=attrs))


def _employee(eid, **attrs):
    ledger.add_entity(Entity(id=eid, entity_type="Employee", attributes=attrs))


def _customer(cid, **attrs):
    ledger.add_entity(Entity(id=cid, entity_type="Customer", attributes=attrs))


def _recall(rid, **attrs):
    ledger.add_entity(Entity(id=rid, entity_type="Recall", attributes=attrs))


class TestHelpers:

    def test_entities_filters_by_entity_type(self):
        _service_record("SRV-00001", Status="Completed")
        _part("PART-00001", PartNumber="PN-1")
        assert len(service_menu._entities("ServiceRecord")) == 1

    def test_safe_float_parses_numeric_strings(self):
        assert service_menu._safe_float("250.00") == 250.0

    def test_safe_float_returns_default_on_bad_input(self):
        assert service_menu._safe_float(None) == 0.0
        assert service_menu._safe_float("not-a-number") == 0.0
        assert service_menu._safe_float("bad", default=99.0) == 99.0

    def test_safe_int_parses_numeric_strings_including_float_like(self):
        assert service_menu._safe_int("10") == 10
        assert service_menu._safe_int("10.0") == 10

    def test_safe_int_returns_default_on_bad_input(self):
        assert service_menu._safe_int(None) == 0
        assert service_menu._safe_int("nope", default=5) == 5

    def test_repair_orders_by_status_groups_and_defaults_unknown(self):
        _service_record("SRV-00001", Status="Completed")
        _service_record("SRV-00002", Status="Completed")
        _service_record("SRV-00003")
        records = service_menu._entities("ServiceRecord")
        result = service_menu._repair_orders_by_status(records)
        assert result == {"Completed": 2, "Unknown": 1}

    def test_repair_orders_by_pay_type_groups_and_defaults_unknown(self):
        _service_record("SRV-00001", PayType="Warranty")
        _service_record("SRV-00002")
        records = service_menu._entities("ServiceRecord")
        result = service_menu._repair_orders_by_pay_type(records)
        assert result == {"Warranty": 1, "Unknown": 1}

    def test_open_recalls_filters_by_open_flag(self):
        _recall("RECALL-00001", open=True)
        _recall("RECALL-00002", open=False)
        result = service_menu._open_recalls()
        assert len(result) == 1
        assert result[0].id == "RECALL-00001"

    def test_parts_inventory_value_computes_real_cost_and_retail_totals(self):
        _part("PART-00001", QuantityOnHand="10", UnitCost="5.00", ListPrice="15.00")
        _part("PART-00002", QuantityOnHand="4", UnitCost="20.00", ListPrice="50.00")
        parts = service_menu._entities("Part")
        cost, retail = service_menu._parts_inventory_value(parts)
        assert cost == 130.0  # 10*5 + 4*20
        assert retail == 350.0  # 10*15 + 4*50

    def test_parts_inventory_value_empty_list(self):
        cost, retail = service_menu._parts_inventory_value([])
        assert (cost, retail) == (0.0, 0.0)


class TestOverview:

    def test_overview_returns_expected_top_level_shape(self):
        result = service_menu.overview("ADMIN")
        assert "repair_orders_total" in result
        assert "repair_orders_by_status" in result
        assert "not_yet_tracked" in result

    def test_overview_open_ros_excludes_completed_status(self):
        _service_record("SRV-00001", Status="Completed", Cost="100")
        _service_record("SRV-00002", Status="In Progress", Cost="200")
        _service_record("SRV-00003", Status="Estimate", Cost="50")
        result = service_menu.overview("ADMIN")
        assert result["repair_orders_total"] == 3
        assert result["repair_orders_open"] == 2

    def test_overview_computes_real_service_revenue_and_parts_totals(self):
        _service_record("SRV-00001", Status="Completed", Cost="250.00")
        _service_record("SRV-00002", Status="Completed", Cost="400.00")
        _part("PART-00001", QuantityOnHand="10", UnitCost="5.00", ListPrice="15.00")
        _part_sale("PSALE-00001", GrossProfit="20.00")
        result = service_menu.overview("ADMIN")
        assert result["service_revenue_total"] == 650.0
        assert result["parts_inventory_cost_value"] == 50.0
        assert result["parts_inventory_retail_value"] == 150.0
        assert result["parts_gross_profit_total"] == 20.0

    def test_overview_open_recall_count_only_counts_open_recalls(self):
        _recall("RECALL-00001", open=True)
        _recall("RECALL-00002", open=False)
        result = service_menu.overview("ADMIN")
        assert result["open_recall_count"] == 1

    def test_overview_headcount_only_counts_service_department_employees(self):
        _employee("EMP-00001", Department="Service")
        _employee("EMP-00002", Department="Sales")
        result = service_menu.overview("ADMIN")
        assert result["service_technician_headcount"] == 1

    def test_overview_honest_gaps_stated_plainly(self):
        result = service_menu.overview("ADMIN")
        assert "bay_utilization" in result["not_yet_tracked"]
        assert "csi_score" in result["not_yet_tracked"]


class TestAppointments:

    def test_appointments_returns_expected_shape(self):
        result = service_menu.appointments("ADMIN")
        assert "recent_intake" in result
        assert "todays_appointments" in result
        assert "this_weeks_schedule" in result
        assert "waiter_vs_dropoff" in result
        assert "no_show_tracking" in result
        assert "bay_assignments" in result["not_yet_tracked"]


class TestRepairOrders:

    def test_repair_orders_default_view_returns_expected_shape(self):
        result = service_menu.repair_orders("ADMIN")
        assert "total" in result
        assert "by_status" in result
        assert "by_pay_type" in result
        assert "stage_counts" in result
        assert "recent" in result

    def test_repair_orders_default_view_recent_sorted_most_recent_first(self):
        _service_record("SRV-00001", Status="Completed", ServiceDate="2026-01-05", VIN="V1", PayType="Customer Pay")
        _service_record("SRV-00002", Status="Completed", ServiceDate="2026-02-10", VIN="V2", PayType="Warranty")
        result = service_menu.repair_orders("ADMIN")
        assert result["total"] == 2
        assert result["recent"][0]["id"] == "SRV-00002"
        assert result["recent"][1]["id"] == "SRV-00001"

    def test_repair_orders_default_view_by_status_and_pay_type_computed_correctly(self):
        _service_record("SRV-00001", Status="Completed", PayType="Customer Pay")
        _service_record("SRV-00002", Status="In Progress", PayType="Warranty")
        result = service_menu.repair_orders("ADMIN")
        assert result["by_status"] == {"Completed": 1, "In Progress": 1}
        assert result["by_pay_type"] == {"Customer Pay": 1, "Warranty": 1}

    def test_repair_orders_srv_id_query_returns_ro_workspace(self):
        _service_record("SRV-00001", Status="Completed")
        result = service_menu.repair_orders("ADMIN", "SRV-00001")
        assert "repair_order" in result

    def test_repair_orders_srv_id_query_lowercase_uppercased(self):
        _service_record("SRV-00001", Status="Completed")
        result = service_menu.repair_orders("ADMIN", "srv-00001")
        assert "repair_order" in result

    def test_repair_orders_srv_id_query_not_found_returns_error(self):
        result = service_menu.repair_orders("ADMIN", "SRV-99999")
        assert "error" in result

    def test_repair_orders_free_text_query_only_returns_service_record_type_results(self):
        _service_record("SRV-00001", Status="Completed", Description="Brake job")
        result = service_menu.repair_orders("ADMIN", "Brake")
        assert result["query"] == "Brake"
        assert "count" in result
        assert "results" in result

    def test_repair_orders_query_whitespace_only_falls_through_to_default_view(self):
        _service_record("SRV-00001", Status="Completed")
        result = service_menu.repair_orders("ADMIN", "   ")
        assert "total" in result


class TestCustomers:

    def test_customers_default_view_empty_ledger(self):
        result = service_menu.customers("ADMIN")
        assert result["default_view"] == "recent_service_customers"
        assert result["customers"] == []
        assert "lost_customer_recovery" in result
        assert "declined_services" in result

    def test_customers_default_view_deduped_by_customer_id_most_recent_first(self):
        _customer("CUST-00001", CustomerID="C1001", FirstName="Joe", LastName="King", Email="joe@x.com", Phone="555")
        _service_record("SRV-00001", CustomerID="C1001", ServiceDate="2026-01-05")
        _service_record("SRV-00002", CustomerID="C1001", ServiceDate="2026-03-01")
        result = service_menu.customers("ADMIN")
        assert len(result["customers"]) == 1
        assert result["customers"][0]["id"] == "CUST-00001"
        assert result["customers"][0]["name"] == "Joe King"
        assert result["customers"][0]["last_service_date"] == "2026-03-01"

    def test_customers_cust_id_query_returns_customer_360(self):
        _customer("CUST-00001", CustomerID="C1001", FirstName="Joe", LastName="King")
        result = service_menu.customers("ADMIN", "CUST-00001")
        assert "customer" in result
        assert "vehicles_owned" in result
        assert "service_history" in result

    def test_customers_free_text_query_only_returns_customer_type_results(self):
        _customer("CUST-00001", CustomerID="C1001", FirstName="Joe", LastName="King")
        result = service_menu.customers("ADMIN", "Joe")
        assert result["query"] == "Joe"
        assert "results" in result


class TestShopControl:

    def test_shop_control_returns_expected_shape(self):
        result = service_menu.shop_control("ADMIN")
        assert "active_technicians" in result
        assert "technician_productivity" in result
        assert "dispatch_board" in result
        assert "technician_utilization" in result
        assert "stalled_ros" in result
        assert "bottlenecks" in result

    def test_shop_control_aggregates_real_per_technician_stats(self):
        _employee("EMP-00001", FirstName="Nate", LastName="Higgins")
        _service_record("SRV-00001", Technician="EMP-00001", LaborHours="1.5", Cost="250.00", PayType="Customer Pay")
        _service_record("SRV-00002", Technician="EMP-00001", LaborHours="2.0", Cost="400.00", PayType="Warranty")
        result = service_menu.shop_control("ADMIN")
        assert result["active_technicians"] == 1
        tech = result["technician_productivity"][0]
        assert tech["technician_id"] == "EMP-00001"
        assert tech["name"] == "Nate Higgins"
        assert tech["ro_count"] == 2
        assert tech["labor_hours"] == 3.5
        assert tech["revenue"] == 650.0
        assert result["total_labor_hours"] == 3.5

    def test_shop_control_falls_back_to_technician_id_when_employee_not_found(self):
        _service_record("SRV-00001", Technician="EMP-UNKNOWN", LaborHours="1.0", Cost="100.00")
        result = service_menu.shop_control("ADMIN")
        assert result["technician_productivity"][0]["name"] == "EMP-UNKNOWN"

    def test_shop_control_skips_records_with_no_assigned_technician(self):
        _service_record("SRV-00001", LaborHours="1.0", Cost="100.00")
        result = service_menu.shop_control("ADMIN")
        assert result["active_technicians"] == 0

    def test_shop_control_technician_productivity_sorted_by_labor_hours_descending(self):
        _service_record("SRV-00001", Technician="EMP-A", LaborHours="1.0", Cost="100")
        _service_record("SRV-00002", Technician="EMP-B", LaborHours="5.0", Cost="200")
        result = service_menu.shop_control("ADMIN")
        ids = [t["technician_id"] for t in result["technician_productivity"]]
        assert ids == ["EMP-B", "EMP-A"]

    def test_shop_control_pay_type_revenue_mix(self):
        _service_record("SRV-00001", PayType="Customer Pay", Cost="100.00")
        _service_record("SRV-00002", PayType="Customer Pay", Cost="50.00")
        _service_record("SRV-00003", PayType="Warranty", Cost="200.00")
        result = service_menu.shop_control("ADMIN")
        assert result["pay_type_revenue_mix"] == {"Customer Pay": 150.0, "Warranty": 200.0}

    def test_shop_control_honest_gaps_stated_plainly(self):
        result = service_menu.shop_control("ADMIN")
        assert "bay_scheduling" in result["not_yet_tracked"]
        assert "technician_clock" in result["not_yet_tracked"]


class TestParts:

    def test_parts_default_view_returns_expected_shape(self):
        result = service_menu.parts("ADMIN")
        assert "sku_count" in result
        assert "by_category" in result
        assert "out_of_stock" in result
        assert "part_sales" in result
        assert "parts_request_queue" in result

    def test_parts_by_category_groups_sku_count_and_units_on_hand(self):
        _part("PART-00001", Category="Filters", QuantityOnHand="10")
        _part("PART-00002", Category="Filters", QuantityOnHand="5")
        _part("PART-00003", Category="Brakes", QuantityOnHand="0")
        result = service_menu.parts("ADMIN")
        assert result["by_category"]["Filters"] == {"sku_count": 2, "units_on_hand": 15}
        assert result["by_category"]["Brakes"] == {"sku_count": 1, "units_on_hand": 0}

    def test_parts_defaults_uncategorized_when_category_missing(self):
        _part("PART-00001", QuantityOnHand="1")
        result = service_menu.parts("ADMIN")
        assert "Uncategorized" in result["by_category"]

    def test_parts_out_of_stock_flags_zero_quantity_only(self):
        _part("PART-00001", PartNumber="PN-1", QuantityOnHand="0")
        _part("PART-00002", PartNumber="PN-2", QuantityOnHand="5")
        result = service_menu.parts("ADMIN")
        assert result["out_of_stock"]["count"] == 1
        assert result["out_of_stock"]["parts"][0]["part_number"] == "PN-1"

    def test_parts_sales_revenue_and_gross_computed_correctly(self):
        _part_sale("PSALE-00001", SalePrice="15.00", QuantitySold="2", GrossProfit="20.00", CustomerType="Retail")
        _part_sale("PSALE-00002", SalePrice="10.00", QuantitySold="1", GrossProfit="4.00", CustomerType="Wholesale")
        result = service_menu.parts("ADMIN")
        assert result["part_sales"]["count"] == 2
        assert result["part_sales"]["revenue_total"] == 40.0  # 15*2 + 10*1
        assert result["part_sales"]["gross_profit_total"] == 24.0
        assert result["part_sales"]["by_customer_type"] == {"Retail": 1, "Wholesale": 1}

    def test_parts_query_matches_part_number_description_or_category(self):
        _part("PART-00001", PartNumber="PN-1", Description="Brake pad", Category="Brakes", QuantityOnHand="5", UnitCost="20", ListPrice="50")
        _part("PART-00002", PartNumber="PN-2", Description="Oil filter", Category="Filters", QuantityOnHand="5", UnitCost="5", ListPrice="15")
        result = service_menu.parts("ADMIN", "brake")
        assert result["count"] == 1
        assert result["results"][0]["part_number"] == "PN-1"

    def test_parts_query_is_case_insensitive_and_matches_category(self):
        _part("PART-00001", PartNumber="PN-1", Description="X", Category="Filters", QuantityOnHand="5", UnitCost="5", ListPrice="15")
        result = service_menu.parts("ADMIN", "FILTERS")
        assert result["count"] == 1

    def test_parts_query_no_match_returns_empty(self):
        _part("PART-00001", PartNumber="PN-1", Description="X", Category="Y")
        result = service_menu.parts("ADMIN", "no-such-string-anywhere")
        assert result["count"] == 0


class TestWarranty:

    def test_warranty_returns_expected_shape(self):
        result = service_menu.warranty("ADMIN")
        assert "warranty_claims" in result
        assert "recalls" in result
        assert "claims_workflow" in result
        assert "rejected_claims" in result
        assert "recall_management" in result

    def test_warranty_recall_counts_and_open_recall_briefs(self):
        _recall("RECALL-00001", open=True, recall_number="R1", make="Ford", model="F-150")
        _recall("RECALL-00002", open=False, recall_number="R2", make="Chevy", model="Malibu")
        result = service_menu.warranty("ADMIN")
        assert result["recalls"]["total"] == 2
        assert result["recalls"]["open"] == 1
        assert result["recalls"]["open_recalls"][0]["id"] == "RECALL-00001"
        assert result["recalls"]["open_recalls"][0]["make"] == "Ford"


class TestReporting:

    def test_reporting_returns_expected_top_level_shape(self):
        result = service_menu.reporting("ADMIN")
        assert set(result.keys()) == {
            "service_performance", "parts_performance", "warranty_performance",
            "personnel_performance", "advisor_performance", "technician_scorecard",
            "shop_capacity", "customer_retention", "forecasting",
            "department_intelligence", "not_yet_tracked",
        }

    def test_reporting_avg_revenue_per_ro_computed_correctly(self):
        _service_record("SRV-00001", Cost="250.00", LaborHours="1.5", PayType="Customer Pay")
        _service_record("SRV-00002", Cost="400.00", LaborHours="2.0", PayType="Warranty")
        result = service_menu.reporting("ADMIN")
        assert result["service_performance"]["repair_order_count"] == 2
        assert result["service_performance"]["service_revenue_total"] == 650.0
        assert result["service_performance"]["avg_revenue_per_ro"] == 325.0

    def test_reporting_avg_revenue_per_ro_none_when_no_records(self):
        result = service_menu.reporting("ADMIN")
        assert result["service_performance"]["avg_revenue_per_ro"] is None

    def test_reporting_parts_performance_computed_correctly(self):
        _part_sale("PSALE-00001", SalePrice="15.00", QuantitySold="2", GrossProfit="20.00")
        result = service_menu.reporting("ADMIN")
        assert result["parts_performance"]["part_sale_count"] == 1
        assert result["parts_performance"]["parts_revenue_total"] == 30.0
        assert result["parts_performance"]["parts_gross_profit_total"] == 20.0

    def test_reporting_department_intelligence_covers_both_service_and_parts(self):
        result = service_menu.reporting("ADMIN")
        assert set(result["department_intelligence"].keys()) == {"service", "parts"}

    def test_reporting_forecasting_covers_both_service_and_parts(self):
        result = service_menu.reporting("ADMIN")
        assert "service" in result["forecasting"]
        assert "parts" in result["forecasting"]

    def test_reporting_honest_gaps_stated_plainly(self):
        result = service_menu.reporting("ADMIN")
        assert "effective_labor_rate" in result["not_yet_tracked"]
        assert "csi_reporting" in result["not_yet_tracked"]
