"""
core/vehicle_inspection_api.py -- ACL layer for core/vehicle_inspection.py.
Viewing matches the RO Workflow Engine's own broad view set (Sales/Finance
both have a legitimate reason to see a DVI's findings -- Sales when
discussing needed work with a customer, Finance when weighing warranty/
cost). Mutating (starting/updating/completing an inspection, attaching a
photo, converting a finding into a Concern) is narrower, ADMIN/OPERATIONS/
SERVICE only, matching the RO Workflow Engine's own mutate set.
"""

from core.permissions import ADMIN, OPERATIONS, SALES, SERVICE, FINANCE
from core.vehicle_inspection import (
    get_catalog,
    start_inspection,
    update_inspection_item,
    attach_inspection_photo,
    complete_inspection,
    get_inspection,
    create_concerns_from_inspection,
    get_inspection_history_for_vehicle,
)

_VIEW_ROLES = (ADMIN, OPERATIONS, SALES, SERVICE, FINANCE)
_MUTATE_ROLES = (ADMIN, OPERATIONS, SERVICE)


def _denied():
    return {"error": "You don't have access to the Digital Vehicle Inspection tool"}


def get_catalog_api(role):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_catalog()


def get_inspection_api(role, ro_id):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_inspection(ro_id)


def start_inspection_api(role, ro_id, started_by):
    if role not in _MUTATE_ROLES:
        return _denied()
    return start_inspection(ro_id, started_by)


def update_inspection_item_api(role, ro_id, item_key, status, notes, updated_by):
    if role not in _MUTATE_ROLES:
        return _denied()
    return update_inspection_item(ro_id, item_key, status, notes, updated_by)


def attach_inspection_photo_api(role, ro_id, item_key, image_url, uploaded_by, media_type="photo"):
    if role not in _MUTATE_ROLES:
        return _denied()
    return attach_inspection_photo(ro_id, item_key, image_url, uploaded_by, media_type)


def complete_inspection_api(role, ro_id, completed_by):
    if role not in _MUTATE_ROLES:
        return _denied()
    return complete_inspection(ro_id, completed_by)


def create_concerns_from_inspection_api(role, ro_id, item_keys, created_by):
    if role not in _MUTATE_ROLES:
        return _denied()
    return create_concerns_from_inspection(ro_id, item_keys, created_by)


def get_inspection_history_api(role, vehicle_id_or_vin):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_inspection_history_for_vehicle(vehicle_id_or_vin)
