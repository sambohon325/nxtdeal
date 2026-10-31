"""
core/vin_decoder_api.py -- ACL layer for NXTDeal VIN Intelligence (Phase 1).
Same thin validate-then-call pattern every other core/*_api.py module in this
codebase already follows (core/pricing_desk_api.py's own established shape,
mirrored directly).

Viewing (decoding a raw VIN, or reading a vehicle's already-stored decode) is
broad -- every department Sam's own kickoff spec named actually wants this:
Inventory (auto-populate a new unit), Sales (trade-in appraisal), Service
(warranty/recall lookup context), Finance (collateral validation). Applying a
decode to a Vehicle -- a real mutation, even though it only ever backfills a
currently-blank field -- is narrower, matching the mutate-role convention
core/inventory_aging.py/core/pricing_desk_api.py already established for
this same Vehicle entity (ADMIN/OPERATIONS/SALES, since Sales legitimately
adds a trade-in vehicle and Inventory/Operations legitimately intake new
stock).
"""

from core.permissions import ADMIN, OPERATIONS, SALES, SERVICE, MARKETING, FINANCE
from core.vin_decoder import (
    decode_vin,
    get_vehicle_vin_decode,
    check_vehicle_vin_match,
    apply_decode_to_vehicle,
    bulk_apply_decode,
)

_VIEW_ROLES = (ADMIN, OPERATIONS, SALES, SERVICE, MARKETING, FINANCE)
_MUTATE_ROLES = (ADMIN, OPERATIONS, SALES)


def _denied():
    return {"error": "You don't have access to NXTDeal VIN Intelligence."}


def decode_vin_api(role, vin, attempt_live=True):
    if role not in _VIEW_ROLES:
        return _denied()
    return decode_vin(vin, attempt_live=attempt_live)


def get_vehicle_vin_decode_api(role, vehicle_id):
    if role not in _VIEW_ROLES:
        return _denied()
    result, error = get_vehicle_vin_decode(vehicle_id)
    if error:
        return {"error": error}
    if result is None:
        return {"vehicle_id": vehicle_id, "vin_decode": None, "note": "This vehicle has not been decoded yet."}
    return {"vehicle_id": vehicle_id, "vin_decode": result}


def check_vehicle_vin_match_api(role, vehicle_id, attempt_live=True):
    if role not in _VIEW_ROLES:
        return _denied()
    result, error = check_vehicle_vin_match(vehicle_id, attempt_live=attempt_live)
    if error:
        return {"error": error}
    return result


def apply_decode_to_vehicle_api(role, employee_id, vehicle_id, attempt_live=True):
    if role not in _MUTATE_ROLES:
        return _denied()
    result, error = apply_decode_to_vehicle(vehicle_id, employee_id, attempt_live=attempt_live)
    if error:
        return {"error": error}
    return result


def bulk_apply_decode_api(role, employee_id, vehicle_ids=None, attempt_live=True, limit=100):
    if role not in _MUTATE_ROLES:
        return _denied()
    return bulk_apply_decode(employee_id, vehicle_ids=vehicle_ids, attempt_live=attempt_live, limit=min(limit, 200))
