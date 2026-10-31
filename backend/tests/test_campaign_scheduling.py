"""
Bumper-parity campaign tooling (2026-07-25): Duplication Station, Multi-Planner, Recurring
Schedule. Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import CUSTOMER, RECURRING_SCHEDULE
from core import campaigns


@pytest.fixture(autouse=True)
def fresh():
    ledger.reset()
    yield
    ledger.reset()


def _add_customer(cid="CUST-1"):
    ledger.add_entity(Entity(id=cid, entity_type=CUSTOMER, attributes={"name": "Jane Doe", "email": "j@d.com"}))


def _base_campaign(name="Spring Service Push"):
    _add_customer()
    return campaigns.create_campaign("retention", name, "email", "EMP-1", {"months_since_service": 6})


# --- Duplication Station ---

def test_duplicate_campaign_clones_into_a_fresh_draft():
    base = _base_campaign()
    base.attributes["notes"] = "hello"
    clone = campaigns.duplicate_campaign(base.id, "EMP-2")
    assert clone.id != base.id
    assert clone.attributes["status"] == "draft"
    assert clone.attributes["name"] == "Spring Service Push (Copy)"
    assert clone.attributes["campaign_type"] == "retention"
    assert clone.attributes["channel"] == "email"
    assert clone.attributes["notes"] == "hello"
    assert clone.attributes["duplicated_from"] == base.id
    assert clone.attributes["created_by"] == "EMP-2"


def test_duplicate_campaign_accepts_a_new_name_and_rejects_unknown():
    base = _base_campaign()
    clone = campaigns.duplicate_campaign(base.id, "EMP-1", new_name="Custom Name")
    assert clone.attributes["name"] == "Custom Name"
    assert "error" in campaigns.duplicate_campaign("CAMP-NOPE", "EMP-1")


# --- Multi-Planner ---

def test_bulk_create_campaigns_creates_valid_and_reports_bad():
    _add_customer()
    result = campaigns.bulk_create_campaigns([
        {"campaign_type": "retention", "name": "A", "channel": "email", "params": {"months_since_service": 6}},
        {"campaign_type": "retention", "name": "", "channel": "email"},          # missing name
        {"campaign_type": "bogus", "name": "C", "channel": "email"},             # bad type
        {"campaign_type": "retention", "name": "D", "channel": "carrier_pigeon"},  # bad channel
    ], "EMP-1")
    assert result["created_count"] == 1
    assert len(result["errors"]) == 3
    assert {e["index"] for e in result["errors"]} == {1, 2, 3}


# --- Recurring Schedule ---

def test_create_recurring_schedule_validates():
    base = _base_campaign()
    assert "error" in campaigns.create_recurring_schedule("CAMP-NOPE", "monthly", "2026-01-01", "EMP-1")
    assert "error" in campaigns.create_recurring_schedule(base.id, "yearly", "2026-01-01", "EMP-1")
    assert "error" in campaigns.create_recurring_schedule(base.id, "monthly", "not-a-date", "EMP-1")
    assert "error" in campaigns.create_recurring_schedule(base.id, "monthly", "2026-02-01", "EMP-1", end_date="2026-01-01")
    sched = campaigns.create_recurring_schedule(base.id, "monthly", "2026-01-01", "EMP-1")
    assert sched.entity_type == RECURRING_SCHEDULE
    assert sched.attributes["next_run_date"] == "2026-01-01"
    assert sched.attributes["active"] is True


def test_add_cadence_advances_correctly():
    from datetime import date
    assert campaigns._add_cadence(date(2026, 1, 31), "daily", 1) == date(2026, 2, 1)
    assert campaigns._add_cadence(date(2026, 1, 1), "weekly", 2) == date(2026, 1, 15)
    # month-end clamp: Jan 31 + 1 month -> Feb 28 (2026 not a leap year)
    assert campaigns._add_cadence(date(2026, 1, 31), "monthly", 1) == date(2026, 2, 28)
    assert campaigns._add_cadence(date(2026, 11, 15), "monthly", 2) == date(2027, 1, 15)


def test_run_due_recurring_schedules_launches_and_advances():
    base = _base_campaign()
    campaigns.create_recurring_schedule(base.id, "monthly", "2026-01-01", "EMP-1")
    # As of Feb 15, both the Jan 1 and Feb 1 runs are due.
    result = campaigns.run_due_recurring_schedules(today="2026-02-15")
    assert result["launched_count"] == 2
    launched_campaigns = [ln["campaign_id"] for ln in result["launched"]]
    for cid in launched_campaigns:
        c = campaigns.get_campaign(cid)
        assert c.attributes["status"] == "active"          # cloned AND launched
        assert c.attributes["duplicated_from"] == base.id
    sched = campaigns.list_recurring_schedules()[0]
    assert sched.attributes["next_run_date"] == "2026-03-01"   # advanced past the due window
    # A second pass on the same day launches nothing new.
    assert campaigns.run_due_recurring_schedules(today="2026-02-15")["launched_count"] == 0


def test_recurring_schedule_respects_end_date_and_pause():
    base = _base_campaign()
    sched = campaigns.create_recurring_schedule(base.id, "monthly", "2026-01-01", "EMP-1", end_date="2026-02-28")
    result = campaigns.run_due_recurring_schedules(today="2026-12-31")
    assert result["launched_count"] == 2                    # Jan + Feb only, then stops at end_date
    assert campaigns.list_recurring_schedules()[0].attributes["active"] is False

    # Pause guard: an inactive schedule never launches.
    base2 = _base_campaign("Second")
    s2 = campaigns.create_recurring_schedule(base2.id, "daily", "2026-01-01", "EMP-1")
    campaigns.set_recurring_schedule_active(s2.id, False)
    before = len(ledger.get_all())
    campaigns.run_due_recurring_schedules(today="2026-01-10")
    # only the first schedule's (already-run) campaigns exist; s2 launched nothing
    assert all(
        c.attributes.get("duplicated_from") != base2.id
        for c in ledger.get_all().values() if c.entity_type.__str__() == "Campaign"
    )


# --- API-layer role gating ---

def test_api_duplicate_respects_view_access():
    from core import campaigns_api
    from core.permissions import ADMIN, SALES
    base = campaigns.create_campaign("retention", "Owned by EMP-1", "email", "EMP-1", {"months_since_service": 6})
    _add_customer()
    # A different SALES rep can't open (and therefore can't clone) someone else's campaign.
    blocked = campaigns_api.duplicate_campaign_api(SALES, "EMP-9", base.id)
    assert "error" in blocked
    # ADMIN can.
    ok = campaigns_api.duplicate_campaign_api(ADMIN, "EMP-9", base.id)
    assert ok["status"] == "draft" and ok["duplicated_from"] == base.id


def test_api_run_and_pause_require_activation_role():
    from core import campaigns_api
    from core.permissions import ADMIN, SALES
    base = _base_campaign()
    sched = campaigns_api.create_recurring_schedule_api("EMP-1", base.id, "monthly", "2026-01-01")
    assert "id" in sched
    # A plain SALES rep can't fire schedules (that sends) or pause them.
    assert "error" in campaigns_api.run_due_recurring_schedules_api(SALES, "EMP-1", today="2026-02-15")
    assert "error" in campaigns_api.set_recurring_schedule_active_api(SALES, "EMP-1", sched["id"], False)
    # ADMIN can run; it launches the due Jan + Feb runs.
    result = campaigns_api.run_due_recurring_schedules_api(ADMIN, "EMP-1", today="2026-02-15")
    assert result["launched_count"] == 2


def test_api_bulk_create_rejects_empty():
    from core import campaigns_api
    assert "error" in campaigns_api.bulk_create_campaigns_api("EMP-1", [])
    _add_customer()
    good = campaigns_api.bulk_create_campaigns_api("EMP-1", [
        {"campaign_type": "retention", "name": "A", "channel": "email", "params": {"months_since_service": 6}},
    ])
    assert good["created_count"] == 1
