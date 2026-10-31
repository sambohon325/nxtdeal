"""
Tests for the agentic bot layer (core/bot_tasks.py, core/bot_learning.py,
core/bot_coverage.py, core/bot_actions.py, core/bot_api.py) -- session 36. Run from
backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

from datetime import datetime, timedelta, timezone

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import EMPLOYEE, LEAD, DEAL
from core.relationships import Relationship
from core.relationship_types import ASSIGNED_TO
from core.pipeline_state import start_pipeline, get_pipeline_state_since
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE

from core import bot_tasks
from core import bot_learning
from core import bot_coverage
from core import bot_actions
from core import bot_api


@pytest.fixture(autouse=True)
def fresh_ledger():

    ledger.reset()

    yield

    ledger.reset()


@pytest.fixture(autouse=True)
def grant_bot_capabilities(fresh_ledger, monkeypatch):
    """Security-hardening pass (2026-07-20, Task #7 "Build Bot Permission
    Layer"): bot_coverage.start_coverage()'s auto-mode path and
    bot_actions.run_action() are now gated by core/bot_permissions.py's own
    separate, additive, default-deny capability check, checked BEFORE
    either function's own real logic runs. This file's own tests here
    predate that gate and are about coverage/action-execution behavior
    itself, not about the permission layer (which gets its own dedicated
    tests/test_bot_permissions.py) -- granting both real capabilities
    dealer-wide before every test, against the same fresh, isolated ledger
    fresh_ledger() just reset, keeps these tests scoped to what they were
    actually designed to test rather than silently failing on an
    unrelated, newer gate."""

    import core.bot_permissions as bot_permissions_mod
    monkeypatch.setattr(bot_permissions_mod, "save_graph", lambda filepath: None)
    monkeypatch.setattr(bot_permissions_mod, "save_audit_log", lambda filepath: None)

    from core.bot_permissions import grant_capability
    grant_capability("bot.coverage.auto_mode", "dealer_wide", True, "EMP-TEST-SETUP")
    grant_capability(
        "bot.action.auto_touch_overdue_leads", "dealer_wide", True, "EMP-TEST-SETUP"
    )
    yield


def _add_employee(employee_id, department, title):

    ledger.add_entity(Entity(
        id=employee_id,
        entity_type=EMPLOYEE,
        attributes={"Department": department, "Title": title}
    ))


def _add_lead(lead_id, days_old):

    ledger.add_entity(Entity(id=lead_id, entity_type=LEAD, attributes={}))

    start_pipeline(lead_id, "NEW")

    # Back-date PipelineStateSince so the follow-up gap check sees it as overdue.
    lead = ledger.get_entity(lead_id)
    stale = datetime.now() - timedelta(days=days_old)
    lead.attributes["PipelineStateSince"] = stale.isoformat()


def _assign(employee_id, lead_id):

    ledger.add_relationship(
        Relationship(source_id=employee_id, target_id=lead_id, relationship_type=ASSIGNED_TO)
    )


def _add_stuck_deal(deal_id, hours_old):

    stale = (datetime.now(timezone.utc) - timedelta(hours=hours_old)).isoformat()

    ledger.add_entity(Entity(
        id=deal_id,
        entity_type=DEAL,
        attributes={"status": "financing", "updated_at": stale}
    ))


# ---------------------------------------------------------------------------
# infer_tier / time_bucket
# ---------------------------------------------------------------------------

def test_infer_tier_staff():
    assert bot_tasks.infer_tier("Sales Consultant") == bot_tasks.TIER_STAFF
    assert bot_tasks.infer_tier("Service Technician") == bot_tasks.TIER_STAFF
    assert bot_tasks.infer_tier(None) == bot_tasks.TIER_STAFF


def test_infer_tier_manager():
    assert bot_tasks.infer_tier("Sales Manager") == bot_tasks.TIER_MANAGER
    assert bot_tasks.infer_tier("F&I Manager") == bot_tasks.TIER_MANAGER
    assert bot_tasks.infer_tier("Marketing Director") == bot_tasks.TIER_MANAGER


def test_infer_tier_executive_general_manager_not_manager():
    # "general manager" must win over the plain "manager" keyword.
    assert bot_tasks.infer_tier("General Manager") == bot_tasks.TIER_EXECUTIVE
    assert bot_tasks.infer_tier("Controller") == bot_tasks.TIER_EXECUTIVE
    assert bot_tasks.infer_tier("Owner") == bot_tasks.TIER_EXECUTIVE


def test_time_bucket_boundaries():
    morning = datetime(2026, 7, 13, 9, 0, tzinfo=timezone.utc)
    midday = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)
    end_of_day = datetime(2026, 7, 13, 17, 0, tzinfo=timezone.utc)

    assert bot_tasks.time_bucket(morning) == "morning"
    assert bot_tasks.time_bucket(midday) == "midday"
    assert bot_tasks.time_bucket(end_of_day) == "end_of_day"


# ---------------------------------------------------------------------------
# generate_tasks -- catalog resolution + gap checks
# ---------------------------------------------------------------------------

def test_generate_tasks_sales_staff_followup_gap_detected():

    _add_employee("EMP-00001", "Sales", "Sales Consultant")
    _add_lead("LEAD-00001", days_old=3)
    _assign("EMP-00001", "LEAD-00001")

    tasks = bot_tasks.generate_tasks("EMP-00001", SALES, "sales")

    keys = [t["key"] for t in tasks]
    assert "sales_followup_leads" in keys

    followup_task = next(t for t in tasks if t["key"] == "sales_followup_leads")
    assert "1 of your leads" in followup_task["description"]


def test_generate_tasks_sales_staff_no_gap_when_leads_current():

    _add_employee("EMP-00002", "Sales", "Sales Consultant")
    _add_lead("LEAD-00002", days_old=0)
    _assign("EMP-00002", "LEAD-00002")

    tasks = bot_tasks.generate_tasks("EMP-00002", SALES, "sales")

    keys = [t["key"] for t in tasks]
    assert "sales_followup_leads" not in keys


def test_generate_tasks_sales_manager_financing_gap():

    _add_employee("EMP-00003", "Sales", "Sales Manager")
    _add_stuck_deal("DEAL-00001", hours_old=48)

    tasks = bot_tasks.generate_tasks("EMP-00003", SALES, "sales")

    keys = [t["key"] for t in tasks]
    assert "sales_mgr_financing_queue" in keys


def test_generate_tasks_sales_manager_no_financing_gap_when_deal_recent():

    _add_employee("EMP-00004", "Sales", "Sales Manager")
    _add_stuck_deal("DEAL-00002", hours_old=2)

    tasks = bot_tasks.generate_tasks("EMP-00004", SALES, "sales")

    keys = [t["key"] for t in tasks]
    assert "sales_mgr_financing_queue" not in keys


def test_generate_tasks_prompts_are_nonempty_strings():

    _add_employee("EMP-00005", "Sales", "General Manager")

    tasks = bot_tasks.generate_tasks("EMP-00005", OPERATIONS, "sales")

    assert tasks
    for t in tasks:
        assert t["prompt"]
        assert t["title"]


def test_generate_tasks_administration_tier_invariant():

    _add_employee("EMP-00006", "Operations", "IT Administrator")

    staff_tasks = bot_tasks.generate_tasks("EMP-00006", ADMIN, "administration")

    _add_employee("EMP-00007", "Operations", "General Manager")

    exec_tasks = bot_tasks.generate_tasks("EMP-00007", ADMIN, "administration")

    assert {t["key"] for t in staff_tasks} == {t["key"] for t in exec_tasks}


def test_generate_tasks_unknown_section_falls_back_to_department():

    _add_employee("EMP-00008", "Finance", "F&I Manager")

    tasks = bot_tasks.generate_tasks("EMP-00008", FINANCE, "not-a-real-section")

    keys = [t["key"] for t in tasks]
    assert any(k.startswith("finance_mgr_") for k in keys)


def test_generate_tasks_no_employee_entity_still_returns_role_fallback():

    tasks = bot_tasks.generate_tasks("EMP-NOPE", SERVICE, "service")

    # No Employee entity backing this id -> tier defaults to staff, section stays
    # "service" (a valid catalog key), so the staff service catalog should come back.
    keys = [t["key"] for t in tasks]
    assert any(k.startswith("service_") for k in keys)


# ---------------------------------------------------------------------------
# bot_learning -- heuristic affinity
# ---------------------------------------------------------------------------

def test_affinity_neutral_with_no_history():

    affinity = bot_learning.get_task_affinity("EMP-X", "some_task")

    assert affinity["suppressed"] is False
    assert affinity["priority_boost"] == 0


def test_affinity_acted_boosts_priority():

    bot_learning.record_task_event("EMP-X", "task_a", "acted")
    bot_learning.record_task_event("EMP-X", "task_a", "acted")

    affinity = bot_learning.get_task_affinity("EMP-X", "task_a")

    assert affinity["priority_boost"] == 2
    assert affinity["suppressed"] is False


def test_affinity_suppressed_after_three_consecutive_dismissals():

    bot_learning.record_task_event("EMP-Y", "task_b", "dismissed")
    bot_learning.record_task_event("EMP-Y", "task_b", "dismissed")
    bot_learning.record_task_event("EMP-Y", "task_b", "dismissed")

    affinity = bot_learning.get_task_affinity("EMP-Y", "task_b")

    assert affinity["suppressed"] is True


def test_affinity_act_resets_dismiss_streak():

    bot_learning.record_task_event("EMP-Z", "task_c", "dismissed")
    bot_learning.record_task_event("EMP-Z", "task_c", "dismissed")
    bot_learning.record_task_event("EMP-Z", "task_c", "acted")
    bot_learning.record_task_event("EMP-Z", "task_c", "dismissed")

    affinity = bot_learning.get_task_affinity("EMP-Z", "task_c")

    # Only one dismissal since the last act -- not suppressed yet.
    assert affinity["suppressed"] is False


def test_record_task_event_rejects_unknown_event_type():

    with pytest.raises(ValueError):
        bot_learning.record_task_event("EMP-X", "task_a", "ignored")


def test_generate_tasks_respects_suppression():

    _add_employee("EMP-00009", "Sales", "Sales Manager")
    _add_stuck_deal("DEAL-00003", hours_old=48)

    for _ in range(3):
        bot_learning.record_task_event("EMP-00009", "sales_mgr_financing_queue", "dismissed")

    tasks = bot_tasks.generate_tasks("EMP-00009", SALES, "sales")

    keys = [t["key"] for t in tasks]
    assert "sales_mgr_financing_queue" not in keys


# ---------------------------------------------------------------------------
# bot_coverage
# ---------------------------------------------------------------------------

def test_start_coverage_requires_existing_employee():

    result = bot_coverage.start_coverage(
        "EMP-ADMIN", "EMP-NOPE", SALES, "sales",
        "2026-07-13T00:00:00+00:00", "2026-07-13T23:59:00+00:00", "draft"
    )

    assert "error" in result


def test_start_coverage_rejects_bad_mode():

    _add_employee("EMP-00010", "Sales", "Sales Consultant")

    result = bot_coverage.start_coverage(
        "EMP-ADMIN", "EMP-00010", SALES, "sales",
        "2026-07-13T00:00:00+00:00", "2026-07-13T23:59:00+00:00", "yolo"
    )

    assert "error" in result


def test_start_coverage_rejects_end_before_start():

    _add_employee("EMP-00011", "Sales", "Sales Consultant")

    result = bot_coverage.start_coverage(
        "EMP-ADMIN", "EMP-00011", SALES, "sales",
        "2026-07-13T23:00:00+00:00", "2026-07-13T01:00:00+00:00", "draft"
    )

    assert "error" in result


def test_start_end_and_list_coverage_roundtrip():

    _add_employee("EMP-00012", "Sales", "Sales Consultant")

    now = datetime.now(timezone.utc)
    starts = (now - timedelta(minutes=5)).isoformat()
    ends = (now + timedelta(hours=8)).isoformat()

    started = bot_coverage.start_coverage(
        "EMP-ADMIN", "EMP-00012", SALES, "sales", starts, ends, "auto", note="out sick"
    )
    assert "coverage" in started
    coverage_id = started["coverage"]["id"]

    active = bot_coverage.get_active_coverage_for("EMP-00012")
    assert active is not None
    assert active["mode"] == "auto"

    all_active = bot_coverage.list_coverage(active_only=True)
    assert any(c["id"] == coverage_id for c in all_active)

    ended = bot_coverage.end_coverage(coverage_id, "EMP-ADMIN")
    assert ended["coverage"]["status"] == "ended"

    assert bot_coverage.get_active_coverage_for("EMP-00012") is None


def test_end_coverage_twice_errors():

    _add_employee("EMP-00013", "Sales", "Sales Consultant")

    now = datetime.now(timezone.utc)
    started = bot_coverage.start_coverage(
        "EMP-ADMIN", "EMP-00013", SALES, "sales",
        (now - timedelta(minutes=5)).isoformat(),
        (now + timedelta(hours=1)).isoformat(),
        "draft"
    )
    coverage_id = started["coverage"]["id"]

    bot_coverage.end_coverage(coverage_id, "EMP-ADMIN")
    second = bot_coverage.end_coverage(coverage_id, "EMP-ADMIN")

    assert "error" in second


# ---------------------------------------------------------------------------
# bot_actions -- whitelist + safety
# ---------------------------------------------------------------------------

def test_run_action_unknown_key_returns_none():

    result = bot_actions.run_action("not_a_real_task", "EMP-00001", "EMP-ADMIN")
    assert result is None


def test_run_action_touches_overdue_leads():

    _add_employee("EMP-00014", "Sales", "Sales Consultant")
    _add_lead("LEAD-00003", days_old=5)
    _assign("EMP-00014", "LEAD-00003")

    before = get_pipeline_state_since("LEAD-00003")

    result = bot_actions.run_action("sales_followup_leads", "EMP-00014", "EMP-ADMIN")

    assert result is not None
    assert "LEAD-00003" in result["touched_leads"]

    after = get_pipeline_state_since("LEAD-00003")
    assert after > before


# ---------------------------------------------------------------------------
# bot_api -- ACL
# ---------------------------------------------------------------------------

def test_start_coverage_api_requires_admin_role():

    _add_employee("EMP-00015", "Sales", "Sales Consultant")

    now = datetime.now(timezone.utc)
    result = bot_api.start_coverage_api(
        SALES, "EMP-BOSS", "EMP-00015", SALES, "sales",
        now.isoformat(), (now + timedelta(hours=1)).isoformat(), "draft"
    )

    assert "error" in result


def test_list_coverage_api_requires_admin_role():

    result = bot_api.list_coverage_api(SALES)
    assert "error" in result


def test_get_my_tasks_api_returns_task_list():

    _add_employee("EMP-00016", "Service", "Service Advisor")

    result = bot_api.get_my_tasks_api("EMP-00016", SERVICE, "service")

    assert "tasks" in result
    assert isinstance(result["tasks"], list)


def test_record_feedback_api_rejects_bad_event_type():

    result = bot_api.record_feedback_api("EMP-00016", "some_task", "whatever")
    assert "error" in result


def test_record_feedback_api_success():

    result = bot_api.record_feedback_api("EMP-00016", "some_task", "acted")
    assert result == {"success": True}
