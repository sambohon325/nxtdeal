import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import VEHICLE, DEAL, AUCTION_TRANSACTION, CUSTOMER
from core import acquisitions
from core import acquisitions_api
from core.acquisitions import SOURCE_TYPES, DIRECT_PURCHASE_CHANNELS, ALL_STAGES, TERMINAL_STAGES
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    monkeypatch.setattr(acquisitions, "save_graph", lambda filepath: None)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _add_vehicle(vehicle_id="VEH-1", sold=False, **overrides):
    attrs = {"VIN": "1HGCM82633A004352", "Year": 2022, "Make": "Honda", "Model": "Accord", "Price": 25000}
    if sold:
        attrs["DateSold"] = "2026-01-01"
    attrs.update(overrides)
    ledger.add_entity(Entity(id=vehicle_id, entity_type=VEHICLE, attributes=attrs))
    return vehicle_id


def _add_deal(deal_id="DEAL-1"):
    ledger.add_entity(Entity(id=deal_id, entity_type=DEAL, attributes={}))
    return deal_id


def _add_auction_transaction(txn_id="AUCT-1"):
    ledger.add_entity(Entity(id=txn_id, entity_type=AUCTION_TRANSACTION, attributes={}))
    return txn_id


def _add_customer(customer_id="CUST-1"):
    ledger.add_entity(Entity(id=customer_id, entity_type=CUSTOMER, attributes={}))
    return customer_id


def _create_request(source_type="auction", **overrides):
    kwargs = {"requested_by": "EMP-1"}
    kwargs.update(overrides)
    return acquisitions.create_acquisition_request(source_type, **kwargs)


def _request_at_pending_approval(**overrides):
    """Full happy-path progression to the pending_approval stage, ready for
    the two-step approval chain -- bypasses the ACL layer entirely (module-
    level calls) so ACL tests only exercise the gate itself."""
    req = _create_request(make="Chevrolet", model="Silverado", year=2022, estimated_acv=20000, **overrides)
    acquisitions.record_price_risk(req["id"], "EMP-1", "low")
    acquisitions.record_recon_estimate(req["id"], "EMP-1", 500)
    acquisitions.record_market_review(req["id"], "EMP-1")
    acquisitions.submit_for_approval(req["id"], "EMP-1")
    return req["id"]


# ---------------------------------------------------------------------------
# Simulated signals
# ---------------------------------------------------------------------------


class TestGetMarketSignal:
    def test_shape_and_bounds(self):
        result = acquisitions.get_market_signal("Chevrolet", "Silverado", 2022)
        assert result["demand_level"] in ("Low", "Medium", "High")
        assert 18 <= result["avg_turn_rate_days"] <= 62
        assert 5 <= result["comparable_sales_count"] <= 44
        assert result["basis"] == "simulated_market_data"
        assert "SIMULATED" in result["disclaimer"]

    def test_deterministic_across_repeat_calls(self):
        r1 = acquisitions.get_market_signal("Chevrolet", "Silverado", 2022)
        r2 = acquisitions.get_market_signal("Chevrolet", "Silverado", 2022)
        assert r1 == r2

    def test_handles_missing_fields_gracefully(self):
        result = acquisitions.get_market_signal(None, None, None)
        assert result["demand_level"] in ("Low", "Medium", "High")


class TestGetBuyRecommendation:
    def test_no_acv_yields_no_recommended_bid(self):
        result = acquisitions.get_buy_recommendation("Chevrolet", "Silverado", 2022)
        assert result["recommended_bid"] is None

    def test_empty_string_acv_yields_no_recommended_bid(self):
        result = acquisitions.get_buy_recommendation("Chevrolet", "Silverado", 2022, estimated_acv="")
        assert result["recommended_bid"] is None

    def test_non_numeric_acv_yields_no_recommended_bid(self):
        result = acquisitions.get_buy_recommendation("Chevrolet", "Silverado", 2022, estimated_acv="not-a-number")
        assert result["recommended_bid"] is None

    def test_zero_acv_is_falsy_and_yields_no_recommended_bid(self):
        # get_buy_recommendation() gates on `if acv:` -- a successfully
        # parsed 0.0 is still falsy in Python, so an explicit "0" acv
        # collapses to no recommended_bid, same as a missing one.
        result = acquisitions.get_buy_recommendation("Chevrolet", "Silverado", 2022, estimated_acv=0)
        assert result["recommended_bid"] is None

    def test_real_acv_anchors_a_recommended_bid(self):
        result = acquisitions.get_buy_recommendation("Chevrolet", "Silverado", 2022, estimated_acv=20000)
        bid = result["recommended_bid"]
        assert bid is not None
        assert bid["anchor_acv"] == 20000.0

        adj = {"High": 1.05, "Medium": 1.0, "Low": 0.92}[result["demand_level"]]
        assert bid["low"] == round(20000.0 * adj * 0.94, 2)
        assert bid["high"] == round(20000.0 * adj * 1.02, 2)

    def test_string_acv_is_parsed(self):
        result = acquisitions.get_buy_recommendation("Chevrolet", "Silverado", 2022, estimated_acv="20000")
        assert result["recommended_bid"]["anchor_acv"] == 20000.0

    def test_includes_the_underlying_market_signal(self):
        result = acquisitions.get_buy_recommendation("Chevrolet", "Silverado", 2022, estimated_acv=20000)
        assert "avg_turn_rate_days" in result
        assert "comparable_sales_count" in result


class TestGetFactoryAllocations:
    def test_empty_when_no_vehicles(self):
        result = acquisitions.get_factory_allocations()
        assert result["allocations"] == []
        assert "SIMULATED" in result["disclaimer"]

    def test_one_entry_per_distinct_make(self):
        _add_vehicle("VEH-1", Make="Honda", Model="Accord")
        _add_vehicle("VEH-2", Make="Ford", Model="F-150")
        result = acquisitions.get_factory_allocations()
        makes = {a["make"] for a in result["allocations"]}
        assert makes == {"Honda", "Ford"}

    def test_vehicles_missing_make_are_skipped(self):
        _add_vehicle("VEH-1", Make=None)
        result = acquisitions.get_factory_allocations()
        assert result["allocations"] == []

    def test_sold_vehicles_still_count(self):
        # get_factory_allocations() has no unsold-only filtering -- it
        # scans every Vehicle entity regardless of DateSold.
        _add_vehicle("VEH-1", Make="Honda", sold=True)
        result = acquisitions.get_factory_allocations()
        assert result["allocations"][0]["make"] == "Honda"

    def test_top_three_models_sorted(self):
        _add_vehicle("VEH-1", Make="Honda", Model="Pilot")
        _add_vehicle("VEH-2", Make="Honda", Model="Accord")
        _add_vehicle("VEH-3", Make="Honda", Model="Civic")
        _add_vehicle("VEH-4", Make="Honda", Model="CR-V")
        result = acquisitions.get_factory_allocations()
        entry = result["allocations"][0]
        assert entry["models"] == sorted(entry["models"])
        assert len(entry["models"]) == 3

    def test_various_fallback_when_no_real_models(self):
        _add_vehicle("VEH-1", Make="Honda", Model=None)
        result = acquisitions.get_factory_allocations()
        assert result["allocations"][0]["models"] == ["Various"]

    def test_qty_and_month_offset_within_bounds(self):
        _add_vehicle("VEH-1", Make="Honda")
        result = acquisitions.get_factory_allocations()
        entry = result["allocations"][0]
        assert 3 <= entry["allocated_units"] <= 14
        assert 1 <= entry["allotment_month_offset"] <= 3
        assert entry["basis"] == "simulated_market_data"

    def test_deterministic_across_repeat_calls(self):
        _add_vehicle("VEH-1", Make="Honda")
        r1 = acquisitions.get_factory_allocations()
        r2 = acquisitions.get_factory_allocations()
        assert r1 == r2


# ---------------------------------------------------------------------------
# create_acquisition_request
# ---------------------------------------------------------------------------


class TestCreateAcquisitionRequest:
    def test_invalid_source_type_rejected(self):
        result = acquisitions.create_acquisition_request("bogus", "EMP-1")
        assert "error" in result

    def test_direct_purchase_requires_valid_channel(self):
        result = acquisitions.create_acquisition_request("direct_purchase", "EMP-1")
        assert "error" in result

    def test_direct_purchase_with_valid_channel_succeeds(self):
        result = acquisitions.create_acquisition_request(
            "direct_purchase", "EMP-1", direct_purchase_channel="walk_in"
        )
        assert result["direct_purchase_channel"] == "walk_in"
        assert "error" not in result

    def test_unknown_linked_deal_rejected(self):
        result = acquisitions.create_acquisition_request("auction", "EMP-1", linked_deal_id="DEAL-NOPE")
        assert "error" in result

    @pytest.mark.parametrize("entity_type", [CUSTOMER, VEHICLE, AUCTION_TRANSACTION])
    def test_linked_deal_rejects_other_entity_types_before_writing(self, monkeypatch, entity_type):
        ledger.add_entity(Entity(id="NOT-A-DEAL", entity_type=entity_type, attributes={}))
        def unexpected(*args, **kwargs):
            pytest.fail("Invalid deal link must not allocate IDs or save")
        monkeypatch.setattr(acquisitions.id_generator, "generate", unexpected)
        monkeypatch.setattr(acquisitions, "save_graph", unexpected)
        result = acquisitions.create_acquisition_request("trade", "EMP-1", linked_deal_id="NOT-A-DEAL")
        assert result == {"error": "Deal 'NOT-A-DEAL' not found"}

    def test_real_linked_deal_accepted(self):
        _add_deal("DEAL-1")
        result = acquisitions.create_acquisition_request("auction", "EMP-1", linked_deal_id="DEAL-1")
        assert result["linked_deal_id"] == "DEAL-1"

    def test_unknown_linked_auction_transaction_rejected(self):
        result = acquisitions.create_acquisition_request(
            "auction", "EMP-1", linked_auction_transaction_id="AUCT-NOPE"
        )
        assert "error" in result

    def test_linked_auction_transaction_checks_entity_type(self):
        # Linked records must have the expected entity type.
        _add_customer("NOT-AN-AUCTION")
        result = acquisitions.create_acquisition_request(
            "auction", "EMP-1", linked_auction_transaction_id="NOT-AN-AUCTION"
        )
        assert "error" in result

    def test_real_linked_auction_transaction_accepted(self):
        _add_auction_transaction("AUCT-1")
        result = acquisitions.create_acquisition_request(
            "auction", "EMP-1", linked_auction_transaction_id="AUCT-1"
        )
        assert result["linked_auction_transaction_id"] == "AUCT-1"

    def test_default_shape_on_success(self):
        result = acquisitions.create_acquisition_request(
            "trade", "EMP-1", year=2021, make="Toyota", model="Camry", trim="LE",
            mileage=40000, vin="1ABCD1234", estimated_acv=15000, notes="From a trade appraisal",
        )
        assert result["id"].startswith("ACQ-")
        assert result["source_type"] == "trade"
        assert result["stage"] == "evaluate"
        assert result["requested_by"] == "EMP-1"
        assert result["created_by"] == "EMP-1"
        assert result["notes"] == "From a trade appraisal"
        assert result["linked_vehicle_id"] is None
        assert result["price_risk_level"] is None
        assert result["inventory_manager_approval"] is None
        assert result["gm_approval"] is None

    def test_unique_ids_across_creates(self):
        r1 = _create_request()
        r2 = _create_request()
        assert r1["id"] != r2["id"]

    def test_creates_a_real_entity_on_the_ledger(self):
        result = _create_request()
        assert ledger.get_entity(result["id"]) is not None


# ---------------------------------------------------------------------------
# create_acquisition_request -- NXTDeal VIN Intelligence, Phase 3
# creation-time auto-decode (real, best-effort, non-blocking; offline-only
# in this sandbox since there's no outbound network access for the live
# NHTSA half)
# ---------------------------------------------------------------------------


class TestCreateAcquisitionRequestVinAutoDecode:
    _REAL_VIN = "1HGCM82633A004352"  # decodes offline to year=2003, make=Honda

    def test_vin_with_all_blank_fields_backfills_year_and_make(self, monkeypatch):
        # Exercise offline backfill deterministically, regardless of network access.
        from core import vin_decoder
        decode = vin_decoder.decode_vin
        monkeypatch.setattr(vin_decoder, "decode_vin", lambda vin, **kwargs: decode(vin, attempt_live=False))
        result = acquisitions.create_acquisition_request("auction", "EMP-1", vin=self._REAL_VIN)
        assert result["vin_decode"] is not None
        assert result["year"] == "2003"
        assert result["make"] == "Honda"
        # Model/Trim genuinely require the live NHTSA half, unavailable in
        # this sandbox -- correctly stay unset, not guessed at.
        assert result["model"] is None
        assert result["trim"] is None

    def test_vin_with_all_fields_already_supplied_skips_auto_decode(self):
        result = acquisitions.create_acquisition_request(
            "auction", "EMP-1", vin=self._REAL_VIN, year=2021, make="Toyota", model="Camry",
        )
        # year/make/model already supplied -- the `not all([...])` guard is
        # False, so no decode is attempted at all and vin_decode stays None.
        assert result["vin_decode"] is None
        assert result["year"] == 2021
        assert result["make"] == "Toyota"
        assert result["model"] == "Camry"

    def test_vin_with_partial_fields_only_backfills_the_blanks(self):
        result = acquisitions.create_acquisition_request(
            "auction", "EMP-1", vin=self._REAL_VIN, make="Some Other Make",
        )
        # make was explicitly supplied -- never overwritten, even though the
        # real decode would resolve a different one (Honda).
        assert result["make"] == "Some Other Make"
        assert result["year"] == "2003"
        assert result["vin_decode"] is not None

    def test_no_vin_supplied_never_attempts_a_decode(self):
        result = acquisitions.create_acquisition_request("auction", "EMP-1")
        assert result["vin_decode"] is None

    def test_malformed_vin_does_not_block_request_creation(self):
        result = acquisitions.create_acquisition_request("auction", "EMP-1", vin="NOTAREALVIN")
        assert "error" not in result
        assert result["id"].startswith("ACQ-")
        # decode_vin() itself never raises on a malformed VIN (it reports
        # valid_format=False honestly), so vin_decode is still populated --
        # just with no resolved year/make/model/trim to backfill.
        assert result["year"] is None
        assert result["make"] is None


class TestGetAcquisitionRequest:
    def test_unknown_id_rejected(self):
        result = acquisitions.get_acquisition_request("ACQ-NOPE")
        assert "error" in result

    def test_returns_flat_serialized_shape(self):
        created = _create_request()
        result = acquisitions.get_acquisition_request(created["id"])
        assert result == created


class TestListAcquisitionRequests:
    def test_empty_state(self):
        result = acquisitions.list_acquisition_requests()
        assert result == {"count": 0, "requests": []}

    def test_no_capping_count_matches_full_list(self):
        # list_acquisition_requests() has no `limit` param at all -- count
        # always equals the true, uncapped number of matching requests.
        for _ in range(5):
            _create_request()
        result = acquisitions.list_acquisition_requests()
        assert result["count"] == 5
        assert len(result["requests"]) == 5

    def test_filters_by_source_type(self):
        _create_request(source_type="auction")
        _create_request(source_type="trade")
        result = acquisitions.list_acquisition_requests(source_type="trade")
        assert result["count"] == 1
        assert result["requests"][0]["source_type"] == "trade"

    def test_filters_by_stage(self):
        r1 = _create_request()
        acquisitions.record_price_risk(r1["id"], "EMP-1", "low")
        _create_request()
        result = acquisitions.list_acquisition_requests(stage="price_risk")
        assert result["count"] == 1
        assert result["requests"][0]["id"] == r1["id"]

    def test_sorted_by_created_at_descending(self):
        r1 = _create_request()
        r2 = _create_request()
        result = acquisitions.list_acquisition_requests()
        ids = [r["id"] for r in result["requests"]]
        assert ids[0] == r2["id"]
        assert ids[1] == r1["id"]


# ---------------------------------------------------------------------------
# Evaluation stages
# ---------------------------------------------------------------------------


class TestRecordPriceRisk:
    def test_unknown_id_rejected(self):
        result = acquisitions.record_price_risk("ACQ-NOPE", "EMP-1", "low")
        assert "error" in result

    def test_invalid_risk_level_rejected(self):
        req = _create_request()
        result = acquisitions.record_price_risk(req["id"], "EMP-1", "bogus")
        assert "error" in result

    def test_valid_risk_level_advances_stage(self):
        req = _create_request()
        result = acquisitions.record_price_risk(req["id"], "EMP-1", "medium", notes="Slight overpay risk")
        assert result["price_risk_level"] == "medium"
        assert result["price_risk_notes"] == "Slight overpay risk"
        assert result["stage"] == "price_risk"

    def test_rejected_once_finalized(self):
        req = _create_request()
        acquisitions.reject_request(req["id"], "EMP-1", "Too far over ACV")
        result = acquisitions.record_price_risk(req["id"], "EMP-1", "low")
        assert "error" in result


class TestRecordReconEstimate:
    def test_unknown_id_rejected(self):
        result = acquisitions.record_recon_estimate("ACQ-NOPE", "EMP-1", 500)
        assert "error" in result

    def test_non_numeric_estimate_rejected(self):
        req = _create_request()
        result = acquisitions.record_recon_estimate(req["id"], "EMP-1", "not-a-number")
        assert "error" in result

    def test_valid_estimate_advances_stage(self):
        req = _create_request()
        result = acquisitions.record_recon_estimate(req["id"], "EMP-1", 750, notes="New tires needed")
        assert result["recon_estimate"] == 750.0
        assert result["recon_notes"] == "New tires needed"
        assert result["stage"] == "estimate_recon"

    def test_rejected_once_finalized(self):
        req = _create_request()
        acquisitions.reject_request(req["id"], "EMP-1", "Passed on this unit")
        result = acquisitions.record_recon_estimate(req["id"], "EMP-1", 500)
        assert "error" in result


class TestRecordMarketReview:
    def test_unknown_id_rejected(self):
        result = acquisitions.record_market_review("ACQ-NOPE", "EMP-1")
        assert "error" in result

    def test_computes_and_stores_the_real_recommendation(self):
        req = _create_request(make="Chevrolet", model="Silverado", year=2022, estimated_acv=20000)
        result = acquisitions.record_market_review(req["id"], "EMP-1", notes="Looks solid")
        assert result["stage"] == "review_market"
        review = result["market_review"]
        assert review["notes"] == "Looks solid"
        assert review["reviewed_by"] == "EMP-1"
        assert review["recommendation"]["recommended_bid"]["anchor_acv"] == 20000.0

    def test_rejected_once_finalized(self):
        req = _create_request()
        acquisitions.reject_request(req["id"], "EMP-1", "Not needed")
        result = acquisitions.record_market_review(req["id"], "EMP-1")
        assert "error" in result


class TestSubmitForApproval:
    def test_unknown_id_rejected(self):
        result = acquisitions.submit_for_approval("ACQ-NOPE", "EMP-1")
        assert "error" in result

    def test_requires_a_market_review_first(self):
        req = _create_request()
        result = acquisitions.submit_for_approval(req["id"], "EMP-1")
        assert "error" in result

    def test_succeeds_once_market_review_exists(self):
        req = _create_request()
        acquisitions.record_market_review(req["id"], "EMP-1")
        result = acquisitions.submit_for_approval(req["id"], "EMP-1")
        assert result["stage"] == "pending_approval"

    def test_rejected_once_finalized(self):
        req = _create_request()
        acquisitions.reject_request(req["id"], "EMP-1", "No thanks")
        result = acquisitions.submit_for_approval(req["id"], "EMP-1")
        assert "error" in result


# ---------------------------------------------------------------------------
# Two-step approval chain
# ---------------------------------------------------------------------------


class TestApproveByInventoryManager:
    def test_unknown_id_rejected(self):
        result = acquisitions.approve_by_inventory_manager("ACQ-NOPE", "EMP-1")
        assert "error" in result

    def test_requires_pending_approval_stage(self):
        req = _create_request()
        result = acquisitions.approve_by_inventory_manager(req["id"], "EMP-1")
        assert "error" in result

    def test_succeeds_at_pending_approval(self):
        request_id = _request_at_pending_approval()
        result = acquisitions.approve_by_inventory_manager(request_id, "EMP-2", notes="Looks good")
        assert result["inventory_manager_approval"]["approved_by"] == "EMP-2"
        assert result["inventory_manager_approval"]["notes"] == "Looks good"
        # Approving as Inventory Manager alone does NOT advance the stage.
        assert result["stage"] == "pending_approval"


class TestApproveByGm:
    def test_unknown_id_rejected(self):
        result = acquisitions.approve_by_gm("ACQ-NOPE", "EMP-1")
        assert "error" in result

    def test_requires_pending_approval_stage(self):
        req = _create_request()
        result = acquisitions.approve_by_gm(req["id"], "EMP-1")
        assert "error" in result

    def test_requires_inventory_manager_approval_first(self):
        request_id = _request_at_pending_approval()
        result = acquisitions.approve_by_gm(request_id, "EMP-1")
        assert "error" in result

    def test_succeeds_after_inventory_manager_approval(self):
        request_id = _request_at_pending_approval()
        acquisitions.approve_by_inventory_manager(request_id, "EMP-2")
        result = acquisitions.approve_by_gm(request_id, "EMP-3", notes="Final sign-off")
        assert result["gm_approval"]["approved_by"] == "EMP-3"
        assert result["stage"] == "approved"


class TestRejectRequest:
    def test_unknown_id_rejected(self):
        result = acquisitions.reject_request("ACQ-NOPE", "EMP-1", "No")
        assert "error" in result

    def test_requires_a_non_empty_reason(self):
        req = _create_request()
        result = acquisitions.reject_request(req["id"], "EMP-1", "")
        assert "error" in result

    def test_whitespace_only_reason_rejected(self):
        req = _create_request()
        result = acquisitions.reject_request(req["id"], "EMP-1", "   ")
        assert "error" in result

    def test_can_reject_straight_from_evaluate_stage(self):
        req = _create_request()
        result = acquisitions.reject_request(req["id"], "EMP-1", "Priced too high")
        assert result["stage"] == "rejected"
        assert result["rejection_reason"] == "Priced too high"
        assert result["rejected_by"] == "EMP-1"

    def test_can_reject_from_pending_approval(self):
        request_id = _request_at_pending_approval()
        result = acquisitions.reject_request(request_id, "EMP-1", "GM declined")
        assert result["stage"] == "rejected"

    def test_rejected_once_already_terminal(self):
        req = _create_request()
        acquisitions.reject_request(req["id"], "EMP-1", "First reason")
        result = acquisitions.reject_request(req["id"], "EMP-1", "Second reason")
        assert "error" in result


class TestMarkPurchased:
    def test_unknown_id_rejected(self):
        result = acquisitions.mark_purchased("ACQ-NOPE", "EMP-1")
        assert "error" in result

    def test_requires_fully_approved_stage(self):
        request_id = _request_at_pending_approval()
        result = acquisitions.mark_purchased(request_id, "EMP-1")
        assert "error" in result

    def test_succeeds_once_fully_approved(self):
        request_id = _request_at_pending_approval()
        acquisitions.approve_by_inventory_manager(request_id, "EMP-2")
        acquisitions.approve_by_gm(request_id, "EMP-3")
        result = acquisitions.mark_purchased(request_id, "EMP-1")
        assert result["stage"] == "purchased"
        assert result["purchased_at"] is not None
        assert result["linked_vehicle_id"] is None

    def test_unknown_vehicle_id_rejected(self):
        request_id = _request_at_pending_approval()
        acquisitions.approve_by_inventory_manager(request_id, "EMP-2")
        acquisitions.approve_by_gm(request_id, "EMP-3")
        result = acquisitions.mark_purchased(request_id, "EMP-1", vehicle_id="VEH-NOPE")
        assert "error" in result

    def test_links_a_real_vehicle_when_supplied(self):
        _add_vehicle("VEH-1")
        request_id = _request_at_pending_approval()
        acquisitions.approve_by_inventory_manager(request_id, "EMP-2")
        acquisitions.approve_by_gm(request_id, "EMP-3")
        result = acquisitions.mark_purchased(request_id, "EMP-1", vehicle_id="VEH-1")
        assert result["linked_vehicle_id"] == "VEH-1"


class TestGetAcquisitionsSummary:
    def test_empty_state(self):
        result = acquisitions.get_acquisitions_summary()
        assert result["total_requests"] == 0
        assert result["by_stage"] == {}
        assert result["by_source_type"] == {}
        assert result["pending_approval_count"] == 0
        assert result["awaiting_gm_signoff_count"] == 0

    def test_counts_by_stage_and_source(self):
        _create_request(source_type="auction")
        _create_request(source_type="trade")
        result = acquisitions.get_acquisitions_summary()
        assert result["total_requests"] == 2
        assert result["by_stage"]["evaluate"] == 2
        assert result["by_source_type"] == {"auction": 1, "trade": 1}

    def test_pending_approval_and_awaiting_gm_counts(self):
        request_id = _request_at_pending_approval()
        result = acquisitions.get_acquisitions_summary()
        assert result["pending_approval_count"] == 1
        assert result["awaiting_gm_signoff_count"] == 0

        acquisitions.approve_by_inventory_manager(request_id, "EMP-2")
        result = acquisitions.get_acquisitions_summary()
        assert result["pending_approval_count"] == 1
        assert result["awaiting_gm_signoff_count"] == 1

        acquisitions.approve_by_gm(request_id, "EMP-3")
        result = acquisitions.get_acquisitions_summary()
        assert result["pending_approval_count"] == 0
        assert result["awaiting_gm_signoff_count"] == 0


# ---------------------------------------------------------------------------
# decode_and_prefill_acquisition_vin -- NXTDeal VIN Intelligence, Phase 3
# manual re-decode action (offline-only in this sandbox)
# ---------------------------------------------------------------------------


class TestDecodeAndPrefillAcquisitionVin:
    _REAL_VIN = "1HGCM82633A004352"  # decodes offline to year=2003, make=Honda

    def test_unknown_request_rejected(self):
        result = acquisitions.decode_and_prefill_acquisition_vin("ACQ-NOPE", "EMP-1")
        assert "error" in result

    def test_finalized_request_rejected(self):
        req = _create_request(vin=self._REAL_VIN)
        acquisitions.reject_request(req["id"], "EMP-1", "No thanks")
        result = acquisitions.decode_and_prefill_acquisition_vin(req["id"], "EMP-1")
        assert "error" in result
        assert "already" in result["error"]

    def test_no_vin_on_file_rejected(self):
        req = _create_request()
        result = acquisitions.decode_and_prefill_acquisition_vin(req["id"], "EMP-1")
        assert "error" in result
        assert "no VIN on file" in result["error"]

    def test_successful_decode_backfills_blank_fields(self, monkeypatch):
        # Exercise offline backfill deterministically, regardless of network access.
        from core import vin_decoder
        decode = vin_decoder.decode_vin
        monkeypatch.setattr(vin_decoder, "decode_vin", lambda vin, **kwargs: decode(vin, attempt_live=False))
        # Created with no VIN so creation-time auto-decode never fires; the
        # VIN is attached afterward, directly on the entity, so this test
        # genuinely isolates decode_and_prefill_acquisition_vin's own
        # backfill logic rather than re-testing create's.
        req = _create_request()
        entity = ledger.get_entity(req["id"])
        entity.attributes["vin"] = self._REAL_VIN
        result = acquisitions.decode_and_prefill_acquisition_vin(req["id"], "EMP-1")
        assert result["year"] == "2003"
        assert result["make"] == "Honda"
        assert result["vin_decode"] is not None
        assert "year" in result["vin_decode_backfilled_fields"]
        assert "make" in result["vin_decode_backfilled_fields"]

    def test_never_overwrites_already_set_fields(self):
        req = _create_request(vin=self._REAL_VIN, year=2021, make="Toyota", model="Camry", trim="LE")
        result = acquisitions.decode_and_prefill_acquisition_vin(req["id"], "EMP-1")
        assert result["year"] == 2021
        assert result["make"] == "Toyota"
        assert result["model"] == "Camry"
        assert result["trim"] == "LE"
        assert result["vin_decode_backfilled_fields"] == []
        # A real decode still runs and gets stored, it just backfills nothing.
        assert result["vin_decode"] is not None

    def test_can_be_called_again_and_updates_the_stored_decode(self):
        req = _create_request(vin=self._REAL_VIN)
        first = acquisitions.decode_and_prefill_acquisition_vin(req["id"], "EMP-1")
        assert first["vin_decode"]["vin"] == self._REAL_VIN
        first_updated_at = first["updated_at"]
        second = acquisitions.decode_and_prefill_acquisition_vin(req["id"], "EMP-2")
        # The manual action is explicitly re-runnable (unlike the vehicle
        # lifecycle's auto-decode-once-on-Received hook) -- every call
        # re-decodes and re-stores, since this is the "retry later with live
        # access" action Sam's own spec described. There's no per-decode
        # actor stamp on the AcquisitionRequest's own vin_decode (unlike
        # Vehicle's apply_decode_to_vehicle, which does track decoded_by) --
        # only the request's own updated_at timestamp reflects each re-run.
        assert second["vin_decode"] is not None
        assert second["updated_at"] is not None
        assert second["updated_at"] >= first_updated_at


# ---------------------------------------------------------------------------
# API layer -- role gating
# ---------------------------------------------------------------------------


_VIEW_ALLOWED = [ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE]
_VIEW_DENIED = ["BOGUS_ROLE"]

_EVALUATE_ALLOWED = [ADMIN, OPERATIONS, FINANCE]
_EVALUATE_DENIED = [SALES, MARKETING, SERVICE, "BOGUS_ROLE"]

_IM_ALLOWED = [ADMIN, OPERATIONS]
_IM_DENIED = [SALES, MARKETING, SERVICE, FINANCE, "BOGUS_ROLE"]

_GM_ALLOWED = [ADMIN]
_GM_DENIED = [OPERATIONS, SALES, MARKETING, SERVICE, FINANCE, "BOGUS_ROLE"]


class TestAcl:
    def test_get_catalog_has_no_role_gate(self):
        result = acquisitions_api.get_catalog_api()
        assert result["source_types"] == list(SOURCE_TYPES)
        assert result["stages"] == list(ALL_STAGES)

    @pytest.mark.parametrize("role", _EVALUATE_DENIED)
    def test_create_acquisition_request_denied(self, role):
        result = acquisitions_api.create_acquisition_request_api(role, "EMP-1", "auction")
        assert "error" in result

    @pytest.mark.parametrize("role", _EVALUATE_ALLOWED)
    def test_create_acquisition_request_allowed(self, role):
        ledger.reset()
        result = acquisitions_api.create_acquisition_request_api(role, "EMP-1", "auction")
        assert result["id"].startswith("ACQ-")

    @pytest.mark.parametrize("role", _VIEW_DENIED)
    def test_get_acquisition_request_denied(self, role):
        req = _create_request()
        result = acquisitions_api.get_acquisition_request_api(role, req["id"])
        assert "error" in result

    @pytest.mark.parametrize("role", _VIEW_ALLOWED)
    def test_get_acquisition_request_allowed(self, role):
        ledger.reset()
        req = _create_request()
        result = acquisitions_api.get_acquisition_request_api(role, req["id"])
        assert result["id"] == req["id"]

    @pytest.mark.parametrize("role", _VIEW_DENIED)
    def test_list_acquisition_requests_denied(self, role):
        result = acquisitions_api.list_acquisition_requests_api(role)
        assert "error" in result

    @pytest.mark.parametrize("role", _VIEW_ALLOWED)
    def test_list_acquisition_requests_allowed(self, role):
        result = acquisitions_api.list_acquisition_requests_api(role)
        assert result == {"count": 0, "requests": []}

    @pytest.mark.parametrize("role", _EVALUATE_DENIED)
    def test_record_price_risk_denied(self, role):
        req = _create_request()
        result = acquisitions_api.record_price_risk_api(role, "EMP-1", req["id"], "low")
        assert "error" in result

    @pytest.mark.parametrize("role", _EVALUATE_ALLOWED)
    def test_record_price_risk_allowed(self, role):
        ledger.reset()
        req = _create_request()
        result = acquisitions_api.record_price_risk_api(role, "EMP-1", req["id"], "low")
        assert result["price_risk_level"] == "low"

    @pytest.mark.parametrize("role", _EVALUATE_DENIED)
    def test_record_recon_estimate_denied(self, role):
        req = _create_request()
        result = acquisitions_api.record_recon_estimate_api(role, "EMP-1", req["id"], 500)
        assert "error" in result

    @pytest.mark.parametrize("role", _EVALUATE_ALLOWED)
    def test_record_recon_estimate_allowed(self, role):
        ledger.reset()
        req = _create_request()
        result = acquisitions_api.record_recon_estimate_api(role, "EMP-1", req["id"], 500)
        assert result["recon_estimate"] == 500.0

    @pytest.mark.parametrize("role", _EVALUATE_DENIED)
    def test_record_market_review_denied(self, role):
        req = _create_request()
        result = acquisitions_api.record_market_review_api(role, "EMP-1", req["id"])
        assert "error" in result

    @pytest.mark.parametrize("role", _EVALUATE_ALLOWED)
    def test_record_market_review_allowed(self, role):
        ledger.reset()
        req = _create_request()
        result = acquisitions_api.record_market_review_api(role, "EMP-1", req["id"])
        assert result["stage"] == "review_market"

    @pytest.mark.parametrize("role", _EVALUATE_DENIED)
    def test_submit_for_approval_denied(self, role):
        req = _create_request()
        acquisitions.record_market_review(req["id"], "EMP-1")
        result = acquisitions_api.submit_for_approval_api(role, "EMP-1", req["id"])
        assert "error" in result

    @pytest.mark.parametrize("role", _EVALUATE_ALLOWED)
    def test_submit_for_approval_allowed(self, role):
        ledger.reset()
        req = _create_request()
        acquisitions.record_market_review(req["id"], "EMP-1")
        result = acquisitions_api.submit_for_approval_api(role, "EMP-1", req["id"])
        assert result["stage"] == "pending_approval"

    @pytest.mark.parametrize("role", _IM_DENIED)
    def test_approve_by_inventory_manager_denied(self, role):
        request_id = _request_at_pending_approval()
        result = acquisitions_api.approve_by_inventory_manager_api(role, "EMP-2", request_id)
        assert "error" in result

    @pytest.mark.parametrize("role", _IM_ALLOWED)
    def test_approve_by_inventory_manager_allowed(self, role):
        ledger.reset()
        request_id = _request_at_pending_approval()
        result = acquisitions_api.approve_by_inventory_manager_api(role, "EMP-2", request_id)
        assert result["inventory_manager_approval"]["approved_by"] == "EMP-2"

    @pytest.mark.parametrize("role", _GM_DENIED)
    def test_approve_by_gm_denied(self, role):
        request_id = _request_at_pending_approval()
        acquisitions.approve_by_inventory_manager(request_id, "EMP-2")
        result = acquisitions_api.approve_by_gm_api(role, "EMP-3", request_id)
        assert "error" in result

    @pytest.mark.parametrize("role", _GM_ALLOWED)
    def test_approve_by_gm_allowed(self, role):
        ledger.reset()
        request_id = _request_at_pending_approval()
        acquisitions.approve_by_inventory_manager(request_id, "EMP-2")
        result = acquisitions_api.approve_by_gm_api(role, "EMP-3", request_id)
        assert result["stage"] == "approved"

    @pytest.mark.parametrize("role", _IM_DENIED)
    def test_reject_request_denied(self, role):
        req = _create_request()
        result = acquisitions_api.reject_request_api(role, "EMP-1", req["id"], "No")
        assert "error" in result

    @pytest.mark.parametrize("role", _IM_ALLOWED)
    def test_reject_request_allowed(self, role):
        ledger.reset()
        req = _create_request()
        result = acquisitions_api.reject_request_api(role, "EMP-1", req["id"], "No")
        assert result["stage"] == "rejected"

    @pytest.mark.parametrize("role", _EVALUATE_DENIED)
    def test_mark_purchased_denied(self, role):
        request_id = _request_at_pending_approval()
        acquisitions.approve_by_inventory_manager(request_id, "EMP-2")
        acquisitions.approve_by_gm(request_id, "EMP-3")
        result = acquisitions_api.mark_purchased_api(role, "EMP-1", request_id)
        assert "error" in result

    @pytest.mark.parametrize("role", _EVALUATE_ALLOWED)
    def test_mark_purchased_allowed(self, role):
        ledger.reset()
        request_id = _request_at_pending_approval()
        acquisitions.approve_by_inventory_manager(request_id, "EMP-2")
        acquisitions.approve_by_gm(request_id, "EMP-3")
        result = acquisitions_api.mark_purchased_api(role, "EMP-1", request_id)
        assert result["stage"] == "purchased"

    @pytest.mark.parametrize("role", _VIEW_DENIED)
    def test_get_acquisitions_summary_denied(self, role):
        result = acquisitions_api.get_acquisitions_summary_api(role)
        assert "error" in result

    @pytest.mark.parametrize("role", _VIEW_ALLOWED)
    def test_get_acquisitions_summary_allowed(self, role):
        result = acquisitions_api.get_acquisitions_summary_api(role)
        assert result["total_requests"] == 0

    @pytest.mark.parametrize("role", _VIEW_DENIED)
    def test_get_buy_recommendation_denied(self, role):
        result = acquisitions_api.get_buy_recommendation_api(role, "Chevrolet", "Silverado", 2022)
        assert "error" in result

    @pytest.mark.parametrize("role", _VIEW_ALLOWED)
    def test_get_buy_recommendation_allowed(self, role):
        result = acquisitions_api.get_buy_recommendation_api(role, "Chevrolet", "Silverado", 2022)
        assert "demand_level" in result

    @pytest.mark.parametrize("role", _VIEW_DENIED)
    def test_get_factory_allocations_denied(self, role):
        result = acquisitions_api.get_factory_allocations_api(role)
        assert "error" in result

    @pytest.mark.parametrize("role", _VIEW_ALLOWED)
    def test_get_factory_allocations_allowed(self, role):
        result = acquisitions_api.get_factory_allocations_api(role)
        assert result["allocations"] == []

    @pytest.mark.parametrize("role", _EVALUATE_DENIED)
    def test_decode_and_prefill_acquisition_vin_denied(self, role):
        req = _create_request(vin="1HGCM82633A004352")
        result = acquisitions_api.decode_and_prefill_acquisition_vin_api(role, "EMP-1", req["id"])
        assert "error" in result

    @pytest.mark.parametrize("role", _EVALUATE_ALLOWED)
    def test_decode_and_prefill_acquisition_vin_allowed(self, role):
        ledger.reset()
        req = _create_request(vin="1HGCM82633A004352")
        result = acquisitions_api.decode_and_prefill_acquisition_vin_api(role, "EMP-1", req["id"])
        assert result["vin_decode"] is not None
        assert "error" not in result


# ---------------------------------------------------------------------------
# Pillar 4 slice 4d: the acquisition lifecycle feeds the FLEET's Inventory agent.
# ---------------------------------------------------------------------------

class TestInventoryAgentWorkflowFeed:
    def _run_buy_flow(self, actor="EMP-1"):
        req = acquisitions_api.create_acquisition_request_api(
            FINANCE, actor, "auction", make="Chevrolet", model="Silverado", year=2022, estimated_acv=20000
        )
        assert "error" not in req
        req_id = req["id"]
        assert "error" not in acquisitions_api.record_price_risk_api(FINANCE, actor, req_id, "low")
        assert "error" not in acquisitions_api.record_recon_estimate_api(FINANCE, actor, req_id, 500)
        assert "error" not in acquisitions_api.record_market_review_api(FINANCE, actor, req_id)
        assert "error" not in acquisitions_api.submit_for_approval_api(FINANCE, actor, req_id)
        return req_id

    def test_two_buys_make_inventory_agent_recognize_the_workflow(self):
        """Two acquisition requests worked by the same buyer (create -> price/risk ->
        recon -> market review -> submit) make the Inventory team agent recognize the
        repeated multi-step buying workflow -- real recognition fed through the API."""

        from core.bot_fleet import get_team_workflows

        self._run_buy_flow()
        self._run_buy_flow()

        wf = get_team_workflows("inventory")

        assert wf["step_count"] == 10  # 2 requests x 5 recorded steps
        recognized = {tuple(w["steps"]): w["occurrences"] for w in wf["recognized_workflows"]}
        # The 5-step buyer flow is mined as maximal 4-grams (MAX_SEQUENCE_LEN=4); its
        # leading window recurs across both requests.
        head = ("create_request", "record_price_risk", "record_recon_estimate", "record_market_review")
        assert head in recognized
        assert recognized[head] >= 2

    def test_buy_flow_does_not_feed_other_teams(self):
        """Honest team scoping: acquisition steps feed only the Inventory agent."""

        from core.bot_fleet import get_team_workflows

        self._run_buy_flow()

        assert get_team_workflows("inventory")["step_count"] == 5
        assert get_team_workflows("sales")["step_count"] == 0
        assert get_team_workflows("service")["step_count"] == 0


class TestIntakeNumericValidation:
    @pytest.mark.parametrize("field,value", [
        ("year", "24"), ("year", "2024x"), ("year", True),
        ("mileage", -1), ("mileage", "10.5"), ("mileage", "1,000"),
        ("estimated_acv", -1), ("estimated_acv", float("nan")),
        ("estimated_acv", float("inf")), ("estimated_acv", "12abc"),
        ("estimated_acv", 1.234), ("estimated_acv", True),
    ])
    def test_invalid_input_has_no_write_or_id_allocation(self, monkeypatch, field, value):
        def unexpected(*args, **kwargs):
            pytest.fail("Invalid intake must not allocate IDs or persist")
        monkeypatch.setattr(acquisitions.id_generator, "generate", unexpected)
        monkeypatch.setattr(acquisitions, "save_graph", unexpected)
        result = _create_request(**{field: value})
        assert "error" in result

    @pytest.mark.parametrize("amount", [None, "", 0, "0.00", 123.45])
    def test_optional_and_zero_facts_remain_valid(self, amount):
        result = _create_request(year="2024", mileage="0", estimated_acv=amount)
        assert result["stage"] == "evaluate"
        assert result["estimated_acv"] == (None if amount in (None, "") else float(amount))
        assert result["linked_vehicle_id"] is None
