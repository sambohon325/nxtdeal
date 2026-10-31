"""
core/lot_control_api.py -- ACL layer for core/lot_control.py. Viewing is
broad, same set used across this Inventory rebuild. Mutating (lot position,
key checkout/checkin, damage reports, showroom assignment, scan logging) is
ADMIN/OPERATIONS/SERVICE -- physical lot control and recon-adjacent damage
reporting genuinely involves Service technicians on the ground, matching
core/vehicle_lifecycle_api.py's own mutate set for the same physical-handling
reasoning (that module allows SERVICE to update recon items/vendor status).
Sales is view-only here -- moving keys and logging damage isn't a Sales
responsibility.
"""

from core.permissions import ADMIN, OPERATIONS, SALES, SERVICE, MARKETING, FINANCE
from core.lot_control import (
    set_lot_position, get_lot_position, get_lot_map,
    checkout_key, checkin_key, report_key_missing, get_key_status, get_key_board,
    report_damage, update_damage_status, list_damage_reports,
    assign_showroom, remove_showroom_assignment, get_showroom_board,
    log_scan, get_scan_log, get_lot_control_view,
)

_VIEW_ROLES = (ADMIN, OPERATIONS, SALES, SERVICE, MARKETING, FINANCE)
_MUTATE_ROLES = (ADMIN, OPERATIONS, SERVICE)


def _denied():
    return {"error": "You don't have access to Lot Management"}


def get_lot_map_api(role):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_lot_map()


def get_lot_control_view_api(role, vehicle_id):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_lot_control_view(vehicle_id)


def set_lot_position_api(role, employee_id, vehicle_id, row=None, space=None, section=None, notes=""):
    if role not in _MUTATE_ROLES:
        return _denied()
    return set_lot_position(vehicle_id, employee_id, row=row, space=space, section=section, notes=notes)


def get_lot_position_api(role, vehicle_id):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_lot_position(vehicle_id)


def checkout_key_api(role, employee_id, vehicle_id, holder, notes=""):
    if role not in _MUTATE_ROLES:
        return _denied()
    return checkout_key(vehicle_id, holder, employee_id, notes=notes)


def checkin_key_api(role, employee_id, vehicle_id, notes=""):
    if role not in _MUTATE_ROLES:
        return _denied()
    return checkin_key(vehicle_id, employee_id, notes=notes)


def report_key_missing_api(role, employee_id, vehicle_id, notes=""):
    if role not in _MUTATE_ROLES:
        return _denied()
    return report_key_missing(vehicle_id, employee_id, notes=notes)


def get_key_status_api(role, vehicle_id):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_key_status(vehicle_id)


def get_key_board_api(role):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_key_board()


def report_damage_api(role, employee_id, vehicle_id, severity, description, estimated_cost=None):
    if role not in _MUTATE_ROLES:
        return _denied()
    return report_damage(vehicle_id, severity, description, employee_id, estimated_cost=estimated_cost)


def update_damage_status_api(role, employee_id, report_id, new_status, resolution_notes=""):
    if role not in _MUTATE_ROLES:
        return _denied()
    return update_damage_status(report_id, new_status, employee_id, resolution_notes=resolution_notes)


def list_damage_reports_api(role, vehicle_id=None, status=None):
    if role not in _VIEW_ROLES:
        return _denied()
    return list_damage_reports(vehicle_id=vehicle_id, status=status)


def assign_showroom_api(role, employee_id, vehicle_id, notes=""):
    if role not in _MUTATE_ROLES:
        return _denied()
    return assign_showroom(vehicle_id, employee_id, notes=notes)


def remove_showroom_assignment_api(role, employee_id, vehicle_id):
    if role not in _MUTATE_ROLES:
        return _denied()
    return remove_showroom_assignment(vehicle_id, employee_id)


def get_showroom_board_api(role):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_showroom_board()


def log_scan_api(role, employee_id, vehicle_id, location_note=""):
    if role not in _MUTATE_ROLES:
        return _denied()
    return log_scan(vehicle_id, employee_id, location_note=location_note)


def get_scan_log_api(role, vehicle_id):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_scan_log(vehicle_id)
