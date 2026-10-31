"""
Tests for NXTDeal Connect (core/connect.py + core/connect_api.py) — 2026-07-24, the
unified communications surface. Run from backend/ with `pytest`.

Covers: the inbox unifies every logged communication across channels and flags AI-handled
touches; channel/direction/ai_only filters; the customer timeline merges communications with
the appointments booked for the same entity, newest first; analytics split AI-handled from
human-handled and roll up by AI role; and the API is open to any authenticated role.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import CUSTOMER
from core.permissions import SALES
from core.communications_hub import log_communication
from core.appointments import create_appointment

from core import connect
from core import connect_api


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield
    ledger.reset()


def _seed():
    # human phone call + two AI touches, two linked to CUST-1
    log_communication("sales", "phone", "inbound", "Called about a truck", "EMP-1", linked_entity_id="CUST-1")
    log_communication("sales", "text", "outbound", "Following up!", "ai_worker:bdc", linked_entity_id="CUST-1")
    log_communication("general", "chat", "inbound", "What are your hours?", "ai_worker:receptionist")


def test_inbox_unifies_channels_and_flags_ai():
    _seed()
    inbox = connect.get_inbox()
    assert inbox["count"] == 3
    channels = {i["channel"] for i in inbox["items"]}
    assert channels == {"phone", "text", "chat"}
    ai_items = [i for i in inbox["items"] if i["handled_by_ai"]]
    assert len(ai_items) == 2
    assert {i["ai_worker_role"] for i in ai_items} == {"bdc", "receptionist"}


def test_inbox_filters():
    _seed()
    assert connect.get_inbox(channel="text")["count"] == 1
    assert connect.get_inbox(direction="inbound")["count"] == 2
    assert connect.get_inbox(ai_only=True)["count"] == 2
    assert connect.get_inbox(linked_entity_id="CUST-1")["count"] == 2


def test_customer_timeline_merges_comms_and_appointments():
    _seed()
    ledger.add_entity(Entity(id="CUST-1", entity_type=CUSTOMER, attributes={"Name": "Pat Q"}))
    create_appointment("Sales", "showroom_visit", "2026-08-01T09:00:00Z", "EMP-1", customer_id="CUST-1")
    timeline = connect.get_customer_timeline("CUST-1")
    kinds = [e["kind"] for e in timeline["events"]]
    assert "communication" in kinds and "appointment" in kinds
    assert timeline["event_count"] == 3  # 2 comms linked to CUST-1 + 1 appointment
    # newest-first ordering (the 2026-08 appointment sorts above the earlier comms)
    ats = [e["at"] for e in timeline["events"] if e["at"]]
    assert ats == sorted(ats, reverse=True)


def test_analytics_split_ai_vs_human():
    _seed()
    a = connect.get_analytics()
    assert a["ai_handled"] == 2
    assert a["human_handled"] == 1
    assert a["ai_by_role"] == {"bdc": 1, "receptionist": 1}
    assert a["communications"]["total_communications"] == 3
    assert "workforce" in a  # AI Workforce tallies tied in


def test_api_open_to_any_role():
    _seed()
    assert connect_api.get_connect_inbox_api(SALES)["count"] == 3
    assert connect_api.get_connect_timeline_api(SALES, "CUST-1")["event_count"] == 2
    assert connect_api.get_connect_analytics_api(SALES)["ai_handled"] == 2


def test_inbox_items_and_analytics_carry_conversation_intelligence():
    _seed()
    inbox = connect.get_inbox()
    assert all("intelligence" in i and "sentiment" in i["intelligence"] for i in inbox["items"])
    analytics = connect.get_analytics()
    assert "intelligence" in analytics
    assert analytics["intelligence"]["total_analyzed"] == 3
