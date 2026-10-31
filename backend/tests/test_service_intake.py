"""
Supplementary tests for core/service_intake.py / core/service_intake_api.py -- quick
Service ticket intake (session 47). Run from backend/ with `pytest`.

tests/test_intake.py already covers the api layer's validation (missing description,
bad pay_type, bad status) and the two HAPPY-path relationship-linking cases (customer_id
resolves, vin resolves). This file fills the real gaps left open by that coverage:
create_service_record()'s attribute shape (ServiceNumber == record.id, entity_type,
CustomerID/VIN default to "" when not supplied), the negative paths where customer_id/vin
is supplied but does NOT resolve via registry (no relationship should be added -- the exact
opposite of what test_intake.py already checks), the case where neither is supplied at all
(no relationship attempts, no crash), optional numeric fields (mileage/cost/parts_cost/
labor_hours) defaulting to "" when None but passing through real values unchanged, and
description.strip()'s whitespace-trimming behavior at the api layer.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger, registry
from core.entity_types import SERVICE_RECORD
from core.relationship_types import AUTHORIZED, HAS_SERVICE_RECORD
from core import service_intake
from core import service_intake_api


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    monkeypatch.setattr(service_intake, "save_graph", lambda filepath: None)


class TestCreateServiceRecordAttributeShape:

    def test_entity_type_and_service_number_match_id(self):
        record = service_intake.create_service_record(
            "EMP-1", "VIN123", "Oil change", "Customer Pay"
        )

        assert record.entity_type == SERVICE_RECORD
        assert record.attributes["ServiceNumber"] == record.id
        assert record.id.startswith("SRV")

    def test_technician_is_always_the_creating_employee(self):
        record = service_intake.create_service_record(
            "EMP-42", "VIN123", "Oil change", "Warranty"
        )
        assert record.attributes["Technician"] == "EMP-42"

    def test_no_customer_or_vin_defaults_customer_id_and_vin_to_empty_string(self):
        record = service_intake.create_service_record(
            "EMP-1", None, "Oil change", "Internal"
        )
        assert record.attributes["CustomerID"] == ""
        assert record.attributes["VIN"] == ""

    def test_optional_numeric_fields_default_to_empty_string_when_none(self):
        record = service_intake.create_service_record(
            "EMP-1", "VIN123", "Oil change", "Internal"
        )
        assert record.attributes["Mileage"] == ""
        assert record.attributes["Cost"] == ""
        assert record.attributes["PartsCost"] == ""
        assert record.attributes["LaborHours"] == ""

    def test_optional_numeric_fields_pass_through_real_values(self):
        record = service_intake.create_service_record(
            "EMP-1", "VIN123", "Oil change", "Internal",
            mileage=45000, cost=89.99, parts_cost=25.50, labor_hours=1.5,
        )
        assert record.attributes["Mileage"] == 45000
        assert record.attributes["Cost"] == 89.99
        assert record.attributes["PartsCost"] == 25.50
        assert record.attributes["LaborHours"] == 1.5

    def test_service_date_is_stamped(self):
        record = service_intake.create_service_record(
            "EMP-1", "VIN123", "Oil change", "Internal"
        )
        assert record.attributes["ServiceDate"]

    def test_default_status_is_completed(self):
        record = service_intake.create_service_record(
            "EMP-1", "VIN123", "Oil change", "Internal"
        )
        assert record.attributes["Status"] == "Completed"

    def test_explicit_status_is_honored(self):
        record = service_intake.create_service_record(
            "EMP-1", "VIN123", "Oil change", "Internal", status="In Progress"
        )
        assert record.attributes["Status"] == "In Progress"


class TestCreateServiceRecordRelationshipNegativePaths:

    def test_unresolvable_customer_id_creates_no_authorized_relationship(self):
        # No registry.register_customer() call for this key -- it should not resolve.
        record = service_intake.create_service_record(
            "EMP-1", "VIN123", "Oil change", "Internal", customer_id="CUST-DOES-NOT-EXIST"
        )

        rels = ledger.get_entity_relationships(record.id)
        assert not any(r.relationship_type == AUTHORIZED for r in rels)
        # The raw external key is still stored on the record even though it didn't resolve.
        assert record.attributes["CustomerID"] == "CUST-DOES-NOT-EXIST"

    def test_unresolvable_vin_creates_no_has_service_record_relationship(self):
        record = service_intake.create_service_record(
            "EMP-1", "VIN-DOES-NOT-EXIST", "Oil change", "Internal"
        )

        rels = ledger.get_entity_relationships(record.id)
        assert not any(r.relationship_type == HAS_SERVICE_RECORD for r in rels)
        assert record.attributes["VIN"] == "VIN-DOES-NOT-EXIST"

    def test_no_customer_id_or_vin_supplied_creates_no_relationships_at_all(self):
        record = service_intake.create_service_record(
            "EMP-1", None, "Oil change", "Internal"
        )

        rels = ledger.get_entity_relationships(record.id)
        assert rels == []

    def test_empty_string_customer_id_is_falsy_and_skips_lookup(self):
        # An empty string is falsy in the `if customer_id:` guard -- registry.find_customer
        # should never even be consulted.
        record = service_intake.create_service_record(
            "EMP-1", "VIN123", "Oil change", "Internal", customer_id=""
        )
        rels = ledger.get_entity_relationships(record.id)
        assert not any(r.relationship_type == AUTHORIZED for r in rels)


class TestCreateServiceRecordApiDescriptionHandling:

    def test_description_is_trimmed_of_surrounding_whitespace(self):
        result = service_intake_api.create_service_record_api(
            "EMP-1", "VIN123", "  Brake job  ", "Customer Pay"
        )
        assert result["Description"] == "Brake job"

    def test_none_description_rejected(self):
        result = service_intake_api.create_service_record_api(
            "EMP-1", "VIN123", None, "Customer Pay"
        )
        assert "error" in result

    def test_valid_pay_types_and_statuses_all_accepted(self):
        for pay_type in service_intake.VALID_PAY_TYPES:
            for status in service_intake.VALID_STATUSES:
                result = service_intake_api.create_service_record_api(
                    "EMP-1", "VIN123", "desc", pay_type, status=status
                )
                assert "error" not in result
                assert result["PayType"] == pay_type
                assert result["Status"] == status

    def test_two_records_from_the_same_employee_get_distinct_ids(self):
        first = service_intake_api.create_service_record_api(
            "EMP-1", "VIN123", "Oil change", "Internal"
        )
        second = service_intake_api.create_service_record_api(
            "EMP-1", "VIN123", "Brake job", "Internal"
        )
        assert first["id"] != second["id"]
