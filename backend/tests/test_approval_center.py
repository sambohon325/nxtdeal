"""
Tests for core/approval_center.py / core/approval_center_api.py -- the
Customer-Facing Approval Center: a real, unguessable per-RO approval link
(generate/status/revoke, staff-facing) plus a genuinely unauthenticated
public read/write pair a real customer uses to view and decide on their own
estimate, recorded with the honest CUSTOMER_SENTINEL rather than any real
employee id.

Reuses test_repair_orders.py's own vehicle/customer/RO fixture helpers
(same shapes) rather than re-deriving them.

Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import VEHICLE, CUSTOMER
from core import repair_orders
from core import approval_center
from core import approval_center_api
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    monkeypatch.setattr(repair_orders, "save_graph", lambda filepath: None)
    monkeypatch.setattr(approval_center, "save_graph", lambda filepath: None)


_VIEW_ROLES = (ADMIN, OPERATIONS, SALES, SERVICE, FINANCE)
_VIEW_DENIED_ROLES = (MARKETING,)
_MUTATE_ROLES = (ADMIN, OPERATIONS, SERVICE)
_MUTATE_DENIED_ROLES = (SALES, MARKETING, FINANCE)


def _add_vehicle(vehicle_id="VEH-1"):
    ledger.add_entity(Entity(id=vehicle_id, entity_type=VEHICLE, attributes={
        "VIN": "VIN1", "Make": "Honda", "Model": "Civic", "Year": "2025",
    }))
    return vehicle_id


def _add_customer(customer_id="CUST-1"):
    ledger.add_entity(Entity(id=customer_id, entity_type=CUSTOMER, attributes={
        "CustomerID": "C1", "FirstName": "Jane", "LastName": "Doe",
    }))
    return customer_id


def _new_ro(with_estimate=False, amount=500.0):
    _add_vehicle()
    _add_customer()
    result = repair_orders.create_repair_order("VEH-1", "CUST-1", "Strange noise", "EMP-1")
    assert "error" not in result
    ro_id = result["id"]
    if with_estimate:
        repair_orders.send_estimate(ro_id, amount, "EMP-1")
    return ro_id


def _flagged_dvi(ro_id):
    ro = ledger.get_entity(ro_id)
    ro.attributes["dvi"] = {
        "items": {
            "tires.tread_depth": {
                "category": "tires", "item": "Tread Depth", "status": "red", "notes": "worn"
            },
            "brakes.front_pads": {
                "category": "brakes", "item": "Front Pads", "status": "green", "notes": ""
            },
        }
    }


class TestGenerateApprovalLink:

    def test_unknown_ro_returns_an_error(self):
        result = approval_center.generate_approval_link("SRV-BOGUS", "EMP-1")

        assert "error" in result

    def test_without_an_estimate_on_file_returns_an_error_and_creates_no_link(self):
        ro_id = _new_ro(with_estimate=False)

        result = approval_center.generate_approval_link(ro_id, "EMP-1")

        assert "error" in result
        assert ledger.get_entity(ro_id).attributes.get("approval_link") is None

    def test_with_an_estimate_on_file_creates_a_real_unguessable_link(self):
        ro_id = _new_ro(with_estimate=True)

        result = approval_center.generate_approval_link(ro_id, "EMP-1")

        assert "error" not in result
        assert result["ro_id"] == ro_id
        assert len(result["token"]) > 20
        assert result["path"] == f"/approve/{result['token']}"

    def test_the_link_is_stored_on_the_ro_with_the_real_metadata(self):
        ro_id = _new_ro(with_estimate=True)

        result = approval_center.generate_approval_link(ro_id, "EMP-1")

        link = ledger.get_entity(ro_id).attributes["approval_link"]
        assert link["token"] == result["token"]
        assert link["created_by"] == "EMP-1"
        assert link["created_at"] is not None
        assert link["revoked"] is False

    def test_two_calls_produce_two_different_tokens(self):
        ro_id = _new_ro(with_estimate=True)

        first = approval_center.generate_approval_link(ro_id, "EMP-1")
        second = approval_center.generate_approval_link(ro_id, "EMP-2")

        assert first["token"] != second["token"]


class TestGetApprovalLinkStatus:

    def test_unknown_ro_returns_an_error(self):
        result = approval_center.get_approval_link_status("SRV-BOGUS")

        assert "error" in result

    def test_no_link_exists_reports_exists_false(self):
        ro_id = _new_ro(with_estimate=True)

        result = approval_center.get_approval_link_status(ro_id)

        assert result == {"ro_id": ro_id, "exists": False}

    def test_a_real_link_reports_exists_true_with_its_metadata_and_path(self):
        ro_id = _new_ro(with_estimate=True)
        created = approval_center.generate_approval_link(ro_id, "EMP-1")

        result = approval_center.get_approval_link_status(ro_id)

        assert result["exists"] is True
        assert result["token"] == created["token"]
        assert result["path"] == f"/approve/{created['token']}"
        assert result["revoked"] is False


class TestRevokeApprovalLink:

    def test_unknown_ro_returns_an_error(self):
        result = approval_center.revoke_approval_link("SRV-BOGUS", "EMP-1")

        assert "error" in result

    def test_no_link_exists_returns_an_error(self):
        ro_id = _new_ro(with_estimate=True)

        result = approval_center.revoke_approval_link(ro_id, "EMP-1")

        assert "error" in result

    def test_a_successful_revoke_marks_the_link_revoked(self):
        ro_id = _new_ro(with_estimate=True)
        approval_center.generate_approval_link(ro_id, "EMP-1")

        result = approval_center.revoke_approval_link(ro_id, "EMP-2")

        assert result == {"ro_id": ro_id, "revoked": True}
        link = ledger.get_entity(ro_id).attributes["approval_link"]
        assert link["revoked"] is True
        assert link["revoked_by"] == "EMP-2"
        assert link["revoked_at"] is not None

    def test_revoking_an_already_revoked_link_returns_an_error(self):
        ro_id = _new_ro(with_estimate=True)
        approval_center.generate_approval_link(ro_id, "EMP-1")
        approval_center.revoke_approval_link(ro_id, "EMP-1")

        result = approval_center.revoke_approval_link(ro_id, "EMP-1")

        assert "error" in result


class TestGetPublicApprovalView:

    def test_an_unknown_token_returns_an_honest_invalid_link_error(self):
        result = approval_center.get_public_approval_view("bogus-token")

        assert "error" in result
        assert "invalid" in result["error"].lower()

    def test_a_real_token_returns_the_full_real_view(self):
        ro_id = _new_ro(with_estimate=True, amount=750.0)
        link = approval_center.generate_approval_link(ro_id, "EMP-1")

        result = approval_center.get_public_approval_view(link["token"])

        assert result["revoked"] is False
        assert result["customer_name"] == "Jane Doe"
        assert result["vehicle"] == "2025 Honda Civic"
        assert result["estimate"]["amount"] == 750.0
        assert result["estimate"]["approved"] is None
        assert result["estimate"]["decided_by_customer"] is False

    def test_only_open_concerns_are_included(self):
        ro_id = _new_ro(with_estimate=True)
        # create_repair_order already seeds an initial concern off the RO's own
        # description ("Strange noise") -- resolve that one, add a fresh one, and
        # confirm only the still-open one survives the public filter.
        repair_orders.add_concern(ro_id, "Still noisy", "EMP-1")
        ro = ledger.get_entity(ro_id)
        initial_concern = next(c for c in ro.attributes["concerns"] if c["description"] == "Strange noise")
        assert "error" not in repair_orders.resolve_concern(ro_id, initial_concern["id"], "EMP-1", resolution_notes="Verified repair in fictional fixture")
        link = approval_center.generate_approval_link(ro_id, "EMP-1")

        result = approval_center.get_public_approval_view(link["token"])

        assert len(result["open_concerns"]) == 1
        assert result["open_concerns"][0]["description"] == "Still noisy"

    def test_only_flagged_yellow_or_red_dvi_findings_are_included(self):
        ro_id = _new_ro(with_estimate=True)
        _flagged_dvi(ro_id)
        link = approval_center.generate_approval_link(ro_id, "EMP-1")

        result = approval_center.get_public_approval_view(link["token"])

        assert len(result["flagged_inspection_findings"]) == 1
        assert result["flagged_inspection_findings"][0]["item"] == "Tread Depth"
        assert result["flagged_inspection_findings"][0]["status"] == "red"

    def test_a_revoked_link_still_renders_read_only_rather_than_erroring(self):
        ro_id = _new_ro(with_estimate=True)
        link = approval_center.generate_approval_link(ro_id, "EMP-1")
        approval_center.revoke_approval_link(ro_id, "EMP-1")

        result = approval_center.get_public_approval_view(link["token"])

        assert "error" not in result
        assert result["revoked"] is True

    def test_decided_by_customer_is_true_once_the_public_decision_path_is_used(self):
        ro_id = _new_ro(with_estimate=True)
        link = approval_center.generate_approval_link(ro_id, "EMP-1")
        approval_center.record_public_approval_decision(link["token"], True)

        result = approval_center.get_public_approval_view(link["token"])

        assert result["estimate"]["decided_by_customer"] is True
        assert result["estimate"]["approved"] is True

    def test_no_customer_or_vehicle_on_file_does_not_raise(self):
        # Build an RO with a vehicle/customer that get deleted from the ledger
        # afterward, to exercise the "no customer/vehicle" None-safe branches.
        ro_id = _new_ro(with_estimate=True)
        link = approval_center.generate_approval_link(ro_id, "EMP-1")
        del ledger.entities["CUST-1"]
        del ledger.entities["VEH-1"]

        result = approval_center.get_public_approval_view(link["token"])

        assert "error" not in result
        assert result["customer_name"] is None
        assert result["vehicle"] is None


class TestRecordPublicApprovalDecision:

    def test_an_unknown_token_returns_an_error(self):
        result = approval_center.record_public_approval_decision("bogus-token", True)

        assert "error" in result

    def test_a_revoked_link_rejects_a_decision(self):
        ro_id = _new_ro(with_estimate=True)
        link = approval_center.generate_approval_link(ro_id, "EMP-1")
        approval_center.revoke_approval_link(ro_id, "EMP-1")

        result = approval_center.record_public_approval_decision(link["token"], True)

        assert "error" in result
        assert "revoked" in result["error"].lower()

    def test_declining_without_a_reason_is_rejected_and_records_nothing(self):
        ro_id = _new_ro(with_estimate=True)
        link = approval_center.generate_approval_link(ro_id, "EMP-1")

        result = approval_center.record_public_approval_decision(link["token"], False)

        assert "error" in result
        estimate = ledger.get_entity(ro_id).attributes["estimate"]
        assert estimate["approved"] is None

    def test_declining_whitespace_only_reason_is_rejected(self):
        ro_id = _new_ro(with_estimate=True)
        link = approval_center.generate_approval_link(ro_id, "EMP-1")

        result = approval_center.record_public_approval_decision(link["token"], False, decline_reason="   ")

        assert "error" in result

    def test_a_second_decision_after_one_already_recorded_is_rejected(self):
        ro_id = _new_ro(with_estimate=True)
        link = approval_center.generate_approval_link(ro_id, "EMP-1")
        approval_center.record_public_approval_decision(link["token"], True)

        result = approval_center.record_public_approval_decision(link["token"], True)

        assert "error" in result
        assert "already" in result["error"].lower()

    def test_a_real_approval_is_recorded_with_the_honest_customer_sentinel(self):
        ro_id = _new_ro(with_estimate=True)
        link = approval_center.generate_approval_link(ro_id, "EMP-1")

        result = approval_center.record_public_approval_decision(link["token"], True)

        assert "error" not in result
        estimate = ledger.get_entity(ro_id).attributes["estimate"]
        assert estimate["approved"] is True
        assert estimate["approved_by"] == approval_center.CUSTOMER_SENTINEL

    def test_a_real_decline_with_a_reason_is_recorded_correctly(self):
        ro_id = _new_ro(with_estimate=True)
        link = approval_center.generate_approval_link(ro_id, "EMP-1")

        result = approval_center.record_public_approval_decision(
            link["token"], False, decline_reason="too expensive"
        )

        assert "error" not in result
        estimate = ledger.get_entity(ro_id).attributes["estimate"]
        assert estimate["approved"] is False
        assert estimate["decline_reason"] == "too expensive"

    def test_a_successful_decision_returns_the_updated_public_view(self):
        ro_id = _new_ro(with_estimate=True)
        link = approval_center.generate_approval_link(ro_id, "EMP-1")

        result = approval_center.record_public_approval_decision(link["token"], True)

        assert result["estimate"]["approved"] is True
        assert result["estimate"]["decided_by_customer"] is True


class TestApprovalCenterApiRoleGating:

    def test_generate_link_is_denied_to_a_non_mutate_role(self):
        ro_id = _new_ro(with_estimate=True)

        for role in _MUTATE_DENIED_ROLES:
            result = approval_center_api.generate_approval_link_api(role, ro_id, "EMP-1")
            assert "error" in result

    def test_generate_link_succeeds_for_every_mutate_role(self):
        for role in _MUTATE_ROLES:
            ledger.reset()
            ro_id = _new_ro(with_estimate=True)
            result = approval_center_api.generate_approval_link_api(role, ro_id, "EMP-1")
            assert "error" not in result

    def test_view_status_is_denied_to_a_non_view_role(self):
        ro_id = _new_ro(with_estimate=True)

        for role in _VIEW_DENIED_ROLES:
            result = approval_center_api.get_approval_link_status_api(role, ro_id)
            assert "error" in result

    def test_view_status_succeeds_for_every_view_role(self):
        ro_id = _new_ro(with_estimate=True)

        for role in _VIEW_ROLES:
            result = approval_center_api.get_approval_link_status_api(role, ro_id)
            assert "error" not in result

    def test_revoke_is_denied_to_a_non_mutate_role(self):
        ro_id = _new_ro(with_estimate=True)
        approval_center.generate_approval_link(ro_id, "EMP-1")

        for role in _MUTATE_DENIED_ROLES:
            result = approval_center_api.revoke_approval_link_api(role, ro_id, "EMP-1")
            assert "error" in result

    def test_revoke_succeeds_for_a_mutate_role(self):
        ro_id = _new_ro(with_estimate=True)
        approval_center.generate_approval_link(ro_id, "EMP-1")

        result = approval_center_api.revoke_approval_link_api(ADMIN, ro_id, "EMP-1")

        assert result == {"ro_id": ro_id, "revoked": True}
