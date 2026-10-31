"""Tests for core/customer_journey.py -- the graph-native Customer Journey
Engine (slice 1): lifecycle stage tracking stored directly as attributes on the
Customer entity, plus its core/customer_journey_api.py ACL layer.

Follows tests/test_communications_hub.py's own established conventions
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

from core import customer_journey
from core import customer_journey_api


_VIEW_ROLES = (ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE)


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    monkeypatch.setattr(customer_journey, "save_graph", lambda filepath: None)


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


class TestStagesConstants:

    def test_stages_are_the_seven_ordered_lifecycle_stages(self):
        assert customer_journey.STAGES == [
            "AWARENESS", "LEAD", "APPOINTMENT", "SALE",
            "SERVICE", "LOYALTY", "REPEAT",
        ]

    def test_forward_transitions_chain_through_the_ordered_stages(self):
        assert customer_journey.FORWARD_TRANSITIONS["AWARENESS"] == "LEAD"
        assert customer_journey.FORWARD_TRANSITIONS["SALE"] == "SERVICE"
        assert customer_journey.FORWARD_TRANSITIONS["REPEAT"] is None


class TestSetJourneyStage:

    def test_sets_a_real_stage_and_returns_the_brief(self):
        _add_customer()
        brief = customer_journey.set_journey_stage("CUST-1", "LEAD")
        assert brief["customer_id"] == "CUST-1"
        assert brief["name"] == "Jamie Buyer"
        assert brief["journey_stage"] == "LEAD"

    def test_persists_the_stage_onto_the_customer_entity(self):
        _add_customer()
        customer_journey.set_journey_stage("CUST-1", "APPOINTMENT")
        entity = ledger.get_entity("CUST-1")
        assert entity.attributes["journey_stage"] == "APPOINTMENT"

    def test_records_a_history_entry_with_stage_timestamp_and_note(self):
        _add_customer()
        brief = customer_journey.set_journey_stage("CUST-1", "SALE", note="Deal funded")
        history = brief["journey_history"]
        assert len(history) == 1
        assert history[0]["stage"] == "SALE"
        assert history[0]["note"] == "Deal funded"
        assert history[0]["timestamp"] is not None

    def test_an_omitted_note_is_stored_as_an_empty_string(self):
        _add_customer()
        brief = customer_journey.set_journey_stage("CUST-1", "LEAD")
        assert brief["journey_history"][0]["note"] == ""

    def test_set_can_jump_to_any_valid_stage_not_just_the_next_one(self):
        _add_customer()
        brief = customer_journey.set_journey_stage("CUST-1", "LOYALTY")
        assert brief["journey_stage"] == "LOYALTY"

    def test_rejects_an_invalid_stage(self):
        _add_customer()
        with pytest.raises(ValueError) as exc:
            customer_journey.set_journey_stage("CUST-1", "PURGATORY")
        assert "Invalid journey stage 'PURGATORY'" in str(exc.value)

    def test_rejects_an_unknown_customer(self):
        with pytest.raises(ValueError) as exc:
            customer_journey.set_journey_stage("CUST-NOPE", "LEAD")
        assert str(exc.value) == "No customer found with id CUST-NOPE."

    def test_rejects_an_id_that_is_not_actually_a_customer(self):
        _add_lead()
        with pytest.raises(ValueError) as exc:
            customer_journey.set_journey_stage("LEAD-1", "LEAD")
        assert str(exc.value) == "No customer found with id LEAD-1."


class TestHistoryAccumulation:

    def test_history_accumulates_one_entry_per_stage_change_in_order(self):
        _add_customer()
        customer_journey.set_journey_stage("CUST-1", "AWARENESS", note="saw an ad")
        customer_journey.set_journey_stage("CUST-1", "LEAD", note="filled a form")
        brief = customer_journey.set_journey_stage("CUST-1", "APPOINTMENT", note="booked")
        stages = [entry["stage"] for entry in brief["journey_history"]]
        assert stages == ["AWARENESS", "LEAD", "APPOINTMENT"]
        notes = [entry["note"] for entry in brief["journey_history"]]
        assert notes == ["saw an ad", "filled a form", "booked"]


class TestAdvanceJourney:

    def test_advancing_a_new_customer_starts_them_at_the_first_stage(self):
        _add_customer()
        brief = customer_journey.advance_journey("CUST-1")
        assert brief["journey_stage"] == "AWARENESS"
        assert len(brief["journey_history"]) == 1

    def test_advancing_moves_to_the_next_ordered_stage(self):
        _add_customer()
        customer_journey.set_journey_stage("CUST-1", "LEAD")
        brief = customer_journey.advance_journey("CUST-1")
        assert brief["journey_stage"] == "APPOINTMENT"

    def test_advancing_all_the_way_walks_every_stage_in_order(self):
        _add_customer()
        seen = [customer_journey.advance_journey("CUST-1")["journey_stage"]]
        for _ in range(len(customer_journey.STAGES) - 1):
            seen.append(customer_journey.advance_journey("CUST-1")["journey_stage"])
        assert seen == customer_journey.STAGES

    def test_advancing_carries_the_note_into_history(self):
        _add_customer()
        brief = customer_journey.advance_journey("CUST-1", note="kickoff")
        assert brief["journey_history"][-1]["note"] == "kickoff"

    def test_advancing_past_the_final_stage_raises(self):
        _add_customer()
        customer_journey.set_journey_stage("CUST-1", "REPEAT")
        with pytest.raises(ValueError) as exc:
            customer_journey.advance_journey("CUST-1")
        assert "already at the final journey stage" in str(exc.value)

    def test_advancing_an_unknown_customer_raises(self):
        with pytest.raises(ValueError) as exc:
            customer_journey.advance_journey("CUST-GHOST")
        assert str(exc.value) == "No customer found with id CUST-GHOST."


class TestGetCustomerJourney:

    def test_returns_the_real_journey_record(self):
        _add_customer()
        customer_journey.set_journey_stage("CUST-1", "SERVICE", note="oil change")
        brief = customer_journey.get_customer_journey("CUST-1")
        assert brief["journey_stage"] == "SERVICE"
        assert brief["journey_history"][0]["stage"] == "SERVICE"

    def test_a_customer_never_set_has_no_stage_and_empty_history(self):
        _add_customer()
        brief = customer_journey.get_customer_journey("CUST-1")
        assert brief["journey_stage"] is None
        assert brief["journey_history"] == []

    def test_unknown_customer_raises(self):
        with pytest.raises(ValueError) as exc:
            customer_journey.get_customer_journey("CUST-404")
        assert str(exc.value) == "No customer found with id CUST-404."


class TestListCustomersInStage:

    def _seed_three(self):
        _add_customer("CUST-1")
        _add_customer("CUST-2")
        _add_customer("CUST-3")
        customer_journey.set_journey_stage("CUST-1", "LEAD")
        customer_journey.set_journey_stage("CUST-2", "LEAD")
        customer_journey.set_journey_stage("CUST-3", "SALE")

    def test_returns_only_customers_in_the_given_stage(self):
        self._seed_three()
        results = customer_journey.list_customers_in_stage("LEAD")
        ids = sorted(r["customer_id"] for r in results)
        assert ids == ["CUST-1", "CUST-2"]

    def test_returns_an_empty_list_for_a_stage_with_no_customers(self):
        self._seed_three()
        assert customer_journey.list_customers_in_stage("REPEAT") == []

    def test_rejects_an_invalid_stage(self):
        with pytest.raises(ValueError) as exc:
            customer_journey.list_customers_in_stage("NOWHERE")
        assert "Invalid journey stage 'NOWHERE'" in str(exc.value)


class TestGetJourneyOverview:

    def test_seeds_every_stage_to_zero_when_empty(self):
        overview = customer_journey.get_journey_overview()
        assert overview["total_customers_in_journey"] == 0
        for stage in customer_journey.STAGES:
            assert overview["counts_by_stage"][stage] == 0

    def test_counts_customers_per_stage_and_totals_them(self):
        _add_customer("CUST-1")
        _add_customer("CUST-2")
        _add_customer("CUST-3")
        _add_customer("CUST-4")
        customer_journey.set_journey_stage("CUST-1", "LEAD")
        customer_journey.set_journey_stage("CUST-2", "LEAD")
        customer_journey.set_journey_stage("CUST-3", "SALE")
        overview = customer_journey.get_journey_overview()
        assert overview["counts_by_stage"]["LEAD"] == 2
        assert overview["counts_by_stage"]["SALE"] == 1
        assert overview["counts_by_stage"]["AWARENESS"] == 0
        assert overview["total_customers_in_journey"] == 3

    def test_a_customer_with_no_stage_is_not_counted(self):
        _add_customer("CUST-1")
        overview = customer_journey.get_journey_overview()
        assert overview["total_customers_in_journey"] == 0

    def test_non_customer_entities_are_never_counted(self):
        _add_lead()
        overview = customer_journey.get_journey_overview()
        assert overview["total_customers_in_journey"] == 0


class TestCustomerJourneyApiRoleGating:

    def _seed_one(self):
        _add_customer()
        customer_journey.set_journey_stage("CUST-1", "LEAD")

    def test_every_real_view_role_can_view_the_overview(self):
        for role in _VIEW_ROLES:
            result = customer_journey_api.get_journey_overview_api(role)
            assert "error" not in result

    def test_an_unknown_role_is_denied_the_overview(self):
        result = customer_journey_api.get_journey_overview_api("BOGUS")
        assert "error" in result

    def test_every_real_view_role_can_view_a_customer_journey(self):
        self._seed_one()
        for role in _VIEW_ROLES:
            result = customer_journey_api.get_customer_journey_api(role, "CUST-1")
            assert "error" not in result

    def test_an_unknown_role_is_denied_viewing_a_customer_journey(self):
        self._seed_one()
        result = customer_journey_api.get_customer_journey_api("BOGUS", "CUST-1")
        assert "error" in result

    def test_every_real_view_role_can_advance(self):
        for role in _VIEW_ROLES:
            _add_customer(f"CUST-{role}")
            result = customer_journey_api.advance_journey_api(role, f"CUST-{role}")
            assert "error" not in result
            assert result["journey_stage"] == "AWARENESS"

    def test_an_unknown_role_is_denied_advancing(self):
        _add_customer()
        result = customer_journey_api.advance_journey_api("BOGUS", "CUST-1")
        assert "error" in result

    def test_every_real_view_role_can_set_a_stage(self):
        for role in _VIEW_ROLES:
            _add_customer(f"CUST-{role}")
            result = customer_journey_api.set_journey_stage_api(role, f"CUST-{role}", "SALE")
            assert "error" not in result
            assert result["journey_stage"] == "SALE"

    def test_an_unknown_role_is_denied_setting_a_stage(self):
        _add_customer()
        result = customer_journey_api.set_journey_stage_api("BOGUS", "CUST-1", "SALE")
        assert "error" in result

    def test_every_real_view_role_can_list_by_stage(self):
        self._seed_one()
        for role in _VIEW_ROLES:
            result = customer_journey_api.list_customers_in_stage_api(role, "LEAD")
            assert isinstance(result, list)

    def test_an_unknown_role_is_denied_listing_by_stage(self):
        result = customer_journey_api.list_customers_in_stage_api("BOGUS", "LEAD")
        assert "error" in result


class TestCustomerJourneyApiErrorsSurface:

    def test_an_unknown_customer_error_surfaces_through_the_api(self):
        result = customer_journey_api.get_customer_journey_api(ADMIN, "CUST-NOPE")
        assert result["error"] == "No customer found with id CUST-NOPE."

    def test_an_invalid_stage_error_surfaces_through_the_api(self):
        _add_customer()
        result = customer_journey_api.set_journey_stage_api(ADMIN, "CUST-1", "BADSTAGE")
        assert "error" in result
        assert "Invalid journey stage 'BADSTAGE'" in result["error"]

    def test_advancing_past_the_final_stage_surfaces_through_the_api(self):
        _add_customer()
        customer_journey.set_journey_stage("CUST-1", "REPEAT")
        result = customer_journey_api.advance_journey_api(ADMIN, "CUST-1")
        assert "error" in result
        assert "already at the final journey stage" in result["error"]
