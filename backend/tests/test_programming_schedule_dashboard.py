"""Tests for the enhanced programming-schedule dashboard JSON (Section 3).

Verifies:
  - Route requires ADMIN (401 / 403 / 200)
  - JSON includes all Section 3 fields: in_progress, up_next, blocked_on_sam,
    done, active_runs, resources, target_date, days_left, pct_done_by_hours
  - _build_dashboard_data() returns well-structured data
  - Route is NOT shadowed by /programming-schedule/{item_id} (returns 200, not 404)
"""
import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("NXTDEAL_AGENT_SECRET", "test-agent-secret")

from core.auth import credential_store, issue_token  # noqa: E402
from core.dealeros import ledger  # noqa: E402
from core import programming_schedule as ps  # noqa: E402
from core.dashboard_renderer import _build_dashboard_data  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_ledger():
    ledger.reset()
    _seed()
    yield
    ledger.reset()


@pytest.fixture
def client():
    from api.app import app
    credential_store.set_credential("PS-ADMIN", "pass-Word1!", "ADMIN", must_change_password=False)
    credential_store.set_credential("PS-SALES", "pass-Word1!", "SALES", must_change_password=False)
    return TestClient(app)


@pytest.fixture
def headers():
    return {
        "admin": {"Authorization": "Bearer " + issue_token("PS-ADMIN", "ADMIN", fresh_auth=True)},
        "sales": {"Authorization": "Bearer " + issue_token("PS-SALES", "SALES", fresh_auth=True)},
        "none": {},
    }


def _seed():
    """Create a small set of items across phases/routes for dashboard tests."""
    ps.create_item(
        title="Phase 0 security review", description="Review auth",
        item_type="security", phase="Phase 0", priority="critical",
        assignee="backend", est_hours=2, resource_route="local", owner="auto",
        security_severity="high",
    )
    ps.create_item(
        title="Phase 3 API routes", description="Build endpoints",
        item_type="feature", phase="Phase 3", priority="high",
        assignee="backend", est_hours=4, resource_route="vps", owner="auto",
    )
    ps.create_item(
        title="Fix billing", description="Need payment method",
        item_type="bug", phase="Phase 1", priority="critical",
        assignee="backend", est_hours=1, resource_route="sam_only", owner="sam",
    )
    ps.create_item(
        title="Add logging", description="Log all routes",
        item_type="tech-debt", phase="Phase 2", priority="low",
        assignee="backend", est_hours=1, resource_route="local", owner="auto",
    )
    # Start a run on the Phase 0 item
    item = ps.list_items(phase="Phase 0")[0]
    ps.create_run(item_id=item["id"], worker="desktop", provider="local", model="gemma3:120b")
    run = ps.get_run(ps.list_runs(item_id=item["id"])[0]["id"])
    if run is None:
        return
    ps.heartbeat_run(run["id"], input_tokens=10, output_tokens=5, cost_usd=0.0)


# ---------------------------------------------------------------------------
# Auth boundary
# ---------------------------------------------------------------------------

def test_dashboard_route_unauthenticated(client, headers):
    r = client.get("/programming-schedule/dashboard", headers=headers["none"])
    assert r.status_code == 401


def test_dashboard_route_non_admin(client, headers):
    r = client.get("/programming-schedule/dashboard", headers=headers["sales"])
    assert r.status_code == 403


def test_dashboard_route_admin_returns_200(client, headers):
    r = client.get("/programming-schedule/dashboard", headers=headers["admin"])
    assert r.status_code == 200
    assert "error" not in r.json()


def test_dashboard_route_not_shadowed_by_item_id(client, headers):
    """The 'dashboard' path must not be captured by /{item_id}."""
    r = client.get("/programming-schedule/dashboard", headers=headers["admin"])
    assert r.status_code == 200
    # If it were captured by {item_id}, we'd get 422 (not found) or a different response
    assert isinstance(r.json(), dict)
    assert "by_phase" in r.json()


# ---------------------------------------------------------------------------
# Data structure
# ---------------------------------------------------------------------------

def test_dashboard_json_has_new_fields(client, headers):
    r = client.get("/programming-schedule/dashboard", headers=headers["admin"])
    data = r.json()
    for field in ["dashboard", "by_phase", "phase_order", "route_labels",
                  "owner_labels", "route_counts", "in_progress", "up_next",
                  "blocked_on_sam", "done", "active_runs", "resources",
                  "target_date", "days_left", "pct_done_by_hours",
                  "total_est_hours", "total_logged_hours"]:
        assert field in data, f"Missing field: {field}"


def test_dashboard_target_date():
    data = _build_dashboard_data()
    assert data["target_date"] == "2026-12-01"
    assert data["days_left"] > 0
    assert isinstance(data["pct_done_by_hours"], (int, float))


def test_dashboard_in_progress_shows_running_runs():
    data = _build_dashboard_data()
    # We seeded a running run on the Phase 0 item
    assert len(data["in_progress"]) >= 1
    item = data["in_progress"][0]
    assert item["run"] is not None
    assert item["run"]["worker"] == "desktop"
    assert item["run"]["outcome"] == "running"
    assert item["claimed_by"] is not None


def test_dashboard_up_next_excludes_sam_only():
    data = _build_dashboard_data()
    assert len(data["up_next"]) >= 1
    for item in data["up_next"]:
        assert item["resource_route"] != "sam_only"


def test_dashboard_blocked_on_sam():
    data = _build_dashboard_data()
    assert len(data["blocked_on_sam"]) >= 1
    for item in data["blocked_on_sam"]:
        # Either sam_only route or blocked status
        assert item["resource_route"] == "sam_only" or item["status"] == "blocked"


def test_dashboard_by_phase_has_item_dicts():
    data = _build_dashboard_data()
    phase0 = data["by_phase"]["Phase 0"]
    assert phase0["total"] >= 1
    assert len(phase0["items"]) >= 1
    item = phase0["items"][0]
    for field in ["id", "title", "phase", "status", "priority", "est_hours",
                  "logged_hours", "resource_route", "owner", "claimed_by",
                  "claimed_at", "lease_expires_at", "run", "event_count"]:
        assert field in item, f"Item missing field: {field}"


def test_dashboard_resources_structure():
    data = _build_dashboard_data()
    res = data["resources"]
    assert "workers" in res
    assert "models" in res
    assert "mtd_total_cost" in res
    assert "mtd_total_tokens" in res
    # The seed run uses local/free model
    if "desktop" in res["workers"]:
        w = res["workers"]["desktop"]
        assert w["runs"] >= 1
        assert w["cost_usd"] == 0.0  # local model = free


def test_dashboard_active_runs():
    data = _build_dashboard_data()
    assert len(data["active_runs"]) >= 1
    run = data["active_runs"][0]
    for field in ["id", "item_id", "worker", "provider", "model", "outcome",
                  "started_at", "input_tokens", "output_tokens", "cost_usd"]:
        assert field in run, f"Run missing field: {field}"


def test_dashboard_done_is_list():
    data = _build_dashboard_data()
    assert isinstance(data["done"], list)


def test_dashboard_phase_order():
    data = _build_dashboard_data()
    assert data["phase_order"] == list(ps.PHASES)
