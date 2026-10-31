"""
Tests for core/parts_desk.py + core/parts_desk_api.py -- Service's Parts
Request Queue / Special Order Tracking / Inventory Recommendations, all real
composition on top of core/repair_orders.py's own parts_requests mechanism
and real Part/PartSale entities. No mutations of its own except
mark_special_order (which extends an existing part-request dict).
"""
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import CUSTOMER, VEHICLE, PART, PART_SALE
from core import repair_orders
from core import parts_desk
from core import parts_desk_api
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    monkeypatch.setattr(repair_orders, "save_graph", lambda filepath: None)
    monkeypatch.setattr(parts_desk, "save_graph", lambda filepath: None)


_VIEW_ROLES = (ADMIN, OPERATIONS, SALES, SERVICE, FINANCE)
_VIEW_DENIED_ROLES = (MARKETING,)
_MUTATE_ROLES = (ADMIN, OPERATIONS, SERVICE)
_MUTATE_DENIED_ROLES = (SALES, MARKETING, FINANCE)


def _add_customer(customer_id="CUST-1", first="Jane", last="Doe"):
    ledger.add_entity(Entity(id=customer_id, entity_type=CUSTOMER, attributes={
        "CustomerID": customer_id, "FirstName": first, "LastName": last,
    }))
    return customer_id


def _add_vehicle(vehicle_id="VEH-1", vin="VIN1234567890"):
    ledger.add_entity(Entity(id=vehicle_id, entity_type=VEHICLE, attributes={
        "VIN": vin, "Year": "2022", "Make": "Ford", "Model": "F-150", "Mileage": 30000,
    }))
    return vehicle_id


def _add_ro(customer_id="CUST-1", vehicle_id="VEH-1", description="Brake noise", created_by="EMP-1"):
    result = repair_orders.create_repair_order(vehicle_id, customer_id, description, created_by)
    assert "error" not in result
    return result["id"]


def _request_part(ro_id, description="Brake pads", requested_by="EMP-1"):
    result = repair_orders.request_part(ro_id, description, requested_by)
    assert "error" not in result
    return result["parts_requests"][-1]["id"]


def _add_part(part_id="PART-1", part_number="PN-100", on_hand=0, category="Brakes"):
    ledger.add_entity(Entity(id=part_id, entity_type=PART, attributes={
        "PartNumber": part_number, "Description": "Brake Pad Set", "Category": category,
        "QuantityOnHand": on_hand,
    }))
    return part_id


def _add_part_sale(sale_id, part_number, quantity_sold, sale_date):
    ledger.add_entity(Entity(id=sale_id, entity_type=PART_SALE, attributes={
        "PartNumber": part_number, "QuantitySold": quantity_sold, "SaleDate": sale_date,
    }))
    return sale_id


def _days_ago(n):
    return (date.today() - timedelta(days=n)).isoformat()


# ---------------------------------------------------------------------------
# get_parts_request_queue
# ---------------------------------------------------------------------------

class TestGetPartsRequestQueue:
    def test_empty_when_no_live_ros(self):
        result = parts_desk.get_parts_request_queue()
        assert result == {"count": 0, "by_status": {}, "requests": []}

    def test_includes_a_real_request_with_ro_context_attached(self):
        _add_customer()
        _add_vehicle()
        ro_id = _add_ro()
        _request_part(ro_id, description="Brake pads")

        result = parts_desk.get_parts_request_queue()
        assert result["count"] == 1
        entry = result["requests"][0]
        assert entry["ro_id"] == ro_id
        assert entry["customer_name"] == "Jane Doe"
        assert "F-150" in entry["vehicle"]
        assert entry["description"] == "Brake pads"

    def test_ro_description_is_not_clobbered_by_the_part_description(self):
        # Regression for the documented "description" key collision this
        # module's own module docstring says was found and fixed live.
        _add_customer()
        _add_vehicle()
        ro_id = _add_ro(description="Grinding noise at highway speed")
        _request_part(ro_id, description="Water pump")

        entry = parts_desk.get_parts_request_queue()["requests"][0]
        assert entry["ro_description"] == "Grinding noise at highway speed"
        assert entry["description"] == "Water pump"

    def test_filters_by_status(self):
        _add_customer()
        _add_vehicle()
        ro_id = _add_ro()
        req_id = _request_part(ro_id)
        repair_orders.update_part_request_status(ro_id, req_id, "ordered", "EMP-1")
        _request_part(ro_id, description="Second part")

        result = parts_desk.get_parts_request_queue(status="ordered")
        assert result["count"] == 1
        assert result["requests"][0]["description"] == "Brake pads"

    def test_by_status_breakdown_counts_every_request_regardless_of_filter(self):
        _add_customer()
        _add_vehicle()
        ro_id = _add_ro()
        req_id = _request_part(ro_id)
        repair_orders.update_part_request_status(ro_id, req_id, "ordered", "EMP-1")
        _request_part(ro_id, description="Second part")

        result = parts_desk.get_parts_request_queue()
        assert result["by_status"]["ordered"] == 1
        assert result["by_status"]["requested"] == 1

    def test_sorted_most_recently_requested_first(self):
        _add_customer()
        _add_vehicle()
        ro_id = _add_ro()
        _request_part(ro_id, description="First")
        _request_part(ro_id, description="Second")

        result = parts_desk.get_parts_request_queue()
        assert result["requests"][0]["description"] == "Second"
        assert result["requests"][1]["description"] == "First"

    def test_ros_with_no_parts_requests_are_excluded(self):
        _add_customer()
        _add_vehicle()
        _add_ro()  # no parts requested
        result = parts_desk.get_parts_request_queue()
        assert result == {"count": 0, "by_status": {}, "requests": []}


# ---------------------------------------------------------------------------
# mark_special_order
# ---------------------------------------------------------------------------

class TestMarkSpecialOrder:
    def test_rejects_a_missing_vendor(self):
        _add_customer()
        _add_vehicle()
        ro_id = _add_ro()
        req_id = _request_part(ro_id)
        result = parts_desk.mark_special_order(ro_id, req_id, "", "2026-08-01", "EMP-1")
        assert "error" in result

    def test_rejects_a_missing_eta(self):
        _add_customer()
        _add_vehicle()
        ro_id = _add_ro()
        req_id = _request_part(ro_id)
        result = parts_desk.mark_special_order(ro_id, req_id, "NAPA", "", "EMP-1")
        assert "error" in result

    def test_rejects_an_unknown_ro(self):
        result = parts_desk.mark_special_order("SRV-NOPE", "PREQ-1", "NAPA", "2026-08-01", "EMP-1")
        assert "error" in result

    def test_rejects_an_unknown_request_id(self):
        _add_customer()
        _add_vehicle()
        ro_id = _add_ro()
        _request_part(ro_id)
        result = parts_desk.mark_special_order(ro_id, "PREQ-NOPE", "NAPA", "2026-08-01", "EMP-1")
        assert "error" in result

    def test_marks_a_requested_part_as_a_special_order_and_advances_status(self):
        _add_customer()
        _add_vehicle()
        ro_id = _add_ro()
        req_id = _request_part(ro_id)

        result = parts_desk.mark_special_order(ro_id, req_id, "NAPA", "2026-08-01", "EMP-1")
        assert "error" not in result
        assert result["is_special_order"] is True
        assert result["vendor"] == "NAPA"
        assert result["eta"] == "2026-08-01"
        assert result["status"] == "ordered"
        assert result["updated_by"] == "EMP-1"

    def test_does_not_regress_an_already_further_along_status(self):
        _add_customer()
        _add_vehicle()
        ro_id = _add_ro()
        req_id = _request_part(ro_id)
        repair_orders.update_part_request_status(ro_id, req_id, "received", "EMP-1")

        result = parts_desk.mark_special_order(ro_id, req_id, "NAPA", "2026-08-01", "EMP-1")
        assert result["status"] == "received"

    def test_persists_onto_the_ro(self):
        _add_customer()
        _add_vehicle()
        ro_id = _add_ro()
        req_id = _request_part(ro_id)
        parts_desk.mark_special_order(ro_id, req_id, "NAPA", "2026-08-01", "EMP-1")

        ro = repair_orders._get_ro(ro_id)
        stored = next(r for r in ro.attributes["parts_requests"] if r["id"] == req_id)
        assert stored["is_special_order"] is True
        assert stored["vendor"] == "NAPA"


# ---------------------------------------------------------------------------
# get_special_orders
# ---------------------------------------------------------------------------

class TestGetSpecialOrders:
    def test_empty_when_none(self):
        result = parts_desk.get_special_orders()
        assert result == {"count": 0, "overdue_count": 0, "special_orders": []}

    def test_only_includes_special_orders(self):
        _add_customer()
        _add_vehicle()
        ro_id = _add_ro()
        req_a = _request_part(ro_id, description="A")
        req_b = _request_part(ro_id, description="B")
        parts_desk.mark_special_order(ro_id, req_a, "NAPA", _days_ago(-10), "EMP-1")

        result = parts_desk.get_special_orders()
        assert result["count"] == 1
        assert result["special_orders"][0]["id"] == req_a

    def test_flags_a_past_due_eta_as_overdue(self):
        _add_customer()
        _add_vehicle()
        ro_id = _add_ro()
        req_id = _request_part(ro_id)
        parts_desk.mark_special_order(ro_id, req_id, "NAPA", _days_ago(3), "EMP-1")

        result = parts_desk.get_special_orders()
        assert result["overdue_count"] == 1
        assert result["special_orders"][0]["overdue"] is True

    def test_does_not_flag_a_future_eta_as_overdue(self):
        _add_customer()
        _add_vehicle()
        ro_id = _add_ro()
        req_id = _request_part(ro_id)
        parts_desk.mark_special_order(ro_id, req_id, "NAPA", _days_ago(-10), "EMP-1")

        result = parts_desk.get_special_orders()
        assert result["overdue_count"] == 0
        assert result["special_orders"][0]["overdue"] is False

    def test_a_received_special_order_past_its_eta_is_not_overdue(self):
        _add_customer()
        _add_vehicle()
        ro_id = _add_ro()
        req_id = _request_part(ro_id)
        parts_desk.mark_special_order(ro_id, req_id, "NAPA", _days_ago(3), "EMP-1")
        repair_orders.update_part_request_status(ro_id, req_id, "received", "EMP-1")

        result = parts_desk.get_special_orders()
        assert result["special_orders"][0]["overdue"] is False

    def test_overdue_entries_sort_before_non_overdue(self):
        _add_customer()
        _add_vehicle()
        ro_id = _add_ro()
        req_future = _request_part(ro_id, description="Future")
        req_overdue = _request_part(ro_id, description="Overdue")
        parts_desk.mark_special_order(ro_id, req_future, "NAPA", _days_ago(-5), "EMP-1")
        parts_desk.mark_special_order(ro_id, req_overdue, "NAPA", _days_ago(2), "EMP-1")

        result = parts_desk.get_special_orders()
        assert result["special_orders"][0]["id"] == req_overdue


# ---------------------------------------------------------------------------
# get_inventory_recommendations
# ---------------------------------------------------------------------------

class TestGetInventoryRecommendations:
    def test_empty_when_no_parts(self):
        result = parts_desk.get_inventory_recommendations()
        assert result["count"] == 0

    def test_a_part_with_no_real_sales_history_is_excluded(self):
        _add_part("PART-1", "PN-100", on_hand=0)
        result = parts_desk.get_inventory_recommendations()
        assert result["count"] == 0

    def test_a_zero_on_hand_part_with_real_sales_is_flagged(self):
        _add_part("PART-1", "PN-100", on_hand=0)
        _add_part_sale("PS-1", "PN-100", 5, _days_ago(10))

        result = parts_desk.get_inventory_recommendations()
        assert result["count"] == 1
        rec = result["recommendations"][0]
        assert rec["part_number"] == "PN-100"
        assert rec["quantity_on_hand"] == 0
        assert "out of stock" in rec["recommendation"]

    def test_a_well_stocked_part_is_not_flagged(self):
        _add_part("PART-1", "PN-100", on_hand=10000)
        _add_part_sale("PS-1", "PN-100", 1, _days_ago(30))

        result = parts_desk.get_inventory_recommendations()
        assert result["count"] == 0

    def test_a_low_supply_part_is_flagged_with_days_of_supply(self):
        # 10 units sold over 10 days -> velocity 1/day; on_hand=5 -> 5 days of supply
        _add_part("PART-1", "PN-100", on_hand=5)
        _add_part_sale("PS-1", "PN-100", 10, _days_ago(10))

        result = parts_desk.get_inventory_recommendations()
        assert result["count"] == 1
        rec = result["recommendations"][0]
        assert rec["days_of_supply"] == 5.0
        assert "Reorder soon" in rec["recommendation"]

    def test_respects_the_limit(self):
        for i in range(3):
            _add_part(f"PART-{i}", f"PN-{i}", on_hand=0)
            _add_part_sale(f"PS-{i}", f"PN-{i}", 5, _days_ago(10))

        result = parts_desk.get_inventory_recommendations(limit=2)
        # count reports the true total (matching wholesale_desk's own
        # count-vs-limited-list convention), only the returned list is capped
        assert result["count"] == 3
        assert len(result["recommendations"]) == 2

    def test_sorted_worst_days_of_supply_first(self):
        _add_part("PART-LOW", "PN-LOW", on_hand=1)
        _add_part_sale("PS-LOW", "PN-LOW", 10, _days_ago(10))  # velocity 1/day -> 1 day of supply

        _add_part("PART-ZERO", "PN-ZERO", on_hand=0)
        _add_part_sale("PS-ZERO", "PN-ZERO", 5, _days_ago(10))  # 0 on hand -> days_of_supply None -> sorts first (-1)

        result = parts_desk.get_inventory_recommendations()
        assert result["recommendations"][0]["part_number"] == "PN-ZERO"

    def test_carries_the_honest_not_yet_tracked_note(self):
        result = parts_desk.get_inventory_recommendations()
        assert "reorder_points" in result["not_yet_tracked"]


# ---------------------------------------------------------------------------
# ACL sweep -- core/parts_desk_api.py
# ---------------------------------------------------------------------------

class TestAcl:
    @pytest.mark.parametrize("role", _VIEW_DENIED_ROLES)
    def test_get_parts_request_queue_api_denied(self, role):
        result = parts_desk_api.get_parts_request_queue_api(role)
        assert "error" in result

    @pytest.mark.parametrize("role", _VIEW_ROLES)
    def test_get_parts_request_queue_api_allowed(self, role):
        result = parts_desk_api.get_parts_request_queue_api(role)
        assert "count" in result

    @pytest.mark.parametrize("role", _MUTATE_DENIED_ROLES)
    def test_mark_special_order_api_denied(self, role):
        _add_customer()
        _add_vehicle()
        ro_id = _add_ro()
        req_id = _request_part(ro_id)
        result = parts_desk_api.mark_special_order_api(role, ro_id, req_id, "NAPA", "2026-08-01", "EMP-1")
        assert "error" in result

    @pytest.mark.parametrize("role", _MUTATE_ROLES)
    def test_mark_special_order_api_allowed(self, role):
        ledger.reset()
        _add_customer()
        _add_vehicle()
        ro_id = _add_ro()
        req_id = _request_part(ro_id)
        result = parts_desk_api.mark_special_order_api(role, ro_id, req_id, "NAPA", "2026-08-01", "EMP-1")
        assert result["is_special_order"] is True

    @pytest.mark.parametrize("role", _VIEW_DENIED_ROLES)
    def test_get_special_orders_api_denied(self, role):
        result = parts_desk_api.get_special_orders_api(role)
        assert "error" in result

    @pytest.mark.parametrize("role", _VIEW_ROLES)
    def test_get_special_orders_api_allowed(self, role):
        result = parts_desk_api.get_special_orders_api(role)
        assert "count" in result

    @pytest.mark.parametrize("role", _VIEW_DENIED_ROLES)
    def test_get_inventory_recommendations_api_denied(self, role):
        result = parts_desk_api.get_inventory_recommendations_api(role)
        assert "error" in result

    @pytest.mark.parametrize("role", _VIEW_ROLES)
    def test_get_inventory_recommendations_api_allowed(self, role):
        result = parts_desk_api.get_inventory_recommendations_api(role)
        assert "count" in result


def test_counter_receipt_and_technician_install_share_request_and_context():
    _add_customer()
    _add_vehicle()
    ro_id = _add_ro()
    request_id = _request_part(ro_id, "Synthetic brake pads")
    parts_desk.mark_special_order(ro_id, request_id, "Synthetic supplier", "2026-10-14", "COUNTER")
    repair_orders.update_part_request_status(ro_id, request_id, "received", "COUNTER")
    received = parts_desk.get_parts_request_queue("received")["requests"][0]
    assert received["id"] == request_id and received["ro_id"] == ro_id
    assert received["customer_name"] == "Jane Doe"
    assert received["description"] == "Synthetic brake pads"
    assert received["vendor"] == "Synthetic supplier"
    assert received["updated_by"] == "COUNTER"
    workspace = repair_orders.get_ro_workspace(ro_id)
    assert workspace["parts_requests"][0]["status"] == "received"
    repair_orders.update_part_request_status(ro_id, request_id, "installed", "TECHNICIAN")
    assert parts_desk.get_parts_request_queue("received")["count"] == 0
    installed = parts_desk.get_parts_request_queue("installed")["requests"][0]
    assert installed["id"] == request_id and installed["updated_by"] == "TECHNICIAN"
    assert installed["vendor"] == "Synthetic supplier"
    assert repair_orders.get_ro_workspace(ro_id)["status"] == workspace["status"]
