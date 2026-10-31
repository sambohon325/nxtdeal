"""
Thin ACL layer for core/vendor_management.py -- same convention as every other
`*_api.py` module. Vendor/contract data is a back-office concern -- matches
core/administration_menu.py's own established ADMIN/OPERATIONS-only convention
for this whole department.
"""

from core.vendor_management import (
    create_vendor,
    update_vendor,
    set_vendor_status,
    get_vendor,
    list_vendors,
    get_vendor_dashboard,
    VENDOR_CATEGORIES,
    VENDOR_STATUSES,
)
from core.permissions import ADMIN, OPERATIONS

_ROLES = (ADMIN, OPERATIONS)
_FORBIDDEN = {"error": "Admin/Operations role required."}


def create_vendor_api(role, employee_id, name, category, **fields):
    if role not in _ROLES:
        return _FORBIDDEN
    return create_vendor(name, category, employee_id, **fields)


def update_vendor_api(role, employee_id, vendor_id, **fields):
    if role not in _ROLES:
        return _FORBIDDEN
    return update_vendor(vendor_id, employee_id, **fields)


def set_vendor_status_api(role, employee_id, vendor_id, status):
    if role not in _ROLES:
        return _FORBIDDEN
    return set_vendor_status(vendor_id, status, employee_id)


def get_vendor_api(role, vendor_id):
    if role not in _ROLES:
        return _FORBIDDEN
    return get_vendor(vendor_id)


def list_vendors_api(role, category=None, status=None):
    if role not in _ROLES:
        return _FORBIDDEN
    return {"vendors": list_vendors(category=category, status=status)}


def get_vendor_dashboard_api(role):
    if role not in _ROLES:
        return _FORBIDDEN
    return get_vendor_dashboard()
