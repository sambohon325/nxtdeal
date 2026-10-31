"""
Programming Schedule tracker tests (2026-10-24).
Run from backend/ with `python -c "from core.dealeros import ledger; from core import programming_schedule as ps; ..."`
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.dealeros import ledger
from core import programming_schedule as ps
from core.entity_types import PROGRAMMING_SCHEDULE
from core.entities import Entity


@pytest.fixture(autouse=True)
def fresh():
    ledger.reset()
    yield
    ledger.reset()


def test_create_item():
    item = ps.create_item("Test feature", "A test", item_type="feature",
                          phase="Phase 1", priority="high", assignee="backend", est_hours=8)
    assert "error" not in item
    assert item["id"] == "PS-test-feature"
    assert item["title"] == "Test feature"
    assert item["phase"] == "Phase 1"
    assert item["progress"] == 0
    assert item["status"] == "todo"
    assert item["type"] == "feature"
    assert item["assignee"] == "backend"
    assert item["est_hours"] == 8
    assert item["logged_hours"] == 0
    assert item["depends_on"] == []
    assert item["security_severity"] is None


def test_get_item():
    ps.create_item("Get test", "", phase="Phase 0")
    item = ps.get_item("PS-get-test")
    assert item is not None
    assert item["title"] == "Get test"
    assert ps.get_item("PS-nonexistent") is None


def test_list_items_unfiltered():
    ps.create_item("List A", "", phase="Phase 0")
    ps.create_item("List B", "", phase="Phase 1")
    items = ps.list_items()
    assert len(items) == 2


def test_list_items_filtered():
    ps.create_item("Bug one", "", item_type="bug", phase="Phase 1", priority="high", assignee="backend")
    ps.create_item("Bug two", "", item_type="bug", phase="Phase 2", priority="low", assignee="frontend")
    ps.create_item("Feature one", "", item_type="feature", phase="Phase 1", priority="high")

    assert len(ps.list_items(item_type="bug")) == 2
    assert len(ps.list_items(phase="Phase 1")) == 2
    assert len(ps.list_items(assignee="backend")) == 1
    assert len(ps.list_items(priority="high")) == 2
    assert len(ps.list_items(status="todo")) == 3
    assert len(ps.list_items(item_type="feature", phase="Phase 1")) == 1


def test_list_items_sorted():
    ps.create_item("Zeta", "", item_type="bug", phase="Phase 1", priority="low")
    ps.create_item("Alpha", "", item_type="feature", phase="Phase 1", priority="critical")
    ps.create_item("Mid", "", item_type="tech-debt", phase="Phase 0", priority="medium")
    items = ps.list_items()
    # Phase 0 first
    assert items[0]["phase"] == "Phase 0"
    # Within Phase 1, priority desc: critical first
    phase1_items = [i for i in items if i["phase"] == "Phase 1"]
    assert phase1_items[0]["priority"] == "critical"


def test_update_item():
    ps.create_item("Update me", "", phase="Phase 0")
    result = ps.update_item("PS-update-me", status="in_progress", priority="high")
    assert "error" not in result
    assert result["status"] == "in_progress"
    assert result["priority"] == "high"
    fetched = ps.get_item("PS-update-me")
    assert fetched["status"] == "in_progress"


def test_update_progress():
    ps.create_item("Progress test", "", phase="Phase 0")
    ps.update_progress("PS-progress-test", 50)
    item = ps.get_item("PS-progress-test")
    assert item is not None
    assert item["progress"] == 50
    assert item["status"] == "in_progress"

    # Auto-advance to in_review at 100
    ps.update_progress("PS-progress-test", 100)
    fetched = ps.get_item("PS-progress-test")
    assert fetched is not None
    assert fetched["progress"] == 100
    assert fetched["status"] == "in_review"


def test_update_progress_invalid():
    ps.create_item("Bad progress", "", phase="Phase 0")
    assert "error" in ps.update_progress("PS-bad-progress", 101)
    assert "error" in ps.update_progress("PS-bad-progress", -1)
    assert "error" in ps.update_progress("PS-bad-progress", 50.5)  # type: ignore[arg-type]


def test_set_progress_invalid_user():
    assert "error" in ps.update_progress("PS-nonexistent", 50)


def test_assign_item():
    ps.create_item("Assign me", "", phase="Phase 0")
    result = ps.assign_item("PS-assign-me", "frontend")
    assert "error" not in result
    assert result["assignee"] == "frontend"
    assert ps.get_item("PS-assign-me")["assignee"] == "frontend"


def test_assign_item_invalid():
    ps.create_item("Bad assign", "", phase="Phase 0")
    assert "error" in ps.assign_item("PS-bad-assign", "not-a-team")


def test_set_status():
    ps.create_item("Status test", "", phase="Phase 0")
    result = ps.set_status("PS-status-test", "in_progress")
    assert result["status"] == "in_progress"
    result = ps.set_status("PS-status-test", "done")
    assert result["status"] == "done"


def test_set_status_invalid():
    ps.create_item("Bad status", "", phase="Phase 0")
    assert "error" in ps.set_status("PS-bad-status", "not-a-status")


def test_add_hours():
    ps.create_item("Hours test", "", phase="Phase 0", est_hours=10)
    result = ps.add_hours("PS-hours-test", 3.5)
    assert result["logged_hours"] == 3.5
    result = ps.add_hours("PS-hours-test", 2.0)
    assert result["logged_hours"] == 5.5


def test_add_hours_invalid():
    ps.create_item("Bad hours", "", phase="Phase 0")
    assert "error" in ps.add_hours("PS-bad-hours", -5)


def test_security_item_requires_severity():
    err = ps.create_item("Security issue", "", item_type="security", priority="high")
    assert "error" in err

    item = ps.create_item("Security issue", "", item_type="security", priority="high", security_severity="critical")
    assert "error" not in item
    assert item["security_severity"] == "critical"


def test_invalid_type_rejected():
    assert "error" in ps.create_item("Bad type", "", item_type="not-a-type")


def test_invalid_phase_rejected():
    assert "error" in ps.create_item("Bad phase", "", phase="Phase 99")


def test_invalid_priority_rejected():
    assert "error" in ps.create_item("Bad priority", "", priority="urgent")


def test_invalid_assignee_rejected():
    assert "error" in ps.create_item("Bad assignee", "", assignee="not-a-team")


def test_title_required():
    assert "error" in ps.create_item("", "no title")


def test_duplicate_rejected():
    ps.create_item("Duplicate", "", phase="Phase 0")
    assert "error" in ps.create_item("Duplicate", "", phase="Phase 0")


def test_progress_bounds():
    ps.create_item("Progress bounds", "", phase="Phase 0")
    item = ps.get_item("PS-progress-bounds")
    assert item is not None
    assert "error" in ps.update_progress("PS-progress-bounds", 101)
    assert "error" in ps.update_progress("PS-progress-bounds", -1)
    assert "error" in ps.update_progress("PS-progress-bounds", 50.5)  # type: ignore[arg-type]


def test_get_dashboard_empty():
    dashboard = ps.get_dashboard()
    assert dashboard["total"] == 0
    assert dashboard["completed"] == 0
    assert dashboard["security_issues"] == 0
    assert dashboard["blockers"] == 0


def test_get_dashboard_with_items():
    ps.create_item("Feature 1", "", item_type="feature", phase="Phase 0", est_hours=10, assignee="backend")
    ps.create_item("Feature 2", "", item_type="feature", phase="Phase 0", est_hours=20, assignee="frontend")
    ps.create_item("Bug 1", "", item_type="bug", phase="Phase 1", priority="critical", assignee="backend")
    ps.create_item("Security issue", "", item_type="security", phase="Phase 2", priority="high", assignee="backend", security_severity="high")

    dash = ps.get_dashboard()
    assert dash["total"] == 4
    assert dash["by_type"]["feature"] == 2
    assert dash["by_type"]["bug"] == 1
    assert dash["by_type"]["security"] == 1
    assert dash["by_phase"]["Phase 0"]["total"] == 2
    assert dash["by_phase"]["Phase 1"]["total"] == 1
    assert dash["by_phase"]["Phase 2"]["total"] == 1
    assert dash["by_assignee"]["backend"] == 3
    assert dash["by_assignee"]["frontend"] == 1
    assert dash["by_priority"]["critical"] == 1
    assert dash["by_priority"]["high"] == 1
    assert dash["security_issues"] == 1
    assert dash["remaining_hours"] == 30.0  # 10 + 20
    assert dash["blockers"] == 0


def test_get_dashboard_with_blocked():
    ps.create_item("Blocked item", "", phase="Phase 0", est_hours=5)
    ps.set_status("PS-blocked-item", "blocked")
    dash = ps.get_dashboard()
    assert dash["blockers"] == 1


def test_get_dashboard_with_completed():
    ps.create_item("Done item", "", phase="Phase 0", est_hours=5)
    ps.set_status("PS-done-item", "done")
    dash = ps.get_dashboard()
    assert dash["completed"] == 1
    assert dash["by_phase"]["Phase 0"]["done"] == 1
    # Done items don't count as remaining hours
    assert dash["remaining_hours"] == 0


def test_item_stored_as_entity():
    item = ps.create_item("Entity test", "", phase="Phase 0")
    entity = ledger.get_entity("PS-entity-test")
    assert entity is not None
    assert entity.entity_type == PROGRAMMING_SCHEDULE
    assert entity.attributes["title"] == "Entity test"


def test_item_updated_persists():
    ps.create_item("Persist test", "", phase="Phase 0")
    ps.update_item("PS-persist-test", assignee="devops", progress=75)
    entity = ledger.get_entity("PS-persist-test")
    assert entity is not None
    assert entity.attributes["assignee"] == "devops"
    assert entity.attributes["progress"] == 75


def test_depends_on_stored():
    ps.create_item("Dependency A", "", phase="Phase 0")
    item = ps.create_item("Dependency B", "", phase="Phase 1", depends_on=["PS-dependency-a"])
    assert "PS-dependency-a" in item["depends_on"]
    fetched = ps.get_item("PS-dependency-b")
    assert fetched is not None
    assert "PS-dependency-a" in fetched["depends_on"]


def test_create_item_with_route_and_owner():
    item = ps.create_item("Route test", "", phase="Phase 0",
                          resource_route="vps", owner="sam")
    assert "error" not in item
    assert item["resource_route"] == "vps"
    assert item["owner"] == "sam"


def test_get_by_route():
    ps.create_item("VPS item 1", "", phase="Phase 0", resource_route="vps")
    ps.create_item("VPS item 2", "", phase="Phase 0", resource_route="vps")
    ps.create_item("Local item 1", "", phase="Phase 0", resource_route="local")
    ps.create_item("Sam item 1", "", phase="Phase 0", resource_route="sam_only")

    vps_items = ps.get_by_route("vps")
    assert len(vps_items) == 2
    assert all(i["resource_route"] == "vps" for i in vps_items)


def test_set_route():
    ps.create_item("Route change", "", phase="Phase 0")
    result = ps.set_route("PS-route-change", "vps", owner="backend")
    assert "error" not in result
    assert result["resource_route"] == "vps"
    assert result["owner"] == "backend"
    fetched = ps.get_item("PS-route-change")
    assert fetched is not None
    assert fetched["resource_route"] == "vps"


def test_set_route_invalid():
    ps.create_item("Bad route", "", phase="Phase 0")
    err = ps.set_route("PS-bad-route", "mars_base")
    assert "error" in err


def test_set_route_invalid_owner():
    ps.create_item("Bad owner", "", phase="Phase 0")
    err = ps.set_route("PS-bad-owner", "local", owner="elon")
    assert "error" in err


def test_default_route_is_local():
    item = ps.create_item("Default route", "", phase="Phase 0")
    assert item["resource_route"] == "local"
    assert item["owner"] == "auto"


def test_list_items_filter_by_route():
    ps.create_item("Filtered 1", "", phase="Phase 0", resource_route="vps")
    ps.create_item("Filtered 2", "", phase="Phase 0", resource_route="sam_only")
    ps.create_item("Filtered 3", "", phase="Phase 0", resource_route="local")
    assert len(ps.list_items(resource_route="vps")) == 1
    assert len(ps.list_items(resource_route="sam_only")) == 1
    assert len(ps.list_items(resource_route="local")) == 1
    assert len(ps.list_items(resource_route="vps", owner="sam")) == 0


def test_invalid_route_rejected():
    err = ps.create_item("Bad route item", "", phase="Phase 0", resource_route="cloud")
    assert "error" in err


def test_invalid_owner_rejected():
    err = ps.create_item("Bad owner item", "", phase="Phase 0", owner="alien")
    assert "error" in err


if __name__ == "__main__":
    # Run all tests
    import traceback
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    failed = 0
    for test in tests:
        try:
            ledger.reset()
            ledger.reset()
            test()
            passed += 1
            print(f"  {test.__name__}: PASS")
        except Exception as e:
            failed += 1
            print(f"  {test.__name__}: FAIL — {e}")
        finally:
            ledger.reset()
    print(f"\n{passed} passed, {failed} failed ({passed + failed} total)")
