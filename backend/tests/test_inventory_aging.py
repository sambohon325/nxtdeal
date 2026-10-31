import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import VEHICLE
from core import inventory_aging
from core import inventory_aging_api
from core import operations_tasks
from core import campaigns
from core.permissions import ADMIN, OPERATIONS, SALES, SERVICE, MARKETING, FINANCE


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    # inventory_aging.py owns its own save_graph() calls for reduce_price()/
    # set_price(); the review/tie-in actions delegate into
    # core/operations_tasks.py's create_task() and core/campaigns.py's
    # create_campaign(), each of which has its own top-level save_graph
    # import and its own save call -- all three need patching.
    monkeypatch.setattr(inventory_aging, "save_graph", lambda filepath: None)
    monkeypatch.setattr(operations_tasks, "save_graph", lambda filepath: None)
    monkeypatch.setattr(campaigns, "save_graph", lambda filepath: None)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _add_vehicle(vehicle_id="VEH-1", **overrides):
    attrs = {
        "VIN": "1HGCM82633A004352",
        "StockNumber": "S1001",
        "Year": 2022,
        "Make": "Honda",
        "Model": "Accord",
        "Price": 20000,
        "Cost": 17000,
    }
    attrs.update(overrides)
    ledger.add_entity(Entity(id=vehicle_id, entity_type=VEHICLE, attributes=attrs))
    return vehicle_id


# ---------------------------------------------------------------------------
# Price banding
# ---------------------------------------------------------------------------


class TestVehicleBrief:
    @pytest.mark.parametrize(
        "price,expected_band",
        [
            (0, "under_15k"),
            (14999, "under_15k"),
            (15000, "15k_25k"),
            (24999, "15k_25k"),
            (25000, "25k_40k"),
            (39999, "25k_40k"),
            (40000, "40k_plus"),
            (999999, "40k_plus"),
        ],
    )
    def test_price_band_boundaries(self, price, expected_band):
        _add_vehicle("VEH-1", Price=price)
        result = inventory_aging.get_vehicle_aging_brief("VEH-1")
        assert result["vehicle"]["price_band"] == expected_band

    def test_margin_pct_computed_from_price_and_cost(self):
        _add_vehicle("VEH-1", Price=20000, Cost=17000)
        result = inventory_aging.get_vehicle_aging_brief("VEH-1")
        assert result["vehicle"]["margin_pct"] == round(100 * (20000 - 17000) / 20000, 1)

    def test_margin_pct_none_when_no_cost(self):
        _add_vehicle("VEH-1", Price=20000, Cost=None)
        result = inventory_aging.get_vehicle_aging_brief("VEH-1")
        assert result["vehicle"]["margin_pct"] is None


class TestGetVehicleAgingBrief:
    def test_unknown_vehicle_rejected(self):
        result = inventory_aging.get_vehicle_aging_brief("VEH-NOPE")
        assert "error" in result

    def test_shape_on_success(self):
        _add_vehicle("VEH-1")
        result = inventory_aging.get_vehicle_aging_brief("VEH-1")
        assert result["vehicle"]["vehicle_id"] == "VEH-1"
        assert result["price_history"] == []
        assert "HEURISTIC" in result["note"]

    def test_includes_real_price_history_after_a_reduction(self):
        _add_vehicle("VEH-1", Price=20000)
        inventory_aging.reduce_price("VEH-1", 18000, "EMP-1")
        result = inventory_aging.get_vehicle_aging_brief("VEH-1")
        assert len(result["price_history"]) == 1
        assert result["price_history"][0]["new_price"] == 18000.0


class TestGetAgingBoard:
    def test_empty_state(self):
        result = inventory_aging.get_aging_board()
        assert result["unsold_count"] == 0
        assert set(result["by_price_band"].keys()) == {"under_15k", "15k_25k", "25k_40k", "40k_plus"}
        assert all(v == [] for v in result["by_price_band"].values())

    def test_only_unsold_vehicles_included(self):
        _add_vehicle("VEH-1", Price=20000)
        _add_vehicle("VEH-2", Price=20000, DateSold="2026-01-01")
        result = inventory_aging.get_aging_board()
        assert result["unsold_count"] == 1
        ids = {v["vehicle_id"] for v in result["by_price_band"]["15k_25k"]}
        assert ids == {"VEH-1"}

    def test_vehicles_bucketed_into_correct_band(self):
        _add_vehicle("VEH-1", Price=10000)
        _add_vehicle("VEH-2", Price=45000)
        result = inventory_aging.get_aging_board()
        assert len(result["by_price_band"]["under_15k"]) == 1
        assert len(result["by_price_band"]["40k_plus"]) == 1

    def test_sorted_descending_by_price_within_band(self):
        _add_vehicle("VEH-1", Price=16000)
        _add_vehicle("VEH-2", Price=24000)
        _add_vehicle("VEH-3", Price=20000)
        result = inventory_aging.get_aging_board()
        prices = [v["price"] for v in result["by_price_band"]["15k_25k"]]
        assert prices == sorted(prices, reverse=True)

    def test_note_is_honest_about_heuristic_basis(self):
        result = inventory_aging.get_aging_board()
        assert "HEURISTIC" in result["note"]


# ---------------------------------------------------------------------------
# reduce_price -- reduction-only, backs Operations' Aging Action Center
# ---------------------------------------------------------------------------


class TestReducePrice:
    def test_unknown_vehicle_rejected(self):
        result = inventory_aging.reduce_price("VEH-NOPE", 15000, "EMP-1")
        assert "error" in result

    def test_non_numeric_price_rejected(self):
        _add_vehicle("VEH-1")
        result = inventory_aging.reduce_price("VEH-1", "not-a-number", "EMP-1")
        assert "error" in result

    def test_zero_or_negative_price_rejected(self):
        _add_vehicle("VEH-1")
        result = inventory_aging.reduce_price("VEH-1", 0, "EMP-1")
        assert "error" in result

    def test_a_higher_price_is_rejected(self):
        _add_vehicle("VEH-1", Price=20000)
        result = inventory_aging.reduce_price("VEH-1", 21000, "EMP-1")
        assert "error" in result

    def test_an_equal_price_is_rejected(self):
        _add_vehicle("VEH-1", Price=20000)
        result = inventory_aging.reduce_price("VEH-1", 20000, "EMP-1")
        assert "error" in result

    def test_zero_old_price_bypasses_the_reduction_only_guard(self):
        # reduce_price()'s direction guard only fires `and old_price > 0`,
        # so a vehicle with no real Price on file lets any positive
        # new_price through even though it isn't technically a reduction.
        _add_vehicle("VEH-1", Price=0)
        result = inventory_aging.reduce_price("VEH-1", 5000, "EMP-1")
        assert "error" not in result
        assert result["vehicle"]["price"] == 5000.0

    def test_a_real_reduction_succeeds_and_logs_history(self):
        _add_vehicle("VEH-1", Price=20000)
        result = inventory_aging.reduce_price("VEH-1", 18000, "EMP-1", reason="Aging inventory")
        assert result["vehicle"]["price"] == 18000.0
        entry = result["history"][0]
        assert entry["old_price"] == 20000.0
        assert entry["new_price"] == 18000.0
        assert entry["reason"] == "Aging inventory"
        assert entry["updated_by"] == "EMP-1"

    def test_mutates_the_real_vehicle_entity(self):
        _add_vehicle("VEH-1", Price=20000)
        inventory_aging.reduce_price("VEH-1", 18000, "EMP-1")
        v = ledger.get_entity("VEH-1")
        assert v.attributes["Price"] == 18000.0

    def test_history_accumulates_across_multiple_reductions(self):
        _add_vehicle("VEH-1", Price=20000)
        inventory_aging.reduce_price("VEH-1", 18000, "EMP-1")
        inventory_aging.reduce_price("VEH-1", 16000, "EMP-1")
        v = ledger.get_entity("VEH-1")
        assert len(v.attributes["price_history"]) == 2


# ---------------------------------------------------------------------------
# set_price -- bidirectional Pricing Desk sibling
# ---------------------------------------------------------------------------


class TestSetPrice:
    def test_unknown_vehicle_rejected(self):
        result = inventory_aging.set_price("VEH-NOPE", 15000, "EMP-1")
        assert "error" in result

    def test_non_numeric_price_rejected(self):
        _add_vehicle("VEH-1")
        result = inventory_aging.set_price("VEH-1", "bogus", "EMP-1")
        assert "error" in result

    def test_zero_or_negative_price_rejected(self):
        _add_vehicle("VEH-1")
        result = inventory_aging.set_price("VEH-1", -1, "EMP-1")
        assert "error" in result

    def test_a_price_increase_is_allowed(self):
        # Unlike reduce_price(), set_price() is genuinely bidirectional --
        # something reduce_price() itself would reject.
        _add_vehicle("VEH-1", Price=20000)
        result = inventory_aging.set_price("VEH-1", 22000, "EMP-1", reason="Underpriced vs. market")
        assert "error" not in result
        assert result["vehicle"]["price"] == 22000.0
        assert result["history"][0]["reason"] == "Underpriced vs. market"

    def test_a_price_decrease_is_also_allowed(self):
        _add_vehicle("VEH-1", Price=20000)
        result = inventory_aging.set_price("VEH-1", 18000, "EMP-1")
        assert result["vehicle"]["price"] == 18000.0

    def test_reduce_price_is_untouched_by_set_price_existing(self):
        _add_vehicle("VEH-1", Price=20000)
        result = inventory_aging.reduce_price("VEH-1", 21000, "EMP-1")
        assert "error" in result


# ---------------------------------------------------------------------------
# Review / assignment / marketing-tie-in actions
# ---------------------------------------------------------------------------


class TestRequestWholesaleReview:
    def test_unknown_vehicle_rejected(self):
        result = inventory_aging.request_wholesale_review("VEH-NOPE", "EMP-1")
        assert "error" in result

    def test_creates_a_real_operations_task(self):
        _add_vehicle("VEH-1", Year=2021, Make="Toyota", Model="Camry")
        task = inventory_aging.request_wholesale_review("VEH-1", "EMP-1", notes="Sitting too long")
        assert task.attributes["task_type"] == "transfer_to_wholesale"
        assert task.attributes["priority"] == "normal"
        assert task.attributes["owner_bucket"] == "Inventory Manager"
        assert task.attributes["linked_entity_id"] == "VEH-1"
        assert task.attributes["source_entity_id"] == "aging:VEH-1"
        assert "Toyota" in task.attributes["detail"]
        assert "Sitting too long" in task.attributes["detail"]


class TestRequestManagerReview:
    def test_unknown_vehicle_rejected(self):
        result = inventory_aging.request_manager_review("VEH-NOPE", "EMP-1")
        assert "error" in result

    def test_creates_a_real_operations_task_at_high_priority(self):
        _add_vehicle("VEH-1")
        task = inventory_aging.request_manager_review("VEH-1", "EMP-1")
        assert task.attributes["task_type"] == "manager_review"
        assert task.attributes["priority"] == "high"
        assert task.attributes["owner_bucket"] == "Inventory Manager"


class TestRequestAuctionAssignment:
    def test_unknown_vehicle_rejected(self):
        result = inventory_aging.request_auction_assignment("VEH-NOPE", "EMP-1")
        assert "error" in result

    def test_creates_a_real_operations_task_with_honest_scope_note(self):
        _add_vehicle("VEH-1")
        task = inventory_aging.request_auction_assignment("VEH-1", "EMP-1")
        assert task.attributes["task_type"] == "auction_assignment"
        assert "No auction-house integration exists" in task.attributes["detail"]


class TestCreateMarketingTieIn:
    def test_unknown_vehicle_rejected(self):
        result = inventory_aging.create_marketing_tie_in("VEH-NOPE", "EMP-1")
        assert "error" in result

    def test_no_make_or_model_rejected(self):
        _add_vehicle("VEH-1", Make=None, Model=None)
        result = inventory_aging.create_marketing_tie_in("VEH-1", "EMP-1")
        assert "error" in result

    def test_creates_a_real_draft_campaign_and_tie_in_task(self):
        _add_vehicle("VEH-1", Year=2021, Make="Toyota", Model="Camry")
        result = inventory_aging.create_marketing_tie_in("VEH-1", "EMP-1")

        campaign = result["campaign"]
        assert campaign.attributes["campaign_type"] == "inventory_ads"
        assert campaign.attributes["params"] == {"make": "Toyota", "model": "Camry"}
        assert campaign.attributes["status"] == "draft"

        task = result["task"]
        assert task.attributes["task_type"] == "marketing_campaign_tie_in"
        assert campaign.id in task.attributes["detail"]
        assert task.attributes["linked_entity_id"] == "VEH-1"

    def test_only_make_present_still_succeeds(self):
        _add_vehicle("VEH-1", Make="Toyota", Model=None)
        result = inventory_aging.create_marketing_tie_in("VEH-1", "EMP-1")
        assert "error" not in result


# ---------------------------------------------------------------------------
# API layer -- role gating
# ---------------------------------------------------------------------------


_VIEW_ALLOWED = [ADMIN, OPERATIONS, SALES, SERVICE, MARKETING, FINANCE]
_VIEW_DENIED = ["BOGUS_ROLE"]

_MUTATE_ALLOWED = [ADMIN, OPERATIONS]
_MUTATE_DENIED = [SALES, SERVICE, MARKETING, FINANCE, "BOGUS_ROLE"]


class TestAcl:
    @pytest.mark.parametrize("role", _VIEW_DENIED)
    def test_get_aging_board_denied(self, role):
        result = inventory_aging_api.get_aging_board_api(role)
        assert "error" in result

    @pytest.mark.parametrize("role", _VIEW_ALLOWED)
    def test_get_aging_board_allowed(self, role):
        result = inventory_aging_api.get_aging_board_api(role)
        assert result["unsold_count"] == 0

    @pytest.mark.parametrize("role", _VIEW_DENIED)
    def test_get_vehicle_aging_brief_denied(self, role):
        _add_vehicle("VEH-1")
        result = inventory_aging_api.get_vehicle_aging_brief_api(role, "VEH-1")
        assert "error" in result

    @pytest.mark.parametrize("role", _VIEW_ALLOWED)
    def test_get_vehicle_aging_brief_allowed(self, role):
        ledger.reset()
        _add_vehicle("VEH-1")
        result = inventory_aging_api.get_vehicle_aging_brief_api(role, "VEH-1")
        assert result["vehicle"]["vehicle_id"] == "VEH-1"

    @pytest.mark.parametrize("role", _MUTATE_DENIED)
    def test_reduce_price_denied(self, role):
        _add_vehicle("VEH-1", Price=20000)
        result = inventory_aging_api.reduce_price_api(role, "EMP-1", "VEH-1", 18000)
        assert "error" in result

    @pytest.mark.parametrize("role", _MUTATE_ALLOWED)
    def test_reduce_price_allowed(self, role):
        ledger.reset()
        _add_vehicle("VEH-1", Price=20000)
        result = inventory_aging_api.reduce_price_api(role, "EMP-1", "VEH-1", 18000)
        assert result["vehicle"]["price"] == 18000.0

    @pytest.mark.parametrize("role", _MUTATE_DENIED)
    def test_request_wholesale_review_denied(self, role):
        _add_vehicle("VEH-1")
        result = inventory_aging_api.request_wholesale_review_api(role, "EMP-1", "VEH-1")
        assert "error" in result

    @pytest.mark.parametrize("role", _MUTATE_ALLOWED)
    def test_request_wholesale_review_allowed(self, role):
        ledger.reset()
        _add_vehicle("VEH-1")
        result = inventory_aging_api.request_wholesale_review_api(role, "EMP-1", "VEH-1")
        assert result["task_type"] == "transfer_to_wholesale"

    @pytest.mark.parametrize("role", _MUTATE_DENIED)
    def test_request_manager_review_denied(self, role):
        _add_vehicle("VEH-1")
        result = inventory_aging_api.request_manager_review_api(role, "EMP-1", "VEH-1")
        assert "error" in result

    @pytest.mark.parametrize("role", _MUTATE_ALLOWED)
    def test_request_manager_review_allowed(self, role):
        ledger.reset()
        _add_vehicle("VEH-1")
        result = inventory_aging_api.request_manager_review_api(role, "EMP-1", "VEH-1")
        assert result["task_type"] == "manager_review"

    @pytest.mark.parametrize("role", _MUTATE_DENIED)
    def test_request_auction_assignment_denied(self, role):
        _add_vehicle("VEH-1")
        result = inventory_aging_api.request_auction_assignment_api(role, "EMP-1", "VEH-1")
        assert "error" in result

    @pytest.mark.parametrize("role", _MUTATE_ALLOWED)
    def test_request_auction_assignment_allowed(self, role):
        ledger.reset()
        _add_vehicle("VEH-1")
        result = inventory_aging_api.request_auction_assignment_api(role, "EMP-1", "VEH-1")
        assert result["task_type"] == "auction_assignment"

    @pytest.mark.parametrize("role", _MUTATE_DENIED)
    def test_create_marketing_tie_in_denied(self, role):
        _add_vehicle("VEH-1")
        result = inventory_aging_api.create_marketing_tie_in_api(role, "EMP-1", "VEH-1")
        assert "error" in result

    @pytest.mark.parametrize("role", _MUTATE_ALLOWED)
    def test_create_marketing_tie_in_allowed(self, role):
        ledger.reset()
        _add_vehicle("VEH-1", Make="Toyota", Model="Camry")
        result = inventory_aging_api.create_marketing_tie_in_api(role, "EMP-1", "VEH-1")
        assert result["campaign"].attributes["campaign_type"] == "inventory_ads"
