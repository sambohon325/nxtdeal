"""
Tests for Home Delivery + Try Before You Buy (core/delivery_fulfillment.py + _api.py) --
2026-07-24, DR-6. Run from backend/ with `pytest`.

Covers: scheduling deliveries by mode (home delivery requires an address); forward-only status
flow with simulated notifications; the delivery board; the TBYB program config; the full TBYB
lifecycle (identity gate -> insurance -> deposit -> release -> keep/return -> inspect ->
recondition -> reinstate) with the vehicle's on_trial flag; and the API role gates.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import VEHICLE, CUSTOMER, DEAL
from core.permissions import ADMIN, SALES, MARKETING

from core import delivery_fulfillment as df
from core import delivery_fulfillment_api as df_api
from core import dealeros_verify as verify


@pytest.fixture(autouse=True)
def fresh_ledger(monkeypatch):
    monkeypatch.setenv("DEALEROS_DEMO", "1")
    ledger.reset()
    yield
    ledger.reset()


def _seed_deal():
    ledger.add_entity(Entity(id="CUST-1", entity_type=CUSTOMER, attributes={"Name": "Pat"}))
    ledger.add_entity(Entity(id="VEH-1", entity_type=VEHICLE, attributes={"Make": "Ford", "Model": "F-150", "Price": 40000}))
    ledger.add_entity(Entity(id="DEAL-1", entity_type=DEAL,
                             attributes={"customer_id": "CUST-1", "vehicle_id": "VEH-1", "status": "contract"}))
    return "DEAL-1"


# ------------------------------------------------------------------- home delivery

def test_home_delivery_requires_address():
    _seed_deal()
    assert "error" in df.schedule_delivery("DEAL-1", "home_delivery", "2026-08-01T10:00:00Z", "EMP-1")
    ok = df.schedule_delivery("DEAL-1", "home_delivery", "2026-08-01T10:00:00Z", "EMP-1", address="1 Main St")
    assert ok["delivery"]["mode"] == "home_delivery" and ok["delivery"]["status"] == "scheduled"


def test_store_pickup_no_address_needed():
    _seed_deal()
    ok = df.schedule_delivery("DEAL-1", "store_pickup", "2026-08-01T10:00:00Z", "EMP-1")
    assert ok["delivery"]["mode"] == "store_pickup"
    # a scheduled notification is queued (simulated)
    assert ok["delivery"]["status_timeline"][0]["notification"]["simulated"] is True


def test_delivery_status_is_forward_only():
    _seed_deal()
    d = df.schedule_delivery("DEAL-1", "home_delivery", "2026-08-01T10:00:00Z", "EMP-1", address="1 Main St")["delivery"]
    assert "error" in df.update_delivery_status(d["id"], "delivered", "EMP-1")  # can't skip
    assert df.update_delivery_status(d["id"], "preparing", "EMP-1")["delivery"]["status"] == "preparing"
    assert df.update_delivery_status(d["id"], "out_for_delivery", "EMP-1")["delivery"]["status"] == "out_for_delivery"
    got = df.update_delivery_status(d["id"], "delivered", "EMP-1")["delivery"]
    assert got["status"] == "delivered"
    assert got["status_timeline"][-1]["notification"]["event"] == "delivery_delivered"


def test_delivery_board_flags_unassigned_home():
    _seed_deal()
    df.schedule_delivery("DEAL-1", "home_delivery", "2026-08-01T10:00:00Z", "EMP-1", address="1 Main St")
    board = df.delivery_board()
    assert board["total"] == 1
    assert board["home_deliveries_without_driver"] == 1
    assert board["by_mode"]["home_delivery"] == 1


# ------------------------------------------------------------------------ TBYB

def test_tbyb_program_config():
    p = df.get_tbyb_program()
    assert p["max_hours"] == 48 and p["deposit_amount"] == 500
    out = df.set_tbyb_program({"max_hours": 24, "max_miles": 100}, "EMP-1")
    assert out["program"]["max_hours"] == 24 and out["program"]["max_miles"] == 100
    assert "error" in df.set_tbyb_program({"max_hours": 0}, "EMP-1")


def _identity_verified_token_customer():
    """A Verify session at Identity Verified + a matching Customer to attach the trial to."""
    started = verify.start_verification(email="p@x.com", phone="555-111-2222")
    vid = started["verification"]["id"]
    verify.confirm_email_code(vid, verify.request_email_code(vid)["dev_code"])
    verify.confirm_sms_code(vid, verify.request_sms_code(vid)["dev_code"])
    verify.submit_identity(vid, "D1234567")
    return vid


def test_tbyb_requires_identity():
    ledger.add_entity(Entity(id="CUST-1", entity_type=CUSTOMER, attributes={"Name": "Pat"}))
    ledger.add_entity(Entity(id="VEH-1", entity_type=VEHICLE, attributes={"Make": "Ford", "Odometer": 12000}))
    # no verification -> blocked
    assert "error" in df.start_tbyb("VEH-1", "CUST-1", "EMP-1")
    vid = _identity_verified_token_customer()
    ok = df.start_tbyb("VEH-1", "CUST-1", "EMP-1", verification_id=vid)
    assert ok["tbyb"]["status"] == "created"


def test_tbyb_full_return_lifecycle():
    ledger.add_entity(Entity(id="CUST-1", entity_type=CUSTOMER, attributes={"Name": "Pat"}))
    ledger.add_entity(Entity(id="VEH-1", entity_type=VEHICLE, attributes={"Make": "Ford"}))
    vid = _identity_verified_token_customer()
    t = df.start_tbyb("VEH-1", "CUST-1", "EMP-1", verification_id=vid)["tbyb"]
    tid = t["id"]

    # ordering is enforced
    assert "error" in df.collect_deposit(tid, "EMP-1")  # insurance first
    assert df.verify_insurance(tid, "POL-123", "EMP-1")["tbyb"]["status"] == "insurance_verified"
    dep = df.collect_deposit(tid, "EMP-1")
    assert dep["tbyb"]["status"] == "deposit_collected"
    assert dep["tbyb"]["deposit"]["amount"] == 500 and dep["tbyb"]["deposit"]["simulated"] is True

    rel = df.release_vehicle(tid, 12000, "EMP-1")
    assert rel["tbyb"]["status"] == "out"
    assert ledger.get_entity("VEH-1").attributes["on_trial"] is True

    dec = df.record_decision(tid, "return", "EMP-1", odometer_in=12180)
    assert dec["tbyb"]["status"] == "returned"
    assert dec["tbyb"]["return"]["miles_driven"] == 180

    assert df.inspect_return(tid, "minor scuff", "EMP-1")["tbyb"]["status"] == "inspected"
    assert df.recondition(tid, "buffed", "EMP-1")["tbyb"]["status"] == "reconditioned"
    fin = df.reinstate_inventory(tid, "EMP-1")
    assert fin["tbyb"]["status"] == "reinstated"
    assert ledger.get_entity("VEH-1").attributes["on_trial"] is False


def test_tbyb_keep_is_terminal():
    ledger.add_entity(Entity(id="CUST-1", entity_type=CUSTOMER, attributes={"Name": "Pat"}))
    ledger.add_entity(Entity(id="VEH-1", entity_type=VEHICLE, attributes={"Make": "Ford"}))
    vid = _identity_verified_token_customer()
    tid = df.start_tbyb("VEH-1", "CUST-1", "EMP-1", verification_id=vid)["tbyb"]["id"]
    df.verify_insurance(tid, "POL-1", "EMP-1")
    df.collect_deposit(tid, "EMP-1")
    df.release_vehicle(tid, 100, "EMP-1")
    kept = df.record_decision(tid, "keep", "EMP-1", odometer_in=150)
    assert kept["tbyb"]["status"] == "kept"
    assert ledger.get_entity("VEH-1").attributes["on_trial"] is False
    # no further workflow after keep
    assert "error" in df.inspect_return(tid, "x", "EMP-1")


# ------------------------------------------------------------------------- API gates

def test_customer_self_service_delivery_wrapper():
    # A credit-verified customer schedules their own delivery through digital_retail.
    from core import digital_retail as dr
    from core import execution_modes as xm

    ledger.add_entity(Entity(id="VEH-9", entity_type=VEHICLE,
                             attributes={"Make": "Ford", "Model": "F-150", "Price": 40000, "Cost": 34000}))
    for wf in ("desking", "credit", "delivery"):
        xm.set_execution_mode(wf, "hybrid", "EMP-1")

    vid = _identity_verified_token_customer()
    token = ledger.get_entity(vid).attributes["session_token"]

    deal_id = dr.start_deal(token, "VEH-9")["deal"]["id"]
    # not credit-verified yet -> delivery blocked
    blocked = dr.schedule_delivery(token, deal_id, "home_delivery", "2026-08-01T10:00:00Z", address="1 Main St")
    assert "error" in blocked and "Credit Verified" in blocked["error"]

    dr.apply_credit(token, deal_id, {"employment_status": "employed"}, monthly_income=5000)
    ok = dr.schedule_delivery(token, deal_id, "home_delivery", "2026-08-01T10:00:00Z", address="1 Main St")
    assert ok["delivery"]["mode"] == "home_delivery"
    assert ok["delivery"]["created_by"] == verify.CUSTOMER_SENTINEL


def test_api_role_gates():
    _seed_deal()
    # scheduling is ops/sales; MARKETING blocked
    assert "error" in df_api.schedule_delivery_api(MARKETING, "EMP-9", "DEAL-1", "store_pickup", "2026-08-01T10:00:00Z")
    ok = df_api.schedule_delivery_api(SALES, "EMP-1", "DEAL-1", "store_pickup", "2026-08-01T10:00:00Z")
    assert "delivery" in ok
    # program config is ADMIN
    assert "error" in df_api.set_tbyb_program_api(SALES, "EMP-1", {"max_hours": 12})
    assert df_api.set_tbyb_program_api(ADMIN, "EMP-1", {"max_hours": 12})["program"]["max_hours"] == 12
    # view is open to any role
    assert "delivery" in df_api.get_fulfillment_dashboard_api(MARKETING)


# ---- Delivery <-> ops Appointment sync (Polish-1) ------------------------------------

def test_delivery_creates_and_syncs_ops_appointment():
    from core.entity_types import APPOINTMENT
    from core.appointments import get_appointment
    _seed_deal()  # DEAL-1 in 'contract' status
    d = df.schedule_delivery("DEAL-1", "home_delivery", "2026-08-01T10:00:00Z", "EMP-1", address="1 Main St")["delivery"]
    appt_id = d["ops_appointment_id"]
    assert appt_id  # a paired ops appointment was created (deal is contract)
    appt = get_appointment(appt_id)
    assert appt.entity_type == APPOINTMENT and appt.attributes.get("appointment_type") == "delivery"
    assert appt.attributes.get("status") == "scheduled"

    # advancing to delivered completes the appointment
    df.update_delivery_status(d["id"], "preparing", "EMP-1")
    df.update_delivery_status(d["id"], "out_for_delivery", "EMP-1")
    df.update_delivery_status(d["id"], "delivered", "EMP-1")
    assert get_appointment(appt_id).attributes.get("status") == "completed"


def test_delivery_before_contract_has_no_appointment_but_still_works():
    from core.entities import Entity
    from core.entity_types import CUSTOMER, VEHICLE, DEAL
    ledger.add_entity(Entity(id="CUST-2", entity_type=CUSTOMER, attributes={"Name": "Q"}))
    ledger.add_entity(Entity(id="VEH-2", entity_type=VEHICLE, attributes={"Make": "Ford"}))
    ledger.add_entity(Entity(id="DEAL-2", entity_type=DEAL,
                             attributes={"customer_id": "CUST-2", "vehicle_id": "VEH-2", "status": "financing"}))
    d = df.schedule_delivery("DEAL-2", "store_pickup", "2026-08-01T10:00:00Z", "EMP-1")["delivery"]
    assert d["ops_appointment_id"] is None  # ops helper only takes contract/funded -> honest gap
    assert d["status"] == "scheduled"


def test_cancel_delivery_cancels_appointment():
    from core.appointments import get_appointment
    _seed_deal()
    d = df.schedule_delivery("DEAL-1", "home_delivery", "2026-08-01T10:00:00Z", "EMP-1", address="1 Main St")["delivery"]
    appt_id = d["ops_appointment_id"]
    df.cancel_delivery(d["id"], "EMP-1")
    assert get_appointment(appt_id).attributes.get("status") == "cancelled"
