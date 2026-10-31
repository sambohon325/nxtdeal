"""
Module-adoption funnel signal (Freemium roadmap, Phase 4, 2026-08-03). The tenant's contribution to
the Hub's extended Dealer Lifecycle Funnel: Foundation Signup -> Foundation Active -> Module Adoption.
Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import VEHICLE
from core import module_adoption as ma
from core import entitlements as ent


@pytest.fixture(autouse=True)
def fresh():
    ledger.reset()
    yield
    ledger.reset()


def test_reference_default_is_module_adoption():
    # default reference profile = all paid modules on = free-to-paid already happened
    ad = ma.compute_module_adoption()
    assert ad["funnel_stage"] == "module_adoption"
    assert ad["free_to_paid"] is True
    assert ad["attach_rate"] == 1.0
    assert ad["paid_module_count"] == len(ent.PAID_MODULES)


def test_foundation_no_data_is_signup():
    ent.set_profile("foundation", "admin")  # no paid modules, no data
    ad = ma.compute_module_adoption()
    assert ad["funnel_stage"] == "foundation_signup"
    assert ad["free_to_paid"] is False
    assert ad["foundation_active"] is False


def test_foundation_with_data_is_active():
    ent.set_profile("foundation", "admin")
    ledger.add_entity(Entity(id="VEH-1", entity_type=VEHICLE, attributes={"Make": "Ford"}))
    ad = ma.compute_module_adoption()
    assert ad["funnel_stage"] == "foundation_active"
    assert ad["foundation_active"] is True
    assert ad["free_to_paid"] is False


def test_one_paid_module_flips_to_adoption():
    ent.set_profile("foundation", "admin")
    ledger.add_entity(Entity(id="VEH-1", entity_type=VEHICLE, attributes={}))
    ent.set_module("sales", True, "admin", level="professional")
    ad = ma.compute_module_adoption()
    assert ad["funnel_stage"] == "module_adoption"
    assert ad["active_paid_modules"] == ["sales"]
    assert 0 < ad["attach_rate"] < 1.0
    sales = next(m for m in ad["modules"] if m["module"] == "sales")
    assert sales["active"] is True and sales["level"] == "professional"


def test_snapshot_equals_compute():
    assert ma.build_module_adoption_snapshot() == ma.compute_module_adoption()
