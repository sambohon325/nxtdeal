"""
Tests for core/up_system.py + core/up_system_api.py -- the Up System (session
100 follow-up): a real walk-in/phone-up log with a genuine round-robin floor
rotation, backed by real Lead entities (not a parallel data model).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import EMPLOYEE, LEAD, UP_ROTATION
from core import up_system
from core import up_system_api
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    monkeypatch.setattr(up_system, "save_graph", lambda filepath: None)


_UP_ROLES = (ADMIN, OPERATIONS, SALES)
_UP_DENIED_ROLES = (MARKETING, SERVICE, FINANCE)


@pytest.mark.parametrize('contact', [{}, {'phone':None,'email':None}, {'phone':'','email':''}])
def test_http_walk_in_accepts_optional_contact_fields(monkeypatch, contact):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.routers import up_system as routes
    _add_employee()
    monkeypatch.setattr(routes, '_authenticate', lambda _: ({'role':ADMIN,'employee_id':'EMP-1'},None))
    app = FastAPI(); app.include_router(routes.router)
    client = TestClient(app)
    response = client.post('/up-system/log',json={'up_type':'walk_in','first_name':'Fictional Visitor',**contact})
    assert response.status_code == 200
    data = response.json()
    assert data.get('first_name') == 'Fictional Visitor', data
    assert ledger.get_entity(data['id']).attributes['FirstName'] == 'Fictional Visitor'


def _add_employee(employee_id="EMP-1", department="Sales", first="Sam", last="Rep"):
    ledger.add_entity(Entity(
        id=employee_id,
        entity_type=EMPLOYEE,
        attributes={"Department": department, "FirstName": first, "LastName": last},
    ))
    return employee_id


def _seed_two_reps():
    _add_employee("EMP-1", first="Sam", last="RepOne")
    _add_employee("EMP-2", first="Pat", last="RepTwo")


# ---------------------------------------------------------------------------
# get_rotation -- lazy seeding
# ---------------------------------------------------------------------------

class TestGetRotation:
    def test_seeds_from_the_real_sales_roster(self):
        _seed_two_reps()
        _add_employee("EMP-3", department="Service", first="Riley", last="Tech")

        rotation = up_system.get_rotation()

        ids = sorted(s["employee_id"] for s in rotation.attributes["board"])
        assert ids == ["EMP-1", "EMP-2"]

    def test_department_match_is_case_insensitive(self):
        _add_employee("EMP-1", department="SALES")
        rotation = up_system.get_rotation()
        assert rotation.attributes["board"] == [{"employee_id": "EMP-1", "active": True}]

    def test_empty_roster_yields_empty_board(self):
        rotation = up_system.get_rotation()
        assert rotation.attributes["board"] == []

    def test_seeding_only_happens_once(self):
        _seed_two_reps()
        up_system.get_rotation()
        up_system.set_board_active("EMP-1", False)

        # A second real Sales employee added AFTER the rotation already exists
        # should NOT retroactively appear -- the rotation is a real, standing
        # entity, not re-derived from the roster on every read.
        _add_employee("EMP-3", first="New", last="Hire")
        rotation = up_system.get_rotation()
        ids = sorted(s["employee_id"] for s in rotation.attributes["board"])
        assert ids == ["EMP-1", "EMP-2"]

    def test_creates_a_real_singleton_entity(self):
        up_system.get_rotation()
        stored = ledger.get_entity("UPROT-00001")
        assert stored is not None
        assert stored.entity_type == UP_ROTATION


# ---------------------------------------------------------------------------
# set_board_active
# ---------------------------------------------------------------------------

class TestSetBoardActive:
    def test_toggles_an_existing_slot(self):
        _seed_two_reps()
        up_system.get_rotation()
        rotation = up_system.set_board_active("EMP-1", False)

        slot = next(s for s in rotation.attributes["board"] if s["employee_id"] == "EMP-1")
        assert slot["active"] is False

    def test_appends_a_new_slot_when_not_already_on_the_board(self):
        rotation = up_system.set_board_active("EMP-NEW", True)
        assert rotation.attributes["board"] == [{"employee_id": "EMP-NEW", "active": True}]

    def test_stepping_out_does_not_remove_the_slot(self):
        _seed_two_reps()
        up_system.get_rotation()
        rotation = up_system.set_board_active("EMP-1", False)
        assert len(rotation.attributes["board"]) == 2


# ---------------------------------------------------------------------------
# set_board_order
# ---------------------------------------------------------------------------

class TestSetBoardOrder:
    def test_rebuilds_the_board_in_the_given_order(self):
        rotation = up_system.set_board_order(["EMP-2", "EMP-1"])
        assert [s["employee_id"] for s in rotation.attributes["board"]] == ["EMP-2", "EMP-1"]

    def test_preserves_active_flag_for_existing_employees(self):
        _seed_two_reps()
        up_system.get_rotation()
        up_system.set_board_active("EMP-1", False)

        rotation = up_system.set_board_order(["EMP-1", "EMP-2"])
        slot = next(s for s in rotation.attributes["board"] if s["employee_id"] == "EMP-1")
        assert slot["active"] is False

    def test_new_entries_default_active(self):
        rotation = up_system.set_board_order(["EMP-NEW"])
        assert rotation.attributes["board"][0]["active"] is True

    def test_resets_next_index_to_zero(self):
        rotation = up_system.set_board_order(["EMP-1", "EMP-2"])
        rotation.attributes["next_index"] = 1
        rotation = up_system.set_board_order(["EMP-2", "EMP-1"])
        assert rotation.attributes["next_index"] == 0


# ---------------------------------------------------------------------------
# peek_next / round-robin advancement
# ---------------------------------------------------------------------------

class TestRotation:
    def test_peek_next_returns_none_on_empty_board(self):
        assert up_system.peek_next() is None

    def test_peek_next_does_not_advance(self):
        up_system.set_board_order(["EMP-1", "EMP-2"])
        first_peek = up_system.peek_next()
        second_peek = up_system.peek_next()
        assert first_peek == second_peek == "EMP-1"

    def test_peek_next_skips_inactive(self):
        up_system.set_board_order(["EMP-1", "EMP-2"])
        up_system.set_board_active("EMP-1", False)
        assert up_system.peek_next() == "EMP-2"

    def test_peek_next_none_when_nobody_active(self):
        up_system.set_board_order(["EMP-1"])
        up_system.set_board_active("EMP-1", False)
        assert up_system.peek_next() is None

    def test_round_robin_via_repeated_log_ups(self):
        up_system.set_board_order(["EMP-1", "EMP-2"])
        u1 = up_system.log_up("walk_in", "EMP-RECEPTION", "A", "One")
        u2 = up_system.log_up("walk_in", "EMP-RECEPTION", "B", "Two")
        u3 = up_system.log_up("walk_in", "EMP-RECEPTION", "C", "Three")

        assert u1.attributes["AssignedSalesperson"] == "EMP-1"
        assert u2.attributes["AssignedSalesperson"] == "EMP-2"
        assert u3.attributes["AssignedSalesperson"] == "EMP-1"  # wraps around

    def test_advance_skips_an_inactive_rep(self):
        up_system.set_board_order(["EMP-1", "EMP-2"])
        up_system.set_board_active("EMP-1", False)
        u1 = up_system.log_up("walk_in", "EMP-RECEPTION", "A", "One")
        assert u1.attributes["AssignedSalesperson"] == "EMP-2"


# ---------------------------------------------------------------------------
# log_up
# ---------------------------------------------------------------------------

class TestLogUp:
    def test_rejects_bad_up_type(self):
        up_system.set_board_order(["EMP-1"])
        result = up_system.log_up("carrier_pigeon", "EMP-1", "A", "One")
        assert "error" in result

    def test_rejects_when_no_name_given(self):
        up_system.set_board_order(["EMP-1"])
        result = up_system.log_up("walk_in", "EMP-1", "", "")
        assert "error" in result

    def test_rejects_when_nobody_is_on_the_rotation(self):
        result = up_system.log_up("walk_in", "EMP-RECEPTION", "A", "One")
        assert "error" in result

    def test_walk_in_source_is_correct(self):
        up_system.set_board_order(["EMP-1"])
        lead = up_system.log_up("walk_in", "EMP-1", "A", "One")
        assert lead.attributes["Source"] == "Walk-In"

    def test_phone_up_source_is_correct(self):
        up_system.set_board_order(["EMP-1"])
        lead = up_system.log_up("phone_up", "EMP-1", "A", "One")
        assert lead.attributes["Source"] == "Phone-Up"

    def test_a_lead_created_by_the_next_rep_themself_is_not_reassigned(self):
        up_system.set_board_order(["EMP-1"])
        lead = up_system.log_up("walk_in", "EMP-1", "A", "One")
        assert lead.attributes["AssignedSalesperson"] == "EMP-1"

    def test_records_the_real_up_fields(self):
        up_system.set_board_order(["EMP-1"])
        lead = up_system.log_up("walk_in", "EMP-RECEPTION", "A", "One", phone="555-1212", notes="Interested in trucks")
        assert lead.attributes["up_type"] == "walk_in"
        assert lead.attributes["up_status"] == "working"
        assert lead.attributes["up_logged_by"] == "EMP-RECEPTION"
        assert lead.attributes["up_logged_at"] is not None
        assert lead.attributes["up_notes"] == "Interested in trucks"

    def test_notes_field_omitted_when_blank(self):
        up_system.set_board_order(["EMP-1"])
        lead = up_system.log_up("walk_in", "EMP-1", "A", "One")
        assert "up_notes" not in lead.attributes

    def test_creates_a_real_lead_entity(self):
        up_system.set_board_order(["EMP-1"])
        lead = up_system.log_up("walk_in", "EMP-1", "A", "One")
        stored = ledger.get_entity(lead.id)
        assert stored is not None
        assert stored.entity_type == LEAD


# ---------------------------------------------------------------------------
# update_up_status
# ---------------------------------------------------------------------------

class TestUpdateUpStatus:
    def test_rejects_unknown_lead(self):
        result = up_system.update_up_status("LEAD-BAD", "demo", "EMP-1")
        assert "error" in result

    def test_rejects_a_lead_that_is_not_an_up(self):
        ledger.add_entity(Entity(id="LEAD-1", entity_type=LEAD, attributes={"Source": "Website"}))
        result = up_system.update_up_status("LEAD-1", "demo", "EMP-1")
        assert "error" in result

    def test_rejects_bad_status(self):
        up_system.set_board_order(["EMP-1"])
        lead = up_system.log_up("walk_in", "EMP-1", "A", "One")
        result = up_system.update_up_status(lead.id, "abducted_by_aliens", "EMP-1")
        assert "error" in result

    def test_updates_status(self):
        up_system.set_board_order(["EMP-1"])
        lead = up_system.log_up("walk_in", "EMP-1", "A", "One")
        result = up_system.update_up_status(lead.id, "demo", "EMP-1")
        assert result.attributes["up_status"] == "demo"

    def test_appends_to_status_history(self):
        up_system.set_board_order(["EMP-1"])
        lead = up_system.log_up("walk_in", "EMP-1", "A", "One")
        up_system.update_up_status(lead.id, "demo", "EMP-1")
        up_system.update_up_status(lead.id, "worksheet", "EMP-1")
        history = lead.attributes["up_status_history"]
        assert len(history) == 2
        assert history[0]["status"] == "demo"
        assert history[1]["status"] == "worksheet"

    def test_rejects_updating_an_already_terminal_up_sold(self):
        up_system.set_board_order(["EMP-1"])
        lead = up_system.log_up("walk_in", "EMP-1", "A", "One")
        up_system.update_up_status(lead.id, "sold", "EMP-1")
        result = up_system.update_up_status(lead.id, "demo", "EMP-1")
        assert "error" in result

    def test_rejects_updating_an_already_terminal_up_no_sale(self):
        up_system.set_board_order(["EMP-1"])
        lead = up_system.log_up("walk_in", "EMP-1", "A", "One")
        up_system.update_up_status(lead.id, "no_sale", "EMP-1")
        result = up_system.update_up_status(lead.id, "be_back", "EMP-1")
        assert "error" in result


# ---------------------------------------------------------------------------
# list_ups / get_be_back_board
# ---------------------------------------------------------------------------

class TestListUps:
    def test_only_returns_ups_not_regular_leads(self):
        up_system.set_board_order(["EMP-1"])
        up_system.log_up("walk_in", "EMP-1", "A", "One")
        ledger.add_entity(Entity(id="LEAD-REGULAR", entity_type=LEAD, attributes={"Source": "Website"}))

        ups = up_system.list_ups()
        assert len(ups) == 1

    def test_filters_by_status(self):
        up_system.set_board_order(["EMP-1", "EMP-2"])
        u1 = up_system.log_up("walk_in", "EMP-1", "A", "One")
        up_system.log_up("walk_in", "EMP-1", "B", "Two")
        up_system.update_up_status(u1.id, "demo", "EMP-1")

        demo_ups = up_system.list_ups(status="demo")
        assert len(demo_ups) == 1
        assert demo_ups[0].id == u1.id

    def test_filters_by_up_type(self):
        up_system.set_board_order(["EMP-1", "EMP-2"])
        up_system.log_up("walk_in", "EMP-1", "A", "One")
        up_system.log_up("phone_up", "EMP-1", "B", "Two")

        walk_ins = up_system.list_ups(up_type="walk_in")
        assert len(walk_ins) == 1
        assert walk_ins[0].attributes["up_type"] == "walk_in"

    def test_filters_by_assigned_to(self):
        up_system.set_board_order(["EMP-1", "EMP-2"])
        up_system.log_up("walk_in", "EMP-RECEPTION", "A", "One")
        up_system.log_up("walk_in", "EMP-RECEPTION", "B", "Two")

        assigned_to_emp1 = up_system.list_ups(assigned_to="EMP-1")
        assert len(assigned_to_emp1) == 1
        assert assigned_to_emp1[0].attributes["AssignedSalesperson"] == "EMP-1"

    def test_filters_by_date_prefix(self):
        up_system.set_board_order(["EMP-1"])
        lead = up_system.log_up("walk_in", "EMP-1", "A", "One")
        real_date_prefix = lead.attributes["up_logged_at"][:10]

        assert len(up_system.list_ups(date=real_date_prefix)) == 1
        assert len(up_system.list_ups(date="1999-01-01")) == 0

    def test_sorted_most_recent_first(self):
        up_system.set_board_order(["EMP-1", "EMP-2"])
        u1 = up_system.log_up("walk_in", "EMP-1", "A", "One")
        u1.attributes["up_logged_at"] = "2026-01-01T00:00:00+00:00"
        u2 = up_system.log_up("walk_in", "EMP-1", "B", "Two")
        u2.attributes["up_logged_at"] = "2026-06-01T00:00:00+00:00"

        ups = up_system.list_ups()
        assert [u.id for u in ups] == [u2.id, u1.id]

    def test_be_back_board_only_returns_be_back_status(self):
        up_system.set_board_order(["EMP-1", "EMP-2"])
        u1 = up_system.log_up("walk_in", "EMP-1", "A", "One")
        up_system.log_up("walk_in", "EMP-1", "B", "Two")
        up_system.update_up_status(u1.id, "be_back", "EMP-1")

        be_backs = up_system.get_be_back_board()
        assert len(be_backs) == 1
        assert be_backs[0].id == u1.id


# ---------------------------------------------------------------------------
# ACL sweep -- core/up_system_api.py
# ---------------------------------------------------------------------------

class TestAcl:
    def test_list_up_types_is_open(self):
        assert up_system_api.list_up_types_api() == list(up_system.UP_TYPES)

    def test_list_up_statuses_is_open(self):
        assert up_system_api.list_up_statuses_api() == up_system.UP_STATUSES

    @pytest.mark.parametrize("role", _UP_DENIED_ROLES)
    def test_get_rotation_api_denied(self, role):
        result = up_system_api.get_rotation_api(role)
        assert "error" in result

    @pytest.mark.parametrize("role", _UP_ROLES)
    def test_get_rotation_api_allowed(self, role):
        ledger.reset()
        result = up_system_api.get_rotation_api(role)
        assert "board" in result
        assert "next_up" in result

    @pytest.mark.parametrize("role", _UP_DENIED_ROLES)
    def test_set_board_active_api_denied(self, role):
        result = up_system_api.set_board_active_api(role, "EMP-1", True)
        assert "error" in result

    @pytest.mark.parametrize("role", _UP_ROLES)
    def test_set_board_active_api_allowed(self, role):
        ledger.reset()
        result = up_system_api.set_board_active_api(role, "EMP-1", True)
        assert "board" in result

    @pytest.mark.parametrize("role", _UP_DENIED_ROLES)
    def test_set_board_order_api_denied(self, role):
        result = up_system_api.set_board_order_api(role, ["EMP-1"])
        assert "error" in result

    @pytest.mark.parametrize("role", _UP_ROLES)
    def test_set_board_order_api_allowed(self, role):
        ledger.reset()
        result = up_system_api.set_board_order_api(role, ["EMP-1"])
        assert "board" in result

    @pytest.mark.parametrize("role", _UP_DENIED_ROLES)
    def test_log_up_api_denied(self, role):
        result = up_system_api.log_up_api(role, "EMP-1", "walk_in", "A", "One")
        assert "error" in result

    @pytest.mark.parametrize("role", _UP_ROLES)
    def test_log_up_api_allowed(self, role):
        ledger.reset()
        up_system.set_board_order(["EMP-1"])
        result = up_system_api.log_up_api(role, "EMP-1", "walk_in", "A", "One")
        assert "error" not in result
        assert result["up_type"] == "walk_in"

    def test_log_up_api_serializes_names(self):
        _add_employee("EMP-1", first="Sam", last="RepOne")
        up_system.set_board_order(["EMP-1"])
        result = up_system_api.log_up_api(ADMIN, "EMP-1", "walk_in", "A", "One")
        assert result["assigned_to_name"] == "Sam RepOne"

    @pytest.mark.parametrize("role", _UP_DENIED_ROLES)
    def test_update_up_status_api_denied(self, role):
        result = up_system_api.update_up_status_api(role, "EMP-1", "LEAD-1", "demo")
        assert "error" in result

    @pytest.mark.parametrize("role", _UP_ROLES)
    def test_update_up_status_api_allowed(self, role):
        ledger.reset()
        up_system.set_board_order(["EMP-1"])
        lead = up_system.log_up("walk_in", "EMP-1", "A", "One")
        result = up_system_api.update_up_status_api(role, "EMP-1", lead.id, "demo")
        assert "error" not in result
        assert result["up_status"] == "demo"

    @pytest.mark.parametrize("role", _UP_DENIED_ROLES)
    def test_list_ups_api_denied(self, role):
        result = up_system_api.list_ups_api(role)
        assert isinstance(result, dict) and "error" in result

    @pytest.mark.parametrize("role", _UP_ROLES)
    def test_list_ups_api_allowed(self, role):
        result = up_system_api.list_ups_api(role)
        assert isinstance(result, list)

    @pytest.mark.parametrize("role", _UP_DENIED_ROLES)
    def test_get_be_back_board_api_denied(self, role):
        result = up_system_api.get_be_back_board_api(role)
        assert isinstance(result, dict) and "error" in result

    @pytest.mark.parametrize("role", _UP_ROLES)
    def test_get_be_back_board_api_allowed(self, role):
        result = up_system_api.get_be_back_board_api(role)
        assert isinstance(result, list)
