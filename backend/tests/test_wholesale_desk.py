"""
Tests for core/wholesale_desk.py + core/wholesale_desk_api.py -- Inventory's
Wholesale disposition center: Open Offers, Sold Wholesale Units, and Fund
Collection, all real action layers on top of a real WholesaleOffer entity.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import VEHICLE, WHOLESALE_OFFER
from core import wholesale_desk
from core import wholesale_desk_api
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    monkeypatch.setattr(wholesale_desk, "save_graph", lambda filepath: None)


_MUTATE_ROLES = (ADMIN, OPERATIONS)
_MUTATE_DENIED_ROLES = (SALES, SERVICE, MARKETING, FINANCE)
_VIEW_ROLES = (ADMIN, OPERATIONS, SALES, SERVICE, MARKETING, FINANCE)


def _add_vehicle(vehicle_id="VEH-1", date_sold=None, price="10000", cost="8000", vin="1FTFW1E5", make="Ford", model="F-150"):
    attrs = {"VIN": vin, "StockNumber": "S1", "Year": "2022", "Make": make, "Model": model, "Price": price, "Cost": cost}
    if date_sold:
        attrs["DateSold"] = date_sold
    ledger.add_entity(Entity(id=vehicle_id, entity_type=VEHICLE, attributes=attrs))
    return vehicle_id


def _submit(vehicle_id="VEH-1", buyer_name="Acme Wholesale", offer_amount=9000, submitted_by="EMP-1", notes=""):
    return wholesale_desk.submit_offer(vehicle_id, buyer_name, offer_amount, submitted_by, notes=notes)


def test_countered_and_accepted_offer_remain_actionable_until_vehicle_is_sold():
    _add_vehicle()
    offer = _submit()
    wholesale_desk.counter_offer(offer["id"], 9500, "EMP-1")
    assert wholesale_desk.get_wholesale_desk_summary()["open_offers"]["offers"][0]["status"] == "countered"
    assert wholesale_desk.accept_offer(offer["id"], "EMP-1")["status"] == "accepted"
    assert wholesale_desk.get_wholesale_desk_summary()["open_offers"]["count"] == 1
    sale = wholesale_desk.mark_wholesale_sold("VEH-1", "Acme Wholesale", 9500, "EMP-1", offer["id"])
    assert sale["wholesale_sale"]["sale_price"] == 9500
    assert wholesale_desk.get_wholesale_desk_summary()["open_offers"]["count"] == 0


# ---------------------------------------------------------------------------
# submit_offer
# ---------------------------------------------------------------------------

class TestSubmitOffer:
    def test_rejects_unknown_vehicle(self):
        result = wholesale_desk.submit_offer("VEH-NOPE", "Acme", 9000, "EMP-1")
        assert "error" in result

    def test_rejects_non_numeric_offer_amount(self):
        _add_vehicle("VEH-1")
        result = wholesale_desk.submit_offer("VEH-1", "Acme", "not-a-number", "EMP-1")
        assert "error" in result

    def test_rejects_zero_offer_amount(self):
        _add_vehicle("VEH-1")
        result = wholesale_desk.submit_offer("VEH-1", "Acme", 0, "EMP-1")
        assert "error" in result

    def test_rejects_negative_offer_amount(self):
        _add_vehicle("VEH-1")
        result = wholesale_desk.submit_offer("VEH-1", "Acme", -500, "EMP-1")
        assert "error" in result

    def test_succeeds_on_a_valid_offer(self):
        _add_vehicle("VEH-1")
        result = _submit()
        assert "error" not in result
        assert result["id"].startswith("WOFR")
        assert result["vehicle_id"] == "VEH-1"
        assert result["buyer_name"] == "Acme Wholesale"
        assert result["offer_amount"] == 9000
        assert result["status"] == "pending"
        assert result["decided_by"] is None
        assert result["decided_at"] is None

    def test_persists_the_offer_in_the_ledger(self):
        _add_vehicle("VEH-1")
        result = _submit()
        stored = ledger.get_entity(result["id"])
        assert stored is not None
        assert stored.entity_type == WHOLESALE_OFFER


# ---------------------------------------------------------------------------
# accept_offer
# ---------------------------------------------------------------------------

class TestAcceptOffer:
    def test_rejects_unknown_offer(self):
        result = wholesale_desk.accept_offer("WOFR-NOPE", "EMP-1")
        assert "error" in result

    def test_rejects_a_non_pending_offer(self):
        _add_vehicle("VEH-1")
        offer = _submit()
        wholesale_desk.accept_offer(offer["id"], "EMP-1")
        result = wholesale_desk.accept_offer(offer["id"], "EMP-2")
        assert "error" in result

    def test_accepts_a_pending_offer(self):
        _add_vehicle("VEH-1")
        offer = _submit()
        result = wholesale_desk.accept_offer(offer["id"], "EMP-1")
        assert "error" not in result
        assert result["status"] == "accepted"
        assert result["decided_by"] == "EMP-1"
        assert result["decided_at"] is not None


# ---------------------------------------------------------------------------
# reject_offer
# ---------------------------------------------------------------------------

class TestRejectOffer:
    def test_rejects_unknown_offer(self):
        result = wholesale_desk.reject_offer("WOFR-NOPE", "EMP-1")
        assert "error" in result

    def test_rejects_a_non_pending_offer(self):
        _add_vehicle("VEH-1")
        offer = _submit()
        wholesale_desk.accept_offer(offer["id"], "EMP-1")
        result = wholesale_desk.reject_offer(offer["id"], "EMP-1")
        assert "error" in result

    def test_rejects_a_pending_offer_without_notes(self):
        _add_vehicle("VEH-1")
        offer = _submit()
        result = wholesale_desk.reject_offer(offer["id"], "EMP-1")
        assert "error" not in result
        assert result["status"] == "rejected"
        assert result["notes"] == ""

    def test_rejects_a_pending_offer_and_appends_notes(self):
        _add_vehicle("VEH-1")
        offer = _submit(notes="Original note")
        result = wholesale_desk.reject_offer(offer["id"], "EMP-1", notes="too low")
        assert "Original note" in result["notes"]
        assert "Rejected: too low" in result["notes"]


# ---------------------------------------------------------------------------
# counter_offer
# ---------------------------------------------------------------------------

class TestCounterOffer:
    def test_rejects_unknown_offer(self):
        result = wholesale_desk.counter_offer("WOFR-NOPE", 9500, "EMP-1")
        assert "error" in result

    def test_rejects_a_non_pending_offer(self):
        _add_vehicle("VEH-1")
        offer = _submit()
        wholesale_desk.accept_offer(offer["id"], "EMP-1")
        result = wholesale_desk.counter_offer(offer["id"], 9500, "EMP-1")
        assert "error" in result

    def test_rejects_a_non_numeric_counter_amount(self):
        _add_vehicle("VEH-1")
        offer = _submit()
        result = wholesale_desk.counter_offer(offer["id"], "nope", "EMP-1")
        assert "error" in result

    def test_counters_a_pending_offer(self):
        _add_vehicle("VEH-1")
        offer = _submit()
        result = wholesale_desk.counter_offer(offer["id"], 9500, "EMP-1")
        assert "error" not in result
        assert result["status"] == "countered"
        assert result["counter_amount"] == 9500
        assert result["decided_by"] == "EMP-1"


# ---------------------------------------------------------------------------
# withdraw_offer
# ---------------------------------------------------------------------------

class TestWithdrawOffer:
    def test_rejects_unknown_offer(self):
        result = wholesale_desk.withdraw_offer("WOFR-NOPE", "EMP-1")
        assert "error" in result

    def test_rejects_an_already_accepted_offer(self):
        _add_vehicle("VEH-1")
        offer = _submit()
        wholesale_desk.accept_offer(offer["id"], "EMP-1")
        result = wholesale_desk.withdraw_offer(offer["id"], "EMP-1")
        assert "error" in result

    def test_rejects_an_already_rejected_offer(self):
        _add_vehicle("VEH-1")
        offer = _submit()
        wholesale_desk.reject_offer(offer["id"], "EMP-1")
        result = wholesale_desk.withdraw_offer(offer["id"], "EMP-1")
        assert "error" in result

    def test_withdraws_a_pending_offer(self):
        _add_vehicle("VEH-1")
        offer = _submit()
        result = wholesale_desk.withdraw_offer(offer["id"], "EMP-1")
        assert "error" not in result
        assert result["status"] == "withdrawn"

    def test_withdraws_a_countered_offer(self):
        _add_vehicle("VEH-1")
        offer = _submit()
        wholesale_desk.counter_offer(offer["id"], 9500, "EMP-1")
        result = wholesale_desk.withdraw_offer(offer["id"], "EMP-1")
        assert "error" not in result
        assert result["status"] == "withdrawn"


# ---------------------------------------------------------------------------
# list_offers
# ---------------------------------------------------------------------------

class TestListOffers:
    def test_empty_when_no_offers(self):
        result = wholesale_desk.list_offers()
        assert result == {"count": 0, "offers": []}

    def test_filters_by_vehicle_id(self):
        _add_vehicle("VEH-1")
        _add_vehicle("VEH-2")
        _submit(vehicle_id="VEH-1")
        _submit(vehicle_id="VEH-2")

        result = wholesale_desk.list_offers(vehicle_id="VEH-1")
        assert result["count"] == 1
        assert result["offers"][0]["vehicle_id"] == "VEH-1"

    def test_filters_by_status(self):
        _add_vehicle("VEH-1")
        _add_vehicle("VEH-2")
        pending = _submit(vehicle_id="VEH-1")
        accepted = _submit(vehicle_id="VEH-2")
        wholesale_desk.accept_offer(accepted["id"], "EMP-1")

        result = wholesale_desk.list_offers(status="pending")
        assert result["count"] == 1
        assert result["offers"][0]["id"] == pending["id"]

    def test_sorted_most_recently_submitted_first(self):
        _add_vehicle("VEH-1")
        first = _submit(vehicle_id="VEH-1", buyer_name="Buyer A")
        second = _submit(vehicle_id="VEH-1", buyer_name="Buyer B")

        result = wholesale_desk.list_offers()
        ids = [o["id"] for o in result["offers"]]
        assert ids[0] == second["id"]
        assert ids[1] == first["id"]


# ---------------------------------------------------------------------------
# mark_wholesale_sold
# ---------------------------------------------------------------------------

class TestMarkWholesaleSold:
    def test_rejects_unknown_vehicle(self):
        result = wholesale_desk.mark_wholesale_sold("VEH-NOPE", "Acme", 9000, "EMP-1")
        assert "error" in result

    def test_rejects_an_already_sold_vehicle(self):
        _add_vehicle("VEH-1", date_sold="2026-01-01")
        result = wholesale_desk.mark_wholesale_sold("VEH-1", "Acme", 9000, "EMP-1")
        assert "error" in result

    def test_rejects_a_non_numeric_sale_price(self):
        _add_vehicle("VEH-1")
        result = wholesale_desk.mark_wholesale_sold("VEH-1", "Acme", "nope", "EMP-1")
        assert "error" in result

    def test_marks_a_vehicle_sold_wholesale(self):
        _add_vehicle("VEH-1")
        result = wholesale_desk.mark_wholesale_sold("VEH-1", "Acme Wholesale", 9000, "EMP-1")
        assert "error" not in result

        vehicle = ledger.get_entity("VEH-1")
        assert vehicle.attributes["DateSold"] is not None
        assert vehicle.attributes["disposition_channel"] == "wholesale"
        sale = vehicle.attributes["wholesale_sale"]
        assert sale["buyer_name"] == "Acme Wholesale"
        assert sale["sale_price"] == 9000
        assert sale["sold_by"] == "EMP-1"
        assert sale["offer_id"] is None
        assert sale["funds_collected"] is None

    def test_marking_sold_with_a_pending_offer_id_accepts_that_offer(self):
        _add_vehicle("VEH-1")
        offer = _submit()
        wholesale_desk.mark_wholesale_sold("VEH-1", "Acme", 9000, "EMP-1", offer_id=offer["id"])

        stored_offer = wholesale_desk._get_offer(offer["id"])
        assert stored_offer.attributes["status"] == "accepted"
        assert stored_offer.attributes["decided_by"] == "EMP-1"

    def test_marking_sold_with_an_already_decided_offer_id_leaves_it_untouched(self):
        _add_vehicle("VEH-1")
        offer = _submit()
        wholesale_desk.reject_offer(offer["id"], "EMP-2", notes="too low")
        wholesale_desk.mark_wholesale_sold("VEH-1", "Acme", 9000, "EMP-1", offer_id=offer["id"])

        stored_offer = wholesale_desk._get_offer(offer["id"])
        assert stored_offer.attributes["status"] == "rejected"
        assert stored_offer.attributes["decided_by"] == "EMP-2"


# ---------------------------------------------------------------------------
# get_sold_wholesale_units
# ---------------------------------------------------------------------------

class TestGetSoldWholesaleUnits:
    def test_empty_when_none(self):
        result = wholesale_desk.get_sold_wholesale_units()
        assert result == {"count": 0, "vehicles": []}

    def test_only_includes_wholesale_disposition_vehicles(self):
        _add_vehicle("VEH-1")
        _add_vehicle("VEH-2", date_sold="2026-01-01")  # sold retail, not wholesale
        wholesale_desk.mark_wholesale_sold("VEH-1", "Acme", 9000, "EMP-1")

        result = wholesale_desk.get_sold_wholesale_units()
        assert result["count"] == 1
        assert result["vehicles"][0]["vehicle_id"] == "VEH-1"

    def test_respects_the_limit(self):
        for i in range(3):
            _add_vehicle(f"VEH-{i}")
            wholesale_desk.mark_wholesale_sold(f"VEH-{i}", "Acme", 9000, "EMP-1")

        result = wholesale_desk.get_sold_wholesale_units(limit=2)
        assert result["count"] == 3
        assert len(result["vehicles"]) == 2


# ---------------------------------------------------------------------------
# record_funds_collected
# ---------------------------------------------------------------------------

class TestRecordFundsCollected:
    def test_rejects_unknown_vehicle(self):
        result = wholesale_desk.record_funds_collected("VEH-NOPE", 9000, "EMP-1")
        assert "error" in result

    def test_rejects_a_vehicle_with_no_wholesale_sale(self):
        _add_vehicle("VEH-1")
        result = wholesale_desk.record_funds_collected("VEH-1", 9000, "EMP-1")
        assert "error" in result

    def test_rejects_a_non_numeric_amount(self):
        _add_vehicle("VEH-1")
        wholesale_desk.mark_wholesale_sold("VEH-1", "Acme", 9000, "EMP-1")
        result = wholesale_desk.record_funds_collected("VEH-1", "nope", "EMP-1")
        assert "error" in result

    def test_records_funds_collected(self):
        _add_vehicle("VEH-1")
        wholesale_desk.mark_wholesale_sold("VEH-1", "Acme", 9000, "EMP-1")
        result = wholesale_desk.record_funds_collected("VEH-1", 9000, "EMP-2", method="wire", notes="paid in full")
        assert "error" not in result
        funds = result["wholesale_sale"]["funds_collected"]
        assert funds["amount"] == 9000
        assert funds["method"] == "wire"
        assert funds["collected_by"] == "EMP-2"

    def test_rejects_double_collection(self):
        _add_vehicle("VEH-1")
        wholesale_desk.mark_wholesale_sold("VEH-1", "Acme", 9000, "EMP-1")
        wholesale_desk.record_funds_collected("VEH-1", 9000, "EMP-2")
        result = wholesale_desk.record_funds_collected("VEH-1", 9000, "EMP-2")
        assert "error" in result


# ---------------------------------------------------------------------------
# get_fund_collection_status
# ---------------------------------------------------------------------------

class TestGetFundCollectionStatus:
    def test_empty_structure_when_none(self):
        result = wholesale_desk.get_fund_collection_status()
        assert result["awaiting_collection"]["count"] == 0
        assert result["collected"]["count"] == 0
        assert result["awaiting_collection"]["total_amount"] == 0
        assert result["collected"]["total_amount"] == 0

    def test_splits_vehicles_into_awaiting_and_collected(self):
        _add_vehicle("VEH-1")
        _add_vehicle("VEH-2")
        wholesale_desk.mark_wholesale_sold("VEH-1", "Acme", 9000, "EMP-1")
        wholesale_desk.mark_wholesale_sold("VEH-2", "Acme", 8000, "EMP-1")
        wholesale_desk.record_funds_collected("VEH-2", 8000, "EMP-2")

        result = wholesale_desk.get_fund_collection_status()
        assert result["awaiting_collection"]["count"] == 1
        assert result["awaiting_collection"]["vehicles"][0]["vehicle_id"] == "VEH-1"
        assert result["collected"]["count"] == 1
        assert result["collected"]["vehicles"][0]["vehicle_id"] == "VEH-2"

    def test_computes_correct_totals(self):
        _add_vehicle("VEH-1")
        _add_vehicle("VEH-2")
        wholesale_desk.mark_wholesale_sold("VEH-1", "Acme", 9000, "EMP-1")
        wholesale_desk.mark_wholesale_sold("VEH-2", "Acme", 8000, "EMP-1")
        wholesale_desk.record_funds_collected("VEH-2", 7500, "EMP-2")

        result = wholesale_desk.get_fund_collection_status()
        assert result["awaiting_collection"]["total_amount"] == 9000
        assert result["collected"]["total_amount"] == 7500


# ---------------------------------------------------------------------------
# get_wholesale_desk_summary
# ---------------------------------------------------------------------------

class TestGetWholesaleDeskSummary:
    def test_composes_the_real_sections(self):
        _add_vehicle("VEH-1")
        _add_vehicle("VEH-2")
        _submit(vehicle_id="VEH-1")
        wholesale_desk.mark_wholesale_sold("VEH-2", "Acme", 8000, "EMP-1")

        summary = wholesale_desk.get_wholesale_desk_summary()
        assert summary["open_offers"]["count"] == 1
        assert summary["sold_wholesale_units"]["count"] == 1
        assert summary["fund_collection"]["awaiting_collection"]["count"] == 1


# ---------------------------------------------------------------------------
# ACL sweep -- core/wholesale_desk_api.py
# ---------------------------------------------------------------------------

class TestAcl:
    def test_get_catalog_api_has_no_role_gate(self):
        result = wholesale_desk_api.get_catalog_api()
        assert "offer_statuses" in result

    @pytest.mark.parametrize("role", _MUTATE_DENIED_ROLES)
    def test_submit_offer_api_denied(self, role):
        _add_vehicle("VEH-1")
        result = wholesale_desk_api.submit_offer_api(role, "EMP-1", "VEH-1", "Acme", 9000)
        assert "error" in result

    @pytest.mark.parametrize("role", _MUTATE_ROLES)
    def test_submit_offer_api_allowed(self, role):
        ledger.reset()
        _add_vehicle("VEH-1")
        result = wholesale_desk_api.submit_offer_api(role, "EMP-1", "VEH-1", "Acme", 9000)
        assert result["status"] == "pending"

    @pytest.mark.parametrize("role", _MUTATE_DENIED_ROLES)
    def test_accept_offer_api_denied(self, role):
        _add_vehicle("VEH-1")
        offer = _submit()
        result = wholesale_desk_api.accept_offer_api(role, "EMP-1", offer["id"])
        assert "error" in result

    @pytest.mark.parametrize("role", _MUTATE_ROLES)
    def test_accept_offer_api_allowed(self, role):
        ledger.reset()
        _add_vehicle("VEH-1")
        offer = _submit()
        result = wholesale_desk_api.accept_offer_api(role, "EMP-1", offer["id"])
        assert result["status"] == "accepted"

    @pytest.mark.parametrize("role", _MUTATE_DENIED_ROLES)
    def test_reject_offer_api_denied(self, role):
        _add_vehicle("VEH-1")
        offer = _submit()
        result = wholesale_desk_api.reject_offer_api(role, "EMP-1", offer["id"])
        assert "error" in result

    @pytest.mark.parametrize("role", _MUTATE_ROLES)
    def test_reject_offer_api_allowed(self, role):
        ledger.reset()
        _add_vehicle("VEH-1")
        offer = _submit()
        result = wholesale_desk_api.reject_offer_api(role, "EMP-1", offer["id"])
        assert result["status"] == "rejected"

    @pytest.mark.parametrize("role", _MUTATE_DENIED_ROLES)
    def test_counter_offer_api_denied(self, role):
        _add_vehicle("VEH-1")
        offer = _submit()
        result = wholesale_desk_api.counter_offer_api(role, "EMP-1", offer["id"], 9500)
        assert "error" in result

    @pytest.mark.parametrize("role", _MUTATE_ROLES)
    def test_counter_offer_api_allowed(self, role):
        ledger.reset()
        _add_vehicle("VEH-1")
        offer = _submit()
        result = wholesale_desk_api.counter_offer_api(role, "EMP-1", offer["id"], 9500)
        assert result["status"] == "countered"

    @pytest.mark.parametrize("role", _MUTATE_DENIED_ROLES)
    def test_withdraw_offer_api_denied(self, role):
        _add_vehicle("VEH-1")
        offer = _submit()
        result = wholesale_desk_api.withdraw_offer_api(role, "EMP-1", offer["id"])
        assert "error" in result

    @pytest.mark.parametrize("role", _MUTATE_ROLES)
    def test_withdraw_offer_api_allowed(self, role):
        ledger.reset()
        _add_vehicle("VEH-1")
        offer = _submit()
        result = wholesale_desk_api.withdraw_offer_api(role, "EMP-1", offer["id"])
        assert result["status"] == "withdrawn"

    @pytest.mark.parametrize("role", _VIEW_ROLES)
    def test_list_offers_api_allowed_for_every_role(self, role):
        result = wholesale_desk_api.list_offers_api(role)
        assert "count" in result

    def test_list_offers_api_denies_an_unrecognized_role(self):
        result = wholesale_desk_api.list_offers_api("NOT_A_REAL_ROLE")
        assert "error" in result

    @pytest.mark.parametrize("role", _MUTATE_DENIED_ROLES)
    def test_mark_wholesale_sold_api_denied(self, role):
        _add_vehicle("VEH-1")
        result = wholesale_desk_api.mark_wholesale_sold_api(role, "EMP-1", "VEH-1", "Acme", 9000)
        assert "error" in result

    @pytest.mark.parametrize("role", _MUTATE_ROLES)
    def test_mark_wholesale_sold_api_allowed(self, role):
        ledger.reset()
        _add_vehicle("VEH-1")
        result = wholesale_desk_api.mark_wholesale_sold_api(role, "EMP-1", "VEH-1", "Acme", 9000)
        assert "error" not in result

    @pytest.mark.parametrize("role", _VIEW_ROLES)
    def test_get_sold_wholesale_units_api_allowed_for_every_role(self, role):
        result = wholesale_desk_api.get_sold_wholesale_units_api(role)
        assert "count" in result

    def test_get_sold_wholesale_units_api_denies_an_unrecognized_role(self):
        result = wholesale_desk_api.get_sold_wholesale_units_api("NOT_A_REAL_ROLE")
        assert "error" in result

    @pytest.mark.parametrize("role", _MUTATE_DENIED_ROLES)
    def test_record_funds_collected_api_denied(self, role):
        _add_vehicle("VEH-1")
        wholesale_desk.mark_wholesale_sold("VEH-1", "Acme", 9000, "EMP-1")
        result = wholesale_desk_api.record_funds_collected_api(role, "EMP-1", "VEH-1", 9000)
        assert "error" in result

    @pytest.mark.parametrize("role", _MUTATE_ROLES)
    def test_record_funds_collected_api_allowed(self, role):
        ledger.reset()
        _add_vehicle("VEH-1")
        wholesale_desk.mark_wholesale_sold("VEH-1", "Acme", 9000, "EMP-1")
        result = wholesale_desk_api.record_funds_collected_api(role, "EMP-1", "VEH-1", 9000)
        assert "error" not in result

    @pytest.mark.parametrize("role", _VIEW_ROLES)
    def test_get_fund_collection_status_api_allowed_for_every_role(self, role):
        result = wholesale_desk_api.get_fund_collection_status_api(role)
        assert "awaiting_collection" in result

    def test_get_fund_collection_status_api_denies_an_unrecognized_role(self):
        result = wholesale_desk_api.get_fund_collection_status_api("NOT_A_REAL_ROLE")
        assert "error" in result

    @pytest.mark.parametrize("role", _VIEW_ROLES)
    def test_get_wholesale_desk_summary_api_allowed_for_every_role(self, role):
        result = wholesale_desk_api.get_wholesale_desk_summary_api(role)
        assert "open_offers" in result

    def test_get_wholesale_desk_summary_api_denies_an_unrecognized_role(self):
        result = wholesale_desk_api.get_wholesale_desk_summary_api("NOT_A_REAL_ROLE")
        assert "error" in result
