"""
core/delivery_fulfillment_api.py -- API layer for Home Delivery + Try Before You Buy
(2026-07-24, DR-6). Viewing dashboards/records is open to any authenticated role; scheduling
and advancing deliveries + running the TBYB workflow are the operations/sales-desk roles; the
TBYB program config is ADMIN.
"""

from core.permissions import ADMIN, OPERATIONS, SALES
from core import delivery_fulfillment as df

_OPS_ROLES = (ADMIN, OPERATIONS, SALES)


def get_fulfillment_dashboard_api(role):
    return df.fulfillment_dashboard()


# ---- Home delivery ----

def list_deliveries_api(role, status=None, mode=None, deal_id=None, limit=100):
    return df.list_deliveries(status=status, mode=mode, deal_id=deal_id, limit=limit)


def get_delivery_api(role, delivery_id):
    view = df.get_delivery(delivery_id)
    return view if view else {"error": f"No delivery {delivery_id}"}


def schedule_delivery_api(role, actor_id, deal_id, mode, window_start,
                          window_end=None, address=None, driver_id=None, notes=""):
    if role not in _OPS_ROLES:
        return {"error": "Not permitted to schedule a delivery"}
    return df.schedule_delivery(deal_id, mode, window_start, actor_id,
                                window_end=window_end, address=address,
                                driver_id=driver_id, notes=notes)


def assign_driver_api(role, actor_id, delivery_id, driver_id):
    if role not in _OPS_ROLES:
        return {"error": "Not permitted to assign a driver"}
    return df.assign_driver(delivery_id, driver_id, actor_id)


def update_delivery_status_api(role, actor_id, delivery_id, status):
    if role not in _OPS_ROLES:
        return {"error": "Not permitted to update a delivery"}
    return df.update_delivery_status(delivery_id, status, actor_id)


# ---- Try Before You Buy ----

def get_tbyb_program_api(role):
    return {"program": df.get_tbyb_program()}


def set_tbyb_program_api(admin_role, admin_id, patch):
    if admin_role != ADMIN:
        return {"error": "Admin role required to change the Try Before You Buy program"}
    return df.set_tbyb_program(patch, admin_id)


def list_tbyb_api(role, status=None, limit=100):
    return df.list_tbyb(status=status, limit=limit)


def get_tbyb_api(role, tbyb_id):
    view = df.get_tbyb(tbyb_id)
    return view if view else {"error": f"No TBYB {tbyb_id}"}


def start_tbyb_api(role, actor_id, vehicle_id, customer_id, deal_id=None, verification_id=None):
    if role not in _OPS_ROLES:
        return {"error": "Not permitted to start a Try Before You Buy"}
    return df.start_tbyb(vehicle_id, customer_id, actor_id,
                         deal_id=deal_id, verification_id=verification_id)


def tbyb_action_api(role, actor_id, tbyb_id, action, **kwargs):
    """Dispatch a TBYB workflow step. action in: insurance, deposit, release, decision,
    inspect, recondition, reinstate."""
    if role not in _OPS_ROLES:
        return {"error": "Not permitted to run the Try Before You Buy workflow"}
    if action == "insurance":
        return df.verify_insurance(tbyb_id, kwargs.get("policy_ref"), actor_id)
    if action == "deposit":
        return df.collect_deposit(tbyb_id, actor_id, amount=kwargs.get("amount"))
    if action == "release":
        return df.release_vehicle(tbyb_id, kwargs.get("odometer_out"), actor_id)
    if action == "decision":
        return df.record_decision(tbyb_id, kwargs.get("decision"), actor_id,
                                  odometer_in=kwargs.get("odometer_in"))
    if action == "inspect":
        return df.inspect_return(tbyb_id, kwargs.get("findings"), actor_id)
    if action == "recondition":
        return df.recondition(tbyb_id, kwargs.get("notes"), actor_id)
    if action == "reinstate":
        return df.reinstate_inventory(tbyb_id, actor_id)
    return {"error": f"Unknown TBYB action '{action}'"}
