import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import DOCUMENT, DEAL, VEHICLE, CUSTOMER
from core import document_workflows
from core import document_workflows_api
from core import operations_tasks
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    # document_workflows.py calls save_graph directly (approve/reject_document),
    # AND request_document() delegates to operations_tasks.create_task(), which
    # has its own separate save_graph binding -- both must be patched.
    monkeypatch.setattr(document_workflows, "save_graph", lambda filepath: None)
    monkeypatch.setattr(operations_tasks, "save_graph", lambda filepath: None)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _add_deal(deal_id="DEAL-1", **overrides):
    attrs = {}
    attrs.update(overrides)
    ledger.add_entity(Entity(id=deal_id, entity_type=DEAL, attributes=attrs))
    return deal_id


def _add_vehicle(vehicle_id="VEH-1", **overrides):
    attrs = {"VIN": "1HGCM82633A004352"}
    attrs.update(overrides)
    ledger.add_entity(Entity(id=vehicle_id, entity_type=VEHICLE, attributes=attrs))
    return vehicle_id


def _add_customer(customer_id="CUST-1", **overrides):
    attrs = {"CustomerName": "Jane Doe"}
    attrs.update(overrides)
    ledger.add_entity(Entity(id=customer_id, entity_type=CUSTOMER, attributes=attrs))
    return customer_id


def _add_document(entity_id, document_type, doc_id=None, **overrides):
    attrs = {
        "EntityID": entity_id,
        "DocumentType": document_type,
        "FileName": f"{document_type}.pdf",
        "UploadedBy": "EMP-1",
        "CreatedAt": "2026-06-01T00:00:00+00:00",
    }
    attrs.update(overrides)
    did = doc_id or f"DOC-{document_type.replace(' ', '')}"
    ledger.add_entity(Entity(id=did, entity_type=DOCUMENT, attributes=attrs))
    return did


# ---------------------------------------------------------------------------
# get_deal_jacket_status / get_title_status (both thin wrappers over
# _completeness_check, tested through their real public entry points)
# ---------------------------------------------------------------------------


class TestDealJacketStatus:
    def test_unknown_deal_returns_error(self):
        result = document_workflows.get_deal_jacket_status("DEAL-NOPE")
        assert "error" in result

    def test_no_documents_missing_both_required_types(self):
        _add_deal()
        result = document_workflows.get_deal_jacket_status("DEAL-1")
        assert result["required_types"] == ["Deal Jacket", "Buyer Order"]
        assert set(result["missing_types"]) == {"Deal Jacket", "Buyer Order"}
        assert result["is_complete"] is False
        assert result["documents"] == []

    def test_partial_documents_still_incomplete(self):
        _add_deal()
        _add_document("DEAL-1", "Deal Jacket")
        result = document_workflows.get_deal_jacket_status("DEAL-1")
        assert result["missing_types"] == ["Buyer Order"]
        assert result["is_complete"] is False
        assert len(result["documents"]) == 1

    def test_both_required_types_present_is_complete(self):
        _add_deal()
        _add_document("DEAL-1", "Deal Jacket")
        _add_document("DEAL-1", "Buyer Order")
        result = document_workflows.get_deal_jacket_status("DEAL-1")
        assert result["missing_types"] == []
        assert result["is_complete"] is True
        assert len(result["documents"]) == 2

    def test_documents_for_other_entity_not_counted(self):
        _add_deal("DEAL-1")
        _add_deal("DEAL-2")
        _add_document("DEAL-2", "Deal Jacket")
        _add_document("DEAL-2", "Buyer Order")
        result = document_workflows.get_deal_jacket_status("DEAL-1")
        assert result["documents"] == []
        assert result["is_complete"] is False

    def test_entity_type_of_wrong_kind_rejected(self):
        _add_vehicle("VEH-1")
        result = document_workflows.get_deal_jacket_status("VEH-1")
        assert "error" in result


class TestTitleStatus:
    def test_unknown_vehicle_returns_error(self):
        result = document_workflows.get_title_status("VEH-NOPE")
        assert "error" in result

    def test_no_title_document_is_missing(self):
        _add_vehicle()
        result = document_workflows.get_title_status("VEH-1")
        assert result["required_types"] == ["Title"]
        assert result["missing_types"] == ["Title"]
        assert result["is_complete"] is False

    def test_title_on_file_is_complete(self):
        _add_vehicle()
        _add_document("VEH-1", "Title")
        result = document_workflows.get_title_status("VEH-1")
        assert result["missing_types"] == []
        assert result["is_complete"] is True


class TestDocBriefShape:
    def test_doc_brief_fields(self):
        _add_deal()
        _add_document("DEAL-1", "Deal Jacket", UploadedBy="EMP-7")
        result = document_workflows.get_deal_jacket_status("DEAL-1")
        doc = result["documents"][0]
        assert doc == {
            "id": "DOC-DealJacket",
            "document_type": "Deal Jacket",
            "file_name": "Deal Jacket.pdf",
            "uploaded_by": "EMP-7",
            "created_at": "2026-06-01T00:00:00+00:00",
            "approval_status": "pending",
        }

    def test_explicit_approval_status_surfaced(self):
        _add_deal()
        _add_document("DEAL-1", "Deal Jacket", approval_status="approved")
        result = document_workflows.get_deal_jacket_status("DEAL-1")
        assert result["documents"][0]["approval_status"] == "approved"


# ---------------------------------------------------------------------------
# request_document
# ---------------------------------------------------------------------------


class TestRequestDocument:
    def test_unknown_entity_rejected(self):
        result = document_workflows.request_document(DEAL, "DEAL-NOPE", "Deal Jacket", "EMP-1")
        assert isinstance(result, dict) and "error" in result

    def test_document_type_not_in_required_list_rejected(self):
        _add_deal()
        result = document_workflows.request_document(DEAL, "DEAL-1", "Title", "EMP-1")
        assert isinstance(result, dict) and "error" in result

    def test_valid_title_request_uses_title_processing_task_type(self):
        _add_vehicle()
        result = document_workflows.request_document(VEHICLE, "VEH-1", "Title", "EMP-1")
        assert result.attributes["task_type"] == "title_processing"
        assert result.attributes["owner_bucket"] == "Title Clerk"

    def test_valid_non_title_request_uses_document_request_task_type(self):
        _add_deal()
        result = document_workflows.request_document(DEAL, "DEAL-1", "Buyer Order", "EMP-1")
        assert result.attributes["task_type"] == "document_request"
        assert result.attributes["owner_bucket"] == "Accounting"

    def test_detail_includes_document_type_and_vin_label(self):
        _add_vehicle()
        result = document_workflows.request_document(VEHICLE, "VEH-1", "Title", "EMP-1")
        assert "Title requested" in result.attributes["detail"]
        assert "1HGCM82633A004352" in result.attributes["detail"]

    def test_detail_includes_notes_when_given(self):
        _add_vehicle()
        result = document_workflows.request_document(
            VEHICLE, "VEH-1", "Title", "EMP-1", notes="Customer misplaced original"
        )
        assert "Customer misplaced original" in result.attributes["detail"]

    def test_detail_falls_back_to_entity_id_when_no_vin_or_customer_name(self):
        _add_deal()
        result = document_workflows.request_document(DEAL, "DEAL-1", "Buyer Order", "EMP-1")
        assert "DEAL-1" in result.attributes["detail"]

    def test_created_by_recorded(self):
        _add_deal()
        result = document_workflows.request_document(DEAL, "DEAL-1", "Deal Jacket", "EMP-42")
        assert result.attributes["created_by"] == "EMP-42"

    def test_linked_entity_id_set(self):
        _add_deal()
        result = document_workflows.request_document(DEAL, "DEAL-1", "Deal Jacket", "EMP-1")
        assert result.attributes["linked_entity_id"] == "DEAL-1"

    def test_customer_compliance_file_request(self):
        _add_customer()
        result = document_workflows.request_document(
            CUSTOMER, "CUST-1", "Compliance File", "EMP-1"
        )
        assert result.attributes["task_type"] == "document_request"
        # CustomerName is the label fallback for a Customer entity (no VIN attribute).
        assert "Jane Doe" in result.attributes["detail"]
        assert "Compliance File requested" in result.attributes["detail"]


# ---------------------------------------------------------------------------
# get_document_packet
# ---------------------------------------------------------------------------


class TestGetDocumentPacket:
    def test_invalid_entity_type_rejected(self):
        result = document_workflows.get_document_packet("Bogus", "DEAL-1")
        assert "error" in result

    def test_valid_entity_type_unknown_entity_propagates_not_found(self):
        result = document_workflows.get_document_packet(DEAL, "DEAL-NOPE")
        assert "error" in result

    def test_valid_entity_type_real_entity_returns_completeness_shape(self):
        _add_deal()
        _add_document("DEAL-1", "Deal Jacket")
        result = document_workflows.get_document_packet(DEAL, "DEAL-1")
        assert result["is_complete"] is False
        assert result["missing_types"] == ["Buyer Order"]
        assert len(result["documents"]) == 1

    def test_full_packet_when_everything_on_file(self):
        _add_vehicle()
        _add_document("VEH-1", "Title")
        result = document_workflows.get_document_packet(VEHICLE, "VEH-1")
        assert result["is_complete"] is True


# ---------------------------------------------------------------------------
# approve_document / reject_document
# ---------------------------------------------------------------------------


class TestApproveDocument:
    def test_unknown_document_rejected(self):
        result = document_workflows.approve_document("DOC-NOPE", "EMP-1")
        assert "error" in result

    def test_valid_approval_sets_fields(self):
        _add_deal()
        _add_document("DEAL-1", "Deal Jacket")
        result = document_workflows.approve_document(
            "DOC-DealJacket", "EMP-2", notes="Looks good"
        )
        assert result["approval_status"] == "approved"
        doc = ledger.get_entity("DOC-DealJacket")
        assert doc.attributes["approval_status"] == "approved"
        assert doc.attributes["approval_notes"] == "Looks good"
        assert doc.attributes["approved_by"] == "EMP-2"
        assert doc.attributes["approval_updated_at"] is not None

    def test_default_notes_empty_string(self):
        _add_deal()
        _add_document("DEAL-1", "Deal Jacket")
        document_workflows.approve_document("DOC-DealJacket", "EMP-2")
        doc = ledger.get_entity("DOC-DealJacket")
        assert doc.attributes["approval_notes"] == ""

    def test_returns_doc_brief_shape(self):
        _add_deal()
        _add_document("DEAL-1", "Deal Jacket")
        result = document_workflows.approve_document("DOC-DealJacket", "EMP-2")
        assert set(result.keys()) == {
            "id", "document_type", "file_name", "uploaded_by", "created_at", "approval_status",
        }


class TestRejectDocument:
    def test_unknown_document_rejected(self):
        result = document_workflows.reject_document("DOC-NOPE", "EMP-1", reason="Bad scan")
        assert "error" in result

    def test_missing_reason_rejected(self):
        _add_deal()
        _add_document("DEAL-1", "Deal Jacket")
        result = document_workflows.reject_document("DOC-DealJacket", "EMP-1")
        assert result["error"] == "A reason is required to reject a document"

    def test_empty_string_reason_rejected(self):
        _add_deal()
        _add_document("DEAL-1", "Deal Jacket")
        result = document_workflows.reject_document("DOC-DealJacket", "EMP-1", reason="")
        assert "error" in result

    def test_valid_rejection_sets_fields(self):
        _add_deal()
        _add_document("DEAL-1", "Deal Jacket")
        result = document_workflows.reject_document(
            "DOC-DealJacket", "EMP-3", reason="Illegible scan"
        )
        assert result["approval_status"] == "rejected"
        doc = ledger.get_entity("DOC-DealJacket")
        assert doc.attributes["approval_status"] == "rejected"
        assert doc.attributes["approval_notes"] == "Illegible scan"
        assert doc.attributes["approved_by"] == "EMP-3"
        assert doc.attributes["approval_updated_at"] is not None

    def test_rejection_does_not_persist_without_reason(self):
        _add_deal()
        _add_document("DEAL-1", "Deal Jacket")
        document_workflows.reject_document("DOC-DealJacket", "EMP-1")
        doc = ledger.get_entity("DOC-DealJacket")
        assert "approval_status" not in doc.attributes


# ---------------------------------------------------------------------------
# list_pending_approvals
# ---------------------------------------------------------------------------


class TestListPendingApprovals:
    def test_empty_state(self):
        result = document_workflows.list_pending_approvals()
        assert result == {"count": 0, "documents": []}

    def test_document_with_no_approval_status_counted_as_pending(self):
        _add_deal()
        _add_document("DEAL-1", "Deal Jacket")
        result = document_workflows.list_pending_approvals()
        assert result["count"] == 1
        assert result["documents"][0]["approval_status"] == "pending"

    def test_explicit_pending_counted(self):
        _add_deal()
        _add_document("DEAL-1", "Deal Jacket", approval_status="pending")
        result = document_workflows.list_pending_approvals()
        assert result["count"] == 1

    def test_approved_excluded(self):
        _add_deal()
        _add_document("DEAL-1", "Deal Jacket", approval_status="approved")
        result = document_workflows.list_pending_approvals()
        assert result["count"] == 0

    def test_rejected_excluded(self):
        _add_deal()
        _add_document("DEAL-1", "Deal Jacket", approval_status="rejected")
        result = document_workflows.list_pending_approvals()
        assert result["count"] == 0

    def test_sorted_most_recently_created_first(self):
        _add_deal()
        _add_document("DEAL-1", "Deal Jacket", doc_id="DOC-A", CreatedAt="2026-06-01T00:00:00+00:00")
        _add_document("DEAL-1", "Buyer Order", doc_id="DOC-B", CreatedAt="2026-06-05T00:00:00+00:00")
        result = document_workflows.list_pending_approvals()
        assert [d["id"] for d in result["documents"]] == ["DOC-B", "DOC-A"]

    def test_limit_caps_documents_but_count_reflects_total(self):
        for i in range(5):
            _add_deal(f"DEAL-{i}")
            _add_document(f"DEAL-{i}", "Deal Jacket", doc_id=f"DOC-{i}")
        result = document_workflows.list_pending_approvals(limit=2)
        assert result["count"] == 5
        assert len(result["documents"]) == 2


# ---------------------------------------------------------------------------
# API layer -- role gating + entity_type string mapping
# ---------------------------------------------------------------------------


_VIEW_ALLOWED = [ADMIN, OPERATIONS, SALES, SERVICE, MARKETING, FINANCE]
_VIEW_DENIED = ["BOGUS_ROLE"]

_MUTATE_ALLOWED = [ADMIN, OPERATIONS]
_MUTATE_DENIED = [SALES, SERVICE, MARKETING, FINANCE, "BOGUS_ROLE"]


class TestAcl:
    @pytest.mark.parametrize("role", _VIEW_DENIED)
    def test_get_deal_jacket_status_denied(self, role):
        _add_deal()
        result = document_workflows_api.get_deal_jacket_status_api(role, "DEAL-1")
        assert "error" in result

    @pytest.mark.parametrize("role", _VIEW_ALLOWED)
    def test_get_deal_jacket_status_allowed(self, role):
        ledger.reset()
        _add_deal()
        result = document_workflows_api.get_deal_jacket_status_api(role, "DEAL-1")
        assert "is_complete" in result

    @pytest.mark.parametrize("role", _VIEW_DENIED)
    def test_get_title_status_denied(self, role):
        _add_vehicle()
        result = document_workflows_api.get_title_status_api(role, "VEH-1")
        assert "error" in result

    @pytest.mark.parametrize("role", _VIEW_ALLOWED)
    def test_get_title_status_allowed(self, role):
        ledger.reset()
        _add_vehicle()
        result = document_workflows_api.get_title_status_api(role, "VEH-1")
        assert "is_complete" in result

    @pytest.mark.parametrize("role", _MUTATE_DENIED)
    def test_request_document_denied(self, role):
        _add_deal()
        result = document_workflows_api.request_document_api(
            role, "EMP-1", "Deal", "DEAL-1", "Deal Jacket"
        )
        assert "error" in result

    @pytest.mark.parametrize("role", _MUTATE_ALLOWED)
    def test_request_document_allowed(self, role):
        ledger.reset()
        _add_deal()
        result = document_workflows_api.request_document_api(
            role, "EMP-1", "Deal", "DEAL-1", "Deal Jacket"
        )
        assert result["task_type"] == "document_request"

    def test_request_document_serializes_to_flat_dict(self):
        _add_deal()
        result = document_workflows_api.request_document_api(
            ADMIN, "EMP-1", "Deal", "DEAL-1", "Deal Jacket"
        )
        assert isinstance(result, dict)
        assert "id" in result
        assert "attributes" not in result

    def test_request_document_bad_entity_type_string_rejected_for_allowed_role(self):
        _add_deal()
        result = document_workflows_api.request_document_api(
            ADMIN, "EMP-1", "Bogus", "DEAL-1", "Deal Jacket"
        )
        assert "error" in result

    @pytest.mark.parametrize("role", _VIEW_DENIED)
    def test_get_document_packet_denied(self, role):
        _add_deal()
        result = document_workflows_api.get_document_packet_api(role, "Deal", "DEAL-1")
        assert "error" in result

    @pytest.mark.parametrize("role", _VIEW_ALLOWED)
    def test_get_document_packet_allowed(self, role):
        ledger.reset()
        _add_deal()
        result = document_workflows_api.get_document_packet_api(role, "Deal", "DEAL-1")
        assert "is_complete" in result

    def test_get_document_packet_bad_entity_type_string(self):
        result = document_workflows_api.get_document_packet_api(ADMIN, "Bogus", "DEAL-1")
        assert "error" in result

    @pytest.mark.parametrize("role", _MUTATE_DENIED)
    def test_approve_document_denied(self, role):
        _add_deal()
        _add_document("DEAL-1", "Deal Jacket")
        result = document_workflows_api.approve_document_api(role, "EMP-1", "DOC-DealJacket")
        assert "error" in result

    @pytest.mark.parametrize("role", _MUTATE_ALLOWED)
    def test_approve_document_allowed(self, role):
        ledger.reset()
        _add_deal()
        _add_document("DEAL-1", "Deal Jacket")
        result = document_workflows_api.approve_document_api(role, "EMP-1", "DOC-DealJacket")
        assert result["approval_status"] == "approved"

    @pytest.mark.parametrize("role", _MUTATE_DENIED)
    def test_reject_document_denied(self, role):
        _add_deal()
        _add_document("DEAL-1", "Deal Jacket")
        result = document_workflows_api.reject_document_api(
            role, "EMP-1", "DOC-DealJacket", reason="Bad scan"
        )
        assert "error" in result

    @pytest.mark.parametrize("role", _MUTATE_ALLOWED)
    def test_reject_document_allowed(self, role):
        ledger.reset()
        _add_deal()
        _add_document("DEAL-1", "Deal Jacket")
        result = document_workflows_api.reject_document_api(
            role, "EMP-1", "DOC-DealJacket", reason="Bad scan"
        )
        assert result["approval_status"] == "rejected"

    @pytest.mark.parametrize("role", _VIEW_DENIED)
    def test_list_pending_approvals_denied(self, role):
        result = document_workflows_api.list_pending_approvals_api(role)
        assert "error" in result

    @pytest.mark.parametrize("role", _VIEW_ALLOWED)
    def test_list_pending_approvals_allowed(self, role):
        ledger.reset()
        result = document_workflows_api.list_pending_approvals_api(role)
        assert result == {"count": 0, "documents": []}
