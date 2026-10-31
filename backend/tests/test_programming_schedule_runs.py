"""Tests for Schedule Run / Event / Claim functionality (Section 1).

Covers:
  - claim_item: atomic claim, dependency gating, priority ordering,
    sam_only exclusion, route matching
  - create_run / get_run / list_runs
  - heartbeat_run: lease extension + token/cost accumulation
  - complete_run: outcome setting, lease release
  - release_expired_leases
  - add_event / get_events: audit trail
  - get_active_runs
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.dealeros import ledger  # noqa: E402
from core import programming_schedule as ps  # noqa: E402
from core.entity_types import SCHEDULE_RUN, SCHEDULE_EVENT  # noqa: E402


@pytest.fixture(autouse=True)
def fresh():
    ledger.reset()
    yield
    ledger.reset()


def make_item(title, **kw):
    """Helper: create an item with common defaults."""
    defaults = {"phase": "Phase 0", "priority": "medium", "assignee": "backend",
                "est_hours": 5}
    defaults.update(kw)
    return ps.create_item(title, "", **defaults)


# ---------------------------------------------------------------------------
# claim_item
# ---------------------------------------------------------------------------

def test_claim_basic():
    """Item is claimed, status -> in_progress, lease set, run_id returned."""
    make_item("Claim test A", resource_route="local")
    result = ps.claim_item("local", "desktop")
    assert "error" not in result
    assert result["claimed_by"] == "desktop"
    assert result["status"] == "in_progress"
    assert result["claimed_at"] is not None
    assert result["lease_expires_at"] is not None
    assert result["run_id"] is not None


def test_claim_returns_run_id():
    """Claim creates a ScheduleRun entity and returns its ID."""
    make_item("Claim run test", resource_route="local")
    result = ps.claim_item("local", "desktop")
    assert "run_id" in result
    run = ps.get_run(result["run_id"])
    assert run is not None
    assert run["item_id"] == result["id"]
    assert run["worker"] == "desktop"
    assert run["outcome"] == "running"


def test_claim_sam_only_never_claimed():
    """sam_only items are never claimed by Hermes workers."""
    make_item("Sam-only item", resource_route="sam_only", owner="sam")
    result = ps.claim_item("local", "desktop")
    assert "error" in result


def test_claim_route_mismatch():
    """Items on the wrong route are not claimed."""
    make_item("VPS item", resource_route="vps")
    result = ps.claim_item("local", "desktop")
    assert "error" in result


def test_claim_dependency_gating():
    """Item with incomplete depends_on is skipped."""
    make_item("Dep A", resource_route="local")
    make_item("Dep B depends on A", resource_route="local", depends_on=["PS-dep-a"])
    result = ps.claim_item("local", "desktop")
    assert "error" not in result
    assert result["id"] == "PS-dep-a"  # Only the dependency-free item is claimed


def test_claim_priority_ordering():
    """Items are claimed in phase, then priority order, then est_hours."""
    # Phase 0, critical, 10h
    make_item("Crit item", phase="Phase 0", priority="critical", est_hours=10)
    # Phase 0, high, 10h (should come before crit because phase is same, critical > high)
    # Wait — critical > high, so critical should come first
    make_item("High item", phase="Phase 0", priority="high", est_hours=10)
    # Phase 0, critical, 5h (same priority as crit item, lower est_hours → comes first)
    make_item("Crit cheap", phase="Phase 0", priority="critical", est_hours=5)

    result = ps.claim_item("local", "desktop")
    assert "error" not in result
    # Critical + lowest hours should be first
    assert result["id"] == "PS-crit-cheap"


def test_claim_phase_ordering():
    """Phase 0 items come before Phase 1 items."""
    make_item("Phase 1 item", phase="Phase 1", resource_route="local")
    make_item("Phase 0 item", phase="Phase 0", resource_route="local")
    result = ps.claim_item("local", "desktop")
    assert "error" not in result
    assert result["phase"] == "Phase 0"


def test_claim_skips_already_claimed():
    """Already-claimed items are skipped."""
    make_item("Item A", resource_route="local")
    make_item("Item B", resource_route="local")
    # First claim grabs Item A (alphabetically first in Phase 0, medium priority)
    result = ps.claim_item("local", "desktop")
    assert result["id"] == "PS-item-a"
    # Second claim should grab Item B
    result2 = ps.claim_item("local", "desktop")
    assert result2["id"] == "PS-item-b"


def test_claim_invalid_route():
    assert "error" in ps.claim_item("mars_base", "desktop")


def test_claim_invalid_worker():
    make_item("Item", resource_route="local")
    assert "error" in ps.claim_item("local", "invalid_worker")


# ---------------------------------------------------------------------------
# heartbeat_run
# ---------------------------------------------------------------------------

def test_heartbeat_extends_lease():
    """heartbeat extends lease_expires_at on the parent item."""
    item = make_item("Heartbeat test", resource_route="local")
    claim_result = ps.claim_item("local", "desktop")
    run_id = claim_result["run_id"]

    # Record lease before heartbeat
    item_entity = ledger.get_entity(item["id"])
    lease_before = item_entity.attributes["lease_expires_at"]

    import time
    time.sleep(0.01)  # Ensure time advances
    ps.heartbeat_run(run_id)
    item_entity = ledger.get_entity(item["id"])
    lease_after = item_entity.attributes["lease_expires_at"]

    assert lease_after > lease_before


def test_heartbeat_accumulates_tokens():
    """heartbeat adds token counts and cost to the run."""
    make_item("Token test", resource_route="local")
    claim_result = ps.claim_item("local", "desktop")
    run_id = claim_result["run_id"]

    result = ps.heartbeat_run(run_id, input_tokens=100, output_tokens=50,
                              cache_read_tokens=20, cost_usd=0.005)
    assert "error" not in result
    assert result["input_tokens"] == 100
    assert result["output_tokens"] == 50
    assert result["cache_read_tokens"] == 20
    assert result["cost_usd"] == 0.005


# ---------------------------------------------------------------------------
# complete_run
# ---------------------------------------------------------------------------

def test_complete_run_releases_lease():
    """complete_run with 'completed' outcome releases the lease."""
    make_item("Complete test", resource_route="local")
    claim_result = ps.claim_item("local", "desktop")
    run_id = claim_result["run_id"]

    result = ps.complete_run(run_id, "completed", commit_sha="abc123",
                            tests_summary="5 passed, 0 failed", notes="all good")
    assert "error" not in result
    assert result["outcome"] == "completed"
    assert result["finished_at"] is not None
    assert result["commit_sha"] == "abc123"
    assert result["tests_summary"] == "5 passed, 0 failed"

    # Lease should be released
    item = ps.get_item(claim_result["id"])
    assert item["claimed_by"] is None
    assert item["lease_expires_at"] is None


def test_complete_run_abandoned_keeps_item():
    """complete_run with 'abandoned' also releases lease."""
    make_item("Abandon test", resource_route="local")
    claim_result = ps.claim_item("local", "desktop")
    run_id = claim_result["run_id"]

    ps.complete_run(run_id, "abandoned", notes="stuck")
    item = ps.get_item(claim_result["id"])
    assert item["claimed_by"] is None


def test_complete_run_invalid_outcome():
    make_item("Invalid outcome", resource_route="local")
    claim_result = ps.claim_item("local", "desktop")
    result = ps.complete_run(claim_result["run_id"], "invalid_outcome")
    assert "error" in result


# ---------------------------------------------------------------------------
# release_expired_leases
# ---------------------------------------------------------------------------

def test_release_expired_leases():
    """Expired leases are released back to todo."""
    make_item("Expiring item", resource_route="local")
    claim_result = ps.claim_item("local", "desktop")

    # Manually expire the lease
    item_entity = ledger.get_entity(claim_result["id"])
    from datetime import datetime, timedelta, timezone
    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    item_entity.attributes["lease_expires_at"] = past

    released = ps.release_expired_leases()
    assert released >= 1

    item = ps.get_item(claim_result["id"])
    assert item["claimed_by"] is None
    assert item["lease_expires_at"] is None


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

def test_add_event():
    """add_event creates a ScheduleEvent entity."""
    item = make_item("Event test", resource_route="local")
    result = ps.add_event(item["id"], "status_change", "admin", "Set to in_review")
    assert "error" not in result
    assert result["event_type"] == "status_change"
    assert result["actor"] == "admin"
    assert result["evidence"] == "Set to in_review"


def test_get_events():
    """get_events returns all events for an item in order."""
    item1 = make_item("Item 1", resource_route="local")
    item2 = make_item("Item 2", resource_route="local")

    ps.add_event(item1["id"], "created", "admin", "Initial creation")
    ps.add_event(item1["id"], "claimed", "desktop", "Claimed by desktop")
    ps.add_event(item2["id"], "created", "admin", "Initial creation")

    events1 = ps.get_events(item1["id"])
    assert len(events1) == 2
    assert events1[0]["event_type"] == "created"
    assert events1[1]["event_type"] == "claimed"

    events2 = ps.get_events(item2["id"])
    assert len(events2) == 1


def test_add_event_invalid_type():
    item = make_item("Invalid event", resource_route="local")
    result = ps.add_event(item["id"], "invalid_type", "admin", "test")
    assert "error" in result


# ---------------------------------------------------------------------------
# get_active_runs
# ---------------------------------------------------------------------------

def test_get_active_runs():
    """get_active_runs returns only 'running' runs."""
    make_item("Run A", resource_route="local")
    make_item("Run B", resource_route="vps")
    r1 = ps.claim_item("local", "desktop")
    r2 = ps.claim_item("vps", "vps")

    # Complete run A
    ps.complete_run(r1["run_id"], "completed", tests_summary="all pass")

    active = ps.get_active_runs()
    assert len(active) == 1
    assert active[0]["id"] == r2["run_id"]
    assert active[0]["outcome"] == "running"


if __name__ == "__main__":
    import traceback
    _tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    failed = 0
    for test in _tests:
        try:
            ledger.reset()
            test()
            passed += 1
            print(f"  {test.__name__}: PASS")
        except Exception as e:
            failed += 1
            print(f"  {test.__name__}: FAIL — {e}")
            traceback.print_exc()
        finally:
            ledger.reset()
    print(f"\n{passed} passed, {failed} failed ({passed + failed} total)")
