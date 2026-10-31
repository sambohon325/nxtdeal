"""
Tests for core/esignature.py + core/esignature_api.py -- eSignature (session
104 follow-up): a real signing envelope snapshotting a Deal's generated
contract, an ESIGN-Act-style consent gate before signing, a typed-name
signature capture, and a decline-voids-the-whole-envelope rule.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import SIGNATURE_REQUEST, DEAL, CUSTOMER
from core import esignature
from core import esignature_api
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE


@pytest.fixture(autouse=True)
def fresh_ledger(monkeypatch):
    # Typed-name execution is supported only in the isolated sample-data demo.
    monkeypatch.setenv("DEALEROS_DEMO", "1")
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    monkeypatch.setattr(esignature, "save_graph", lambda filepath: None)


_ALLOWED_ROLES = (ADMIN, OPERATIONS, SALES, FINANCE)
_DENIED_ROLES = (MARKETING, SERVICE)


def _add_customer(customer_id="CUST-1", first="Jane", last="Doe"):
    ledger.add_entity(Entity(id=customer_id, entity_type=CUSTOMER, attributes={"FirstName": first, "LastName": last}))
    return customer_id


def _add_deal(deal_id="DEAL-1", with_contract=True, customer_id="CUST-1", amount="25000"):
    attrs = {"customer_id": customer_id}
    if with_contract:
        attrs["contract"] = {"customer_id": customer_id, "amount_financed": amount}
    ledger.add_entity(Entity(id=deal_id, entity_type=DEAL, attributes=attrs))
    return deal_id


_VALID_SIGNERS = [{"name": "Jane Doe", "role": "customer"}]


def _start_valid_request(**overrides):
    _add_customer()
    _add_deal()
    signers = overrides.pop("signers", _VALID_SIGNERS)
    result = esignature.create_signature_request("DEAL-1", "EMP-1", signers)
    assert "error" not in result.attributes if hasattr(result, "attributes") else True
    return result


def _sent_request_index(index=0):
    req = _start_valid_request()
    esignature.send_signature_request(req.id)
    return req.id, index


# ---------------------------------------------------------------------------
# create_signature_request
# ---------------------------------------------------------------------------

class TestCreateSignatureRequest:
    def test_rejects_non_deal_linked_id(self):
        result = esignature.create_signature_request("VEH-1", "EMP-1", _VALID_SIGNERS)
        assert "error" in result

    def test_rejects_deal_with_no_contract(self):
        _add_deal(with_contract=False)
        result = esignature.create_signature_request("DEAL-1", "EMP-1", _VALID_SIGNERS)
        assert "error" in result

    def test_rejects_empty_signers(self):
        _add_deal()
        result = esignature.create_signature_request("DEAL-1", "EMP-1", [])
        assert "error" in result

    def test_rejects_signer_missing_name(self):
        _add_deal()
        result = esignature.create_signature_request("DEAL-1", "EMP-1", [{"name": "  ", "role": "customer"}])
        assert "error" in result

    def test_rejects_bad_signer_role(self):
        _add_deal()
        result = esignature.create_signature_request("DEAL-1", "EMP-1", [{"name": "Jane Doe", "role": "witness"}])
        assert "error" in result

    def test_succeeds_with_valid_signers(self):
        req = _start_valid_request()
        assert req.attributes["status"] == "draft"
        assert len(req.attributes["signers"]) == 1
        assert req.attributes["signers"][0]["name"] == "Jane Doe"
        assert req.attributes["signers"][0]["status"] == "pending"

    def test_snapshots_the_contract_at_creation_time(self):
        req = _start_valid_request()
        assert req.attributes["contract_snapshot"]["amount_financed"] == "25000"

    def test_contract_snapshot_is_a_copy_not_a_live_reference(self):
        req = _start_valid_request()
        deal = ledger.get_entity("DEAL-1")
        deal.attributes["contract"]["amount_financed"] = "99999"
        assert req.attributes["contract_snapshot"]["amount_financed"] == "25000"

    def test_creates_a_real_entity_on_the_ledger(self):
        req = _start_valid_request()
        stored = ledger.get_entity(req.id)
        assert stored is not None
        assert stored.entity_type == SIGNATURE_REQUEST


# ---------------------------------------------------------------------------
# add_signer / remove_signer
# ---------------------------------------------------------------------------

class TestAddSigner:
    def test_rejects_unknown_request(self):
        result = esignature.add_signer("SIGN-BAD", "John Q", "co_signer")
        assert "error" in result

    def test_rejects_once_no_longer_a_draft(self):
        req = _start_valid_request()
        esignature.send_signature_request(req.id)
        result = esignature.add_signer(req.id, "John Q", "co_signer")
        assert "error" in result

    def test_rejects_empty_name(self):
        req = _start_valid_request()
        result = esignature.add_signer(req.id, "  ", "co_signer")
        assert "error" in result

    def test_rejects_bad_role(self):
        req = _start_valid_request()
        result = esignature.add_signer(req.id, "John Q", "witness")
        assert "error" in result

    def test_appends_a_real_signer(self):
        req = _start_valid_request()
        result = esignature.add_signer(req.id, "John Q", "co_signer", email="j@example.com")
        assert len(result.attributes["signers"]) == 2
        assert result.attributes["signers"][1]["email"] == "j@example.com"


class TestRemoveSigner:
    def test_rejects_unknown_request(self):
        result = esignature.remove_signer("SIGN-BAD", 0)
        assert "error" in result

    def test_rejects_once_no_longer_a_draft(self):
        req = _start_valid_request()
        esignature.send_signature_request(req.id)
        result = esignature.remove_signer(req.id, 0)
        assert "error" in result

    def test_rejects_bad_index(self):
        req = _start_valid_request()
        result = esignature.remove_signer(req.id, 5)
        assert "error" in result

    def test_removes_a_signer(self):
        req = _start_valid_request()
        esignature.add_signer(req.id, "John Q", "co_signer")
        result = esignature.remove_signer(req.id, 1)
        assert len(result.attributes["signers"]) == 1


# ---------------------------------------------------------------------------
# send_signature_request
# ---------------------------------------------------------------------------

class TestSendSignatureRequest:
    def test_rejects_unknown_request(self):
        result = esignature.send_signature_request("SIGN-BAD")
        assert "error" in result

    def test_rejects_when_already_sent(self):
        req = _start_valid_request()
        esignature.send_signature_request(req.id)
        result = esignature.send_signature_request(req.id)
        assert "error" in result

    def test_rejects_with_no_signers(self):
        _add_customer()
        _add_deal()
        req = esignature.create_signature_request("DEAL-1", "EMP-1", _VALID_SIGNERS)
        esignature.remove_signer(req.id, 0)
        result = esignature.send_signature_request(req.id)
        assert "error" in result

    def test_succeeds(self):
        req = _start_valid_request()
        result = esignature.send_signature_request(req.id)
        assert result.attributes["status"] == "sent"
        assert result.attributes["sent_at"] is not None


# ---------------------------------------------------------------------------
# capture_signer_consent
# ---------------------------------------------------------------------------

class TestCaptureConsent:
    def test_rejects_unknown_request(self):
        result = esignature.capture_signer_consent("SIGN-BAD", 0)
        assert "error" in result

    def test_rejects_before_sending(self):
        req = _start_valid_request()
        result = esignature.capture_signer_consent(req.id, 0)
        assert "error" in result

    def test_rejects_bad_index(self):
        req_id, _ = _sent_request_index()
        result = esignature.capture_signer_consent(req_id, 9)
        assert "error" in result

    def test_rejects_when_signer_already_signed(self):
        req_id, idx = _sent_request_index()
        esignature.capture_signer_consent(req_id, idx)
        esignature.sign(req_id, idx, "Jane Doe")
        result = esignature.capture_signer_consent(req_id, idx)
        assert "error" in result

    def test_succeeds(self):
        req_id, idx = _sent_request_index()
        result = esignature.capture_signer_consent(req_id, idx)
        assert result.attributes["signers"][idx]["esign_consent"] is True
        assert result.attributes["signers"][idx]["esign_consent_at"] is not None


# ---------------------------------------------------------------------------
# sign
# ---------------------------------------------------------------------------

class TestSign:
    def test_rejects_unknown_request(self):
        result = esignature.sign("SIGN-BAD", 0, "Jane Doe")
        assert "error" in result

    def test_rejects_before_sending(self):
        req = _start_valid_request()
        result = esignature.sign(req.id, 0, "Jane Doe")
        assert "error" in result

    def test_rejects_bad_index(self):
        req_id, _ = _sent_request_index()
        result = esignature.sign(req_id, 9, "Jane Doe")
        assert "error" in result

    def test_rejects_without_consent(self):
        req_id, idx = _sent_request_index()
        result = esignature.sign(req_id, idx, "Jane Doe")
        assert "error" in result

    def test_rejects_empty_typed_signature(self):
        req_id, idx = _sent_request_index()
        esignature.capture_signer_consent(req_id, idx)
        result = esignature.sign(req_id, idx, "   ")
        assert "error" in result

    def test_rejects_mismatched_name(self):
        req_id, idx = _sent_request_index()
        esignature.capture_signer_consent(req_id, idx)
        result = esignature.sign(req_id, idx, "Bob Smith")
        assert "error" in result

    def test_succeeds_with_a_reasonably_matching_name(self):
        req_id, idx = _sent_request_index()
        esignature.capture_signer_consent(req_id, idx)
        result = esignature.sign(req_id, idx, "jane doe")
        assert result.attributes["signers"][idx]["status"] == "signed"
        assert result.attributes["signers"][idx]["typed_signature"] == "jane doe"
        assert result.attributes["signers"][idx]["verification_note"] == esignature._VERIFICATION_NOTE

    def test_rejects_signing_twice(self):
        req_id, idx = _sent_request_index()
        esignature.capture_signer_consent(req_id, idx)
        esignature.sign(req_id, idx, "Jane Doe")
        result = esignature.sign(req_id, idx, "Jane Doe")
        assert "error" in result

    def test_envelope_auto_completes_once_every_signer_has_signed(self):
        req = _start_valid_request()
        esignature.add_signer(req.id, "John Q", "co_signer")
        esignature.send_signature_request(req.id)

        esignature.capture_signer_consent(req.id, 0)
        result = esignature.sign(req.id, 0, "Jane Doe")
        assert result.attributes["status"] == "sent"

        esignature.capture_signer_consent(req.id, 1)
        result = esignature.sign(req.id, 1, "John Q")
        assert result.attributes["status"] == "completed"
        assert result.attributes["completed_at"] is not None


# ---------------------------------------------------------------------------
# decline_signer
# ---------------------------------------------------------------------------

class TestDeclineSigner:
    def test_rejects_unknown_request(self):
        result = esignature.decline_signer("SIGN-BAD", 0, "Changed mind")
        assert "error" in result

    def test_rejects_before_sending(self):
        req = _start_valid_request()
        result = esignature.decline_signer(req.id, 0, "Changed mind")
        assert "error" in result

    def test_rejects_empty_reason(self):
        req_id, idx = _sent_request_index()
        result = esignature.decline_signer(req_id, idx, "   ")
        assert "error" in result

    def test_rejects_bad_index(self):
        req_id, _ = _sent_request_index()
        result = esignature.decline_signer(req_id, 9, "Changed mind")
        assert "error" in result

    def test_voids_the_whole_envelope(self):
        req = _start_valid_request()
        esignature.add_signer(req.id, "John Q", "co_signer")
        esignature.send_signature_request(req.id)

        result = esignature.decline_signer(req.id, 0, "Changed mind")
        assert result.attributes["signers"][0]["status"] == "declined"
        assert result.attributes["signers"][0]["decline_reason"] == "Changed mind"
        assert result.attributes["status"] == "declined"


# ---------------------------------------------------------------------------
# void_signature_request
# ---------------------------------------------------------------------------

class TestVoidSignatureRequest:
    def test_rejects_unknown_request(self):
        result = esignature.void_signature_request("SIGN-BAD")
        assert "error" in result

    def test_rejects_once_completed(self):
        req_id, idx = _sent_request_index()
        esignature.capture_signer_consent(req_id, idx)
        esignature.sign(req_id, idx, "Jane Doe")
        result = esignature.void_signature_request(req_id)
        assert "error" in result

    def test_rejects_when_already_voided(self):
        req = _start_valid_request()
        esignature.void_signature_request(req.id)
        result = esignature.void_signature_request(req.id)
        assert "error" in result

    def test_voids_a_draft(self):
        req = _start_valid_request()
        result = esignature.void_signature_request(req.id)
        assert result.attributes["status"] == "voided"
        assert result.attributes["voided_at"] is not None

    def test_voids_a_sent_envelope(self):
        req_id, _ = _sent_request_index()
        result = esignature.void_signature_request(req_id)
        assert result.attributes["status"] == "voided"


# ---------------------------------------------------------------------------
# list_signature_requests / is_deal_fully_signed
# ---------------------------------------------------------------------------

class TestListSignatureRequests:
    def test_lists_all(self):
        _start_valid_request()
        assert len(esignature.list_signature_requests()) == 1

    def test_filters_by_linked_deal_id(self):
        req1 = _start_valid_request()

        _add_customer("CUST-2")
        _add_deal("DEAL-2", customer_id="CUST-2")
        req2 = esignature.create_signature_request("DEAL-2", "EMP-1", [{"name": "Jane Doe", "role": "customer"}])

        for_deal1 = esignature.list_signature_requests(linked_deal_id="DEAL-1")
        assert len(for_deal1) == 1
        assert for_deal1[0].id == req1.id

    def test_filters_by_status(self):
        req = _start_valid_request()
        esignature.send_signature_request(req.id)

        drafts = esignature.list_signature_requests(status="draft")
        sent = esignature.list_signature_requests(status="sent")

        assert len(drafts) == 0
        assert len(sent) == 1


class TestIsDealFullySigned:
    def test_false_when_no_requests(self):
        _add_deal()
        assert esignature.is_deal_fully_signed("DEAL-1") is False

    def test_false_when_only_sent(self):
        req_id, _ = _sent_request_index()
        assert esignature.is_deal_fully_signed("DEAL-1") is False

    def test_true_once_completed(self):
        req_id, idx = _sent_request_index()
        esignature.capture_signer_consent(req_id, idx)
        esignature.sign(req_id, idx, "Jane Doe")
        assert esignature.is_deal_fully_signed("DEAL-1") is True


# ---------------------------------------------------------------------------
# get_stats
# ---------------------------------------------------------------------------

class TestStats:
    def test_empty_stats_are_honest_zeros_and_nones(self):
        stats = esignature.get_stats()
        assert stats["total"] == 0
        assert stats["completion_rate_pct"] is None

    def test_counts_by_status(self):
        req1 = _start_valid_request()  # draft

        _add_customer("CUST-2")
        _add_deal("DEAL-2", customer_id="CUST-2")
        req2 = esignature.create_signature_request("DEAL-2", "EMP-1", [{"name": "Jane Doe", "role": "customer"}])
        esignature.send_signature_request(req2.id)
        esignature.capture_signer_consent(req2.id, 0)
        esignature.sign(req2.id, 0, "Jane Doe")  # completed

        stats = esignature.get_stats()
        assert stats["total"] == 2
        assert stats["draft"] == 1
        assert stats["completed"] == 1

    def test_completion_rate_computed_over_sent_or_beyond_only(self):
        _start_valid_request()  # draft -- excluded from the denominator

        _add_customer("CUST-2")
        _add_deal("DEAL-2", customer_id="CUST-2")
        req2 = esignature.create_signature_request("DEAL-2", "EMP-1", [{"name": "Jane Doe", "role": "customer"}])
        esignature.send_signature_request(req2.id)
        esignature.capture_signer_consent(req2.id, 0)
        esignature.sign(req2.id, 0, "Jane Doe")  # completed

        stats = esignature.get_stats()
        assert stats["completion_rate_pct"] == 100.0


# ---------------------------------------------------------------------------
# _names_reasonably_match
# ---------------------------------------------------------------------------

class TestNamesReasonablyMatch:
    def test_matches_on_first_name(self):
        assert esignature._names_reasonably_match("jane", "Jane Doe") is True

    def test_matches_on_last_name(self):
        assert esignature._names_reasonably_match("doe", "Jane Doe") is True

    def test_rejects_unrelated_name(self):
        assert esignature._names_reasonably_match("bob smith", "Jane Doe") is False

    def test_ignores_punctuation_and_case(self):
        assert esignature._names_reasonably_match("JANE-DOE!", "Jane Doe") is True


# ---------------------------------------------------------------------------
# ACL sweep -- core/esignature_api.py
# ---------------------------------------------------------------------------

class TestAcl:
    def test_list_statuses_open(self):
        assert esignature_api.list_esignature_statuses_api() == esignature.STATUSES

    def test_list_signer_statuses_open(self):
        assert esignature_api.list_esignature_signer_statuses_api() == esignature.SIGNER_STATUSES

    def test_list_signer_roles_open(self):
        assert esignature_api.list_esignature_signer_roles_api() == esignature.SIGNER_ROLES

    @pytest.mark.parametrize("role", _DENIED_ROLES)
    def test_create_denied(self, role):
        _add_customer()
        _add_deal()
        result = esignature_api.create_signature_request_api(role, "EMP-1", "DEAL-1", _VALID_SIGNERS)
        assert "error" in result

    @pytest.mark.parametrize("role", _ALLOWED_ROLES)
    def test_create_allowed(self, role):
        ledger.reset()
        _add_customer()
        _add_deal()
        result = esignature_api.create_signature_request_api(role, "EMP-1", "DEAL-1", _VALID_SIGNERS)
        assert "error" not in result
        assert result["status"] == "draft"

    def test_create_api_includes_customer_brief(self):
        _add_customer(first="Jane", last="Doe")
        _add_deal()
        result = esignature_api.create_signature_request_api(ADMIN, "EMP-1", "DEAL-1", _VALID_SIGNERS)
        assert result["customer"]["name"] == "Jane Doe"

    @pytest.mark.parametrize("role", _DENIED_ROLES)
    def test_add_signer_denied(self, role):
        req = _start_valid_request()
        result = esignature_api.add_signer_api(role, req.id, "John Q", "co_signer")
        assert "error" in result

    @pytest.mark.parametrize("role", _ALLOWED_ROLES)
    def test_add_signer_allowed(self, role):
        ledger.reset()
        req = _start_valid_request()
        result = esignature_api.add_signer_api(role, req.id, "John Q", "co_signer")
        assert "error" not in result

    @pytest.mark.parametrize("role", _DENIED_ROLES)
    def test_remove_signer_denied(self, role):
        req = _start_valid_request()
        result = esignature_api.remove_signer_api(role, req.id, 0)
        assert "error" in result

    @pytest.mark.parametrize("role", _ALLOWED_ROLES)
    def test_remove_signer_allowed(self, role):
        ledger.reset()
        req = _start_valid_request()
        esignature.add_signer(req.id, "John Q", "co_signer")
        result = esignature_api.remove_signer_api(role, req.id, 1)
        assert "error" not in result

    @pytest.mark.parametrize("role", _DENIED_ROLES)
    def test_send_denied(self, role):
        req = _start_valid_request()
        result = esignature_api.send_signature_request_api(role, req.id)
        assert "error" in result

    @pytest.mark.parametrize("role", _ALLOWED_ROLES)
    def test_send_allowed(self, role):
        ledger.reset()
        req = _start_valid_request()
        result = esignature_api.send_signature_request_api(role, req.id)
        assert "error" not in result
        assert result["status"] == "sent"

    @pytest.mark.parametrize("role", _DENIED_ROLES)
    def test_capture_consent_denied(self, role):
        req_id, idx = _sent_request_index()
        result = esignature_api.capture_signer_consent_api(role, req_id, idx)
        assert "error" in result

    @pytest.mark.parametrize("role", _ALLOWED_ROLES)
    def test_capture_consent_allowed(self, role):
        ledger.reset()
        req_id, idx = _sent_request_index()
        result = esignature_api.capture_signer_consent_api(role, req_id, idx)
        assert "error" not in result

    @pytest.mark.parametrize("role", _DENIED_ROLES)
    def test_sign_denied(self, role):
        req_id, idx = _sent_request_index()
        esignature.capture_signer_consent(req_id, idx)
        result = esignature_api.sign_api(role, req_id, idx, "Jane Doe")
        assert "error" in result

    @pytest.mark.parametrize("role", _ALLOWED_ROLES)
    def test_sign_allowed(self, role):
        ledger.reset()
        req_id, idx = _sent_request_index()
        esignature.capture_signer_consent(req_id, idx)
        result = esignature_api.sign_api(role, req_id, idx, "Jane Doe")
        assert "error" not in result
        assert result["status"] == "completed"

    @pytest.mark.parametrize("role", _DENIED_ROLES)
    def test_decline_denied(self, role):
        req_id, idx = _sent_request_index()
        result = esignature_api.decline_signer_api(role, req_id, idx, "Changed mind")
        assert "error" in result

    @pytest.mark.parametrize("role", _ALLOWED_ROLES)
    def test_decline_allowed(self, role):
        ledger.reset()
        req_id, idx = _sent_request_index()
        result = esignature_api.decline_signer_api(role, req_id, idx, "Changed mind")
        assert "error" not in result
        assert result["status"] == "declined"

    @pytest.mark.parametrize("role", _DENIED_ROLES)
    def test_void_denied(self, role):
        req = _start_valid_request()
        result = esignature_api.void_signature_request_api(role, req.id)
        assert "error" in result

    @pytest.mark.parametrize("role", _ALLOWED_ROLES)
    def test_void_allowed(self, role):
        ledger.reset()
        req = _start_valid_request()
        result = esignature_api.void_signature_request_api(role, req.id)
        assert "error" not in result
        assert result["status"] == "voided"

    @pytest.mark.parametrize("role", _DENIED_ROLES)
    def test_get_denied(self, role):
        req = _start_valid_request()
        result = esignature_api.get_signature_request_api(role, req.id)
        assert "error" in result

    @pytest.mark.parametrize("role", _ALLOWED_ROLES)
    def test_get_allowed(self, role):
        ledger.reset()
        req = _start_valid_request()
        result = esignature_api.get_signature_request_api(role, req.id)
        assert result["id"] == req.id

    def test_get_unknown_id(self):
        result = esignature_api.get_signature_request_api(ADMIN, "SIGN-BAD")
        assert "error" in result

    @pytest.mark.parametrize("role", _DENIED_ROLES)
    def test_list_denied(self, role):
        result = esignature_api.list_signature_requests_api(role)
        assert isinstance(result, dict) and "error" in result

    @pytest.mark.parametrize("role", _ALLOWED_ROLES)
    def test_list_allowed(self, role):
        result = esignature_api.list_signature_requests_api(role)
        assert isinstance(result, list)

    @pytest.mark.parametrize("role", _DENIED_ROLES)
    def test_dashboard_denied(self, role):
        result = esignature_api.get_esignature_dashboard_api(role)
        assert "error" in result

    @pytest.mark.parametrize("role", _ALLOWED_ROLES)
    def test_dashboard_allowed(self, role):
        result = esignature_api.get_esignature_dashboard_api(role)
        assert "error" not in result
        assert "recent" in result
        assert "stats" in result
