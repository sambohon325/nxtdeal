"""
Tests for core/lead_conversion.py / core/lead_conversion_api.py -- the real, live
Lead -> Customer conversion mechanism (Sales sub-menu spec, session 92 follow-up),
using the pre-existing BECAME relationship. Run from backend/ with `pytest`.

Covers: convert_lead_to_customer()'s not-found/wrong-entity-type rejection, the
happy path (real Customer created from the Lead's own real attributes, CreditScore
deliberately absent, ConvertedFromLeadID/ConvertedAt/ConvertedBy stamped, a real
BECAME relationship added, the Lead's own ConvertedCustomerID/ConvertedAt attributes
updated, the customer registered so registry.find_customer resolves it), the
already-converted-with-a-still-real-customer short-circuit (returns the existing
customer_id without creating a duplicate), the edge case where ConvertedCustomerID
points at a customer that no longer exists (falls through and re-converts rather
than erroring), and the core/lead_conversion_api.py ACL layer
(ADMIN/OPERATIONS/SALES/MARKETING allowed, FINANCE/SERVICE denied).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger, registry
from core.entities import Entity
from core.entity_types import LEAD, CUSTOMER
from core.relationship_types import BECAME
from core import lead_conversion
from core import lead_conversion_api
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, FINANCE, SERVICE


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    monkeypatch.setattr(lead_conversion, "save_graph", lambda filepath: None)


def _make_lead(lead_id="LEAD-1", **extra):
    attrs = {
        "FirstName": "Jordan", "LastName": "Rivera", "Email": "jordan@example.com",
        "Phone": "555-1234", "City": "Kansas City", "State": "MO",
    }
    attrs.update(extra)
    ledger.add_entity(Entity(id=lead_id, entity_type=LEAD, attributes=attrs))
    return lead_id


def _became_targets(lead_id):
    return [
        r.target_id for r in ledger.get_relationships()
        if r.source_id == lead_id and r.relationship_type == BECAME
    ]


class TestConvertLeadToCustomer:

    def test_lead_not_found(self):
        result = lead_conversion.convert_lead_to_customer("LEAD-BOGUS", "EMP-1")
        assert result == {"error": "Lead 'LEAD-BOGUS' not found"}

    def test_wrong_entity_type_treated_as_not_found(self):
        ledger.add_entity(Entity(id="LEAD-1", entity_type=CUSTOMER, attributes={}))
        result = lead_conversion.convert_lead_to_customer("LEAD-1", "EMP-1")
        assert result == {"error": "Lead 'LEAD-1' not found"}

    def test_happy_path_creates_real_customer_from_lead_attributes(self):
        _make_lead("LEAD-1")

        result = lead_conversion.convert_lead_to_customer("LEAD-1", "EMP-9")

        assert isinstance(result, Entity)
        assert result.entity_type == CUSTOMER
        assert result.attributes["FirstName"] == "Jordan"
        assert result.attributes["LastName"] == "Rivera"
        assert result.attributes["Email"] == "jordan@example.com"
        assert result.attributes["Phone"] == "555-1234"
        assert result.attributes["City"] == "Kansas City"
        assert result.attributes["State"] == "MO"
        assert result.attributes["ConvertedFromLeadID"] == "LEAD-1"
        assert result.attributes["ConvertedBy"] == "EMP-9"
        assert result.attributes["ConvertedAt"] is not None

    def test_credit_score_deliberately_absent(self):
        _make_lead("LEAD-1")
        result = lead_conversion.convert_lead_to_customer("LEAD-1", "EMP-1")
        assert "CreditScore" not in result.attributes

    def test_missing_lead_fields_default_to_empty_string(self):
        ledger.add_entity(Entity(id="LEAD-1", entity_type=LEAD, attributes={}))
        result = lead_conversion.convert_lead_to_customer("LEAD-1", "EMP-1")
        assert result.attributes["FirstName"] == ""
        assert result.attributes["Email"] == ""

    def test_became_relationship_added(self):
        _make_lead("LEAD-1")
        result = lead_conversion.convert_lead_to_customer("LEAD-1", "EMP-1")
        assert _became_targets("LEAD-1") == [result.id]

    def test_lead_marked_converted(self):
        _make_lead("LEAD-1")
        result = lead_conversion.convert_lead_to_customer("LEAD-1", "EMP-1")

        lead = ledger.get_entity("LEAD-1")
        assert lead.attributes["ConvertedCustomerID"] == result.id
        assert lead.attributes["ConvertedAt"] is not None

    def test_customer_registered_and_resolvable(self):
        _make_lead("LEAD-1")
        result = lead_conversion.convert_lead_to_customer("LEAD-1", "EMP-1")
        assert registry.find_customer(result.id) == result.id

    def test_already_converted_with_existing_customer_short_circuits(self):
        _make_lead("LEAD-1")
        first = lead_conversion.convert_lead_to_customer("LEAD-1", "EMP-1")

        result = lead_conversion.convert_lead_to_customer("LEAD-1", "EMP-2")

        assert result["error"] == f"This lead was already converted to customer {first.id}"
        assert result["customer_id"] == first.id
        # no duplicate BECAME relationship / duplicate customer created
        assert _became_targets("LEAD-1") == [first.id]

    def test_already_converted_but_customer_no_longer_exists_reconverts(self):
        _make_lead("LEAD-1", ConvertedCustomerID="CUST-GHOST")

        result = lead_conversion.convert_lead_to_customer("LEAD-1", "EMP-1")

        assert isinstance(result, Entity)
        assert result.entity_type == CUSTOMER
        assert result.id != "CUST-GHOST"
        lead = ledger.get_entity("LEAD-1")
        assert lead.attributes["ConvertedCustomerID"] == result.id


class TestLeadConversionApiAcl:

    _ALLOWED = [ADMIN, OPERATIONS, SALES, MARKETING]
    _DENIED = [FINANCE, SERVICE]

    @pytest.mark.parametrize("role", _ALLOWED)
    def test_allowed_roles_succeed_and_flatten_result(self, role):
        _make_lead("LEAD-1")

        result = lead_conversion_api.convert_lead_to_customer_api(role, "EMP-1", "LEAD-1")

        assert "error" not in result
        assert "id" in result
        assert result["FirstName"] == "Jordan"

    @pytest.mark.parametrize("role", _DENIED)
    def test_denied_roles_rejected(self, role):
        _make_lead("LEAD-1")

        result = lead_conversion_api.convert_lead_to_customer_api(role, "EMP-1", "LEAD-1")
        assert result == {"error": "You don't have access to convert this lead"}

    def test_error_from_core_passed_through_unwrapped(self):
        result = lead_conversion_api.convert_lead_to_customer_api(ADMIN, "EMP-1", "LEAD-BOGUS")
        assert result == {"error": "Lead 'LEAD-BOGUS' not found"}
