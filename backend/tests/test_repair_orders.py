"""
Tests for core/repair_orders.py + core/repair_orders_api.py -- the RO
Workflow Engine, the flagship build of Service's rebuild (session 111): a
10-stage RO lifecycle, concern tracking, an estimate/approval flow, parts
requests, a QC checklist, a composed timeline, and real warranty/recall
status inference -- all layered as additive attributes on the existing
ServiceRecord entity, no new entity type.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import VEHICLE, CUSTOMER, SERVICE_RECORD, RECALL
from core import repair_orders
from core import repair_orders_api
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    monkeypatch.setattr(repair_orders, "save_graph", lambda filepath: None)


_VIEW_ROLES = (ADMIN, OPERATIONS, SALES, SERVICE, FINANCE)
_VIEW_DENIED_ROLES = (MARKETING,)
_MUTATE_ROLES = (ADMIN, OPERATIONS, SERVICE)
_MUTATE_DENIED_ROLES = (SALES, MARKETING, FINANCE)


def _add_vehicle(vehicle_id="VEH-1", vin="VIN1", make="Honda", model="Civic",
                  year="2025", condition="Used", mileage=15000):
    ledger.add_entity(Entity(id=vehicle_id, entity_type=VEHICLE, attributes={
        "VIN": vin, "Make": make, "Model": model, "Year": year,
        "Condition": condition, "Mileage": mileage,
    }))
    return vehicle_id


def _add_customer(customer_id="CUST-1", customer_key="C1", first="Jane", last="Doe",
                   phone="555-0100", email="jane@example.com"):
    ledger.add_entity(Entity(id=customer_id, entity_type=CUSTOMER, attributes={
        "CustomerID": customer_key, "FirstName": first, "LastName": last,
        "Phone": phone, "Email": email,
    }))
    return customer_id


def _add_recall(recall_id="RECALL-1", make="Honda", model="Civic", open_=True,
                 recall_number="R-1", description="Airbag issue", campaign_type="safety"):
    ledger.add_entity(Entity(id=recall_id, entity_type=RECALL, attributes={
        "make": make, "model": model, "open": open_,
        "recall_number": recall_number, "description": description,
        "campaign_type": campaign_type,
    }))
    return recall_id


def _create_ro(vehicle_id="VEH-1", customer_id="CUST-1", description="Strange noise",
                created_by="EMP-1", **kwargs):
    _add_vehicle(vehicle_id) if not ledger.get_entity(vehicle_id) else None
    _add_customer(customer_id) if not ledger.get_entity(customer_id) else None
    return repair_orders.create_repair_order(vehicle_id, customer_id, description, created_by, **kwargs)


def _new_ro(**kwargs):
    """Convenience: create vehicle + customer + RO, return the RO id."""
    _add_vehicle()
    _add_customer()
    result = repair_orders.create_repair_order("VEH-1", "CUST-1", "Strange noise", "EMP-1", **kwargs)
    assert "error" not in result
    return result["id"]


# ---------------------------------------------------------------------------
# create_repair_order
# ---------------------------------------------------------------------------

class TestCreateRepairOrder:
    def test_rejects_unknown_vehicle(self):
        _add_customer()
        result = repair_orders.create_repair_order("VEH-BAD", "CUST-1", "Noise", "EMP-1")
        assert "error" in result

    def test_rejects_vehicle_id_that_is_not_a_vehicle(self):
        _add_customer()
        ledger.add_entity(Entity(id="NOTAVEH", entity_type=CUSTOMER, attributes={}))
        result = repair_orders.create_repair_order("NOTAVEH", "CUST-1", "Noise", "EMP-1")
        assert "error" in result

    def test_rejects_unknown_customer(self):
        _add_vehicle()
        result = repair_orders.create_repair_order("VEH-1", "CUST-BAD", "Noise", "EMP-1")
        assert "error" in result

    def test_rejects_empty_description(self):
        _add_vehicle()
        _add_customer()
        result = repair_orders.create_repair_order("VEH-1", "CUST-1", "   ", "EMP-1")
        assert "error" in result

    def test_rejects_missing_description(self):
        _add_vehicle()
        _add_customer()
        result = repair_orders.create_repair_order("VEH-1", "CUST-1", "", "EMP-1")
        assert "error" in result

    def test_creates_a_real_service_record(self):
        ro_id = _new_ro()
        entity = ledger.get_entity(ro_id)
        assert entity is not None
        assert entity.entity_type == SERVICE_RECORD
        assert entity.attributes["Status"] == "Open"
        assert entity.attributes["ro_stage"] == "Check-In"

    def test_starts_at_check_in_stage(self):
        ro_id = _new_ro()
        ws = repair_orders.get_ro_workspace(ro_id)
        assert ws["ro_stage"] == "Check-In"
        assert ws["ro_stage_is_default"] is False

    def test_seeds_stage_history_with_check_in(self):
        ro_id = _new_ro()
        entity = ledger.get_entity(ro_id)
        history = entity.attributes["ro_stage_history"]
        assert len(history) == 1
        assert history[0]["stage"] == "Check-In"
        assert history[0]["by"] == "EMP-1"

    def test_seeds_one_concern_from_the_description(self):
        ro_id = _new_ro()
        ws = repair_orders.get_ro_workspace(ro_id)
        assert len(ws["concerns"]) == 1
        assert ws["concerns"][0]["description"] == "Strange noise"
        assert ws["concerns"][0]["status"] == "open"

    def test_defaults_pay_type_to_customer_pay(self):
        ro_id = _new_ro()
        ws = repair_orders.get_ro_workspace(ro_id)
        assert ws["pay_type"] == "Customer Pay"

    def test_accepts_a_custom_pay_type(self):
        _add_vehicle()
        _add_customer()
        result = repair_orders.create_repair_order("VEH-1", "CUST-1", "Noise", "EMP-1", pay_type="Warranty")
        ws = repair_orders.get_ro_workspace(result["id"])
        assert ws["pay_type"] == "Warranty"

    def test_records_preferred_contact_method(self):
        _add_vehicle()
        _add_customer()
        result = repair_orders.create_repair_order(
            "VEH-1", "CUST-1", "Noise", "EMP-1", preferred_contact_method="text",
        )
        ws = repair_orders.get_ro_workspace(result["id"])
        assert ws["customer"]["preferred_contact_method"] == "text"

    def test_creates_real_relationships(self):
        ro_id = _new_ro()
        rels = [r for r in ledger.get_relationships() if r.target_id == ro_id]
        types = {r.relationship_type for r in rels}
        assert "AUTHORIZED" in types
        assert "HAS_SERVICE_RECORD" in types

    def test_copies_vin_and_mileage_from_the_vehicle(self):
        _add_vehicle(vin="XYZ999", mileage=42000)
        _add_customer()
        result = repair_orders.create_repair_order("VEH-1", "CUST-1", "Noise", "EMP-1")
        ws = repair_orders.get_ro_workspace(result["id"])
        assert ws["vehicle"]["vin"] == "XYZ999"
        assert ws["vehicle"]["mileage"] == 42000


# ---------------------------------------------------------------------------
# advance_stage
# ---------------------------------------------------------------------------

class TestAdvanceStage:
    def test_rejects_unknown_stage(self):
        ro_id = _new_ro()
        result = repair_orders.advance_stage(ro_id, "Not A Real Stage", "EMP-1")
        assert "error" in result

    def test_rejects_unknown_ro(self):
        result = repair_orders.advance_stage("SRV-BAD", "RO Written", "EMP-1")
        assert "error" in result

    def test_moves_to_the_new_stage(self):
        ro_id = _new_ro()
        result = repair_orders.advance_stage(ro_id, "RO Written", "EMP-1")
        assert result["ro_stage"] == "RO Written"

    def test_appends_to_stage_history(self):
        ro_id = _new_ro()
        repair_orders.advance_stage(ro_id, "RO Written", "EMP-2")
        entity = ledger.get_entity(ro_id)
        history = entity.attributes["ro_stage_history"]
        assert len(history) == 2
        assert history[-1]["stage"] == "RO Written"
        assert history[-1]["by"] == "EMP-2"

    def test_moving_to_follow_up_marks_status_completed(self):
        ro_id = _new_ro()
        _prepare_delivery(ro_id)
        repair_orders.advance_stage(ro_id, "Delivery", "EMP-1")
        result = repair_orders.advance_stage(ro_id, "Follow-Up", "EMP-1")
        assert result["status"] == "Completed"

    def test_moving_to_a_non_follow_up_stage_does_not_mark_completed(self):
        ro_id = _new_ro()
        result = repair_orders.advance_stage(ro_id, "Inspection", "EMP-1")
        assert result["status"] == "Open"

    def test_can_move_backwards_in_the_stage_list(self):
        ro_id = _new_ro()
        repair_orders.advance_stage(ro_id, "Repair", "EMP-1")
        result = repair_orders.advance_stage(ro_id, "Estimate", "EMP-1")
        assert result["ro_stage"] == "Estimate"


# ---------------------------------------------------------------------------
# Default stage computation (historical-data honesty)
# ---------------------------------------------------------------------------

class TestDefaultStage:
    def test_completed_historical_record_defaults_to_follow_up(self):
        ledger.add_entity(Entity(id="SRV-HIST-1", entity_type=SERVICE_RECORD, attributes={
            "ServiceNumber": "SRV-HIST-1", "Status": "Completed",
        }))
        ws = repair_orders.get_ro_workspace("SRV-HIST-1")
        assert ws["ro_stage"] == "Follow-Up"
        assert ws["ro_stage_is_default"] is True

    def test_open_historical_record_defaults_to_check_in(self):
        ledger.add_entity(Entity(id="SRV-HIST-2", entity_type=SERVICE_RECORD, attributes={
            "ServiceNumber": "SRV-HIST-2", "Status": "Open",
        }))
        ws = repair_orders.get_ro_workspace("SRV-HIST-2")
        assert ws["ro_stage"] == "Check-In"
        assert ws["ro_stage_is_default"] is True

    def test_default_is_replaced_once_advance_stage_is_called(self):
        ledger.add_entity(Entity(id="SRV-HIST-3", entity_type=SERVICE_RECORD, attributes={
            "ServiceNumber": "SRV-HIST-3", "Status": "Completed",
        }))
        repair_orders.advance_stage("SRV-HIST-3", "Inspection", "EMP-1")
        ws = repair_orders.get_ro_workspace("SRV-HIST-3")
        assert ws["ro_stage"] == "Inspection"
        assert ws["ro_stage_is_default"] is False

    def test_stage_counts_include_the_computed_default(self):
        ledger.add_entity(Entity(id="SRV-HIST-4", entity_type=SERVICE_RECORD, attributes={
            "ServiceNumber": "SRV-HIST-4", "Status": "Completed",
        }))
        counts = repair_orders.get_stage_counts()
        assert counts["Follow-Up"] == 1


# ---------------------------------------------------------------------------
# add_concern / resolve_concern
# ---------------------------------------------------------------------------

class TestConcerns:
    def test_add_concern_rejects_unknown_ro(self):
        result = repair_orders.add_concern("SRV-BAD", "Squeal", "EMP-1")
        assert "error" in result

    def test_add_concern_rejects_empty_description(self):
        ro_id = _new_ro()
        result = repair_orders.add_concern(ro_id, "   ", "EMP-1")
        assert "error" in result

    def test_add_concern_appends_a_second_concern(self):
        ro_id = _new_ro()
        repair_orders.add_concern(ro_id, "Brake squeal", "EMP-1", occurs_at="On braking")
        ws = repair_orders.get_ro_workspace(ro_id)
        assert len(ws["concerns"]) == 2
        assert ws["concerns"][1]["description"] == "Brake squeal"
        assert ws["concerns"][1]["occurs_at"] == "On braking"
        assert ws["concerns"][1]["status"] == "open"

    def test_resolve_concern_rejects_unknown_ro(self):
        result = repair_orders.resolve_concern("SRV-BAD", "CONC-1", "EMP-1")
        assert "error" in result

    def test_resolve_concern_rejects_unknown_concern_id(self):
        ro_id = _new_ro()
        result = repair_orders.resolve_concern(ro_id, "CONC-BAD", "EMP-1")
        assert "error" in result

    def test_resolve_concern_marks_it_resolved(self):
        ro_id = _new_ro()
        ws = repair_orders.get_ro_workspace(ro_id)
        concern_id = ws["concerns"][0]["id"]
        result = repair_orders.resolve_concern(ro_id, concern_id, "EMP-2", resolution_notes="Replaced pads")
        resolved = result["concerns"][0]
        assert resolved["status"] == "resolved"
        assert resolved["resolved_by"] == "EMP-2"
        assert resolved["resolution_notes"] == "Replaced pads"

    def test_each_concern_gets_a_distinct_id(self):
        ro_id = _new_ro()
        repair_orders.add_concern(ro_id, "Second concern", "EMP-1")
        ws = repair_orders.get_ro_workspace(ro_id)
        ids = [c["id"] for c in ws["concerns"]]
        assert len(set(ids)) == len(ids)


# ---------------------------------------------------------------------------
# send_estimate / record_customer_approval
# ---------------------------------------------------------------------------

class TestEstimateAndApproval:
    def test_send_estimate_rejects_unknown_ro(self):
        result = repair_orders.send_estimate("SRV-BAD", 500, "EMP-1")
        assert "error" in result

    def test_send_estimate_rejects_non_numeric_amount(self):
        ro_id = _new_ro()
        result = repair_orders.send_estimate(ro_id, "not-a-number", "EMP-1")
        assert "error" in result

    def test_send_estimate_stores_a_real_estimate(self):
        ro_id = _new_ro()
        result = repair_orders.send_estimate(ro_id, "450.50", "EMP-1")
        estimate = result["estimate"]
        assert estimate["amount"] == 450.5
        assert estimate["sent_by"] == "EMP-1"
        assert estimate["approved"] is None

    def test_approval_rejects_unknown_ro(self):
        result = repair_orders.record_customer_approval("SRV-BAD", True, "EMP-1")
        assert "error" in result

    def test_approval_rejects_when_no_estimate_sent_yet(self):
        ro_id = _new_ro()
        result = repair_orders.record_customer_approval(ro_id, True, "EMP-1")
        assert "error" in result

    def test_approval_records_a_real_approve(self):
        ro_id = _new_ro()
        repair_orders.send_estimate(ro_id, 500, "EMP-1")
        result = repair_orders.record_customer_approval(ro_id, True, "EMP-2")
        estimate = result["estimate"]
        assert estimate["approved"] is True
        assert estimate["approved_by"] == "EMP-2"
        assert estimate["decline_reason"] is None

    def test_approval_records_a_real_decline_with_reason(self):
        ro_id = _new_ro()
        repair_orders.send_estimate(ro_id, 500, "EMP-1")
        result = repair_orders.record_customer_approval(ro_id, False, "EMP-2", decline_reason="Too expensive")
        estimate = result["estimate"]
        assert estimate["approved"] is False
        assert estimate["decline_reason"] == "Too expensive"


# ---------------------------------------------------------------------------
# assign_technician
# ---------------------------------------------------------------------------

class TestAssignTechnician:
    def test_rejects_unknown_ro(self):
        result = repair_orders.assign_technician("SRV-BAD", "EMP-9", "EMP-1")
        assert "error" in result

    def test_rejects_unknown_technician_id(self):
        ro_id = _new_ro()
        result = repair_orders.assign_technician(ro_id, "EMP-NOPE", "EMP-1")
        assert "error" in result

    def test_assigns_a_real_technician(self):
        ledger.add_entity(Entity(id="EMP-TECH", entity_type=CUSTOMER, attributes={}))
        ro_id = _new_ro()
        result = repair_orders.assign_technician(ro_id, "EMP-TECH", "EMP-1")
        assert result["technician"] == "EMP-TECH"

    def test_records_assignment_history(self):
        ledger.add_entity(Entity(id="EMP-TECH", entity_type=CUSTOMER, attributes={}))
        ro_id = _new_ro()
        repair_orders.assign_technician(ro_id, "EMP-TECH", "EMP-1")
        entity = ledger.get_entity(ro_id)
        history = entity.attributes["technician_assignment_history"]
        assert len(history) == 1
        assert history[0]["technician_id"] == "EMP-TECH"

    def test_none_unassigns(self):
        ledger.add_entity(Entity(id="EMP-TECH", entity_type=CUSTOMER, attributes={}))
        ro_id = _new_ro()
        repair_orders.assign_technician(ro_id, "EMP-TECH", "EMP-1")
        result = repair_orders.assign_technician(ro_id, None, "EMP-1")
        assert result["technician"] is None

    def test_empty_string_unassigns(self):
        ledger.add_entity(Entity(id="EMP-TECH", entity_type=CUSTOMER, attributes={}))
        ro_id = _new_ro()
        repair_orders.assign_technician(ro_id, "EMP-TECH", "EMP-1")
        result = repair_orders.assign_technician(ro_id, "", "EMP-1")
        assert result["technician"] is None


# ---------------------------------------------------------------------------
# Parts (status + requests)
# ---------------------------------------------------------------------------

class TestParts:
    def test_update_parts_status_rejects_bad_status(self):
        ro_id = _new_ro()
        result = repair_orders.update_parts_status(ro_id, "not_real", "EMP-1")
        assert "error" in result

    def test_update_parts_status_rejects_unknown_ro(self):
        result = repair_orders.update_parts_status("SRV-BAD", "all_available", "EMP-1")
        assert "error" in result

    def test_update_parts_status_stores_a_real_status(self):
        ro_id = _new_ro()
        result = repair_orders.update_parts_status(ro_id, "backordered", "EMP-1", notes="Waiting on OEM")
        assert result["parts_status"]["status"] == "backordered"
        assert result["parts_status"]["notes"] == "Waiting on OEM"

    def test_request_part_rejects_unknown_ro(self):
        result = repair_orders.request_part("SRV-BAD", "Water pump", "EMP-1")
        assert "error" in result

    def test_request_part_rejects_empty_description(self):
        ro_id = _new_ro()
        result = repair_orders.request_part(ro_id, "   ", "EMP-1")
        assert "error" in result

    def test_request_part_creates_a_real_request(self):
        ro_id = _new_ro()
        result = repair_orders.request_part(ro_id, "Water pump", "EMP-1")
        assert len(result["parts_requests"]) == 1
        assert result["parts_requests"][0]["description"] == "Water pump"
        assert result["parts_requests"][0]["status"] == "requested"

    def test_update_part_request_status_rejects_bad_status(self):
        ro_id = _new_ro()
        repair_orders.request_part(ro_id, "Water pump", "EMP-1")
        ws = repair_orders.get_ro_workspace(ro_id)
        req_id = ws["parts_requests"][0]["id"]
        result = repair_orders.update_part_request_status(ro_id, req_id, "not_real", "EMP-1")
        assert "error" in result

    def test_update_part_request_status_rejects_unknown_ro(self):
        result = repair_orders.update_part_request_status("SRV-BAD", "PREQ-1", "in_stock", "EMP-1")
        assert "error" in result

    def test_update_part_request_status_rejects_unknown_request(self):
        ro_id = _new_ro()
        result = repair_orders.update_part_request_status(ro_id, "PREQ-BAD", "in_stock", "EMP-1")
        assert "error" in result

    def test_update_part_request_status_updates_it(self):
        ro_id = _new_ro()
        repair_orders.request_part(ro_id, "Water pump", "EMP-1")
        ws = repair_orders.get_ro_workspace(ro_id)
        req_id = ws["parts_requests"][0]["id"]
        repair_orders.update_part_request_status(ro_id, req_id, "received", "EMP-1")
        result = repair_orders.update_part_request_status(ro_id, req_id, "installed", "EMP-2")
        assert result["parts_requests"][0]["status"] == "installed"
        assert result["parts_requests"][0]["updated_by"] == "EMP-2"

    def test_each_part_request_gets_a_distinct_id(self):
        ro_id = _new_ro()
        repair_orders.request_part(ro_id, "Water pump", "EMP-1")
        repair_orders.request_part(ro_id, "Serpentine belt", "EMP-1")
        ws = repair_orders.get_ro_workspace(ro_id)
        ids = [r["id"] for r in ws["parts_requests"]]
        assert len(set(ids)) == 2


# ---------------------------------------------------------------------------
# Quality Control
# ---------------------------------------------------------------------------

class TestQualityControl:
    def test_rejects_unknown_item(self):
        ro_id = _new_ro()
        result = repair_orders.update_qc_item(ro_id, "not_a_real_item", True, "EMP-1")
        assert "error" in result

    def test_rejects_unknown_ro(self):
        result = repair_orders.update_qc_item("SRV-BAD", "washed", True, "EMP-1")
        assert "error" in result

    def test_marks_a_single_item_complete(self):
        ro_id = _new_ro()
        result = repair_orders.update_qc_item(ro_id, "washed", True, "EMP-1")
        assert result["qc_checklist"]["washed"]["complete"] is True

    def test_not_ready_for_pickup_until_all_four_items_complete(self):
        ro_id = _new_ro()
        repair_orders.update_qc_item(ro_id, "repair_complete", True, "EMP-1")
        repair_orders.update_qc_item(ro_id, "road_test", True, "EMP-1")
        repair_orders.update_qc_item(ro_id, "qc_inspection", True, "EMP-1")
        result = repair_orders.update_qc_item(ro_id, "washed", False, "EMP-1")
        assert result["qc_ready_for_pickup"] is False

    def test_ready_for_pickup_once_all_four_items_complete(self):
        ro_id = _new_ro()
        for item in repair_orders.QC_ITEMS:
            result = repair_orders.update_qc_item(ro_id, item, True, "EMP-1")
        assert result["qc_ready_for_pickup"] is True

    def test_can_flip_an_item_back_to_incomplete(self):
        ro_id = _new_ro()
        for item in repair_orders.QC_ITEMS:
            repair_orders.update_qc_item(ro_id, item, True, "EMP-1")
        result = repair_orders.update_qc_item(ro_id, "washed", False, "EMP-1")
        assert result["qc_checklist"]["washed"]["complete"] is False
        assert result["qc_ready_for_pickup"] is False


# ---------------------------------------------------------------------------
# Communication Center
# ---------------------------------------------------------------------------

class TestCommunicationCenter:
    def test_rejects_bad_channel(self):
        ro_id = _new_ro()
        result = repair_orders.log_ro_communication(ro_id, "carrier_pigeon", "Called customer", "EMP-1")
        assert "error" in result

    def test_rejects_unknown_ro(self):
        result = repair_orders.log_ro_communication("SRV-BAD", "call", "Called customer", "EMP-1")
        assert "error" in result

    def test_rejects_empty_body(self):
        ro_id = _new_ro()
        result = repair_orders.log_ro_communication(ro_id, "call", "   ", "EMP-1")
        assert "error" in result

    def test_logs_a_real_communication(self):
        ro_id = _new_ro()
        repair_orders.log_ro_communication(ro_id, "text", "Vehicle is ready", "EMP-1")
        timeline = repair_orders.get_ro_timeline(ro_id)
        comms = [e for e in timeline["events"] if e["type"] == "communication"]
        assert len(comms) == 1
        assert "Vehicle is ready" in comms[0]["label"]
        assert "[text]" in comms[0]["label"]

    @pytest.mark.parametrize("channel", ["call", "text", "email"])
    def test_accepts_every_real_channel(self, channel):
        ro_id = _new_ro()
        result = repair_orders.log_ro_communication(ro_id, channel, "Hello", "EMP-1")
        assert "error" not in result


# ---------------------------------------------------------------------------
# Warranty + recall status
# ---------------------------------------------------------------------------

class TestWarrantyAndRecallStatus:
    def test_new_vehicle_is_likely_covered(self):
        _add_vehicle(condition="New")
        _add_customer()
        result = repair_orders.create_repair_order("VEH-1", "CUST-1", "Noise", "EMP-1")
        assert result["vehicle"]["warranty_status"]["status"] == "likely_covered"

    def test_certified_pre_owned_is_likely_covered(self):
        _add_vehicle(condition="Certified Pre-Owned")
        _add_customer()
        result = repair_orders.create_repair_order("VEH-1", "CUST-1", "Noise", "EMP-1")
        assert result["vehicle"]["warranty_status"]["status"] == "likely_covered"

    def test_used_vehicle_is_likely_not_covered(self):
        _add_vehicle(condition="Used")
        _add_customer()
        result = repair_orders.create_repair_order("VEH-1", "CUST-1", "Noise", "EMP-1")
        assert result["vehicle"]["warranty_status"]["status"] == "likely_not_covered"

    def test_no_vehicle_on_file_reports_unknown_warranty(self):
        ledger.add_entity(Entity(id="SRV-NOVEH", entity_type=SERVICE_RECORD, attributes={
            "ServiceNumber": "SRV-NOVEH", "VIN": "NOTREAL",
        }))
        ws = repair_orders.get_ro_workspace("SRV-NOVEH")
        assert ws["vehicle"]["warranty_status"]["status"] == "unknown"

    def test_open_recall_matching_make_and_model_is_found(self):
        _add_vehicle(make="Honda", model="Civic")
        _add_customer()
        _add_recall(make="Honda", model="Civic", open_=True)
        result = repair_orders.create_repair_order("VEH-1", "CUST-1", "Noise", "EMP-1")
        recall_status = result["vehicle"]["recall_status"]
        assert recall_status["count"] == 1
        assert recall_status["open_recalls"][0]["recall_number"] == "R-1"

    def test_closed_recall_is_not_counted(self):
        _add_vehicle(make="Honda", model="Civic")
        _add_customer()
        _add_recall(make="Honda", model="Civic", open_=False)
        result = repair_orders.create_repair_order("VEH-1", "CUST-1", "Noise", "EMP-1")
        assert result["vehicle"]["recall_status"]["count"] == 0

    def test_recall_for_a_different_model_is_not_counted(self):
        _add_vehicle(make="Honda", model="Civic")
        _add_customer()
        _add_recall(make="Honda", model="Accord", open_=True)
        result = repair_orders.create_repair_order("VEH-1", "CUST-1", "Noise", "EMP-1")
        assert result["vehicle"]["recall_status"]["count"] == 0

    def test_no_vehicle_reports_zero_recalls(self):
        ledger.add_entity(Entity(id="SRV-NOVEH", entity_type=SERVICE_RECORD, attributes={
            "ServiceNumber": "SRV-NOVEH", "VIN": "NOTREAL",
        }))
        ws = repair_orders.get_ro_workspace("SRV-NOVEH")
        assert ws["vehicle"]["recall_status"]["count"] == 0


# ---------------------------------------------------------------------------
# Timeline composition
# ---------------------------------------------------------------------------

class TestTimeline:
    def test_rejects_unknown_ro(self):
        result = repair_orders.get_ro_timeline("SRV-BAD")
        assert "error" in result

    def test_includes_stage_changes(self):
        ro_id = _new_ro()
        repair_orders.advance_stage(ro_id, "RO Written", "EMP-1")
        timeline = repair_orders.get_ro_timeline(ro_id)
        stage_events = [e for e in timeline["events"] if e["type"] == "stage_change"]
        assert len(stage_events) == 2

    def test_includes_concern_added_and_resolved(self):
        ro_id = _new_ro()
        ws = repair_orders.get_ro_workspace(ro_id)
        concern_id = ws["concerns"][0]["id"]
        repair_orders.resolve_concern(ro_id, concern_id, "EMP-1", "Repair verified")
        timeline = repair_orders.get_ro_timeline(ro_id)
        types = [e["type"] for e in timeline["events"]]
        assert "concern_added" in types
        assert "concern_resolved" in types

    def test_includes_estimate_sent_and_approved(self):
        ro_id = _new_ro()
        repair_orders.send_estimate(ro_id, 500, "EMP-1")
        repair_orders.record_customer_approval(ro_id, True, "EMP-1")
        timeline = repair_orders.get_ro_timeline(ro_id)
        types = [e["type"] for e in timeline["events"]]
        assert "estimate_sent" in types
        assert "estimate_approved" in types

    def test_includes_estimate_declined(self):
        ro_id = _new_ro()
        repair_orders.send_estimate(ro_id, 500, "EMP-1")
        repair_orders.record_customer_approval(ro_id, False, "EMP-1", decline_reason="Too much")
        timeline = repair_orders.get_ro_timeline(ro_id)
        declined = [e for e in timeline["events"] if e["type"] == "estimate_declined"]
        assert len(declined) == 1
        assert declined[0]["notes"] == "Too much"

    def test_includes_part_requested_and_status_change(self):
        ro_id = _new_ro()
        repair_orders.request_part(ro_id, "Water pump", "EMP-1")
        ws = repair_orders.get_ro_workspace(ro_id)
        req_id = ws["parts_requests"][0]["id"]
        repair_orders.update_part_request_status(ro_id, req_id, "in_stock", "EMP-1")
        timeline = repair_orders.get_ro_timeline(ro_id)
        types = [e["type"] for e in timeline["events"]]
        assert "part_requested" in types
        assert "part_status" in types

    def test_includes_qc_items(self):
        ro_id = _new_ro()
        repair_orders.update_qc_item(ro_id, "washed", True, "EMP-1")
        timeline = repair_orders.get_ro_timeline(ro_id)
        qc_events = [e for e in timeline["events"] if e["type"] == "qc_item"]
        assert len(qc_events) == 1

    def test_includes_technician_assignment(self):
        ledger.add_entity(Entity(id="EMP-TECH", entity_type=CUSTOMER, attributes={}))
        ro_id = _new_ro()
        repair_orders.assign_technician(ro_id, "EMP-TECH", "EMP-1")
        timeline = repair_orders.get_ro_timeline(ro_id)
        tech_events = [e for e in timeline["events"] if e["type"] == "technician_assigned"]
        assert len(tech_events) == 1

    def test_events_are_chronologically_sorted(self):
        ro_id = _new_ro()
        repair_orders.advance_stage(ro_id, "RO Written", "EMP-1")
        repair_orders.advance_stage(ro_id, "Inspection", "EMP-1")
        timeline = repair_orders.get_ro_timeline(ro_id)
        timestamps = [e["at"] for e in timeline["events"] if e.get("at")]
        assert timestamps == sorted(timestamps)

    def test_respects_the_limit_parameter(self):
        ro_id = _new_ro()
        for i in range(5):
            repair_orders.log_ro_communication(ro_id, "call", f"Call {i}", "EMP-1")
        timeline = repair_orders.get_ro_timeline(ro_id, limit=2)
        assert len(timeline["events"]) == 2


# ---------------------------------------------------------------------------
# Board + stage counts + catalog
# ---------------------------------------------------------------------------

class TestBoardAndCatalog:
    def test_get_catalog_shape(self):
        catalog = repair_orders.get_catalog()
        assert catalog["stages"] == repair_orders.RO_STAGES
        assert set(catalog["qc_items"]) == set(repair_orders.QC_ITEMS)
        assert set(catalog["parts_statuses"]) == set(repair_orders.PARTS_STATUSES)
        assert set(catalog["comm_channels"]) == set(repair_orders.COMM_CHANNELS)

    def test_stage_counts_sum_to_total_service_records(self):
        _new_ro()
        vehicle_id = "VEH-2"
        _add_vehicle(vehicle_id, vin="VIN2")
        result = repair_orders.create_repair_order(vehicle_id, "CUST-1", "Other issue", "EMP-1")
        assert "error" not in result
        counts = repair_orders.get_stage_counts()
        assert sum(counts.values()) == 2

    def test_board_groups_ros_by_stage(self):
        ro_id_1 = _new_ro()
        vehicle_id = "VEH-2"
        _add_vehicle(vehicle_id, vin="VIN2")
        ro_2 = repair_orders.create_repair_order(vehicle_id, "CUST-1", "Other", "EMP-1")
        repair_orders.advance_stage(ro_2["id"], "Repair", "EMP-1")
        board = repair_orders.get_ro_board()
        assert any(b["id"] == ro_id_1 for b in board["Check-In"])
        assert any(b["id"] == ro_2["id"] for b in board["Repair"])

    def test_board_respects_limit_per_stage(self):
        for i in range(3):
            vehicle_id = f"VEH-{i}"
            _add_vehicle(vehicle_id, vin=f"VIN{i}")
            repair_orders.create_repair_order(vehicle_id, "CUST-1" if i == 0 else _new_ro_customer(i), "Noise", "EMP-1")
        board = repair_orders.get_ro_board(limit_per_stage=1)
        assert len(board["Check-In"]) <= 1

    def test_board_includes_uncapped_stage_counts_agreement(self):
        """get_stage_counts() must never undercount relative to a real
        population, even though get_ro_board()'s own per-stage list is
        capped for rendering -- exactly the distinction this module's own
        get_stage_counts() docstring draws."""
        for i in range(5):
            vehicle_id = f"VEH-{i}"
            _add_vehicle(vehicle_id, vin=f"VIN{i}")
            customer_id = f"CUST-{i}"
            _add_customer(customer_id, customer_key=f"C{i}")
            repair_orders.create_repair_order(vehicle_id, customer_id, "Noise", "EMP-1")
        counts = repair_orders.get_stage_counts()
        board = repair_orders.get_ro_board(limit_per_stage=2)
        assert counts["Check-In"] == 5
        assert len(board["Check-In"]) == 2


def _new_ro_customer(i):
    customer_id = f"CUST-{i}"
    if not ledger.get_entity(customer_id):
        _add_customer(customer_id, customer_key=f"C{i}")
    return customer_id


# ---------------------------------------------------------------------------
# get_ro_workspace shape
# ---------------------------------------------------------------------------

class TestRoWorkspaceShape:
    def test_rejects_unknown_ro(self):
        result = repair_orders.get_ro_workspace("SRV-BAD")
        assert "error" in result

    def test_includes_customer_name(self):
        ro_id = _new_ro()
        ws = repair_orders.get_ro_workspace(ro_id)
        assert ws["customer"]["name"] == "Jane Doe"
        assert ws["customer"]["phone"] == "555-0100"
        assert ws["customer"]["email"] == "jane@example.com"

    def test_includes_workflow_checklist_with_correct_current_marker(self):
        ro_id = _new_ro()
        ws = repair_orders.get_ro_workspace(ro_id)
        checklist = ws["workflow_checklist"]
        assert checklist[0]["stage"] == "Check-In"
        assert checklist[0]["status"] == "current"
        assert checklist[1]["status"] == "pending"

    def test_workflow_checklist_marks_earlier_stages_complete(self):
        ro_id = _new_ro()
        repair_orders.advance_stage(ro_id, "Estimate", "EMP-1")
        ws = repair_orders.get_ro_workspace(ro_id)
        checklist = {c["stage"]: c["status"] for c in ws["workflow_checklist"]}
        assert checklist["Check-In"] == "complete"
        assert checklist["RO Written"] == "complete"
        assert checklist["Estimate"] == "current"
        assert checklist["Customer Approval"] == "pending"

    def test_no_customer_on_file_returns_none_fields(self):
        ledger.add_entity(Entity(id="SRV-NOCUST", entity_type=SERVICE_RECORD, attributes={
            "ServiceNumber": "SRV-NOCUST", "CustomerID": "NOTREAL",
        }))
        ws = repair_orders.get_ro_workspace("SRV-NOCUST")
        assert ws["customer"]["id"] is None
        assert ws["customer"]["name"] is None


# ---------------------------------------------------------------------------
# ACL sweep -- core/repair_orders_api.py
# ---------------------------------------------------------------------------

class TestAclViewRoles:
    @pytest.mark.parametrize("role", _VIEW_DENIED_ROLES)
    def test_get_catalog_denied(self, role):
        assert "error" in repair_orders_api.get_catalog_api(role)

    @pytest.mark.parametrize("role", _VIEW_ROLES)
    def test_get_catalog_allowed(self, role):
        assert "error" not in repair_orders_api.get_catalog_api(role)

    @pytest.mark.parametrize("role", _VIEW_DENIED_ROLES)
    def test_get_ro_board_denied(self, role):
        assert "error" in repair_orders_api.get_ro_board_api(role)

    @pytest.mark.parametrize("role", _VIEW_ROLES)
    def test_get_ro_board_allowed(self, role):
        assert "error" not in repair_orders_api.get_ro_board_api(role)

    @pytest.mark.parametrize("role", _VIEW_DENIED_ROLES)
    def test_get_stage_counts_denied(self, role):
        assert "error" in repair_orders_api.get_stage_counts_api(role)

    @pytest.mark.parametrize("role", _VIEW_ROLES)
    def test_get_stage_counts_allowed(self, role):
        assert "error" not in repair_orders_api.get_stage_counts_api(role)

    @pytest.mark.parametrize("role", _VIEW_DENIED_ROLES)
    def test_get_ro_workspace_denied(self, role):
        ro_id = _new_ro()
        assert "error" in repair_orders_api.get_ro_workspace_api(role, ro_id)

    @pytest.mark.parametrize("role", _VIEW_ROLES)
    def test_get_ro_workspace_allowed(self, role):
        ro_id = _new_ro()
        assert "error" not in repair_orders_api.get_ro_workspace_api(role, ro_id)


class TestAclMutateRoles:
    @pytest.mark.parametrize("role", _MUTATE_DENIED_ROLES)
    def test_create_repair_order_denied(self, role):
        _add_vehicle()
        _add_customer()
        result = repair_orders_api.create_repair_order_api(role, "EMP-1", "VEH-1", "CUST-1", "Noise")
        assert "error" in result

    @pytest.mark.parametrize("role", _MUTATE_ROLES)
    def test_create_repair_order_allowed(self, role):
        ledger.reset()
        _add_vehicle()
        _add_customer()
        result = repair_orders_api.create_repair_order_api(role, "EMP-1", "VEH-1", "CUST-1", "Noise")
        assert "error" not in result

    @pytest.mark.parametrize("role", _MUTATE_DENIED_ROLES)
    def test_advance_stage_denied(self, role):
        ro_id = _new_ro()
        result = repair_orders_api.advance_stage_api(role, "EMP-1", ro_id, "RO Written")
        assert "error" in result

    @pytest.mark.parametrize("role", _MUTATE_DENIED_ROLES)
    def test_add_concern_denied(self, role):
        ro_id = _new_ro()
        result = repair_orders_api.add_concern_api(role, "EMP-1", ro_id, "Noise")
        assert "error" in result

    @pytest.mark.parametrize("role", _MUTATE_DENIED_ROLES)
    def test_resolve_concern_denied(self, role):
        ro_id = _new_ro()
        ws = repair_orders.get_ro_workspace(ro_id)
        concern_id = ws["concerns"][0]["id"]
        result = repair_orders_api.resolve_concern_api(role, "EMP-1", ro_id, concern_id)
        assert "error" in result

    @pytest.mark.parametrize("role", _MUTATE_DENIED_ROLES)
    def test_send_estimate_denied(self, role):
        ro_id = _new_ro()
        result = repair_orders_api.send_estimate_api(role, "EMP-1", ro_id, 500)
        assert "error" in result

    @pytest.mark.parametrize("role", _MUTATE_DENIED_ROLES)
    def test_record_customer_approval_denied(self, role):
        ro_id = _new_ro()
        repair_orders.send_estimate(ro_id, 500, "EMP-1")
        result = repair_orders_api.record_customer_approval_api(role, "EMP-1", ro_id, True)
        assert "error" in result

    @pytest.mark.parametrize("role", _MUTATE_DENIED_ROLES)
    def test_update_parts_status_denied(self, role):
        ro_id = _new_ro()
        result = repair_orders_api.update_parts_status_api(role, "EMP-1", ro_id, "all_available")
        assert "error" in result

    @pytest.mark.parametrize("role", _MUTATE_DENIED_ROLES)
    def test_request_part_denied(self, role):
        ro_id = _new_ro()
        result = repair_orders_api.request_part_api(role, "EMP-1", ro_id, "Water pump")
        assert "error" in result

    @pytest.mark.parametrize("role", _MUTATE_DENIED_ROLES)
    def test_update_part_request_status_denied(self, role):
        ro_id = _new_ro()
        repair_orders.request_part(ro_id, "Water pump", "EMP-1")
        ws = repair_orders.get_ro_workspace(ro_id)
        req_id = ws["parts_requests"][0]["id"]
        result = repair_orders_api.update_part_request_status_api(role, "EMP-1", ro_id, req_id, "in_stock")
        assert "error" in result

    @pytest.mark.parametrize("role", _MUTATE_DENIED_ROLES)
    def test_update_qc_item_denied(self, role):
        ro_id = _new_ro()
        result = repair_orders_api.update_qc_item_api(role, "EMP-1", ro_id, "washed", True)
        assert "error" in result

    @pytest.mark.parametrize("role", _MUTATE_DENIED_ROLES)
    def test_log_ro_communication_denied(self, role):
        ro_id = _new_ro()
        result = repair_orders_api.log_ro_communication_api(role, "EMP-1", ro_id, "call", "Hello")
        assert "error" in result

    @pytest.mark.parametrize("role", _MUTATE_DENIED_ROLES)
    def test_assign_technician_denied(self, role):
        ledger.add_entity(Entity(id="EMP-TECH", entity_type=CUSTOMER, attributes={}))
        ro_id = _new_ro()
        result = repair_orders_api.assign_technician_api(role, "EMP-1", ro_id, "EMP-TECH")
        assert "error" in result

    @pytest.mark.parametrize("role", _MUTATE_ROLES)
    def test_advance_stage_allowed(self, role):
        ledger.reset()
        ro_id = _new_ro()
        result = repair_orders_api.advance_stage_api(role, "EMP-1", ro_id, "RO Written")
        assert "error" not in result

    @pytest.mark.parametrize("role", _MUTATE_ROLES)
    def test_log_ro_communication_allowed(self, role):
        ledger.reset()
        ro_id = _new_ro()
        result = repair_orders_api.log_ro_communication_api(role, "EMP-1", ro_id, "call", "Hello")
        assert "error" not in result


# ---------------------------------------------------------------------------
# Pillar 4 slice 4d: the RO lifecycle feeds the agentic-bot FLEET's Service agent.
# ---------------------------------------------------------------------------

class TestServiceAgentWorkflowFeed:
    def _run_flow(self, vehicle_id, customer_id, actor="EMP-1"):
        _add_vehicle(vehicle_id)
        _add_customer(customer_id)
        ro = repair_orders_api.create_repair_order_api(SERVICE, actor, vehicle_id, customer_id, "Strange noise")
        assert "error" not in ro
        ro_id = ro["id"]
        assert "error" not in repair_orders_api.add_concern_api(SERVICE, actor, ro_id, "Grinding on braking")
        assert "error" not in repair_orders_api.send_estimate_api(SERVICE, actor, ro_id, 500)
        assert "error" not in repair_orders_api.record_customer_approval_api(SERVICE, actor, ro_id, True)
        return ro_id

    def test_two_ros_make_service_agent_recognize_the_workflow(self):
        """Running two ROs through the same advisor (create -> add concern -> send
        estimate -> customer approval) makes the Service team agent recognize the
        repeated multi-step workflow -- real recognition fed through the RO API."""

        from core.bot_fleet import get_team_workflows

        self._run_flow("VEH-1", "CUST-1")
        self._run_flow("VEH-2", "CUST-2")

        wf = get_team_workflows("service")

        assert wf["step_count"] == 8  # 2 ROs x 4 recorded steps
        recognized = {tuple(w["steps"]): w["occurrences"] for w in wf["recognized_workflows"]}
        assert ("create_ro", "add_concern", "send_estimate", "customer_approval") in recognized
        assert recognized[("create_ro", "add_concern", "send_estimate", "customer_approval")] >= 2

    def test_service_flow_does_not_feed_other_teams(self):
        """Honest team scoping: RO steps feed only the Service agent."""

        from core.bot_fleet import get_team_workflows

        self._run_flow("VEH-1", "CUST-1")

        assert get_team_workflows("service")["step_count"] == 4
        assert get_team_workflows("sales")["step_count"] == 0
        assert get_team_workflows("inventory")["step_count"] == 0

def test_live_intake_resolves_links_without_optional_import_keys():
    _add_customer(customer_key=None)
    _add_vehicle(vin=None)
    result = repair_orders.create_repair_order('VEH-1', 'CUST-1', 'Fictional brake concern', 'EMP-1')
    assert result['customer']['id'] == 'CUST-1'
    assert result['vehicle']['id'] == 'VEH-1'
    assert result['concerns'][0]['description'] == 'Fictional brake concern'
    assert repair_orders.get_ro_workspace(result['id'])['customer']['name'] == 'Jane Doe'


def test_live_links_take_precedence_over_duplicate_import_identifiers():
    _add_customer('CUST-WRONG', customer_key='C1')
    _add_vehicle('VEH-WRONG', vin='VIN1')
    _add_customer()
    _add_vehicle()
    result = repair_orders.create_repair_order('VEH-1', 'CUST-1', 'Fictional concern', 'EMP-1')
    assert result['customer']['id'] == 'CUST-1'
    assert result['vehicle']['id'] == 'VEH-1'

@pytest.mark.parametrize('amount', [-1, 'nan', 'inf', '-inf'])
def test_estimate_rejects_invalid_amount_without_replacing_existing_estimate(amount):
    ro_id = _new_ro()
    repair_orders.send_estimate(ro_id, 125, 'EMP-1')
    result = repair_orders.send_estimate(ro_id, amount, 'EMP-1')
    assert 'error' in result
    assert repair_orders.get_ro_workspace(ro_id)['estimate']['amount'] == 125

@pytest.mark.parametrize("status", ["requested", "ordered"])
def test_install_requires_available_part_without_overwriting_status(status):
    ro_id = _new_ro()
    repair_orders.request_part(ro_id, "Synthetic brake pads", "EMP-1")
    req_id = repair_orders.get_ro_workspace(ro_id)["parts_requests"][0]["id"]
    repair_orders.update_part_request_status(ro_id, req_id, status, "EMP-1")
    result = repair_orders.update_part_request_status(ro_id, req_id, "installed", "EMP-2")
    assert "error" in result
    request = repair_orders.get_ro_workspace(ro_id)["parts_requests"][0]
    assert request["status"] == status
    assert request["updated_by"] == "EMP-1"

@pytest.mark.parametrize("status", ["in_stock", "received"])
def test_available_part_can_be_installed_and_retried(status):
    ro_id = _new_ro()
    repair_orders.request_part(ro_id, "Synthetic brake pads", "EMP-1")
    req_id = repair_orders.get_ro_workspace(ro_id)["parts_requests"][0]["id"]
    repair_orders.update_part_request_status(ro_id, req_id, status, "EMP-1")
    for _ in range(2):
        result = repair_orders.update_part_request_status(ro_id, req_id, "installed", "EMP-2")
        assert result["parts_requests"][0]["status"] == "installed"

@pytest.mark.parametrize("outcome", ["resolved", "declined", "deferred"])
def test_concern_outcome_requires_notes_and_preserves_customer_decision(outcome):
    ro_id = _new_ro()
    concern_id = repair_orders.get_ro_workspace(ro_id)["concerns"][0]["id"]
    rejected = repair_orders.resolve_concern(ro_id, concern_id, "EMP-1", "  ", outcome)
    assert "error" in rejected
    assert repair_orders.get_ro_workspace(ro_id)["concerns"][0]["status"] == "open"
    result = repair_orders.resolve_concern(ro_id, concern_id, "EMP-1", "Fictional decision record", outcome)
    concern = result["concerns"][0]
    assert concern["status"] == outcome
    assert concern["resolution_notes"] == "Fictional decision record"
    assert concern["outcome_history"][0]["outcome"] == outcome
    assert any(f"Concern {outcome}:" in e["label"] for e in result["timeline"]["events"])
    repair_orders.resolve_concern(ro_id, concern_id, "EMP-2", "Later repair verified", "resolved")
    assert len(repair_orders.get_ro_workspace(ro_id)["concerns"][0]["outcome_history"]) == 2

def test_concern_rejects_unknown_outcome():
    ro_id = _new_ro()
    concern_id = repair_orders.get_ro_workspace(ro_id)["concerns"][0]["id"]
    result = repair_orders.resolve_concern(ro_id, concern_id, "EMP-1", "Notes", "done-ish")
    assert "error" in result
    assert repair_orders.get_ro_workspace(ro_id)["concerns"][0]["status"] == "open"

def _prepare_delivery(ro_id):
    for c in repair_orders.get_ro_workspace(ro_id)["concerns"]:
        repair_orders.resolve_concern(ro_id, c["id"], "EMP-1", "Synthetic repair checked")
    for item in repair_orders.QC_ITEMS:
        repair_orders.update_qc_item(ro_id, item, True, "EMP-1")

@pytest.mark.parametrize("stage", ["Delivery", "Follow-Up"])
def test_delivery_rejection_preserves_stage_status_and_history(stage):
    ro_id = _new_ro()
    before = repair_orders.get_ro_workspace(ro_id)
    history = list(ledger.get_entity(ro_id).attributes.get("ro_stage_history", []))
    result = repair_orders.advance_stage(ro_id, stage, "EMP-1")
    assert "error" in result and result["blockers"]
    after = repair_orders.get_ro_workspace(ro_id)
    assert after["ro_stage"] == before["ro_stage"]
    assert after["status"] == before["status"]
    assert ledger.get_entity(ro_id).attributes.get("ro_stage_history", []) == history

@pytest.mark.parametrize("outcome", ["declined", "deferred"])
def test_unperformed_work_cannot_be_presented_as_completed_delivery(outcome):
    ro_id = _new_ro()
    _prepare_delivery(ro_id)
    c = repair_orders.get_ro_workspace(ro_id)["concerns"][0]
    repair_orders.resolve_concern(ro_id, c["id"], "EMP-1", "Synthetic decision", outcome)
    result = repair_orders.advance_stage(ro_id, "Delivery", "EMP-1")
    assert "separate return review" in result["error"]

def test_delivery_rechecks_estimate_parts_and_requires_delivery_before_followup():
    ro_id = _new_ro()
    _prepare_delivery(ro_id)
    repair_orders.send_estimate(ro_id, 125, "EMP-1")
    repair_orders.request_part(ro_id, "Synthetic pads", "EMP-1")
    result = repair_orders.advance_stage(ro_id, "Delivery", "EMP-1")
    assert any("approval" in b for b in result["blockers"])
    assert any("parts" in b for b in result["blockers"])
    repair_orders.record_customer_approval(ro_id, True, "EMP-1")
    r = repair_orders.get_ro_workspace(ro_id)["parts_requests"][0]
    repair_orders.update_part_request_status(ro_id, r["id"], "received", "EMP-1")
    repair_orders.update_part_request_status(ro_id, r["id"], "installed", "EMP-1")
    assert "error" in repair_orders.advance_stage(ro_id, "Follow-Up", "EMP-1")
    assert repair_orders.advance_stage(ro_id, "Delivery", "EMP-1")["ro_stage"] == "Delivery"
    repair_orders.update_qc_item(ro_id, "road_test", False, "EMP-1")
    assert "error" in repair_orders.advance_stage(ro_id, "Follow-Up", "EMP-1")

def _deferred_ro():
    ro_id = _new_ro()
    concern = repair_orders.get_ro_workspace(ro_id)["concerns"][0]
    repair_orders.resolve_concern(ro_id, concern["id"], "EMP-1", "Synthetic deferred work", "deferred")
    return ro_id

@pytest.mark.parametrize("transport,notes,ack", [("", "Plan", True), ("tow", " ", True), ("tow", "Plan", False)])
def test_return_review_requires_transport_notes_and_acknowledgement(transport, notes, ack):
    ro_id = _deferred_ro()
    assert "error" in repair_orders.record_return_review(ro_id,"EMP-1",transport,notes,ack)
    assert repair_orders.get_ro_workspace(ro_id)["return_review"] is None

def test_return_review_is_a_record_not_release_and_becomes_stale():
    ro_id = _deferred_ro()
    before = repair_orders.get_ro_workspace(ro_id)
    result = repair_orders.record_return_review(ro_id,"EMP-1","tow","Synthetic transport review",True)
    assert result["return_review"]["current"] is True
    assert "snapshot" not in result["return_review"]
    assert result["ro_stage"] == before["ro_stage"] and result["status"] == before["status"]
    assert "error" in repair_orders.advance_stage(ro_id,"Delivery","EMP-1")
    repair_orders.add_concern(ro_id,"New fictional concern","EMP-1")
    assert repair_orders.get_ro_workspace(ro_id)["return_review"]["current"] is False
    assert "error" in repair_orders.record_return_review(ro_id,"EMP-1","tow","Another review",True)
    assert len(ledger.get_entity(ro_id).attributes["return_reviews"]) == 1

@pytest.mark.parametrize("role", [SALES, MARKETING, FINANCE])
def test_return_review_preserves_existing_role_boundary(role):
    ro_id = _deferred_ro()
    result = repair_orders_api.record_return_review_api(role,"EMP-1",ro_id,"tow","Plan",True)
    assert "error" in result
    assert repair_orders.get_ro_workspace(ro_id)["return_review"] is None

@pytest.mark.parametrize("role", [ADMIN, OPERATIONS, SERVICE])
def test_return_review_allowed_roles_record_actor(role):
    ro_id = _deferred_ro()
    result = repair_orders_api.record_return_review_api(role,"EMP-1",ro_id,"tow","Synthetic plan",True)
    assert result["return_review"]["recorded_by"] == "EMP-1"

def _reviewed_return_ro():
    ro_id = _deferred_ro()
    repair_orders.record_return_review(ro_id,"EMP-1","tow","Synthetic return plan",True)
    return ro_id

@pytest.mark.parametrize("recipient,reference,confirmed", [("", "SYN-REF", True), ("Test recipient", " ", True), ("Test recipient", "SYN-REF", False)])
def test_return_handover_requires_explicit_details(recipient,reference,confirmed):
    ro_id = _reviewed_return_ro()
    assert "error" in repair_orders.record_return_handover(ro_id,"EMP-1",recipient,reference,confirmed)
    assert repair_orders.get_ro_workspace(ro_id)["return_handover"] is None

def test_return_handover_needs_current_review():
    ro_id = _deferred_ro()
    assert "error" in repair_orders.record_return_handover(ro_id,"EMP-1","Test recipient","SYN-REF",True)
    repair_orders.record_return_review(ro_id,"EMP-1","tow","Synthetic plan",True)
    repair_orders.send_estimate(ro_id,100,"EMP-1")
    assert "error" in repair_orders.record_return_handover(ro_id,"EMP-1","Test recipient","SYN-REF",True)

def test_custody_return_preserves_unperformed_work_and_prevents_duplicate():
    ro_id = _reviewed_return_ro()
    before = repair_orders.get_ro_workspace(ro_id)
    result = repair_orders.record_return_handover(ro_id,"EMP-2","Synthetic Carrier","SYN-NO-CHARGE",True)
    returned = result["return_handover"]
    assert returned["recorded_by"] == "EMP-2" and returned["transport"] == "tow"
    assert returned["settlement_basis"] == "staff_recorded_external_check"
    assert "snapshot" not in returned
    assert result["status"] == before["status"] and result["ro_stage"] == before["ro_stage"]
    assert result["concerns"][0]["status"] == "deferred"
    assert "error" in repair_orders.record_return_handover(ro_id,"EMP-3","Other","Other",True)
    assert repair_orders.get_ro_workspace(ro_id)["return_handover"] == returned
    repair_orders.add_concern(ro_id,"Synthetic later concern","EMP-1")
    assert repair_orders.get_ro_workspace(ro_id)["return_handover"]["work_changed_since"] is True

@pytest.mark.parametrize("role", [SALES, MARKETING, FINANCE])
def test_return_handover_denied_roles(role):
    ro_id = _reviewed_return_ro()
    assert "error" in repair_orders_api.record_return_handover_api(role,"EMP-1",ro_id,"Test","SYN-REF",True)
    assert repair_orders.get_ro_workspace(ro_id)["return_handover"] is None

@pytest.mark.parametrize("due,action", [("2026-02-30","Call"),("20261014","Call"),("2026-10-14"," ")])
def test_return_followup_validates_without_creating_plan(due,action):
    ro_id = _reviewed_return_ro()
    repair_orders.record_return_handover(ro_id,"EMP-1","Test","SYN-REF",True)
    assert "error" in repair_orders.plan_return_followup(ro_id,"EMP-2",due,action)
    assert repair_orders.get_ro_workspace(ro_id)["return_followup"] is None

def test_return_followup_needs_handover_and_preserves_history():
    ro_id = _reviewed_return_ro()
    assert "error" in repair_orders.plan_return_followup(ro_id,"EMP-1","2026-10-14","Call")
    repair_orders.record_return_handover(ro_id,"EMP-1","Test","SYN-REF",True)
    before = repair_orders.get_ro_workspace(ro_id)
    result = repair_orders.plan_return_followup(ro_id,"EMP-2","2026-10-14","Review deferred work")
    assert result["return_followup"]["owner_id"] == "EMP-2"
    assert result["ro_stage"] == before["ro_stage"]
    assert result["return_handover"] == before["return_handover"]
    repair_orders.plan_return_followup(ro_id,"EMP-3","2026-10-15","New plan")
    assert len(ledger.get_entity(ro_id).attributes["return_followup_history"]) == 2

@pytest.mark.parametrize("role", [SALES, MARKETING, FINANCE])
def test_return_followup_denies_non_service_roles(role):
    ro_id = _reviewed_return_ro()
    assert "error" in repair_orders_api.plan_return_followup_api(role,"EMP-1",ro_id,"2026-10-14","Call")


def _planned_return_ro():
    ro_id = _reviewed_return_ro()
    repair_orders.record_return_handover(ro_id,"EMP-1","Test","SYN-REF",True)
    repair_orders.plan_return_followup(ro_id,"EMP-1","2026-10-14","Review deferred work")
    return ro_id


def test_followup_outcome_preserves_repairs_and_allows_another_plan():
    ro_id = _planned_return_ro()
    before = repair_orders.get_ro_workspace(ro_id)
    version = before["return_followup"]["updated_at"]
    assert "error" in repair_orders.complete_return_followup(ro_id,"EMP-1"," ",version)
    assert repair_orders.get_ro_workspace(ro_id) == before
    result = repair_orders.complete_return_followup(ro_id,"EMP-2","Synthetic review completed",version)
    assert result["return_followup"]["status"] == "completed"
    assert result["return_followup"]["completed_by"] == "EMP-2"
    for key in ("status", "ro_stage", "concerns", "return_handover"):
        assert result[key] == before[key]
    assert "error" in repair_orders.complete_return_followup(ro_id,"EMP-2","Duplicate",result["return_followup"]["updated_at"])
    replanned = repair_orders.plan_return_followup(ro_id,"EMP-1","2026-10-20","Second review")
    assert replanned["return_followup"]["status"] == "planned"
    assert "outcome" not in replanned["return_followup"]
    assert len(ledger.get_entity(ro_id).attributes["return_followup_history"]) == 3


def test_followup_outcome_rejects_stale_plan_without_changes():
    ro_id = _planned_return_ro()
    before = repair_orders.get_ro_workspace(ro_id)
    assert "error" in repair_orders.complete_return_followup(ro_id,"EMP-1","Result","stale-version")
    assert repair_orders.get_ro_workspace(ro_id) == before
    assert "error" in repair_orders.complete_return_followup(_reviewed_return_ro(),"EMP-1","Result","")


@pytest.mark.parametrize("role", [SALES, MARKETING, FINANCE])
def test_followup_outcome_denied_roles_preserve_plan(role):
    ro_id = _planned_return_ro()
    before = repair_orders.get_ro_workspace(ro_id)
    assert "error" in repair_orders_api.complete_return_followup_api(role,"EMP-1",ro_id,"Result",before["return_followup"]["updated_at"])
    assert repair_orders.get_ro_workspace(ro_id) == before
