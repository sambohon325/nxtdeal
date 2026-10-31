"""
Tests for core/appointment_scheduling.py -- Appointments' "smart-scheduling
upgrades" (Capacity Planning, Technician/Rep Matching, Automated Customer
Communication (SIMULATED), and real Pre-Visit Check-In), shared across Sales
and Service on top of core/appointments.py's own Appointment entity. Added
per BUILD_QUEUE.md's standing "convert to a real pytest suite as each module
gets touched" rule (see CLAUDE.md's missing_test_coverage / CAF-00123 work).

Fixtures use the real core.appointments.create_appointment() to build
genuine Appointment entities (that module's own already-tested, simple
behavior) rather than hand-constructing entities, plus real Employee/
Customer/Lead/Vehicle entities seeded directly into the ledger. Both
core.appointments.save_graph and core.appointment_scheduling.save_graph are
stubbed -- appointment_scheduling.py calls core.appointments.update_status()
internally, which persists via appointments.py's own imported save_graph
reference, so both namespaces need patching, same "patch the importing
module's own reference" rule test_appointments.py already documents. Fully
deterministic, seed-independent, never touches the real graph.json.
"""

import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

from datetime import datetime, timezone, timedelta

import pytest

from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.entity_types import EMPLOYEE, CUSTOMER, LEAD, VEHICLE

from core import appointments
from core import appointment_scheduling as sched


# --------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def fixed_scheduling_clock(monkeypatch):
    """Keep now+1h on the same date as today, including runs after 23:00 UTC."""
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            fixed = cls(2026, 9, 30, 12, 0, tzinfo=timezone.utc)
            return fixed.astimezone(tz) if tz is not None else fixed.replace(tzinfo=None)

    monkeypatch.setattr(sys.modules[__name__], "datetime", FixedDateTime)
    monkeypatch.setattr(appointments, "datetime", FixedDateTime)
    monkeypatch.setattr(sched, "datetime", FixedDateTime)


@pytest.fixture(autouse=True)
def fresh_singletons():
    def _reset():
        ledger.reset()
        for prefix in id_generator.counters:
            id_generator.counters[prefix] = 0

    _reset()
    yield
    _reset()


@pytest.fixture(autouse=True)
def no_real_disk_writes(monkeypatch):
    monkeypatch.setattr(appointments, "save_graph", lambda filepath: None)
    monkeypatch.setattr(sched, "save_graph", lambda filepath: None)


def _iso_in(**delta):
    return (datetime.now(timezone.utc) + timedelta(**delta)).isoformat()


def _today():
    return datetime.now(timezone.utc).date().isoformat()


def _make(department="Sales", appointment_type="showroom_visit", start=None, **kw):
    return appointments.create_appointment(
        department=department,
        appointment_type=appointment_type,
        scheduled_start=start or _iso_in(hours=1),
        created_by="EMP-00001",
        **kw,
    )


def _add_employee(entity_id="EMP-00010", department="Sales", first="Jane", last="Doe", title="Sales Rep"):
    ledger.add_entity(Entity(
        id=entity_id,
        entity_type=EMPLOYEE,
        attributes={"Department": department, "FirstName": first, "LastName": last, "Title": title},
    ))
    return entity_id


def _add_customer(entity_id="CUST-00001", first="Alex", last="Buyer"):
    ledger.add_entity(Entity(
        id=entity_id, entity_type=CUSTOMER,
        attributes={"FirstName": first, "LastName": last},
    ))
    return entity_id


def _add_lead(entity_id="LEAD-00001", first="Sam", last="Prospect"):
    ledger.add_entity(Entity(
        id=entity_id, entity_type=LEAD,
        attributes={"FirstName": first, "LastName": last},
    ))
    return entity_id


def _add_vehicle(entity_id="VEH-00001", year="2024", make="Toyota", model="Camry"):
    ledger.add_entity(Entity(
        id=entity_id, entity_type=VEHICLE,
        attributes={"Year": year, "Make": make, "Model": model},
    ))
    return entity_id


# --------------------------------------------------------------------------
# _now / _employee_name
# --------------------------------------------------------------------------


class TestNow:
    def test_now_returns_aware_datetime(self):
        now = sched._now()
        assert now.tzinfo is not None


class TestEmployeeName:
    def test_none_employee_returns_none(self):
        assert sched._employee_name(None) is None

    def test_full_name_returned(self):
        _add_employee("EMP-1", first="Jane", last="Doe")
        emp = ledger.get_entity("EMP-1")
        assert sched._employee_name(emp) == "Jane Doe"

    def test_missing_first_or_last_name_still_works(self):
        ledger.add_entity(Entity(id="EMP-2", entity_type=EMPLOYEE, attributes={"LastName": "Doe"}))
        emp = ledger.get_entity("EMP-2")
        assert sched._employee_name(emp) == "Doe"

    def test_no_name_fields_returns_empty_string(self):
        ledger.add_entity(Entity(id="EMP-3", entity_type=EMPLOYEE, attributes={}))
        emp = ledger.get_entity("EMP-3")
        assert sched._employee_name(emp) == ""


# --------------------------------------------------------------------------
# _employees_for_department
# --------------------------------------------------------------------------


class TestEmployeesForDepartment:
    def test_matches_case_insensitively(self):
        _add_employee("EMP-1", department="sales")
        _add_employee("EMP-2", department="SALES")
        _add_employee("EMP-3", department="Service")

        result = sched._employees_for_department("Sales")

        ids = {e.id for e in result}
        assert ids == {"EMP-1", "EMP-2"}

    def test_no_matching_employees_returns_empty_list(self):
        _add_employee("EMP-1", department="Service")
        assert sched._employees_for_department("Sales") == []

    def test_employee_missing_department_attribute_is_excluded(self):
        ledger.add_entity(Entity(id="EMP-1", entity_type=EMPLOYEE, attributes={}))
        assert sched._employees_for_department("Sales") == []


# --------------------------------------------------------------------------
# _find_appointment_by_token
# --------------------------------------------------------------------------


class TestFindAppointmentByToken:
    def test_not_found_returns_none(self):
        assert sched._find_appointment_by_token("nope") is None

    def test_found_by_matching_token(self):
        appt = _make()
        gen = sched.generate_checkin_link(appt.id, created_by="EMP-00001")
        token = gen["token"]

        found = sched._find_appointment_by_token(token)

        assert found is not None
        assert found.id == appt.id

    def test_appointment_with_no_checkin_link_is_not_matched(self):
        _make()
        assert sched._find_appointment_by_token("random-token") is None


# --------------------------------------------------------------------------
# _linked_brief
# --------------------------------------------------------------------------


class TestLinkedBrief:
    def test_all_none_when_nothing_linked(self):
        appt = _make()
        brief = sched._linked_brief(appt)
        assert brief == {"person_name": None, "vehicle": None}

    def test_resolves_customer_name(self):
        _add_customer("CUST-1", first="Alex", last="Buyer")
        appt = _make(customer_id="CUST-1")
        brief = sched._linked_brief(appt)
        assert brief["person_name"] == "Alex Buyer"

    def test_resolves_lead_name_when_no_customer(self):
        _add_lead("LEAD-1", first="Sam", last="Prospect")
        appt = _make(lead_id="LEAD-1")
        brief = sched._linked_brief(appt)
        assert brief["person_name"] == "Sam Prospect"

    def test_customer_preferred_over_lead_when_both_present(self):
        _add_customer("CUST-1", first="Alex", last="Buyer")
        _add_lead("LEAD-1", first="Sam", last="Prospect")
        appt = _make(customer_id="CUST-1", lead_id="LEAD-1")
        brief = sched._linked_brief(appt)
        assert brief["person_name"] == "Alex Buyer"

    def test_resolves_vehicle_description(self):
        _add_vehicle("VEH-1", year="2024", make="Toyota", model="Camry")
        appt = _make(vehicle_id="VEH-1")
        brief = sched._linked_brief(appt)
        assert brief["vehicle"] == "2024 Toyota Camry"

    def test_unresolvable_linked_ids_still_produce_none(self):
        # create_appointment() itself validates customer_id/lead_id against the
        # ledger and rejects an unknown one -- to exercise _linked_brief()'s own
        # defensive handling of a dangling reference, build the Appointment
        # directly rather than going through that validation.
        appt = _make()
        appt.attributes["customer_id"] = "CUST-99999"
        appt.attributes["vehicle_id"] = "VEH-99999"

        brief = sched._linked_brief(appt)

        assert brief == {"person_name": None, "vehicle": None}


# --------------------------------------------------------------------------
# get_capacity_planning
# --------------------------------------------------------------------------


class TestGetCapacityPlanning:
    def test_rejects_unknown_department(self):
        result = sched.get_capacity_planning("Marketing")
        assert "error" in result

    def test_empty_department_no_appointments_no_employees(self):
        result = sched.get_capacity_planning("Sales")

        assert result["department"] == "Sales"
        assert result["employees"] == []
        assert result["total_booked"] == 0
        assert result["assumed_daily_capacity_per_employee"] == 8

    def test_defaults_date_to_today(self):
        result = sched.get_capacity_planning("Sales")
        assert result["date"] == _today()

    def test_counts_real_booked_appointments_per_employee(self):
        _add_employee("EMP-1", department="Sales")
        today_start = _iso_in(hours=1)
        _make(department="Sales", start=today_start, assigned_to="EMP-1")
        _make(department="Sales", start=today_start, assigned_to="EMP-1")

        result = sched.get_capacity_planning("Sales", date=_today())

        row = next(r for r in result["employees"] if r["employee_id"] == "EMP-1")
        assert row["booked_count"] == 2
        assert row["available_slots"] == 6
        assert row["at_capacity"] is False

    def test_cancelled_and_no_show_excluded_from_booked_count(self):
        _add_employee("EMP-1", department="Sales")
        appt = _make(department="Sales", assigned_to="EMP-1")
        appointments.update_status(appt.id, "cancelled", "EMP-00001")

        result = sched.get_capacity_planning("Sales", date=_today())

        row = next(r for r in result["employees"] if r["employee_id"] == "EMP-1")
        assert row["booked_count"] == 0

    def test_employee_with_no_appointments_shows_zero_booked(self):
        _add_employee("EMP-1", department="Sales")

        result = sched.get_capacity_planning("Sales", date=_today())

        row = result["employees"][0]
        assert row["employee_id"] == "EMP-1"
        assert row["booked_count"] == 0
        assert row["available_slots"] == 8

    def test_assigned_employee_not_on_roster_still_shown(self):
        # assigned_to references an id with no matching Employee entity on file --
        # still surfaced, not silently dropped, matching the module's own comment.
        _make(department="Sales", assigned_to="EMP-GHOST")

        result = sched.get_capacity_planning("Sales", date=_today())

        row = next(r for r in result["employees"] if r["employee_id"] == "EMP-GHOST")
        assert row["name"] == "EMP-GHOST"
        assert row["title"] is None
        assert row["booked_count"] == 1

    def test_at_capacity_flag_set_when_booked_meets_capacity(self):
        _add_employee("EMP-1", department="Service")  # capacity 6
        for _ in range(6):
            _make(department="Service", appointment_type="service", assigned_to="EMP-1")

        result = sched.get_capacity_planning("Service", date=_today())

        row = result["employees"][0]
        assert row["booked_count"] == 6
        assert row["at_capacity"] is True
        assert row["available_slots"] == 0

    def test_rows_sorted_by_available_slots_descending(self):
        _add_employee("EMP-1", department="Sales")
        _add_employee("EMP-2", department="Sales")
        _make(department="Sales", assigned_to="EMP-1")
        _make(department="Sales", assigned_to="EMP-1")
        _make(department="Sales", assigned_to="EMP-1")

        result = sched.get_capacity_planning("Sales", date=_today())

        slots = [r["available_slots"] for r in result["employees"]]
        assert slots == sorted(slots, reverse=True)
        assert result["employees"][0]["employee_id"] == "EMP-2"

    def test_totals_and_pct_booked_computed_correctly(self):
        _add_employee("EMP-1", department="Sales")
        _add_employee("EMP-2", department="Sales")
        _make(department="Sales", assigned_to="EMP-1")
        _make(department="Sales", assigned_to="EMP-1")

        result = sched.get_capacity_planning("Sales", date=_today())

        assert result["total_booked"] == 2
        assert result["total_capacity"] == 16
        assert result["pct_booked"] == 12.5

    def test_pct_booked_zero_when_no_employees_at_all(self):
        result = sched.get_capacity_planning("Sales", date=_today())
        assert result["total_capacity"] == 8  # falls back to bare capacity
        assert result["pct_booked"] == 0.0

    def test_note_mentions_heuristic_and_the_assumed_capacity(self):
        result = sched.get_capacity_planning("Sales", date=_today())
        assert "HEURISTIC" in result["note"]
        assert "8" in result["note"]

    def test_only_matching_department_appointments_counted(self):
        _add_employee("EMP-1", department="Sales")
        _make(department="Sales", assigned_to="EMP-1")
        _add_employee("EMP-2", department="Service")
        _make(department="Service", appointment_type="service", assigned_to="EMP-2")

        result = sched.get_capacity_planning("Sales", date=_today())

        assert len(result["employees"]) == 1
        assert result["employees"][0]["employee_id"] == "EMP-1"
        assert result["employees"][0]["booked_count"] == 1

    def test_only_matching_date_appointments_counted(self):
        _add_employee("EMP-1", department="Sales")
        _make(department="Sales", assigned_to="EMP-1", start=_iso_in(hours=1))
        _make(department="Sales", assigned_to="EMP-1", start=_iso_in(days=5))

        result = sched.get_capacity_planning("Sales", date=_today())

        row = result["employees"][0]
        assert row["booked_count"] == 1


# --------------------------------------------------------------------------
# suggest_assignee
# --------------------------------------------------------------------------


class TestSuggestAssignee:
    def test_propagates_capacity_planning_error(self):
        result = sched.suggest_assignee("Marketing")
        assert "error" in result

    def test_no_employees_returns_error(self):
        result = sched.suggest_assignee("Sales", date=_today())
        assert "error" in result
        assert "No Sales employees" in result["error"]

    def test_returns_least_loaded_employee(self):
        _add_employee("EMP-1", department="Sales")
        _add_employee("EMP-2", department="Sales")
        _make(department="Sales", assigned_to="EMP-1")
        _make(department="Sales", assigned_to="EMP-1")

        result = sched.suggest_assignee("Sales", date=_today())

        assert result["recommended_employee_id"] == "EMP-2"
        assert result["at_capacity"] is False
        assert "not an AI match" in result["note"]

    def test_every_employee_at_capacity_still_returns_least_loaded(self):
        _add_employee("EMP-1", department="Service")  # capacity 6
        for _ in range(6):
            _make(department="Service", appointment_type="service", assigned_to="EMP-1")

        result = sched.suggest_assignee("Service", date=_today())

        assert result["recommended_employee_id"] == "EMP-1"
        assert result["at_capacity"] is True
        assert "at or over the assumed daily capacity" in result["note"]


# --------------------------------------------------------------------------
# send_appointment_reminder / get_reminder_history
# --------------------------------------------------------------------------


class TestSendAppointmentReminder:
    def test_not_found_returns_error(self):
        result = sched.send_appointment_reminder("APPT-99999", "sms", sent_by="EMP-00001")
        assert "error" in result

    def test_invalid_channel_returns_error(self):
        appt = _make()
        result = sched.send_appointment_reminder(appt.id, "carrier_pigeon", sent_by="EMP-00001")
        assert "error" in result

    def test_terminal_status_rejects_reminder(self):
        appt = _make()
        appointments.update_status(appt.id, "completed", "EMP-00001")

        result = sched.send_appointment_reminder(appt.id, "sms", sent_by="EMP-00001")

        assert "error" in result
        assert "no reminder needed" in result["error"]

    def test_successful_reminder_appended_with_correct_shape(self):
        appt = _make()

        result = sched.send_appointment_reminder(appt.id, "sms", sent_by="EMP-00001")

        assert "error" not in result
        assert len(result["reminders_sent"]) == 1
        reminder = result["reminders_sent"][0]
        assert reminder["channel"] == "sms"
        assert reminder["sent_by"] == "EMP-00001"
        assert reminder["basis"] == "simulated_communication"
        assert "SIMULATED" in result["disclaimer"]

    def test_multiple_reminders_accumulate(self):
        appt = _make()

        sched.send_appointment_reminder(appt.id, "sms", sent_by="EMP-00001")
        result = sched.send_appointment_reminder(appt.id, "email", sent_by="EMP-00002")

        assert len(result["reminders_sent"]) == 2
        assert result["reminders_sent"][0]["channel"] == "sms"
        assert result["reminders_sent"][1]["channel"] == "email"

    def test_reminder_persisted_on_the_appointment_entity(self):
        appt = _make()
        sched.send_appointment_reminder(appt.id, "call", sent_by="EMP-00001")

        refetched = appointments.get_appointment(appt.id)
        assert len(refetched.attributes["reminders_sent"]) == 1


class TestGetReminderHistory:
    def test_not_found_returns_error(self):
        result = sched.get_reminder_history("APPT-99999")
        assert "error" in result

    def test_empty_history_returns_empty_list(self):
        appt = _make()
        result = sched.get_reminder_history(appt.id)
        assert result["reminders_sent"] == []

    def test_populated_history_returned(self):
        appt = _make()
        sched.send_appointment_reminder(appt.id, "sms", sent_by="EMP-00001")

        result = sched.get_reminder_history(appt.id)

        assert len(result["reminders_sent"]) == 1
        assert result["reminders_sent"][0]["channel"] == "sms"


# --------------------------------------------------------------------------
# generate_checkin_link / get_checkin_link_status / revoke_checkin_link
# --------------------------------------------------------------------------


class TestGenerateCheckinLink:
    def test_not_found_returns_error(self):
        result = sched.generate_checkin_link("APPT-99999", created_by="EMP-00001")
        assert "error" in result

    def test_terminal_status_rejects_link_generation(self):
        appt = _make()
        appointments.update_status(appt.id, "no_show", "EMP-00001")

        result = sched.generate_checkin_link(appt.id, created_by="EMP-00001")

        assert "error" in result
        assert "can't generate a check-in link" in result["error"]

    def test_successful_generation_returns_real_token(self):
        appt = _make()

        result = sched.generate_checkin_link(appt.id, created_by="EMP-00001")

        assert "error" not in result
        assert result["appointment_id"] == appt.id
        assert isinstance(result["token"], str) and len(result["token"]) > 10
        assert result["path"] == f"/checkin/{result['token']}"

    def test_link_persisted_on_the_appointment_entity(self):
        appt = _make()
        result = sched.generate_checkin_link(appt.id, created_by="EMP-00001")

        refetched = appointments.get_appointment(appt.id)
        link = refetched.attributes["checkin_link"]
        assert link["token"] == result["token"]
        assert link["created_by"] == "EMP-00001"
        assert link["revoked"] is False

    def test_generating_twice_replaces_the_prior_token(self):
        appt = _make()
        first = sched.generate_checkin_link(appt.id, created_by="EMP-00001")
        second = sched.generate_checkin_link(appt.id, created_by="EMP-00002")

        assert first["token"] != second["token"]
        status = sched.get_checkin_link_status(appt.id)
        assert status["token"] == second["token"]


class TestGetCheckinLinkStatus:
    def test_not_found_returns_error(self):
        result = sched.get_checkin_link_status("APPT-99999")
        assert "error" in result

    def test_no_link_yet_reports_exists_false(self):
        appt = _make()
        result = sched.get_checkin_link_status(appt.id)
        assert result == {"appointment_id": appt.id, "exists": False}

    def test_existing_link_reports_full_details(self):
        appt = _make()
        gen = sched.generate_checkin_link(appt.id, created_by="EMP-00001")

        result = sched.get_checkin_link_status(appt.id)

        assert result["exists"] is True
        assert result["token"] == gen["token"]
        assert result["revoked"] is False
        assert result["path"] == f"/checkin/{gen['token']}"


class TestRevokeCheckinLink:
    def test_not_found_returns_error(self):
        result = sched.revoke_checkin_link("APPT-99999", revoked_by="EMP-00001")
        assert "error" in result

    def test_no_link_exists_returns_error(self):
        appt = _make()
        result = sched.revoke_checkin_link(appt.id, revoked_by="EMP-00001")
        assert "error" in result
        assert "No check-in link exists" in result["error"]

    def test_already_revoked_returns_error(self):
        appt = _make()
        sched.generate_checkin_link(appt.id, created_by="EMP-00001")
        sched.revoke_checkin_link(appt.id, revoked_by="EMP-00001")

        result = sched.revoke_checkin_link(appt.id, revoked_by="EMP-00002")

        assert "error" in result
        assert "already revoked" in result["error"]

    def test_successful_revoke(self):
        appt = _make()
        sched.generate_checkin_link(appt.id, created_by="EMP-00001")

        result = sched.revoke_checkin_link(appt.id, revoked_by="EMP-00002")

        assert result == {"appointment_id": appt.id, "revoked": True}
        status = sched.get_checkin_link_status(appt.id)
        assert status["revoked"] is True
        assert status["revoked_by"] == "EMP-00002"


# --------------------------------------------------------------------------
# get_public_checkin_view
# --------------------------------------------------------------------------


class TestGetPublicCheckinView:
    def test_invalid_token_returns_error(self):
        result = sched.get_public_checkin_view("bogus-token")
        assert "error" in result
        assert "invalid or has expired" in result["error"]

    def test_valid_token_returns_full_view(self):
        _add_customer("CUST-1", first="Alex", last="Buyer")
        _add_vehicle("VEH-1", year="2024", make="Honda", model="Accord")
        appt = _make(customer_id="CUST-1", vehicle_id="VEH-1")
        gen = sched.generate_checkin_link(appt.id, created_by="EMP-00001")

        result = sched.get_public_checkin_view(gen["token"])

        assert result["revoked"] is False
        assert result["department"] == "Sales"
        assert result["appointment_type"] == "showroom_visit"
        assert result["status"] == "scheduled"
        assert result["person_name"] == "Alex Buyer"
        assert result["vehicle"] == "2024 Honda Accord"
        assert result["checkin"] is None

    def test_revoked_link_discloses_no_appointment_data(self, monkeypatch):
        appt = _make()
        gen = sched.generate_checkin_link(appt.id, created_by="EMP-00001")
        sched.revoke_checkin_link(appt.id, revoked_by="EMP-00001")

        def forbidden_projection(*args):
            pytest.fail("Revoked token must not resolve customer details")
        monkeypatch.setattr(sched, "_linked_brief", forbidden_projection)
        result = sched.get_public_checkin_view(gen["token"])

        assert set(result) == {"error"}
        assert "revoked" in result["error"]


# --------------------------------------------------------------------------
# record_public_checkin
# --------------------------------------------------------------------------


class TestRecordPublicCheckin:
    def test_invalid_token_returns_error(self):
        result = sched.record_public_checkin("bogus-token", "wait")
        assert "error" in result
        assert "invalid or has expired" in result["error"]

    def test_revoked_link_rejects_checkin(self):
        appt = _make()
        gen = sched.generate_checkin_link(appt.id, created_by="EMP-00001")
        sched.revoke_checkin_link(appt.id, revoked_by="EMP-00001")

        result = sched.record_public_checkin(gen["token"], "wait")

        assert "error" in result
        assert "revoked" in result["error"]

    def test_already_checked_in_rejects_second_submission(self):
        appt = _make()
        gen = sched.generate_checkin_link(appt.id, created_by="EMP-00001")
        sched.record_public_checkin(gen["token"], "wait")

        result = sched.record_public_checkin(gen["token"], "drop_off")

        assert "error" in result
        assert "already checked in" in result["error"]

    def test_terminal_status_rejects_checkin(self):
        appt = _make()
        gen = sched.generate_checkin_link(appt.id, created_by="EMP-00001")
        appointments.update_status(appt.id, "cancelled", "EMP-00001")

        result = sched.record_public_checkin(gen["token"], "wait")

        assert "error" in result
        assert "no longer available" in result["error"]

    def test_invalid_drop_off_or_wait_value_rejected(self):
        appt = _make()
        gen = sched.generate_checkin_link(appt.id, created_by="EMP-00001")

        result = sched.record_public_checkin(gen["token"], "teleport")

        assert "error" in result
        assert "drop_off_or_wait" in result["error"]

    def test_successful_checkin_sets_checkin_attributes_with_customer_sentinel(self):
        appt = _make()
        gen = sched.generate_checkin_link(appt.id, created_by="EMP-00001")

        result = sched.record_public_checkin(gen["token"], "drop_off", contact_preference="text", notes="Running 10 min late")

        assert "error" not in result
        assert result["checkin"]["drop_off_or_wait"] == "drop_off"
        assert result["checkin"]["contact_preference"] == "text"
        assert result["checkin"]["notes"] == "Running 10 min late"
        assert result["checkin"]["submitted_by"] == sched.CUSTOMER_SENTINEL

    def test_scheduled_appointment_moves_to_confirmed_on_checkin(self):
        appt = _make()
        assert appt.attributes["status"] == "scheduled"
        gen = sched.generate_checkin_link(appt.id, created_by="EMP-00001")

        sched.record_public_checkin(gen["token"], "wait")

        refetched = appointments.get_appointment(appt.id)
        assert refetched.attributes["status"] == "confirmed"
        history = refetched.attributes["status_history"]
        assert history[-1]["status"] == "confirmed"
        assert history[-1]["by"] == sched.CUSTOMER_SENTINEL

    def test_already_confirmed_appointment_does_not_re_trigger_update_status(self):
        appt = _make()
        appointments.update_status(appt.id, "confirmed", "EMP-00001")
        history_len_before = len(appointments.get_appointment(appt.id).attributes["status_history"])

        gen = sched.generate_checkin_link(appt.id, created_by="EMP-00001")
        result = sched.record_public_checkin(gen["token"], "wait")

        assert "error" not in result
        refetched = appointments.get_appointment(appt.id)
        assert refetched.attributes["status"] == "confirmed"
        # status_history should have gained no new entry, since record_public_checkin
        # only calls update_status() when the current status is exactly "scheduled"
        assert len(refetched.attributes["status_history"]) == history_len_before

    def test_checkin_persisted_and_view_reflects_it_afterward(self):
        appt = _make()
        gen = sched.generate_checkin_link(appt.id, created_by="EMP-00001")
        sched.record_public_checkin(gen["token"], "drop_off")

        view = sched.get_public_checkin_view(gen["token"])

        assert view["checkin"]["drop_off_or_wait"] == "drop_off"
        assert view["status"] == "confirmed"

@pytest.mark.parametrize('legacy', [False, True])
def test_checkin_link_expires_at_issuance_boundary(monkeypatch, legacy):
    from datetime import timedelta
    appt = _make()
    token = sched.generate_checkin_link(appt.id, 'EMP-00001')['token']
    link = appt.attributes['checkin_link']
    issued = datetime.fromisoformat(link['created_at'])
    if legacy:
        link.pop('expires_at')
    monkeypatch.setattr(sched, '_now', lambda: issued + timedelta(days=7) - timedelta(microseconds=1))
    assert 'error' not in sched.get_public_checkin_view(token)
    monkeypatch.setattr(sched, '_now', lambda: issued + timedelta(days=7))
    assert set(sched.get_public_checkin_view(token)) == {'error'}
    assert 'expired' in sched.record_public_checkin(token, 'wait')['error']
    assert not appt.attributes.get('checkin')

@pytest.mark.parametrize('created', [None, '', 'bad-date', '2026-09-30T12:00:00', '2099-01-01T00:00:00+00:00'])
def test_invalid_or_future_issuance_cannot_read_or_write(created):
    appt = _make()
    token = sched.generate_checkin_link(appt.id, 'EMP-00001')['token']
    appt.attributes['checkin_link']['created_at'] = created
    assert set(sched.get_public_checkin_view(token)) == {'error'}
    assert 'error' in sched.record_public_checkin(token, 'wait')
    assert not appt.attributes.get('checkin')

def test_explicit_deadline_cannot_extend_maximum_lifetime(monkeypatch):
    from datetime import timedelta
    appt = _make()
    token = sched.generate_checkin_link(appt.id, 'EMP-00001')['token']
    link = appt.attributes['checkin_link']
    issued = datetime.fromisoformat(link['created_at'])
    link['expires_at'] = (issued + timedelta(days=100)).isoformat()
    monkeypatch.setattr(sched, '_now', lambda: issued + timedelta(days=8))
    assert 'expired' in sched.get_public_checkin_view(token)['error']

@pytest.mark.parametrize('status', ['scheduled', 'confirmed', 'arrived'])
def test_checkin_save_failure_restores_state_and_allows_retry(monkeypatch, status):
    from copy import deepcopy

    appt = _make()
    token = sched.generate_checkin_link(appt.id, 'EMP-00001')['token']
    if status != 'scheduled':
        appointments.update_status(appt.id, status, 'EMP-00001')
    previous = deepcopy(appt.attributes)
    calls = []

    def fail(path):
        calls.append(deepcopy(appt.attributes))
        raise OSError('check-in persistence unavailable')

    monkeypatch.setattr(appointments, 'save_graph', fail)
    monkeypatch.setattr(sched, 'save_graph', fail)
    with pytest.raises(OSError, match='persistence unavailable'):
        sched.record_public_checkin(token, 'wait', 'text', 'Customer note')
    assert len(calls) == 1
    assert calls[0]['checkin']['notes'] == 'Customer note'
    assert calls[0]['status'] == ('confirmed' if status == 'scheduled' else status)
    assert appt.attributes == previous
    assert sched.get_public_checkin_view(token)['checkin'] is None

    calls.clear()
    monkeypatch.setattr(appointments, 'save_graph', lambda path: calls.append(deepcopy(appt.attributes)))
    monkeypatch.setattr(sched, 'save_graph', lambda path: calls.append(deepcopy(appt.attributes)))
    result = sched.record_public_checkin(token, 'wait')
    assert 'error' not in result
    assert len(calls) == 1
    assert result['status'] == ('confirmed' if status == 'scheduled' else status)
    assert len(appt.attributes['status_history']) == len(previous['status_history']) + (status == 'scheduled')


def test_checkin_confirmation_and_customer_details_survive_one_save(monkeypatch, tmp_path):
    appt = _make()
    token = sched.generate_checkin_link(appt.id, 'EMP-00001')['token']
    path = str(tmp_path / 'confirmed-checkin.json')
    calls = []

    def persist(_):
        calls.append(appt.id)
        ledger.save(path)

    monkeypatch.setattr(appointments, 'save_graph', persist)
    monkeypatch.setattr(sched, 'save_graph', persist)
    result = sched.record_public_checkin(token, 'drop_off', 'text', 'Customer request')
    assert result['status'] == 'confirmed'
    assert calls == [appt.id]
    ledger.reset()
    assert ledger.load(path) is True
    restored = appointments.get_appointment(appt.id)
    assert restored.attributes['status'] == 'confirmed'
    assert restored.attributes['status_history'][-1]['by'] == sched.CUSTOMER_SENTINEL
    view = sched.get_public_checkin_view(token)
    assert view['checkin']['notes'] == 'Customer request'
    assert view['checkin']['submitted_by'] == sched.CUSTOMER_SENTINEL


@pytest.mark.parametrize('action', ['create', 'replace', 'revoke', 'reminder'])
def test_scheduling_action_failure_preserves_confirmed_state(monkeypatch, action):
    from copy import deepcopy

    appt = _make()
    old_token = None
    if action in ('replace', 'revoke'):
        old_token = sched.generate_checkin_link(appt.id, 'EMP-00001')['token']
    previous = deepcopy(appt.attributes)

    def fail(_):
        raise OSError('scheduling persistence unavailable')

    monkeypatch.setattr(sched, 'save_graph', fail)
    def perform():
        if action in ('create', 'replace'):
            return sched.generate_checkin_link(appt.id, 'EMP-00002')
        if action == 'revoke':
            return sched.revoke_checkin_link(appt.id, 'EMP-00002')
        return sched.send_appointment_reminder(appt.id, 'sms', 'EMP-00002')

    with pytest.raises(OSError, match='persistence unavailable'):
        perform()
    assert appt.attributes == previous
    if old_token:
        assert 'error' not in sched.get_public_checkin_view(old_token)
    else:
        assert sched.get_checkin_link_status(appt.id)['exists'] is False
    assert sched.get_reminder_history(appt.id)['reminders_sent'] == []

    monkeypatch.setattr(sched, 'save_graph', lambda _: None)
    result = perform()
    assert 'error' not in result
    if action == 'revoke':
        assert 'revoked' in sched.get_public_checkin_view(old_token)['error']
    elif action == 'replace':
        assert 'error' in sched.get_public_checkin_view(old_token)
        assert 'error' not in sched.get_public_checkin_view(result['token'])
    elif action == 'create':
        assert 'error' not in sched.get_public_checkin_view(result['token'])
    else:
        assert len(result['reminders_sent']) == 1
        assert result['reminders_sent'][0]['basis'] == 'simulated_communication'


@pytest.mark.parametrize('field,value', [('contact_preference','x'*201), ('notes','x'*2001), ('contact_preference',None), ('notes',{'unexpected':'object'})])
def test_public_checkin_rejects_invalid_details_without_mutation(monkeypatch, field, value):
    from copy import deepcopy
    appt = _make()
    token = sched.generate_checkin_link(appt.id, 'EMP-00001')['token']
    previous = deepcopy(appt.attributes)
    def unexpected_save(_):
        pytest.fail('invalid input must not persist')
    monkeypatch.setattr(sched, 'save_graph', unexpected_save)
    monkeypatch.setattr(appointments, 'save_graph', unexpected_save)
    assert 'error' in sched.record_public_checkin(token, 'wait', **{field:value})
    assert appt.attributes == previous


def test_public_checkin_accepts_exact_detail_limits():
    appt = _make()
    token = sched.generate_checkin_link(appt.id, 'EMP-00001')['token']
    result = sched.record_public_checkin(token, 'wait', 'c'*200, 'n'*2000)
    assert result['checkin']['contact_preference'] == 'c'*200
    assert result['checkin']['notes'] == 'n'*2000
