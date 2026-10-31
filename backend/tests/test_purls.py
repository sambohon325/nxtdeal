import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.relationships import Relationship
from core.entity_types import (
    CUSTOMER,
    LEAD,
    VEHICLE,
    DEAL,
    FINANCE_CONTRACT,
    APPOINTMENT,
    MARKETING_LIST,
    SMART_AUDIENCE,
    PERSONALIZED_URL,
)
from core.relationship_types import OWNS, FINANCED_BY

from core import purls as purls
from core import purls_api
from core import lead_intake as lead_intake
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    # purls.py itself saves, AND submit_purl_lead() calls into lead_intake.create_lead(),
    # which saves via its OWN module-bound save_graph reference -- both need patching.
    monkeypatch.setattr(purls, "save_graph", lambda filepath: None)
    monkeypatch.setattr(lead_intake, "save_graph", lambda filepath: None)


def _add_entity(entity_id, entity_type, **attrs):
    entity = Entity(id=entity_id, entity_type=entity_type, attributes=attrs)
    ledger.add_entity(entity)
    return entity


def _add_rel(source_id, target_id, relationship_type):
    ledger.add_relationship(Relationship(source_id=source_id, target_id=target_id, relationship_type=relationship_type))


def _add_customer(customer_id="CUST-1", **overrides):
    attrs = {
        "FirstName": "Jane", "LastName": "Doe", "Email": "jane@example.com",
        "Phone": "555-0100", "City": "Springfield", "State": "IL",
        "CreditScore": "700", "CustomerID": customer_id,
    }
    attrs.update(overrides)
    return _add_entity(customer_id, CUSTOMER, **attrs)


def _add_lead(lead_id="LEAD-1", **overrides):
    attrs = {"FirstName": "Sam", "LastName": "Prospect", "Email": "sam@example.com", "Phone": "555-0200"}
    attrs.update(overrides)
    return _add_entity(lead_id, LEAD, **attrs)


def _add_vehicle(vehicle_id="VEH-1", **overrides):
    attrs = {"VIN": "1FA0001", "Year": 2022, "Make": "Ford", "Model": "F-150", "Trim": "XLT", "Price": 35000, "Cost": 30000, "DateSold": None}
    attrs.update(overrides)
    return _add_entity(vehicle_id, VEHICLE, **attrs)


def _add_finance_contract(contract_id="FIN-1", customer_id="CUST-1", **overrides):
    attrs = {
        "ContractDate": "2020-01-01", "TermMonths": 24, "CustomerID": customer_id,
        "AmountFinanced": 25000, "LenderName": "First Dealer Bank", "VIN": "1FA0001",
        "MonthlyPayment": 550,
    }
    attrs.update(overrides)
    return _add_entity(contract_id, FINANCE_CONTRACT, **attrs)


def _add_deal(deal_id="DEAL-1", customer_id="CUST-1", **overrides):
    attrs = {"status": "funded", "vehicle_id": "VEH-1", "funded_at": "2026-02-01T00:00:00+00:00", "customer_id": customer_id}
    attrs.update(overrides)
    return _add_entity(deal_id, DEAL, **attrs)


def _add_appointment(appt_id="APPT-1", customer_id=None, lead_id=None, created_at="2026-02-01T00:00:00+00:00"):
    return _add_entity(appt_id, APPOINTMENT, customer_id=customer_id, lead_id=lead_id, created_at=created_at)


def _add_marketing_list(list_id="MLIST-1", member_ids=None, **overrides):
    attrs = {"name": "Test List", "member_ids": member_ids or []}
    attrs.update(overrides)
    return _add_entity(list_id, MARKETING_LIST, **attrs)


def _add_smart_audience(audience_id="SAUD-1", conditions=None, **overrides):
    attrs = {"name": "Everyone", "conditions": conditions if conditions is not None else [], "preset_key": None}
    attrs.update(overrides)
    return _add_entity(audience_id, SMART_AUDIENCE, **attrs)


# ---------------------------------------------------------------------------
# generate_purl
# ---------------------------------------------------------------------------

class TestGeneratePurl:

    def test_generate_for_customer(self):
        _add_customer("CUST-1")
        result = purls.generate_purl("EMP-1", offer_type="current_vehicle", customer_id="CUST-1")
        assert "error" not in result
        assert result["purl"]["customer_id"] == "CUST-1"
        assert result["purl"]["offer_type"] == "current_vehicle"
        assert result["purl"]["status"] == "active"
        assert result["purl"]["token"]
        assert result["public_path"] == f"/purl/{result['purl']['token']}"

    def test_generate_for_lead(self):
        _add_lead("LEAD-1")
        result = purls.generate_purl("EMP-1", lead_id="LEAD-1")
        assert result["purl"]["lead_id"] == "LEAD-1"
        assert result["purl"]["customer_id"] is None

    def test_requires_a_target(self):
        result = purls.generate_purl("EMP-1")
        assert result == {"error": "A PURL must target a real customer_id or lead_id"}

    def test_rejects_both_targets_at_once(self):
        _add_customer("CUST-1")
        _add_lead("LEAD-1")
        result = purls.generate_purl("EMP-1", customer_id="CUST-1", lead_id="LEAD-1")
        assert "error" in result
        assert "not both" in result["error"]

    def test_rejects_invalid_offer_type(self):
        _add_customer("CUST-1")
        result = purls.generate_purl("EMP-1", offer_type="bogus", customer_id="CUST-1")
        assert "error" in result
        assert "Invalid offer_type" in result["error"]

    def test_rejects_nonexistent_target(self):
        result = purls.generate_purl("EMP-1", customer_id="CUST-NOPE")
        assert result == {"error": "Target customer/lead not found"}

    def test_rejects_target_of_wrong_entity_type(self):
        _add_vehicle("VEH-1")
        result = purls.generate_purl("EMP-1", customer_id="VEH-1")
        assert result == {"error": "Target customer/lead not found"}

    def test_default_offer_type_is_general(self):
        _add_customer("CUST-1")
        result = purls.generate_purl("EMP-1", customer_id="CUST-1")
        assert result["purl"]["offer_type"] == "general"

    def test_token_is_unique_across_calls(self):
        _add_customer("CUST-1")
        _add_customer("CUST-2")
        a = purls.generate_purl("EMP-1", customer_id="CUST-1")
        b = purls.generate_purl("EMP-1", customer_id="CUST-2")
        assert a["purl"]["token"] != b["purl"]["token"]


# ---------------------------------------------------------------------------
# bulk_generate_purls
# ---------------------------------------------------------------------------

class TestBulkGeneratePurls:

    def test_rejects_invalid_source_type(self):
        result = purls.bulk_generate_purls("EMP-1", "bogus_source", "X-1")
        assert "error" in result
        assert "source_type" in result["error"]

    def test_marketing_list_not_found(self):
        result = purls.bulk_generate_purls("EMP-1", "marketing_list", "MLIST-NOPE")
        assert result == {"error": "Marketing list not found"}

    def test_marketing_list_bulk_generate_mixed_customer_and_lead(self):
        _add_customer("CUST-1")
        _add_lead("LEAD-1")
        _add_marketing_list("MLIST-1", member_ids=["CUST-1", "LEAD-1"])

        result = purls.bulk_generate_purls("EMP-1", "marketing_list", "MLIST-1", offer_type="general")

        assert result["source_type"] == "marketing_list"
        assert result["requested"] == 2
        assert result["created_count"] == 2
        assert result["skipped_count"] == 0
        created_targets = {(c["customer_id"], c["lead_id"]) for c in result["created"]}
        assert ("CUST-1", None) in created_targets
        assert (None, "LEAD-1") in created_targets

    def test_marketing_list_with_no_real_members_errors(self):
        _add_marketing_list("MLIST-1", member_ids=["CUST-GONE"])
        result = purls.bulk_generate_purls("EMP-1", "marketing_list", "MLIST-1")
        assert result == {"error": "No real members found in this source -- nothing to generate"}

    def test_marketing_list_skips_unsupported_entity_types(self):
        _add_customer("CUST-1")
        _add_vehicle("VEH-1")
        _add_marketing_list("MLIST-1", member_ids=["CUST-1", "VEH-1"])
        result = purls.bulk_generate_purls("EMP-1", "marketing_list", "MLIST-1")
        assert result["created_count"] == 1
        assert result["skipped_count"] == 1
        assert result["skipped"][0]["id"] == "VEH-1"

    def test_smart_audience_bulk_generate(self):
        _add_customer("CUST-1")
        _add_customer("CUST-2")
        _add_smart_audience("SAUD-1", conditions=[])

        result = purls.bulk_generate_purls("EMP-1", "smart_audience", "SAUD-1", offer_type="trade_equity")

        assert result["source_type"] == "smart_audience"
        assert result["requested"] == 2
        assert result["created_count"] == 2
        assert all(c["offer_type"] == "trade_equity" for c in result["created"])

    def test_smart_audience_not_found(self):
        result = purls.bulk_generate_purls("EMP-1", "smart_audience", "SAUD-NOPE")
        assert result == {"error": "Smart audience not found"}

    def test_persists_only_once_when_at_least_one_created(self, monkeypatch):
        _add_customer("CUST-1")
        _add_customer("CUST-2")
        _add_marketing_list("MLIST-1", member_ids=["CUST-1", "CUST-2"])

        calls = []
        monkeypatch.setattr(purls, "save_graph", lambda filepath: calls.append(1))

        purls.bulk_generate_purls("EMP-1", "marketing_list", "MLIST-1")
        assert len(calls) == 1

    def test_does_not_save_when_nothing_created(self, monkeypatch):
        _add_marketing_list("MLIST-1", member_ids=[])
        calls = []
        monkeypatch.setattr(purls, "save_graph", lambda filepath: calls.append(1))
        purls.bulk_generate_purls("EMP-1", "marketing_list", "MLIST-1")
        assert calls == []


# ---------------------------------------------------------------------------
# revoke_purl
# ---------------------------------------------------------------------------

class TestRevokePurl:

    def test_revoke_active_purl(self):
        _add_customer("CUST-1")
        created = purls.generate_purl("EMP-1", customer_id="CUST-1")
        purl_id = created["purl"]["id"]

        result = purls.revoke_purl(purl_id, "EMP-2")
        assert result["purl"]["status"] == "revoked"

    def test_revoke_nonexistent_purl(self):
        result = purls.revoke_purl("PURL-NOPE", "EMP-2")
        assert "error" in result
        assert "not found" in result["error"]

    def test_revoke_already_revoked_purl_rejected(self):
        _add_customer("CUST-1")
        created = purls.generate_purl("EMP-1", customer_id="CUST-1")
        purl_id = created["purl"]["id"]
        purls.revoke_purl(purl_id, "EMP-2")

        result = purls.revoke_purl(purl_id, "EMP-2")
        assert "error" in result
        assert "already" in result["error"]

    def test_revoked_by_and_revoked_at_stamped(self):
        _add_customer("CUST-1")
        created = purls.generate_purl("EMP-1", customer_id="CUST-1")
        purl_id = created["purl"]["id"]
        purls.revoke_purl(purl_id, "EMP-9")

        entity = ledger.get_entity(purl_id)
        assert entity.attributes["revoked_by"] == "EMP-9"
        assert entity.attributes["revoked_at"]


# ---------------------------------------------------------------------------
# list_purls
# ---------------------------------------------------------------------------

class TestListPurls:

    def test_empty_when_none_exist(self):
        result = purls.list_purls()
        assert result == {"count": 0, "purls": []}

    def test_lists_every_purl(self):
        _add_customer("CUST-1")
        _add_customer("CUST-2")
        purls.generate_purl("EMP-1", customer_id="CUST-1")
        purls.generate_purl("EMP-2", customer_id="CUST-2")
        result = purls.list_purls()
        assert result["count"] == 2

    def test_filters_by_created_by(self):
        _add_customer("CUST-1")
        _add_customer("CUST-2")
        purls.generate_purl("EMP-1", customer_id="CUST-1")
        purls.generate_purl("EMP-2", customer_id="CUST-2")
        result = purls.list_purls(created_by="EMP-1")
        assert result["count"] == 1
        assert result["purls"][0]["created_by"] == "EMP-1"

    def test_filters_by_status(self):
        _add_customer("CUST-1")
        _add_customer("CUST-2")
        a = purls.generate_purl("EMP-1", customer_id="CUST-1")
        purls.generate_purl("EMP-2", customer_id="CUST-2")
        purls.revoke_purl(a["purl"]["id"], "EMP-9")

        result = purls.list_purls(status="revoked")
        assert result["count"] == 1
        assert result["purls"][0]["id"] == a["purl"]["id"]

    def test_sorted_most_recently_created_first(self):
        _add_customer("CUST-1")
        p1 = purls.generate_purl("EMP-1", customer_id="CUST-1")
        entity1 = ledger.get_entity(p1["purl"]["id"])
        entity1.attributes["created_at"] = "2026-01-01T00:00:00+00:00"

        _add_customer("CUST-2")
        p2 = purls.generate_purl("EMP-1", customer_id="CUST-2")
        entity2 = ledger.get_entity(p2["purl"]["id"])
        entity2.attributes["created_at"] = "2026-06-01T00:00:00+00:00"

        result = purls.list_purls()
        assert result["purls"][0]["id"] == p2["purl"]["id"]


# ---------------------------------------------------------------------------
# _current_vehicles
# ---------------------------------------------------------------------------

class TestCurrentVehicles:

    def test_lead_has_no_current_vehicles(self):
        lead = _add_lead("LEAD-1")
        assert purls._current_vehicles(lead) == []

    def test_customer_with_no_owns_relationships(self):
        customer = _add_customer("CUST-1")
        assert purls._current_vehicles(customer) == []

    def test_customer_with_one_owned_vehicle(self):
        customer = _add_customer("CUST-1")
        _add_vehicle("VEH-1", Make="Ford", Model="F-150", Year=2022)
        _add_rel("CUST-1", "VEH-1", OWNS)
        result = purls._current_vehicles(customer)
        assert len(result) == 1
        assert result[0]["make"] == "Ford"

    def test_dedupes_duplicate_owns_relationships_to_same_vehicle(self):
        customer = _add_customer("CUST-1")
        _add_vehicle("VEH-1")
        _add_rel("CUST-1", "VEH-1", OWNS)
        _add_rel("CUST-1", "VEH-1", OWNS)
        result = purls._current_vehicles(customer)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# _trade_equity_offer
# ---------------------------------------------------------------------------

class TestTradeEquityOffer:

    def test_lead_is_ineligible(self):
        lead = _add_lead("LEAD-1")
        result = purls._trade_equity_offer(lead)
        assert result["eligible"] is False
        assert "leads" in result["reason"]

    def test_customer_with_no_equity_signal_ineligible(self):
        customer = _add_customer("CUST-1")
        result = purls._trade_equity_offer(customer)
        assert result["eligible"] is False
        assert "No real equity-mining signal" in result["reason"]

    def test_customer_with_a_real_equity_candidate_eligible(self):
        customer = _add_customer("CUST-1", CustomerID="CUST-1")
        _add_finance_contract("FIN-1", customer_id="CUST-1", ContractDate="2020-01-01", TermMonths=24)
        result = purls._trade_equity_offer(customer)
        assert result["eligible"] is True
        assert result["basis"] == "heuristic_elapsed_term"
        assert result["pct_term_elapsed"] == 1.0
        assert "disclaimer" in result


# ---------------------------------------------------------------------------
# _inventory_matches
# ---------------------------------------------------------------------------

class TestInventoryMatches:

    def test_no_unsold_inventory_returns_empty(self):
        customer = _add_customer("CUST-1")
        assert purls._inventory_matches(customer, []) == []

    def test_prefers_matching_make(self):
        customer = _add_customer("CUST-1")
        _add_vehicle("VEH-FORD", Make="Ford", Price=30000)
        _add_vehicle("VEH-HONDA", Make="Honda", Price=25000)
        current = [{"make": "Ford"}]
        matches = purls._inventory_matches(customer, current)
        assert len(matches) == 1
        assert matches[0]["id"] == "VEH-FORD"

    def test_falls_back_to_any_unsold_when_no_make_match(self):
        customer = _add_customer("CUST-1")
        _add_vehicle("VEH-HONDA", Make="Honda", Price=25000)
        current = [{"make": "Ford"}]
        matches = purls._inventory_matches(customer, current)
        assert len(matches) == 1
        assert matches[0]["id"] == "VEH-HONDA"

    def test_falls_back_to_any_unsold_when_no_current_vehicle_known(self):
        customer = _add_customer("CUST-1")
        _add_vehicle("VEH-HONDA", Make="Honda", Price=25000)
        matches = purls._inventory_matches(customer, [])
        assert len(matches) == 1

    def test_excludes_sold_vehicles(self):
        customer = _add_customer("CUST-1")
        _add_vehicle("VEH-SOLD", DateSold="2026-01-01", Price=20000)
        matches = purls._inventory_matches(customer, [])
        assert matches == []

    def test_sorted_by_price_ascending_capped_at_limit(self):
        customer = _add_customer("CUST-1")
        _add_vehicle("VEH-EXPENSIVE", Price=60000)
        _add_vehicle("VEH-CHEAP", Price=20000)
        _add_vehicle("VEH-MID", Price=40000)
        matches = purls._inventory_matches(customer, [], limit=2)
        assert [m["id"] for m in matches] == ["VEH-CHEAP", "VEH-MID"]


# ---------------------------------------------------------------------------
# _current_finance_contract / _payment_reduction_offer
# ---------------------------------------------------------------------------

class TestCurrentFinanceContract:

    def test_lead_has_no_finance_contract(self):
        lead = _add_lead("LEAD-1")
        assert purls._current_finance_contract(lead) is None

    def test_customer_with_no_financed_by_relationship(self):
        customer = _add_customer("CUST-1")
        assert purls._current_finance_contract(customer) is None

    def test_customer_with_a_financed_by_relationship(self):
        customer = _add_customer("CUST-1")
        _add_finance_contract("FIN-1")
        _add_rel("CUST-1", "FIN-1", FINANCED_BY)
        contract = purls._current_finance_contract(customer)
        assert contract.id == "FIN-1"


class TestPaymentReductionOffer:

    def test_no_finance_contract_ineligible(self):
        customer = _add_customer("CUST-1")
        result = purls._payment_reduction_offer(customer, [])
        assert result["eligible"] is False
        assert "No on-file finance contract" in result["reason"]

    def test_no_monthly_payment_on_contract_ineligible(self):
        customer = _add_customer("CUST-1")
        _add_finance_contract("FIN-1", MonthlyPayment=None)
        _add_rel("CUST-1", "FIN-1", FINANCED_BY)
        result = purls._payment_reduction_offer(customer, [{"price": 30000}])
        assert result["eligible"] is False
        assert "No real current monthly payment" in result["reason"]

    def test_no_inventory_matches_ineligible(self):
        customer = _add_customer("CUST-1")
        _add_finance_contract("FIN-1", MonthlyPayment=500)
        _add_rel("CUST-1", "FIN-1", FINANCED_BY)
        result = purls._payment_reduction_offer(customer, [])
        assert result["eligible"] is False
        assert "No matching inventory" in result["reason"]

    def test_matched_vehicle_with_no_price_ineligible(self):
        customer = _add_customer("CUST-1")
        _add_finance_contract("FIN-1", MonthlyPayment=500)
        _add_rel("CUST-1", "FIN-1", FINANCED_BY)
        result = purls._payment_reduction_offer(customer, [{"price": None}])
        assert result["eligible"] is False
        assert "no real price" in result["reason"]

    def test_eligible_computes_real_amortization(self):
        customer = _add_customer("CUST-1", CreditScore="750")
        _add_finance_contract("FIN-1", MonthlyPayment=700, TermMonths=60)
        _add_rel("CUST-1", "FIN-1", FINANCED_BY)
        result = purls._payment_reduction_offer(customer, [{"price": 25000}])
        assert result["eligible"] is True
        assert result["basis"] == "real_amortization_math"
        assert result["current_monthly_payment"] == 700
        assert result["estimated_apr"] == 4.9  # credit score 750 -> excellent tier
        assert result["estimated_new_monthly_payment"] > 0
        assert result["estimated_savings"] == round(700 - result["estimated_new_monthly_payment"], 2)

    def test_lead_is_always_ineligible_since_it_can_never_have_a_finance_contract(self):
        # _current_finance_contract() only ever resolves for a real Customer entity
        # type -- a Lead is always ineligible here, even with a real FINANCED_BY
        # relationship on file, since that relationship is only ever meaningful once
        # the Lead has become a Customer.
        lead = _add_lead("LEAD-1")
        _add_finance_contract("FIN-1", MonthlyPayment=500)
        _add_rel("LEAD-1", "FIN-1", FINANCED_BY)
        result = purls._payment_reduction_offer(lead, [{"price": 20000}])
        assert result["eligible"] is False
        assert "No on-file finance contract" in result["reason"]

    def test_customer_with_no_real_credit_score_falls_back_to_default_apr_tier(self):
        customer = _add_customer("CUST-1", CreditScore=None)
        _add_finance_contract("FIN-1", MonthlyPayment=500)
        _add_rel("CUST-1", "FIN-1", FINANCED_BY)
        result = purls._payment_reduction_offer(customer, [{"price": 20000}])
        assert result["eligible"] is True
        assert result["estimated_apr"] == 6.9

    def test_bad_credit_score_string_falls_back_to_default_apr(self):
        customer = _add_customer("CUST-1", CreditScore="not-a-number")
        _add_finance_contract("FIN-1", MonthlyPayment=500)
        _add_rel("CUST-1", "FIN-1", FINANCED_BY)
        result = purls._payment_reduction_offer(customer, [{"price": 20000}])
        assert result["estimated_apr"] == 6.9


# ---------------------------------------------------------------------------
# get_personalized_offer (PUBLIC)
# ---------------------------------------------------------------------------

class TestGetPersonalizedOffer:

    def test_invalid_token(self):
        result = purls.get_personalized_offer("bad-token")
        assert result == {"error": "This link is not valid."}

    def test_valid_token_returns_full_offer(self):
        _add_customer("CUST-1")
        created = purls.generate_purl("EMP-1", offer_type="current_vehicle", customer_id="CUST-1")
        token = created["purl"]["token"]

        result = purls.get_personalized_offer(token)
        assert "error" not in result
        assert result["revoked"] is False
        assert result["person"]["id"] == "CUST-1"
        assert result["offer_type"] == "current_vehicle"
        assert "current_vehicles" in result
        assert "trade_equity" in result
        assert "inventory_matches" in result
        assert "payment_reduction" in result
        assert result["already_submitted"] is False
        assert result["generated_lead_id"] is None

    def test_revoked_link_exposes_no_pii_or_offer_data(self):
        # SECURITY: a revoked PURL is the mitigation when a link leaks; it must expose NOTHING
        # (no person PII, owned VINs, trade-equity, or on-file payment) on this public route.
        _add_customer("CUST-1")
        created = purls.generate_purl("EMP-1", customer_id="CUST-1")
        purls.revoke_purl(created["purl"]["id"], "EMP-9")

        result = purls.get_personalized_offer(created["purl"]["token"])
        assert result["revoked"] is True
        assert "error" in result
        # None of the sensitive fields may be present on a revoked response.
        for leaky in ("person", "current_vehicles", "trade_equity", "payment_reduction", "inventory_matches"):
            assert leaky not in result

    def test_person_no_longer_exists(self):
        _add_customer("CUST-1")
        created = purls.generate_purl("EMP-1", customer_id="CUST-1")
        token = created["purl"]["token"]

        ledger.entities.pop("CUST-1")

        result = purls.get_personalized_offer(token)
        assert result == {"error": "This link is no longer valid -- the person it was created for could not be found."}

    def test_already_submitted_reflects_generated_lead(self):
        _add_customer("CUST-1")
        created = purls.generate_purl("EMP-1", customer_id="CUST-1")
        token = created["purl"]["token"]
        purls.submit_purl_lead(token)

        result = purls.get_personalized_offer(token)
        assert result["already_submitted"] is True
        assert result["generated_lead_id"]

    def test_person_brief_shape(self):
        _add_customer("CUST-1", FirstName="Alex", LastName="Rivera", Email="alex@example.com", Phone="555-0001")
        created = purls.generate_purl("EMP-1", customer_id="CUST-1")
        result = purls.get_personalized_offer(created["purl"]["token"])
        person = result["person"]
        assert person["type"] == "customer"
        assert person["name"] == "Alex Rivera"
        assert person["email"] == "alex@example.com"
        assert person["phone"] == "555-0001"

    def test_lead_person_brief_type(self):
        _add_lead("LEAD-1")
        created = purls.generate_purl("EMP-1", lead_id="LEAD-1")
        result = purls.get_personalized_offer(created["purl"]["token"])
        assert result["person"]["type"] == "lead"


# ---------------------------------------------------------------------------
# record_purl_visit (PUBLIC)
# ---------------------------------------------------------------------------

class TestRecordPurlVisit:

    def test_invalid_token(self):
        result = purls.record_purl_visit("bad-token")
        assert result == {"error": "This link is not valid."}

    def test_first_visit_sets_first_and_last_visited_at(self):
        _add_customer("CUST-1")
        created = purls.generate_purl("EMP-1", customer_id="CUST-1")
        token = created["purl"]["token"]

        result = purls.record_purl_visit(token, user_agent="TestAgent/1.0")
        assert result["visit_count"] == 1

        entity = ledger.get_entity(created["purl"]["id"])
        assert entity.attributes["first_visited_at"] == result["visited_at"]
        assert entity.attributes["last_visited_at"] == result["visited_at"]
        assert entity.attributes["visit_log"][0]["user_agent"] == "TestAgent/1.0"

    def test_multiple_visits_increment_count_and_keep_first_visited(self):
        _add_customer("CUST-1")
        created = purls.generate_purl("EMP-1", customer_id="CUST-1")
        token = created["purl"]["token"]

        r1 = purls.record_purl_visit(token)
        r2 = purls.record_purl_visit(token)

        entity = ledger.get_entity(created["purl"]["id"])
        assert entity.attributes["visit_count"] == 2
        assert entity.attributes["first_visited_at"] == r1["visited_at"]
        assert len(entity.attributes["visit_log"]) == 2


# ---------------------------------------------------------------------------
# submit_purl_lead (PUBLIC)
# ---------------------------------------------------------------------------

class TestSubmitPurlLead:

    def test_invalid_token(self):
        result = purls.submit_purl_lead("bad-token")
        assert result == {"error": "This link is not valid."}

    def test_revoked_link_rejected(self):
        _add_customer("CUST-1")
        created = purls.generate_purl("EMP-1", customer_id="CUST-1")
        purls.revoke_purl(created["purl"]["id"], "EMP-9")

        result = purls.submit_purl_lead(created["purl"]["token"])
        assert result == {"error": "This link has been revoked."}

    def test_double_submit_rejected(self):
        _add_customer("CUST-1")
        created = purls.generate_purl("EMP-1", customer_id="CUST-1")
        token = created["purl"]["token"]
        first = purls.submit_purl_lead(token)

        second = purls.submit_purl_lead(token)
        assert "error" in second
        assert "already been submitted" in second["error"]
        assert second["lead_id"] == first["lead_id"]

    def test_successful_submit_creates_real_lead_assigned_to_creator(self):
        _add_customer("CUST-1", FirstName="Jane", LastName="Doe")
        created = purls.generate_purl("EMP-7", customer_id="CUST-1")
        token = created["purl"]["token"]

        result = purls.submit_purl_lead(token, notes="Ready to buy")
        assert result["assigned_to"] == "EMP-7"

        lead = ledger.get_entity(result["lead_id"])
        assert lead.entity_type == LEAD
        assert lead.attributes["Source"] == "PURL"
        assert lead.attributes["FirstName"] == "Jane"
        assert lead.attributes["Notes"] == "Ready to buy"
        assert lead.attributes["SourcePurlId"] == created["purl"]["id"]

        purl_entity = ledger.get_entity(created["purl"]["id"])
        assert purl_entity.attributes["generated_lead_id"] == result["lead_id"]
        assert purl_entity.attributes["lead_submitted_by"] == purls.CUSTOMER_SENTINEL

    def test_person_no_longer_exists(self):
        _add_customer("CUST-1")
        created = purls.generate_purl("EMP-1", customer_id="CUST-1")
        token = created["purl"]["token"]
        ledger.entities.pop("CUST-1")

        result = purls.submit_purl_lead(token)
        assert result == {"error": "This link is no longer valid -- the person it was created for could not be found."}


# ---------------------------------------------------------------------------
# create_mail_piece
# ---------------------------------------------------------------------------

class TestCreateMailPiece:

    def test_purl_not_found(self):
        result = purls.create_mail_piece("PURL-NOPE", "Spring Postcard", "postcard")
        assert "error" in result
        assert "not found" in result["error"]

    def test_creates_mail_piece_metadata(self):
        _add_customer("CUST-1")
        created = purls.generate_purl("EMP-1", customer_id="CUST-1")
        purl_id = created["purl"]["id"]

        result = purls.create_mail_piece(purl_id, "Spring Postcard", "postcard", mail_date="2026-03-01", created_by="EMP-2")
        piece = result["purl"]["mail_piece"]
        assert piece["piece_name"] == "Spring Postcard"
        assert piece["piece_type"] == "postcard"
        assert piece["mail_date"] == "2026-03-01"
        assert piece["created_by"] == "EMP-2"

    def test_overwrites_prior_mail_piece(self):
        _add_customer("CUST-1")
        created = purls.generate_purl("EMP-1", customer_id="CUST-1")
        purl_id = created["purl"]["id"]

        purls.create_mail_piece(purl_id, "First", "postcard")
        result = purls.create_mail_piece(purl_id, "Second", "letter")
        assert result["purl"]["mail_piece"]["piece_name"] == "Second"


# ---------------------------------------------------------------------------
# get_purl_analytics
# ---------------------------------------------------------------------------

class TestGetPurlAnalytics:

    def test_purl_not_found(self):
        result = purls.get_purl_analytics("PURL-NOPE")
        assert "error" in result
        assert "not found" in result["error"]

    def test_analytics_shape_for_no_activity(self):
        _add_customer("CUST-1")
        created = purls.generate_purl("EMP-1", customer_id="CUST-1")
        result = purls.get_purl_analytics(created["purl"]["id"])
        assert result["visits"] == 0
        assert result["lead_generated"] is False
        assert result["lead_id"] is None
        corr = result["correlated_since_creation"]
        assert corr["basis"] == "real_but_not_proven_causal"
        assert corr["appointments_count"] == 0
        assert corr["funded_deals_count"] == 0
        assert corr["revenue"] == 0

    def test_counts_real_visits(self):
        _add_customer("CUST-1")
        created = purls.generate_purl("EMP-1", customer_id="CUST-1")
        token = created["purl"]["token"]
        purls.record_purl_visit(token)
        purls.record_purl_visit(token)

        result = purls.get_purl_analytics(created["purl"]["id"])
        assert result["visits"] == 2

    def test_counts_appointments_since_creation(self):
        _add_customer("CUST-1")
        created = purls.generate_purl("EMP-1", customer_id="CUST-1")
        entity = ledger.get_entity(created["purl"]["id"])
        entity.attributes["created_at"] = "2026-01-01T00:00:00+00:00"

        _add_appointment("APPT-1", customer_id="CUST-1", created_at="2026-02-01T00:00:00+00:00")
        # An appointment BEFORE the PURL was created shouldn't count.
        _add_appointment("APPT-OLD", customer_id="CUST-1", created_at="2025-01-01T00:00:00+00:00")

        result = purls.get_purl_analytics(created["purl"]["id"])
        assert result["correlated_since_creation"]["appointments_count"] == 1

    def test_counts_real_funded_deals_and_revenue_for_customer_target(self):
        _add_customer("CUST-1")
        created = purls.generate_purl("EMP-1", customer_id="CUST-1")
        entity = ledger.get_entity(created["purl"]["id"])
        entity.attributes["created_at"] = "2026-01-01T00:00:00+00:00"

        _add_vehicle("VEH-1", Price=30000, Cost=25000)
        _add_deal("DEAL-1", customer_id="CUST-1", status="funded", vehicle_id="VEH-1", funded_at="2026-02-01T00:00:00+00:00")

        result = purls.get_purl_analytics(created["purl"]["id"])
        assert result["correlated_since_creation"]["funded_deals_count"] == 1
        assert result["correlated_since_creation"]["revenue"] == 30000.0

    def test_lead_target_never_counts_funded_deals(self):
        # _funded_deals_since is only ever computed when the target is a Customer --
        # a Lead-targeted PURL always reports 0 deals/revenue, even if a deal
        # somehow references the lead's own id as customer_id.
        _add_lead("LEAD-1")
        created = purls.generate_purl("EMP-1", lead_id="LEAD-1")
        _add_deal("DEAL-1", customer_id="LEAD-1", status="funded")

        result = purls.get_purl_analytics(created["purl"]["id"])
        assert result["correlated_since_creation"]["funded_deals_count"] == 0
        assert result["correlated_since_creation"]["revenue"] == 0

    def test_reflects_generated_lead(self):
        _add_customer("CUST-1")
        created = purls.generate_purl("EMP-1", customer_id="CUST-1")
        token = created["purl"]["token"]
        submitted = purls.submit_purl_lead(token)

        result = purls.get_purl_analytics(created["purl"]["id"])
        assert result["lead_generated"] is True
        assert result["lead_id"] == submitted["lead_id"]


# ---------------------------------------------------------------------------
# get_purl_dashboard
# ---------------------------------------------------------------------------

class TestGetPurlDashboard:

    def test_empty_dashboard(self):
        result = purls.get_purl_dashboard(ADMIN)
        assert result["kpis"]["total_purls"] == 0
        assert result["kpis"]["conversion_rate"] == 0.0
        assert result["recent_purls"] == []

    def test_kpis_reflect_real_state(self):
        _add_customer("CUST-1")
        _add_customer("CUST-2")
        a = purls.generate_purl("EMP-1", customer_id="CUST-1")
        purls.generate_purl("EMP-1", customer_id="CUST-2")
        purls.revoke_purl(a["purl"]["id"], "EMP-9")

        result = purls.get_purl_dashboard(ADMIN)
        assert result["kpis"]["total_purls"] == 2
        assert result["kpis"]["active_purls"] == 1

    def test_conversion_rate_computed_from_generated_leads(self):
        _add_customer("CUST-1")
        _add_customer("CUST-2")
        a = purls.generate_purl("EMP-1", customer_id="CUST-1")
        purls.generate_purl("EMP-1", customer_id="CUST-2")
        purls.submit_purl_lead(a["purl"]["token"])

        result = purls.get_purl_dashboard(ADMIN)
        assert result["kpis"]["leads_generated"] == 1
        assert result["kpis"]["conversion_rate"] == 50.0

    def test_filters_by_created_by(self):
        _add_customer("CUST-1")
        _add_customer("CUST-2")
        purls.generate_purl("EMP-1", customer_id="CUST-1")
        purls.generate_purl("EMP-2", customer_id="CUST-2")

        result = purls.get_purl_dashboard(ADMIN, created_by="EMP-1")
        assert result["kpis"]["total_purls"] == 1

    def test_recent_purls_capped_at_50(self):
        for i in range(55):
            _add_customer(f"CUST-{i}")
            purls.generate_purl("EMP-1", customer_id=f"CUST-{i}")
        result = purls.get_purl_dashboard(ADMIN)
        assert result["kpis"]["total_purls"] == 55
        assert len(result["recent_purls"]) == 50


# ---------------------------------------------------------------------------
# get_purl_activity_for_customer
# ---------------------------------------------------------------------------

class TestGetPurlActivityForCustomer:

    def test_no_purls_returns_empty(self):
        result = purls.get_purl_activity_for_customer("CUST-1")
        assert result == {"count": 0, "purl_count": 0, "visits": [], "basis": "real_purl_visit_log"}

    def test_flattens_visit_logs_across_multiple_purls(self):
        _add_customer("CUST-1")
        p1 = purls.generate_purl("EMP-1", offer_type="current_vehicle", customer_id="CUST-1")
        p2 = purls.generate_purl("EMP-1", offer_type="trade_equity", customer_id="CUST-1")

        purls.record_purl_visit(p1["purl"]["token"])
        purls.record_purl_visit(p2["purl"]["token"])
        purls.record_purl_visit(p2["purl"]["token"])

        result = purls.get_purl_activity_for_customer("CUST-1")
        assert result["count"] == 3
        assert result["purl_count"] == 2

    def test_excludes_other_customers_purls(self):
        _add_customer("CUST-1")
        _add_customer("CUST-2")
        p1 = purls.generate_purl("EMP-1", customer_id="CUST-1")
        p2 = purls.generate_purl("EMP-1", customer_id="CUST-2")
        purls.record_purl_visit(p1["purl"]["token"])
        purls.record_purl_visit(p2["purl"]["token"])

        result = purls.get_purl_activity_for_customer("CUST-1")
        assert result["count"] == 1

    def test_sorted_most_recent_first(self):
        _add_customer("CUST-1")
        p = purls.generate_purl("EMP-1", customer_id="CUST-1")
        entity = ledger.get_entity(p["purl"]["id"])
        entity.attributes["visit_log"] = [
            {"visited_at": "2026-01-01T00:00:00+00:00", "user_agent": None},
            {"visited_at": "2026-06-01T00:00:00+00:00", "user_agent": None},
        ]
        result = purls.get_purl_activity_for_customer("CUST-1")
        assert result["visits"][0]["visited_at"] == "2026-06-01T00:00:00+00:00"

    def test_capped_at_20(self):
        _add_customer("CUST-1")
        p = purls.generate_purl("EMP-1", customer_id="CUST-1")
        entity = ledger.get_entity(p["purl"]["id"])
        entity.attributes["visit_log"] = [
            {"visited_at": f"2026-01-{i + 1:02d}T00:00:00+00:00", "user_agent": None} for i in range(25)
        ]
        result = purls.get_purl_activity_for_customer("CUST-1")
        assert result["count"] == 25
        assert len(result["visits"]) == 20


# ---------------------------------------------------------------------------
# ACL: core/purls_api.py
# ---------------------------------------------------------------------------

ALLOWED_ROLES = (ADMIN, OPERATIONS, SALES, MARKETING)
DENIED_ROLES = (SERVICE, FINANCE, "BOGUS_ROLE", "", None)


class TestAcl:

    @pytest.mark.parametrize("role", ALLOWED_ROLES)
    def test_allowed_roles_can_generate(self, role):
        ledger.reset()
        _add_customer("CUST-1")
        result = purls_api.generate_purl_api(role, "EMP-1", customer_id="CUST-1")
        assert "error" not in result

    @pytest.mark.parametrize("role", DENIED_ROLES)
    def test_denied_roles_cannot_generate(self, role):
        _add_customer("CUST-1")
        result = purls_api.generate_purl_api(role, "EMP-1", customer_id="CUST-1")
        assert result == {"error": "You don't have access to the PURL Platform with your current role."}

    @pytest.mark.parametrize("role", DENIED_ROLES)
    def test_denied_roles_cannot_revoke(self, role):
        result = purls_api.revoke_purl_api(role, "PURL-1", "EMP-1")
        assert result == {"error": "You don't have access to the PURL Platform with your current role."}

    @pytest.mark.parametrize("role", DENIED_ROLES)
    def test_denied_roles_cannot_list(self, role):
        result = purls_api.list_purls_api(role)
        assert result == {"error": "You don't have access to the PURL Platform with your current role."}

    @pytest.mark.parametrize("role", DENIED_ROLES)
    def test_denied_roles_cannot_create_mail_piece(self, role):
        result = purls_api.create_mail_piece_api(role, "PURL-1", "Postcard", "postcard")
        assert result == {"error": "You don't have access to the PURL Platform with your current role."}

    @pytest.mark.parametrize("role", DENIED_ROLES)
    def test_denied_roles_cannot_get_analytics(self, role):
        result = purls_api.get_purl_analytics_api(role, "PURL-1")
        assert result == {"error": "You don't have access to the PURL Platform with your current role."}

    @pytest.mark.parametrize("role", DENIED_ROLES)
    def test_denied_roles_cannot_get_dashboard(self, role):
        result = purls_api.get_purl_dashboard_api(role)
        assert result == {"error": "You don't have access to the PURL Platform with your current role."}

    @pytest.mark.parametrize("role", DENIED_ROLES)
    def test_denied_roles_cannot_bulk_generate(self, role):
        result = purls_api.bulk_generate_purls_api(role, "EMP-1", "marketing_list", "MLIST-1")
        assert result == {"error": "You don't have access to the PURL Platform with your current role."}

    @pytest.mark.parametrize("role", ALLOWED_ROLES)
    def test_allowed_roles_reach_real_dashboard(self, role):
        result = purls_api.get_purl_dashboard_api(role)
        assert "kpis" in result

    def test_allowed_role_but_nonexistent_purl_passes_through_real_error(self):
        result = purls_api.revoke_purl_api(ADMIN, "PURL-NOPE", "EMP-1")
        assert "error" in result
        assert "not found" in result["error"]

    def test_bulk_generate_reaches_real_function_for_allowed_role(self):
        _add_customer("CUST-1")
        _add_marketing_list("MLIST-1", member_ids=["CUST-1"])
        result = purls_api.bulk_generate_purls_api(ADMIN, "EMP-1", "marketing_list", "MLIST-1")
        assert result["created_count"] == 1
