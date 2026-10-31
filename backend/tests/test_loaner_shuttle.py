"""
Tests for core/loaner_shuttle.py + core/loaner_shuttle_api.py -- Loaner &
Shuttle Management (session 111 follow-up, "FEATURES COMPLETELY MISSING"
Service list item #3): the real fleet/checkout-checkin/shuttle-request
lifecycle plus the composed RO-scoped transportation view.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import CUSTOMER, VEHICLE
from core import repair_orders
from core import loaner_shuttle
from core import loaner_shuttle_api
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    monkeypatch.setattr(loaner_shuttle, "save_graph", lambda filepath: None)
    monkeypatch.setattr(repair_orders, "save_graph", lambda filepath: None)


_VIEW_ROLES = (ADMIN, OPERATIONS, SALES, SERVICE, FINANCE)
_VIEW_DENIED_ROLES = (MARKETING,)
_MUTATE_ROLES = (ADMIN, OPERATIONS, SERVICE)
_MUTATE_DENIED_ROLES = (SALES, MARKETING, FINANCE)


def _add_customer(customer_id="CUST-1", customer_key="C1", first="Jane", last="Doe"):
    ledger.add_entity(Entity(
        id=customer_id,
        entity_type=CUSTOMER,
        attributes={"CustomerID": customer_key, "FirstName": first, "LastName": last},
    ))
    return customer_id


def _add_vehicle(vehicle_id="VEH-1", vin="VIN1", make="Honda", model="Civic", year="2025"):
    ledger.add_entity(Entity(
        id=vehicle_id,
        entity_type=VEHICLE,
        attributes={"VIN": vin, "Make": make, "Model": model, "Year": year, "Mileage": 10000},
    ))
    return vehicle_id


def _add_ro(vehicle_id="VEH-1", customer_id="CUST-1", created_by="EMP-1"):
    result = repair_orders.create_repair_order(vehicle_id, customer_id, "Strange noise", created_by)
    return result["id"]


def _add_loaner(**kwargs):
    defaults = dict(make="Toyota", model="Corolla", year="2024", vin="LOANVIN1", mileage=5000, added_by="EMP-1")
    defaults.update(kwargs)
    result = loaner_shuttle.add_loaner_vehicle(**defaults)
    return result["loaner_id"]


# ---------------------------------------------------------------------------
# Loaner fleet
# ---------------------------------------------------------------------------

def test_add_loaner_vehicle_creates_real_available_entity():
    loaner_id = _add_loaner()
    v = ledger.get_entity(loaner_id)
    assert v is not None
    assert v.attributes["status"] == "available"
    assert v.attributes["make"] == "Toyota"


def test_get_loaner_vehicle_unknown_errors():
    result = loaner_shuttle.get_loaner_vehicle("LOAN-999")
    assert "error" in result


def test_get_loaner_vehicle_includes_assignment_history():
    loaner_id = _add_loaner()
    result = loaner_shuttle.get_loaner_vehicle(loaner_id)
    assert result["loaner_id"] == loaner_id
    assert result["assignment_history"] == []


def test_list_loaner_fleet_filters_by_status():
    id1 = _add_loaner(vin="V1")
    id2 = _add_loaner(vin="V2")
    loaner_shuttle.update_loaner_status(id2, "maintenance", "EMP-1")

    all_fleet = loaner_shuttle.list_loaner_fleet()
    assert all_fleet["count"] == 2

    available = loaner_shuttle.list_loaner_fleet(status="available")
    assert available["count"] == 1
    assert available["fleet"][0]["loaner_id"] == id1


def test_update_loaner_status_unknown_loaner_errors():
    result = loaner_shuttle.update_loaner_status("LOAN-999", "maintenance", "EMP-1")
    assert "error" in result


def test_update_loaner_status_rejects_bad_status():
    loaner_id = _add_loaner()
    result = loaner_shuttle.update_loaner_status(loaner_id, "on_the_moon", "EMP-1")
    assert "error" in result


def test_update_loaner_status_rejects_direct_transition_to_out():
    loaner_id = _add_loaner()
    result = loaner_shuttle.update_loaner_status(loaner_id, "out", "EMP-1")
    assert "error" in result
    assert "checkout_loaner" in result["error"]


def test_update_loaner_status_rejects_while_checked_out():
    _add_customer()
    loaner_id = _add_loaner()
    loaner_shuttle.checkout_loaner(loaner_id, "CUST-1", "EMP-1", odometer_out=5000)
    result = loaner_shuttle.update_loaner_status(loaner_id, "maintenance", "EMP-1")
    assert "error" in result
    assert "currently checked out" in result["error"]


def test_update_loaner_status_success():
    loaner_id = _add_loaner()
    result = loaner_shuttle.update_loaner_status(loaner_id, "out_of_service", "EMP-1", notes="engine trouble")
    assert result["status"] == "out_of_service"
    v = ledger.get_entity(loaner_id)
    assert "engine trouble" in v.attributes["notes"]


# ---------------------------------------------------------------------------
# checkout_loaner / checkin_loaner
# ---------------------------------------------------------------------------

def test_checkout_loaner_unknown_loaner_errors():
    _add_customer()
    result = loaner_shuttle.checkout_loaner("LOAN-999", "CUST-1", "EMP-1", odometer_out=5000)
    assert "error" in result


def test_checkout_loaner_rejects_when_not_available():
    _add_customer()
    loaner_id = _add_loaner()
    loaner_shuttle.update_loaner_status(loaner_id, "maintenance", "EMP-1")
    result = loaner_shuttle.checkout_loaner(loaner_id, "CUST-1", "EMP-1", odometer_out=5000)
    assert "error" in result
    assert "not available" in result["error"]


def test_checkout_loaner_unknown_customer_errors():
    loaner_id = _add_loaner()
    result = loaner_shuttle.checkout_loaner(loaner_id, "CUST-999", "EMP-1", odometer_out=5000)
    assert "error" in result


def test_checkout_loaner_unknown_ro_errors():
    _add_customer()
    loaner_id = _add_loaner()
    result = loaner_shuttle.checkout_loaner(loaner_id, "CUST-1", "EMP-1", odometer_out=5000, ro_id="SRV-999")
    assert "error" in result


def test_checkout_loaner_rejects_bad_odometer():
    _add_customer()
    loaner_id = _add_loaner()
    result = loaner_shuttle.checkout_loaner(loaner_id, "CUST-1", "EMP-1", odometer_out="not-a-number")
    assert "error" in result


def test_checkout_loaner_success_flips_loaner_to_out():
    _add_customer()
    _add_vehicle()
    ro_id = _add_ro()
    loaner_id = _add_loaner()

    result = loaner_shuttle.checkout_loaner(
        loaner_id, "CUST-1", "EMP-1", odometer_out=5000, ro_id=ro_id, agreement_signed=True,
    )
    assert result["loaner_vehicle_id"] == loaner_id
    assert result["ro_id"] == ro_id
    assert result["agreement_signed"] is True
    assert result["status"] == "out"

    v = ledger.get_entity(loaner_id)
    assert v.attributes["status"] == "out"


def test_checkin_loaner_unknown_assignment_errors():
    result = loaner_shuttle.checkin_loaner("LNAS-999", "EMP-1", odometer_in=5100)
    assert "error" in result


def test_checkin_loaner_rejects_already_checked_in():
    _add_customer()
    loaner_id = _add_loaner()
    checkout = loaner_shuttle.checkout_loaner(loaner_id, "CUST-1", "EMP-1", odometer_out=5000)
    loaner_shuttle.checkin_loaner(checkout["id"], "EMP-1", odometer_in=5100)
    result = loaner_shuttle.checkin_loaner(checkout["id"], "EMP-1", odometer_in=5150)
    assert "error" in result
    assert "already been checked in" in result["error"]


def test_checkin_loaner_rejects_bad_odometer():
    _add_customer()
    loaner_id = _add_loaner()
    checkout = loaner_shuttle.checkout_loaner(loaner_id, "CUST-1", "EMP-1", odometer_out=5000)
    result = loaner_shuttle.checkin_loaner(checkout["id"], "EMP-1", odometer_in="not-a-number")
    assert "error" in result


def test_checkin_loaner_rejects_odometer_in_less_than_out():
    _add_customer()
    loaner_id = _add_loaner()
    checkout = loaner_shuttle.checkout_loaner(loaner_id, "CUST-1", "EMP-1", odometer_out=5000)
    result = loaner_shuttle.checkin_loaner(checkout["id"], "EMP-1", odometer_in=4900)
    assert "error" in result


def test_checkin_loaner_success_computes_miles_and_frees_loaner():
    _add_customer()
    loaner_id = _add_loaner()
    checkout = loaner_shuttle.checkout_loaner(loaner_id, "CUST-1", "EMP-1", odometer_out=5000)
    result = loaner_shuttle.checkin_loaner(checkout["id"], "EMP-1", odometer_in=5175, fuel_in="Half")

    assert result["miles_driven"] == 175
    assert result["odometer_in"] == 5175
    assert result["status"] == "returned"

    v = ledger.get_entity(loaner_id)
    assert v.attributes["status"] == "available"
    assert v.attributes["mileage"] == 5175


def test_checkin_loaner_send_to_maintenance_sets_loaner_maintenance():
    _add_customer()
    loaner_id = _add_loaner()
    checkout = loaner_shuttle.checkout_loaner(loaner_id, "CUST-1", "EMP-1", odometer_out=5000)
    loaner_shuttle.checkin_loaner(checkout["id"], "EMP-1", odometer_in=5100, send_to_maintenance=True)

    v = ledger.get_entity(loaner_id)
    assert v.attributes["status"] == "maintenance"


def test_get_assignment_unknown_errors():
    result = loaner_shuttle.get_assignment("LNAS-999")
    assert "error" in result


def test_assignment_status_overdue_when_expected_return_in_past():
    _add_customer()
    loaner_id = _add_loaner()
    checkout = loaner_shuttle.checkout_loaner(
        loaner_id, "CUST-1", "EMP-1", odometer_out=5000, expected_return_at="2020-01-01T00:00:00+00:00",
    )
    result = loaner_shuttle.get_assignment(checkout["id"])
    assert result["status"] == "overdue"


def test_get_assignments_for_loaner_sorted_most_recent_first():
    _add_customer()
    loaner_id = _add_loaner()
    a1 = loaner_shuttle.checkout_loaner(loaner_id, "CUST-1", "EMP-1", odometer_out=5000)
    loaner_shuttle.checkin_loaner(a1["id"], "EMP-1", odometer_in=5100)
    a2 = loaner_shuttle.checkout_loaner(loaner_id, "CUST-1", "EMP-1", odometer_out=5100)

    history = loaner_shuttle.get_assignments_for_loaner(loaner_id)
    assert len(history) == 2
    assert history[0]["id"] == a2["id"]


def test_get_assignments_for_ro():
    _add_customer()
    _add_vehicle()
    ro_id = _add_ro()
    loaner_id = _add_loaner()
    loaner_shuttle.checkout_loaner(loaner_id, "CUST-1", "EMP-1", odometer_out=5000, ro_id=ro_id)

    assignments = loaner_shuttle.get_assignments_for_ro(ro_id)
    assert len(assignments) == 1
    assert assignments[0]["ro_id"] == ro_id


def test_get_assignments_for_customer():
    _add_customer()
    loaner_id = _add_loaner()
    loaner_shuttle.checkout_loaner(loaner_id, "CUST-1", "EMP-1", odometer_out=5000)

    assignments = loaner_shuttle.get_assignments_for_customer("CUST-1")
    assert len(assignments) == 1
    assert assignments[0]["customer"]["customer_id"] == "CUST-1"


def test_get_loaner_board_counts_and_overdue():
    _add_customer()
    id1 = _add_loaner(vin="V1")
    id2 = _add_loaner(vin="V2")
    loaner_shuttle.update_loaner_status(id2, "maintenance", "EMP-1")

    loaner_shuttle.checkout_loaner(id1, "CUST-1", "EMP-1", odometer_out=5000, expected_return_at="2020-01-01T00:00:00+00:00")

    board = loaner_shuttle.get_loaner_board()
    assert board["total_fleet"] == 2
    assert board["by_status"]["out"] == 1
    assert board["by_status"]["maintenance"] == 1
    assert board["overdue_count"] == 1
    assert len(board["active_assignments"]) == 1


# ---------------------------------------------------------------------------
# Shuttle requests
# ---------------------------------------------------------------------------

def test_request_shuttle_unknown_customer_errors():
    result = loaner_shuttle.request_shuttle(
        "CUST-999", "to_dealership", "123 Main St", "Dealership", "2026-06-01T09:00:00", "EMP-1",
    )
    assert "error" in result


def test_request_shuttle_rejects_bad_direction():
    _add_customer()
    result = loaner_shuttle.request_shuttle(
        "CUST-1", "sideways", "123 Main St", "Dealership", "2026-06-01T09:00:00", "EMP-1",
    )
    assert "error" in result


def test_request_shuttle_unknown_ro_errors():
    _add_customer()
    result = loaner_shuttle.request_shuttle(
        "CUST-1", "to_dealership", "123 Main St", "Dealership", "2026-06-01T09:00:00", "EMP-1", ro_id="SRV-999",
    )
    assert "error" in result


def test_request_shuttle_success():
    _add_customer()
    result = loaner_shuttle.request_shuttle(
        "CUST-1", "from_dealership", "Dealership", "123 Main St", "2026-06-01T15:00:00", "EMP-1",
    )
    assert result["status"] == "requested"
    assert result["direction"] == "from_dealership"
    assert result["customer"]["customer_id"] == "CUST-1"


def test_assign_shuttle_driver_unknown_request_errors():
    result = loaner_shuttle.assign_shuttle_driver("SHTL-999", "EMP-2", "EMP-1")
    assert "error" in result


def test_assign_shuttle_driver_rejects_terminal_status():
    _add_customer()
    req = loaner_shuttle.request_shuttle(
        "CUST-1", "to_dealership", "123 Main St", "Dealership", "2026-06-01T09:00:00", "EMP-1",
    )
    loaner_shuttle.update_shuttle_status(req["id"], "cancelled", "EMP-1")
    result = loaner_shuttle.assign_shuttle_driver(req["id"], "EMP-2", "EMP-1")
    assert "error" in result


def test_assign_shuttle_driver_moves_requested_to_assigned():
    _add_customer()
    req = loaner_shuttle.request_shuttle(
        "CUST-1", "to_dealership", "123 Main St", "Dealership", "2026-06-01T09:00:00", "EMP-1",
    )
    result = loaner_shuttle.assign_shuttle_driver(req["id"], "EMP-2", "EMP-1")
    assert result["status"] == "assigned"
    assert result["driver_id"] == "EMP-2"


def test_assign_shuttle_driver_does_not_change_status_if_already_assigned():
    _add_customer()
    req = loaner_shuttle.request_shuttle(
        "CUST-1", "to_dealership", "123 Main St", "Dealership", "2026-06-01T09:00:00", "EMP-1",
    )
    loaner_shuttle.assign_shuttle_driver(req["id"], "EMP-2", "EMP-1")
    loaner_shuttle.update_shuttle_status(req["id"], "en_route", "EMP-1")
    result = loaner_shuttle.assign_shuttle_driver(req["id"], "EMP-3", "EMP-1")
    assert result["status"] == "en_route"
    assert result["driver_id"] == "EMP-3"


def test_update_shuttle_status_unknown_request_errors():
    result = loaner_shuttle.update_shuttle_status("SHTL-999", "assigned", "EMP-1")
    assert "error" in result


def test_update_shuttle_status_rejects_bad_status_value():
    _add_customer()
    req = loaner_shuttle.request_shuttle(
        "CUST-1", "to_dealership", "123 Main St", "Dealership", "2026-06-01T09:00:00", "EMP-1",
    )
    result = loaner_shuttle.update_shuttle_status(req["id"], "teleported", "EMP-1")
    assert "error" in result


def test_update_shuttle_status_rejects_invalid_transition():
    _add_customer()
    req = loaner_shuttle.request_shuttle(
        "CUST-1", "to_dealership", "123 Main St", "Dealership", "2026-06-01T09:00:00", "EMP-1",
    )
    result = loaner_shuttle.update_shuttle_status(req["id"], "completed", "EMP-1")
    assert "error" in result
    assert "Cannot move" in result["error"]


def test_update_shuttle_status_full_valid_lifecycle():
    _add_customer()
    req = loaner_shuttle.request_shuttle(
        "CUST-1", "to_dealership", "123 Main St", "Dealership", "2026-06-01T09:00:00", "EMP-1",
    )
    req_id = req["id"]

    r1 = loaner_shuttle.update_shuttle_status(req_id, "assigned", "EMP-1")
    assert r1["status"] == "assigned"

    r2 = loaner_shuttle.update_shuttle_status(req_id, "en_route", "EMP-1")
    assert r2["status"] == "en_route"

    r3 = loaner_shuttle.update_shuttle_status(req_id, "completed", "EMP-1", notes="dropped off")
    assert r3["status"] == "completed"
    assert r3["completed_at"] is not None


def test_update_shuttle_status_cancelled_terminal_from_any_open_state():
    _add_customer()
    req = loaner_shuttle.request_shuttle(
        "CUST-1", "to_dealership", "123 Main St", "Dealership", "2026-06-01T09:00:00", "EMP-1",
    )
    result = loaner_shuttle.update_shuttle_status(req["id"], "cancelled", "EMP-1", notes="customer no-show")
    assert result["status"] == "cancelled"
    assert result["cancelled_reason"] == "customer no-show"

    result2 = loaner_shuttle.update_shuttle_status(req["id"], "assigned", "EMP-1")
    assert "error" in result2


def test_get_shuttle_request_unknown_errors():
    result = loaner_shuttle.get_shuttle_request("SHTL-999")
    assert "error" in result


def test_list_shuttle_requests_filters_by_status():
    _add_customer()
    r1 = loaner_shuttle.request_shuttle(
        "CUST-1", "to_dealership", "A", "B", "2026-06-01T09:00:00", "EMP-1",
    )
    r2 = loaner_shuttle.request_shuttle(
        "CUST-1", "to_dealership", "A", "B", "2026-06-01T10:00:00", "EMP-1",
    )
    loaner_shuttle.update_shuttle_status(r2["id"], "cancelled", "EMP-1")

    all_requests = loaner_shuttle.list_shuttle_requests()
    assert all_requests["count"] == 2

    requested_only = loaner_shuttle.list_shuttle_requests(status="requested")
    assert requested_only["count"] == 1
    assert requested_only["requests"][0]["id"] == r1["id"]


def test_get_shuttle_requests_for_ro():
    _add_customer()
    _add_vehicle()
    ro_id = _add_ro()
    req = loaner_shuttle.request_shuttle(
        "CUST-1", "to_dealership", "A", "B", "2026-06-01T09:00:00", "EMP-1", ro_id=ro_id,
    )
    result = loaner_shuttle.get_shuttle_requests_for_ro(ro_id)
    assert len(result) == 1
    assert result[0]["id"] == req["id"]


def test_get_shuttle_queue_pending_excludes_terminal_statuses():
    _add_customer()
    r1 = loaner_shuttle.request_shuttle(
        "CUST-1", "to_dealership", "A", "B", "2026-06-01T09:00:00", "EMP-1",
    )
    r2 = loaner_shuttle.request_shuttle(
        "CUST-1", "to_dealership", "A", "B", "2026-06-01T10:00:00", "EMP-1",
    )
    loaner_shuttle.update_shuttle_status(r2["id"], "cancelled", "EMP-1")

    queue = loaner_shuttle.get_shuttle_queue()
    assert queue["total"] == 2
    assert queue["by_status"]["cancelled"] == 1
    assert queue["by_status"]["requested"] == 1
    assert len(queue["pending"]) == 1
    assert queue["pending"][0]["id"] == r1["id"]


# ---------------------------------------------------------------------------
# Composed RO transportation view
# ---------------------------------------------------------------------------

def test_get_ro_transportation_summary_unknown_ro_errors():
    result = loaner_shuttle.get_ro_transportation_summary("SRV-999")
    assert "error" in result


def test_get_ro_transportation_summary_composes_active_loaner_and_shuttle():
    _add_customer()
    _add_vehicle()
    ro_id = _add_ro()
    loaner_id = _add_loaner()

    checkout = loaner_shuttle.checkout_loaner(loaner_id, "CUST-1", "EMP-1", odometer_out=5000, ro_id=ro_id)
    loaner_shuttle.request_shuttle(
        "CUST-1", "to_dealership", "A", "B", "2026-06-01T09:00:00", "EMP-1", ro_id=ro_id,
    )

    summary = loaner_shuttle.get_ro_transportation_summary(ro_id)
    assert summary["ro_id"] == ro_id
    assert summary["active_loaner_assignment"]["id"] == checkout["id"]
    assert len(summary["assignment_history"]) == 1
    assert len(summary["shuttle_requests"]) == 1


def test_get_ro_transportation_summary_no_active_loaner_once_returned():
    _add_customer()
    _add_vehicle()
    ro_id = _add_ro()
    loaner_id = _add_loaner()

    checkout = loaner_shuttle.checkout_loaner(loaner_id, "CUST-1", "EMP-1", odometer_out=5000, ro_id=ro_id)
    loaner_shuttle.checkin_loaner(checkout["id"], "EMP-1", odometer_in=5100)

    summary = loaner_shuttle.get_ro_transportation_summary(ro_id)
    assert summary["active_loaner_assignment"] is None
    assert len(summary["assignment_history"]) == 1


# ---------------------------------------------------------------------------
# ACL layer -- core/loaner_shuttle_api.py
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("role", _MUTATE_DENIED_ROLES)
def test_add_loaner_vehicle_api_denies_unauthorized_roles(role):
    result = loaner_shuttle_api.add_loaner_vehicle_api(role, "EMP-1", "Toyota", "Corolla", "2024", "VINX", 1000)
    assert "error" in result


@pytest.mark.parametrize("role", _MUTATE_ROLES)
def test_add_loaner_vehicle_api_allows_authorized_roles(role):
    ledger.reset()
    result = loaner_shuttle_api.add_loaner_vehicle_api(role, "EMP-1", "Toyota", "Corolla", "2024", "VINX", 1000)
    assert "loaner_id" in result


@pytest.mark.parametrize("role", _VIEW_DENIED_ROLES)
def test_list_loaner_fleet_api_denies_unauthorized_roles(role):
    result = loaner_shuttle_api.list_loaner_fleet_api(role)
    assert "error" in result


@pytest.mark.parametrize("role", _VIEW_ROLES)
def test_list_loaner_fleet_api_allows_authorized_roles(role):
    result = loaner_shuttle_api.list_loaner_fleet_api(role)
    assert "fleet" in result


@pytest.mark.parametrize("role", _VIEW_DENIED_ROLES)
def test_get_loaner_board_api_denies_unauthorized_roles(role):
    result = loaner_shuttle_api.get_loaner_board_api(role)
    assert "error" in result


@pytest.mark.parametrize("role", _VIEW_ROLES)
def test_get_loaner_board_api_allows_authorized_roles(role):
    result = loaner_shuttle_api.get_loaner_board_api(role)
    assert "total_fleet" in result


@pytest.mark.parametrize("role", _MUTATE_DENIED_ROLES)
def test_checkout_loaner_api_denies_unauthorized_roles(role):
    _add_customer()
    loaner_id = _add_loaner()
    result = loaner_shuttle_api.checkout_loaner_api(role, "EMP-1", loaner_id, "CUST-1", 5000)
    assert "error" in result


@pytest.mark.parametrize("role", _MUTATE_ROLES)
def test_checkout_loaner_api_allows_authorized_roles(role):
    ledger.reset()
    _add_customer()
    loaner_id = _add_loaner()
    result = loaner_shuttle_api.checkout_loaner_api(role, "EMP-1", loaner_id, "CUST-1", 5000)
    assert result["status"] == "out"


@pytest.mark.parametrize("role", _MUTATE_DENIED_ROLES)
def test_checkin_loaner_api_denies_unauthorized_roles(role):
    _add_customer()
    loaner_id = _add_loaner()
    checkout = loaner_shuttle.checkout_loaner(loaner_id, "CUST-1", "EMP-1", odometer_out=5000)
    result = loaner_shuttle_api.checkin_loaner_api(role, "EMP-1", checkout["id"], 5100)
    assert "error" in result


@pytest.mark.parametrize("role", _VIEW_DENIED_ROLES)
def test_get_assignments_for_customer_api_denies_unauthorized_roles(role):
    result = loaner_shuttle_api.get_assignments_for_customer_api(role, "CUST-1")
    assert "error" in result


@pytest.mark.parametrize("role", _VIEW_ROLES)
def test_get_assignments_for_customer_api_allows_authorized_roles(role):
    result = loaner_shuttle_api.get_assignments_for_customer_api(role, "CUST-1")
    assert result == []


@pytest.mark.parametrize("role", _MUTATE_DENIED_ROLES)
def test_request_shuttle_api_denies_unauthorized_roles(role):
    _add_customer()
    result = loaner_shuttle_api.request_shuttle_api(role, "EMP-1", "CUST-1", "to_dealership", "A", "B", "2026-06-01T09:00:00")
    assert "error" in result


@pytest.mark.parametrize("role", _MUTATE_ROLES)
def test_request_shuttle_api_allows_authorized_roles(role):
    ledger.reset()
    _add_customer()
    result = loaner_shuttle_api.request_shuttle_api(role, "EMP-1", "CUST-1", "to_dealership", "A", "B", "2026-06-01T09:00:00")
    assert result["status"] == "requested"


@pytest.mark.parametrize("role", _MUTATE_DENIED_ROLES)
def test_assign_shuttle_driver_api_denies_unauthorized_roles(role):
    _add_customer()
    req = loaner_shuttle.request_shuttle("CUST-1", "to_dealership", "A", "B", "2026-06-01T09:00:00", "EMP-1")
    result = loaner_shuttle_api.assign_shuttle_driver_api(role, "EMP-1", req["id"], "EMP-2")
    assert "error" in result


@pytest.mark.parametrize("role", _MUTATE_DENIED_ROLES)
def test_update_shuttle_status_api_denies_unauthorized_roles(role):
    _add_customer()
    req = loaner_shuttle.request_shuttle("CUST-1", "to_dealership", "A", "B", "2026-06-01T09:00:00", "EMP-1")
    result = loaner_shuttle_api.update_shuttle_status_api(role, "EMP-1", req["id"], "assigned")
    assert "error" in result


@pytest.mark.parametrize("role", _VIEW_DENIED_ROLES)
def test_get_shuttle_queue_api_denies_unauthorized_roles(role):
    result = loaner_shuttle_api.get_shuttle_queue_api(role)
    assert "error" in result


@pytest.mark.parametrize("role", _VIEW_ROLES)
def test_get_shuttle_queue_api_allows_authorized_roles(role):
    result = loaner_shuttle_api.get_shuttle_queue_api(role)
    assert "pending" in result


@pytest.mark.parametrize("role", _VIEW_DENIED_ROLES)
def test_get_ro_transportation_summary_api_denies_unauthorized_roles(role):
    _add_customer()
    _add_vehicle()
    ro_id = _add_ro()
    result = loaner_shuttle_api.get_ro_transportation_summary_api(role, ro_id)
    assert "error" in result


@pytest.mark.parametrize("role", _VIEW_ROLES)
def test_get_ro_transportation_summary_api_allows_authorized_roles(role):
    ledger.reset()
    _add_customer()
    _add_vehicle()
    ro_id = _add_ro()
    result = loaner_shuttle_api.get_ro_transportation_summary_api(role, ro_id)
    assert result["ro_id"] == ro_id
