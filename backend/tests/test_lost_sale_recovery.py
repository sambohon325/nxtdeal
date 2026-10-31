import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import LEAD, CUSTOMER, DEAL, VEHICLE
from core import lost_sale_recovery
from core import lost_sale_recovery_api
from core import lead_workflows
from core import pipeline_state
from core import field_notes
from core import marketing_lists
from core.audit import audit_log
from core.permissions import ADMIN, OPERATIONS, SALES, FINANCE, MARKETING, SERVICE


LOST_REASON_CODES = lost_sale_recovery.LOST_REASON_CODES


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    monkeypatch.setattr(lost_sale_recovery, "save_graph", lambda filepath: None)
    monkeypatch.setattr(lead_workflows, "save_graph", lambda filepath: None)
    monkeypatch.setattr(pipeline_state, "save_graph", lambda filepath: None)
    monkeypatch.setattr(field_notes, "save_graph", lambda filepath: None)
    monkeypatch.setattr(marketing_lists, "save_graph", lambda filepath: None)


def make_lead(suffix="00001", **extra):
    attrs = {
        "FirstName": "John",
        "LastName": f"Prospect{suffix}",
        "Email": f"john{suffix}@example.com",
        "Phone": "555-0100",
        "Source": "Website",
        "AssignedSalesperson": "EMP-00001",
    }
    attrs.update(extra)
    entity = Entity(id=f"LEAD-{suffix}", entity_type=LEAD, attributes=attrs)
    ledger.add_entity(entity)
    return entity


def make_customer(suffix="00001", **extra):
    attrs = {
        "FirstName": "Jane",
        "LastName": f"Doe{suffix}",
        "Email": f"jane{suffix}@example.com",
        "Phone": "555-0200",
    }
    attrs.update(extra)
    entity = Entity(id=f"CUST-{suffix}", entity_type=CUSTOMER, attributes=attrs)
    ledger.add_entity(entity)
    return entity


def make_vehicle(suffix="00001", **extra):
    attrs = {"Year": 2022, "Make": "Ford", "Model": "F-150", "VIN": f"VIN{suffix}", "Price": 35000}
    attrs.update(extra)
    entity = Entity(id=f"VEH-{suffix}", entity_type=VEHICLE, attributes=attrs)
    ledger.add_entity(entity)
    return entity


def make_deal(suffix="00001", status="cancelled", customer_id=None, vehicle_id=None, **extra):
    attrs = {
        "status": status,
        "customer_id": customer_id,
        "vehicle_id": vehicle_id,
        "updated_at": "2026-07-01T00:00:00+00:00",
    }
    attrs.update(extra)
    entity = Entity(id=f"DEAL-{suffix}", entity_type=DEAL, attributes=attrs)
    ledger.add_entity(entity)
    return entity


def move_to_contacted(lead_id):
    lead_workflows.create_lead_workflow(lead_id)
    lead_workflows.advance_lead_workflow(lead_id, "CONTACTED")


def mark_lost(lead_id, reason="price", lost_by="EMP-00001"):
    move_to_contacted(lead_id)
    return lost_sale_recovery.mark_lead_lost(lead_id, reason, lost_by)


# ---------------------------------------------------------------------------
# LOST_REASON_CODES
# ---------------------------------------------------------------------------

class TestLostReasonCodes:

    def test_is_a_real_nonempty_list_of_strings(self):
        assert isinstance(LOST_REASON_CODES, list)
        assert len(LOST_REASON_CODES) > 0
        assert all(isinstance(code, str) for code in LOST_REASON_CODES)

    def test_contains_the_documented_codes(self):
        for code in [
            "price", "financing_declined", "lost_to_competitor",
            "went_with_another_dealer", "changed_mind", "credit_issue",
            "trade_value_disagreement", "no_response",
            "vehicle_no_longer_available", "other",
        ]:
            assert code in LOST_REASON_CODES


# ---------------------------------------------------------------------------
# get_lost_leads / get_cancelled_deals
# ---------------------------------------------------------------------------

class TestGetLostLeads:

    def test_empty_when_no_lost_leads_exist(self):
        make_lead("00001")
        assert lost_sale_recovery.get_lost_leads() == []

    def test_only_includes_leads_in_the_lost_pipeline_state(self):
        lead_a = make_lead("00001")
        mark_lost(lead_a.id)

        make_lead("00002")  # never touched -- stays NEW

        result = lost_sale_recovery.get_lost_leads()
        assert len(result) == 1
        assert result[0]["id"] == lead_a.id

    def test_sorted_most_recently_lost_first(self):
        lead_a = make_lead("00001")
        mark_lost(lead_a.id)
        lead_a.attributes["LostAt"] = "2026-01-01T00:00:00+00:00"

        lead_b = make_lead("00002")
        mark_lost(lead_b.id)
        lead_b.attributes["LostAt"] = "2026-06-01T00:00:00+00:00"

        result = lost_sale_recovery.get_lost_leads()
        assert [r["id"] for r in result] == [lead_b.id, lead_a.id]

    def test_falls_back_to_pipeline_state_since_when_lost_at_missing(self):
        lead_a = make_lead("00001")
        mark_lost(lead_a.id)
        lead_a.attributes["LostAt"] = None
        lead_a.attributes["PipelineStateSince"] = "2026-02-01T00:00:00+00:00"

        lead_b = make_lead("00002")
        mark_lost(lead_b.id)
        lead_b.attributes["LostAt"] = None
        lead_b.attributes["PipelineStateSince"] = "2026-05-01T00:00:00+00:00"

        result = lost_sale_recovery.get_lost_leads()
        assert [r["id"] for r in result] == [lead_b.id, lead_a.id]

    def test_respects_limit(self):
        for i in range(5):
            lead = make_lead(f"{i:05}")
            mark_lost(lead.id)

        assert len(lost_sale_recovery.get_lost_leads(limit=2)) == 2
        assert len(lost_sale_recovery.get_lost_leads(limit=50)) == 5

    def test_brief_shape(self):
        lead = make_lead("00001")
        mark_lost(lead.id, reason="credit_issue")

        result = lost_sale_recovery.get_lost_leads()[0]
        assert result["id"] == lead.id
        assert result["name"] == "John Prospect00001"
        assert result["email"] == "john00001@example.com"
        assert result["phone"] == "555-0100"
        assert result["source"] == "Website"
        assert result["assigned_salesperson"] == "EMP-00001"
        assert result["lost_reason"] == "credit_issue"
        assert result["lost_at"] is not None
        assert result["lost_by"] == "EMP-00001"
        assert result["previous_lost_reasons"] == []
        assert result["converted_customer"] is None


class TestGetCancelledDeals:

    def test_empty_when_no_cancelled_deals_exist(self):
        make_deal("00001", status="funded")
        assert lost_sale_recovery.get_cancelled_deals() == []

    def test_only_includes_cancelled_status(self):
        cancelled = make_deal("00001", status="cancelled")
        make_deal("00002", status="funded")
        make_deal("00003", status="desking")

        result = lost_sale_recovery.get_cancelled_deals()
        assert len(result) == 1
        assert result[0]["id"] == cancelled.id

    def test_sorted_most_recently_cancelled_first(self):
        deal_a = make_deal("00001", status="cancelled", updated_at="2026-01-01T00:00:00+00:00")
        deal_b = make_deal("00002", status="cancelled", updated_at="2026-06-01T00:00:00+00:00")

        result = lost_sale_recovery.get_cancelled_deals()
        assert [r["id"] for r in result] == [deal_b.id, deal_a.id]

    def test_respects_limit(self):
        for i in range(5):
            make_deal(f"{i:05}", status="cancelled")

        assert len(lost_sale_recovery.get_cancelled_deals(limit=2)) == 2
        assert len(lost_sale_recovery.get_cancelled_deals(limit=50)) == 5

    def test_brief_shape_with_linked_customer_and_vehicle(self):
        customer = make_customer("00001")
        vehicle = make_vehicle("00001")
        deal = make_deal(
            "00001", status="cancelled",
            customer_id=customer.id, vehicle_id=vehicle.id,
            cancel_reason="price", cancel_reason_by="EMP-00002",
            cancel_reason_at="2026-07-02T00:00:00+00:00",
        )

        result = lost_sale_recovery.get_cancelled_deals()[0]
        assert result["id"] == deal.id
        assert result["status"] == "cancelled"
        assert result["cancelled_at"] == "2026-07-01T00:00:00+00:00"
        assert result["cancel_reason"] == "price"
        assert result["cancel_reason_by"] == "EMP-00002"
        assert result["cancel_reason_at"] == "2026-07-02T00:00:00+00:00"
        assert result["customer"]["id"] == customer.id
        assert result["customer"]["name"] == "Jane Doe00001"
        assert result["vehicle"]["id"] == vehicle.id
        assert result["vehicle"]["description"] == "2022 Ford F-150"

    def test_brief_with_no_linked_customer_or_vehicle(self):
        make_deal("00001", status="cancelled")

        result = lost_sale_recovery.get_cancelled_deals()[0]
        assert result["customer"] is None
        assert result["vehicle"] is None


# ---------------------------------------------------------------------------
# mark_lead_lost
# ---------------------------------------------------------------------------

class TestMarkLeadLost:

    def test_unknown_reason_code_rejected(self):
        lead = make_lead("00001")
        move_to_contacted(lead.id)

        result = lost_sale_recovery.mark_lead_lost(lead.id, "not_a_real_code", "EMP-00001")
        assert "error" in result
        assert "Unknown reason code" in result["error"]

    def test_lead_not_found(self):
        result = lost_sale_recovery.mark_lead_lost("LEAD-99999", "price", "EMP-00001")
        assert result == {"error": "Lead not found"}

    def test_wrong_entity_type_rejected(self):
        customer = make_customer("00001")
        result = lost_sale_recovery.mark_lead_lost(customer.id, "price", "EMP-00001")
        assert result == {"error": "Lead not found"}

    def test_lead_still_at_new_rejects_direct_transition_to_lost(self):
        lead = make_lead("00001")
        lead_workflows.create_lead_workflow(lead.id)  # sets PipelineState=NEW, never advances

        result = lost_sale_recovery.mark_lead_lost(lead.id, "price", "EMP-00001")
        assert result == {"error": "Invalid transition: NEW -> LOST"}

    def test_lead_with_no_pipeline_state_at_all_rejected(self):
        lead = make_lead("00001")  # never entered the workflow at all

        result = lost_sale_recovery.mark_lead_lost(lead.id, "price", "EMP-00001")
        assert result == {"error": f"No workflow found for {lead.id}"}

    def test_happy_path_stamps_reason_and_moves_to_lost(self):
        lead = make_lead("00001")
        move_to_contacted(lead.id)

        result = lost_sale_recovery.mark_lead_lost(lead.id, "financing_declined", "EMP-00007")

        assert "error" not in result
        assert result["id"] == lead.id
        assert result["lost_reason"] == "financing_declined"
        assert result["lost_by"] == "EMP-00007"
        assert result["lost_at"] is not None
        assert lead.attributes["PipelineState"] == "LOST"
        assert pipeline_state.get_pipeline_state(lead.id) == "LOST"

    def test_can_mark_lost_from_any_valid_pre_lost_state(self):
        # PROPOSAL -> LOST is a valid transition per LEAD_WORKFLOW
        lead = make_lead("00001")
        lead_workflows.create_lead_workflow(lead.id)
        for state in ("CONTACTED", "APPOINTMENT_SET", "VISITED", "PROPOSAL"):
            lead_workflows.advance_lead_workflow(lead.id, state)

        result = lost_sale_recovery.mark_lead_lost(lead.id, "other", "EMP-00001")
        assert "error" not in result
        assert result["lost_reason"] == "other"


# ---------------------------------------------------------------------------
# record_deal_lost_reason
# ---------------------------------------------------------------------------

class TestRecordDealLostReason:

    def test_deal_not_found(self):
        result = lost_sale_recovery.record_deal_lost_reason("DEAL-99999", "price", "EMP-00001")
        assert result == {"error": "Deal not found"}

    def test_wrong_entity_type_rejected(self):
        lead = make_lead("00001")
        result = lost_sale_recovery.record_deal_lost_reason(lead.id, "price", "EMP-00001")
        assert result == {"error": "Deal not found"}

    def test_deal_not_cancelled_rejected_with_status_in_message(self):
        deal = make_deal("00001", status="funded")
        result = lost_sale_recovery.record_deal_lost_reason(deal.id, "price", "EMP-00001")
        assert result == {
            "error": "Deal is 'funded' -- a lost-sale reason can only be recorded on a cancelled deal"
        }

    def test_deal_at_desking_status_rejected(self):
        deal = make_deal("00001", status="desking")
        result = lost_sale_recovery.record_deal_lost_reason(deal.id, "price", "EMP-00001")
        assert "desking" in result["error"]

    def test_does_not_validate_reason_against_the_reason_code_catalog(self):
        # Unlike mark_lead_lost, this function accepts any reason string.
        deal = make_deal("00001", status="cancelled")
        result = lost_sale_recovery.record_deal_lost_reason(deal.id, "totally_made_up_reason", "EMP-00001")
        assert "error" not in result
        assert result["cancel_reason"] == "totally_made_up_reason"

    def test_happy_path_stamps_reason(self):
        deal = make_deal("00001", status="cancelled")

        result = lost_sale_recovery.record_deal_lost_reason(deal.id, "lost_to_competitor", "EMP-00003")

        assert "error" not in result
        assert result["cancel_reason"] == "lost_to_competitor"
        assert result["cancel_reason_by"] == "EMP-00003"
        assert result["cancel_reason_at"] is not None
        assert deal.attributes["cancel_reason"] == "lost_to_competitor"

    def test_can_be_recorded_any_time_after_the_fact_and_overwritten(self):
        deal = make_deal("00001", status="cancelled")

        lost_sale_recovery.record_deal_lost_reason(deal.id, "price", "EMP-00001")
        second = lost_sale_recovery.record_deal_lost_reason(deal.id, "changed_mind", "EMP-00002")

        assert second["cancel_reason"] == "changed_mind"
        assert second["cancel_reason_by"] == "EMP-00002"


# ---------------------------------------------------------------------------
# reactivate_lost_lead
# ---------------------------------------------------------------------------

class TestReactivateLostLead:

    def test_lead_not_found(self):
        result = lost_sale_recovery.reactivate_lost_lead("LEAD-99999", "EMP-00001")
        assert result == {"error": "Lead not found"}

    def test_wrong_entity_type_rejected(self):
        customer = make_customer("00001")
        result = lost_sale_recovery.reactivate_lost_lead(customer.id, "EMP-00001")
        assert result == {"error": "Lead not found"}

    def test_lead_not_currently_lost_rejected(self):
        lead = make_lead("00001")
        move_to_contacted(lead.id)  # currently CONTACTED, not LOST

        result = lost_sale_recovery.reactivate_lost_lead(lead.id, "EMP-00001")
        assert result == {"error": "Lead is not currently in the LOST state"}

    def test_lead_never_entered_pipeline_rejected(self):
        lead = make_lead("00001")
        result = lost_sale_recovery.reactivate_lost_lead(lead.id, "EMP-00001")
        assert result == {"error": "Lead is not currently in the LOST state"}

    def test_happy_path_moves_back_to_contacted_and_clears_reason(self):
        lead = make_lead("00001")
        mark_lost(lead.id, reason="price", lost_by="EMP-00001")

        result = lost_sale_recovery.reactivate_lost_lead(lead.id, "EMP-00002")

        assert "error" not in result
        assert result["lost_reason"] is None
        assert result["lost_at"] is None
        assert result["lost_by"] is None
        assert lead.attributes["PipelineState"] == "CONTACTED"
        assert pipeline_state.get_pipeline_state(lead.id) == "CONTACTED"

    def test_prior_reason_preserved_in_previous_lost_reasons_history(self):
        lead = make_lead("00001")
        mark_lost(lead.id, reason="price", lost_by="EMP-00001")

        result = lost_sale_recovery.reactivate_lost_lead(lead.id, "EMP-00002")

        history = result["previous_lost_reasons"]
        assert len(history) == 1
        assert history[0]["reason"] == "price"
        assert history[0]["lost_by"] == "EMP-00001"
        assert history[0]["reactivated_by"] == "EMP-00002"
        assert history[0]["lost_at"] is not None
        assert history[0]["reactivated_at"] is not None

    def test_can_be_lost_and_reactivated_more_than_once(self):
        lead = make_lead("00001")
        mark_lost(lead.id, reason="price", lost_by="EMP-00001")
        lost_sale_recovery.reactivate_lost_lead(lead.id, "EMP-00002")

        # advance back through the funnel and lose it again
        lead_workflows.advance_lead_workflow(lead.id, "APPOINTMENT_SET")
        lost_sale_recovery.mark_lead_lost(lead.id, "changed_mind", "EMP-00003")

        result = lost_sale_recovery.reactivate_lost_lead(lead.id, "EMP-00004")

        history = result["previous_lost_reasons"]
        assert len(history) == 2
        assert history[0]["reason"] == "price"
        assert history[1]["reason"] == "changed_mind"

    def test_no_history_appended_when_no_prior_reason_was_ever_captured(self):
        # A lead reaching LOST without ever going through mark_lead_lost (e.g. legacy
        # data predating this feature) has no LostReason at all.
        lead = make_lead("00001")
        lead_workflows.create_lead_workflow(lead.id)
        lead_workflows.advance_lead_workflow(lead.id, "CONTACTED")
        lead_workflows.advance_lead_workflow(lead.id, "LOST")

        result = lost_sale_recovery.reactivate_lost_lead(lead.id, "EMP-00001")

        assert "error" not in result
        assert result["previous_lost_reasons"] == []
        assert "PreviousLostReasons" not in lead.attributes

    def test_records_a_real_lead_reactivated_audit_event(self):
        # NOTE: audit_log is a module-level singleton not reset between tests
        # (only the ledger is, via the fresh_ledger fixture), so entity ids reused
        # across tests in this file can accumulate prior events -- assert against
        # the MOST RECENT matching event rather than an exact count.
        lead = make_lead("00001")
        mark_lost(lead.id, reason="price", lost_by="EMP-00001")

        lost_sale_recovery.reactivate_lost_lead(lead.id, "EMP-00002", note="Called and won them back")

        events = audit_log.get_for_entity(lead.id)
        reactivation_events = [e for e in events if e.event_type == "lead_reactivated"]
        assert len(reactivation_events) >= 1
        last = reactivation_events[-1]
        assert last.actor == "EMP-00002"
        assert last.details["from"] == "LOST"
        assert last.details["to"] == "CONTACTED"
        assert last.details["prior_reason"] == "price"
        assert last.details["note"] == "Called and won them back"

    def test_note_creates_a_real_recovery_attempt_field_note(self):
        lead = make_lead("00001")
        mark_lost(lead.id, reason="price", lost_by="EMP-00001")

        lost_sale_recovery.reactivate_lost_lead(lead.id, "EMP-00002", note="Won them back with a rebate")

        attempts = lost_sale_recovery.list_recovery_attempts(lead.id)
        assert len(attempts) == 1
        assert attempts[0]["body"] == "Won them back with a rebate"
        assert attempts[0]["created_by"] == "EMP-00002"

    def test_no_note_creates_no_field_note(self):
        lead = make_lead("00001")
        mark_lost(lead.id, reason="price", lost_by="EMP-00001")

        lost_sale_recovery.reactivate_lost_lead(lead.id, "EMP-00002")

        assert lost_sale_recovery.list_recovery_attempts(lead.id) == []


# ---------------------------------------------------------------------------
# log_recovery_attempt / list_recovery_attempts
# ---------------------------------------------------------------------------

class TestLogRecoveryAttempt:

    def test_entity_not_found_rejected(self):
        result = lost_sale_recovery.log_recovery_attempt("LEAD-99999", LEAD, "note", "EMP-00001")
        assert result == {"error": "Entity must be a real Lead or Deal id"}

    def test_wrong_entity_type_rejected(self):
        vehicle = make_vehicle("00001")
        result = lost_sale_recovery.log_recovery_attempt(vehicle.id, VEHICLE, "note", "EMP-00001")
        assert result == {"error": "Entity must be a real Lead or Deal id"}

    def test_happy_path_against_a_lead(self):
        lead = make_lead("00001")

        result = lost_sale_recovery.log_recovery_attempt(lead.id, LEAD, "Left a voicemail", "EMP-00001")

        assert "error" not in result
        assert result["entity_id"] == lead.id
        assert result["entity_type"] == LEAD
        assert result["body"] == "Left a voicemail"
        assert result["created_by"] == "EMP-00001"
        assert result["created_at"] is not None
        assert result["id"] is not None

    def test_happy_path_against_a_deal(self):
        deal = make_deal("00001", status="cancelled")

        result = lost_sale_recovery.log_recovery_attempt(deal.id, DEAL, "Sent a follow-up email", "EMP-00002")

        assert "error" not in result
        assert result["entity_id"] == deal.id
        assert result["entity_type"] == DEAL

    def test_department_is_always_sales_regardless_of_entity_type_param(self):
        lead = make_lead("00001")
        lost_sale_recovery.log_recovery_attempt(lead.id, DEAL, "note", "EMP-00001")

        notes = field_notes.list_field_notes(linked_entity_id=lead.id)
        assert len(notes) == 1
        assert notes[0].attributes["department"] == "Sales"

    def test_entity_type_param_is_ignored_and_real_entity_type_is_returned(self):
        # entity_id points at a real Lead, but the caller passes the wrong entity_type;
        # the function should still succeed and report the REAL type, not the param.
        lead = make_lead("00001")

        result = lost_sale_recovery.log_recovery_attempt(lead.id, CUSTOMER, "note", "EMP-00001")

        assert "error" not in result
        assert result["entity_type"] == LEAD

    def test_creates_a_field_note_in_the_recovery_attempt_category(self):
        lead = make_lead("00001")
        lost_sale_recovery.log_recovery_attempt(lead.id, LEAD, "note", "EMP-00001")

        notes = field_notes.list_field_notes(linked_entity_id=lead.id)
        assert len(notes) == 1
        assert notes[0].attributes["category"] == "recovery_attempt"


class TestListRecoveryAttempts:

    def test_empty_when_none_exist(self):
        lead = make_lead("00001")
        assert lost_sale_recovery.list_recovery_attempts(lead.id) == []

    def test_excludes_other_categories_on_the_same_entity(self):
        lead = make_lead("00001")
        lost_sale_recovery.log_recovery_attempt(lead.id, LEAD, "a real recovery note", "EMP-00001")
        field_notes.create_field_note(
            department="Sales", category="call", body="unrelated call log",
            created_by="EMP-00001", linked_entity_id=lead.id,
        )

        result = lost_sale_recovery.list_recovery_attempts(lead.id)
        assert len(result) == 1
        assert result[0]["body"] == "a real recovery note"

    def test_excludes_notes_linked_to_a_different_entity(self):
        lead_a = make_lead("00001")
        lead_b = make_lead("00002")
        lost_sale_recovery.log_recovery_attempt(lead_a.id, LEAD, "note for A", "EMP-00001")
        lost_sale_recovery.log_recovery_attempt(lead_b.id, LEAD, "note for B", "EMP-00001")

        result_a = lost_sale_recovery.list_recovery_attempts(lead_a.id)
        assert len(result_a) == 1
        assert result_a[0]["body"] == "note for A"

    def test_shape_of_each_entry(self):
        lead = make_lead("00001")
        lost_sale_recovery.log_recovery_attempt(lead.id, LEAD, "note", "EMP-00009")

        entry = lost_sale_recovery.list_recovery_attempts(lead.id)[0]
        assert set(entry.keys()) == {"id", "body", "created_by", "created_at"}
        assert entry["created_by"] == "EMP-00009"


# ---------------------------------------------------------------------------
# save_recovery_pool_as_list
# ---------------------------------------------------------------------------

class TestSaveRecoveryPoolAsList:

    def test_bad_source_rejected(self):
        result = lost_sale_recovery.save_recovery_pool_as_list("Pool", "EMP-00001", "not_a_real_source")
        assert result == {"error": "source must be 'lost_leads' or 'cancelled_deals'"}

    def test_lost_leads_source_includes_only_lost_leads(self):
        lead_a = make_lead("00001")
        mark_lost(lead_a.id)
        lead_b = make_lead("00002")
        mark_lost(lead_b.id)
        make_lead("00003")  # not lost -- should be excluded

        result = lost_sale_recovery.save_recovery_pool_as_list(
            "Win-Back Pool", "EMP-00001", "lost_leads",
        )

        assert "error" not in result
        assert result["source"] == "lost_leads"
        assert result["requested"] == 2
        assert result["added"] == 2

        saved_list = marketing_lists.get_list(result["list_id"])
        assert set(saved_list.attributes["member_ids"]) == {lead_a.id, lead_b.id}

    def test_cancelled_deals_source_resolves_and_dedupes_customer_ids(self):
        customer_a = make_customer("00001")
        customer_b = make_customer("00002")

        # two cancelled deals sharing the same customer -- should dedupe to one
        make_deal("00001", status="cancelled", customer_id=customer_a.id)
        make_deal("00002", status="cancelled", customer_id=customer_a.id)
        # a distinct customer
        make_deal("00003", status="cancelled", customer_id=customer_b.id)
        # a cancelled deal with no customer_id at all -- excluded
        make_deal("00004", status="cancelled", customer_id=None)
        # a non-cancelled deal -- excluded entirely
        make_deal("00005", status="funded", customer_id=customer_a.id)

        result = lost_sale_recovery.save_recovery_pool_as_list(
            "Win-Back Pool", "EMP-00001", "cancelled_deals",
        )

        assert result["source"] == "cancelled_deals"
        assert result["requested"] == 2
        assert result["added"] == 2

        saved_list = marketing_lists.get_list(result["list_id"])
        assert set(saved_list.attributes["member_ids"]) == {customer_a.id, customer_b.id}

    def test_cancelled_deal_pointing_at_a_nonexistent_customer_is_requested_but_not_added(self):
        make_deal("00001", status="cancelled", customer_id="CUST-99999")

        result = lost_sale_recovery.save_recovery_pool_as_list(
            "Win-Back Pool", "EMP-00001", "cancelled_deals",
        )

        assert result["requested"] == 1
        assert result["added"] == 0

    def test_default_description_names_the_source(self):
        result = lost_sale_recovery.save_recovery_pool_as_list(
            "Win-Back Pool", "EMP-00001", "lost_leads",
        )
        saved_list = marketing_lists.get_list(result["list_id"])
        assert "Lost Sale Recovery" in saved_list.attributes["description"]
        assert "lost_leads" in saved_list.attributes["description"]

    def test_custom_description_is_honored(self):
        result = lost_sale_recovery.save_recovery_pool_as_list(
            "Win-Back Pool", "EMP-00001", "lost_leads", description="A custom description",
        )
        saved_list = marketing_lists.get_list(result["list_id"])
        assert saved_list.attributes["description"] == "A custom description"

    def test_empty_pool_still_creates_a_list_with_zero_members(self):
        result = lost_sale_recovery.save_recovery_pool_as_list(
            "Empty Pool", "EMP-00001", "lost_leads",
        )
        assert result["requested"] == 0
        assert result["added"] == 0
        saved_list = marketing_lists.get_list(result["list_id"])
        assert saved_list.attributes["member_ids"] == []


# ---------------------------------------------------------------------------
# get_lost_sale_stats
# ---------------------------------------------------------------------------

class TestGetLostSaleStats:

    def test_empty_state(self):
        stats = lost_sale_recovery.get_lost_sale_stats()
        assert stats["total_lost_leads"] == 0
        assert stats["total_cancelled_deals"] == 0
        assert stats["lost_lead_reasons"] == {}
        assert stats["cancelled_deal_reasons"] == {}
        assert stats["recovery_rate_pct"] is None
        assert stats["leads_ever_lost"] == 0
        assert stats["leads_reactivated"] == 0

    def test_total_counts(self):
        lead_a = make_lead("00001")
        mark_lost(lead_a.id)
        lead_b = make_lead("00002")
        mark_lost(lead_b.id)
        make_deal("00001", status="cancelled")
        make_deal("00002", status="funded")

        stats = lost_sale_recovery.get_lost_sale_stats()
        assert stats["total_lost_leads"] == 2
        assert stats["total_cancelled_deals"] == 1

    def test_lost_lead_reason_breakdown_with_not_recorded_bucket(self):
        lead_a = make_lead("00001")
        mark_lost(lead_a.id, reason="price")
        lead_b = make_lead("00002")
        mark_lost(lead_b.id, reason="price")
        lead_c = make_lead("00003")
        # bypass mark_lead_lost entirely -- legacy data with no reason captured
        lead_workflows.create_lead_workflow(lead_c.id)
        lead_workflows.advance_lead_workflow(lead_c.id, "CONTACTED")
        lead_workflows.advance_lead_workflow(lead_c.id, "LOST")

        stats = lost_sale_recovery.get_lost_sale_stats()
        assert stats["lost_lead_reasons"] == {"price": 2, "not_recorded": 1}

    def test_cancelled_deal_reason_breakdown_with_not_recorded_bucket(self):
        deal_a = make_deal("00001", status="cancelled")
        lost_sale_recovery.record_deal_lost_reason(deal_a.id, "price", "EMP-00001")
        make_deal("00002", status="cancelled")  # reason never recorded

        stats = lost_sale_recovery.get_lost_sale_stats()
        assert stats["cancelled_deal_reasons"] == {"price": 1, "not_recorded": 1}

    def test_recovery_rate_computed_over_ever_lost_leads_only(self):
        # lead A: lost then reactivated -- counts toward both ever_lost and reactivated
        lead_a = make_lead("00001")
        mark_lost(lead_a.id, reason="price")
        lost_sale_recovery.reactivate_lost_lead(lead_a.id, "EMP-00002")

        # lead B: still lost, never reactivated -- counts toward ever_lost only
        lead_b = make_lead("00002")
        mark_lost(lead_b.id, reason="price")

        # lead C: never touched at all -- should not affect the rate either way
        make_lead("00003")

        stats = lost_sale_recovery.get_lost_sale_stats()
        assert stats["leads_ever_lost"] == 2
        assert stats["leads_reactivated"] == 1
        assert stats["recovery_rate_pct"] == 50.0

    def test_recovery_rate_is_none_when_nobody_has_ever_been_lost(self):
        make_lead("00001")
        make_deal("00001", status="funded")

        stats = lost_sale_recovery.get_lost_sale_stats()
        assert stats["recovery_rate_pct"] is None


# ---------------------------------------------------------------------------
# Brief helpers -- direct edge-case coverage
# ---------------------------------------------------------------------------

class TestBriefHelpers:

    def test_customer_brief_none_for_missing_id(self):
        assert lost_sale_recovery._customer_brief(None) is None
        assert lost_sale_recovery._customer_brief("") is None
        assert lost_sale_recovery._customer_brief("CUST-99999") is None

    def test_customer_brief_none_for_wrong_entity_type(self):
        lead = make_lead("00001")
        assert lost_sale_recovery._customer_brief(lead.id) is None

    def test_vehicle_brief_none_for_missing_id(self):
        assert lost_sale_recovery._vehicle_brief(None) is None
        assert lost_sale_recovery._vehicle_brief("VEH-99999") is None

    def test_vehicle_brief_none_for_wrong_entity_type(self):
        customer = make_customer("00001")
        assert lost_sale_recovery._vehicle_brief(customer.id) is None

    def test_lead_brief_falls_back_to_id_when_no_name_on_file(self):
        lead = Entity(id="LEAD-00099", entity_type=LEAD, attributes={})
        ledger.add_entity(lead)
        brief = lost_sale_recovery._lead_brief(lead)
        assert brief["name"] == "LEAD-00099"


# ---------------------------------------------------------------------------
# lost_sale_recovery_api -- ACL sweep
# ---------------------------------------------------------------------------

_VIEW_ALLOWED = [ADMIN, OPERATIONS, SALES, MARKETING]
_VIEW_DENIED = [FINANCE, SERVICE, "BOGUS_ROLE", None, ""]
_ACTION_ALLOWED = [ADMIN, OPERATIONS, SALES]
_ACTION_DENIED = [MARKETING, FINANCE, SERVICE, "BOGUS_ROLE", None, ""]


class TestApiAcl:

    def test_get_lost_reason_codes_api(self):
        for role in _VIEW_ALLOWED:
            assert lost_sale_recovery_api.get_lost_reason_codes_api(role) == LOST_REASON_CODES
        for role in _VIEW_DENIED:
            assert lost_sale_recovery_api.get_lost_reason_codes_api(role) == {
                "error": "You don't have access to Lost Sale Recovery"
            }

    def test_get_lost_leads_api(self):
        for role in _VIEW_ALLOWED:
            assert lost_sale_recovery_api.get_lost_leads_api(role) == []
        for role in _VIEW_DENIED:
            assert lost_sale_recovery_api.get_lost_leads_api(role) == {
                "error": "You don't have access to Lost Sale Recovery"
            }

    def test_get_cancelled_deals_api(self):
        for role in _VIEW_ALLOWED:
            assert lost_sale_recovery_api.get_cancelled_deals_api(role) == []
        for role in _VIEW_DENIED:
            assert lost_sale_recovery_api.get_cancelled_deals_api(role) == {
                "error": "You don't have access to Lost Sale Recovery"
            }

    def test_list_recovery_attempts_api(self):
        lead = make_lead("00001")
        for role in _VIEW_ALLOWED:
            assert lost_sale_recovery_api.list_recovery_attempts_api(role, lead.id) == []
        for role in _VIEW_DENIED:
            assert lost_sale_recovery_api.list_recovery_attempts_api(role, lead.id) == {
                "error": "You don't have access to Lost Sale Recovery"
            }

    def test_save_recovery_pool_as_list_api_allows_marketing(self):
        for role in _VIEW_ALLOWED:
            result = lost_sale_recovery_api.save_recovery_pool_as_list_api(
                role, "EMP-00001", f"Pool for {role}", "lost_leads",
            )
            assert "error" not in result
        for role in _VIEW_DENIED:
            assert lost_sale_recovery_api.save_recovery_pool_as_list_api(
                role, "EMP-00001", "Pool", "lost_leads",
            ) == {"error": "You don't have access to Lost Sale Recovery"}

    def test_get_lost_sale_stats_api(self):
        for role in _VIEW_ALLOWED:
            stats = lost_sale_recovery_api.get_lost_sale_stats_api(role)
            assert "total_lost_leads" in stats
        for role in _VIEW_DENIED:
            assert lost_sale_recovery_api.get_lost_sale_stats_api(role) == {
                "error": "You don't have access to Lost Sale Recovery reporting"
            }

    def test_get_lost_sale_recovery_dashboard_api(self):
        for role in _VIEW_ALLOWED:
            dash = lost_sale_recovery_api.get_lost_sale_recovery_dashboard_api(role)
            assert set(dash.keys()) == {"reason_codes", "lost_leads", "cancelled_deals", "stats"}
        for role in _VIEW_DENIED:
            assert lost_sale_recovery_api.get_lost_sale_recovery_dashboard_api(role) == {
                "error": "You don't have access to the Lost Sale Recovery dashboard"
            }

    @pytest.mark.parametrize("role", _ACTION_ALLOWED)
    def test_action_apis_succeed_for_allowed_roles(self, role):
        lead = make_lead("90001")
        move_to_contacted(lead.id)

        result = lost_sale_recovery_api.mark_lead_lost_api(role, "EMP-00001", lead.id, "price")
        assert "error" not in result
        assert result["lost_reason"] == "price"

        deal = make_deal("90001", status="cancelled")
        result = lost_sale_recovery_api.record_deal_lost_reason_api(role, "EMP-00001", deal.id, "price")
        assert "error" not in result
        assert result["cancel_reason"] == "price"

        result = lost_sale_recovery_api.reactivate_lost_lead_api(role, "EMP-00001", lead.id, note="won back")
        assert "error" not in result
        assert result["lost_reason"] is None

        result = lost_sale_recovery_api.log_recovery_attempt_api(role, "EMP-00001", lead.id, LEAD, "called them")
        assert "error" not in result
        assert result["body"] == "called them"

    @pytest.mark.parametrize("role", _ACTION_DENIED)
    def test_action_apis_denied_for_disallowed_roles(self, role):
        lead = make_lead("90002")
        deal = make_deal("90002", status="cancelled")

        assert lost_sale_recovery_api.mark_lead_lost_api(role, "EMP-00001", lead.id, "price") == {
            "error": "Only Sales/Operations/Admin can mark a lead lost"
        }
        assert lost_sale_recovery_api.record_deal_lost_reason_api(role, "EMP-00001", deal.id, "price") == {
            "error": "Only Sales/Operations/Admin can record a cancelled deal's lost-sale reason"
        }
        assert lost_sale_recovery_api.reactivate_lost_lead_api(role, "EMP-00001", lead.id) == {
            "error": "Only Sales/Operations/Admin can reactivate a lost lead"
        }
        assert lost_sale_recovery_api.log_recovery_attempt_api(role, "EMP-00001", lead.id, LEAD, "note") == {
            "error": "Only Sales/Operations/Admin can log a recovery attempt"
        }

    def test_marketing_is_denied_every_action_but_allowed_every_view(self):
        lead = make_lead("90003")
        deal = make_deal("90003", status="cancelled")

        assert "error" in lost_sale_recovery_api.mark_lead_lost_api(MARKETING, "EMP-00001", lead.id, "price")
        assert "error" in lost_sale_recovery_api.record_deal_lost_reason_api(MARKETING, "EMP-00001", deal.id, "price")
        assert "error" in lost_sale_recovery_api.reactivate_lost_lead_api(MARKETING, "EMP-00001", lead.id)
        assert "error" in lost_sale_recovery_api.log_recovery_attempt_api(MARKETING, "EMP-00001", lead.id, LEAD, "note")

        # Viewing (including the cancelled-deals queue itself) is allowed for MARKETING --
        # only the mutating actions above are denied.
        leads_result = lost_sale_recovery_api.get_lost_leads_api(MARKETING)
        assert isinstance(leads_result, list)

        deals_result = lost_sale_recovery_api.get_cancelled_deals_api(MARKETING)
        assert isinstance(deals_result, list)
        assert any(d["id"] == deal.id for d in deals_result)

        assert "error" not in lost_sale_recovery_api.save_recovery_pool_as_list_api(
            MARKETING, "EMP-00001", "Marketing Pool", "lost_leads",
        )
