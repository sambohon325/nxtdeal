"""Tests for core/call_center.py + core/call_center_api.py (Phase 2: Communications
Platform, Voice -- 2026-07-22) -- the first-class Call entity, least-busy inbound
routing, outbound placement, reassignment, the ringing->connected->ended/missed/
voicemail lifecycle, simulated voicemail, and the cross-module Communication record
every terminal call produces via core/communications_hub.py's log_communication().

Follows tests/test_communications_hub.py's own established conventions exactly:
fresh_ledger/no_real_persistence autouse fixtures (the ledger is a module-level
singleton, so every test gets a clean slate, and no test call ever reaches a real
save_graph() -- both core/call_center.py's own save_graph reference AND
core/communications_hub.py's own save_graph reference are monkeypatched, since
end_call/mark_missed/send_to_voicemail all call into that sibling module's
log_communication(), which persists via its own module-level save_graph binding,
not call_center's).
"""

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import CUSTOMER, EMPLOYEE, LEAD
from core.permissions import ADMIN, FINANCE, MARKETING, OPERATIONS, SALES, SERVICE

import core.call_center as call_center
import core.call_center_api as call_center_api
import core.communications_hub as communications_hub

_VIEW_ROLES = (ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE)


@pytest.fixture(autouse=True)
def fresh_ledger():

    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):

    monkeypatch.setattr(call_center, "save_graph", lambda filepath: None)
    monkeypatch.setattr(communications_hub, "save_graph", lambda filepath: None)


def _add_employee(employee_id="EMP-1", department="Sales", first="Jordan", last="Agent"):

    employee = Entity(
        id=employee_id,
        entity_type=EMPLOYEE,
        attributes={"FirstName": first, "LastName": last, "Department": department},
    )
    ledger.add_entity(employee)
    return employee


def _add_lead(lead_id="LEAD-1"):

    lead = Entity(id=lead_id, entity_type=LEAD, attributes={"FirstName": "Pat", "LastName": "Prospect"})
    ledger.add_entity(lead)
    return lead


def _add_customer(customer_id="CUST-1"):

    customer = Entity(id=customer_id, entity_type=CUSTOMER, attributes={"FirstName": "Sam", "LastName": "Owner"})
    ledger.add_entity(customer)
    return customer


class TestRouteIncomingCall:

    def test_rejects_an_unknown_department(self):

        call, error = call_center.route_incoming_call("bogus", "555-0001")
        assert call is None
        assert error == "Unknown department 'bogus'. Must be one of ['sales', 'service', 'finance', 'general']."

    def test_general_department_has_no_roster_and_is_always_unassigned(self):

        call, error = call_center.route_incoming_call("general", "555-0001")
        assert error is None
        assert call["assigned_to"] is None
        assert call["routing_note"] == "No staffed General employees on roster -- call unassigned."
        assert call["status"] == "ringing"
        assert call["direction"] == "inbound"
        assert call["department"] == "general"

    def test_a_real_department_with_zero_staffed_employees_is_unassigned(self):

        call, error = call_center.route_incoming_call("finance", "555-0002")
        assert error is None
        assert call["assigned_to"] is None
        assert call["routing_note"] == "No staffed Finance employees on roster -- call unassigned."

    def test_routes_to_the_only_available_agent_with_zero_other_active_calls(self):

        agent = _add_employee("EMP-1", "Sales")
        call, error = call_center.route_incoming_call("sales", "555-0003")
        assert error is None
        assert call["assigned_to"] == agent.id
        assert call["routing_note"] == "Routed to least-busy available Sales agent (0 other active call(s) at time of routing)."

    def test_routes_to_the_least_busy_agent_when_one_is_already_connected(self):

        e1 = _add_employee("EMP-1", "Sales")
        e2 = _add_employee("EMP-2", "Sales")

        call1, err1 = call_center.route_incoming_call("sales", "555-1111")
        assert err1 is None
        first_assigned = call1["assigned_to"]
        assert first_assigned in (e1.id, e2.id)

        connected, connect_err = call_center.connect_call(call1["id"])
        assert connect_err is None
        assert connected["status"] == "connected"

        call2, err2 = call_center.route_incoming_call("sales", "555-2222")
        assert err2 is None
        assert call2["assigned_to"] != first_assigned

    def test_default_created_by_is_the_inbound_call_router(self):

        call, error = call_center.route_incoming_call("general", "555-0001")
        assert error is None
        assert call["created_by"] == "inbound_call_router"

    def test_a_custom_created_by_is_honored(self):

        call, error = call_center.route_incoming_call("general", "555-0001", created_by="IVR-42")
        assert error is None
        assert call["created_by"] == "IVR-42"

    def test_to_number_and_linked_entity_id_pass_through(self):

        lead = _add_lead()
        call, error = call_center.route_incoming_call(
            "general", "555-0001", to_number="555-9999", linked_entity_id=lead.id,
        )
        assert error is None
        assert call["to_number"] == "555-9999"
        assert call["linked_entity_id"] == lead.id

    def test_every_lifecycle_field_starts_none(self):

        call, error = call_center.route_incoming_call("general", "555-0001")
        assert error is None
        assert call["connected_at"] is None
        assert call["ended_at"] is None
        assert call["duration_seconds"] is None
        assert call["notes"] is None
        assert call["voicemail"] is None
        assert call["coaching_score"] is None
        assert call["qa_review"] is None
        assert call["communication_id"] is None
        assert call["created_at"] is not None


class TestPlaceOutboundCall:

    def test_rejects_an_unknown_department(self):

        _add_employee("EMP-1", "Sales")
        call, error = call_center.place_outbound_call("bogus", "555-0001", created_by="EMP-1")
        assert call is None
        assert error == "Unknown department 'bogus'. Must be one of ['sales', 'service', 'finance', 'general']."

    def test_rejects_an_unknown_created_by_employee(self):

        call, error = call_center.place_outbound_call("sales", "555-0001", created_by="EMP-GHOST")
        assert call is None
        assert error == "Employee 'EMP-GHOST' not found."

    def test_rejects_a_created_by_that_is_not_an_employee_entity(self):

        lead = _add_lead()
        call, error = call_center.place_outbound_call("sales", "555-0001", created_by=lead.id)
        assert call is None
        assert error == f"Employee '{lead.id}' not found."

    def test_success_assigns_directly_to_the_placing_employee(self):

        agent = _add_employee("EMP-1", "Sales")
        call, error = call_center.place_outbound_call("sales", "555-0001", created_by=agent.id)
        assert error is None
        assert call["direction"] == "outbound"
        assert call["assigned_to"] == agent.id
        assert call["created_by"] == agent.id
        assert call["status"] == "ringing"
        assert call["routing_note"] == f"Outbound call placed directly by {agent.id}."

    def test_from_number_and_linked_entity_id_pass_through(self):

        agent = _add_employee("EMP-1", "Sales")
        customer = _add_customer()
        call, error = call_center.place_outbound_call(
            "sales", "555-0001", created_by=agent.id, from_number="555-3333", linked_entity_id=customer.id,
        )
        assert error is None
        assert call["from_number"] == "555-3333"
        assert call["linked_entity_id"] == customer.id


class TestReassignCall:

    def test_rejects_an_unknown_call(self):

        agent = _add_employee("EMP-1", "Sales")
        call, error = call_center.reassign_call("CALL-GHOST", agent.id, "EMP-2")
        assert call is None
        assert error == "Call 'CALL-GHOST' not found."

    def test_rejects_reassigning_a_call_that_is_not_ringing(self):

        e1 = _add_employee("EMP-1", "Finance")
        call, _ = call_center.route_incoming_call("finance", "555-0001")
        call_center.reassign_call(call["id"], e1.id, "EMP-ADMIN")
        call_center.connect_call(call["id"])

        e2 = _add_employee("EMP-2", "Finance")
        reassigned, error = call_center.reassign_call(call["id"], e2.id, "EMP-ADMIN")
        assert reassigned is None
        assert error == "Call is 'connected', not 'ringing' -- cannot reassign."

    def test_rejects_an_unknown_employee(self):

        call, _ = call_center.route_incoming_call("finance", "555-0001")
        reassigned, error = call_center.reassign_call(call["id"], "EMP-GHOST", "EMP-ADMIN")
        assert reassigned is None
        assert error == "Employee 'EMP-GHOST' not found."

    def test_success_updates_assignment_and_routing_note(self):

        agent = _add_employee("EMP-1", "Finance")
        # Route to "general", which has no roster mapping and is always left
        # unassigned -- this is the reliable way to get a genuinely-unassigned
        # ringing call to exercise manual reassignment against, since routing
        # to "finance" here would auto-assign the sole available Finance agent
        # immediately (least-busy auto-assignment fires whenever any staffed
        # agent is available, even if there's only one candidate).
        call, _ = call_center.route_incoming_call("general", "555-0001")
        assert call["assigned_to"] is None

        reassigned, error = call_center.reassign_call(call["id"], agent.id, "EMP-ADMIN")
        assert error is None
        assert reassigned["assigned_to"] == agent.id
        assert reassigned["routing_note"] == f"Manually reassigned to {agent.id} by EMP-ADMIN."
        assert reassigned["status"] == "ringing"


class TestConnectCall:

    def test_rejects_an_unknown_call(self):

        call, error = call_center.connect_call("CALL-GHOST")
        assert call is None
        assert error == "Call 'CALL-GHOST' not found."

    def test_rejects_a_call_with_no_assigned_agent(self):

        call, _ = call_center.route_incoming_call("general", "555-0001")
        connected, error = call_center.connect_call(call["id"])
        assert connected is None
        assert error == "No agent is assigned to this call yet -- route or reassign before connecting."

    def test_rejects_connecting_a_call_that_is_not_ringing(self):

        agent = _add_employee("EMP-1", "Sales")
        call, _ = call_center.route_incoming_call("sales", "555-0001")
        call_center.connect_call(call["id"])

        connected, error = call_center.connect_call(call["id"])
        assert connected is None
        assert error == "Call is 'connected', not 'ringing' -- cannot connect."

    def test_success_sets_status_and_connected_at(self):

        agent = _add_employee("EMP-1", "Sales")
        call, _ = call_center.route_incoming_call("sales", "555-0001")
        connected, error = call_center.connect_call(call["id"])
        assert error is None
        assert connected["status"] == "connected"
        assert connected["connected_at"] is not None


class TestEndCall:

    def test_rejects_an_unknown_call(self):

        ended, error = call_center.end_call("CALL-GHOST", "EMP-1")
        assert ended is None
        assert error == "Call 'CALL-GHOST' not found."

    def test_rejects_ending_a_call_that_is_not_connected(self):

        agent = _add_employee("EMP-1", "Sales")
        call, _ = call_center.route_incoming_call("sales", "555-0001")

        ended, error = call_center.end_call(call["id"], agent.id)
        assert ended is None
        assert error == "Call is 'ringing', not 'connected' -- cannot end."

    def test_success_computes_a_non_negative_duration_when_not_supplied(self):

        agent = _add_employee("EMP-1", "Sales")
        call, _ = call_center.route_incoming_call("sales", "555-0001")
        call_center.connect_call(call["id"])

        ended, error = call_center.end_call(call["id"], agent.id)
        assert error is None
        assert ended["status"] == "ended"
        assert ended["ended_at"] is not None
        assert ended["duration_seconds"] is not None
        assert ended["duration_seconds"] >= 0

    def test_an_explicit_duration_seconds_overrides_the_computed_one(self):

        agent = _add_employee("EMP-1", "Sales")
        call, _ = call_center.route_incoming_call("sales", "555-0001")
        call_center.connect_call(call["id"])

        ended, error = call_center.end_call(call["id"], agent.id, duration_seconds=245)
        assert error is None
        assert ended["duration_seconds"] == 245

    def test_notes_are_stored_on_the_call(self):

        agent = _add_employee("EMP-1", "Sales")
        call, _ = call_center.route_incoming_call("sales", "555-0001")
        call_center.connect_call(call["id"])

        ended, error = call_center.end_call(call["id"], agent.id, notes="Discussed trade-in value.")
        assert error is None
        assert ended["notes"] == "Discussed trade-in value."

    def test_ending_a_call_produces_a_real_communication_with_a_simulated_recording(self):

        agent = _add_employee("EMP-1", "Sales")
        lead = _add_lead()
        call, _ = call_center.route_incoming_call("sales", "555-0001", linked_entity_id=lead.id)
        call_center.connect_call(call["id"])

        ended, error = call_center.end_call(call["id"], agent.id, duration_seconds=120)
        assert error is None
        assert ended["communication_id"] is not None

        comm, _ = communications_hub.get_communication(ended["communication_id"])
        assert comm is not None
        assert comm["channel"] == "phone"
        assert comm["recording"] is not None
        assert comm["recording"]["basis"] == "simulated_call_recording"


class TestMarkMissed:

    def test_rejects_an_unknown_call(self):

        missed, error = call_center.mark_missed("CALL-GHOST")
        assert missed is None
        assert error == "Call 'CALL-GHOST' not found."

    def test_rejects_marking_missed_a_call_that_is_not_ringing(self):

        agent = _add_employee("EMP-1", "Sales")
        call, _ = call_center.route_incoming_call("sales", "555-0001")
        call_center.connect_call(call["id"])

        missed, error = call_center.mark_missed(call["id"])
        assert missed is None
        assert error == "Call is 'connected', not 'ringing' -- cannot mark missed."

    def test_success_sets_zero_duration_and_ended_at(self):

        _add_employee("EMP-1", "Sales")
        call, _ = call_center.route_incoming_call("sales", "555-0001")

        missed, error = call_center.mark_missed(call["id"])
        assert error is None
        assert missed["status"] == "missed"
        assert missed["duration_seconds"] == 0
        assert missed["ended_at"] is not None

    def test_produces_a_communication_with_no_recording(self):

        _add_employee("EMP-1", "Sales")
        call, _ = call_center.route_incoming_call("sales", "555-0001")

        missed, error = call_center.mark_missed(call["id"])
        assert error is None
        assert missed["communication_id"] is not None

        comm, _ = communications_hub.get_communication(missed["communication_id"])
        assert comm is not None
        assert comm["channel"] == "phone"
        assert comm["recording"] is None

    def test_falls_back_to_a_system_actor_when_no_agent_is_assigned(self):

        call, _ = call_center.route_incoming_call("general", "555-0001")
        missed, error = call_center.mark_missed(call["id"])
        assert error is None

        comm, _ = communications_hub.get_communication(missed["communication_id"])
        assert comm["created_by"] == "call_center_system"

    def test_uses_the_assigned_agent_as_the_actor_when_one_exists(self):

        agent = _add_employee("EMP-1", "Sales")
        call, _ = call_center.route_incoming_call("sales", "555-0001")
        missed, _ = call_center.mark_missed(call["id"])

        comm, _ = communications_hub.get_communication(missed["communication_id"])
        assert comm["created_by"] == agent.id


class TestSendToVoicemail:

    def test_rejects_an_unknown_call(self):

        vm, error = call_center.send_to_voicemail("CALL-GHOST")
        assert vm is None
        assert error == "Call 'CALL-GHOST' not found."

    def test_rejects_sending_to_voicemail_a_call_that_is_not_ringing(self):

        agent = _add_employee("EMP-1", "Sales")
        call, _ = call_center.route_incoming_call("sales", "555-0001")
        call_center.connect_call(call["id"])

        vm, error = call_center.send_to_voicemail(call["id"])
        assert vm is None
        assert error == "Call is 'connected', not 'ringing' -- cannot send to voicemail."

    def test_success_populates_a_disclosed_simulated_voicemail(self):

        call, _ = call_center.route_incoming_call("general", "555-0001")
        vm, error = call_center.send_to_voicemail(call["id"])
        assert error is None
        assert vm["status"] == "voicemail"
        assert vm["ended_at"] is not None
        assert vm["duration_seconds"] == vm["voicemail"]["duration_seconds"]

        voicemail = vm["voicemail"]
        assert voicemail["basis"] == "simulated_voicemail"
        assert "SIMULATED" in voicemail["disclaimer"]
        assert 10 <= voicemail["duration_seconds"] < 100
        assert voicemail["audio_url"] == f"https://simulated-voicemails.example/{call['id']}.mp3"
        assert voicemail["transcript"] in call_center._VOICEMAIL_SNIPPETS
        assert voicemail["left_at"] is not None

    def test_the_simulated_voicemail_is_deterministic_per_call_id(self):

        # left_at is a real "now" timestamp stamped at generation time, not
        # part of the seeded/deterministic content -- everything else (basis,
        # disclaimer, duration, audio_url, transcript) is seeded off the call
        # id itself and must match exactly across repeat calls.
        first = call_center._simulate_voicemail("CALL-00042")
        second = call_center._simulate_voicemail("CALL-00042")
        first_stable = {k: v for k, v in first.items() if k != "left_at"}
        second_stable = {k: v for k, v in second.items() if k != "left_at"}
        assert first_stable == second_stable
        assert first["left_at"] is not None
        assert second["left_at"] is not None

    def test_different_call_ids_can_produce_different_simulated_voicemails(self):

        results = {call_center._simulate_voicemail(f"CALL-{n:05d}")["transcript"] for n in range(20)}
        assert len(results) > 1

    def test_produces_a_communication_with_no_recording_and_a_transcript_preview_body(self):

        call, _ = call_center.route_incoming_call("general", "555-0001")
        vm, error = call_center.send_to_voicemail(call["id"])
        assert error is None
        assert vm["communication_id"] is not None

        comm, _ = communications_hub.get_communication(vm["communication_id"])
        assert comm is not None
        assert comm["channel"] == "phone"
        assert comm["recording"] is None
        assert "Voicemail left:" in comm["body"]


class TestGetCall:

    def test_returns_none_for_an_unknown_id(self):

        assert call_center.get_call("CALL-GHOST") is None

    def test_returns_none_for_an_id_belonging_to_a_different_entity_type(self):

        agent = _add_employee("EMP-1", "Sales")
        assert call_center.get_call(agent.id) is None

    def test_returns_the_full_brief_for_a_real_call(self):

        agent = _add_employee("EMP-1", "Sales")
        created, _ = call_center.route_incoming_call("sales", "555-0001")

        fetched = call_center.get_call(created["id"])
        assert fetched == created


class TestListCalls:

    def test_returns_every_call_when_unfiltered(self):

        _add_employee("EMP-1", "Sales")
        call_center.route_incoming_call("sales", "555-0001")
        call_center.route_incoming_call("general", "555-0002")

        assert len(call_center.list_calls()) == 2

    def test_filters_by_department(self):

        _add_employee("EMP-1", "Sales")
        call_center.route_incoming_call("sales", "555-0001")
        call_center.route_incoming_call("general", "555-0002")

        results = call_center.list_calls(department="sales")
        assert len(results) == 1
        assert results[0]["department"] == "sales"

    def test_filters_by_status(self):

        agent = _add_employee("EMP-1", "Sales")
        call1, _ = call_center.route_incoming_call("sales", "555-0001")
        call_center.route_incoming_call("sales", "555-0002")
        call_center.mark_missed(call1["id"])

        results = call_center.list_calls(status="missed")
        assert len(results) == 1
        assert results[0]["id"] == call1["id"]

    def test_filters_by_assigned_to(self):

        e1 = _add_employee("EMP-1", "Sales")
        e2 = _add_employee("EMP-2", "Sales")
        call_center.place_outbound_call("sales", "555-0001", created_by=e1.id)
        call_center.place_outbound_call("sales", "555-0002", created_by=e2.id)

        results = call_center.list_calls(assigned_to=e1.id)
        assert len(results) == 1
        assert results[0]["assigned_to"] == e1.id

    def test_filters_by_linked_entity_id(self):

        lead = _add_lead()
        call_center.route_incoming_call("general", "555-0001", linked_entity_id=lead.id)
        call_center.route_incoming_call("general", "555-0002")

        results = call_center.list_calls(linked_entity_id=lead.id)
        assert len(results) == 1
        assert results[0]["linked_entity_id"] == lead.id

    def test_sorts_most_recently_created_first(self):

        first, _ = call_center.route_incoming_call("general", "555-0001")
        second, _ = call_center.route_incoming_call("general", "555-0002")

        results = call_center.list_calls()
        assert results[0]["id"] == second["id"]
        assert results[1]["id"] == first["id"]

    def test_limit_caps_the_result_count(self):

        for n in range(5):
            call_center.route_incoming_call("general", f"555-000{n}")

        assert len(call_center.list_calls(limit=2)) == 2


class TestGetAgentWorkload:

    def test_no_department_aggregates_across_the_three_real_rosters(self):

        _add_employee("EMP-1", "Sales")
        _add_employee("EMP-2", "Service")
        _add_employee("EMP-3", "Finance")

        workload = call_center.get_agent_workload()
        departments = {row["department"] for row in workload}
        assert departments == {"sales", "service", "finance"}
        assert len(workload) == 3

    def test_general_has_no_roster_to_report(self):

        workload = call_center.get_agent_workload(department="general")
        assert workload == []

    def test_a_specific_department_is_filtered(self):

        _add_employee("EMP-1", "Sales")
        _add_employee("EMP-2", "Service")

        workload = call_center.get_agent_workload(department="sales")
        assert len(workload) == 1
        assert workload[0]["department"] == "sales"
        assert workload[0]["employee_id"] == "EMP-1"
        assert workload[0]["name"] == "Jordan Agent"

    def test_active_calls_reflects_ringing_and_connected_calls_only(self):

        agent = _add_employee("EMP-1", "Sales")
        call1, _ = call_center.route_incoming_call("sales", "555-0001")
        call2, _ = call_center.route_incoming_call("sales", "555-0002")
        call_center.connect_call(call2["id"])
        call_center.end_call(call2["id"], agent.id)

        workload = call_center.get_agent_workload(department="sales")
        assert workload[0]["active_calls"] == 1


class TestGetCallCenterStats:

    def test_zero_state_reports_a_zero_initialized_status_breakdown(self):

        stats = call_center.get_call_center_stats()
        assert stats["total_calls"] == 0
        assert stats["by_status"] == {"ringing": 0, "connected": 0, "ended": 0, "missed": 0, "voicemail": 0}
        assert stats["active_calls"] == 0
        assert stats["average_ended_call_duration_seconds"] is None
        assert stats["missed_calls"] == 0
        assert stats["voicemails_left"] == 0

    def test_aggregates_a_mix_of_statuses_correctly(self):

        agent = _add_employee("EMP-1", "Sales")

        ringing_call, _ = call_center.route_incoming_call("sales", "555-0001")

        ended_call, _ = call_center.route_incoming_call("sales", "555-0002")
        call_center.connect_call(ended_call["id"])
        call_center.end_call(ended_call["id"], agent.id, duration_seconds=100)

        missed_call, _ = call_center.route_incoming_call("sales", "555-0003")
        call_center.mark_missed(missed_call["id"])

        vm_call, _ = call_center.route_incoming_call("sales", "555-0004")
        call_center.send_to_voicemail(vm_call["id"])

        stats = call_center.get_call_center_stats(department="sales")
        assert stats["total_calls"] == 4
        assert stats["by_status"]["ringing"] == 1
        assert stats["by_status"]["ended"] == 1
        assert stats["by_status"]["missed"] == 1
        assert stats["by_status"]["voicemail"] == 1
        assert stats["active_calls"] == 1
        assert stats["missed_calls"] == 1
        assert stats["voicemails_left"] == 1
        assert stats["average_ended_call_duration_seconds"] == 100.0

    def test_average_duration_is_computed_across_multiple_ended_calls(self):

        agent = _add_employee("EMP-1", "Sales")

        call1, _ = call_center.route_incoming_call("sales", "555-0001")
        call_center.connect_call(call1["id"])
        call_center.end_call(call1["id"], agent.id, duration_seconds=100)

        call2, _ = call_center.route_incoming_call("sales", "555-0002")
        call_center.connect_call(call2["id"])
        call_center.end_call(call2["id"], agent.id, duration_seconds=200)

        stats = call_center.get_call_center_stats()
        assert stats["average_ended_call_duration_seconds"] == 150.0

    def test_filters_by_department(self):

        _add_employee("EMP-1", "Sales")
        _add_employee("EMP-2", "Finance")
        call_center.route_incoming_call("sales", "555-0001")
        call_center.route_incoming_call("finance", "555-0002")

        sales_stats = call_center.get_call_center_stats(department="sales")
        assert sales_stats["total_calls"] == 1
        assert sales_stats["department"] == "sales"


class TestCallCenterApiRoleGating:

    def _seed_ready_call(self, status="ringing"):

        agent = _add_employee("EMP-1", "Sales")
        call, _ = call_center.route_incoming_call("sales", "555-0001")
        if status == "connected":
            call_center.connect_call(call["id"])
        return agent, call

    def test_route_incoming_call_api_gating(self):

        for role in _VIEW_ROLES:
            ledger.reset()
            call = call_center_api.route_incoming_call_api(role, department="general", from_number="555-0001")
            assert "error" not in call

        ledger.reset()
        denied = call_center_api.route_incoming_call_api("BOGUS", department="general", from_number="555-0001")
        assert denied == {"error": "Role 'BOGUS' is not permitted to route an incoming call."}

    def test_place_outbound_call_api_gating(self):

        for role in _VIEW_ROLES:
            ledger.reset()
            agent = _add_employee("EMP-1", "Sales")
            call = call_center_api.place_outbound_call_api(role, agent.id, department="sales", to_number="555-0001")
            assert "error" not in call

        ledger.reset()
        agent = _add_employee("EMP-1", "Sales")
        denied = call_center_api.place_outbound_call_api("BOGUS", agent.id, department="sales", to_number="555-0001")
        assert denied == {"error": "Role 'BOGUS' is not permitted to place an outbound call."}

    def test_reassign_call_api_gating(self):

        for role in _VIEW_ROLES:
            ledger.reset()
            _, call = self._seed_ready_call()
            other = _add_employee("EMP-2", "Sales")
            result = call_center_api.reassign_call_api(role, call["id"], other.id, "EMP-ADMIN")
            assert "error" not in result

        ledger.reset()
        _, call = self._seed_ready_call()
        other = _add_employee("EMP-2", "Sales")
        denied = call_center_api.reassign_call_api("BOGUS", call["id"], other.id, "EMP-ADMIN")
        assert denied == {"error": "Role 'BOGUS' is not permitted to reassign a call."}

    def test_connect_call_api_gating(self):

        for role in _VIEW_ROLES:
            ledger.reset()
            _, call = self._seed_ready_call()
            result = call_center_api.connect_call_api(role, call["id"])
            assert "error" not in result

        ledger.reset()
        _, call = self._seed_ready_call()
        denied = call_center_api.connect_call_api("BOGUS", call["id"])
        assert denied == {"error": "Role 'BOGUS' is not permitted to connect a call."}

    def test_end_call_api_gating(self):

        for role in _VIEW_ROLES:
            ledger.reset()
            agent, call = self._seed_ready_call(status="connected")
            result = call_center_api.end_call_api(role, call["id"], agent.id)
            assert "error" not in result

        ledger.reset()
        agent, call = self._seed_ready_call(status="connected")
        denied = call_center_api.end_call_api("BOGUS", call["id"], agent.id)
        assert denied == {"error": "Role 'BOGUS' is not permitted to end a call."}

    def test_mark_missed_api_gating(self):

        for role in _VIEW_ROLES:
            ledger.reset()
            _, call = self._seed_ready_call()
            result = call_center_api.mark_missed_api(role, call["id"])
            assert "error" not in result

        ledger.reset()
        _, call = self._seed_ready_call()
        denied = call_center_api.mark_missed_api("BOGUS", call["id"])
        assert denied == {"error": "Role 'BOGUS' is not permitted to mark a call as missed."}

    def test_send_to_voicemail_api_gating(self):

        for role in _VIEW_ROLES:
            ledger.reset()
            _, call = self._seed_ready_call()
            result = call_center_api.send_to_voicemail_api(role, call["id"])
            assert "error" not in result

        ledger.reset()
        _, call = self._seed_ready_call()
        denied = call_center_api.send_to_voicemail_api("BOGUS", call["id"])
        assert denied == {"error": "Role 'BOGUS' is not permitted to send a call to voicemail."}

    def test_get_call_api_gating(self):

        _, call = self._seed_ready_call()

        for role in _VIEW_ROLES:
            result = call_center_api.get_call_api(role, call["id"])
            assert "error" not in result

        denied = call_center_api.get_call_api("BOGUS", call["id"])
        assert denied == {"error": "Role 'BOGUS' is not permitted to view this call."}

    def test_get_call_api_reports_a_not_found_error_for_a_real_role(self):

        result = call_center_api.get_call_api("ADMIN", "CALL-GHOST")
        assert result == {"error": "Call 'CALL-GHOST' not found."}

    def test_list_calls_api_gating(self):

        for role in _VIEW_ROLES:
            result = call_center_api.list_calls_api(role)
            assert isinstance(result, list)

        denied = call_center_api.list_calls_api("BOGUS")
        assert denied == {"error": "Role 'BOGUS' is not permitted to view calls."}

    def test_get_agent_workload_api_gating(self):

        for role in _VIEW_ROLES:
            result = call_center_api.get_agent_workload_api(role)
            assert isinstance(result, list)

        denied = call_center_api.get_agent_workload_api("BOGUS")
        assert denied == {"error": "Role 'BOGUS' is not permitted to view agent workload."}

    def test_get_call_center_stats_api_gating(self):

        for role in _VIEW_ROLES:
            result = call_center_api.get_call_center_stats_api(role)
            assert "error" not in result
            assert "total_calls" in result

        denied = call_center_api.get_call_center_stats_api("BOGUS")
        assert denied == {"error": "Role 'BOGUS' is not permitted to view Call Center stats."}
