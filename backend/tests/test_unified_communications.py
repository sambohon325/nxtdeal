"""
Tests for core/unified_communications.py / core/unified_communications_api.py --
Operations' "Communications" Top Menu item, a real read-only cross-department
aggregation of three already-real, department-siloed FieldNote-backed contact
logs (Sales' Communication Hub, Service's RO Communication Center, Finance's
Collections contact log) into one company-wide, filterable feed.

This module makes no mutations of its own -- create_field_note() (used to build
test fixtures) does call save_graph() internally, so field_notes.save_graph is
monkeypatched to a no-op the same way every other module's own save_graph is
patched at its own point of use.

Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import LEAD, CUSTOMER, DEAL, VEHICLE, SERVICE_RECORD, FINANCE_CONTRACT, EMAIL_TEMPLATE
from core.relationships import Relationship
from core import field_notes
from core import repair_orders
from core import unified_communications
from core import unified_communications_api
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    monkeypatch.setattr(field_notes, "save_graph", lambda filepath: None)
    monkeypatch.setattr(repair_orders, "save_graph", lambda filepath: None)


_VIEW_ROLES = (ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE)


def _add_lead(lead_id="LEAD-1", first="John", last="Smith"):
    ledger.add_entity(Entity(id=lead_id, entity_type=LEAD, attributes={
        "FirstName": first, "LastName": last,
    }))
    return lead_id


def _add_customer(customer_id="CUST-1", customer_key="C1", first="Jane", last="Doe"):
    ledger.add_entity(Entity(id=customer_id, entity_type=CUSTOMER, attributes={
        "CustomerID": customer_key, "FirstName": first, "LastName": last,
    }))
    return customer_id


def _add_vehicle(vehicle_id="VEH-1", vin="VIN1"):
    ledger.add_entity(Entity(id=vehicle_id, entity_type=VEHICLE, attributes={"VIN": vin}))
    return vehicle_id


def _add_ro(ro_id="SRV-1", customer_key="C1", vin="VIN1", description="Brake noise"):
    ledger.add_entity(Entity(id=ro_id, entity_type=SERVICE_RECORD, attributes={
        "CustomerID": customer_key, "VIN": vin, "Description": description,
    }))
    return ro_id


def _add_loan(loan_id="FIN-1", customer_id=None):
    ledger.add_entity(Entity(id=loan_id, entity_type=FINANCE_CONTRACT, attributes={}))
    if customer_id:
        ledger.add_relationship(Relationship(
            source_id=customer_id, target_id=loan_id, relationship_type="FINANCED_BY"
        ))
    return loan_id


def _note(department, category, body, linked_entity_id=None, created_by="EMP-1"):
    return field_notes.create_field_note(department, category, body, created_by, linked_entity_id=linked_entity_id)


class TestLeadOrCustomerLabel:

    def test_a_lead_resolves_to_its_real_name(self):
        _add_lead()

        assert unified_communications._lead_or_customer_label("LEAD-1") == "John Smith"

    def test_a_customer_resolves_to_its_real_name(self):
        _add_customer()

        assert unified_communications._lead_or_customer_label("CUST-1") == "Jane Doe"

    def test_a_lead_with_no_name_falls_back_to_its_id(self):
        ledger.add_entity(Entity(id="LEAD-2", entity_type=LEAD, attributes={}))

        assert unified_communications._lead_or_customer_label("LEAD-2") == "LEAD-2"

    def test_a_deal_resolves_to_a_real_deal_label(self):
        ledger.add_entity(Entity(id="DEAL-1", entity_type=DEAL, attributes={}))

        assert unified_communications._lead_or_customer_label("DEAL-1") == "Deal DEAL-1"

    def test_an_unrecognized_entity_type_falls_back_to_its_id(self):
        ledger.add_entity(Entity(id="VEH-1", entity_type=VEHICLE, attributes={}))

        assert unified_communications._lead_or_customer_label("VEH-1") == "VEH-1"

    def test_a_nonexistent_entity_id_returns_none(self):
        assert unified_communications._lead_or_customer_label("LEAD-BOGUS") is None

    def test_a_none_entity_id_returns_none(self):
        assert unified_communications._lead_or_customer_label(None) is None


class TestRoLabel:

    def test_a_none_ro_id_returns_none(self):
        assert unified_communications._ro_label(None) is None

    def test_an_unknown_ro_id_returns_the_id_itself(self):
        assert unified_communications._ro_label("SRV-BOGUS") == "SRV-BOGUS"

    def test_a_real_ro_with_a_customer_and_description_combines_both(self):
        _add_customer()
        _add_ro()

        assert unified_communications._ro_label("SRV-1") == "Jane Doe -- Brake noise"

    def test_a_real_ro_with_no_matching_customer_falls_back_to_description_only(self):
        _add_ro(customer_key="C-NOMATCH")

        assert unified_communications._ro_label("SRV-1") == "Brake noise"

    def test_a_real_ro_with_no_customer_and_no_description_falls_back_to_the_ro_id(self):
        ledger.add_entity(Entity(id="SRV-1", entity_type=SERVICE_RECORD, attributes={}))

        assert unified_communications._ro_label("SRV-1") == "SRV-1"


class TestLoanLabel:

    def test_a_none_loan_id_returns_none(self):
        assert unified_communications._loan_label(None) is None

    def test_an_unknown_loan_id_returns_the_id_itself(self):
        assert unified_communications._loan_label("FIN-BOGUS") == "FIN-BOGUS"

    def test_a_real_loan_with_a_linked_customer_combines_name_and_loan_id(self):
        _add_customer()
        _add_loan(customer_id="CUST-1")

        assert unified_communications._loan_label("FIN-1") == "Jane Doe (FIN-1)"

    def test_a_real_loan_with_no_linked_customer_falls_back_to_the_loan_id(self):
        _add_loan()

        assert unified_communications._loan_label("FIN-1") == "FIN-1"


class TestTouchBrief:

    def test_a_sales_call_touch_resolves_a_real_lead_label(self):
        _add_lead()
        note = _note("Sales", "call", "Discussed pricing", linked_entity_id="LEAD-1")

        brief = unified_communications._touch_brief(note)

        assert brief["department"] == "Sales"
        assert brief["channel"] == "call"
        assert brief["body"] == "Discussed pricing"
        assert brief["linked_entity_label"] == "John Smith"
        assert brief["linked_entity_id"] == "LEAD-1"
        assert brief["created_by"] == "EMP-1"
        assert brief["created_at"] is not None

    def test_an_ro_communication_touch_parses_its_embedded_channel_prefix(self):
        _add_customer()
        _add_ro()
        note = _note("Service", "ro_communication", "[text] Vehicle is ready for pickup", linked_entity_id="SRV-1")

        brief = unified_communications._touch_brief(note)

        assert brief["channel"] == "text"
        assert brief["body"] == "Vehicle is ready for pickup"
        assert brief["linked_entity_label"] == "Jane Doe -- Brake noise"

    def test_an_ro_communication_touch_with_no_prefix_falls_back_to_the_raw_category_and_body(self):
        _add_ro()
        note = _note("Service", "ro_communication", "No prefix here at all", linked_entity_id="SRV-1")

        brief = unified_communications._touch_brief(note)

        assert brief["channel"] == "ro_communication"
        assert brief["body"] == "No prefix here at all"

    def test_a_finance_touch_resolves_a_real_loan_label(self):
        _add_customer()
        _add_loan(customer_id="CUST-1")
        note = _note("Finance", "call", "Discussed payment plan", linked_entity_id="FIN-1")

        brief = unified_communications._touch_brief(note)

        assert brief["channel"] == "call"
        assert brief["linked_entity_label"] == "Jane Doe (FIN-1)"

    def test_a_touch_with_no_linked_entity_falls_back_the_label_to_the_linked_id(self):
        note = _note("Sales", "email", "Sent a follow-up", linked_entity_id=None)

        brief = unified_communications._touch_brief(note)

        assert brief["linked_entity_id"] is None
        assert brief["linked_entity_label"] is None


class TestGetUnifiedFeed:

    def test_an_empty_ledger_returns_a_real_empty_feed(self):
        result = unified_communications.get_unified_feed()

        assert result == {"total": 0, "by_department": {}, "by_channel": {}, "items": []}

    def test_only_real_touch_categories_are_included(self):
        _add_lead()
        _note("Sales", "call", "A real call", linked_entity_id="LEAD-1")
        _note("Sales", "note", "An internal note, not a touch category", linked_entity_id="LEAD-1")

        result = unified_communications.get_unified_feed()

        assert result["total"] == 1
        assert result["items"][0]["body"] == "A real call"

    def test_department_filter_only_returns_that_departments_touches(self):
        _add_lead()
        _add_customer()
        _add_loan(customer_id="CUST-1")
        _note("Sales", "call", "sales call", linked_entity_id="LEAD-1")
        _note("Finance", "call", "finance call", linked_entity_id="FIN-1")

        result = unified_communications.get_unified_feed(department="Sales")

        assert result["total"] == 1
        assert result["items"][0]["department"] == "Sales"

    def test_channel_filter_only_returns_that_channels_touches(self):
        _add_lead()
        _note("Sales", "call", "a call", linked_entity_id="LEAD-1")
        _note("Sales", "text", "a text", linked_entity_id="LEAD-1")

        result = unified_communications.get_unified_feed(channel="text")

        assert result["total"] == 1
        assert result["items"][0]["channel"] == "text"

    def test_by_department_and_by_channel_breakdowns_are_real_counts(self):
        _add_lead()
        _add_customer()
        _add_loan(customer_id="CUST-1")
        _note("Sales", "call", "sales call 1", linked_entity_id="LEAD-1")
        _note("Sales", "call", "sales call 2", linked_entity_id="LEAD-1")
        _note("Finance", "text", "finance text", linked_entity_id="FIN-1")

        result = unified_communications.get_unified_feed()

        assert result["by_department"] == {"Sales": 2, "Finance": 1}
        assert result["by_channel"] == {"call": 2, "text": 1}

    def test_the_channel_filter_applies_after_ro_communication_channel_parsing(self):
        _add_ro()
        _note("Service", "ro_communication", "[email] Estimate sent", linked_entity_id="SRV-1")
        _note("Service", "ro_communication", "[call] Called about repair", linked_entity_id="SRV-1")

        result = unified_communications.get_unified_feed(channel="email")

        assert result["total"] == 1
        assert result["items"][0]["body"] == "Estimate sent"

    def test_the_items_list_is_capped_at_the_given_limit(self):
        _add_lead()
        for i in range(5):
            _note("Sales", "call", f"call {i}", linked_entity_id="LEAD-1")

        result = unified_communications.get_unified_feed(limit=2)

        assert result["total"] == 5
        assert len(result["items"]) == 2


class TestGetMarketingSendCount:

    def test_no_email_templates_returns_real_zeros(self):
        result = unified_communications.get_marketing_send_count()

        assert result == {"total_templates": 0, "attached_to_campaign": 0}

    def test_counts_total_templates_and_those_attached_to_a_campaign(self):
        ledger.add_entity(Entity(id="TMPL-1", entity_type=EMAIL_TEMPLATE, attributes={
            "linked_campaign_id": "CAMP-1",
        }))
        ledger.add_entity(Entity(id="TMPL-2", entity_type=EMAIL_TEMPLATE, attributes={}))

        result = unified_communications.get_marketing_send_count()

        assert result == {"total_templates": 2, "attached_to_campaign": 1}


class TestGetUnifiedCommunicationsOverview:

    def test_composes_the_feed_marketing_sends_and_a_real_not_yet_tracked_note(self):
        _add_lead()
        _note("Sales", "call", "a real call", linked_entity_id="LEAD-1")
        ledger.add_entity(Entity(id="TMPL-1", entity_type=EMAIL_TEMPLATE, attributes={
            "linked_campaign_id": "CAMP-1",
        }))

        result = unified_communications.get_unified_communications_overview(ADMIN)

        assert result["feed"]["total"] == 1
        assert result["marketing_sends"] == {"total_templates": 1, "attached_to_campaign": 1}
        assert "read_receipts" in result["not_yet_tracked"]
        assert "live_telephony_sms_email_integration" in result["not_yet_tracked"]
        assert "marketing_bulk_sends" in result["not_yet_tracked"]

    def test_department_and_channel_filters_pass_through_to_the_feed(self):
        _add_lead()
        _add_customer()
        _add_loan(customer_id="CUST-1")
        _note("Sales", "call", "sales call", linked_entity_id="LEAD-1")
        _note("Finance", "text", "finance text", linked_entity_id="FIN-1")

        result = unified_communications.get_unified_communications_overview(
            ADMIN, department="Finance", channel="text"
        )

        assert result["feed"]["total"] == 1
        assert result["feed"]["items"][0]["department"] == "Finance"


class TestUnifiedCommunicationsApiRoleGating:

    def test_every_real_view_role_is_allowed(self):
        for role in _VIEW_ROLES:
            result = unified_communications_api.get_unified_communications_overview_api(role)
            assert "error" not in result

    def test_an_unknown_role_is_denied(self):
        result = unified_communications_api.get_unified_communications_overview_api("BOGUS")

        assert "error" in result

    def test_a_denied_call_does_not_include_any_feed_data(self):
        result = unified_communications_api.get_unified_communications_overview_api("BOGUS")

        assert "feed" not in result
