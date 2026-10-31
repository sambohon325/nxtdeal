"""
Tests for core/appointments.py -- the shared Appointment/calendar entity added in the
session-96 follow-up (see CLAUDE.md's session-96 note and the "Sales Deal Desk" arc).
This is the first committed regression coverage for that module, added per
BUILD_QUEUE.md's standing "convert the loose test_*.py scripts to a real backend/tests/
pytest suite as each module gets touched" rule.

The Appointment entity is load-bearing: both Sales (AppointmentsBoard) and Service
(ServiceAppointmentsBoard) share it, and sales_overview.py's My Tasks Widget depends on
list_upcoming_within(). Everything here seeds Customer/Lead entities directly into the
ledger and stubs save_graph, so it's fully deterministic, seed-independent, and never
touches the real graph.json -- same precautions tests/test_intake.py documents. It also
imports only the ledger chain (not the FUSE-truncated *_menu/api.app modules), so it runs
green in the sandbox. Run from backend/ with `pytest`.
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
from core.entity_types import CUSTOMER, LEAD

from core import appointments


# --------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def fresh_singletons():
    """Reset the ledger + the APPT id counter before/after every test. ledger.reset()
    clears entities but does NOT reset id_generator counters, so ids would otherwise
    leak across tests (same rule tests/test_intake.py documents)."""

    def _reset():
        ledger.reset()
        for prefix in id_generator.counters:
            id_generator.counters[prefix] = 0

    _reset()
    yield
    _reset()


@pytest.fixture(autouse=True)
def no_real_disk_writes(monkeypatch):
    """appointments.py does `from core.storage import save_graph`, so patch the imported
    reference in its namespace -- otherwise every mutation would clobber the real
    storage/graph.json with the empty test ledger."""

    monkeypatch.setattr(appointments, "save_graph", lambda filepath: None)


def _add_customer(entity_id="CUST-00001"):
    ledger.add_entity(Entity(id=entity_id, entity_type=CUSTOMER, attributes={"Name": "Test Buyer"}))
    return entity_id


def _add_lead(entity_id="LEAD-00001"):
    ledger.add_entity(Entity(id=entity_id, entity_type=LEAD, attributes={"Name": "Test Lead"}))
    return entity_id


def _iso_in(**delta):
    """A tz-aware ISO timestamp `delta` from now (e.g. _iso_in(hours=1))."""
    return (datetime.now(timezone.utc) + timedelta(**delta)).isoformat()


def _make(department="Sales", appointment_type="showroom_visit", start=None, **kw):
    return appointments.create_appointment(
        department=department,
        appointment_type=appointment_type,
        scheduled_start=start or _iso_in(hours=1),
        created_by="EMP-00001",
        **kw,
    )


# --------------------------------------------------------------------------
# create_appointment -- validation
# --------------------------------------------------------------------------


def test_create_success_defaults_to_scheduled():
    appt = _make()

    assert not isinstance(appt, dict)  # returns the Entity, not an error dict
    assert appt.id.startswith("APPT-")
    assert appt.attributes["status"] == "scheduled"
    assert appt.attributes["department"] == "Sales"
    assert appt.attributes["appointment_type"] == "showroom_visit"
    assert appt.attributes["created_by"] == "EMP-00001"
    assert appt.attributes["status_history"][0]["status"] == "scheduled"


def test_create_rejects_unknown_department():
    result = appointments.create_appointment(
        department="Marketing",
        appointment_type="showroom_visit",
        scheduled_start=_iso_in(hours=1),
        created_by="EMP-00001",
    )
    assert "error" in result


def test_create_rejects_type_from_wrong_department():
    # "test_drive" is a Sales type, not valid for Service
    result = appointments.create_appointment(
        department="Service",
        appointment_type="test_drive",
        scheduled_start=_iso_in(hours=1),
        created_by="EMP-00001",
    )
    assert "error" in result


def test_create_requires_scheduled_start():
    result = appointments.create_appointment(
        department="Sales",
        appointment_type="showroom_visit",
        scheduled_start="",
        created_by="EMP-00001",
    )
    assert "error" in result


def test_create_rejects_missing_customer():
    result = _make(customer_id="CUST-99999")
    assert "error" in result


def test_create_rejects_missing_lead():
    result = _make(lead_id="LEAD-99999")
    assert "error" in result


def test_create_rejects_customer_id_pointing_at_a_lead():
    lead_id = _add_lead()
    # passing a Lead's id as customer_id must fail the entity_type check
    result = _make(customer_id=lead_id)
    assert "error" in result


def test_create_accepts_valid_customer_and_lead():
    cust = _add_customer()
    lead = _add_lead()
    appt = _make(customer_id=cust, lead_id=lead, vehicle_id="VEH-00001")
    assert not isinstance(appt, dict)
    assert appt.attributes["customer_id"] == cust
    assert appt.attributes["lead_id"] == lead
    assert appt.attributes["vehicle_id"] == "VEH-00001"


def test_service_department_accepts_its_own_types():
    appt = _make(department="Service", appointment_type="waiter")
    assert not isinstance(appt, dict)
    assert appt.attributes["department"] == "Service"


# --------------------------------------------------------------------------
# get_appointment
# --------------------------------------------------------------------------


def test_get_appointment_round_trip():
    appt = _make()
    fetched = appointments.get_appointment(appt.id)
    assert fetched is not None
    assert fetched.id == appt.id


def test_get_appointment_missing_returns_none():
    assert appointments.get_appointment("APPT-99999") is None


def test_get_appointment_wrong_type_returns_none():
    cust = _add_customer()
    # a real entity id that isn't an Appointment
    assert appointments.get_appointment(cust) is None


# --------------------------------------------------------------------------
# update_status -- lifecycle
# --------------------------------------------------------------------------


def test_update_status_happy_path():
    appt = _make()
    updated = appointments.update_status(appt.id, "confirmed", "EMP-00002")
    assert updated.attributes["status"] == "confirmed"
    assert updated.attributes["status_history"][-1] == {
        "status": "confirmed",
        "at": updated.attributes["status_history"][-1]["at"],
        "by": "EMP-00002",
    }


def test_update_status_rejects_unknown_status():
    appt = _make()
    result = appointments.update_status(appt.id, "rescheduled", "EMP-00002")
    # "rescheduled" is a history label, not a valid explicit status
    assert "error" in result


def test_update_status_rejects_missing_appointment():
    result = appointments.update_status("APPT-99999", "confirmed", "EMP-00002")
    assert "error" in result


def test_update_status_terminal_is_locked():
    appt = _make()
    appointments.update_status(appt.id, "completed", "EMP-00002")
    result = appointments.update_status(appt.id, "confirmed", "EMP-00002")
    assert "error" in result


@pytest.mark.parametrize("terminal", ["completed", "cancelled", "no_show"])
def test_all_terminal_states_lock_the_record(terminal):
    appt = _make()
    appointments.update_status(appt.id, terminal, "EMP-00002")
    result = appointments.update_status(appt.id, "arrived", "EMP-00002")
    assert "error" in result


# --------------------------------------------------------------------------
# reschedule_appointment
# --------------------------------------------------------------------------


def test_reschedule_resets_to_scheduled():
    appt = _make()
    appointments.update_status(appt.id, "confirmed", "EMP-00002")
    new_start = _iso_in(days=2)
    updated = appointments.reschedule_appointment(appt.id, new_start, "EMP-00002")
    assert updated.attributes["scheduled_start"] == new_start
    assert updated.attributes["status"] == "scheduled"
    assert updated.attributes["status_history"][-1]["status"] == "rescheduled"


def test_reschedule_requires_new_start():
    appt = _make()
    result = appointments.reschedule_appointment(appt.id, "", "EMP-00002")
    assert "error" in result


def test_reschedule_rejects_terminal_record():
    appt = _make()
    appointments.update_status(appt.id, "completed", "EMP-00002")
    result = appointments.reschedule_appointment(appt.id, _iso_in(days=1), "EMP-00002")
    assert "error" in result


def test_reschedule_missing_appointment():
    result = appointments.reschedule_appointment("APPT-99999", _iso_in(days=1), "EMP-00002")
    assert "error" in result


# --------------------------------------------------------------------------
# list_appointments -- filtering + sort
# --------------------------------------------------------------------------


def test_list_filters_by_department():
    _make(department="Sales", appointment_type="showroom_visit")
    _make(department="Service", appointment_type="waiter")
    sales = appointments.list_appointments(department="Sales")
    assert len(sales) == 1
    assert sales[0].attributes["department"] == "Sales"


def test_list_filters_by_assigned_to():
    _make(assigned_to="EMP-A")
    _make(assigned_to="EMP-B")
    only_a = appointments.list_appointments(assigned_to="EMP-A")
    assert len(only_a) == 1
    assert only_a[0].attributes["assigned_to"] == "EMP-A"


def test_list_filters_by_status():
    a1 = _make()
    _make()
    appointments.update_status(a1.id, "confirmed", "EMP-00002")
    confirmed = appointments.list_appointments(status="confirmed")
    assert len(confirmed) == 1
    assert confirmed[0].id == a1.id


def test_list_filters_by_linked_entity():
    cust = _add_customer()
    lead = _add_lead()
    _make(customer_id=cust)
    _make(lead_id=lead)
    by_cust = appointments.list_appointments(linked_entity_id=cust)
    by_lead = appointments.list_appointments(linked_entity_id=lead)
    assert len(by_cust) == 1 and by_cust[0].attributes["customer_id"] == cust
    assert len(by_lead) == 1 and by_lead[0].attributes["lead_id"] == lead


def test_list_sorted_by_scheduled_start():
    later = _make(start=_iso_in(days=3))
    sooner = _make(start=_iso_in(hours=2))
    ordered = appointments.list_appointments()
    assert [a.id for a in ordered] == [sooner.id, later.id]


# --------------------------------------------------------------------------
# list_todays / list_this_week / list_upcoming_within
# --------------------------------------------------------------------------


def test_list_todays_only_returns_today():
    today = datetime.now(timezone.utc).date().isoformat()
    _make(start=f"{today}T14:00:00+00:00")
    _make(start=_iso_in(days=5))
    todays = appointments.list_todays()
    assert len(todays) == 1
    assert str(todays[0].attributes["scheduled_start"]).startswith(today)


def test_list_this_week_window_is_inclusive_of_boundaries():
    today = datetime.now(timezone.utc).date()
    week_end = today + timedelta(days=7)
    _make(start=f"{today.isoformat()}T09:00:00+00:00")          # today boundary
    _make(start=f"{week_end.isoformat()}T09:00:00+00:00")       # +7d boundary
    _make(start=_iso_in(days=30))                                # far outside
    this_week = appointments.list_this_week()
    assert len(this_week) == 2


def test_list_upcoming_within_respects_horizon_and_open_status():
    soon = _make(start=_iso_in(hours=1))          # within 2h
    _make(start=_iso_in(hours=5))                  # outside 2h
    upcoming = appointments.list_upcoming_within(2)
    assert [a.id for a in upcoming] == [soon.id]


def test_list_upcoming_within_excludes_closed_and_rescheduled_out():
    soon = _make(start=_iso_in(hours=1))
    completed = _make(start=_iso_in(hours=1))
    appointments.update_status(completed.id, "completed", "EMP-00002")
    upcoming = appointments.list_upcoming_within(2)
    # only the still-open soon appointment; the completed one is filtered out
    assert [a.id for a in upcoming] == [soon.id]


def test_list_upcoming_within_ignores_past_appointments():
    _make(start=_iso_in(hours=-1))  # already started, before "now"
    upcoming = appointments.list_upcoming_within(2)
    assert upcoming == []


def test_list_upcoming_within_skips_unparseable_start():
    _make(start="not-a-real-timestamp")
    # must not raise -- the ValueError branch just skips the row
    upcoming = appointments.list_upcoming_within(2)
    assert upcoming == []

def test_failed_create_leaves_no_phantom_booking_and_retry_creates_one(monkeypatch):
    customer_id = _add_customer()
    existing = _make(customer_id=customer_id)
    before = dict(ledger.get_all())
    attempted = []

    def fail(_):
        attempted.extend(a.id for a in appointments.list_appointments() if a.id not in before)
        raise OSError('fixture save failure')

    monkeypatch.setattr(appointments, 'save_graph', fail)
    with pytest.raises(OSError):
        _make(customer_id=customer_id)
    assert ledger.get_all() == before
    assert appointments.list_appointments(linked_entity_id=customer_id) == [existing]
    assert len(attempted) == 1
    assert appointments.get_appointment(attempted[0]) is None

    monkeypatch.setattr(appointments, 'save_graph', lambda *_: None)
    retry = _make(customer_id=customer_id)
    assert retry.id != attempted[0]
    assert len(appointments.list_appointments(linked_entity_id=customer_id)) == 2
    assert retry.attributes['status'] == 'scheduled'


@pytest.mark.parametrize('operation', ['confirm', 'cancel', 'reschedule'])
def test_failed_calendar_change_restores_record_and_allows_retry(monkeypatch, operation):
    from copy import deepcopy
    customer_id=_add_customer()
    appt=appointments.create_appointment('Service','service','2026-10-04T10:00:00Z','EMP-1',customer_id=customer_id,scheduled_end='2026-10-04T11:00:00Z')
    before=deepcopy(appt.attributes)
    def change():
        if operation=='reschedule':
            return appointments.reschedule_appointment(appt.id,'2026-10-05T12:00:00Z','EMP-1',new_end='2026-10-05T13:00:00Z')
        return appointments.update_status(appt.id,'confirmed' if operation=='confirm' else 'cancelled','EMP-1')
    def fail(_): raise OSError('fixture save failure')
    monkeypatch.setattr(appointments,'save_graph',fail)
    with pytest.raises(OSError): change()
    assert appointments.get_appointment(appt.id).attributes==before
    assert appointments.list_appointments(linked_entity_id=customer_id)[0].attributes==before
    monkeypatch.setattr(appointments,'save_graph',lambda *_:None)
    assert change().id==appt.id
    assert len(appt.attributes['status_history'])==len(before['status_history'])+1
    if operation=='reschedule':
        assert appt.attributes['scheduled_start']=='2026-10-05T12:00:00Z'
        assert appt.attributes['scheduled_end']=='2026-10-05T13:00:00Z'
    else:
        assert appt.attributes['status']==('confirmed' if operation=='confirm' else 'cancelled')

@pytest.mark.parametrize('start,end', [
    ('nonsense',None), ('2026-10-04',None), ('2026-02-30T10:00:00Z',None),
    ('2026-10-04T10:00:00Z','invalid'), ('2026-10-04T10:00:00Z','2026-10-04T10:00:00Z'),
    ('2026-10-04T10:00:00Z','2026-10-04T09:00:00Z'),
    ('2026-10-04T10:00:00Z','2026-10-04T11:00:00')])
def test_invalid_time_range_does_not_create_appointment(start,end):
    result=appointments.create_appointment('Sales','showroom_visit',start,'EMP-1',scheduled_end=end)
    assert 'error' in result
    assert appointments.list_appointments()==[]


def test_reschedule_rejects_retained_end_before_new_start_without_mutation():
    from copy import deepcopy
    appt=_make(start='2026-10-04T10:00:00Z',scheduled_end='2026-10-04T11:00:00Z')
    before=deepcopy(appt.attributes)
    result=appointments.reschedule_appointment(appt.id,'2026-10-05T10:00:00Z','EMP-1')
    assert 'error' in result and appt.attributes==before


def test_time_range_compares_offsets_and_preserves_legacy_local_times():
    assert not isinstance(_make(start='2026-10-04T10:00:00-05:00',scheduled_end='2026-10-04T16:00:00Z'),dict)
    assert not isinstance(_make(start='2026-10-04T10:00',scheduled_end='2026-10-04T11:00'),dict)
