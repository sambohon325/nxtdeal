"""
Tests for core/orphan_owner_mining.py / core/orphan_owner_mining_api.py -- the
"Orphan Owner Mining" workflow: customers who own a vehicle but have zero
traceable salesperson attribution on file, and the real claim-into-a-Lead action.

Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.relationships import Relationship
from core.entity_types import CUSTOMER, VEHICLE, DEAL, SERVICE_RECORD, LEAD, FIELD_NOTE
from core.relationship_types import OWNS, AUTHORIZED, GENERATED_LEAD
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE

from core import orphan_owner_mining
from core import lead_intake
from core import field_notes
from core.orphan_owner_mining import (
    get_orphan_owners,
    get_orphan_owner_detail,
    claim_orphan_owner,
    get_orphan_owner_stats,
)
from core.orphan_owner_mining_api import (
    get_orphan_owners_api,
    get_orphan_owner_detail_api,
    claim_orphan_owner_api,
    get_orphan_owner_stats_api,
    get_orphan_owner_dashboard_api,
)


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    monkeypatch.setattr(orphan_owner_mining, "save_graph", lambda filepath: None)
    monkeypatch.setattr(lead_intake, "save_graph", lambda filepath: None)
    monkeypatch.setattr(field_notes, "save_graph", lambda filepath: None)


ALL_ROLES = (ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE)


def _customer(customer_id, first="Jane", last="Doe", email="jane@example.com", phone="555-0100"):
    ledger.add_entity(Entity(id=customer_id, entity_type=CUSTOMER, attributes={
        "FirstName": first, "LastName": last, "Email": email, "Phone": phone,
        "City": "Springfield", "State": "IL",
    }))


def _vehicle(vehicle_id, vin=None, year="2020", make="Honda", model="Civic"):
    ledger.add_entity(Entity(id=vehicle_id, entity_type=VEHICLE, attributes={
        "VIN": vin or f"VIN{vehicle_id}", "Year": year, "Make": make, "Model": model,
    }))


def _own(customer_id, vehicle_id):
    ledger.add_relationship(Relationship(source_id=customer_id, target_id=vehicle_id, relationship_type=OWNS))


def _funded_deal(deal_id, customer_id, created_by="EMP-1"):
    ledger.add_entity(Entity(id=deal_id, entity_type=DEAL, attributes={
        "status": "funded", "customer_id": customer_id, "created_by": created_by,
    }))


def _unfunded_deal(deal_id, customer_id, created_by="EMP-1"):
    ledger.add_entity(Entity(id=deal_id, entity_type=DEAL, attributes={
        "status": "desking", "customer_id": customer_id, "created_by": created_by,
    }))


def _service_record(record_id, customer_id, service_date):
    ledger.add_entity(Entity(id=record_id, entity_type=SERVICE_RECORD, attributes={
        "ServiceDate": service_date,
    }))
    ledger.add_relationship(Relationship(source_id=customer_id, target_id=record_id, relationship_type=AUTHORIZED))


# ---------------------------------------------------------------------------
# get_orphan_owners
# ---------------------------------------------------------------------------

class TestGetOrphanOwners:

    def test_unattributed_owner_appears(self):
        _customer("CUST-1")
        _vehicle("VEH-1")
        _own("CUST-1", "VEH-1")

        results = get_orphan_owners()
        assert len(results) == 1
        assert results[0]["customer"]["id"] == "CUST-1"
        assert results[0]["claimed"] is False

    def test_customer_with_no_ownership_never_appears(self):
        _customer("CUST-1")
        results = get_orphan_owners()
        assert results == []

    def test_funded_deal_with_created_by_excludes_owner(self):
        _customer("CUST-1")
        _vehicle("VEH-1")
        _own("CUST-1", "VEH-1")
        _funded_deal("DEAL-1", "CUST-1", created_by="EMP-1")

        results = get_orphan_owners()
        assert results == []

    def test_funded_deal_with_no_created_by_still_counts_as_orphan(self):
        _customer("CUST-1")
        _vehicle("VEH-1")
        _own("CUST-1", "VEH-1")
        _funded_deal("DEAL-1", "CUST-1", created_by=None)

        results = get_orphan_owners()
        assert len(results) == 1

    def test_unfunded_deal_does_not_grant_attribution(self):
        _customer("CUST-1")
        _vehicle("VEH-1")
        _own("CUST-1", "VEH-1")
        _unfunded_deal("DEAL-1", "CUST-1", created_by="EMP-1")

        results = get_orphan_owners()
        assert len(results) == 1

    def test_claimed_owner_excluded_by_default(self):
        _customer("CUST-1")
        _vehicle("VEH-1")
        _own("CUST-1", "VEH-1")
        claim_orphan_owner("CUST-1", "EMP-1")

        results = get_orphan_owners()
        assert results == []

    def test_claimed_owner_included_with_include_claimed(self):
        _customer("CUST-1")
        _vehicle("VEH-1")
        _own("CUST-1", "VEH-1")
        claim_result = claim_orphan_owner("CUST-1", "EMP-1")

        results = get_orphan_owners(include_claimed=True)
        assert len(results) == 1
        assert results[0]["claimed"] is True
        assert results[0]["claimed_lead_id"] == claim_result["lead_id"]
        assert results[0]["claimed_by"] == "EMP-1"

    def test_sorted_by_vehicle_count_descending(self):
        _customer("CUST-1")
        _vehicle("VEH-1")
        _vehicle("VEH-2")
        _own("CUST-1", "VEH-1")
        _own("CUST-1", "VEH-2")

        _customer("CUST-2")
        _vehicle("VEH-3")
        _own("CUST-2", "VEH-3")

        results = get_orphan_owners()
        assert results[0]["customer"]["id"] == "CUST-1"
        assert results[0]["vehicles_owned"]["count"] == 2
        assert results[1]["customer"]["id"] == "CUST-2"

    def test_sort_tiebreak_by_most_recent_service_visit(self):
        _customer("CUST-1")
        _vehicle("VEH-1")
        _own("CUST-1", "VEH-1")
        _service_record("SR-1", "CUST-1", "2026-01-01")

        _customer("CUST-2")
        _vehicle("VEH-2")
        _own("CUST-2", "VEH-2")
        _service_record("SR-2", "CUST-2", "2026-06-01")

        results = get_orphan_owners()
        assert results[0]["customer"]["id"] == "CUST-2"
        assert results[1]["customer"]["id"] == "CUST-1"

    def test_limit_truncates_results(self):
        for i in range(5):
            cid = f"CUST-{i}"
            vid = f"VEH-{i}"
            _customer(cid)
            _vehicle(vid)
            _own(cid, vid)

        results = get_orphan_owners(limit=2)
        assert len(results) == 2


# ---------------------------------------------------------------------------
# get_orphan_owner_detail
# ---------------------------------------------------------------------------

class TestGetOrphanOwnerDetail:

    def test_unknown_customer_rejected(self):
        result = get_orphan_owner_detail("CUST-GHOST")
        assert "error" in result

    def test_wrong_entity_type_rejected(self):
        _vehicle("VEH-1")
        result = get_orphan_owner_detail("VEH-1")
        assert "error" in result

    def test_customer_with_no_vehicles_rejected(self):
        _customer("CUST-1")
        result = get_orphan_owner_detail("CUST-1")
        assert "error" in result
        assert "no vehicle ownership" in result["error"]

    def test_real_orphan_returns_full_detail(self):
        _customer("CUST-1")
        _vehicle("VEH-1")
        _own("CUST-1", "VEH-1")

        result = get_orphan_owner_detail("CUST-1")
        assert result["has_salesperson_attribution"] is False
        assert result["claimed"] is False
        assert result["vehicles_owned"]["count"] == 1

    def test_owner_with_salesperson_attribution_still_returns_detail(self):
        _customer("CUST-1")
        _vehicle("VEH-1")
        _own("CUST-1", "VEH-1")
        _funded_deal("DEAL-1", "CUST-1", created_by="EMP-1")

        result = get_orphan_owner_detail("CUST-1")
        assert result["has_salesperson_attribution"] is True

    def test_claimed_owner_detail_shows_claim_info(self):
        _customer("CUST-1")
        _vehicle("VEH-1")
        _own("CUST-1", "VEH-1")
        claim_result = claim_orphan_owner("CUST-1", "EMP-1")

        result = get_orphan_owner_detail("CUST-1")
        assert result["claimed"] is True
        assert result["claimed_lead_id"] == claim_result["lead_id"]


# ---------------------------------------------------------------------------
# claim_orphan_owner
# ---------------------------------------------------------------------------

class TestClaimOrphanOwner:

    def test_unknown_customer_rejected(self):
        result = claim_orphan_owner("CUST-GHOST", "EMP-1")
        assert "error" in result

    def test_wrong_entity_type_rejected(self):
        _vehicle("VEH-1")
        result = claim_orphan_owner("VEH-1", "EMP-1")
        assert "error" in result

    def test_no_vehicle_ownership_rejected(self):
        _customer("CUST-1")
        result = claim_orphan_owner("CUST-1", "EMP-1")
        assert "error" in result

    def test_real_salesperson_attribution_rejected(self):
        _customer("CUST-1")
        _vehicle("VEH-1")
        _own("CUST-1", "VEH-1")
        _funded_deal("DEAL-1", "CUST-1", created_by="EMP-1")

        result = claim_orphan_owner("CUST-1", "EMP-2")
        assert "error" in result
        assert "already has a real funded deal" in result["error"]

    def test_double_claim_rejected(self):
        _customer("CUST-1")
        _vehicle("VEH-1")
        _own("CUST-1", "VEH-1")
        first = claim_orphan_owner("CUST-1", "EMP-1")

        second = claim_orphan_owner("CUST-1", "EMP-2")
        assert "error" in second
        assert first["lead_id"] in second["error"]

    def test_successful_claim_creates_real_lead(self):
        _customer("CUST-1", first="John", last="Smith", email="john@example.com", phone="555-1234")
        _vehicle("VEH-1", vin="1HGCM82633A004352")
        _own("CUST-1", "VEH-1")

        result = claim_orphan_owner("CUST-1", "EMP-1")

        assert "error" not in result
        assert result["customer_id"] == "CUST-1"
        assert result["vehicle_id"] == "VEH-1"
        assert result["assigned_to"] == "EMP-1"

        lead = ledger.get_entity(result["lead_id"])
        assert lead is not None
        assert lead.entity_type == LEAD
        assert lead.attributes["Source"] == "Orphan Owner Mining"
        assert lead.attributes["AssignedSalesperson"] == "EMP-1"
        assert lead.attributes["FirstName"] == "John"

    def test_successful_claim_creates_generated_lead_relationship(self):
        _customer("CUST-1")
        _vehicle("VEH-1")
        _own("CUST-1", "VEH-1")

        result = claim_orphan_owner("CUST-1", "EMP-1")

        matches = [
            r for r in ledger.get_relationships()
            if r.source_id == "CUST-1" and r.target_id == result["lead_id"]
            and r.relationship_type == GENERATED_LEAD
        ]
        assert len(matches) == 1

    def test_claim_with_note_creates_field_note(self):
        _customer("CUST-1")
        _vehicle("VEH-1")
        _own("CUST-1", "VEH-1")

        claim_orphan_owner("CUST-1", "EMP-1", note="Reached out via phone.")

        notes = [e for e in ledger.get_all().values() if e.entity_type == FIELD_NOTE]
        assert len(notes) == 1
        assert notes[0].attributes["category"] == "recovery_attempt"
        assert notes[0].attributes["department"] == "Sales"
        assert notes[0].attributes["body"] == "Reached out via phone."
        assert notes[0].attributes["linked_entity_id"] == "CUST-1"

    def test_claim_without_note_creates_no_field_note(self):
        _customer("CUST-1")
        _vehicle("VEH-1")
        _own("CUST-1", "VEH-1")

        claim_orphan_owner("CUST-1", "EMP-1")

        notes = [e for e in ledger.get_all().values() if e.entity_type == FIELD_NOTE]
        assert notes == []

    def test_claimed_customer_drops_out_of_unclaimed_queue(self):
        _customer("CUST-1")
        _vehicle("VEH-1")
        _own("CUST-1", "VEH-1")

        assert len(get_orphan_owners()) == 1
        claim_orphan_owner("CUST-1", "EMP-1")
        assert len(get_orphan_owners()) == 0


# ---------------------------------------------------------------------------
# get_orphan_owner_stats
# ---------------------------------------------------------------------------

class TestGetOrphanOwnerStats:

    def test_stats_computed_correctly(self):
        _customer("CUST-1")
        _vehicle("VEH-1")
        _own("CUST-1", "VEH-1")

        _customer("CUST-2")
        _vehicle("VEH-2")
        _own("CUST-2", "VEH-2")

        _customer("CUST-3")
        _vehicle("VEH-3")
        _vehicle("VEH-4")
        _own("CUST-3", "VEH-3")
        _own("CUST-3", "VEH-4")
        claim_orphan_owner("CUST-3", "EMP-1")

        stats = get_orphan_owner_stats()
        assert stats["total_orphan_owners"] == 3
        assert stats["unclaimed"] == 2
        assert stats["claimed"] == 1
        assert stats["total_vehicles_represented"] == 4

    def test_stats_zero_state(self):
        stats = get_orphan_owner_stats()
        assert stats["total_orphan_owners"] == 0
        assert stats["unclaimed"] == 0
        assert stats["claimed"] == 0
        assert stats["total_vehicles_represented"] == 0


# ---------------------------------------------------------------------------
# ACL layer
# ---------------------------------------------------------------------------

class TestGetOrphanOwnersApi:

    def test_marketing_can_view(self):
        result = get_orphan_owners_api(MARKETING)
        assert "error" not in result

    def test_service_denied(self):
        result = get_orphan_owners_api(SERVICE)
        assert "error" in result

    def test_finance_denied(self):
        result = get_orphan_owners_api(FINANCE)
        assert "error" in result

    def test_admin_can_view(self):
        result = get_orphan_owners_api(ADMIN)
        assert "error" not in result


class TestGetOrphanOwnerDetailApi:

    def test_denied_for_service(self):
        result = get_orphan_owner_detail_api(SERVICE, "CUST-1")
        assert "error" in result

    def test_allowed_for_sales(self):
        _customer("CUST-1")
        _vehicle("VEH-1")
        _own("CUST-1", "VEH-1")
        result = get_orphan_owner_detail_api(SALES, "CUST-1")
        assert "error" not in result


class TestClaimOrphanOwnerApi:

    def test_admin_can_claim(self):
        _customer("CUST-1")
        _vehicle("VEH-1")
        _own("CUST-1", "VEH-1")
        result = claim_orphan_owner_api(ADMIN, "EMP-1", "CUST-1")
        assert "error" not in result

    def test_operations_can_claim(self):
        _customer("CUST-1")
        _vehicle("VEH-1")
        _own("CUST-1", "VEH-1")
        result = claim_orphan_owner_api(OPERATIONS, "EMP-1", "CUST-1")
        assert "error" not in result

    def test_sales_can_claim(self):
        _customer("CUST-1")
        _vehicle("VEH-1")
        _own("CUST-1", "VEH-1")
        result = claim_orphan_owner_api(SALES, "EMP-1", "CUST-1")
        assert "error" not in result

    def test_marketing_view_only_cannot_claim(self):
        _customer("CUST-1")
        _vehicle("VEH-1")
        _own("CUST-1", "VEH-1")
        result = claim_orphan_owner_api(MARKETING, "EMP-1", "CUST-1")
        assert "error" in result

    def test_service_cannot_claim(self):
        _customer("CUST-1")
        _vehicle("VEH-1")
        _own("CUST-1", "VEH-1")
        result = claim_orphan_owner_api(SERVICE, "EMP-1", "CUST-1")
        assert "error" in result


class TestGetOrphanOwnerStatsApi:

    def test_denied_for_finance(self):
        result = get_orphan_owner_stats_api(FINANCE)
        assert "error" in result

    def test_allowed_for_admin(self):
        result = get_orphan_owner_stats_api(ADMIN)
        assert "error" not in result


class TestGetOrphanOwnerDashboardApi:

    def test_denied_for_service(self):
        result = get_orphan_owner_dashboard_api(SERVICE)
        assert "error" in result

    def test_composes_queue_and_stats(self):
        _customer("CUST-1")
        _vehicle("VEH-1")
        _own("CUST-1", "VEH-1")

        result = get_orphan_owner_dashboard_api(ADMIN)
        assert "queue" in result
        assert "stats" in result
        assert result["stats"]["total_orphan_owners"] == 1
        assert len(result["queue"]) == 1
