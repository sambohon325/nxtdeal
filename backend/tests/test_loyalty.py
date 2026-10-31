"""Tests for core/loyalty.py -- the graph-native Loyalty / VIP Rewards engine
(points/tier/visit/referral/reward state stored directly as attributes on the
Customer entity) plus its core/loyalty_api.py ACL layer.

Follows tests/test_customer_journey.py's own established conventions
(fresh_ledger + no_real_persistence autouse fixtures, a _VIEW_ROLES constant,
class-grouped tests, direct asserts, no per-test docstrings) so the suite never
touches real storage.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import CUSTOMER, LEAD
from core.permissions import ADMIN, FINANCE, MARKETING, OPERATIONS, SALES, SERVICE

from core import loyalty
from core import loyalty_api


_VIEW_ROLES = (ADMIN, OPERATIONS, SALES, MARKETING, SERVICE)


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    monkeypatch.setattr(loyalty, "save_graph", lambda filepath: None)


def _add_customer(customer_id="CUST-1", first="Jamie", last="Buyer"):
    customer = Entity(
        id=customer_id,
        entity_type=CUSTOMER,
        attributes={"FirstName": first, "LastName": last},
    )
    ledger.add_entity(customer)
    return customer


def _add_lead(lead_id="LEAD-1", name="Jordan Prospect"):
    lead = Entity(id=lead_id, entity_type=LEAD, attributes={"Name": name})
    ledger.add_entity(lead)
    return lead


class TestTierConstants:

    def test_four_ordered_tiers_with_ascending_thresholds(self):
        assert loyalty.TIERS == ["Bronze", "Silver", "Gold", "Platinum"]
        thresholds = [t for _, t in loyalty.TIER_THRESHOLDS]
        assert thresholds == sorted(thresholds)

    def test_compute_tier_maps_lifetime_points_to_the_right_tier(self):
        assert loyalty._compute_tier(0) == "Bronze"
        assert loyalty._compute_tier(2499) == "Bronze"
        assert loyalty._compute_tier(2500) == "Silver"
        assert loyalty._compute_tier(7500) == "Gold"
        assert loyalty._compute_tier(19999) == "Gold"
        assert loyalty._compute_tier(20000) == "Platinum"
        assert loyalty._compute_tier(999999) == "Platinum"


class TestGetMemberAutoEnroll:

    def test_first_touch_auto_enrolls_with_zeroed_state(self):
        _add_customer()
        member = loyalty.get_member("CUST-1")
        assert member["customer_id"] == "CUST-1"
        assert member["name"] == "Jamie Buyer"
        assert member["enrolled"] is True
        assert member["points_balance"] == 0
        assert member["lifetime_points"] == 0
        assert member["tier"] == "Bronze"
        assert member["visits"] == 0
        assert member["referrals"] == 0
        assert member["ledger"] == []
        assert member["redemptions"] == []

    def test_enrollment_persists_onto_the_customer_entity(self):
        _add_customer()
        loyalty.get_member("CUST-1")
        entity = ledger.get_entity("CUST-1")
        assert entity.attributes["loyalty_enrolled_at"] is not None
        assert entity.attributes["loyalty_tier"] == "Bronze"

    def test_unknown_customer_raises(self):
        with pytest.raises(ValueError) as exc:
            loyalty.get_member("CUST-404")
        assert str(exc.value) == "No customer found with id CUST-404."

    def test_a_non_customer_id_raises(self):
        _add_lead()
        with pytest.raises(ValueError) as exc:
            loyalty.get_member("LEAD-1")
        assert str(exc.value) == "No customer found with id LEAD-1."


class TestAwardPoints:

    def test_awarding_updates_balance_lifetime_and_records_ledger(self):
        _add_customer()
        member = loyalty.award_points("CUST-1", 500, "Vehicle purchase", "Sales")
        assert member["points_balance"] == 500
        assert member["lifetime_points"] == 500
        assert member["tier"] == "Bronze"
        assert len(member["ledger"]) == 1
        entry = member["ledger"][0]
        assert entry["entry_type"] == "earn"
        assert entry["points"] == 500
        assert entry["reason"] == "Vehicle purchase"
        assert entry["department"] == "Sales"
        assert entry["balance_after"] == 500

    def test_points_accumulate_across_awards(self):
        _add_customer()
        loyalty.award_points("CUST-1", 1000, "Service", "Service")
        member = loyalty.award_points("CUST-1", 800, "Parts", "Parts")
        assert member["points_balance"] == 1800
        assert member["lifetime_points"] == 1800
        assert len(member["ledger"]) == 2

    def test_tier_recomputes_across_thresholds(self):
        _add_customer()
        m = loyalty.award_points("CUST-1", 2500, "Big buy", "Sales")
        assert m["tier"] == "Silver"
        m = loyalty.award_points("CUST-1", 5000, "Service plan", "Service")
        assert m["lifetime_points"] == 7500
        assert m["tier"] == "Gold"
        m = loyalty.award_points("CUST-1", 12500, "Second vehicle", "Sales")
        assert m["lifetime_points"] == 20000
        assert m["tier"] == "Platinum"

    def test_rejects_non_positive_points(self):
        _add_customer()
        with pytest.raises(ValueError):
            loyalty.award_points("CUST-1", 0, "nope", "Sales")
        with pytest.raises(ValueError):
            loyalty.award_points("CUST-1", -50, "nope", "Sales")

    def test_awarding_to_unknown_customer_raises(self):
        with pytest.raises(ValueError) as exc:
            loyalty.award_points("CUST-GHOST", 100, "x", "Sales")
        assert str(exc.value) == "No customer found with id CUST-GHOST."


class TestRecordVisit:

    def test_visit_increments_counter_and_logs_zero_point_entry(self):
        _add_customer()
        member = loyalty.record_visit("CUST-1", "Service")
        assert member["visits"] == 1
        assert member["ledger"][-1]["entry_type"] == "visit"
        assert member["ledger"][-1]["points"] == 0
        assert member["points_balance"] == 0

    def test_visits_accumulate(self):
        _add_customer()
        loyalty.record_visit("CUST-1", "Sales")
        member = loyalty.record_visit("CUST-1", "Parts")
        assert member["visits"] == 2

    def test_visit_unknown_customer_raises(self):
        with pytest.raises(ValueError):
            loyalty.record_visit("CUST-NOPE", "Sales")


class TestRecordReferral:

    def test_referral_increments_counter_and_logs_entry(self):
        _add_customer()
        member = loyalty.record_referral("CUST-1", "Alex Friend")
        assert member["referrals"] == 1
        assert member["ledger"][-1]["entry_type"] == "referral"
        assert "Alex Friend" in member["ledger"][-1]["reason"]

    def test_referral_requires_a_name(self):
        _add_customer()
        with pytest.raises(ValueError):
            loyalty.record_referral("CUST-1", "")

    def test_referral_unknown_customer_raises(self):
        with pytest.raises(ValueError):
            loyalty.record_referral("CUST-NOPE", "Someone")


class TestRewardsCatalog:

    def test_catalog_lists_rewards_with_point_costs_and_departments(self):
        catalog = loyalty.list_rewards_catalog()
        assert len(catalog) == len(loyalty.REWARDS_CATALOG)
        for item in catalog:
            assert item["reward_id"]
            assert item["name"]
            assert isinstance(item["point_cost"], int)
            assert item["department"]

    def test_catalog_spans_multiple_departments(self):
        departments = {item["department"] for item in loyalty.list_rewards_catalog()}
        assert {"Service", "Parts", "Accessories", "Sales"}.issubset(departments)


class TestRedeemReward:

    def test_redeem_deducts_balance_records_redemption_and_ledger(self):
        _add_customer()
        loyalty.award_points("CUST-1", 3000, "Purchase", "Sales")
        member = loyalty.redeem_reward("CUST-1", "RWD-OILCHANGE")  # 1500 cost
        assert member["points_balance"] == 1500
        assert len(member["redemptions"]) == 1
        assert member["redemptions"][0]["reward_id"] == "RWD-OILCHANGE"
        assert member["ledger"][-1]["entry_type"] == "redeem"
        assert member["ledger"][-1]["points"] == -1500

    def test_redeem_does_not_lower_lifetime_points_or_tier(self):
        _add_customer()
        loyalty.award_points("CUST-1", 2500, "Purchase", "Sales")
        assert loyalty.get_member("CUST-1")["tier"] == "Silver"
        member = loyalty.redeem_reward("CUST-1", "RWD-CARWASH")  # 500 cost
        assert member["points_balance"] == 2000
        assert member["lifetime_points"] == 2500
        assert member["tier"] == "Silver"

    def test_redeem_with_insufficient_points_raises(self):
        _add_customer()
        loyalty.award_points("CUST-1", 100, "Small", "Service")
        with pytest.raises(ValueError) as exc:
            loyalty.redeem_reward("CUST-1", "RWD-OILCHANGE")
        assert "Insufficient points" in str(exc.value)

    def test_redeem_unknown_reward_raises(self):
        _add_customer()
        loyalty.award_points("CUST-1", 5000, "Purchase", "Sales")
        with pytest.raises(ValueError) as exc:
            loyalty.redeem_reward("CUST-1", "RWD-DOES-NOT-EXIST")
        assert "No reward found with id RWD-DOES-NOT-EXIST." == str(exc.value)

    def test_redeem_unknown_customer_raises(self):
        with pytest.raises(ValueError) as exc:
            loyalty.redeem_reward("CUST-NOPE", "RWD-CARWASH")
        assert str(exc.value) == "No customer found with id CUST-NOPE."


class TestLoyaltyOverview:

    def test_empty_program_seeds_every_tier_to_zero(self):
        overview = loyalty.get_loyalty_overview()
        assert overview["member_count"] == 0
        assert overview["total_outstanding_points"] == 0
        assert overview["total_redemptions"] == 0
        for tier in loyalty.TIERS:
            assert overview["tier_distribution"][tier] == 0

    def test_overview_counts_members_points_tiers_and_redemptions(self):
        _add_customer("CUST-1")
        _add_customer("CUST-2")
        _add_customer("CUST-3")
        loyalty.award_points("CUST-1", 500, "buy", "Sales")     # Bronze, bal 500
        loyalty.award_points("CUST-2", 3000, "buy", "Sales")    # Silver, bal 3000
        loyalty.redeem_reward("CUST-2", "RWD-CARWASH")          # -500 -> bal 2500
        loyalty.get_member("CUST-3")                            # enrolled, Bronze, bal 0

        overview = loyalty.get_loyalty_overview()
        assert overview["member_count"] == 3
        assert overview["total_outstanding_points"] == 500 + 2500 + 0
        assert overview["tier_distribution"]["Bronze"] == 2
        assert overview["tier_distribution"]["Silver"] == 1
        assert overview["tier_distribution"]["Gold"] == 0
        assert overview["total_redemptions"] == 1

    def test_non_enrolled_customers_and_non_customers_are_not_counted(self):
        _add_customer("CUST-1")   # never touched -> not enrolled
        _add_lead()
        overview = loyalty.get_loyalty_overview()
        assert overview["member_count"] == 0


class TestLoyaltyApiRoleGating:

    def _seed_one(self):
        _add_customer()
        loyalty.award_points("CUST-1", 1000, "buy", "Sales")

    def test_every_real_view_role_can_view_the_overview(self):
        for role in _VIEW_ROLES:
            result = loyalty_api.get_loyalty_overview_api(role)
            assert "error" not in result

    def test_finance_is_denied_the_overview(self):
        result = loyalty_api.get_loyalty_overview_api(FINANCE)
        assert "error" in result

    def test_an_unknown_role_is_denied_the_overview(self):
        result = loyalty_api.get_loyalty_overview_api("BOGUS")
        assert "error" in result

    def test_every_real_view_role_can_view_the_catalog(self):
        for role in _VIEW_ROLES:
            result = loyalty_api.list_rewards_catalog_api(role)
            assert isinstance(result, list)

    def test_every_real_view_role_can_view_a_member(self):
        self._seed_one()
        for role in _VIEW_ROLES:
            result = loyalty_api.get_member_api(role, "CUST-1")
            assert "error" not in result

    def test_an_unknown_role_is_denied_viewing_a_member(self):
        self._seed_one()
        result = loyalty_api.get_member_api("BOGUS", "CUST-1")
        assert "error" in result

    def test_every_real_view_role_can_award_points(self):
        for role in _VIEW_ROLES:
            _add_customer(f"CUST-{role}")
            result = loyalty_api.award_points_api(role, f"CUST-{role}", 100, "x", "Sales")
            assert "error" not in result
            assert result["points_balance"] == 100

    def test_an_unknown_role_is_denied_awarding_points(self):
        _add_customer()
        result = loyalty_api.award_points_api("BOGUS", "CUST-1", 100, "x", "Sales")
        assert "error" in result

    def test_every_real_view_role_can_record_visit_and_referral(self):
        for role in _VIEW_ROLES:
            _add_customer(f"CUST-{role}")
            v = loyalty_api.record_visit_api(role, f"CUST-{role}", "Service")
            assert "error" not in v
            r = loyalty_api.record_referral_api(role, f"CUST-{role}", "Friend")
            assert "error" not in r

    def test_every_real_view_role_can_redeem(self):
        for role in _VIEW_ROLES:
            _add_customer(f"CUST-{role}")
            loyalty_api.award_points_api(role, f"CUST-{role}", 1000, "x", "Sales")
            result = loyalty_api.redeem_reward_api(role, f"CUST-{role}", "RWD-CARWASH")
            assert "error" not in result
            assert result["points_balance"] == 500

    def test_an_unknown_role_is_denied_redeeming(self):
        self._seed_one()
        result = loyalty_api.redeem_reward_api("BOGUS", "CUST-1", "RWD-CARWASH")
        assert "error" in result


class TestLoyaltyApiErrorsSurface:

    def test_unknown_customer_error_surfaces_through_the_api(self):
        result = loyalty_api.get_member_api(ADMIN, "CUST-NOPE")
        assert result["error"] == "No customer found with id CUST-NOPE."

    def test_insufficient_points_error_surfaces_through_the_api(self):
        _add_customer()
        loyalty_api.award_points_api(ADMIN, "CUST-1", 100, "x", "Service")
        result = loyalty_api.redeem_reward_api(ADMIN, "CUST-1", "RWD-OILCHANGE")
        assert "error" in result
        assert "Insufficient points" in result["error"]

    def test_unknown_reward_error_surfaces_through_the_api(self):
        _add_customer()
        loyalty_api.award_points_api(ADMIN, "CUST-1", 5000, "x", "Sales")
        result = loyalty_api.redeem_reward_api(ADMIN, "CUST-1", "RWD-BOGUS")
        assert "error" in result
        assert "No reward found with id RWD-BOGUS." == result["error"]
