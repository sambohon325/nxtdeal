"""
Tests for the NXTDeal AI Workforce (core/ai_worker.py + core/ai_worker_api.py) —
2026-07-24, the AI Worker foundation + AI Receptionist. Run from backend/ with `pytest`.

Covers: the eight workers materialize inactive/draft; role normalization; admin
activate/deactivate; autonomous mode gated by the default-deny ai.worker.autonomous
capability; handling an interaction always logs a real Communication and detects intent;
the execution gate (draft mode drafts everything; assisted executes a whitelisted action;
off-whitelist always drafts); the receptionist books a real appointment when armed and a
time is given, and asks for a time otherwise; and everything persists as AiWorker /
AiWorkerAction entities in the one ledger. API admin gating.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import (
    AI_WORKER, AI_WORKER_ACTION, COMMUNICATION, APPOINTMENT, DEAL, CUSTOMER, VEHICLE,
)
from core.permissions import ADMIN, SALES

from core import ai_worker
from core import ai_worker_api


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield
    ledger.reset()


@pytest.fixture
def grant_autonomous(monkeypatch):
    """Grant the default-deny ai.worker.autonomous capability dealer-wide, the same way
    tests/test_bot_fleet.py grants bot.coverage.auto_mode — so autonomous-mode tests
    exercise worker behavior, not the permission layer (which has its own tests)."""
    import core.bot_permissions as bp
    monkeypatch.setattr(bp, "save_graph", lambda filepath: None)
    monkeypatch.setattr(bp, "save_audit_log", lambda filepath: None)
    from core.bot_permissions import grant_capability
    grant_capability("ai.worker.autonomous", "dealer_wide", True, "EMP-TEST-SETUP")
    yield


# ---- workforce listing + normalization ----------------------------------------------

def test_workforce_materializes_all_workers_inactive_by_default():
    workforce = ai_worker.list_workforce()
    assert len(workforce) == len(ai_worker.WORKER_ROLES) == 13
    roles = {w["role"] for w in workforce}
    assert roles == set(ai_worker.WORKER_ROLES)
    assert all(w["status"] == "inactive" and w["mode"] == "draft" for w in workforce)
    assert any(w["display_name"] == "AI Receptionist" for w in workforce)


def test_role_normalization():
    assert ai_worker.normalize_role("Receptionist") == "receptionist"
    assert ai_worker.normalize_role("  BDC ") == "bdc"
    assert ai_worker.normalize_role("not-a-role") is None


# ---- activation ---------------------------------------------------------------------

def test_admin_activate_and_deactivate_draft_mode():
    result = ai_worker.activate_worker("receptionist", "draft", "ADMIN-1")
    assert result["worker"]["status"] == "active"
    assert result["worker"]["mode"] == "draft"
    # one AiWorker entity in the one ledger
    workers = [e for e in ledger.get_all().values() if e.entity_type == AI_WORKER and e.attributes.get("role") == "receptionist"]
    assert len(workers) == 1 and workers[0].id.startswith("AIW")

    off = ai_worker.deactivate_worker("receptionist", "ADMIN-1")
    assert off["worker"]["status"] == "inactive"


def test_activate_rejects_unknown_role_and_mode():
    assert "error" in ai_worker.activate_worker("nope", "draft", "ADMIN-1")
    assert "error" in ai_worker.activate_worker("receptionist", "turbo", "ADMIN-1")


def test_autonomous_mode_requires_capability():
    # Without the grant, autonomous activation fails loud.
    denied = ai_worker.activate_worker("receptionist", "autonomous", "ADMIN-1")
    assert "error" in denied


def test_autonomous_mode_activates_with_capability(grant_autonomous):
    ok = ai_worker.activate_worker("receptionist", "autonomous", "ADMIN-1")
    assert ok["worker"]["mode"] == "autonomous"


# ---- handling interactions ----------------------------------------------------------

def _appointments():
    return [e for e in ledger.get_all().values() if e.entity_type == APPOINTMENT]


def test_handle_logs_a_communication_and_detects_intent():
    ai_worker.activate_worker("receptionist", "draft", "ADMIN-1")
    result = ai_worker.handle_interaction("receptionist", "chat", "What are your hours?", "svc")
    assert result["intent"] == "hours"
    assert result["response"]  # a templated answer
    comms = [e for e in ledger.get_all().values() if e.entity_type == COMMUNICATION]
    assert len(comms) == 1  # the inbound touch was logged


def test_draft_mode_never_books_even_with_a_time():
    ai_worker.activate_worker("receptionist", "draft", "ADMIN-1")
    result = ai_worker.handle_interaction(
        "receptionist", "chat", "I'd like to schedule an oil change",
        "svc", scheduled_start="2026-08-01T09:00:00Z"
    )
    assert result["intent"] == "schedule_service"
    book = [a for a in result["actions"] if a["action_key"] == "book_appointment"][0]
    assert book["status"] == "drafted"
    assert _appointments() == []  # nothing booked


def test_assisted_mode_books_a_real_appointment_when_time_given():
    ai_worker.activate_worker("receptionist", "assisted", "ADMIN-1")
    result = ai_worker.handle_interaction(
        "receptionist", "phone", "Can I schedule an oil change please?",
        "svc", scheduled_start="2026-08-01T09:00:00Z"
    )
    book = [a for a in result["actions"] if a["action_key"] == "book_appointment"][0]
    assert book["status"] == "executed"
    appts = _appointments()
    assert len(appts) == 1
    assert appts[0].attributes.get("appointment_type") == "service"


def test_schedule_without_a_time_asks_for_one_and_does_not_book():
    ai_worker.activate_worker("receptionist", "assisted", "ADMIN-1")
    result = ai_worker.handle_interaction(
        "receptionist", "chat", "I need an oil change", "svc"
    )
    book = [a for a in result["actions"] if a["action_key"] == "book_appointment"][0]
    assert book["status"] == "drafted"          # no time -> can't execute
    assert "day" in result["response"].lower()   # asks for a preferred day
    assert _appointments() == []


def test_autonomous_receptionist_books_end_to_end(grant_autonomous):
    ai_worker.activate_worker("receptionist", "autonomous", "ADMIN-1")
    result = ai_worker.handle_interaction(
        "receptionist", "phone", "schedule an oil change", "svc",
        scheduled_start="2026-08-02T10:00:00Z"
    )
    statuses = {a["action_key"]: a["status"] for a in result["actions"]}
    assert statuses.get("book_appointment") == "executed"
    assert statuses.get("send_confirmation") == "executed"
    assert len(_appointments()) == 1


def test_off_whitelist_action_always_drafts():
    # A worker without deep inbound handling (e.g. marketing) proposes a draft_follow_up,
    # which is never a whitelisted executable action -> always drafted, even when armed.
    ai_worker.activate_worker("marketing", "assisted", "ADMIN-1")
    result = ai_worker.handle_interaction("marketing", "sms", "random question", "svc")
    follow = [a for a in result["actions"] if a["action_key"] == "draft_follow_up"][0]
    assert follow["status"] == "drafted"


def test_actions_persist_as_graph_entities_and_detail_reads_them():
    ai_worker.activate_worker("receptionist", "assisted", "ADMIN-1")
    ai_worker.handle_interaction(
        "receptionist", "phone", "book an oil change", "svc",
        scheduled_start="2026-08-01T09:00:00Z"
    )
    actions = [e for e in ledger.get_all().values() if e.entity_type == AI_WORKER_ACTION]
    assert actions and all(a.id.startswith("AIWA") for a in actions)
    detail = ai_worker.get_worker_detail("receptionist")
    assert detail["available"] is True
    assert detail["interactions_handled"] >= 1
    assert detail["actions_executed"] >= 1
    assert "book_appointment" in detail["safe_actions"]


# ---- API gating ---------------------------------------------------------------------

def test_api_activate_and_deactivate_are_admin_only():
    assert "error" in ai_worker_api.activate_worker_api(SALES, "EMP-1", "receptionist", "draft")
    ok = ai_worker_api.activate_worker_api(ADMIN, "ADMIN-1", "receptionist", "draft")
    assert "error" not in ok
    assert "error" in ai_worker_api.deactivate_worker_api(SALES, "EMP-1", "receptionist")


def test_api_view_and_handle_open_to_any_role():
    workforce = ai_worker_api.get_workforce_api(SALES)
    assert workforce["summary"]["total_workers"] == 13
    handled = ai_worker_api.handle_interaction_api("EMP-1", "receptionist", "chat", "what are your hours?")
    assert handled["intent"] == "hours"


# ---- Slice 2: AI BDC agent (outbound queue) -----------------------------------------

from datetime import datetime, timezone, timedelta
from core.entities import Entity
from core.entity_types import LEAD


def _new_web_lead(lead_id, first="Pat"):
    ledger.add_entity(Entity(
        id=lead_id, entity_type=LEAD,
        attributes={"Source": "Website", "PipelineState": "NEW", "FirstName": first, "LastName": "Q"},
    ))


def _outbound_comms():
    return [e for e in ledger.get_all().values()
            if e.entity_type == COMMUNICATION and e.attributes.get("direction") == "outbound"]


def test_work_queue_implemented_for_the_queue_roles():
    # sales/service/collections now return a real result (a summary), not "available: False".
    assert "summary" in ai_worker.work_queue("sales", "ADMIN-1")


def test_bdc_follows_up_untouched_leads_when_armed():
    _new_web_lead("LEAD-1", "Alex")
    _new_web_lead("LEAD-2", "Sam")
    ai_worker.activate_worker("bdc", "assisted", "ADMIN-1")
    result = ai_worker.work_queue("bdc", "ADMIN-1")
    assert result["summary"]["leads_followed_up"] == 2
    assert all(x["status"] == "executed" for x in result["leads_followed_up"])
    assert len(_outbound_comms()) == 2  # a real outbound touch per lead


def test_bdc_draft_mode_drafts_every_touch():
    _new_web_lead("LEAD-1")
    ai_worker.activate_worker("bdc", "draft", "ADMIN-1")
    result = ai_worker.work_queue("bdc", "ADMIN-1")
    assert result["summary"]["executed"] == 0
    assert all(x["status"] == "drafted" for x in result["leads_followed_up"])
    assert _outbound_comms() == []  # nothing sent


def test_bdc_confirms_upcoming_and_recovers_no_shows():
    from core.appointments import create_appointment, update_status
    soon = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()
    create_appointment("Sales", "showroom_visit", soon, "svc")
    past_appt = create_appointment("Sales", "showroom_visit", soon, "svc")
    update_status(past_appt.id, "no_show", "svc")

    ai_worker.activate_worker("bdc", "assisted", "ADMIN-1")
    result = ai_worker.work_queue("bdc", "ADMIN-1")
    assert result["summary"]["appointments_confirmed"] >= 1
    assert result["summary"]["no_shows_recovered"] == 1
    assert all(x["status"] == "executed" for x in result["appointments_confirmed"])
    assert all(x["status"] == "executed" for x in result["no_shows_recovered"])


def test_api_run_queue_is_admin_only():
    assert "error" in ai_worker_api.run_worker_queue_api(SALES, "EMP-1", "bdc")
    ok = ai_worker_api.run_worker_queue_api(ADMIN, "ADMIN-1", "bdc")
    assert "error" not in ok


# ---- Slice 3: Sales / Service / Collections agents ----------------------------------

from core.entity_types import SERVICE_RECORD


def test_operator_has_no_outbound_queue():
    # The Operator is inbound-only (internal screen help) -- no outbound queue.
    assert ai_worker.work_queue("operator", "ADMIN-1")["available"] is False


def test_sales_agent_follows_up_stale_open_leads_skipping_terminal(monkeypatch):
    import core.follow_up_queue as fuq
    monkeypatch.setattr(fuq, "get_follow_up_queue", lambda ids, threshold_days=7: [
        {"lead_id": "LEAD-A", "current_state": "Working", "days_in_state": 9},
        {"lead_id": "LEAD-B", "current_state": "Contacted", "days_in_state": 5},
        {"lead_id": "LEAD-C", "current_state": "Sold", "days_in_state": 20},  # terminal -> skipped
    ])
    ai_worker.activate_worker("sales", "assisted", "ADMIN-1")
    result = ai_worker.work_queue("sales", "ADMIN-1")
    assert result["summary"]["leads_followed_up"] == 2  # LEAD-C excluded
    assert {x["lead_id"] for x in result["leads_followed_up"]} == {"LEAD-A", "LEAD-B"}
    assert len(_outbound_comms()) == 2


def test_service_agent_notifies_ready_and_follows_up():
    ledger.add_entity(Entity(id="SVC-1", entity_type=SERVICE_RECORD, attributes={"ro_stage": "Delivery"}))
    ledger.add_entity(Entity(id="SVC-2", entity_type=SERVICE_RECORD, attributes={"ro_stage": "Follow-Up"}))
    ai_worker.activate_worker("service", "assisted", "ADMIN-1")
    result = ai_worker.work_queue("service", "ADMIN-1")
    assert result["summary"]["ready_for_pickup"] == 1
    assert result["summary"]["service_follow_ups"] == 1
    assert result["summary"]["executed"] == 2


def test_collections_agent_reminds_past_due_accounts_when_armed(monkeypatch):
    import core.collections as collections_mod
    monkeypatch.setattr(collections_mod, "get_collection_queue", lambda bucket=None: {"loans": [
        {"loan_id": "LOAN-1", "customer_name": "Jordan", "days_past_due": 12},
        {"loan_id": "LOAN-2", "customer_name": "Casey", "days_past_due": 40},
    ]})
    ai_worker.activate_worker("collections", "assisted", "ADMIN-1")
    result = ai_worker.work_queue("collections", "ADMIN-1")
    assert result["summary"]["payment_reminders"] == 2
    assert result["summary"]["executed"] == 2
    assert len(_outbound_comms()) == 2  # every touch logged (compliance)


def test_collections_draft_mode_drafts_every_reminder(monkeypatch):
    import core.collections as collections_mod
    monkeypatch.setattr(collections_mod, "get_collection_queue", lambda bucket=None: {"loans": [
        {"loan_id": "LOAN-1", "customer_name": "Jordan", "days_past_due": 12},
    ]})
    ai_worker.activate_worker("collections", "draft", "ADMIN-1")
    result = ai_worker.work_queue("collections", "ADMIN-1")
    assert result["summary"]["executed"] == 0
    assert result["summary"]["payment_reminders"] == 1
    assert result["payment_reminders"][0]["status"] == "drafted"
    assert _outbound_comms() == []


def test_sales_agent_books_from_inbound_reply():
    # Sales now shares the receptionist/bdc inbound scheduling handler.
    ai_worker.activate_worker("sales", "assisted", "ADMIN-1")
    result = ai_worker.handle_interaction(
        "sales", "sms", "yes I'd like to come in for a test drive", "svc",
        scheduled_start="2026-08-05T14:00:00Z"
    )
    book = [a for a in result["actions"] if a["action_key"] == "book_appointment"][0]
    assert book["status"] == "executed"
    assert len(_appointments()) == 1


# ---- Slice 3b: Finance / Marketing / Operator agents --------------------------------

from core.entity_types import DEAL


def test_finance_agent_updates_deals_pending_financing():
    ledger.add_entity(Entity(id="DEAL-1", entity_type=DEAL, attributes={"financing_status": "submitted"}))
    ledger.add_entity(Entity(id="DEAL-2", entity_type=DEAL, attributes={"financing_status": "submitted"}))
    ledger.add_entity(Entity(id="DEAL-3", entity_type=DEAL, attributes={"financing_status": "approved"}))  # not pending
    ai_worker.activate_worker("finance", "assisted", "ADMIN-1")
    result = ai_worker.work_queue("finance", "ADMIN-1")
    assert result["summary"]["funding_updates"] == 2
    assert result["summary"]["executed"] == 2
    assert len(_outbound_comms()) == 2


def test_marketing_agent_only_drafts_never_publishes_even_autonomous(grant_autonomous):
    ai_worker.activate_worker("marketing", "autonomous", "ADMIN-1")  # fully armed
    result = ai_worker.work_queue("marketing", "ADMIN-1")
    assert result["summary"]["asset_drafts"] == 3
    assert result["summary"]["executed"] == 0            # never auto-published
    assert all(d["status"] == "drafted" for d in result["asset_drafts"])
    assert _outbound_comms() == []                        # nothing sent to customers


def test_operator_handles_screen_help_inbound():
    ai_worker.activate_worker("operator", "assisted", "ADMIN-1")
    result = ai_worker.handle_interaction("operator", "chat", "help me with this screen", "EMP-9")
    assert "screen" in result["response"].lower()
    # Operator only answers -- it proposes no executable/draft actions.
    assert result["actions"] == []


# ---- Digital Retail AI roles (DR-7) --------------------------------------------------

def test_dr7_roles_are_registered():
    dr = {"product_specialist", "trade_manager", "negotiator", "delivery_coordinator", "ownership_concierge"}
    assert dr <= set(ai_worker.WORKER_ROLES)
    assert ai_worker.ROLE_DISPLAY["negotiator"] == "AI Negotiator"
    assert ai_worker.ROLE_DISPLAY["ownership_concierge"] == "AI Ownership Concierge"


def test_product_specialist_is_inbound_only():
    res = ai_worker.work_queue("product_specialist", "EMP-1")
    assert res.get("available") is False


def test_trade_manager_queue_acknowledges_submitted_trades():
    ledger.add_entity(Entity(id="CUST-1", entity_type=CUSTOMER, attributes={"Name": "P"}))
    ledger.add_entity(Entity(id="VEH-1", entity_type=VEHICLE, attributes={"Make": "Ford"}))
    ledger.add_entity(Entity(id="DEAL-1", entity_type=DEAL, attributes={
        "customer_id": "CUST-1", "vehicle_id": "VEH-1", "status": "desking",
        "trade_in": {"vin": "1X", "mileage": 40000}}))
    res = ai_worker.work_queue("trade_manager", "EMP-1")
    assert res["summary"]["trades_acknowledged"] == 1
    assert len(res["actions"]) == 1


def test_negotiator_queue_nudges_active_sessions():
    ledger.add_entity(Entity(id="CUST-1", entity_type=CUSTOMER, attributes={"Name": "P", "CreditScore": 720}))
    ledger.add_entity(Entity(id="VEH-1", entity_type=VEHICLE, attributes={"Make": "Ford", "Price": 30000, "Cost": 25000}))
    from core.deals import create_deal
    from core.negotiation_engine import start_session
    deal = create_deal("CUST-1", "VEH-1", "EMP-1")
    start_session(deal.id, "EMP-1")
    res = ai_worker.work_queue("negotiator", "EMP-1")
    assert res["summary"]["negotiations_nudged"] == 1


def test_delivery_coordinator_queue_updates_in_flight():
    ledger.add_entity(Entity(id="CUST-1", entity_type=CUSTOMER, attributes={"Name": "P"}))
    ledger.add_entity(Entity(id="VEH-1", entity_type=VEHICLE, attributes={"Make": "Ford"}))
    ledger.add_entity(Entity(id="DEAL-1", entity_type=DEAL, attributes={
        "customer_id": "CUST-1", "vehicle_id": "VEH-1", "status": "contract"}))
    from core.delivery_fulfillment import schedule_delivery
    schedule_delivery("DEAL-1", "store_pickup", "2026-08-01T10:00:00Z", "EMP-1")
    res = ai_worker.work_queue("delivery_coordinator", "EMP-1")
    assert res["summary"]["deliveries_updated"] == 1


def test_ownership_concierge_welcomes_funded_owners():
    ledger.add_entity(Entity(id="CUST-1", entity_type=CUSTOMER, attributes={"Name": "P"}))
    ledger.add_entity(Entity(id="VEH-1", entity_type=VEHICLE, attributes={"Make": "Ford"}))
    ledger.add_entity(Entity(id="DEAL-9", entity_type=DEAL, attributes={
        "customer_id": "CUST-1", "vehicle_id": "VEH-1", "status": "funded"}))
    res = ai_worker.work_queue("ownership_concierge", "EMP-1")
    assert res["summary"]["owners_welcomed"] == 1


def test_dr7_roles_draft_by_default_nothing_executes():
    # inactive (default) workers draft every touch -- no autonomous execution
    ledger.add_entity(Entity(id="CUST-1", entity_type=CUSTOMER, attributes={"Name": "P"}))
    ledger.add_entity(Entity(id="VEH-1", entity_type=VEHICLE, attributes={"Make": "Ford"}))
    ledger.add_entity(Entity(id="DEAL-9", entity_type=DEAL, attributes={
        "customer_id": "CUST-1", "vehicle_id": "VEH-1", "status": "funded"}))
    res = ai_worker.work_queue("ownership_concierge", "EMP-1")
    assert res["summary"]["executed"] == 0
    assert all(a["status"] == "drafted" for a in res["actions"])


# ---- Deepened agent queues (Polish-3) -----------------------------------------------

def test_service_agent_requests_dvi_approval_with_a_real_link():
    from core.entity_types import SERVICE_RECORD
    ledger.add_entity(Entity(id="RO-9", entity_type=SERVICE_RECORD, attributes={
        "ro_stage": "Customer Approval",
        "estimate": {"total": 850, "lines": [{"desc": "brakes", "price": 850}]},
    }))
    res = ai_worker.work_queue("service", "EMP-1")
    approvals = res["approvals_requested"]
    assert len(approvals) == 1
    assert approvals[0]["approval_path"] and approvals[0]["approval_path"].startswith("/approve/")


def test_finance_agent_drafts_a_document_checklist():
    # a deal awaiting a lender decision (pending financing)
    ledger.add_entity(Entity(id="CUST-1", entity_type=CUSTOMER, attributes={"FirstName": "P", "CreditScore": 700}))
    ledger.add_entity(Entity(id="VEH-1", entity_type=VEHICLE, attributes={"Make": "Ford", "Price": 30000, "Cost": 26000}))
    from core.deals import create_deal, add_scenario, select_scenario, submit_to_lender
    from core.entities import Entity as E
    from core.entity_types import LENDER
    ledger.add_entity(E(id="LEN-1", entity_type=LENDER, attributes={"Name": "Acme Bank"}))
    deal = create_deal("CUST-1", "VEH-1", "EMP-1")
    add_scenario(deal.id, "Base", 29000, 3000, 60)
    select_scenario(deal.id, "scn-1")
    submit_to_lender(deal.id, "LEN-1")  # -> pending financing

    res = ai_worker.work_queue("finance", "EMP-1")
    assert res["summary"]["funding_updates"] == 1
    docs = res["document_requests"]
    assert len(docs) == 1 and len(docs[0]["checklist"]) >= 4
    # a document request always drafts (never auto-sent)
    assert docs[0]["status"] == "drafted"


def test_marketing_agent_creates_real_draft_campaigns():
    from core.entity_types import CAMPAIGN
    res = ai_worker.work_queue("marketing", "ADMIN-1")
    # existing behavior preserved
    assert res["summary"]["asset_drafts"] == 3
    assert all(d["status"] == "drafted" for d in res["asset_drafts"])
    # plus real draft campaign entities
    drafted = res["campaigns_drafted"]
    assert len(drafted) == 3
    campaigns = [e for e in ledger.get_all().values() if e.entity_type == CAMPAIGN]
    assert len(campaigns) == 3
    assert all(c.attributes.get("status") == "draft" for c in campaigns)
    # idempotent -- a second run creates no duplicates
    ai_worker.work_queue("marketing", "ADMIN-1")
    assert len([e for e in ledger.get_all().values() if e.entity_type == CAMPAIGN]) == 3


def test_assisted_mode_respects_the_ai_kill_switch():
    """Regression: an emergency kill switch must stop ASSISTED workers too, not only autonomous —
    no auto-booking/messaging while the dealer-wide stop is active."""
    from core import ai_kill_switch
    ai_worker.activate_worker("receptionist", "assisted", "ADMIN-1")
    ai_kill_switch.set_dealer_wide_kill_switch(True, "ADMIN-1")  # emergency stop ON
    try:
        result = ai_worker.handle_interaction(
            "receptionist", "phone", "Can I schedule an oil change please?",
            "svc", scheduled_start="2026-08-01T09:00:00Z"
        )
        book = [a for a in result["actions"] if a["action_key"] == "book_appointment"][0]
        assert book["status"] == "drafted"      # not executed while the switch is active
        assert len(_appointments()) == 0
    finally:
        ai_kill_switch.set_dealer_wide_kill_switch(False, "ADMIN-1")
