import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.relationships import Relationship
from core.entity_types import (
    CUSTOMER,
    LEAD,
    CAMPAIGN,
    EVENT_RSVP,
    WEBSITE_CHAT_SESSION,
    DEAL,
    FIELD_NOTE,
    TRIGGER_ALERT,
    CREDIT_APPLICATION,
    PERSONALIZED_URL,
    SERVICE_RECORD,
    FINANCE_CONTRACT,
    VEHICLE,
    PERMISSION_OVERRIDE,
    EMPLOYEE,
)
from core.relationship_types import BECAME, GENERATED_LEAD, AUTHORIZED, FINANCED_BY, OWNS
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE

from core import customer_360
from core import customer_360_api


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


# customer_360.py makes no graph mutations of its own -- a pure read/composition
# module (confirmed via source read, zero save_graph import). No monkeypatch is
# needed for the module itself; nothing else in this test file triggers a save
# either, since we hand-construct every fixture entity directly via ledger.add_entity
# rather than calling through any other module's own mutating create_* functions.


ALL_ROLES = (ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE)


def _add_entity(entity_id, entity_type, **attrs):
    entity = Entity(id=entity_id, entity_type=entity_type, attributes=attrs)
    ledger.add_entity(entity)
    return entity


def _add_customer(customer_id="CUST-1", **overrides):
    attrs = {
        "FirstName": "Jane",
        "LastName": "Doe",
        "Email": "jane@example.com",
        "Phone": "555-0100",
        "CreditScore": "720",
    }
    attrs.update(overrides)
    return _add_entity(customer_id, CUSTOMER, **attrs)


def _add_lead(lead_id="LEAD-1", **overrides):
    attrs = {
        "Source": "Website",
        "PipelineState": "NEW",
        "CreatedAt": "2026-01-01T00:00:00+00:00",
    }
    attrs.update(overrides)
    return _add_entity(lead_id, LEAD, **attrs)


def _add_rel(source_id, target_id, relationship_type):
    ledger.add_relationship(Relationship(source_id=source_id, target_id=target_id, relationship_type=relationship_type))


def _add_deal(deal_id="DEAL-1", customer_id="CUST-1", **overrides):
    attrs = {"status": "funded", "vehicle_id": "VEH-1", "funded_at": "2026-02-01T00:00:00+00:00", "customer_id": customer_id}
    attrs.update(overrides)
    return _add_entity(deal_id, DEAL, **attrs)


def _add_service_record(record_id="SRV-1", **overrides):
    attrs = {"ServiceDate": "2026-01-15", "Description": "Oil change", "Technician": "EMP-9"}
    attrs.update(overrides)
    return _add_entity(record_id, SERVICE_RECORD, **attrs)


def _add_finance_contract(contract_id="FIN-1", **overrides):
    attrs = {"ContractDate": "2026-01-01", "TermMonths": 60, "lender_id": "LENDER-1"}
    attrs.update(overrides)
    return _add_entity(contract_id, FINANCE_CONTRACT, **attrs)


def _add_vehicle(vehicle_id="VEH-1", **overrides):
    attrs = {"VIN": "1FA0001", "Year": 2022, "Make": "Ford", "Model": "F-150"}
    attrs.update(overrides)
    return _add_entity(vehicle_id, VEHICLE, **attrs)


def _add_alert(alert_id="ALERT-1", alert_type="equity_mining", target_entity_id="CUST-1", **overrides):
    attrs = {
        "alert_type": alert_type,
        "target_entity_id": target_entity_id,
        "target_entity_type": CUSTOMER,
        "status": "new",
        "urgency": "medium",
        "headline": "Positive equity signal",
        "vehicle_id": "VEH-1",
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    attrs.update(overrides)
    return _add_entity(alert_id, TRIGGER_ALERT, **attrs)


def _add_note(note_id="NOTE-1", linked_entity_id="LEAD-1", category="call", **overrides):
    attrs = {
        "category": category,
        "linked_entity_id": linked_entity_id,
        "body": "Talked about pricing",
        "created_by": "EMP-1",
        "created_at": "2026-01-05T00:00:00+00:00",
    }
    attrs.update(overrides)
    return _add_entity(note_id, FIELD_NOTE, **attrs)


def _add_chat_session(session_id="CHAT-1", lead_id="LEAD-1", **overrides):
    attrs = {"lead_id": lead_id, "website_id": "SITE-1", "status": "promoted", "created_at": "2026-01-04T00:00:00+00:00"}
    attrs.update(overrides)
    return _add_entity(session_id, WEBSITE_CHAT_SESSION, **attrs)


def _add_rsvp(rsvp_id="RSVP-1", customer_id="CUST-1", **overrides):
    attrs = {"event_id": "EVENT-1", "status": "confirmed", "attended": False, "created_at": "2026-01-03T00:00:00+00:00", "customer_id": customer_id}
    attrs.update(overrides)
    return _add_entity(rsvp_id, EVENT_RSVP, **attrs)


def _add_campaign(campaign_id="CAMP-1", audience_ids=None, **overrides):
    attrs = {
        "name": "Spring Sale",
        "campaign_type": "inventory_ads",
        "channel": "email",
        "status": "active",
        "activated_at": "2026-01-02T00:00:00+00:00",
        "created_at": "2026-01-01T00:00:00+00:00",
        "audience_ids": audience_ids if audience_ids is not None else ["CUST-1"],
    }
    attrs.update(overrides)
    return _add_entity(campaign_id, CAMPAIGN, **attrs)


def _add_credit_app(app_id="CAPP-1", customer_id="CUST-1", decision=None, **overrides):
    attrs = {
        "customer_id": customer_id,
        "status": "decisioned" if decision else "draft",
        "linked_deal_id": None,
        "requested_amount": 25000,
        "decision": decision,
        "created_at": "2026-01-06T00:00:00+00:00",
    }
    attrs.update(overrides)
    return _add_entity(app_id, CREDIT_APPLICATION, **attrs)


def _add_purl(purl_id="PURL-1", customer_id="CUST-1", offer_type="payment_reduction", visit_log=None, **overrides):
    attrs = {
        "customer_id": customer_id,
        "offer_type": offer_type,
        "visit_log": visit_log if visit_log is not None else [],
    }
    attrs.update(overrides)
    return _add_entity(purl_id, PERSONALIZED_URL, **attrs)


def _add_field_override(employee_id, entity_type, field_name, granted):
    return _add_entity(
        f"PERM-{employee_id}-{field_name}",
        PERMISSION_OVERRIDE,
        employee_id=employee_id,
        permission_key=f"field:{entity_type}.{field_name}",
        granted=granted,
        active=True,
        created_at="2026-01-01T00:00:00+00:00",
    )


# ---------------------------------------------------------------------------
# _linked_lead_ids
# ---------------------------------------------------------------------------

class TestLinkedLeadIds:

    def test_no_relationships_returns_empty(self):
        _add_customer("CUST-1")
        assert customer_360._linked_lead_ids("CUST-1") == []

    def test_origin_lead_via_became(self):
        _add_customer("CUST-1")
        _add_lead("LEAD-1")
        _add_rel("LEAD-1", "CUST-1", BECAME)
        assert customer_360._linked_lead_ids("CUST-1") == ["LEAD-1"]

    def test_generated_lead_via_generated_lead_rel(self):
        _add_customer("CUST-1")
        _add_lead("LEAD-2")
        _add_rel("CUST-1", "LEAD-2", GENERATED_LEAD)
        assert customer_360._linked_lead_ids("CUST-1") == ["LEAD-2"]

    def test_both_directions_combined_origin_first(self):
        _add_customer("CUST-1")
        _add_lead("LEAD-1")
        _add_lead("LEAD-2")
        _add_rel("LEAD-1", "CUST-1", BECAME)
        _add_rel("CUST-1", "LEAD-2", GENERATED_LEAD)
        assert customer_360._linked_lead_ids("CUST-1") == ["LEAD-1", "LEAD-2"]

    def test_dedupes_repeat_ids(self):
        _add_customer("CUST-1")
        _add_lead("LEAD-1")
        _add_rel("LEAD-1", "CUST-1", BECAME)
        _add_rel("CUST-1", "LEAD-1", GENERATED_LEAD)
        assert customer_360._linked_lead_ids("CUST-1") == ["LEAD-1"]

    def test_wrong_relationship_type_ignored(self):
        _add_customer("CUST-1")
        _add_lead("LEAD-1")
        _add_rel("LEAD-1", "CUST-1", OWNS)
        assert customer_360._linked_lead_ids("CUST-1") == []

    def test_became_relationship_to_a_different_customer_not_included(self):
        _add_customer("CUST-1")
        _add_customer("CUST-2")
        _add_lead("LEAD-1")
        _add_rel("LEAD-1", "CUST-2", BECAME)
        assert customer_360._linked_lead_ids("CUST-1") == []


# ---------------------------------------------------------------------------
# _lead_brief
# ---------------------------------------------------------------------------

class TestLeadBrief:

    def test_valid_lead_returns_brief(self):
        _add_lead("LEAD-1", Source="Facebook", PipelineState="CONTACTED")
        brief = customer_360._lead_brief("LEAD-1")
        assert brief == {
            "id": "LEAD-1",
            "source": "Facebook",
            "pipeline_state": "CONTACTED",
            "created_at": "2026-01-01T00:00:00+00:00",
        }

    def test_nonexistent_lead_returns_none(self):
        assert customer_360._lead_brief("LEAD-NOPE") is None

    def test_entity_of_wrong_type_returns_none(self):
        _add_customer("CUST-1")
        assert customer_360._lead_brief("CUST-1") is None

    def test_created_date_fallback_when_created_at_absent(self):
        _add_lead("LEAD-1", CreatedAt=None, CreatedDate="2026-03-01")
        brief = customer_360._lead_brief("LEAD-1")
        assert brief["created_at"] == "2026-03-01"

    def test_created_at_preferred_over_created_date(self):
        _add_lead("LEAD-1", CreatedAt="2026-05-01T00:00:00+00:00", CreatedDate="2026-03-01")
        brief = customer_360._lead_brief("LEAD-1")
        assert brief["created_at"] == "2026-05-01T00:00:00+00:00"


# ---------------------------------------------------------------------------
# _get_lead_history
# ---------------------------------------------------------------------------

class TestGetLeadHistory:

    def test_empty_when_no_leads_linked(self):
        _add_customer("CUST-1")
        history = customer_360._get_lead_history("CUST-1")
        assert history["origin_leads"] == {"count": 0, "leads": []}
        assert history["re_engagement_leads"] == {"count": 0, "leads": []}

    def test_origin_and_generated_grouped_separately(self):
        _add_customer("CUST-1")
        _add_lead("LEAD-1")
        _add_lead("LEAD-2")
        _add_rel("LEAD-1", "CUST-1", BECAME)
        _add_rel("CUST-1", "LEAD-2", GENERATED_LEAD)

        history = customer_360._get_lead_history("CUST-1")
        assert history["origin_leads"]["count"] == 1
        assert history["origin_leads"]["leads"][0]["id"] == "LEAD-1"
        assert history["re_engagement_leads"]["count"] == 1
        assert history["re_engagement_leads"]["leads"][0]["id"] == "LEAD-2"

    def test_multiple_origin_leads(self):
        _add_customer("CUST-1")
        _add_lead("LEAD-1")
        _add_lead("LEAD-2")
        _add_rel("LEAD-1", "CUST-1", BECAME)
        _add_rel("LEAD-2", "CUST-1", BECAME)

        history = customer_360._get_lead_history("CUST-1")
        assert history["origin_leads"]["count"] == 2

    def test_deleted_lead_entity_excluded_from_brief_list(self):
        # A BECAME relationship pointing at a lead id that no longer exists in the
        # ledger -- _lead_brief returns None for it and the list comprehension in
        # _get_lead_history filters that None out.
        _add_customer("CUST-1")
        _add_rel("LEAD-GONE", "CUST-1", BECAME)
        history = customer_360._get_lead_history("CUST-1")
        assert history["origin_leads"] == {"count": 0, "leads": []}


# ---------------------------------------------------------------------------
# _get_trade_equity
# ---------------------------------------------------------------------------

class TestGetTradeEquity:

    def test_no_alerts_returns_empty(self):
        result = customer_360._get_trade_equity("CUST-1")
        assert result["count"] == 0
        assert result["basis"] == "heuristic_equity_mining"
        assert result["signals"] == []

    def test_matching_alert_included(self):
        _add_alert("ALERT-1", alert_type="equity_mining", target_entity_id="CUST-1")
        result = customer_360._get_trade_equity("CUST-1")
        assert result["count"] == 1
        assert result["signals"][0]["id"] == "ALERT-1"
        assert result["signals"][0]["headline"] == "Positive equity signal"

    def test_alert_for_different_customer_excluded(self):
        _add_alert("ALERT-1", alert_type="equity_mining", target_entity_id="CUST-2")
        result = customer_360._get_trade_equity("CUST-1")
        assert result["count"] == 0

    def test_non_equity_mining_alert_type_excluded(self):
        _add_alert("ALERT-1", alert_type="lease_maturity", target_entity_id="CUST-1")
        result = customer_360._get_trade_equity("CUST-1")
        assert result["count"] == 0

    def test_multiple_matching_alerts(self):
        _add_alert("ALERT-1", alert_type="equity_mining", target_entity_id="CUST-1")
        _add_alert("ALERT-2", alert_type="equity_mining", target_entity_id="CUST-1", urgency="high")
        result = customer_360._get_trade_equity("CUST-1")
        assert result["count"] == 2


# ---------------------------------------------------------------------------
# _get_communication_activity
# ---------------------------------------------------------------------------

class TestGetCommunicationActivity:

    def test_no_lead_ids_returns_empty(self):
        result = customer_360._get_communication_activity([])
        assert result["count"] == 0
        assert result["by_channel"] == {}
        assert result["recent"] == []

    def test_call_category_included(self):
        _add_note("NOTE-1", linked_entity_id="LEAD-1", category="call")
        result = customer_360._get_communication_activity(["LEAD-1"])
        assert result["count"] == 1
        assert result["by_channel"] == {"call": 1}

    @pytest.mark.parametrize("category", ["call", "text", "email", "video"])
    def test_every_communication_category_counted(self, category):
        _add_note("NOTE-1", linked_entity_id="LEAD-1", category=category)
        result = customer_360._get_communication_activity(["LEAD-1"])
        assert result["count"] == 1
        assert result["by_channel"] == {category: 1}

    def test_non_communication_category_excluded(self):
        _add_note("NOTE-1", linked_entity_id="LEAD-1", category="recovery_attempt")
        result = customer_360._get_communication_activity(["LEAD-1"])
        assert result["count"] == 0
        assert result["recent"] == []

    def test_pulls_from_every_linked_lead(self):
        _add_note("NOTE-1", linked_entity_id="LEAD-1", category="call")
        _add_note("NOTE-2", linked_entity_id="LEAD-2", category="text")
        result = customer_360._get_communication_activity(["LEAD-1", "LEAD-2"])
        assert result["count"] == 2
        assert result["by_channel"] == {"call": 1, "text": 1}

    def test_note_for_unrelated_lead_excluded(self):
        _add_note("NOTE-1", linked_entity_id="LEAD-99", category="call")
        result = customer_360._get_communication_activity(["LEAD-1"])
        assert result["count"] == 0

    def test_sorted_most_recent_first(self):
        _add_note("NOTE-OLD", linked_entity_id="LEAD-1", category="call", created_at="2026-01-01T00:00:00+00:00")
        _add_note("NOTE-NEW", linked_entity_id="LEAD-1", category="call", created_at="2026-06-01T00:00:00+00:00")
        result = customer_360._get_communication_activity(["LEAD-1"])
        assert [n["id"] for n in result["recent"]] == ["NOTE-NEW", "NOTE-OLD"]

    def test_recent_capped_at_20(self):
        for i in range(25):
            _add_note(f"NOTE-{i}", linked_entity_id="LEAD-1", category="call", created_at=f"2026-01-{i + 1:02d}T00:00:00+00:00")
        result = customer_360._get_communication_activity(["LEAD-1"])
        assert result["count"] == 25
        assert len(result["recent"]) == 20

    def test_recent_entry_shape(self):
        _add_note("NOTE-1", linked_entity_id="LEAD-1", category="email", body="Sent a quote", created_by="EMP-5")
        result = customer_360._get_communication_activity(["LEAD-1"])
        entry = result["recent"][0]
        assert entry["id"] == "NOTE-1"
        assert entry["category"] == "email"
        assert entry["body"] == "Sent a quote"
        assert entry["created_by"] == "EMP-5"


# ---------------------------------------------------------------------------
# _get_chat_activity
# ---------------------------------------------------------------------------

class TestGetChatActivity:

    def test_no_lead_ids_returns_empty(self):
        _add_chat_session("CHAT-1", lead_id="LEAD-1")
        result = customer_360._get_chat_activity([])
        assert result["count"] == 0
        assert result["sessions"] == []

    def test_session_for_linked_lead_included(self):
        _add_chat_session("CHAT-1", lead_id="LEAD-1")
        result = customer_360._get_chat_activity(["LEAD-1"])
        assert result["count"] == 1
        assert result["sessions"][0]["id"] == "CHAT-1"

    def test_session_for_unlinked_lead_excluded(self):
        _add_chat_session("CHAT-1", lead_id="LEAD-99")
        result = customer_360._get_chat_activity(["LEAD-1"])
        assert result["count"] == 0

    def test_session_with_no_lead_id_excluded(self):
        _add_chat_session("CHAT-1", lead_id=None)
        result = customer_360._get_chat_activity(["LEAD-1"])
        assert result["count"] == 0

    def test_sorted_most_recent_first(self):
        _add_chat_session("CHAT-OLD", lead_id="LEAD-1", created_at="2026-01-01T00:00:00+00:00")
        _add_chat_session("CHAT-NEW", lead_id="LEAD-1", created_at="2026-06-01T00:00:00+00:00")
        result = customer_360._get_chat_activity(["LEAD-1"])
        assert [s["id"] for s in result["sessions"]] == ["CHAT-NEW", "CHAT-OLD"]

    def test_includes_not_yet_tracked_note(self):
        result = customer_360._get_chat_activity([])
        assert "not_yet_tracked" in result
        assert "anonymous" in result["not_yet_tracked"].lower()

    def test_session_shape(self):
        _add_chat_session("CHAT-1", lead_id="LEAD-1", website_id="SITE-9", status="active")
        result = customer_360._get_chat_activity(["LEAD-1"])
        s = result["sessions"][0]
        assert s["website_id"] == "SITE-9"
        assert s["status"] == "active"


# ---------------------------------------------------------------------------
# _get_event_attendance
# ---------------------------------------------------------------------------

class TestGetEventAttendance:

    def test_no_rsvps_returns_empty(self):
        result = customer_360._get_event_attendance("CUST-1")
        assert result["count"] == 0
        assert result["rsvps"] == []

    def test_rsvp_for_customer_included(self):
        _add_rsvp("RSVP-1", customer_id="CUST-1")
        result = customer_360._get_event_attendance("CUST-1")
        assert result["count"] == 1
        assert result["rsvps"][0]["id"] == "RSVP-1"

    def test_rsvp_for_different_customer_excluded(self):
        _add_rsvp("RSVP-1", customer_id="CUST-2")
        result = customer_360._get_event_attendance("CUST-1")
        assert result["count"] == 0

    def test_sorted_most_recent_first(self):
        _add_rsvp("RSVP-OLD", customer_id="CUST-1", created_at="2026-01-01T00:00:00+00:00")
        _add_rsvp("RSVP-NEW", customer_id="CUST-1", created_at="2026-06-01T00:00:00+00:00")
        result = customer_360._get_event_attendance("CUST-1")
        assert [r["id"] for r in result["rsvps"]] == ["RSVP-NEW", "RSVP-OLD"]

    def test_rsvp_shape(self):
        _add_rsvp("RSVP-1", customer_id="CUST-1", event_id="EVENT-7", status="attended", attended=True)
        result = customer_360._get_event_attendance("CUST-1")
        r = result["rsvps"][0]
        assert r["event_id"] == "EVENT-7"
        assert r["status"] == "attended"
        assert r["attended"] is True


# ---------------------------------------------------------------------------
# _get_campaign_activity
# ---------------------------------------------------------------------------

class TestGetCampaignActivity:

    def test_no_campaigns_returns_empty(self):
        result = customer_360._get_campaign_activity("CUST-1", [])
        assert result["count"] == 0
        assert result["campaigns"] == []
        assert "not_yet_tracked" in result

    def test_campaign_targeting_customer_id_directly(self):
        _add_campaign("CAMP-1", audience_ids=["CUST-1"])
        result = customer_360._get_campaign_activity("CUST-1", [])
        assert result["count"] == 1
        assert result["campaigns"][0]["id"] == "CAMP-1"

    def test_campaign_targeting_a_linked_lead(self):
        _add_campaign("CAMP-1", audience_ids=["LEAD-1"])
        result = customer_360._get_campaign_activity("CUST-1", ["LEAD-1"])
        assert result["count"] == 1

    def test_campaign_targeting_neither_excluded(self):
        _add_campaign("CAMP-1", audience_ids=["CUST-99"])
        result = customer_360._get_campaign_activity("CUST-1", ["LEAD-1"])
        assert result["count"] == 0

    def test_campaign_with_no_audience_ids_excluded(self):
        _add_campaign("CAMP-1", audience_ids=[])
        result = customer_360._get_campaign_activity("CUST-1", [])
        assert result["count"] == 0

    def test_sorted_most_recent_first(self):
        _add_campaign("CAMP-OLD", audience_ids=["CUST-1"], created_at="2026-01-01T00:00:00+00:00")
        _add_campaign("CAMP-NEW", audience_ids=["CUST-1"], created_at="2026-06-01T00:00:00+00:00")
        result = customer_360._get_campaign_activity("CUST-1", [])
        assert [c["id"] for c in result["campaigns"]] == ["CAMP-NEW", "CAMP-OLD"]

    def test_campaign_shape(self):
        _add_campaign("CAMP-1", audience_ids=["CUST-1"], name="Fall Push", campaign_type="retention", channel="sms", status="draft")
        result = customer_360._get_campaign_activity("CUST-1", [])
        c = result["campaigns"][0]
        assert c["name"] == "Fall Push"
        assert c["campaign_type"] == "retention"
        assert c["channel"] == "sms"
        assert c["status"] == "draft"


# ---------------------------------------------------------------------------
# _get_credit_applications
# ---------------------------------------------------------------------------

class TestGetCreditApplications:

    def test_no_applications_returns_empty(self):
        result = customer_360._get_credit_applications("CUST-1")
        assert result["count"] == 0
        assert result["applications"] == []

    def test_application_with_no_decision_yet(self):
        _add_credit_app("CAPP-1", customer_id="CUST-1", decision=None, status="pending_consent")
        result = customer_360._get_credit_applications("CUST-1")
        app = result["applications"][0]
        assert app["decision"] is None
        assert app["score_band"] is None
        assert app["estimated_apr"] is None
        assert app["status"] == "pending_consent"

    def test_application_with_approved_decision(self):
        _add_credit_app(
            "CAPP-1",
            customer_id="CUST-1",
            decision={"decision": "approved", "score_band": "Excellent", "estimated_apr": 4.9},
        )
        result = customer_360._get_credit_applications("CUST-1")
        app = result["applications"][0]
        assert app["decision"] == "approved"
        assert app["score_band"] == "Excellent"
        assert app["estimated_apr"] == 4.9

    def test_application_for_different_customer_excluded(self):
        _add_credit_app("CAPP-1", customer_id="CUST-2")
        result = customer_360._get_credit_applications("CUST-1")
        assert result["count"] == 0

    def test_application_shape_includes_linked_deal_and_requested_amount(self):
        _add_credit_app("CAPP-1", customer_id="CUST-1", linked_deal_id="DEAL-9", requested_amount=30000)
        result = customer_360._get_credit_applications("CUST-1")
        app = result["applications"][0]
        assert app["id"] == "CAPP-1"
        assert app["linked_deal_id"] == "DEAL-9"
        assert app["requested_amount"] == 30000


# ---------------------------------------------------------------------------
# _get_trade_ins
# ---------------------------------------------------------------------------

class TestGetTradeIns:

    def test_no_deals_returns_empty(self):
        result = customer_360._get_trade_ins("CUST-1")
        assert result["count"] == 0
        assert result["trades"] == []

    def test_deal_with_no_trade_in_excluded(self):
        _add_deal("DEAL-1", customer_id="CUST-1", trade_in=None)
        result = customer_360._get_trade_ins("CUST-1")
        assert result["count"] == 0

    def test_deal_with_empty_trade_in_dict_excluded(self):
        # An empty dict is falsy in Python -- the same "if e.attributes.get(...)"
        # truthiness check that excludes trade_in=None also excludes {}.
        _add_deal("DEAL-1", customer_id="CUST-1", trade_in={})
        result = customer_360._get_trade_ins("CUST-1")
        assert result["count"] == 0

    def test_deal_with_real_trade_in_included(self):
        _add_deal(
            "DEAL-1",
            customer_id="CUST-1",
            trade_in={
                "vin": "1G1ABC1", "year": 2018, "make": "Chevrolet", "model": "Malibu",
                "acv": 8500, "market_value_estimate": 9200, "approved": True,
                "appraised_by": "EMP-3", "appraised_at": "2026-02-01T00:00:00+00:00",
            },
        )
        result = customer_360._get_trade_ins("CUST-1")
        assert result["count"] == 1
        t = result["trades"][0]
        assert t["deal_id"] == "DEAL-1"
        assert t["vin"] == "1G1ABC1"
        assert t["acv"] == 8500
        assert t["approved"] is True
        assert t["appraised_by"] == "EMP-3"

    def test_deal_for_different_customer_excluded(self):
        _add_deal("DEAL-1", customer_id="CUST-2", trade_in={"vin": "X"})
        result = customer_360._get_trade_ins("CUST-1")
        assert result["count"] == 0

    def test_sorted_most_recently_appraised_first(self):
        _add_deal("DEAL-OLD", customer_id="CUST-1", trade_in={"appraised_at": "2026-01-01T00:00:00+00:00"})
        _add_deal("DEAL-NEW", customer_id="CUST-1", trade_in={"appraised_at": "2026-06-01T00:00:00+00:00"})
        result = customer_360._get_trade_ins("CUST-1")
        assert [t["deal_id"] for t in result["trades"]] == ["DEAL-NEW", "DEAL-OLD"]

    def test_deal_status_carried_through(self):
        _add_deal("DEAL-1", customer_id="CUST-1", status="contract", trade_in={"vin": "X"})
        result = customer_360._get_trade_ins("CUST-1")
        assert result["trades"][0]["deal_status"] == "contract"


# ---------------------------------------------------------------------------
# get_customer_360 -- the full orchestrator
# ---------------------------------------------------------------------------

class TestGetCustomer360:

    def test_nonexistent_customer_returns_entity_not_found(self):
        result = customer_360.get_customer_360(ADMIN, "CUST-NOPE")
        assert result == {"error": "Entity not found"}

    def test_wrong_entity_type_when_role_can_access_that_type(self):
        # ADMIN can access every entity type (can_access_entity's bypass), so
        # get_entity_by_id succeeds for a Lead id -- the second, explicit
        # entity_type != CUSTOMER check in get_customer_360 is what actually
        # rejects it.
        _add_lead("LEAD-1")
        result = customer_360.get_customer_360(ADMIN, "LEAD-1")
        assert result == {"error": "Customer not found"}

    def test_role_forbidden_from_entity_type_returns_forbidden_message(self):
        # SERVICE is not in ENTITY_ACCESS[LEAD] -- get_entity_by_id's own Forbidden
        # branch fires before get_customer_360 even reaches its second check.
        _add_lead("LEAD-1")
        result = customer_360.get_customer_360(SERVICE, "LEAD-1")
        assert result == {"error": "Forbidden: your role cannot access this entity type"}

    def test_happy_path_returns_all_top_level_sections(self):
        _add_customer("CUST-1")
        result = customer_360.get_customer_360(ADMIN, "CUST-1")
        assert "error" not in result
        for key in (
            "customer", "related_entities", "lead_history", "purchase_history",
            "vehicles_owned", "service_history", "finance_contracts", "trade_equity",
            "communication_activity", "chat_activity", "event_attendance",
            "campaign_activity", "credit_applications", "trade_ins",
            "website_activity", "timeline", "not_yet_tracked",
        ):
            assert key in result, key

    def test_customer_id_present_in_customer_block(self):
        _add_customer("CUST-1")
        result = customer_360.get_customer_360(ADMIN, "CUST-1")
        assert result["customer"]["id"] == "CUST-1"

    def test_not_yet_tracked_has_two_stated_gaps(self):
        _add_customer("CUST-1")
        result = customer_360.get_customer_360(ADMIN, "CUST-1")
        assert "anonymous_website_browsing" in result["not_yet_tracked"]
        assert "email_sms_delivery_status" in result["not_yet_tracked"]

    def test_credit_score_masked_for_role_without_field_access(self):
        _add_customer("CUST-1", CreditScore="700")
        result = customer_360.get_customer_360(SALES, "CUST-1")
        assert result["customer"]["attributes"]["CreditScore"] == "•••• (restricted)"

    def test_credit_score_visible_for_admin(self):
        _add_customer("CUST-1", CreditScore="700")
        result = customer_360.get_customer_360(ADMIN, "CUST-1")
        assert result["customer"]["attributes"]["CreditScore"] == "700"

    def test_credit_score_visible_for_finance(self):
        _add_customer("CUST-1", CreditScore="700")
        result = customer_360.get_customer_360(FINANCE, "CUST-1")
        assert result["customer"]["attributes"]["CreditScore"] == "700"

    def test_credit_score_masked_for_marketing(self):
        _add_customer("CUST-1", CreditScore="700")
        result = customer_360.get_customer_360(MARKETING, "CUST-1")
        assert result["customer"]["attributes"]["CreditScore"] == "•••• (restricted)"

    def test_field_override_grants_visibility_to_a_role_normally_denied(self):
        _add_customer("CUST-1", CreditScore="700")
        _add_field_override("EMP-1", "Customer", "CreditScore", granted=True)
        result = customer_360.get_customer_360(SALES, "CUST-1", employee_id="EMP-1")
        assert result["customer"]["attributes"]["CreditScore"] == "700"

    def test_field_override_can_also_revoke_a_normally_allowed_view(self):
        _add_customer("CUST-1", CreditScore="700")
        _add_field_override("EMP-1", "Customer", "CreditScore", granted=False)
        result = customer_360.get_customer_360(ADMIN, "CUST-1", employee_id="EMP-1")
        assert result["customer"]["attributes"]["CreditScore"] == "•••• (restricted)"

    def test_no_employee_id_falls_back_to_role_default(self):
        _add_customer("CUST-1", CreditScore="700")
        result = customer_360.get_customer_360(SALES, "CUST-1", employee_id=None)
        assert result["customer"]["attributes"]["CreditScore"] == "•••• (restricted)"

    def test_composes_sales_customer_360_purchase_history(self):
        _add_customer("CUST-1")
        _add_deal("DEAL-1", customer_id="CUST-1")
        result = customer_360.get_customer_360(ADMIN, "CUST-1")
        assert result["purchase_history"]["count"] == 1
        assert result["purchase_history"]["deals"][0]["id"] == "DEAL-1"

    def test_composes_sales_customer_360_service_history(self):
        _add_customer("CUST-1")
        _add_service_record("SRV-1")
        _add_rel("CUST-1", "SRV-1", AUTHORIZED)
        result = customer_360.get_customer_360(ADMIN, "CUST-1")
        assert result["service_history"]["count"] == 1

    def test_composes_sales_customer_360_finance_contracts(self):
        _add_customer("CUST-1")
        _add_finance_contract("FIN-1")
        _add_rel("CUST-1", "FIN-1", FINANCED_BY)
        result = customer_360.get_customer_360(ADMIN, "CUST-1")
        assert result["finance_contracts"]["count"] == 1

    def test_composes_sales_customer_360_vehicles_owned(self):
        _add_customer("CUST-1")
        _add_vehicle("VEH-1")
        _add_rel("CUST-1", "VEH-1", OWNS)
        result = customer_360.get_customer_360(ADMIN, "CUST-1")
        assert result["vehicles_owned"]["count"] == 1

    def test_lead_history_composed(self):
        _add_customer("CUST-1")
        _add_lead("LEAD-1")
        _add_rel("LEAD-1", "CUST-1", BECAME)
        result = customer_360.get_customer_360(ADMIN, "CUST-1")
        assert result["lead_history"]["origin_leads"]["count"] == 1

    def test_communication_activity_resolved_through_linked_leads(self):
        _add_customer("CUST-1")
        _add_lead("LEAD-1")
        _add_rel("LEAD-1", "CUST-1", BECAME)
        _add_note("NOTE-1", linked_entity_id="LEAD-1", category="call")
        result = customer_360.get_customer_360(ADMIN, "CUST-1")
        assert result["communication_activity"]["count"] == 1

    def test_related_entities_reuses_ai_tools(self):
        _add_customer("CUST-1")
        _add_vehicle("VEH-1")
        _add_rel("CUST-1", "VEH-1", OWNS)
        result = customer_360.get_customer_360(ADMIN, "CUST-1")
        related_ids = [r["entity"]["id"] for r in result["related_entities"]]
        assert "VEH-1" in related_ids

    def test_website_activity_reuses_purl_engine(self):
        _add_customer("CUST-1")
        _add_purl("PURL-1", customer_id="CUST-1", visit_log=[{"visited_at": "2026-03-01T00:00:00+00:00"}])
        result = customer_360.get_customer_360(ADMIN, "CUST-1")
        assert result["website_activity"]["count"] == 1
        assert result["website_activity"]["basis"] == "real_purl_visit_log"


class TestTimelineComposition:

    def test_empty_customer_has_empty_timeline(self):
        _add_customer("CUST-1")
        result = customer_360.get_customer_360(ADMIN, "CUST-1")
        assert result["timeline"] == []

    def test_purchase_entry_present(self):
        _add_customer("CUST-1")
        _add_deal("DEAL-1", customer_id="CUST-1", status="funded", funded_at="2026-02-01T00:00:00+00:00")
        result = customer_360.get_customer_360(ADMIN, "CUST-1")
        types = [t["type"] for t in result["timeline"]]
        assert "purchase" in types

    def test_purchase_entry_dropped_when_no_funded_at_timestamp(self):
        _add_customer("CUST-1")
        _add_deal("DEAL-1", customer_id="CUST-1", status="desking", funded_at=None)
        result = customer_360.get_customer_360(ADMIN, "CUST-1")
        types = [t["type"] for t in result["timeline"]]
        assert "purchase" not in types

    def test_service_entry_present(self):
        _add_customer("CUST-1")
        _add_service_record("SRV-1", ServiceDate="2026-01-15")
        _add_rel("CUST-1", "SRV-1", AUTHORIZED)
        result = customer_360.get_customer_360(ADMIN, "CUST-1")
        types = [t["type"] for t in result["timeline"]]
        assert "service" in types

    def test_communication_entry_present(self):
        _add_customer("CUST-1")
        _add_lead("LEAD-1")
        _add_rel("LEAD-1", "CUST-1", BECAME)
        _add_note("NOTE-1", linked_entity_id="LEAD-1", category="call")
        result = customer_360.get_customer_360(ADMIN, "CUST-1")
        types = [t["type"] for t in result["timeline"]]
        assert "communication" in types

    def test_chat_entry_present(self):
        _add_customer("CUST-1")
        _add_lead("LEAD-1")
        _add_rel("LEAD-1", "CUST-1", BECAME)
        _add_chat_session("CHAT-1", lead_id="LEAD-1")
        result = customer_360.get_customer_360(ADMIN, "CUST-1")
        types = [t["type"] for t in result["timeline"]]
        assert "chat" in types

    def test_event_entry_present(self):
        _add_customer("CUST-1")
        _add_rsvp("RSVP-1", customer_id="CUST-1")
        result = customer_360.get_customer_360(ADMIN, "CUST-1")
        types = [t["type"] for t in result["timeline"]]
        assert "event" in types

    def test_campaign_entry_present(self):
        _add_customer("CUST-1")
        _add_campaign("CAMP-1", audience_ids=["CUST-1"], activated_at="2026-01-02T00:00:00+00:00")
        result = customer_360.get_customer_360(ADMIN, "CUST-1")
        types = [t["type"] for t in result["timeline"]]
        assert "campaign" in types

    def test_campaign_entry_dropped_when_never_activated(self):
        _add_customer("CUST-1")
        _add_campaign("CAMP-1", audience_ids=["CUST-1"], activated_at=None)
        result = customer_360.get_customer_360(ADMIN, "CUST-1")
        types = [t["type"] for t in result["timeline"]]
        assert "campaign" not in types

    def test_trade_equity_entry_present(self):
        _add_customer("CUST-1")
        _add_alert("ALERT-1", alert_type="equity_mining", target_entity_id="CUST-1")
        result = customer_360.get_customer_360(ADMIN, "CUST-1")
        types = [t["type"] for t in result["timeline"]]
        assert "trade_equity" in types

    def test_credit_application_entry_present(self):
        _add_customer("CUST-1")
        _add_credit_app("CAPP-1", customer_id="CUST-1", decision={"decision": "approved"})
        result = customer_360.get_customer_360(ADMIN, "CUST-1")
        types = [t["type"] for t in result["timeline"]]
        assert "credit_application" in types

    def test_credit_application_entry_uses_status_when_no_decision_yet(self):
        _add_customer("CUST-1")
        _add_credit_app("CAPP-1", customer_id="CUST-1", decision=None, status="pending_consent")
        result = customer_360.get_customer_360(ADMIN, "CUST-1")
        entry = next(t for t in result["timeline"] if t["type"] == "credit_application")
        assert "pending_consent" in entry["summary"]

    def test_trade_in_entry_present(self):
        _add_customer("CUST-1")
        _add_deal("DEAL-1", customer_id="CUST-1", trade_in={"vin": "X", "year": 2019, "make": "Kia", "model": "Soul", "appraised_at": "2026-02-01T00:00:00+00:00", "approved": True})
        result = customer_360.get_customer_360(ADMIN, "CUST-1")
        types = [t["type"] for t in result["timeline"]]
        assert "trade_in" in types
        entry = next(t for t in result["timeline"] if t["type"] == "trade_in")
        assert "2019 Kia Soul" in entry["summary"]
        assert "approved" in entry["summary"]

    def test_trade_in_entry_shows_pending_when_not_approved(self):
        _add_customer("CUST-1")
        _add_deal("DEAL-1", customer_id="CUST-1", trade_in={"vin": "X", "appraised_at": "2026-02-01T00:00:00+00:00", "approved": False})
        result = customer_360.get_customer_360(ADMIN, "CUST-1")
        entry = next(t for t in result["timeline"] if t["type"] == "trade_in")
        assert "pending approval" in entry["summary"]

    def test_website_activity_entry_present(self):
        _add_customer("CUST-1")
        _add_purl("PURL-1", customer_id="CUST-1", offer_type="trade_equity", visit_log=[{"visited_at": "2026-03-01T00:00:00+00:00"}])
        result = customer_360.get_customer_360(ADMIN, "CUST-1")
        types = [t["type"] for t in result["timeline"]]
        assert "website_activity" in types

    def test_timeline_sorted_most_recent_first_across_types(self):
        _add_customer("CUST-1")
        _add_deal("DEAL-1", customer_id="CUST-1", status="funded", funded_at="2026-01-01T00:00:00+00:00")
        _add_rsvp("RSVP-1", customer_id="CUST-1", created_at="2026-06-01T00:00:00+00:00")
        result = customer_360.get_customer_360(ADMIN, "CUST-1")
        timestamps = [t["timestamp"] for t in result["timeline"]]
        assert timestamps == sorted(timestamps, reverse=True)
        assert result["timeline"][0]["type"] == "event"

    def test_entries_without_a_timestamp_are_dropped(self):
        _add_customer("CUST-1")
        _add_alert("ALERT-1", alert_type="equity_mining", target_entity_id="CUST-1", created_at=None)
        result = customer_360.get_customer_360(ADMIN, "CUST-1")
        # a None-timestamped equity signal is filtered out of the timeline entirely,
        # even though it still shows up in the trade_equity section itself.
        assert result["trade_equity"]["count"] == 1
        assert all(t.get("timestamp") for t in result["timeline"])


# ---------------------------------------------------------------------------
# ACL: core/customer_360_api.py
# ---------------------------------------------------------------------------

ALLOWED_ROLES = (ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE)
DENIED_ROLES = ("BOGUS_ROLE", "", None, "SUPERADMIN")


class TestAcl:

    @pytest.mark.parametrize("role", ALLOWED_ROLES)
    def test_allowed_roles_reach_the_real_function(self, role):
        ledger.reset()
        _add_customer("CUST-1")
        result = customer_360_api.get_customer_360_api(role, "CUST-1")
        assert "error" not in result or result.get("error") != "You don't have access to Customer 360 with your current role."
        assert result["customer"]["id"] == "CUST-1"

    @pytest.mark.parametrize("role", DENIED_ROLES)
    def test_denied_roles_get_forbidden_message(self, role):
        _add_customer("CUST-1")
        result = customer_360_api.get_customer_360_api(role, "CUST-1")
        assert result == {"error": "You don't have access to Customer 360 with your current role."}

    def test_api_layer_passes_employee_id_through(self):
        _add_customer("CUST-1", CreditScore="700")
        _add_field_override("EMP-1", "Customer", "CreditScore", granted=True)
        result = customer_360_api.get_customer_360_api(SALES, "CUST-1", employee_id="EMP-1")
        assert result["customer"]["attributes"]["CreditScore"] == "700"

    def test_api_layer_default_employee_id_is_none(self):
        _add_customer("CUST-1", CreditScore="700")
        result = customer_360_api.get_customer_360_api(SALES, "CUST-1")
        assert result["customer"]["attributes"]["CreditScore"] == "•••• (restricted)"

    def test_allowed_role_but_nonexistent_customer_still_passes_through_to_real_error(self):
        result = customer_360_api.get_customer_360_api(ADMIN, "CUST-NOPE")
        assert result == {"error": "Entity not found"}
