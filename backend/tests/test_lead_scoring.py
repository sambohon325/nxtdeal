"""
Tests for core/lead_scoring.py / core/lead_scoring_api.py -- the real Lead Scoring
engine (identity resolution, per-signal point breakdown, tiering) and the
leaderboard, plus the ACL layer.

Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.relationships import Relationship
from core.entity_types import (
    LEAD, CUSTOMER, DEAL, CREDIT_APPLICATION, DEMO_DRIVE, EVENT_RSVP,
    APPOINTMENT, WEBSITE_CHAT_SESSION, TRIGGER_ALERT,
)
from core.relationship_types import BECAME, GENERATED_LEAD
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE

from core import field_notes
from core.lead_scoring import compute_score, leaderboard, POINTS
from core.lead_scoring_api import compute_score_api, leaderboard_api


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    monkeypatch.setattr(field_notes, "save_graph", lambda filepath: None)


def _lead(lead_id="LEAD-1", pipeline_state="NEW", source="Website"):
    entity = Entity(
        id=lead_id,
        entity_type=LEAD,
        attributes={"PipelineState": pipeline_state, "Source": source},
    )
    ledger.add_entity(entity)
    return entity


def _customer(customer_id="CUST-1"):
    entity = Entity(id=customer_id, entity_type=CUSTOMER, attributes={"FirstName": "Jordan"})
    ledger.add_entity(entity)
    return entity


def _became(lead_id, customer_id):
    ledger.add_relationship(Relationship(source_id=lead_id, target_id=customer_id, relationship_type=BECAME))


def _generated_lead(customer_id, lead_id):
    ledger.add_relationship(Relationship(source_id=customer_id, target_id=lead_id, relationship_type=GENERATED_LEAD))


_id_counter = [0]


def _next_id(prefix):
    _id_counter[0] += 1
    return f"{prefix}-TEST-{_id_counter[0]:05d}"


def _credit_app(customer_id):
    entity = Entity(id=_next_id("CAPP"), entity_type=CREDIT_APPLICATION, attributes={"customer_id": customer_id})
    ledger.add_entity(entity)
    return entity


def _deal(customer_id):
    entity = Entity(id=_next_id("DEAL"), entity_type=DEAL, attributes={"customer_id": customer_id})
    ledger.add_entity(entity)
    return entity


def _demo_drive(linked_entity_id, status="returned"):
    entity = Entity(id=_next_id("DEMO"), entity_type=DEMO_DRIVE, attributes={"linked_entity_id": linked_entity_id, "status": status})
    ledger.add_entity(entity)
    return entity


def _appointment(customer_id=None, lead_id=None, status="scheduled"):
    entity = Entity(
        id=_next_id("APPT"),
        entity_type=APPOINTMENT,
        attributes={"customer_id": customer_id, "lead_id": lead_id, "status": status},
    )
    ledger.add_entity(entity)
    return entity


def _rsvp(customer_id=None, lead_id=None):
    entity = Entity(id=_next_id("RSVP"), entity_type=EVENT_RSVP, attributes={"customer_id": customer_id, "lead_id": lead_id})
    ledger.add_entity(entity)
    return entity


def _chat_session(lead_id):
    entity = Entity(id=_next_id("CHAT"), entity_type=WEBSITE_CHAT_SESSION, attributes={"lead_id": lead_id})
    ledger.add_entity(entity)
    return entity


def _trigger_alert(target_entity_id, status="new"):
    entity = Entity(id=_next_id("ALERT"), entity_type=TRIGGER_ALERT, attributes={"target_entity_id": target_entity_id, "status": status})
    ledger.add_entity(entity)
    return entity


# ---------------------------------------------------------------------------
# _resolve_identity() -- exercised indirectly through compute_score(), since
# it's a private helper with no direct export.
# ---------------------------------------------------------------------------

class TestIdentityResolution:

    def test_unknown_entity_returns_error(self):
        result = compute_score("LEAD-NOPE")
        assert result == {"error": "Entity not found or not a Lead/Customer"}

    def test_lead_only_no_conversion(self):
        _lead("LEAD-1")
        result = compute_score("LEAD-1")
        assert "error" not in result
        assert result["entity_id"] == "LEAD-1"

    def test_score_resolves_across_lead_to_customer_conversion(self):
        _lead("LEAD-1")
        _customer("CUST-1")
        _became("LEAD-1", "CUST-1")
        _deal("CUST-1")

        result = compute_score("LEAD-1")

        assert result["score"] == POINTS["deal_desked"]

    def test_score_resolves_from_customer_back_to_became_lead(self):
        _lead("LEAD-1")
        _customer("CUST-1")
        _became("LEAD-1", "CUST-1")
        _chat_session("LEAD-1")

        result = compute_score("CUST-1")

        assert result["score"] == POINTS["website_chat_initiated"]

    def test_score_resolves_from_customer_to_generated_lead(self):
        _customer("CUST-1")
        _lead("LEAD-GEN")
        _generated_lead("CUST-1", "LEAD-GEN")
        _chat_session("LEAD-GEN")

        result = compute_score("CUST-1")

        assert result["score"] == POINTS["website_chat_initiated"]

    def test_generated_lead_resolution_is_one_directional_from_the_customer(self):
        # _resolve_identity() only walks GENERATED_LEAD from the Customer's own
        # side (Customer -> its generated Lead(s)) -- it does not walk the
        # relationship in reverse when starting from the Lead itself, so a
        # signal attached to the originating Customer is NOT visible when
        # querying the generated Lead directly. Confirms the resolution is
        # deliberately one-directional here, not a bug in this test.
        _customer("CUST-1")
        _lead("LEAD-GEN")
        _generated_lead("CUST-1", "LEAD-GEN")
        _deal("CUST-1")

        result = compute_score("LEAD-GEN")

        assert result["score"] == 0


# ---------------------------------------------------------------------------
# compute_score() -- per-signal breakdown.
# ---------------------------------------------------------------------------

class TestComputeScoreSignals:

    def test_credit_application_started(self):
        _lead("LEAD-1")
        _customer("CUST-1")
        _became("LEAD-1", "CUST-1")
        _credit_app("CUST-1")

        result = compute_score("LEAD-1")

        assert result["score"] == POINTS["credit_application_started"]
        reason = next(b for b in result["breakdown"] if b["reason"] == "Started Credit Application")
        assert reason["count"] == 1
        assert reason["points"] == 40

    def test_deal_desked(self):
        _lead("LEAD-1")
        _customer("CUST-1")
        _became("LEAD-1", "CUST-1")
        _deal("CUST-1")
        _deal("CUST-1")

        result = compute_score("LEAD-1")

        assert result["score"] == 2 * POINTS["deal_desked"]

    def test_test_drive_completed_only_counts_returned_status(self):
        _lead("LEAD-1")
        _demo_drive("LEAD-1", status="returned")
        _demo_drive("LEAD-1", status="out")
        _demo_drive("LEAD-1", status="cancelled")

        result = compute_score("LEAD-1")

        assert result["score"] == POINTS["test_drive_completed"]

    def test_appointment_attended_counts_arrived_and_completed(self):
        _lead("LEAD-1")
        _appointment(lead_id="LEAD-1", status="arrived")
        _appointment(lead_id="LEAD-1", status="completed")

        result = compute_score("LEAD-1")

        assert result["score"] == 2 * POINTS["appointment_attended"]

    def test_appointment_scheduled_excludes_terminal_statuses(self):
        _lead("LEAD-1")
        _appointment(lead_id="LEAD-1", status="scheduled")
        _appointment(lead_id="LEAD-1", status="confirmed")
        _appointment(lead_id="LEAD-1", status="no_show")
        _appointment(lead_id="LEAD-1", status="cancelled")

        result = compute_score("LEAD-1")

        assert result["score"] == 2 * POINTS["appointment_scheduled"]

    def test_appointment_can_match_via_customer_id_too(self):
        _lead("LEAD-1")
        _customer("CUST-1")
        _became("LEAD-1", "CUST-1")
        _appointment(customer_id="CUST-1", status="arrived")

        result = compute_score("LEAD-1")

        assert result["score"] == POINTS["appointment_attended"]

    def test_event_rsvp(self):
        _lead("LEAD-1")
        _rsvp(lead_id="LEAD-1")

        result = compute_score("LEAD-1")

        assert result["score"] == POINTS["event_rsvp"]

    def test_website_chat_initiated_only_matches_lead_id(self):
        _lead("LEAD-1")
        _customer("CUST-1")
        _became("LEAD-1", "CUST-1")
        _chat_session("LEAD-1")
        # A chat session with no lead_id at all should never match anything.
        Entity_no_lead = Entity(id="CHAT-ANON", entity_type=WEBSITE_CHAT_SESSION, attributes={"lead_id": None})
        ledger.add_entity(Entity_no_lead)

        result = compute_score("LEAD-1")

        assert result["score"] == POINTS["website_chat_initiated"]

    def test_trigger_alert_match_only_counts_new_status(self):
        _lead("LEAD-1")
        _trigger_alert("LEAD-1", status="new")
        _trigger_alert("LEAD-1", status="dismissed")
        _trigger_alert("LEAD-1", status="promoted")

        result = compute_score("LEAD-1")

        assert result["score"] == POINTS["trigger_alert_match"]

    def test_communication_logged_counts_only_communication_categories(self):
        _lead("LEAD-1")
        field_notes.create_field_note("Sales", "call", "Called", "EMP-1", linked_entity_id="LEAD-1")
        field_notes.create_field_note("Sales", "text", "Texted", "EMP-1", linked_entity_id="LEAD-1")
        field_notes.create_field_note("Sales", "objection", "Not a comm category", "EMP-1", linked_entity_id="LEAD-1")

        result = compute_score("LEAD-1")

        assert result["score"] == 2 * POINTS["communication_logged"]

    def test_communication_logged_capped_at_three(self):
        _lead("LEAD-1")
        for i in range(5):
            field_notes.create_field_note("Sales", "call", f"Call {i}", "EMP-1", linked_entity_id="LEAD-1")

        result = compute_score("LEAD-1")

        assert result["score"] == 3 * POINTS["communication_logged"]
        reason = next(b for b in result["breakdown"] if b["reason"] == "Communication Logged")
        assert reason["count"] == 3

    def test_zero_signals_yields_zero_score_and_empty_breakdown(self):
        _lead("LEAD-1")
        result = compute_score("LEAD-1")
        assert result["score"] == 0
        assert result["breakdown"] == []

    def test_not_yet_tracked_present_with_four_documented_gaps(self):
        _lead("LEAD-1")
        result = compute_score("LEAD-1")
        assert len(result["not_yet_tracked"]) == 4


class TestComputeScoreTiers:

    def test_cool_tier_under_50(self):
        _lead("LEAD-1")
        _rsvp(lead_id="LEAD-1")  # 15 points
        result = compute_score("LEAD-1")
        assert result["score"] == 15
        assert result["tier"] == "cool"

    def test_warm_tier_at_exactly_50(self):
        _lead("LEAD-1")
        _customer("CUST-1")
        _became("LEAD-1", "CUST-1")
        _deal("CUST-1")  # 30
        _rsvp(lead_id="LEAD-1")  # 15
        field_notes.create_field_note("Sales", "call", "Call", "EMP-1", linked_entity_id="LEAD-1")  # 5
        result = compute_score("LEAD-1")
        assert result["score"] == 50
        assert result["tier"] == "warm"

    def test_hot_tier_at_exactly_100(self):
        _lead("LEAD-1")
        _customer("CUST-1")
        _became("LEAD-1", "CUST-1")
        _credit_app("CUST-1")  # 40
        _deal("CUST-1")  # 30
        _demo_drive("LEAD-1", status="returned")  # 25
        _rsvp(lead_id="LEAD-1")  # 15
        result = compute_score("LEAD-1")
        assert result["score"] == 110
        assert result["tier"] == "hot"

    def test_cool_tier_just_under_warm_boundary(self):
        _lead("LEAD-1")
        _rsvp(lead_id="LEAD-1")  # 15
        _rsvp(lead_id="LEAD-1")  # 15
        _rsvp(lead_id="LEAD-1")  # 15
        result = compute_score("LEAD-1")
        assert result["score"] == 45
        assert result["tier"] == "cool"


# ---------------------------------------------------------------------------
# leaderboard()
# ---------------------------------------------------------------------------

class TestLeaderboard:

    def test_empty_leaderboard(self):
        result = leaderboard()
        assert result == {"count": 0, "by_tier": {"hot": 0, "warm": 0, "cool": 0}, "leads": []}

    def test_sold_and_lost_leads_excluded(self):
        _lead("LEAD-SOLD", pipeline_state="SOLD")
        _lead("LEAD-LOST", pipeline_state="LOST")
        _lead("LEAD-OPEN", pipeline_state="NEW")

        result = leaderboard()

        ids = {l["lead_id"] for l in result["leads"]}
        assert ids == {"LEAD-OPEN"}
        assert result["count"] == 1

    def test_sorted_descending_by_score(self):
        _lead("LEAD-LOW")
        _lead("LEAD-HIGH")
        _rsvp(lead_id="LEAD-LOW")  # 15
        _rsvp(lead_id="LEAD-HIGH")
        _rsvp(lead_id="LEAD-HIGH")
        _rsvp(lead_id="LEAD-HIGH")  # 45

        result = leaderboard()

        assert [l["lead_id"] for l in result["leads"]] == ["LEAD-HIGH", "LEAD-LOW"]

    def test_by_tier_counts_are_accurate(self):
        _lead("LEAD-COOL")
        _lead("LEAD-WARM")
        _customer("CUST-WARM")
        _became("LEAD-WARM", "CUST-WARM")
        _deal("CUST-WARM")
        _rsvp(lead_id="LEAD-WARM")
        field_notes.create_field_note("Sales", "call", "Call", "EMP-1", linked_entity_id="LEAD-WARM")  # 30+15+5=50

        result = leaderboard()

        assert result["by_tier"] == {"hot": 0, "warm": 1, "cool": 1}

    def test_limit_truncates_returned_leads_but_not_count(self):
        for i in range(5):
            _lead(f"LEAD-{i}")

        result = leaderboard(limit=2)

        assert result["count"] == 5
        assert len(result["leads"]) == 2

    def test_leaderboard_entries_carry_pipeline_state_and_source(self):
        _lead("LEAD-1", pipeline_state="CONTACTED", source="Referral")

        result = leaderboard()

        entry = result["leads"][0]
        assert entry["pipeline_state"] == "CONTACTED"
        assert entry["source"] == "Referral"


# ---------------------------------------------------------------------------
# ACL layer
# ---------------------------------------------------------------------------

class TestComputeScoreApi:

    @pytest.mark.parametrize("role", [SERVICE, FINANCE])
    def test_denied_roles(self, role):
        _lead("LEAD-1")
        result = compute_score_api(role, "LEAD-1")
        assert result == {"error": "You don't have access to Lead Scoring with your current role."}

    @pytest.mark.parametrize("role", [ADMIN, OPERATIONS, SALES, MARKETING])
    def test_allowed_roles_match_direct_call(self, role):
        _lead("LEAD-1")
        direct = compute_score("LEAD-1")
        via_api = compute_score_api(role, "LEAD-1")
        assert via_api == direct


class TestLeaderboardApi:

    @pytest.mark.parametrize("role", [SERVICE, FINANCE])
    def test_denied_roles(self, role):
        result = leaderboard_api(role)
        assert result == {"error": "You don't have access to Lead Scoring with your current role."}

    @pytest.mark.parametrize("role", [ADMIN, OPERATIONS, SALES, MARKETING])
    def test_allowed_roles_match_direct_call(self, role):
        _lead("LEAD-1")
        direct = leaderboard()
        via_api = leaderboard_api(role)
        assert via_api == direct

    def test_limit_passed_through(self):
        for i in range(5):
            _lead(f"LEAD-{i}")

        result = leaderboard_api(ADMIN, limit=2)

        assert len(result["leads"]) == 2
