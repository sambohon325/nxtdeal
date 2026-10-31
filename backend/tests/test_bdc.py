"""
Tests for core/bdc.py + core/bdc_api.py -- the BDC (internet-lead) queue. A pure
live-filter/computation module over already-real Lead entities and FieldNotes --
no new entity type, no mutations of its own.
"""
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import LEAD
from core.field_notes import create_field_note
from core import bdc
from core import bdc_api
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


_BDC_ROLES = (ADMIN, OPERATIONS, SALES)
_BDC_DENIED_ROLES = (MARKETING, SERVICE, FINANCE)


def _iso_minutes_ago(minutes):
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()


def _add_lead(lead_id="LEAD-1", source="Website", pipeline_state="NEW", minutes_ago=None, first="Alex", last="Prospect"):
    attrs = {
        "FirstName": first,
        "LastName": last,
        "Source": source,
        "PipelineState": pipeline_state,
        "CreatedDate": "2026-01-01",
    }
    if minutes_ago is not None:
        attrs["CreatedAt"] = _iso_minutes_ago(minutes_ago)
    ledger.add_entity(Entity(id=lead_id, entity_type=LEAD, attributes=attrs))
    return lead_id


def _log_contact(lead_id, category="call", minutes_ago=0):
    note = create_field_note("Sales", category, "Called the lead", "EMP-1", linked_entity_id=lead_id)
    note.attributes["created_at"] = _iso_minutes_ago(minutes_ago)
    return note


# ---------------------------------------------------------------------------
# get_untouched_queue
# ---------------------------------------------------------------------------

class TestGetUntouchedQueue:
    def test_only_includes_internet_sourced_leads(self):
        _add_lead("LEAD-1", source="Website", minutes_ago=5)
        _add_lead("LEAD-2", source="Autotrader", minutes_ago=5)
        _add_lead("LEAD-3", source="Referral", minutes_ago=5)

        queue = bdc.get_untouched_queue()
        assert {b["id"] for b in queue} == {"LEAD-1", "LEAD-2"}

    def test_only_includes_new_pipeline_state(self):
        _add_lead("LEAD-1", source="Website", pipeline_state="NEW", minutes_ago=5)
        _add_lead("LEAD-2", source="Website", pipeline_state="CONTACTED", minutes_ago=5)

        queue = bdc.get_untouched_queue()
        assert {b["id"] for b in queue} == {"LEAD-1"}

    def test_sorted_most_overdue_first(self):
        _add_lead("LEAD-RECENT", source="Website", minutes_ago=2)
        _add_lead("LEAD-OLD", source="Website", minutes_ago=90)

        queue = bdc.get_untouched_queue()
        assert [b["id"] for b in queue] == ["LEAD-OLD", "LEAD-RECENT"]

    def test_leads_without_precise_timestamp_sort_after_precise_ones(self):
        _add_lead("LEAD-PRECISE", source="Website", minutes_ago=5)
        _add_lead("LEAD-HISTORICAL", source="Website")  # no CreatedAt at all

        queue = bdc.get_untouched_queue()
        assert [b["id"] for b in queue] == ["LEAD-PRECISE", "LEAD-HISTORICAL"]

    def test_urgency_ok_under_threshold(self):
        _add_lead("LEAD-1", source="Website", minutes_ago=3)
        assert bdc.get_untouched_queue()[0]["urgency"] == "ok"

    def test_urgency_warning_between_thresholds(self):
        _add_lead("LEAD-1", source="Website", minutes_ago=20)
        assert bdc.get_untouched_queue()[0]["urgency"] == "warning"

    def test_urgency_critical_over_warning_threshold(self):
        _add_lead("LEAD-1", source="Website", minutes_ago=60)
        assert bdc.get_untouched_queue()[0]["urgency"] == "critical"

    def test_urgency_unknown_without_precise_timestamp(self):
        _add_lead("LEAD-1", source="Website")
        brief = bdc.get_untouched_queue()[0]
        assert brief["urgency"] == "unknown"
        assert brief["precise_timestamp"] is False

    def test_precise_timestamp_flag_true_when_created_at_present(self):
        _add_lead("LEAD-1", source="Website", minutes_ago=1)
        assert bdc.get_untouched_queue()[0]["precise_timestamp"] is True


# ---------------------------------------------------------------------------
# get_response_time_stats
# ---------------------------------------------------------------------------

class TestGetResponseTimeStats:
    def test_empty_when_no_leads(self):
        stats = bdc.get_response_time_stats()
        assert stats == {"sample_size": 0, "average_minutes": None, "under_target_pct": None}

    def test_empty_when_no_contact_logged(self):
        _add_lead("LEAD-1", source="Website", minutes_ago=30)
        stats = bdc.get_response_time_stats()
        assert stats["sample_size"] == 0

    def test_leads_without_created_at_are_excluded(self):
        lead_id = _add_lead("LEAD-1", source="Website")  # no CreatedAt
        _log_contact(lead_id, minutes_ago=0)
        stats = bdc.get_response_time_stats()
        assert stats["sample_size"] == 0

    def test_computes_a_real_delta(self):
        lead_id = _add_lead("LEAD-1", source="Website", minutes_ago=20)
        _log_contact(lead_id, minutes_ago=10)  # contacted 10 min ago, created 20 min ago -> ~10 min response

        stats = bdc.get_response_time_stats()
        assert stats["sample_size"] == 1
        assert 9.0 <= stats["average_minutes"] <= 11.0

    def test_under_target_pct_counts_responses_at_or_under_urgent_minutes(self):
        lead_a = _add_lead("LEAD-A", source="Website", minutes_ago=20)
        _log_contact(lead_a, minutes_ago=10)  # ~10 min response -> under 15

        lead_b = _add_lead("LEAD-B", source="Website", minutes_ago=60)
        _log_contact(lead_b, minutes_ago=10)  # ~50 min response -> over 15

        stats = bdc.get_response_time_stats()
        assert stats["sample_size"] == 2
        assert stats["under_target_pct"] == 50.0

    def test_ignores_a_negative_delta(self):
        # Contacted BEFORE the lead's own creation timestamp -- a real data-quality
        # defense, never counted.
        lead_id = _add_lead("LEAD-1", source="Website", minutes_ago=5)
        _log_contact(lead_id, minutes_ago=30)  # "contacted" 30 min ago, but lead only created 5 min ago

        stats = bdc.get_response_time_stats()
        assert stats["sample_size"] == 0

    def test_uses_the_first_contact_only(self):
        lead_id = _add_lead("LEAD-1", source="Website", minutes_ago=30)
        _log_contact(lead_id, category="text", minutes_ago=20)  # first, later
        _log_contact(lead_id, category="call", minutes_ago=25)  # actually earlier

        stats = bdc.get_response_time_stats()
        # first real contact is 25 min after creation start (30 -> 25 = 5 min response)
        assert 4.0 <= stats["average_minutes"] <= 6.0

    def test_ignores_non_communication_categories(self):
        lead_id = _add_lead("LEAD-1", source="Website", minutes_ago=20)
        note = create_field_note("Sales", "general", "Just a note", "EMP-1", linked_entity_id=lead_id)
        note.attributes["created_at"] = _iso_minutes_ago(10)

        stats = bdc.get_response_time_stats()
        assert stats["sample_size"] == 0

    def test_excludes_non_internet_sources(self):
        lead_id = _add_lead("LEAD-1", source="Referral", minutes_ago=20)
        _log_contact(lead_id, minutes_ago=10)
        stats = bdc.get_response_time_stats()
        assert stats["sample_size"] == 0


# ---------------------------------------------------------------------------
# get_qualification_queue / get_handoff_candidates
# ---------------------------------------------------------------------------

class TestQualificationAndHandoff:
    def test_qualification_queue_only_includes_contacted(self):
        _add_lead("LEAD-1", source="Website", pipeline_state="CONTACTED", minutes_ago=5)
        _add_lead("LEAD-2", source="Website", pipeline_state="NEW", minutes_ago=5)
        _add_lead("LEAD-3", source="Website", pipeline_state="APPOINTMENT_SET", minutes_ago=5)

        queue = bdc.get_qualification_queue()
        assert {b["id"] for b in queue} == {"LEAD-1"}

    def test_qualification_queue_excludes_non_internet_leads(self):
        _add_lead("LEAD-1", source="Referral", pipeline_state="CONTACTED", minutes_ago=5)
        assert bdc.get_qualification_queue() == []

    def test_handoff_candidates_includes_appointment_set_and_visited(self):
        _add_lead("LEAD-1", source="Website", pipeline_state="APPOINTMENT_SET", minutes_ago=5)
        _add_lead("LEAD-2", source="Autotrader", pipeline_state="VISITED", minutes_ago=5)
        _add_lead("LEAD-3", source="Website", pipeline_state="CONTACTED", minutes_ago=5)

        candidates = bdc.get_handoff_candidates()
        assert {b["id"] for b in candidates} == {"LEAD-1", "LEAD-2"}

    def test_handoff_candidates_excludes_non_internet_leads(self):
        _add_lead("LEAD-1", source="Referral", pipeline_state="VISITED", minutes_ago=5)
        assert bdc.get_handoff_candidates() == []


# ---------------------------------------------------------------------------
# get_bdc_dashboard
# ---------------------------------------------------------------------------

class TestGetBdcDashboard:
    def test_composes_the_real_sections(self):
        _add_lead("LEAD-1", source="Website", minutes_ago=5)
        dashboard = bdc.get_bdc_dashboard()

        assert dashboard["untouched_queue"]["count"] == 1
        assert "response_time" in dashboard
        assert dashboard["sla_thresholds"] == {"urgent_minutes": 15, "warning_minutes": 45}
        assert dashboard["internet_sources"] == ["Website", "Autotrader"]
        assert "not_yet_tracked" in dashboard


# ---------------------------------------------------------------------------
# ACL sweep -- core/bdc_api.py
# ---------------------------------------------------------------------------

class TestAcl:
    @pytest.mark.parametrize("role", _BDC_DENIED_ROLES)
    def test_get_bdc_dashboard_api_denied(self, role):
        result = bdc_api.get_bdc_dashboard_api(role)
        assert "error" in result

    @pytest.mark.parametrize("role", _BDC_ROLES)
    def test_get_bdc_dashboard_api_allowed(self, role):
        result = bdc_api.get_bdc_dashboard_api(role)
        assert "untouched_queue" in result

    @pytest.mark.parametrize("role", _BDC_DENIED_ROLES)
    def test_get_untouched_queue_api_denied(self, role):
        result = bdc_api.get_untouched_queue_api(role)
        assert "error" in result

    @pytest.mark.parametrize("role", _BDC_ROLES)
    def test_get_untouched_queue_api_allowed(self, role):
        result = bdc_api.get_untouched_queue_api(role)
        assert "count" in result and "leads" in result

    @pytest.mark.parametrize("role", _BDC_DENIED_ROLES)
    def test_get_qualification_queue_api_denied(self, role):
        result = bdc_api.get_qualification_queue_api(role)
        assert "error" in result

    @pytest.mark.parametrize("role", _BDC_ROLES)
    def test_get_qualification_queue_api_allowed(self, role):
        result = bdc_api.get_qualification_queue_api(role)
        assert "count" in result and "leads" in result

    @pytest.mark.parametrize("role", _BDC_DENIED_ROLES)
    def test_get_handoff_candidates_api_denied(self, role):
        result = bdc_api.get_handoff_candidates_api(role)
        assert "error" in result

    @pytest.mark.parametrize("role", _BDC_ROLES)
    def test_get_handoff_candidates_api_allowed(self, role):
        result = bdc_api.get_handoff_candidates_api(role)
        assert "count" in result and "leads" in result
