"""
Tests for core/warranty_desk.py + core/warranty_desk_api.py -- Service's
Warranty Desk: a real Submission Workflow (draft -> submitted ->
approved/rejected -> paid) as an additive attribute on Warranty pay-type
ServiceRecords, Warranty Eligibility (a Condition-based inference plus a
real open-recall cross-reference), and Recall Management (a real
completed_recalls tracker + needs_repair/completed campaign split).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import CUSTOMER, VEHICLE, RECALL
from core.relationships import Relationship
from core.relationship_types import OWNS
from core import repair_orders
from core import warranty_desk
from core import warranty_desk_api
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    monkeypatch.setattr(repair_orders, "save_graph", lambda filepath: None)
    monkeypatch.setattr(warranty_desk, "save_graph", lambda filepath: None)


_VIEW_ROLES = (ADMIN, OPERATIONS, SALES, SERVICE, FINANCE)
_VIEW_DENIED_ROLES = (MARKETING,)
_MUTATE_ROLES = (ADMIN, OPERATIONS, SERVICE)
_MUTATE_DENIED_ROLES = (SALES, MARKETING, FINANCE)


def _add_customer(customer_id="CUST-1", first="Jane", last="Doe"):
    ledger.add_entity(Entity(id=customer_id, entity_type=CUSTOMER, attributes={
        "CustomerID": customer_id, "FirstName": first, "LastName": last,
    }))
    return customer_id


def _add_vehicle(vehicle_id="VEH-1", vin="VIN1234567890", condition="New", make="Ford", model="F-150"):
    ledger.add_entity(Entity(id=vehicle_id, entity_type=VEHICLE, attributes={
        "VIN": vin, "Year": "2022", "Make": make, "Model": model, "Condition": condition, "Mileage": 30000,
    }))
    return vehicle_id


def _own(customer_id, vehicle_id):
    ledger.add_relationship(Relationship(source_id=customer_id, target_id=vehicle_id, relationship_type=OWNS))


def _add_ro(customer_id="CUST-1", vehicle_id="VEH-1", description="Transmission slip", created_by="EMP-1", pay_type="Warranty"):
    result = repair_orders.create_repair_order(vehicle_id, customer_id, description, created_by, pay_type=pay_type)
    assert "error" not in result
    return result["id"]


def _add_recall(recall_id="REC-1", make="Ford", model="F-150", open_=True, recall_number="R-100"):
    ledger.add_entity(Entity(id=recall_id, entity_type=RECALL, attributes={
        "make": make, "model": model, "open": open_, "recall_number": recall_number, "description": "Fuel pump defect",
    }))
    return recall_id


def _completion_ro(vehicle_id, ro_id="SRV-1"):
    ledger.add_entity(Entity(id=ro_id, entity_type="ServiceRecord", attributes={"PayType": "Warranty"}))
    ledger.add_relationship(Relationship(source_id=vehicle_id, target_id=ro_id, relationship_type="HAS_SERVICE_RECORD"))


# ---------------------------------------------------------------------------
# get_warranty_claim
# ---------------------------------------------------------------------------

class TestGetWarrantyClaim:
    def test_rejects_unknown_ro(self):
        result = warranty_desk.get_warranty_claim("SRV-NOPE")
        assert "error" in result

    def test_rejects_a_non_warranty_ro(self):
        _add_customer()
        _add_vehicle()
        ro_id = _add_ro(pay_type="Customer Pay")
        result = warranty_desk.get_warranty_claim(ro_id)
        assert "error" in result

    def test_defaults_to_draft_status_for_a_warranty_ro_with_no_claim_yet(self):
        _add_customer()
        _add_vehicle()
        ro_id = _add_ro()
        result = warranty_desk.get_warranty_claim(ro_id)
        assert result["status"] == "draft"
        assert result["oem_claim_number"] is None
        assert result["ro_id"] == ro_id
        assert result["customer_name"] == "Jane Doe"


# ---------------------------------------------------------------------------
# submit_warranty_claim
# ---------------------------------------------------------------------------

class TestSubmitWarrantyClaim:
    def test_rejects_unknown_ro(self):
        result = warranty_desk.submit_warranty_claim("SRV-NOPE", "EMP-1")
        assert "error" in result

    def test_rejects_a_non_warranty_ro(self):
        _add_customer()
        _add_vehicle()
        ro_id = _add_ro(pay_type="Customer Pay")
        result = warranty_desk.submit_warranty_claim(ro_id, "EMP-1")
        assert "error" in result

    def test_submits_a_draft_claim(self):
        _add_customer()
        _add_vehicle()
        ro_id = _add_ro()
        result = warranty_desk.submit_warranty_claim(ro_id, "EMP-1", oem_claim_number="OEM-999")
        assert "error" not in result
        assert result["status"] == "submitted"
        assert result["oem_claim_number"] == "OEM-999"
        assert result["submitted_by"] == "EMP-1"
        assert result["submitted_at"] is not None

    def test_rejects_a_double_submit(self):
        _add_customer()
        _add_vehicle()
        ro_id = _add_ro()
        warranty_desk.submit_warranty_claim(ro_id, "EMP-1")
        result = warranty_desk.submit_warranty_claim(ro_id, "EMP-1")
        assert "error" in result

    def test_can_resubmit_a_rejected_claim(self):
        _add_customer()
        _add_vehicle()
        ro_id = _add_ro()
        warranty_desk.submit_warranty_claim(ro_id, "EMP-1")
        warranty_desk.record_warranty_decision(ro_id, False, "EMP-2", rejection_reason="Missing documentation")
        result = warranty_desk.submit_warranty_claim(ro_id, "EMP-1", oem_claim_number="OEM-1000")
        assert "error" not in result
        assert result["status"] == "submitted"
        assert result["rejection_reason"] is None

    def test_resubmit_clears_prior_decision_fields(self):
        _add_customer()
        _add_vehicle()
        ro_id = _add_ro()
        warranty_desk.submit_warranty_claim(ro_id, "EMP-1")
        warranty_desk.record_warranty_decision(ro_id, False, "EMP-2", rejection_reason="Missing documentation")
        result = warranty_desk.submit_warranty_claim(ro_id, "EMP-1")
        assert result["decided_by"] is None
        assert result["decided_at"] is None


# ---------------------------------------------------------------------------
# record_warranty_decision
# ---------------------------------------------------------------------------

class TestRecordWarrantyDecision:
    def test_rejects_unknown_ro(self):
        result = warranty_desk.record_warranty_decision("SRV-NOPE", True, "EMP-2")
        assert "error" in result

    def test_rejects_deciding_a_draft_claim(self):
        _add_customer()
        _add_vehicle()
        ro_id = _add_ro()
        result = warranty_desk.record_warranty_decision(ro_id, True, "EMP-2")
        assert "error" in result

    def test_rejects_declining_without_a_reason(self):
        _add_customer()
        _add_vehicle()
        ro_id = _add_ro()
        warranty_desk.submit_warranty_claim(ro_id, "EMP-1")
        result = warranty_desk.record_warranty_decision(ro_id, False, "EMP-2", rejection_reason="")
        assert "error" in result

    def test_approves_a_submitted_claim(self):
        _add_customer()
        _add_vehicle()
        ro_id = _add_ro()
        warranty_desk.submit_warranty_claim(ro_id, "EMP-1")
        result = warranty_desk.record_warranty_decision(ro_id, True, "EMP-2")
        assert "error" not in result
        assert result["status"] == "approved"
        assert result["decided_by"] == "EMP-2"
        assert result["rejection_reason"] is None

    def test_rejects_a_submitted_claim_with_a_reason(self):
        _add_customer()
        _add_vehicle()
        ro_id = _add_ro()
        warranty_desk.submit_warranty_claim(ro_id, "EMP-1")
        result = warranty_desk.record_warranty_decision(ro_id, False, "EMP-2", rejection_reason="Not covered")
        assert result["status"] == "rejected"
        assert result["rejection_reason"] == "Not covered"

    def test_rejects_deciding_an_already_decided_claim(self):
        _add_customer()
        _add_vehicle()
        ro_id = _add_ro()
        warranty_desk.submit_warranty_claim(ro_id, "EMP-1")
        warranty_desk.record_warranty_decision(ro_id, True, "EMP-2")
        result = warranty_desk.record_warranty_decision(ro_id, True, "EMP-2")
        assert "error" in result


# ---------------------------------------------------------------------------
# record_warranty_payment
# ---------------------------------------------------------------------------

class TestRecordWarrantyPayment:
    def test_rejects_unknown_ro(self):
        result = warranty_desk.record_warranty_payment("SRV-NOPE", 500, "EMP-3")
        assert "error" in result

    def test_rejects_paying_a_non_approved_claim(self):
        _add_customer()
        _add_vehicle()
        ro_id = _add_ro()
        result = warranty_desk.record_warranty_payment(ro_id, 500, "EMP-3")
        assert "error" in result

    def test_rejects_a_non_numeric_amount(self):
        _add_customer()
        _add_vehicle()
        ro_id = _add_ro()
        warranty_desk.submit_warranty_claim(ro_id, "EMP-1")
        warranty_desk.record_warranty_decision(ro_id, True, "EMP-2")
        result = warranty_desk.record_warranty_payment(ro_id, "nope", "EMP-3")
        assert "error" in result

    def test_rejects_a_non_positive_amount(self):
        _add_customer()
        _add_vehicle()
        ro_id = _add_ro()
        warranty_desk.submit_warranty_claim(ro_id, "EMP-1")
        warranty_desk.record_warranty_decision(ro_id, True, "EMP-2")
        result = warranty_desk.record_warranty_payment(ro_id, 0, "EMP-3")
        assert "error" in result

    def test_records_payment_on_an_approved_claim(self):
        _add_customer()
        _add_vehicle()
        ro_id = _add_ro()
        warranty_desk.submit_warranty_claim(ro_id, "EMP-1")
        warranty_desk.record_warranty_decision(ro_id, True, "EMP-2")
        result = warranty_desk.record_warranty_payment(ro_id, 750.50, "EMP-3")
        assert "error" not in result
        assert result["status"] == "paid"
        assert result["paid_amount"] == 750.50
        assert result["paid_by"] == "EMP-3"

    def test_rejects_double_payment(self):
        _add_customer()
        _add_vehicle()
        ro_id = _add_ro()
        warranty_desk.submit_warranty_claim(ro_id, "EMP-1")
        warranty_desk.record_warranty_decision(ro_id, True, "EMP-2")
        warranty_desk.record_warranty_payment(ro_id, 750, "EMP-3")
        result = warranty_desk.record_warranty_payment(ro_id, 750, "EMP-3")
        assert "error" in result


# ---------------------------------------------------------------------------
# get_claims_queue / get_rejected_claims_queue
# ---------------------------------------------------------------------------

class TestGetClaimsQueue:
    def test_empty_when_no_warranty_records(self):
        result = warranty_desk.get_claims_queue()
        assert result == {"count": 0, "by_status": {}, "claims": []}

    def test_lists_all_warranty_records_with_computed_draft_default(self):
        _add_customer()
        _add_vehicle()
        _add_ro()
        result = warranty_desk.get_claims_queue()
        assert result["count"] == 1
        assert result["claims"][0]["status"] == "draft"

    def test_excludes_non_warranty_pay_type_records(self):
        _add_customer()
        _add_vehicle()
        _add_ro(pay_type="Customer Pay")
        result = warranty_desk.get_claims_queue()
        assert result["count"] == 0

    def test_filters_by_status(self):
        _add_customer()
        _add_vehicle()
        ro_a = _add_ro()
        ro_b = _add_ro()
        warranty_desk.submit_warranty_claim(ro_a, "EMP-1")

        result = warranty_desk.get_claims_queue(status="submitted")
        assert result["count"] == 1
        assert result["claims"][0]["ro_id"] == ro_a

    def test_by_status_breakdown(self):
        _add_customer()
        _add_vehicle()
        ro_a = _add_ro()
        ro_b = _add_ro()
        warranty_desk.submit_warranty_claim(ro_a, "EMP-1")

        result = warranty_desk.get_claims_queue()
        assert result["by_status"]["draft"] == 1
        assert result["by_status"]["submitted"] == 1

    def test_sorted_most_recently_submitted_first(self):
        _add_customer()
        _add_vehicle()
        ro_a = _add_ro()
        ro_b = _add_ro()
        warranty_desk.submit_warranty_claim(ro_a, "EMP-1")
        warranty_desk.submit_warranty_claim(ro_b, "EMP-1")

        result = warranty_desk.get_claims_queue(status="submitted")
        assert result["claims"][0]["ro_id"] == ro_b
        assert result["claims"][1]["ro_id"] == ro_a

    def test_get_rejected_claims_queue_only_includes_rejected(self):
        _add_customer()
        _add_vehicle()
        ro_a = _add_ro()
        ro_b = _add_ro()
        warranty_desk.submit_warranty_claim(ro_a, "EMP-1")
        warranty_desk.record_warranty_decision(ro_a, False, "EMP-2", rejection_reason="Not covered")
        warranty_desk.submit_warranty_claim(ro_b, "EMP-1")

        result = warranty_desk.get_rejected_claims_queue()
        assert result["count"] == 1
        assert result["claims"][0]["ro_id"] == ro_a
        assert result["claims"][0]["rejection_reason"] == "Not covered"


# ---------------------------------------------------------------------------
# get_warranty_eligibility
# ---------------------------------------------------------------------------

class TestGetWarrantyEligibility:
    def test_rejects_unknown_vehicle(self):
        result = warranty_desk.get_warranty_eligibility("VEH-NOPE")
        assert "error" in result

    def test_new_vehicle_is_likely_covered_with_no_matching_recall(self):
        _add_vehicle("VEH-1", condition="New")
        result = warranty_desk.get_warranty_eligibility("VEH-1")
        assert result["general_warranty"]["status"] == "likely_covered"
        assert result["recall_eligible_repairs"] == []

    def test_used_vehicle_is_likely_not_covered(self):
        _add_vehicle("VEH-1", condition="Used")
        result = warranty_desk.get_warranty_eligibility("VEH-1")
        assert result["general_warranty"]["status"] == "likely_not_covered"

    def test_a_matching_open_recall_is_surfaced_regardless_of_condition(self):
        _add_vehicle("VEH-1", condition="Used", make="Ford", model="F-150")
        _add_recall(make="Ford", model="F-150", open_=True)

        result = warranty_desk.get_warranty_eligibility("VEH-1")
        assert len(result["recall_eligible_repairs"]) == 1
        assert result["recall_eligible_repairs"][0]["recall_number"] == "R-100"

    def test_a_closed_recall_is_not_surfaced(self):
        _add_vehicle("VEH-1", make="Ford", model="F-150")
        _add_recall(make="Ford", model="F-150", open_=False)

        result = warranty_desk.get_warranty_eligibility("VEH-1")
        assert result["recall_eligible_repairs"] == []

    def test_a_non_matching_make_model_recall_is_not_surfaced(self):
        _add_vehicle("VEH-1", make="Ford", model="F-150")
        _add_recall(make="Honda", model="Civic", open_=True)

        result = warranty_desk.get_warranty_eligibility("VEH-1")
        assert result["recall_eligible_repairs"] == []


# ---------------------------------------------------------------------------
# mark_recall_completed
# ---------------------------------------------------------------------------

class TestMarkRecallCompleted:
    def test_rejects_unknown_vehicle(self):
        _add_recall()
        result = warranty_desk.mark_recall_completed("VEH-NOPE", "REC-1", "SRV-1", "EMP-1")
        assert "error" in result

    def test_rejects_unknown_recall(self):
        _add_vehicle("VEH-1")
        result = warranty_desk.mark_recall_completed("VEH-1", "REC-NOPE", "SRV-1", "EMP-1")
        assert "error" in result

    def test_marks_a_recall_completed(self):
        _add_vehicle("VEH-1")
        _add_recall()
        _completion_ro("VEH-1")
        result = warranty_desk.mark_recall_completed("VEH-1", "REC-1", "SRV-1", "EMP-1")
        assert "error" not in result
        assert len(result["completed_recalls"]) == 1
        assert result["completed_recalls"][0]["recall_id"] == "REC-1"
        assert result["completed_recalls"][0]["ro_id"] == "SRV-1"

    def test_rejects_marking_the_same_recall_completed_twice(self):
        _add_vehicle("VEH-1")
        _add_recall()
        _completion_ro("VEH-1")
        warranty_desk.mark_recall_completed("VEH-1", "REC-1", "SRV-1", "EMP-1")
        result = warranty_desk.mark_recall_completed("VEH-1", "REC-1", "SRV-1", "EMP-1")
        assert "error" in result

    def test_persists_onto_the_vehicle(self):
        _add_vehicle("VEH-1")
        _add_recall()
        _completion_ro("VEH-1")
        warranty_desk.mark_recall_completed("VEH-1", "REC-1", "SRV-1", "EMP-1")
        vehicle = ledger.get_entity("VEH-1")
        assert len(vehicle.attributes["completed_recalls"]) == 1


# ---------------------------------------------------------------------------
# get_recall_management_queue
# ---------------------------------------------------------------------------

class TestGetRecallManagementQueue:
    def test_empty_when_no_open_recalls(self):
        result = warranty_desk.get_recall_management_queue()
        assert result == {"campaign_count": 0, "total_needs_repair": 0, "total_completed": 0, "campaigns": []}

    def test_closed_recalls_are_excluded_entirely(self):
        _add_recall(open_=False)
        result = warranty_desk.get_recall_management_queue()
        assert result["campaign_count"] == 0

    def test_splits_owning_customers_into_needs_repair_and_completed(self):
        _add_customer("CUST-1", "Jane", "Doe")
        _add_vehicle("VEH-1", make="Ford", model="F-150")
        _own("CUST-1", "VEH-1")

        _add_customer("CUST-2", "John", "Smith")
        _add_vehicle("VEH-2", make="Ford", model="F-150")
        _own("CUST-2", "VEH-2")

        _add_recall("REC-1", make="Ford", model="F-150")
        _completion_ro("VEH-2")
        warranty_desk.mark_recall_completed("VEH-2", "REC-1", "SRV-1", "EMP-1")

        result = warranty_desk.get_recall_management_queue()
        assert result["campaign_count"] == 1
        campaign = result["campaigns"][0]
        assert len(campaign["needs_repair"]) == 1
        assert campaign["needs_repair"][0]["vehicle_id"] == "VEH-1"
        assert len(campaign["completed"]) == 1
        assert campaign["completed"][0]["vehicle_id"] == "VEH-2"
        assert result["total_needs_repair"] == 1
        assert result["total_completed"] == 1

    def test_a_vehicle_not_matching_make_model_is_excluded(self):
        _add_customer("CUST-1")
        _add_vehicle("VEH-1", make="Honda", model="Civic")
        _own("CUST-1", "VEH-1")
        _add_recall("REC-1", make="Ford", model="F-150")

        result = warranty_desk.get_recall_management_queue()
        assert result["campaigns"][0]["needs_repair"] == []

    def test_deduplicates_a_vehicle_with_multiple_owns_relationships(self):
        _add_customer("CUST-1")
        _add_vehicle("VEH-1", make="Ford", model="F-150")
        _own("CUST-1", "VEH-1")
        _own("CUST-1", "VEH-1")  # duplicate OWNS -- a real, pre-existing seed-data quirk
        _add_recall("REC-1", make="Ford", model="F-150")

        result = warranty_desk.get_recall_management_queue()
        assert len(result["campaigns"][0]["needs_repair"]) == 1


# ---------------------------------------------------------------------------
# ACL sweep -- core/warranty_desk_api.py
# ---------------------------------------------------------------------------

class TestAcl:
    @pytest.mark.parametrize("role", _VIEW_DENIED_ROLES)
    def test_get_warranty_claim_api_denied(self, role):
        _add_customer()
        _add_vehicle()
        ro_id = _add_ro()
        result = warranty_desk_api.get_warranty_claim_api(role, ro_id)
        assert "error" in result

    @pytest.mark.parametrize("role", _VIEW_ROLES)
    def test_get_warranty_claim_api_allowed(self, role):
        _add_customer()
        _add_vehicle()
        ro_id = _add_ro()
        result = warranty_desk_api.get_warranty_claim_api(role, ro_id)
        assert result["status"] == "draft"

    @pytest.mark.parametrize("role", _MUTATE_DENIED_ROLES)
    def test_submit_warranty_claim_api_denied(self, role):
        _add_customer()
        _add_vehicle()
        ro_id = _add_ro()
        result = warranty_desk_api.submit_warranty_claim_api(role, ro_id, "EMP-1")
        assert "error" in result

    @pytest.mark.parametrize("role", _MUTATE_ROLES)
    def test_submit_warranty_claim_api_allowed(self, role):
        ledger.reset()
        _add_customer()
        _add_vehicle()
        ro_id = _add_ro()
        result = warranty_desk_api.submit_warranty_claim_api(role, ro_id, "EMP-1")
        assert result["status"] == "submitted"

    @pytest.mark.parametrize("role", _MUTATE_DENIED_ROLES)
    def test_record_warranty_decision_api_denied(self, role):
        _add_customer()
        _add_vehicle()
        ro_id = _add_ro()
        warranty_desk.submit_warranty_claim(ro_id, "EMP-1")
        result = warranty_desk_api.record_warranty_decision_api(role, ro_id, True, "EMP-2")
        assert "error" in result

    @pytest.mark.parametrize("role", _MUTATE_ROLES)
    def test_record_warranty_decision_api_allowed(self, role):
        ledger.reset()
        _add_customer()
        _add_vehicle()
        ro_id = _add_ro()
        warranty_desk.submit_warranty_claim(ro_id, "EMP-1")
        result = warranty_desk_api.record_warranty_decision_api(role, ro_id, True, "EMP-2")
        assert result["status"] == "approved"

    @pytest.mark.parametrize("role", _MUTATE_DENIED_ROLES)
    def test_record_warranty_payment_api_denied(self, role):
        _add_customer()
        _add_vehicle()
        ro_id = _add_ro()
        warranty_desk.submit_warranty_claim(ro_id, "EMP-1")
        warranty_desk.record_warranty_decision(ro_id, True, "EMP-2")
        result = warranty_desk_api.record_warranty_payment_api(role, ro_id, 500, "EMP-3")
        assert "error" in result

    @pytest.mark.parametrize("role", _MUTATE_ROLES)
    def test_record_warranty_payment_api_allowed(self, role):
        ledger.reset()
        _add_customer()
        _add_vehicle()
        ro_id = _add_ro()
        warranty_desk.submit_warranty_claim(ro_id, "EMP-1")
        warranty_desk.record_warranty_decision(ro_id, True, "EMP-2")
        result = warranty_desk_api.record_warranty_payment_api(role, ro_id, 500, "EMP-3")
        assert result["status"] == "paid"

    @pytest.mark.parametrize("role", _VIEW_DENIED_ROLES)
    def test_get_claims_queue_api_denied(self, role):
        result = warranty_desk_api.get_claims_queue_api(role)
        assert "error" in result

    @pytest.mark.parametrize("role", _VIEW_ROLES)
    def test_get_claims_queue_api_allowed(self, role):
        result = warranty_desk_api.get_claims_queue_api(role)
        assert "count" in result

    @pytest.mark.parametrize("role", _VIEW_DENIED_ROLES)
    def test_get_rejected_claims_queue_api_denied(self, role):
        result = warranty_desk_api.get_rejected_claims_queue_api(role)
        assert "error" in result

    @pytest.mark.parametrize("role", _VIEW_ROLES)
    def test_get_rejected_claims_queue_api_allowed(self, role):
        result = warranty_desk_api.get_rejected_claims_queue_api(role)
        assert "count" in result

    @pytest.mark.parametrize("role", _VIEW_DENIED_ROLES)
    def test_get_warranty_eligibility_api_denied(self, role):
        _add_vehicle("VEH-1")
        result = warranty_desk_api.get_warranty_eligibility_api(role, "VEH-1")
        assert "error" in result

    @pytest.mark.parametrize("role", _VIEW_ROLES)
    def test_get_warranty_eligibility_api_allowed(self, role):
        _add_vehicle("VEH-1")
        result = warranty_desk_api.get_warranty_eligibility_api(role, "VEH-1")
        assert "general_warranty" in result

    @pytest.mark.parametrize("role", _MUTATE_DENIED_ROLES)
    def test_mark_recall_completed_api_denied(self, role):
        _add_vehicle("VEH-1")
        _add_recall()
        _completion_ro("VEH-1")
        result = warranty_desk_api.mark_recall_completed_api(role, "VEH-1", "REC-1", "SRV-1", "EMP-1")
        assert "error" in result

    @pytest.mark.parametrize("role", _MUTATE_ROLES)
    def test_mark_recall_completed_api_allowed(self, role):
        ledger.reset()
        _add_vehicle("VEH-1")
        _add_recall()
        _completion_ro("VEH-1")
        result = warranty_desk_api.mark_recall_completed_api(role, "VEH-1", "REC-1", "SRV-1", "EMP-1")
        assert "error" not in result

    @pytest.mark.parametrize("role", _VIEW_DENIED_ROLES)
    def test_get_recall_management_queue_api_denied(self, role):
        result = warranty_desk_api.get_recall_management_queue_api(role)
        assert "error" in result

    @pytest.mark.parametrize("role", _VIEW_ROLES)
    def test_get_recall_management_queue_api_allowed(self, role):
        result = warranty_desk_api.get_recall_management_queue_api(role)
        assert "campaign_count" in result


@pytest.mark.parametrize("ro_id", ["", "MISSING", "VEH-1"])
def test_recall_rejects_nonexistent_or_non_ro_reference_without_mutation(ro_id):
    _add_vehicle()
    _add_recall()
    result = warranty_desk.mark_recall_completed("VEH-1", "REC-1", ro_id, "EMP-1")
    assert "error" in result
    assert "completed_recalls" not in ledger.get_entity("VEH-1").attributes


def test_recall_rejects_another_vehicle_repair_order_without_mutation():
    _add_vehicle()
    _add_vehicle("VEH-2")
    _add_recall()
    _completion_ro("VEH-2")
    result = warranty_desk.mark_recall_completed("VEH-1", "REC-1", "SRV-1", "EMP-1")
    assert "does not belong" in result["error"]
    assert "completed_recalls" not in ledger.get_entity("VEH-1").attributes
