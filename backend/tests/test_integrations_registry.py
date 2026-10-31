"""
Tests for the integration provider seam (core/integrations_registry.py + _api.py, 2026-07-24).
Run from backend/ with `pytest`.

Covers: the capability catalog + status (everything simulated until an adapter is registered);
dispatchers return honest simulated results; a registered adapter goes live at the same call
site; configuring an intended provider is informational + ADMIN-gated; and the DR-6 delivery /
TBYB flows now route their notifications / deposit / insurance through the seam.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import CUSTOMER, VEHICLE, DEAL
from core.permissions import ADMIN, SALES

from core import integrations_registry as ir
from core import integrations_registry_api as ir_api
from core import delivery_fulfillment as df
from core import dealeros_verify as verify


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    monkeypatch.setenv("DEALEROS_DEMO", "1")
    ledger.reset()
    ir._ADAPTERS.clear()
    yield
    ledger.reset()
    ir._ADAPTERS.clear()


def test_status_lists_every_capability_simulated():
    status = ir.provider_status()
    caps = {p["capability"] for p in status["providers"]}
    # Self-maintaining against the capability catalog (was a hardcoded 5-set that drifted
    # as banking/ads were added -- compare to the source of truth instead).
    assert caps == set(ir.CAPABILITIES)
    assert all(p["mode"] == "simulated" for p in status["providers"])
    assert status["live_count"] == 0 and status["simulated_count"] == len(ir.CAPABILITIES)


def test_dispatchers_return_simulated_results():
    n = ir.send_notification("CUST-1", "delivery_scheduled")
    assert n["simulated"] is True and n["event"] == "delivery_scheduled" and n["channels"]
    d = ir.charge_deposit(500)
    assert d["simulated"] is True and d["amount"] == 500 and d["status"] == "collected"
    i = ir.verify_insurance_policy("POL-1")
    assert i["simulated"] is True and i["verified"] is True


def test_registered_adapter_goes_live():
    ir.register_adapter("notifications", lambda to, event, channels: {"live": True, "to": to})
    assert ir.is_live("notifications") is True
    n = ir.send_notification("CUST-1", "x")
    assert n.get("live") is True
    assert ir.provider_status_one("notifications")["mode"] == "live"


def test_configure_provider_is_informational_and_admin_only():
    assert "error" in ir_api.configure_provider_api(SALES, "EMP-1", "payments", "Stripe")
    ok = ir_api.configure_provider_api(ADMIN, "EMP-1", "payments", "Stripe")
    assert ok["status"]["configured_provider"] == "Stripe"
    # still simulated -- naming a provider doesn't fake a live connection
    assert ok["status"]["mode"] == "simulated"
    assert "error" in ir_api.configure_provider_api(ADMIN, "EMP-1", "nope", "X")


def test_delivery_notifications_route_through_seam():
    ledger.add_entity(Entity(id="CUST-1", entity_type=CUSTOMER, attributes={"Name": "P"}))
    ledger.add_entity(Entity(id="VEH-1", entity_type=VEHICLE, attributes={"Make": "Ford"}))
    ledger.add_entity(Entity(id="DEAL-1", entity_type=DEAL,
                             attributes={"customer_id": "CUST-1", "vehicle_id": "VEH-1", "status": "contract"}))
    d = df.schedule_delivery("DEAL-1", "store_pickup", "2026-08-01T10:00:00Z", "EMP-1")["delivery"]
    notif = d["status_timeline"][0]["notification"]
    assert notif["capability"] == "notifications" and notif["simulated"] is True
    assert notif["provider"]  # carries the (recommended) provider label


def test_tbyb_deposit_and_insurance_route_through_seam():
    ledger.add_entity(Entity(id="CUST-1", entity_type=CUSTOMER, attributes={"Name": "P"}))
    ledger.add_entity(Entity(id="VEH-1", entity_type=VEHICLE, attributes={"Make": "Ford"}))
    started = verify.start_verification(email="p@x.com", phone="555-1")
    vid = started["verification"]["id"]
    verify.confirm_email_code(vid, verify.request_email_code(vid)["dev_code"])
    verify.confirm_sms_code(vid, verify.request_sms_code(vid)["dev_code"])
    verify.submit_identity(vid, "D1")
    tid = df.start_tbyb("VEH-1", "CUST-1", "EMP-1", verification_id=vid)["tbyb"]["id"]
    ins = df.verify_insurance(tid, "POL-9", "EMP-1")["tbyb"]["insurance"]
    assert ins["simulated"] is True and ins["provider"]
    dep = df.collect_deposit(tid, "EMP-1")["tbyb"]["deposit"]
    assert dep["simulated"] is True and dep["provider"] and dep["amount"] == 500


def test_provider_status_is_read_only_and_registration_is_not_approval(monkeypatch):
    from copy import deepcopy
    before = deepcopy(ledger.get_all())
    def unexpected_save(*args):
        raise AssertionError("Reading provider status must not write settings")
    monkeypatch.setattr(ir, "save_graph", unexpected_save)
    ir.register_adapter("notifications", lambda *args, **kwargs: {"sent": True})
    status = ir.provider_status()
    notification = next(row for row in status["providers"] if row["capability"] == "notifications")
    assert notification["adapter_registered"] is True
    assert notification["oem_approval_status"] == "not_verified_by_registry"
    assert notification["production_readiness_status"] == "not_verified_by_registry"
    assert notification["authorization_evidence_status"] == "not_verified_by_registry"
    assert ledger.get_all() == before
