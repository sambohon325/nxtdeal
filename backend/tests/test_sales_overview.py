"""
Test coverage for core/sales_overview.py -- Sales' "Overview" command center:
My Tasks Widget, Action Center, Daily Sales Dashboard, and the Sales Manager
Dashboard (gated to manager/executive-tier employees, per core.bot_tasks'
infer_tier() off Employee.Title, or ADMIN/OPERATIONS roles).

Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta, timezone

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import LEAD, DEAL, EMPLOYEE
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING

import core.sales_overview as so
import core.lead_assignment as lead_assignment
import core.field_notes as field_notes
import core.lead_tasks as lead_tasks
import core.appointments as appointments


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield
    ledger.reset()


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    monkeypatch.setattr(lead_assignment, "save_graph", lambda filepath: None)
    monkeypatch.setattr(field_notes, "save_graph", lambda filepath: None)
    monkeypatch.setattr(lead_tasks, "save_graph", lambda filepath: None)
    monkeypatch.setattr(appointments, "save_graph", lambda filepath: None)


def _now():
    return datetime.now(timezone.utc)


def _iso(dt):
    return dt.isoformat()


def _lead(lid, **attrs):
    attrs.setdefault("FirstName", "Jane")
    attrs.setdefault("LastName", "Doe")
    attrs.setdefault("PipelineState", "NEW")
    ledger.add_entity(Entity(id=lid, entity_type=LEAD, attributes=attrs))
    return ledger.get_entity(lid)


def _deal(did, **attrs):
    ledger.add_entity(Entity(id=did, entity_type=DEAL, attributes=attrs))
    return ledger.get_entity(did)


def _employee(eid, title="Sales Associate"):
    ledger.add_entity(Entity(id=eid, entity_type=EMPLOYEE, attributes={"Title": title}))
    return ledger.get_entity(eid)


def _assign(lead_id, employee_id):
    lead_assignment.assign_lead(lead_id, employee_id)


def _note(lead_id, category, created_at, created_by="EMP-1"):
    note = field_notes.create_field_note(
        department="Sales",
        category=category,
        body="test note",
        created_by=created_by,
        linked_entity_id=lead_id,
    )
    note.attributes["created_at"] = created_at
    return note


def _appointment(scheduled_start, assigned_to="EMP-1", appointment_type="test_drive", **kwargs):
    result = appointments.create_appointment(
        department="Sales",
        appointment_type=appointment_type,
        scheduled_start=scheduled_start,
        created_by="EMP-1",
        assigned_to=assigned_to,
        **kwargs,
    )
    return result


class TestMyLeadIds:

    def test_relationship_based_assignment_is_included(self):
        _lead("LEAD-1")
        _assign("LEAD-1", "EMP-1")
        assert so._my_lead_ids("EMP-1") == {"LEAD-1"}

    def test_attribute_fallback_is_included(self):
        _lead("LEAD-1", AssignedSalesperson="EMP-1")
        assert so._my_lead_ids("EMP-1") == {"LEAD-1"}

    def test_union_dedups_when_both_signals_agree(self):
        _lead("LEAD-1", AssignedSalesperson="EMP-1")
        _assign("LEAD-1", "EMP-1")
        assert so._my_lead_ids("EMP-1") == {"LEAD-1"}

    def test_union_combines_leads_from_both_signals(self):
        _lead("LEAD-1", AssignedSalesperson="EMP-1")
        _lead("LEAD-2")
        _assign("LEAD-2", "EMP-1")
        assert so._my_lead_ids("EMP-1") == {"LEAD-1", "LEAD-2"}

    def test_no_leads_for_unassigned_employee(self):
        _lead("LEAD-1", AssignedSalesperson="EMP-2")
        assert so._my_lead_ids("EMP-1") == set()

    def test_reassigned_lead_only_counts_for_current_employee(self):
        _lead("LEAD-1")
        _assign("LEAD-1", "EMP-1")
        _assign("LEAD-1", "EMP-2")
        assert so._my_lead_ids("EMP-1") == set()
        assert so._my_lead_ids("EMP-2") == {"LEAD-1"}


class TestLeadBrief:

    def test_brief_shape(self):
        lead = _lead("LEAD-1", FirstName="John", LastName="Smith", Phone="555-1234",
                      Email="j@x.com", Source="Website", PipelineState="CONTACTED")
        brief = so._lead_brief(lead, last_contact="2026-07-01T00:00:00+00:00", overdue_count=2)
        assert brief["id"] == "LEAD-1"
        assert brief["name"] == "John Smith"
        assert brief["phone"] == "555-1234"
        assert brief["email"] == "j@x.com"
        assert brief["source"] == "Website"
        assert brief["pipeline_state"] == "CONTACTED"
        assert brief["last_contact"] == "2026-07-01T00:00:00+00:00"
        assert brief["overdue_task_count"] == 2
        assert brief["available_actions"] == so.AVAILABLE_ACTIONS

    def test_brief_handles_missing_name_parts(self):
        lead = _lead("LEAD-1", FirstName="", LastName="")
        brief = so._lead_brief(lead)
        assert brief["name"] == ""
        assert brief["last_contact"] is None
        assert brief["overdue_task_count"] == 0


class TestGetMyTasks:

    def test_lead_with_no_contact_needs_contact(self):
        _lead("LEAD-1", PipelineState="NEW")
        _assign("LEAD-1", "EMP-1")
        result = so.get_my_tasks(SALES, "EMP-1")
        ids = [i["id"] for i in result["leads_requiring_contact_today"]["items"]]
        assert "LEAD-1" in ids
        assert result["leads_requiring_contact_today"]["count"] == 1

    def test_lead_contacted_today_does_not_need_contact(self):
        lead = _lead("LEAD-1", PipelineState="CONTACTED")
        _assign("LEAD-1", "EMP-1")
        _note("LEAD-1", "call", _iso(_now()))
        result = so.get_my_tasks(SALES, "EMP-1")
        ids = [i["id"] for i in result["leads_requiring_contact_today"]["items"]]
        assert "LEAD-1" not in ids

    def test_lead_contacted_yesterday_needs_contact_again(self):
        _lead("LEAD-1", PipelineState="CONTACTED")
        _assign("LEAD-1", "EMP-1")
        _note("LEAD-1", "call", _iso(_now() - timedelta(days=1, hours=1)))
        result = so.get_my_tasks(SALES, "EMP-1")
        ids = [i["id"] for i in result["leads_requiring_contact_today"]["items"]]
        assert "LEAD-1" in ids

    def test_sold_leads_are_excluded_entirely(self):
        _lead("LEAD-1", PipelineState="SOLD")
        _assign("LEAD-1", "EMP-1")
        result = so.get_my_tasks(SALES, "EMP-1")
        assert result["leads_requiring_contact_today"]["count"] == 0
        assert result["missing_follow_ups"]["count"] == 0
        assert result["unsold_showroom_visits"]["count"] == 0

    def test_lost_leads_are_excluded_entirely(self):
        _lead("LEAD-1", PipelineState="LOST")
        _assign("LEAD-1", "EMP-1")
        result = so.get_my_tasks(SALES, "EMP-1")
        assert result["leads_requiring_contact_today"]["count"] == 0

    def test_overdue_task_shows_in_missing_follow_ups(self):
        _lead("LEAD-1", PipelineState="CONTACTED")
        _assign("LEAD-1", "EMP-1")
        _note("LEAD-1", "call", _iso(_now()))
        lead_tasks.create_task(
            lead_id="LEAD-1", task_type="call", description="call back",
            due_at=_iso(_now() - timedelta(days=1)), created_by="EMP-1",
        )
        result = so.get_my_tasks(SALES, "EMP-1")
        ids = [i["id"] for i in result["missing_follow_ups"]["items"]]
        assert "LEAD-1" in ids

    def test_visited_state_shows_in_unsold_showroom(self):
        _lead("LEAD-1", PipelineState="VISITED")
        _assign("LEAD-1", "EMP-1")
        result = so.get_my_tasks(SALES, "EMP-1")
        ids = [i["id"] for i in result["unsold_showroom_visits"]["items"]]
        assert "LEAD-1" in ids

    def test_action_center_dedups_a_lead_appearing_in_multiple_buckets(self):
        # VISITED with no contact -> needing_contact AND unsold_showroom_visits,
        # but action_center should only list it once.
        _lead("LEAD-1", PipelineState="VISITED")
        _assign("LEAD-1", "EMP-1")
        result = so.get_my_tasks(SALES, "EMP-1")
        assert result["unsold_showroom_visits"]["count"] == 1
        assert result["leads_requiring_contact_today"]["count"] == 1
        assert result["action_center"]["count"] == 1

    def test_appointments_within_2_hours_are_surfaced(self):
        _appointment(_iso(_now() + timedelta(hours=1)), assigned_to="EMP-1")
        result = so.get_my_tasks(SALES, "EMP-1")
        assert result["appointments_arriving_within_2_hours"]["count"] == 1

    def test_appointments_outside_2_hours_are_excluded(self):
        _appointment(_iso(_now() + timedelta(hours=5)), assigned_to="EMP-1")
        result = so.get_my_tasks(SALES, "EMP-1")
        assert result["appointments_arriving_within_2_hours"]["count"] == 0

    def test_appointments_scoped_to_this_employee(self):
        _appointment(_iso(_now() + timedelta(hours=1)), assigned_to="EMP-2")
        result = so.get_my_tasks(SALES, "EMP-1")
        assert result["appointments_arriving_within_2_hours"]["count"] == 0

    def test_not_yet_tracked_notes_manager_approval_gap(self):
        result = so.get_my_tasks(SALES, "EMP-1")
        assert "deals_awaiting_manager_approval" in result["not_yet_tracked"]

    def test_no_leads_returns_all_empty_buckets(self):
        result = so.get_my_tasks(SALES, "EMP-1")
        assert result["leads_requiring_contact_today"]["count"] == 0
        assert result["missing_follow_ups"]["count"] == 0
        assert result["unsold_showroom_visits"]["count"] == 0
        assert result["action_center"]["count"] == 0


class TestGetDailyDashboard:

    def test_todays_leads_counted(self):
        today = _now().date().isoformat()
        _lead("LEAD-1", AssignedSalesperson="EMP-1", PipelineCreatedAt=today)
        result = so.get_daily_dashboard(SALES, "EMP-1")
        assert result["todays_leads"]["count"] == 1

    def test_leads_from_other_days_not_counted(self):
        yesterday = (_now() - timedelta(days=1)).date().isoformat()
        _lead("LEAD-1", AssignedSalesperson="EMP-1", PipelineCreatedAt=yesterday)
        result = so.get_daily_dashboard(SALES, "EMP-1")
        assert result["todays_leads"]["count"] == 0

    def test_leads_not_assigned_to_this_employee_not_counted(self):
        today = _now().date().isoformat()
        _lead("LEAD-1", AssignedSalesperson="EMP-2", PipelineCreatedAt=today)
        result = so.get_daily_dashboard(SALES, "EMP-1")
        assert result["todays_leads"]["count"] == 0

    def test_todays_shows_requires_visited_state_and_today_timestamp(self):
        today = _now().date().isoformat()
        _lead("LEAD-1", AssignedSalesperson="EMP-1", PipelineState="VISITED",
              PipelineStateSince=today)
        result = so.get_daily_dashboard(SALES, "EMP-1")
        assert result["todays_shows"]["count"] == 1

    def test_todays_shows_excludes_non_visited_state(self):
        today = _now().date().isoformat()
        _lead("LEAD-1", AssignedSalesperson="EMP-1", PipelineState="CONTACTED",
              PipelineStateSince=today)
        result = so.get_daily_dashboard(SALES, "EMP-1")
        assert result["todays_shows"]["count"] == 0

    def test_write_ups_today_counts_deals_created_today_by_employee(self):
        today = _iso(_now())
        _deal("DEAL-1", created_by="EMP-1", created_at=today)
        result = so.get_daily_dashboard(SALES, "EMP-1")
        assert result["write_ups_today"]["count"] == 1

    def test_write_ups_excludes_deals_by_other_employees(self):
        today = _iso(_now())
        _deal("DEAL-1", created_by="EMP-2", created_at=today)
        result = so.get_daily_dashboard(SALES, "EMP-1")
        assert result["write_ups_today"]["count"] == 0

    def test_deliveries_today_counts_deals_funded_today(self):
        today = _iso(_now())
        _deal("DEAL-1", created_by="EMP-1", funded_at=today)
        result = so.get_daily_dashboard(SALES, "EMP-1")
        assert result["deliveries_today"]["count"] == 1

    def test_deliveries_excludes_deals_funded_on_other_days(self):
        yesterday = _iso(_now() - timedelta(days=1))
        _deal("DEAL-1", created_by="EMP-1", funded_at=yesterday)
        result = so.get_daily_dashboard(SALES, "EMP-1")
        assert result["deliveries_today"]["count"] == 0

    def test_todays_appointments_counted(self):
        _appointment(_iso(_now()), assigned_to="EMP-1", appointment_type="showroom_visit")
        result = so.get_daily_dashboard(SALES, "EMP-1")
        assert result["todays_appointments"]["count"] == 1

    def test_demo_drives_is_subset_of_todays_appointments_by_type(self):
        _appointment(_iso(_now()), assigned_to="EMP-1", appointment_type="test_drive")
        _appointment(_iso(_now()), assigned_to="EMP-1", appointment_type="showroom_visit")
        result = so.get_daily_dashboard(SALES, "EMP-1")
        assert result["todays_appointments"]["count"] == 2
        assert result["demo_drives"]["count"] == 1

    def test_empty_state_returns_zero_counts(self):
        result = so.get_daily_dashboard(SALES, "EMP-1")
        assert result["todays_leads"]["count"] == 0
        assert result["todays_shows"]["count"] == 0
        assert result["write_ups_today"]["count"] == 0
        assert result["deliveries_today"]["count"] == 0
        assert result["todays_appointments"]["count"] == 0
        assert result["demo_drives"]["count"] == 0


class TestGetManagerDashboard:

    def test_unworked_lead_is_new_with_no_field_notes(self):
        _lead("LEAD-1", PipelineState="NEW")
        result = so.get_manager_dashboard(ADMIN)
        assert result["unworked_leads"]["count"] == 1

    def test_new_lead_with_a_note_is_not_unworked(self):
        _lead("LEAD-1", PipelineState="NEW")
        _note("LEAD-1", "call", _iso(_now()))
        result = so.get_manager_dashboard(ADMIN)
        assert result["unworked_leads"]["count"] == 0

    def test_non_new_lead_is_not_unworked(self):
        _lead("LEAD-1", PipelineState="CONTACTED")
        result = so.get_manager_dashboard(ADMIN)
        assert result["unworked_leads"]["count"] == 0

    def test_overdue_follow_ups_counted_platform_wide(self):
        _lead("LEAD-1")
        lead_tasks.create_task(
            lead_id="LEAD-1", task_type="call", description="call back",
            due_at=_iso(_now() - timedelta(days=1)), created_by="EMP-1",
        )
        result = so.get_manager_dashboard(ADMIN)
        assert result["overdue_follow_ups"]["count"] == 1

    def test_deals_stuck_in_fi_reuses_sales_fi_turnover_queue(self):
        _deal("DEAL-1", status="financing", customer_id="CUST-1", vehicle_id="VEH-1")
        result = so.get_manager_dashboard(ADMIN)
        assert result["deals_stuck_in_fi"]["count"] == 1

    def test_trades_awaiting_appraisal_needs_trade_in_and_not_approved(self):
        _deal("DEAL-1", customer_id="CUST-1", vehicle_id="VEH-1",
              trade_in={"approved": False, "acv": 5000})
        result = so.get_manager_dashboard(ADMIN)
        assert result["trades_awaiting_appraisal"]["count"] == 1
        assert result["trades_awaiting_appraisal"]["deals"][0]["id"] == "DEAL-1"

    def test_approved_trade_in_is_excluded(self):
        _deal("DEAL-1", customer_id="CUST-1", vehicle_id="VEH-1",
              trade_in={"approved": True, "acv": 5000})
        result = so.get_manager_dashboard(ADMIN)
        assert result["trades_awaiting_appraisal"]["count"] == 0

    def test_deal_with_no_trade_in_is_excluded(self):
        _deal("DEAL-1", customer_id="CUST-1", vehicle_id="VEH-1")
        result = so.get_manager_dashboard(ADMIN)
        assert result["trades_awaiting_appraisal"]["count"] == 0

    def test_open_to_requests_included_for_allowed_role(self):
        result = so.get_manager_dashboard(ADMIN)
        assert "open_to_requests" in result
        assert result["open_to_requests"]["count"] == 0
        assert result["open_to_requests"]["requests"] == []
        assert "stats" in result["open_to_requests"]

    def test_open_to_requests_degrades_gracefully_for_denied_role(self):
        # MARKETING is outside manager_to_api's _REQUEST_ROLES -- both
        # list_open_tos_api and get_to_stats_api return an {"error": ...}
        # dict. count/requests degrade to 0/[] via the isinstance guard,
        # but "stats" is embedded verbatim, error dict and all.
        result = so.get_manager_dashboard(MARKETING)
        assert result["open_to_requests"]["count"] == 0
        assert result["open_to_requests"]["requests"] == []
        assert "error" in result["open_to_requests"]["stats"]

    def test_empty_state_all_zero(self):
        result = so.get_manager_dashboard(ADMIN)
        assert result["unworked_leads"]["count"] == 0
        assert result["overdue_follow_ups"]["count"] == 0
        assert result["deals_stuck_in_fi"]["count"] == 0
        assert result["trades_awaiting_appraisal"]["count"] == 0


class TestGetMyDay:

    def test_admin_role_is_manager_view_regardless_of_title(self):
        _employee("EMP-1", title="Sales Associate")
        result = so.get_my_day(ADMIN, "EMP-1")
        assert result["is_manager_view"] is True
        assert "manager_dashboard" in result

    def test_operations_role_is_manager_view(self):
        _employee("EMP-1", title="Sales Associate")
        result = so.get_my_day(OPERATIONS, "EMP-1")
        assert result["is_manager_view"] is True

    def test_manager_title_is_manager_view_even_with_sales_role(self):
        _employee("EMP-1", title="Sales Manager")
        result = so.get_my_day(SALES, "EMP-1")
        assert result["is_manager_view"] is True
        assert "manager_dashboard" in result

    def test_staff_title_with_sales_role_is_not_manager_view(self):
        _employee("EMP-1", title="Sales Associate")
        result = so.get_my_day(SALES, "EMP-1")
        assert result["is_manager_view"] is False
        assert "manager_dashboard" not in result

    def test_executive_title_is_manager_view(self):
        _employee("EMP-1", title="General Manager")
        result = so.get_my_day(SALES, "EMP-1")
        assert result["is_manager_view"] is True

    def test_missing_employee_defaults_to_staff_tier(self):
        result = so.get_my_day(SALES, "EMP-DOES-NOT-EXIST")
        assert result["is_manager_view"] is False

    def test_response_always_includes_my_tasks_and_daily_dashboard(self):
        _employee("EMP-1", title="Sales Associate")
        result = so.get_my_day(SALES, "EMP-1")
        assert "my_tasks" in result
        assert "daily_dashboard" in result
