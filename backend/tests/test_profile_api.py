"""
Tests for core/profile_api.py — the entity 360 profile view (GET /profile/{entity_id}).
Covers dispatch by entity type (Customer/Employee/Vehicle get a dedicated view, everything
else falls back to entity + direct relationships) and, most importantly, that RBAC
filtering applies to every entity *nested inside* a profile, not just the top-level one —
a role that can't see finance contracts directly shouldn't see them smuggled into a
customer's profile. Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.relationships import Relationship

from core.entity_types import (
    CUSTOMER, EMPLOYEE, VEHICLE, LEAD, FINANCE_CONTRACT, SERVICE_RECORD, DOCUMENT,
)

from core.relationship_types import (
    FINANCED_BY, COVERS, AUTHORIZED, HAS_DOCUMENT, ASSIGNED_TO, INTERESTED_IN,
)

from core.permissions import ADMIN, SALES, SERVICE, MARKETING

from core.profile_api import get_profile


@pytest.fixture(autouse=True)
def fresh_ledger():

    ledger.reset()

    yield

    ledger.reset()


def _seed_customer_profile():

    ledger.add_entity(Entity(id="CUS-1", entity_type=CUSTOMER, attributes={"Name": "Jane"}))
    ledger.add_entity(Entity(id="FIN-1", entity_type=FINANCE_CONTRACT, attributes={}))
    ledger.add_entity(Entity(id="VEH-1", entity_type=VEHICLE, attributes={}))
    ledger.add_entity(Entity(id="SRV-1", entity_type=SERVICE_RECORD, attributes={}))
    ledger.add_entity(Entity(id="DOC-1", entity_type=DOCUMENT, attributes={}))

    ledger.add_relationship(Relationship("CUS-1", "FIN-1", FINANCED_BY))
    ledger.add_relationship(Relationship("FIN-1", "VEH-1", COVERS))
    ledger.add_relationship(Relationship("CUS-1", "SRV-1", AUTHORIZED))
    ledger.add_relationship(Relationship("CUS-1", "DOC-1", HAS_DOCUMENT))


def test_customer_profile_admin_sees_everything():

    _seed_customer_profile()

    profile = get_profile(ADMIN, "CUS-1")

    assert profile["entity_type"] == CUSTOMER
    assert profile["customer"]["id"] == "CUS-1"
    assert [f["id"] for f in profile["finances"]] == ["FIN-1"]
    assert [v["id"] for v in profile["vehicles"]] == ["VEH-1"]
    assert [s["id"] for s in profile["service_records"]] == ["SRV-1"]
    assert [d["id"] for d in profile["documents"]] == ["DOC-1"]


def test_customer_profile_sales_role_filters_finance_and_service():
    """SALES can see CUSTOMER/VEHICLE/DOCUMENT but not FINANCE_CONTRACT/SERVICE_RECORD
    per core/permissions.py's ENTITY_ACCESS — the profile must reflect that even though
    the customer itself is visible."""

    _seed_customer_profile()

    profile = get_profile(SALES, "CUS-1")

    assert profile["customer"]["id"] == "CUS-1"
    assert profile["finances"] == []
    assert profile["service_records"] == []
    assert [v["id"] for v in profile["vehicles"]] == ["VEH-1"]
    assert [d["id"] for d in profile["documents"]] == ["DOC-1"]


def test_employee_profile_requires_admin():
    """EMPLOYEE has no ENTITY_ACCESS entry at all — only ADMIN's bypass grants access,
    matching how GET /entity/{id} already treats employee lookups today."""

    ledger.add_entity(Entity(id="EMP-1", entity_type=EMPLOYEE, attributes={"Name": "Rep"}))
    ledger.add_entity(Entity(id="LEAD-1", entity_type=LEAD, attributes={}))
    ledger.add_relationship(Relationship("EMP-1", "LEAD-1", ASSIGNED_TO))

    denied = get_profile(SALES, "EMP-1")
    assert denied == {"error": "Forbidden: your role cannot access this entity type"}

    allowed = get_profile(ADMIN, "EMP-1")
    assert allowed["entity_type"] == EMPLOYEE
    assert allowed["employee"]["id"] == "EMP-1"
    assert [l["id"] for l in allowed["leads"]] == ["LEAD-1"]


def test_vehicle_profile_dispatch():

    ledger.add_entity(Entity(id="VEH-2", entity_type=VEHICLE, attributes={}))
    ledger.add_entity(Entity(id="CUS-2", entity_type=CUSTOMER, attributes={}))

    ledger.add_relationship(Relationship("CUS-2", "VEH-2", "OWNS"))

    profile = get_profile(ADMIN, "VEH-2")

    assert profile["entity_type"] == VEHICLE
    assert profile["vehicle"]["id"] == "VEH-2"
    assert [o["id"] for o in profile["owners"]] == ["CUS-2"]


def test_unknown_entity_returns_error():

    assert get_profile(ADMIN, "DOES-NOT-EXIST") == {"error": "Entity not found"}


def test_fallback_profile_for_entity_type_without_dedicated_view():
    """LEAD has no get_*_360() of its own — falls back to entity + direct relationships,
    still filtered per-relationship by can_access_entity."""

    ledger.add_entity(Entity(id="LEAD-2", entity_type=LEAD, attributes={}))
    ledger.add_entity(Entity(id="VEH-3", entity_type=VEHICLE, attributes={}))
    ledger.add_relationship(Relationship("LEAD-2", "VEH-3", INTERESTED_IN))

    profile = get_profile(MARKETING, "LEAD-2")

    assert profile["entity_type"] == LEAD
    assert profile["entity"]["id"] == "LEAD-2"
    assert len(profile["relationships"]) == 1
    assert profile["relationships"][0]["entity"]["id"] == "VEH-3"
    assert profile["relationships"][0]["relationship"] == INTERESTED_IN


def test_top_level_forbidden_for_disallowed_role():
    """SERVICE isn't in LEAD's ENTITY_ACCESS list — denied before ever reaching the
    fallback branch."""

    ledger.add_entity(Entity(id="LEAD-3", entity_type=LEAD, attributes={}))

    assert get_profile(SERVICE, "LEAD-3") == {
        "error": "Forbidden: your role cannot access this entity type"
    }
