"""Tests for core/equity_center.py -- the graph-native Equity Center
(estimated equity position, lease-maturity + trade-up opportunities, recorded
upgrade offers, a live overview, and a real isolated-OpenAI AI upgrade offer)
plus its core/equity_center_api.py ACL layer.

Follows tests/test_customer_journey.py's / tests/test_customer_journey_ai.py's
own established conventions (fresh_ledger + no_real_persistence autouse
fixtures, a _VIEW_ROLES constant, class-grouped tests, direct asserts, no
per-test docstrings) so the suite never touches real storage.

The AI feature's kill-switch flag ('equity_upgrade_offer_enabled') and catalog
entry are wired by the parent into the shared FEATURE_FLAGS / AI_FEATURE_CATALOG
and are NOT present standalone -- so, rather than lean on set_feature_flag (which
validates against FEATURE_FLAGS) or is_feature_enabled (which fails open for an
unknown key), these tests monkeypatch equity_center.is_feature_enabled and
equity_center.record_call_attempt directly. This keeps the suite standalone-green
today AND correct once the parent wires the real flag. This sandbox has no
outbound network, so the happy-path test monkeypatches the isolated OpenAI client
(equity_center.client) with a fake returning valid JSON.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
from datetime import date, timedelta

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import CUSTOMER, LEAD
from core.permissions import ADMIN, FINANCE, MARKETING, OPERATIONS, SALES, SERVICE

from core import equity_center
from core import equity_center_api


_VIEW_ROLES = (ADMIN, OPERATIONS, SALES, FINANCE)
_DENIED_ROLES = (MARKETING, SERVICE, "BOGUS")

_OFFER_KEYS = {"headline", "message", "suggested_next_step"}


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    monkeypatch.setattr(equity_center, "save_graph", lambda filepath: None)


def _soon_date(days=30):
    return (date.today() + timedelta(days=days)).isoformat()


def _add_customer(customer_id="CUST-1", first="Jamie", last="Buyer", **attrs):
    base = {"FirstName": first, "LastName": last}
    base.update(attrs)
    customer = Entity(id=customer_id, entity_type=CUSTOMER, attributes=base)
    ledger.add_entity(customer)
    return customer


def _add_lead(lead_id="LEAD-1", name="Jordan Prospect"):
    lead = Entity(id=lead_id, entity_type=LEAD, attributes={"Name": name})
    ledger.add_entity(lead)
    return lead


class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content):
        self.message = _FakeMessage(content)


class _FakeCompletion:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


def _install_fake_client(monkeypatch, content):
    def _fake_create(*args, **kwargs):
        return _FakeCompletion(content)

    monkeypatch.setattr(equity_center.client.chat.completions, "create", _fake_create)


_VALID_OFFER_JSON = json.dumps({
    "headline": "Time to trade up?",
    "message": "You may be sitting on strong estimated equity. Let's confirm the real numbers.",
    "suggested_next_step": "Book an appraisal appointment",
})


class TestGetEquityPosition:

    def test_positive_equity_status(self):
        _add_customer(estimated_payoff=15000, estimated_value=20000)
        position = equity_center.get_equity_position("CUST-1")
        assert position["equity_amount"] == 5000.0
        assert position["status"] == "positive"
        assert position["is_estimated"] is True
        assert position["basis"] == equity_center.ESTIMATE_BASIS
        assert position["disclaimer"]

    def test_negative_equity_status(self):
        _add_customer(estimated_payoff=18000, estimated_value=12000)
        position = equity_center.get_equity_position("CUST-1")
        assert position["equity_amount"] == -6000.0
        assert position["status"] == "negative"

    def test_near_even_equity_status(self):
        _add_customer(estimated_payoff=15200, estimated_value=15000)
        position = equity_center.get_equity_position("CUST-1")
        assert position["equity_amount"] == -200.0
        assert position["status"] == "near_even"

    def test_missing_estimates_are_unknown_never_fabricated(self):
        _add_customer()
        position = equity_center.get_equity_position("CUST-1")
        assert position["equity_amount"] is None
        assert position["status"] == "unknown"
        assert position["has_estimate_inputs"] is False

    def test_lease_maturing_soon_is_flagged(self):
        _add_customer(lease_maturity_date=_soon_date(30))
        position = equity_center.get_equity_position("CUST-1")
        assert position["lease_maturing_soon"] is True
        assert 0 <= position["days_to_lease_maturity"] <= 90

    def test_lease_far_out_is_not_flagged(self):
        _add_customer(lease_maturity_date=_soon_date(400))
        position = equity_center.get_equity_position("CUST-1")
        assert position["lease_maturing_soon"] is False

    def test_unknown_customer_raises(self):
        with pytest.raises(ValueError) as exc:
            equity_center.get_equity_position("CUST-404")
        assert str(exc.value) == "No customer found with id CUST-404."

    def test_non_customer_id_raises(self):
        _add_lead()
        with pytest.raises(ValueError) as exc:
            equity_center.get_equity_position("LEAD-1")
        assert str(exc.value) == "No customer found with id LEAD-1."


class TestListEquityOpportunities:

    def _seed(self):
        _add_customer("CUST-POS", estimated_payoff=15000, estimated_value=20000)
        _add_customer("CUST-LEASE", estimated_payoff=15000, estimated_value=15100,
                      lease_maturity_date=_soon_date(20))
        _add_customer("CUST-BOTH", estimated_payoff=10000, estimated_value=18000,
                      lease_maturity_date=_soon_date(15))
        _add_customer("CUST-NEG", estimated_payoff=18000, estimated_value=12000)
        _add_customer("CUST-NONE")

    def test_returns_only_positive_equity_or_lease_maturing_customers(self):
        self._seed()
        results = equity_center.list_equity_opportunities()
        ids = {r["customer_id"] for r in results}
        assert ids == {"CUST-POS", "CUST-LEASE", "CUST-BOTH"}

    def test_upgrade_ready_requires_both_signals(self):
        self._seed()
        by_id = {r["customer_id"]: r for r in equity_center.list_equity_opportunities()}
        assert by_id["CUST-BOTH"]["upgrade_ready"] is True
        assert by_id["CUST-POS"]["upgrade_ready"] is False
        assert by_id["CUST-LEASE"]["upgrade_ready"] is False

    def test_each_opportunity_carries_a_reason(self):
        self._seed()
        by_id = {r["customer_id"]: r for r in equity_center.list_equity_opportunities()}
        assert "Positive estimated equity" in by_id["CUST-POS"]["reason"]
        assert "matures in" in by_id["CUST-LEASE"]["reason"]

    def test_strongest_prospect_sorts_first(self):
        self._seed()
        results = equity_center.list_equity_opportunities()
        assert results[0]["customer_id"] == "CUST-BOTH"

    def test_honors_a_custom_horizon(self):
        _add_customer("CUST-FAR", lease_maturity_date=_soon_date(120))
        assert equity_center.list_equity_opportunities() == []
        results = equity_center.list_equity_opportunities(horizon_days=180)
        assert {r["customer_id"] for r in results} == {"CUST-FAR"}


class TestCreateUpgradeOffer:

    def test_records_an_offer_on_the_customer(self):
        _add_customer(estimated_payoff=15000, estimated_value=20000)
        offer = equity_center.create_upgrade_offer("CUST-1", note="Called, interested")
        assert offer["id"].startswith("EQOF-")
        assert offer["customer_id"] == "CUST-1"
        assert offer["note"] == "Called, interested"
        assert offer["equity_amount"] == 5000.0
        assert offer["status"] == "positive"
        assert offer["is_estimated"] is True

    def test_offer_is_persisted_onto_the_customer_entity(self):
        _add_customer(estimated_payoff=15000, estimated_value=20000)
        equity_center.create_upgrade_offer("CUST-1")
        equity_center.create_upgrade_offer("CUST-1")
        entity = ledger.get_entity("CUST-1")
        offers = entity.attributes[equity_center.OFFERS_KEY]
        assert len(offers) == 2
        assert offers[0]["id"] != offers[1]["id"]

    def test_omitted_note_is_stored_as_empty_string(self):
        _add_customer(estimated_payoff=15000, estimated_value=20000)
        offer = equity_center.create_upgrade_offer("CUST-1")
        assert offer["note"] == ""

    def test_unknown_customer_raises(self):
        with pytest.raises(ValueError) as exc:
            equity_center.create_upgrade_offer("CUST-404")
        assert str(exc.value) == "No customer found with id CUST-404."


class TestGetEquityOverview:

    def test_seeds_zero_on_an_empty_ledger(self):
        overview = equity_center.get_equity_overview()
        assert overview["positive_equity"] == 0
        assert overview["lease_maturing_soon"] == 0
        assert overview["upgrade_ready"] == 0
        assert overview["total_estimated_opportunity"] == 0.0

    def test_counts_and_totals_the_estimated_opportunity(self):
        _add_customer("CUST-POS", estimated_payoff=15000, estimated_value=20000)
        _add_customer("CUST-BOTH", estimated_payoff=10000, estimated_value=18000,
                      lease_maturity_date=_soon_date(15))
        _add_customer("CUST-LEASE", estimated_payoff=15000, estimated_value=15100,
                      lease_maturity_date=_soon_date(20))
        _add_customer("CUST-NEG", estimated_payoff=18000, estimated_value=12000)
        _add_customer("CUST-NONE")
        overview = equity_center.get_equity_overview()
        assert overview["positive_equity"] == 2  # CUST-POS + CUST-BOTH
        assert overview["lease_maturing_soon"] == 2  # CUST-BOTH + CUST-LEASE
        assert overview["upgrade_ready"] == 1  # CUST-BOTH only
        assert overview["negative_equity"] == 1
        assert overview["near_even"] == 1  # CUST-LEASE
        assert overview["customers_with_estimates"] == 4
        assert overview["total_customers"] == 5
        # 5000 (POS) + 8000 (BOTH) = 13000 estimated opportunity.
        assert overview["total_estimated_opportunity"] == 13000.0
        assert overview["is_estimated"] is True

    def test_non_customers_are_never_counted(self):
        _add_lead()
        overview = equity_center.get_equity_overview()
        assert overview["total_customers"] == 0


class TestGenerateUpgradeOfferHappyPath:

    def test_returns_and_stores_the_ai_offer(self, monkeypatch):
        _add_customer(estimated_payoff=15000, estimated_value=20000)
        monkeypatch.setattr(equity_center, "is_feature_enabled", lambda key: True)
        monkeypatch.setattr(equity_center, "record_call_attempt", lambda *a, **k: None)
        _install_fake_client(monkeypatch, _VALID_OFFER_JSON)

        result = equity_center.generate_upgrade_offer("CUST-1")

        assert _OFFER_KEYS.issubset(result.keys())
        assert result["headline"] == "Time to trade up?"
        assert result["suggested_next_step"] == "Book an appraisal appointment"
        assert result["ai_generated"] is True
        assert "disabled" not in result

        entity = ledger.get_entity("CUST-1")
        assert entity.attributes["equity_ai_upgrade_offer"]["ai_generated"] is True

    def test_missing_model_keys_default_to_empty(self, monkeypatch):
        _add_customer(estimated_payoff=15000, estimated_value=20000)
        monkeypatch.setattr(equity_center, "is_feature_enabled", lambda key: True)
        monkeypatch.setattr(equity_center, "record_call_attempt", lambda *a, **k: None)
        _install_fake_client(monkeypatch, json.dumps({"headline": "Hi"}))

        result = equity_center.generate_upgrade_offer("CUST-1")
        assert result["headline"] == "Hi"
        assert result["message"] == ""
        assert result["suggested_next_step"] == ""
        assert result["ai_generated"] is True


class TestGenerateUpgradeOfferDisabled:

    def test_returns_an_honest_disabled_fallback(self, monkeypatch):
        _add_customer(estimated_payoff=15000, estimated_value=20000)
        monkeypatch.setattr(equity_center, "is_feature_enabled", lambda key: False)
        monkeypatch.setattr(equity_center, "record_call_attempt", lambda *a, **k: None)

        result = equity_center.generate_upgrade_offer("CUST-1")

        assert _OFFER_KEYS.issubset(result.keys())
        assert result["ai_generated"] is False
        assert result["disabled"] is True

    def test_a_disabled_offer_is_not_persisted(self, monkeypatch):
        _add_customer(estimated_payoff=15000, estimated_value=20000)
        monkeypatch.setattr(equity_center, "is_feature_enabled", lambda key: False)
        monkeypatch.setattr(equity_center, "record_call_attempt", lambda *a, **k: None)

        equity_center.generate_upgrade_offer("CUST-1")
        entity = ledger.get_entity("CUST-1")
        assert "equity_ai_upgrade_offer" not in entity.attributes


class TestGenerateUpgradeOfferFallback:

    def test_malformed_output_falls_back_with_a_reason(self, monkeypatch):
        _add_customer(estimated_payoff=15000, estimated_value=20000)
        monkeypatch.setattr(equity_center, "is_feature_enabled", lambda key: True)
        monkeypatch.setattr(equity_center, "record_call_attempt", lambda *a, **k: None)
        _install_fake_client(monkeypatch, "not valid json {oops")

        result = equity_center.generate_upgrade_offer("CUST-1")
        assert _OFFER_KEYS.issubset(result.keys())
        assert result["ai_generated"] is False
        assert "disabled" not in result
        assert result["fallback_reason"]

    def test_a_failed_offer_is_not_persisted(self, monkeypatch):
        _add_customer(estimated_payoff=15000, estimated_value=20000)
        monkeypatch.setattr(equity_center, "is_feature_enabled", lambda key: True)
        monkeypatch.setattr(equity_center, "record_call_attempt", lambda *a, **k: None)
        _install_fake_client(monkeypatch, "not json")

        equity_center.generate_upgrade_offer("CUST-1")
        entity = ledger.get_entity("CUST-1")
        assert "equity_ai_upgrade_offer" not in entity.attributes

    def test_fallback_offer_is_grounded_in_the_real_status(self):
        position = {"name": "Sam", "status": "positive", "equity_amount": 5000,
                    "lease_maturing_soon": False, "days_to_lease_maturity": None}
        offer = equity_center.fallback_upgrade_offer(position)
        assert _OFFER_KEYS.issubset(offer.keys())
        assert offer["headline"]
        assert offer["message"]

    def test_unknown_customer_raises(self):
        with pytest.raises(ValueError) as exc:
            equity_center.generate_upgrade_offer("CUST-404")
        assert str(exc.value) == "No customer found with id CUST-404."


class TestEquityCenterApiRoleGating:

    def _seed_one(self):
        _add_customer(estimated_payoff=15000, estimated_value=20000)

    def test_every_view_role_can_view_the_overview(self):
        for role in _VIEW_ROLES:
            result = equity_center_api.get_equity_overview_api(role)
            assert "error" not in result

    def test_denied_roles_cannot_view_the_overview(self):
        for role in _DENIED_ROLES:
            result = equity_center_api.get_equity_overview_api(role)
            assert "error" in result

    def test_every_view_role_can_list_opportunities(self):
        self._seed_one()
        for role in _VIEW_ROLES:
            result = equity_center_api.list_equity_opportunities_api(role)
            assert isinstance(result, list)

    def test_denied_role_cannot_list_opportunities(self):
        result = equity_center_api.list_equity_opportunities_api("MARKETING")
        assert "error" in result

    def test_every_view_role_can_view_a_position(self):
        self._seed_one()
        for role in _VIEW_ROLES:
            result = equity_center_api.get_equity_position_api(role, "CUST-1")
            assert "error" not in result

    def test_denied_role_cannot_view_a_position(self):
        self._seed_one()
        result = equity_center_api.get_equity_position_api("SERVICE", "CUST-1")
        assert "error" in result

    def test_every_view_role_can_create_an_offer(self):
        for role in _VIEW_ROLES:
            _add_customer(f"CUST-{role}", estimated_payoff=15000, estimated_value=20000)
            result = equity_center_api.create_upgrade_offer_api(role, f"CUST-{role}")
            assert "error" not in result
            assert result["id"].startswith("EQOF-")

    def test_denied_role_cannot_create_an_offer(self):
        self._seed_one()
        result = equity_center_api.create_upgrade_offer_api("BOGUS", "CUST-1")
        assert "error" in result

    def test_denied_role_cannot_generate_an_ai_offer(self):
        self._seed_one()
        result = equity_center_api.generate_upgrade_offer_api("MARKETING", "CUST-1")
        assert "error" in result


class TestEquityCenterApiErrorsSurface:

    def test_unknown_customer_position_error_surfaces(self):
        result = equity_center_api.get_equity_position_api(ADMIN, "CUST-NOPE")
        assert result["error"] == "No customer found with id CUST-NOPE."

    def test_unknown_customer_offer_error_surfaces(self):
        result = equity_center_api.create_upgrade_offer_api(ADMIN, "CUST-NOPE")
        assert result["error"] == "No customer found with id CUST-NOPE."

    def test_unknown_customer_ai_offer_error_surfaces(self, monkeypatch):
        monkeypatch.setattr(equity_center, "is_feature_enabled", lambda key: False)
        monkeypatch.setattr(equity_center, "record_call_attempt", lambda *a, **k: None)
        result = equity_center_api.generate_upgrade_offer_api(ADMIN, "CUST-NOPE")
        assert result["error"] == "No customer found with id CUST-NOPE."
