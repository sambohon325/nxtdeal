"""
Tests for core/manager_to.py + core/manager_to_api.py -- Manager TO /
Turn-Over (session 101 follow-up): a real timed hand-off queue (requested ->
claimed -> resolved), tier-gated claim/resolve, and real save-rate/wait-time
stats.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import TURN_OVER, LEAD, DEAL, CUSTOMER, EMPLOYEE
from core import manager_to
from core import manager_to_api
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    monkeypatch.setattr(manager_to, "save_graph", lambda filepath: None)


_REQUEST_ROLES = (ADMIN, OPERATIONS, SALES)
_REQUEST_DENIED_ROLES = (MARKETING, SERVICE, FINANCE)


def _add_lead(lead_id="LEAD-1", first="Alex", last="Prospect"):
    ledger.add_entity(Entity(id=lead_id, entity_type=LEAD, attributes={"FirstName": first, "LastName": last}))
    return lead_id


def _add_customer(customer_id="CUST-1", first="Jane", last="Doe"):
    ledger.add_entity(Entity(id=customer_id, entity_type=CUSTOMER, attributes={"FirstName": first, "LastName": last}))
    return customer_id


def _add_deal(deal_id="DEAL-1", customer_id="CUST-1"):
    ledger.add_entity(Entity(id=deal_id, entity_type=DEAL, attributes={"customer_id": customer_id}))
    return deal_id


def _add_employee(employee_id="EMP-1", title="Sales Rep", first="Sam", last="Sales"):
    ledger.add_entity(Entity(id=employee_id, entity_type=EMPLOYEE, attributes={"Title": title, "FirstName": first, "LastName": last}))
    return employee_id


# ---------------------------------------------------------------------------
# request_to
# ---------------------------------------------------------------------------

class TestRequestTo:
    def test_rejects_unknown_linked_entity(self):
        result = manager_to.request_to("LEAD-BAD", "EMP-1", "price")
        assert "error" in result

    def test_rejects_entity_that_is_not_a_lead_or_deal(self):
        _add_customer()
        result = manager_to.request_to("CUST-1", "EMP-1", "price")
        assert "error" in result

    def test_rejects_bad_reason(self):
        _add_lead()
        result = manager_to.request_to("LEAD-1", "EMP-1", "not_a_real_reason")
        assert "error" in result

    def test_succeeds_with_a_lead(self):
        _add_lead()
        result = manager_to.request_to("LEAD-1", "EMP-1", "price", notes="Wants to think about it")
        assert result.attributes["status"] == "requested"
        assert result.attributes["linked_entity_type"] == LEAD
        assert result.attributes["notes"] == "Wants to think about it"

    def test_succeeds_with_a_deal(self):
        _add_customer()
        _add_deal()
        result = manager_to.request_to("DEAL-1", "EMP-1", "payment")
        assert result.attributes["status"] == "requested"
        assert result.attributes["linked_entity_type"] == DEAL

    def test_initial_fields_are_honest(self):
        _add_lead()
        result = manager_to.request_to("LEAD-1", "EMP-1", "price")
        assert result.attributes["requested_at"] is not None
        assert result.attributes["claimed_by"] is None
        assert result.attributes["claimed_at"] is None
        assert result.attributes["resolved_by"] is None
        assert result.attributes["resolved_at"] is None
        assert result.attributes["outcome"] is None

    def test_creates_a_real_entity_on_the_ledger(self):
        _add_lead()
        result = manager_to.request_to("LEAD-1", "EMP-1", "price")
        stored = ledger.get_entity(result.id)
        assert stored is not None
        assert stored.entity_type == TURN_OVER


# ---------------------------------------------------------------------------
# claim_to
# ---------------------------------------------------------------------------

class TestClaimTo:
    def test_rejects_unknown_to(self):
        result = manager_to.claim_to("TO-BAD", "EMP-MGR")
        assert "error" in result

    def test_claims_a_requested_to(self):
        _add_lead()
        to = manager_to.request_to("LEAD-1", "EMP-1", "price")
        result = manager_to.claim_to(to.id, "EMP-MGR")
        assert result.attributes["status"] == "claimed"
        assert result.attributes["claimed_by"] == "EMP-MGR"
        assert result.attributes["claimed_at"] is not None

    def test_rejects_claiming_an_already_claimed_to(self):
        _add_lead()
        to = manager_to.request_to("LEAD-1", "EMP-1", "price")
        manager_to.claim_to(to.id, "EMP-MGR")
        result = manager_to.claim_to(to.id, "EMP-MGR2")
        assert "error" in result

    def test_rejects_claiming_a_resolved_to(self):
        _add_lead()
        to = manager_to.request_to("LEAD-1", "EMP-1", "price")
        manager_to.resolve_to(to.id, "EMP-MGR", "saved")
        result = manager_to.claim_to(to.id, "EMP-MGR2")
        assert "error" in result


# ---------------------------------------------------------------------------
# resolve_to
# ---------------------------------------------------------------------------

class TestResolveTo:
    def test_rejects_unknown_to(self):
        result = manager_to.resolve_to("TO-BAD", "EMP-MGR", "saved")
        assert "error" in result

    def test_rejects_already_resolved(self):
        _add_lead()
        to = manager_to.request_to("LEAD-1", "EMP-1", "price")
        manager_to.resolve_to(to.id, "EMP-MGR", "saved")
        result = manager_to.resolve_to(to.id, "EMP-MGR", "lost")
        assert "error" in result

    def test_rejects_bad_outcome(self):
        _add_lead()
        to = manager_to.request_to("LEAD-1", "EMP-1", "price")
        result = manager_to.resolve_to(to.id, "EMP-MGR", "sold_it")
        assert "error" in result

    def test_resolving_directly_from_requested_also_claims_it(self):
        _add_lead()
        to = manager_to.request_to("LEAD-1", "EMP-1", "price")
        result = manager_to.resolve_to(to.id, "EMP-MGR", "saved", notes="Got the deal done")
        assert result.attributes["status"] == "resolved"
        assert result.attributes["claimed_by"] == "EMP-MGR"
        assert result.attributes["claimed_at"] is not None
        assert result.attributes["resolved_by"] == "EMP-MGR"
        assert result.attributes["outcome"] == "saved"
        assert result.attributes["resolution_notes"] == "Got the deal done"

    def test_resolving_an_already_claimed_to_keeps_the_original_claimer(self):
        _add_lead()
        to = manager_to.request_to("LEAD-1", "EMP-1", "price")
        manager_to.claim_to(to.id, "EMP-MGR-A")
        result = manager_to.resolve_to(to.id, "EMP-MGR-B", "lost")
        assert result.attributes["claimed_by"] == "EMP-MGR-A"
        assert result.attributes["resolved_by"] == "EMP-MGR-B"


# ---------------------------------------------------------------------------
# list_tos / list_open_tos
# ---------------------------------------------------------------------------

class TestListing:
    def test_lists_all(self):
        _add_lead()
        manager_to.request_to("LEAD-1", "EMP-1", "price")
        assert len(manager_to.list_tos()) == 1

    def test_filters_by_status(self):
        _add_lead()
        to1 = manager_to.request_to("LEAD-1", "EMP-1", "price")
        manager_to.claim_to(to1.id, "EMP-MGR")

        _add_lead("LEAD-2")
        manager_to.request_to("LEAD-2", "EMP-1", "payment")

        requested = manager_to.list_tos(status="requested")
        claimed = manager_to.list_tos(status="claimed")
        assert len(requested) == 1
        assert len(claimed) == 1

    def test_list_open_excludes_resolved(self):
        _add_lead()
        to1 = manager_to.request_to("LEAD-1", "EMP-1", "price")
        manager_to.resolve_to(to1.id, "EMP-MGR", "saved")

        _add_lead("LEAD-2")
        to2 = manager_to.request_to("LEAD-2", "EMP-1", "payment")

        open_tos = manager_to.list_open_tos()
        assert len(open_tos) == 1
        assert open_tos[0].id == to2.id

    def test_list_open_sorted_oldest_first(self):
        _add_lead()
        to1 = manager_to.request_to("LEAD-1", "EMP-1", "price")
        to1.attributes["requested_at"] = "2026-01-01T00:00:00+00:00"

        _add_lead("LEAD-2")
        to2 = manager_to.request_to("LEAD-2", "EMP-1", "payment")
        to2.attributes["requested_at"] = "2026-06-01T00:00:00+00:00"

        open_tos = manager_to.list_open_tos()
        assert [t.id for t in open_tos] == [to1.id, to2.id]


# ---------------------------------------------------------------------------
# get_stats
# ---------------------------------------------------------------------------

class TestStats:
    def test_empty_stats_are_honest(self):
        stats = manager_to.get_stats()
        assert stats["sample_size"] == 0
        assert stats["save_rate_pct"] is None
        assert stats["avg_claim_wait_minutes"] is None
        assert stats["avg_resolution_minutes"] is None

    def test_save_rate_computed_over_resolved_only(self):
        _add_lead()
        to1 = manager_to.request_to("LEAD-1", "EMP-1", "price")
        manager_to.resolve_to(to1.id, "EMP-MGR", "saved")

        _add_lead("LEAD-2")
        to2 = manager_to.request_to("LEAD-2", "EMP-1", "payment")
        manager_to.resolve_to(to2.id, "EMP-MGR", "lost")

        _add_lead("LEAD-3")
        manager_to.request_to("LEAD-3", "EMP-1", "financing")  # still open, excluded

        stats = manager_to.get_stats()
        assert stats["sample_size"] == 2
        assert stats["save_rate_pct"] == 50.0

    def test_avg_wait_and_resolution_are_real(self):
        _add_lead()
        to = manager_to.request_to("LEAD-1", "EMP-1", "price")
        manager_to.resolve_to(to.id, "EMP-MGR", "saved")

        stats = manager_to.get_stats()
        assert stats["avg_claim_wait_minutes"] is not None
        assert stats["avg_claim_wait_minutes"] >= 0
        assert stats["avg_resolution_minutes"] is not None
        assert stats["avg_resolution_minutes"] >= 0


# ---------------------------------------------------------------------------
# ACL sweep -- core/manager_to_api.py
# ---------------------------------------------------------------------------

class TestAcl:
    def test_list_reasons_is_open(self):
        assert manager_to_api.list_to_reasons_api() == manager_to.REASONS

    def test_list_statuses_is_open(self):
        assert manager_to_api.list_to_statuses_api() == manager_to.STATUSES

    def test_list_outcomes_is_open(self):
        assert manager_to_api.list_to_outcomes_api() == manager_to.OUTCOMES

    @pytest.mark.parametrize("role", _REQUEST_DENIED_ROLES)
    def test_request_to_api_denied(self, role):
        _add_lead()
        result = manager_to_api.request_to_api(role, "EMP-1", "LEAD-1", "price")
        assert "error" in result

    @pytest.mark.parametrize("role", _REQUEST_ROLES)
    def test_request_to_api_allowed(self, role):
        ledger.reset()
        _add_lead()
        result = manager_to_api.request_to_api(role, "EMP-1", "LEAD-1", "price")
        assert "error" not in result
        assert result["status"] == "requested"

    def test_request_to_api_serializes_lead_label(self):
        _add_lead(first="Alex", last="Prospect")
        result = manager_to_api.request_to_api(ADMIN, "EMP-1", "LEAD-1", "price")
        assert result["linked_entity_label"] == "Alex Prospect"

    def test_request_to_api_serializes_deal_label_from_customer(self):
        _add_customer(first="Jane", last="Doe")
        _add_deal()
        result = manager_to_api.request_to_api(ADMIN, "EMP-1", "DEAL-1", "payment")
        assert result["linked_entity_label"] == "Jane Doe"

    def test_claim_to_api_admin_bypasses_title_check(self):
        _add_employee(title="Sales Rep")  # staff tier
        _add_lead()
        to = manager_to.request_to("LEAD-1", "EMP-1", "price")
        result = manager_to_api.claim_to_api(ADMIN, "EMP-1", to.id)
        assert "error" not in result
        assert result["status"] == "claimed"

    def test_claim_to_api_denied_for_staff_titled_employee(self):
        _add_employee(title="Sales Rep")
        _add_lead()
        to = manager_to.request_to("LEAD-1", "EMP-1", "price")
        result = manager_to_api.claim_to_api(SALES, "EMP-1", to.id)
        assert "error" in result

    def test_claim_to_api_allowed_for_manager_titled_employee(self):
        _add_employee(employee_id="EMP-MGR", title="Sales Manager")
        _add_lead()
        to = manager_to.request_to("LEAD-1", "EMP-1", "price")
        result = manager_to_api.claim_to_api(SALES, "EMP-MGR", to.id)
        assert "error" not in result

    def test_claim_to_api_denied_for_unknown_employee(self):
        _add_lead()
        to = manager_to.request_to("LEAD-1", "EMP-1", "price")
        result = manager_to_api.claim_to_api(SALES, "EMP-BAD", to.id)
        assert "error" in result

    def test_resolve_to_api_denied_for_staff_titled_employee(self):
        _add_employee(title="Sales Rep")
        _add_lead()
        to = manager_to.request_to("LEAD-1", "EMP-1", "price")
        result = manager_to_api.resolve_to_api(SALES, "EMP-1", to.id, "saved")
        assert "error" in result

    def test_resolve_to_api_allowed_for_executive_titled_employee(self):
        _add_employee(employee_id="EMP-GM", title="General Manager")
        _add_lead()
        to = manager_to.request_to("LEAD-1", "EMP-1", "price")
        result = manager_to_api.resolve_to_api(SALES, "EMP-GM", to.id, "saved")
        assert "error" not in result
        assert result["status"] == "resolved"

    @pytest.mark.parametrize("role", _REQUEST_DENIED_ROLES)
    def test_list_open_tos_api_denied(self, role):
        result = manager_to_api.list_open_tos_api(role)
        assert isinstance(result, dict) and "error" in result

    @pytest.mark.parametrize("role", _REQUEST_ROLES)
    def test_list_open_tos_api_allowed(self, role):
        result = manager_to_api.list_open_tos_api(role)
        assert isinstance(result, list)

    @pytest.mark.parametrize("role", _REQUEST_DENIED_ROLES)
    def test_list_tos_api_denied(self, role):
        result = manager_to_api.list_tos_api(role)
        assert isinstance(result, dict) and "error" in result

    @pytest.mark.parametrize("role", _REQUEST_ROLES)
    def test_list_tos_api_allowed(self, role):
        result = manager_to_api.list_tos_api(role)
        assert isinstance(result, list)

    @pytest.mark.parametrize("role", _REQUEST_DENIED_ROLES)
    def test_get_stats_api_denied(self, role):
        result = manager_to_api.get_to_stats_api(role)
        assert "error" in result

    @pytest.mark.parametrize("role", _REQUEST_ROLES)
    def test_get_stats_api_allowed(self, role):
        result = manager_to_api.get_to_stats_api(role)
        assert "sample_size" in result
