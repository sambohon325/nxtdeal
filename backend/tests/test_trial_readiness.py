"""Trial/deposit boundaries must not turn sample provider results into authority."""
from copy import deepcopy

import pytest

from core import delivery_fulfillment as trials, integrations_registry as providers
from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import TRY_BEFORE_YOU_BUY, VEHICLE


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.delenv("DEALEROS_DEMO", raising=False)
    ledger.reset()
    monkeypatch.setattr(providers, "_ADAPTERS", {})
    yield
    ledger.reset()


@pytest.mark.parametrize("demo", [False, True])
@pytest.mark.parametrize("capability,dispatch,args", [
    ("payments", providers.charge_deposit, (500,)),
    ("insurance", providers.verify_insurance_policy, ("POL-SAMPLE",)),
])
def test_registration_does_not_authorize_external_dispatch(monkeypatch, demo, capability, dispatch, args):
    monkeypatch.setenv("DEALEROS_DEMO", "1" if demo else "0")
    providers.register_adapter(capability, lambda *a: pytest.fail("Unreviewed adapter called"))
    assert dispatch(*args)["blocked"] is True


@pytest.mark.parametrize("amount", [None, "bad", 0, -1, float("nan"), float("inf")])
def test_invalid_demo_deposit_is_not_collected(monkeypatch, amount):
    monkeypatch.setenv("DEALEROS_DEMO", "1")
    assert "error" in providers.charge_deposit(amount)


def seed(status):
    trial = Entity("TRIAL-TEST", TRY_BEFORE_YOU_BUY, {
        "status": status, "vehicle_id": "VEH-TEST", "program": {"deposit_amount": 500},
        "insurance": {"simulated": True}, "deposit": {"simulated": True}, "history": [],
    })
    vehicle = Entity("VEH-TEST", VEHICLE, {"on_trial": False})
    ledger.add_entity(trial)
    ledger.add_entity(vehicle)
    return trial, vehicle


@pytest.mark.parametrize("status,action", [
    ("created", lambda: trials.verify_insurance("TRIAL-TEST", "POL-SAMPLE", "EMP-TEST")),
    ("insurance_verified", lambda: trials.collect_deposit("TRIAL-TEST", "EMP-TEST")),
    ("deposit_collected", lambda: trials.release_vehicle("TRIAL-TEST", 100, "EMP-TEST")),
])
def test_production_trial_cannot_advance_or_change_inventory(status, action):
    trial, vehicle = seed(status)
    before = deepcopy((trial.attributes, vehicle.attributes))
    assert action()["blocked"] is True
    assert (trial.attributes, vehicle.attributes) == before


@pytest.mark.parametrize("payload", [{"status": "declined"}, {"status": "pending"}, None, {"error": "failure"}])
def test_unconfirmed_deposit_leaves_trial_unchanged(monkeypatch, payload):
    trial, _ = seed("insurance_verified")
    before = deepcopy(trial.attributes)
    monkeypatch.setattr(providers, "charge_deposit", lambda *a, **kw: payload)
    assert "error" in trials.collect_deposit(trial.id, "EMP-TEST")
    assert trial.attributes == before


def test_repeated_deposit_does_not_dispatch(monkeypatch):
    seed("deposit_collected")
    monkeypatch.setattr(providers, "charge_deposit", lambda *a, **kw: pytest.fail("Repeated charge"))
    assert "error" in trials.collect_deposit("TRIAL-TEST", "EMP-TEST")
