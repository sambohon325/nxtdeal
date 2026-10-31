"""
core/loaner_shuttle_api.py -- ACL layer for core/loaner_shuttle.py. Viewing
the fleet/assignments/shuttle queue is broad (ADMIN/OPERATIONS/SALES/
SERVICE/FINANCE), matching the RO Workflow Engine's own view set -- Sales
cares whether a customer has a loaner for delivery-day planning, Finance
cares about fleet asset visibility. Mutating (adding to the fleet, checkout/
checkin, shuttle request/assign/status) is ADMIN/OPERATIONS/SERVICE only,
matching every other Service-specific workflow engine's mutate set.
"""

from core.permissions import ADMIN, OPERATIONS, SALES, SERVICE, FINANCE
from core.loaner_shuttle import (
    add_loaner_vehicle, update_loaner_status, get_loaner_vehicle, list_loaner_fleet,
    checkout_loaner, checkin_loaner, get_assignment, get_assignments_for_ro,
    get_assignments_for_customer, get_loaner_board,
    request_shuttle, assign_shuttle_driver, update_shuttle_status, get_shuttle_request,
    list_shuttle_requests, get_shuttle_requests_for_ro, get_shuttle_queue,
    get_ro_transportation_summary,
)

_VIEW_ROLES = (ADMIN, OPERATIONS, SALES, SERVICE, FINANCE)
_MUTATE_ROLES = (ADMIN, OPERATIONS, SERVICE)


def _denied():
    return {"error": "You don't have access to Loaner & Shuttle Management"}


# --- Fleet ---

def add_loaner_vehicle_api(role, added_by, make, model, year, vin, mileage, notes=""):
    if role not in _MUTATE_ROLES:
        return _denied()
    return add_loaner_vehicle(make, model, year, vin, mileage, added_by, notes=notes)


def update_loaner_status_api(role, updated_by, loaner_id, status, notes=""):
    if role not in _MUTATE_ROLES:
        return _denied()
    return update_loaner_status(loaner_id, status, updated_by, notes=notes)


def get_loaner_vehicle_api(role, loaner_id):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_loaner_vehicle(loaner_id)


def list_loaner_fleet_api(role, status=None):
    if role not in _VIEW_ROLES:
        return _denied()
    return list_loaner_fleet(status=status)


def get_loaner_board_api(role):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_loaner_board()


# --- Assignments ---

def checkout_loaner_api(role, checked_out_by, loaner_vehicle_id, customer_id, odometer_out,
                         fuel_out="Full", ro_id=None, expected_return_at=None, agreement_signed=False, notes=""):
    if role not in _MUTATE_ROLES:
        return _denied()
    return checkout_loaner(
        loaner_vehicle_id, customer_id, checked_out_by, odometer_out,
        fuel_out=fuel_out, ro_id=ro_id, expected_return_at=expected_return_at,
        agreement_signed=agreement_signed, notes=notes,
    )


def checkin_loaner_api(role, checked_in_by, assignment_id, odometer_in, fuel_in="Full",
                        send_to_maintenance=False, notes=""):
    if role not in _MUTATE_ROLES:
        return _denied()
    return checkin_loaner(assignment_id, checked_in_by, odometer_in, fuel_in=fuel_in,
                           send_to_maintenance=send_to_maintenance, notes=notes)


def get_assignment_api(role, assignment_id):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_assignment(assignment_id)


def get_assignments_for_ro_api(role, ro_id):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_assignments_for_ro(ro_id)


def get_assignments_for_customer_api(role, customer_id):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_assignments_for_customer(customer_id)


# --- Shuttle ---

def request_shuttle_api(role, requested_by, customer_id, direction, pickup_location,
                         dropoff_location, requested_time, ro_id=None, notes=""):
    if role not in _MUTATE_ROLES:
        return _denied()
    return request_shuttle(customer_id, direction, pickup_location, dropoff_location,
                            requested_time, requested_by, ro_id=ro_id, notes=notes)


def assign_shuttle_driver_api(role, updated_by, request_id, driver_id):
    if role not in _MUTATE_ROLES:
        return _denied()
    return assign_shuttle_driver(request_id, driver_id, updated_by)


def update_shuttle_status_api(role, updated_by, request_id, status, notes=""):
    if role not in _MUTATE_ROLES:
        return _denied()
    return update_shuttle_status(request_id, status, updated_by, notes=notes)


def get_shuttle_request_api(role, request_id):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_shuttle_request(request_id)


def list_shuttle_requests_api(role, status=None):
    if role not in _VIEW_ROLES:
        return _denied()
    return list_shuttle_requests(status=status)


def get_shuttle_requests_for_ro_api(role, ro_id):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_shuttle_requests_for_ro(ro_id)


def get_shuttle_queue_api(role):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_shuttle_queue()


# --- Composed ---

def get_ro_transportation_summary_api(role, ro_id):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_ro_transportation_summary(ro_id)
