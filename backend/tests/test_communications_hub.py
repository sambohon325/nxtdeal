"""Tests for core/communications_hub.py -- the first-class Communication log
(real Phone/Text/Email/Chat/Social logging, honestly-simulated phone
recording/transcript/sentiment, real embedded follow-ups, and a real,
isolated-OpenAI-backed AI summary with an honest fallback) plus its
core/communications_hub_api.py ACL layer.

Follows tests/test_unified_communications.py's own established conventions
(fresh_ledger + no_real_persistence autouse fixtures, a _VIEW_ROLES constant,
class-grouped tests, direct asserts, no per-test docstrings) and
tests/test_email_wizard.py's own convention for testing an isolated-OpenAI
module: this sandbox genuinely has no outbound network access, so the AI
summary tests toggle the real "communications_hub_summary_enabled" feature
flag and assert on the real disabled/fallback dict shapes rather than mocking
the OpenAI client.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import CUSTOMER, LEAD
from core.permissions import ADMIN, FINANCE, MARKETING, OPERATIONS, SALES, SERVICE

from core import communications_hub
from core import communications_hub_api
from core.system_config import set_feature_flag


_VIEW_ROLES = (ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE)


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    monkeypatch.setattr(communications_hub, "save_graph", lambda filepath: None)


def _add_lead(lead_id="LEAD-1", name="Jordan Prospect"):
    lead = Entity(id=lead_id, entity_type=LEAD, attributes={"Name": name})
    ledger.add_entity(lead)
    return lead


def _add_customer(customer_id="CUST-1", first="Jamie", last="Buyer"):
    customer = Entity(
        id=customer_id,
        entity_type=CUSTOMER,
        attributes={"FirstName": first, "LastName": last},
    )
    ledger.add_entity(customer)
    return customer


class TestLogCommunicationValidation:

    def test_rejects_an_invalid_channel(self):
        comm, error = communications_hub.log_communication(
            department="Sales",
            channel="carrier_pigeon",
            direction="inbound",
            body="hello",
            created_by="EMP-1",
        )
        assert comm is None
        assert error == (
            "Invalid channel 'carrier_pigeon'. Must be one of: "
            + ", ".join(communications_hub.CHANNELS)
            + "."
        )

    def test_rejects_an_invalid_direction(self):
        comm, error = communications_hub.log_communication(
            department="Sales",
            channel="phone",
            direction="sideways",
            body="hello",
            created_by="EMP-1",
        )
        assert comm is None
        assert error == (
            "Invalid direction 'sideways'. Must be one of: "
            + ", ".join(communications_hub.DIRECTIONS)
            + "."
        )

    def test_rejects_an_empty_body(self):
        comm, error = communications_hub.log_communication(
            department="Sales",
            channel="text",
            direction="outbound",
            body="",
            created_by="EMP-1",
        )
        assert comm is None
        assert error == "A communication must have a non-empty body/summary."

    def test_rejects_a_whitespace_only_body(self):
        comm, error = communications_hub.log_communication(
            department="Sales",
            channel="text",
            direction="outbound",
            body="    ",
            created_by="EMP-1",
        )
        assert comm is None
        assert error == "A communication must have a non-empty body/summary."


class TestLogCommunicationSuccess:

    def test_logs_a_real_text_communication_with_no_recording(self):
        comm, error = communications_hub.log_communication(
            department="Sales",
            channel="text",
            direction="outbound",
            body="Following up on your trade-in",
            created_by="EMP-1",
        )
        assert error is None
        assert comm["id"].startswith("COMM-")
        assert comm["channel"] == "text"
        assert comm["direction"] == "outbound"
        assert comm["department"] == "Sales"
        assert comm["body"] == "Following up on your trade-in"
        assert comm["created_by"] == "EMP-1"
        assert comm["created_at"] is not None
        assert comm["recording"] is None
        assert comm["follow_up"] is None
        assert comm["ai_summary"] is None

    def test_every_non_phone_channel_gets_no_recording(self):
        for channel in communications_hub.CHANNELS:
            if channel == "phone":
                continue
            comm, error = communications_hub.log_communication(
                department="Service",
                channel=channel,
                direction="inbound",
                body="a message",
                created_by="EMP-2",
            )
            assert error is None
            assert comm["recording"] is None

    def test_logs_a_real_entity_it_can_be_linked_to(self):
        _add_lead()
        comm, error = communications_hub.log_communication(
            department="Sales",
            channel="email",
            direction="inbound",
            body="Interested in the SUV",
            created_by="EMP-1",
            linked_entity_id="LEAD-1",
        )
        assert error is None
        assert comm["linked_entity_id"] == "LEAD-1"

    def test_a_phone_communication_gets_a_real_simulated_recording(self):
        comm, error = communications_hub.log_communication(
            department="Sales",
            channel="phone",
            direction="inbound",
            body="Discussed financing options",
            created_by="EMP-1",
        )
        assert error is None
        recording = comm["recording"]
        assert recording is not None
        assert recording["basis"] == communications_hub.RECORDING_BASIS
        assert recording["disclaimer"] == communications_hub.RECORDING_DISCLAIMER
        assert recording["recording_url"] == f"https://simulated-recordings.example/{comm['id']}.mp3"
        assert recording["sentiment_label"] in communications_hub.SENTIMENT_LABELS
        assert 0.0 <= recording["sentiment_score"] <= 1.0
        assert isinstance(recording["transcript"], str) and recording["transcript"]

    def test_a_phone_call_with_no_duration_supplied_gets_backfilled_from_the_simulation(self):
        comm, error = communications_hub.log_communication(
            department="Sales",
            channel="phone",
            direction="outbound",
            body="Left a voicemail",
            created_by="EMP-1",
        )
        assert error is None
        assert comm["duration_seconds"] == comm["recording"]["duration_seconds"]
        assert comm["duration_seconds"] >= 30

    def test_a_phone_call_with_a_real_duration_supplied_keeps_it(self):
        comm, error = communications_hub.log_communication(
            department="Sales",
            channel="phone",
            direction="outbound",
            body="Long call",
            created_by="EMP-1",
            duration_seconds=842,
        )
        assert error is None
        assert comm["duration_seconds"] == 842
        assert comm["recording"]["duration_seconds"] == 842

    def test_the_same_comm_id_always_produces_the_same_simulated_recording(self):
        first = communications_hub._simulate_call_recording("COMM-FIXED", None)
        second = communications_hub._simulate_call_recording("COMM-FIXED", None)
        assert first == second

    def test_a_follow_up_is_created_with_all_expected_fields(self):
        comm, error = communications_hub.log_communication(
            department="Finance",
            channel="phone",
            direction="outbound",
            body="Need to confirm the payoff amount",
            created_by="EMP-3",
            follow_up_required=True,
            follow_up_due_at="2026-08-01T00:00:00+00:00",
            follow_up_note="Call back with payoff figure",
        )
        assert error is None
        follow_up = comm["follow_up"]
        assert follow_up["required"] is True
        assert follow_up["due_at"] == "2026-08-01T00:00:00+00:00"
        assert follow_up["completed"] is False
        assert follow_up["completed_at"] is None
        assert follow_up["completed_by"] is None
        assert follow_up["note"] == "Call back with payoff figure"

    def test_no_follow_up_is_created_when_not_requested(self):
        comm, error = communications_hub.log_communication(
            department="Finance",
            channel="email",
            direction="inbound",
            body="Just checking in",
            created_by="EMP-3",
        )
        assert error is None
        assert comm["follow_up"] is None


class TestGetCommunication:

    def test_returns_a_real_logged_communication(self):
        created, _ = communications_hub.log_communication(
            department="Sales",
            channel="chat",
            direction="inbound",
            body="Website chat message",
            created_by="EMP-1",
        )
        comm, error = communications_hub.get_communication(created["id"])
        assert error is None
        assert comm["id"] == created["id"]
        assert comm["body"] == "Website chat message"

    def test_returns_a_real_error_for_an_unknown_id(self):
        comm, error = communications_hub.get_communication("COMM-DOES-NOT-EXIST")
        assert comm is None
        assert error == "No communication found with id COMM-DOES-NOT-EXIST."

    def test_returns_a_real_error_for_an_id_that_is_not_actually_a_communication(self):
        _add_lead()
        comm, error = communications_hub.get_communication("LEAD-1")
        assert comm is None
        assert error == "No communication found with id LEAD-1."


class TestListCommunications:

    def _seed_mixed(self):
        communications_hub.log_communication(
            department="Sales", channel="phone", direction="inbound",
            body="a", created_by="EMP-1", linked_entity_id="LEAD-1",
        )
        communications_hub.log_communication(
            department="Sales", channel="text", direction="outbound",
            body="b", created_by="EMP-1", linked_entity_id="LEAD-1",
        )
        communications_hub.log_communication(
            department="Service", channel="phone", direction="inbound",
            body="c", created_by="EMP-2", linked_entity_id="CUST-1",
        )

    def test_returns_a_plain_list_of_every_communication_when_unfiltered(self):
        self._seed_mixed()
        results = communications_hub.list_communications()
        assert isinstance(results, list)
        assert len(results) == 3

    def test_filters_by_department(self):
        self._seed_mixed()
        results = communications_hub.list_communications(department="Service")
        assert len(results) == 1
        assert results[0]["department"] == "Service"

    def test_filters_by_channel(self):
        self._seed_mixed()
        results = communications_hub.list_communications(channel="text")
        assert len(results) == 1
        assert results[0]["channel"] == "text"

    def test_filters_by_linked_entity_id(self):
        self._seed_mixed()
        results = communications_hub.list_communications(linked_entity_id="CUST-1")
        assert len(results) == 1
        assert results[0]["linked_entity_id"] == "CUST-1"

    def test_filters_to_only_communications_with_a_pending_follow_up(self):
        communications_hub.log_communication(
            department="Finance", channel="phone", direction="outbound",
            body="follow up needed", created_by="EMP-3",
            follow_up_required=True,
        )
        communications_hub.log_communication(
            department="Finance", channel="phone", direction="outbound",
            body="no follow up", created_by="EMP-3",
        )
        results = communications_hub.list_communications(follow_up_pending_only=True)
        assert len(results) == 1
        assert results[0]["follow_up"]["required"] is True

    def test_a_completed_follow_up_is_excluded_from_the_pending_filter(self):
        created, _ = communications_hub.log_communication(
            department="Finance", channel="phone", direction="outbound",
            body="follow up needed", created_by="EMP-3",
            follow_up_required=True,
        )
        communications_hub.complete_follow_up(created["id"], "EMP-9")
        results = communications_hub.list_communications(follow_up_pending_only=True)
        assert results == []

    def test_results_are_sorted_most_recent_first(self):
        first, _ = communications_hub.log_communication(
            department="Sales", channel="text", direction="outbound",
            body="first", created_by="EMP-1",
        )
        second, _ = communications_hub.log_communication(
            department="Sales", channel="text", direction="outbound",
            body="second", created_by="EMP-1",
        )
        results = communications_hub.list_communications()
        assert results[0]["id"] == second["id"]
        assert results[1]["id"] == first["id"]

    def test_limit_caps_the_number_of_results(self):
        self._seed_mixed()
        results = communications_hub.list_communications(limit=1)
        assert len(results) == 1


class TestCompleteFollowUp:

    def test_completes_a_real_pending_follow_up(self):
        created, _ = communications_hub.log_communication(
            department="Finance", channel="phone", direction="outbound",
            body="callback needed", created_by="EMP-3",
            follow_up_required=True, follow_up_note="call about payoff",
        )
        comm, error = communications_hub.complete_follow_up(created["id"], "EMP-9")
        assert error is None
        assert comm["follow_up"]["completed"] is True
        assert comm["follow_up"]["completed_by"] == "EMP-9"
        assert comm["follow_up"]["completed_at"] is not None
        assert comm["follow_up"]["note"] == "call about payoff"

    def test_errors_on_an_unknown_communication_id(self):
        comm, error = communications_hub.complete_follow_up("COMM-BOGUS", "EMP-9")
        assert comm is None
        assert error == "No communication found with id COMM-BOGUS."

    def test_errors_when_there_is_no_follow_up_at_all(self):
        created, _ = communications_hub.log_communication(
            department="Sales", channel="text", direction="outbound",
            body="no follow up here", created_by="EMP-1",
        )
        comm, error = communications_hub.complete_follow_up(created["id"], "EMP-9")
        assert comm is None
        assert error == "This communication has no follow-up to complete."

    def test_errors_when_the_follow_up_is_already_completed(self):
        created, _ = communications_hub.log_communication(
            department="Finance", channel="phone", direction="outbound",
            body="callback needed", created_by="EMP-3",
            follow_up_required=True,
        )
        communications_hub.complete_follow_up(created["id"], "EMP-9")
        comm, error = communications_hub.complete_follow_up(created["id"], "EMP-9")
        assert comm is None
        assert error == "This communication's follow-up is already completed."


class TestGetCommunicationsStats:

    def test_returns_real_aggregate_counts(self):
        communications_hub.log_communication(
            department="Sales", channel="phone", direction="inbound",
            body="a", created_by="EMP-1",
        )
        communications_hub.log_communication(
            department="Sales", channel="text", direction="outbound",
            body="b", created_by="EMP-1", follow_up_required=True,
        )
        communications_hub.log_communication(
            department="Service", channel="phone", direction="outbound",
            body="c", created_by="EMP-2",
        )
        stats = communications_hub.get_communications_stats()
        assert stats["total_communications"] == 3
        assert stats["by_channel"]["phone"] == 2
        assert stats["by_channel"]["text"] == 1
        assert stats["by_direction"]["inbound"] == 1
        assert stats["by_direction"]["outbound"] == 2
        assert stats["open_follow_ups"] == 1
        assert stats["phone_calls_with_simulated_recording"] == 2
        assert stats["recording_basis_note"] == communications_hub.RECORDING_DISCLAIMER

    def test_by_channel_and_by_direction_are_seeded_for_every_real_value_even_at_zero(self):
        stats = communications_hub.get_communications_stats()
        assert stats["total_communications"] == 0
        for channel in communications_hub.CHANNELS:
            assert stats["by_channel"][channel] == 0
        for direction in communications_hub.DIRECTIONS:
            assert stats["by_direction"][direction] == 0

    def test_filters_by_department(self):
        communications_hub.log_communication(
            department="Sales", channel="phone", direction="inbound",
            body="a", created_by="EMP-1",
        )
        communications_hub.log_communication(
            department="Service", channel="phone", direction="inbound",
            body="b", created_by="EMP-2",
        )
        stats = communications_hub.get_communications_stats(department="Service")
        assert stats["total_communications"] == 1


class TestFallbackSummary:

    def test_builds_a_plain_honest_summary_from_the_communication(self):
        comm = {"channel": "text", "direction": "outbound", "body": "Following up on your trade-in"}
        result = communications_hub.fallback_summary(comm)
        assert result["summary"] == "A text outbound was logged: Following up on your trade-in"
        assert result["key_points"] == []
        assert result["suggested_follow_up"] == ""

    def test_truncates_a_very_long_body_to_200_characters(self):
        long_body = "x" * 500
        comm = {"channel": "phone", "direction": "inbound", "body": long_body}
        result = communications_hub.fallback_summary(comm)
        assert result["summary"] == f"A phone inbound was logged: {'x' * 200}"


class TestGenerateAiSummary:

    def test_errors_on_an_unknown_communication_id(self):
        summary, error = communications_hub.generate_ai_summary("COMM-BOGUS")
        assert summary is None
        assert error == "No communication found with id COMM-BOGUS."

    def test_returns_an_honest_disabled_fallback_when_the_feature_flag_is_off(self):
        created, _ = communications_hub.log_communication(
            department="Sales", channel="text", direction="outbound",
            body="Following up on your trade-in", created_by="EMP-1",
        )
        set_feature_flag("communications_hub_summary_enabled", False, "EMP-TEST")
        summary, error = communications_hub.generate_ai_summary(created["id"])
        assert error is None
        assert summary["ai_generated"] is False
        assert summary["disabled"] is True
        assert summary["summary"] == "A text outbound was logged: Following up on your trade-in"
        assert summary["key_points"] == []
        assert summary["suggested_follow_up"] == ""

    def test_returns_an_honest_fallback_with_a_reason_when_enabled_but_the_call_fails(self):
        created, _ = communications_hub.log_communication(
            department="Sales", channel="phone", direction="inbound",
            body="Discussed financing options", created_by="EMP-1",
        )
        set_feature_flag("communications_hub_summary_enabled", True, "EMP-TEST")
        summary, error = communications_hub.generate_ai_summary(created["id"])
        assert error is None
        assert summary["ai_generated"] is False
        assert "disabled" not in summary
        assert "fallback_reason" in summary
        assert summary["fallback_reason"]

    def test_a_disabled_summary_does_not_get_persisted_onto_the_communication(self):
        created, _ = communications_hub.log_communication(
            department="Sales", channel="text", direction="outbound",
            body="hello", created_by="EMP-1",
        )
        set_feature_flag("communications_hub_summary_enabled", False, "EMP-TEST")
        communications_hub.generate_ai_summary(created["id"])
        comm, _ = communications_hub.get_communication(created["id"])
        assert comm["ai_summary"] is None


class TestGetCommunicationsHubOverview:

    def test_returns_all_expected_top_level_keys(self):
        overview = communications_hub.get_communications_hub_overview(ADMIN)
        assert set(overview.keys()) == {
            "hub_stats",
            "hub_recent_communications",
            "hub_open_follow_ups",
            "legacy_unified_feed",
            "note",
        }

    def test_composes_real_hub_data_alongside_the_legacy_feed(self):
        communications_hub.log_communication(
            department="Sales", channel="phone", direction="inbound",
            body="a call", created_by="EMP-1", follow_up_required=True,
        )
        overview = communications_hub.get_communications_hub_overview(ADMIN)
        assert overview["hub_stats"]["total_communications"] == 1
        assert len(overview["hub_recent_communications"]) == 1
        assert len(overview["hub_open_follow_ups"]) == 1
        assert overview["legacy_unified_feed"] is not None

    def test_department_and_channel_filters_are_threaded_through(self):
        communications_hub.log_communication(
            department="Sales", channel="phone", direction="inbound",
            body="a", created_by="EMP-1",
        )
        communications_hub.log_communication(
            department="Service", channel="text", direction="inbound",
            body="b", created_by="EMP-2",
        )
        overview = communications_hub.get_communications_hub_overview(
            ADMIN, department="Sales", channel="phone"
        )
        assert overview["hub_stats"]["total_communications"] == 1
        assert overview["hub_recent_communications"][0]["department"] == "Sales"


class TestCommunicationsHubApiLogCommunication:

    def test_any_authenticated_role_may_log_a_communication_no_gate(self):
        for role in list(_VIEW_ROLES) + ["BOGUS"]:
            result = communications_hub_api.log_communication_api(
                "EMP-1",
                department="Sales",
                channel="text",
                direction="outbound",
                body=f"message from {role}",
            )
            assert "error" not in result

    def test_a_real_validation_error_still_surfaces_through_the_api(self):
        result = communications_hub_api.log_communication_api(
            "EMP-1",
            department="Sales",
            channel="not-a-channel",
            direction="outbound",
            body="hi",
        )
        assert "error" in result


class TestCommunicationsHubApiRoleGating:

    def _seed_one(self):
        return communications_hub_api.log_communication_api(
            "EMP-1", department="Sales", channel="text", direction="outbound", body="hi",
        )

    def test_every_real_view_role_can_view_a_communication(self):
        created = self._seed_one()
        for role in _VIEW_ROLES:
            result = communications_hub_api.get_communication_api(role, created["id"])
            assert "error" not in result

    def test_an_unknown_role_is_denied_viewing_a_communication(self):
        created = self._seed_one()
        result = communications_hub_api.get_communication_api("BOGUS", created["id"])
        assert "error" in result

    def test_every_real_view_role_can_list_communications(self):
        for role in _VIEW_ROLES:
            result = communications_hub_api.list_communications_api(role)
            assert isinstance(result, list)

    def test_an_unknown_role_is_denied_listing_communications(self):
        result = communications_hub_api.list_communications_api("BOGUS")
        assert "error" in result

    def test_every_real_view_role_can_complete_a_follow_up(self):
        for role in _VIEW_ROLES:
            created = communications_hub_api.log_communication_api(
                "EMP-1", department="Sales", channel="phone", direction="outbound",
                body="hi", follow_up_required=True,
            )
            result = communications_hub_api.complete_follow_up_api(role, "EMP-9", created["id"])
            assert "error" not in result

    def test_an_unknown_role_is_denied_completing_a_follow_up(self):
        created = communications_hub_api.log_communication_api(
            "EMP-1", department="Sales", channel="phone", direction="outbound",
            body="hi", follow_up_required=True,
        )
        result = communications_hub_api.complete_follow_up_api("BOGUS", "EMP-9", created["id"])
        assert "error" in result

    def test_every_real_view_role_can_view_stats(self):
        for role in _VIEW_ROLES:
            result = communications_hub_api.get_communications_stats_api(role)
            assert "error" not in result

    def test_an_unknown_role_is_denied_viewing_stats(self):
        result = communications_hub_api.get_communications_stats_api("BOGUS")
        assert "error" in result

    def test_every_real_view_role_can_generate_an_ai_summary(self):
        set_feature_flag("communications_hub_summary_enabled", False, "EMP-TEST")
        for role in _VIEW_ROLES:
            created = self._seed_one()
            result = communications_hub_api.generate_ai_summary_api(role, created["id"])
            assert "error" not in result

    def test_an_unknown_role_is_denied_generating_an_ai_summary(self):
        created = self._seed_one()
        result = communications_hub_api.generate_ai_summary_api("BOGUS", created["id"])
        assert "error" in result

    def test_every_real_view_role_can_view_the_hub_overview(self):
        for role in _VIEW_ROLES:
            result = communications_hub_api.get_communications_hub_overview_api(role)
            assert "error" not in result

    def test_an_unknown_role_is_denied_the_hub_overview(self):
        result = communications_hub_api.get_communications_hub_overview_api("BOGUS")
        assert "error" in result

    def test_a_denied_overview_call_does_not_include_any_hub_data(self):
        result = communications_hub_api.get_communications_hub_overview_api("BOGUS")
        assert "hub_stats" not in result
