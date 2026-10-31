"""Tests for Section 2: Machine endpoints (claim, heartbeat, complete).

Covers worker token auth, claim atomicity, dependency gating, lease management,
free-model gate, and that machine endpoints are NOT accessible with admin sessions.
"""
import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("NXTDEAL_GITHUB_WEBHOOK_SECRET", "test-gh-secret")
os.environ.setdefault("NXTDEAL_COOLIFY_WEBHOOK_SECRET", "test-coolify-secret")
os.environ.setdefault("NXTDEAL_AGENT_SECRET", "test-agent-secret")

from core.auth import credential_store, issue_token  # noqa: E402
from core.dealeros import ledger  # noqa: E402
from core import programming_schedule as ps  # noqa: E402
from core.schedule_auth import generate_worker_token  # noqa: E402
from core.storage_paths import GRAPH_PATH  # noqa: E402

# Generate worker tokens at module level (conftest has already set
# DEALEROS_STORAGE_DIR, so tokens are written to the isolated temp dir).
DESKTOP_TOKEN = generate_worker_token("desktop")
MAC_TOKEN = generate_worker_token("mac")
VPS_TOKEN = generate_worker_token("vps")


@pytest.fixture(autouse=True)
def _reset_ledger():
    if os.path.exists(GRAPH_PATH):
        os.remove(GRAPH_PATH)
    ledger.reset()
    yield
    if os.path.exists(GRAPH_PATH):
        os.remove(GRAPH_PATH)
    ledger.reset()


@pytest.fixture
def client():
    from api.app import app
    credential_store.set_credential("PS-ADMIN", "pass-Word1!", "ADMIN",
                                    must_change_password=False)
    credential_store.set_credential("PS-SALES", "pass-Word1!", "SALES",
                                    must_change_password=False)
    return TestClient(app)


@pytest.fixture
def admin_headers():
    return {"Authorization": "Bearer " + issue_token("PS-ADMIN", "ADMIN", fresh_auth=True)}


@pytest.fixture
def sales_headers():
    return {"Authorization": "Bearer " + issue_token("PS-SALES", "SALES", fresh_auth=True)}


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Worker token auth
# ---------------------------------------------------------------------------

class TestWorkerTokenAuth:
    def test_claim_without_token(self, client):
        ps.create_item("Test item", "", resource_route="local")
        resp = client.post("/programming-schedule/claim",
                           json={"worker": "desktop", "route": "local"})
        body = resp.json()
        assert "error" in body
        assert "token" in body["error"].lower()

    def test_claim_invalid_token(self, client):
        ps.create_item("Test item", "", resource_route="local")
        resp = client.post("/programming-schedule/claim",
                           json={"worker": "desktop", "route": "local"},
                           headers=_auth("invalid-token"))
        body = resp.json()
        assert "error" in body

    def test_heartbeat_without_token(self, client):
        resp = client.post("/programming-schedule/runs/SR-test/heartbeat", json={})
        body = resp.json()
        assert "error" in body

    def test_complete_without_token(self, client):
        resp = client.post("/programming-schedule/runs/SR-test/complete",
                           json={"outcome": "completed"})
        body = resp.json()
        assert "error" in body


# ---------------------------------------------------------------------------
# Claim endpoint
# ---------------------------------------------------------------------------

class TestClaimEndpoint:
    def test_claim_returns_item_and_run_id(self, client):
        ps.create_item("Claim test", "", resource_route="local")
        resp = client.post("/programming-schedule/claim",
                           json={"worker": "desktop", "route": "local"},
                           headers=_auth(DESKTOP_TOKEN))
        body = resp.json()
        assert "run_id" in body
        assert body["claimed_by"] == "desktop"
        assert body["status"] == "in_progress"
        assert body["lease_expires_at"] is not None

    def test_claim_no_eligible_items(self, client):
        ps.create_item("Sam item", "", resource_route="sam_only", owner="sam")
        resp = client.post("/programming-schedule/claim",
                           json={"worker": "desktop", "route": "local"},
                           headers=_auth(DESKTOP_TOKEN))
        body = resp.json()
        assert "error" in body

    def test_claim_route_mismatch(self, client):
        ps.create_item("VPS item", "", resource_route="vps")
        resp = client.post("/programming-schedule/claim",
                           json={"worker": "desktop", "route": "local"},
                           headers=_auth(DESKTOP_TOKEN))
        body = resp.json()
        assert "error" in body

    def test_claim_dependency_gating(self, client):
        ps.create_item("Dep A", "", resource_route="local")
        ps.create_item("Dep B", "", resource_route="local", depends_on=["PS-dep-a"])
        resp = client.post("/programming-schedule/claim",
                           json={"worker": "desktop", "route": "local"},
                           headers=_auth(DESKTOP_TOKEN))
        body = resp.json()
        assert "run_id" in body
        assert body["id"] == "PS-dep-a"

    def test_claim_priority_ordering(self, client):
        ps.create_item("Low item", "", phase="Phase 0", priority="low",
                       resource_route="local", est_hours=5)
        ps.create_item("High item", "", phase="Phase 0", priority="high",
                       resource_route="local", est_hours=5)
        ps.create_item("Critical item", "", phase="Phase 0", priority="critical",
                       resource_route="local", est_hours=3)
        resp = client.post("/programming-schedule/claim",
                           json={"worker": "desktop", "route": "local"},
                           headers=_auth(DESKTOP_TOKEN))
        body = resp.json()
        assert "run_id" in body
        assert body["title"] == "Critical item"

    def test_claim_phase_ordering(self, client):
        ps.create_item("Phase 1 item", "", phase="Phase 1", resource_route="local")
        ps.create_item("Phase 0 item", "", phase="Phase 0", resource_route="local")
        resp = client.post("/programming-schedule/claim",
                           json={"worker": "desktop", "route": "local"},
                           headers=_auth(DESKTOP_TOKEN))
        body = resp.json()
        assert "run_id" in body
        assert body["phase"] == "Phase 0"

    def test_claim_skips_already_claimed(self, client):
        ps.create_item("Item A", "", resource_route="local")
        ps.create_item("Item B", "", resource_route="local")
        r1 = client.post("/programming-schedule/claim",
                         json={"worker": "desktop", "route": "local"},
                         headers=_auth(DESKTOP_TOKEN)).json()
        r2 = client.post("/programming-schedule/claim",
                         json={"worker": "desktop", "route": "local"},
                         headers=_auth(DESKTOP_TOKEN)).json()
        assert "run_id" in r1
        assert "run_id" in r2
        assert r1["id"] != r2["id"]

    def test_claim_invalid_route(self, client):
        resp = client.post("/programming-schedule/claim",
                           json={"worker": "desktop", "route": "mars_base"},
                           headers=_auth(DESKTOP_TOKEN))
        body = resp.json()
        assert "error" in body

    def test_claim_token_determines_worker(self, client):
        """Worker is identified by the token, not the request body."""
        ps.create_item("Mismatch test", "", resource_route="local")
        resp = client.post("/programming-schedule/claim",
                           json={"worker": "mac", "route": "local"},
                           headers=_auth(DESKTOP_TOKEN))
        body = resp.json()
        assert body.get("claimed_by") == "desktop"


# ---------------------------------------------------------------------------
# Heartbeat endpoint
# ---------------------------------------------------------------------------

class TestHeartbeatEndpoint:
    def _claim(self, client):
        ps.create_item("Heartbeat test", "", resource_route="local")
        resp = client.post("/programming-schedule/claim",
                           json={"worker": "desktop", "route": "local"},
                           headers=_auth(DESKTOP_TOKEN))
        return resp.json()

    def test_heartbeat_returns_updated_run(self, client):
        run_id = self._claim(client)["run_id"]
        resp = client.post(f"/programming-schedule/runs/{run_id}/heartbeat",
                           json={"input_tokens": 100, "output_tokens": 50,
                                 "cost_usd": 0.001},
                           headers=_auth(DESKTOP_TOKEN))
        body = resp.json()
        assert body["input_tokens"] == 100
        assert body["output_tokens"] == 50
        assert body["cost_usd"] == 0.001

    def test_heartbeat_wrong_worker_token(self, client):
        claim = self._claim(client)
        run_id = claim["run_id"]
        resp = client.post(f"/programming-schedule/runs/{run_id}/heartbeat",
                           json={}, headers=_auth(MAC_TOKEN))
        body = resp.json()
        assert "error" in body

    def test_heartbeat_nonexistent_run(self, client):
        resp = client.post("/programming-schedule/runs/SR-noexist/heartbeat",
                           json={}, headers=_auth(DESKTOP_TOKEN))
        body = resp.json()
        assert "error" in body
        assert "not found" in body["error"]


# ---------------------------------------------------------------------------
# Complete endpoint
# ---------------------------------------------------------------------------

class TestCompleteEndpoint:
    def _claim(self, client):
        ps.create_item("Complete test", "", resource_route="local")
        resp = client.post("/programming-schedule/claim",
                           json={"worker": "desktop", "route": "local"},
                           headers=_auth(DESKTOP_TOKEN))
        return resp.json()

    def test_complete_marks_done(self, client):
        claim = self._claim(client)
        run_id = claim["run_id"]
        resp = client.post(f"/programming-schedule/runs/{run_id}/complete",
                           json={"outcome": "completed", "commit_sha": "abc123",
                                 "tests_summary": "5 passed"},
                           headers=_auth(DESKTOP_TOKEN))
        body = resp.json()
        assert body["outcome"] == "completed"
        assert body["commit_sha"] == "abc123"
        item = ps.get_item(claim["id"])
        assert item["claimed_by"] is None
        assert item["lease_expires_at"] is None

    def test_complete_with_progress(self, client):
        claim = self._claim(client)
        run_id = claim["run_id"]
        resp = client.post(f"/programming-schedule/runs/{run_id}/complete",
                           json={"outcome": "partial", "progress": 50},
                           headers=_auth(DESKTOP_TOKEN))
        body = resp.json()
        assert body["outcome"] == "partial"
        item = ps.get_item(claim["id"])
        assert item["progress"] == 50

    def test_complete_wrong_worker_token(self, client):
        claim = self._claim(client)
        run_id = claim["run_id"]
        resp = client.post(f"/programming-schedule/runs/{run_id}/complete",
                           json={"outcome": "completed"}, headers=_auth(MAC_TOKEN))
        body = resp.json()
        assert "error" in body

    def test_complete_invalid_outcome(self, client):
        claim = self._claim(client)
        run_id = claim["run_id"]
        resp = client.post(f"/programming-schedule/runs/{run_id}/complete",
                           json={"outcome": "invalid"}, headers=_auth(DESKTOP_TOKEN))
        body = resp.json()
        assert "error" in body

    def test_complete_non_free_model_recorded(self, client):
        claim = self._claim(client)
        run_id = claim["run_id"]
        resp = client.post(f"/programming-schedule/runs/{run_id}/complete",
                           json={"outcome": "completed", "model": "openai/gpt-4"},
                           headers=_auth(DESKTOP_TOKEN))
        body = resp.json()
        assert body["outcome"] == "completed"
        events = ps.get_events(claim["id"])
        warnings = [e for e in events if "non-free" in e.get("evidence", "")]
        assert len(warnings) >= 1

    def test_complete_free_model_no_warning(self, client):
        claim = self._claim(client)
        run_id = claim["run_id"]
        resp = client.post(f"/programming-schedule/runs/{run_id}/complete",
                           json={"outcome": "completed",
                                 "model": "poolside/laguna-s-2.1:free"},
                           headers=_auth(DESKTOP_TOKEN))
        body = resp.json()
        assert body["outcome"] == "completed"
        events = ps.get_events(claim["id"])
        warnings = [e for e in events if "non-free" in e.get("evidence", "")]
        assert len(warnings) == 0


# ---------------------------------------------------------------------------
# Run queries
# ---------------------------------------------------------------------------

class TestRunQueries:
    def test_active_runs_empty(self, client):
        resp = client.get("/programming-schedule/runs/active",
                          headers=_auth(DESKTOP_TOKEN))
        body = resp.json()
        assert body == []

    def test_active_runs_shows_running(self, client):
        ps.create_item("Run test", "", resource_route="local")
        claim = client.post("/programming-schedule/claim",
                            json={"worker": "desktop", "route": "local"},
                            headers=_auth(DESKTOP_TOKEN)).json()
        resp = client.get("/programming-schedule/runs/active",
                          headers=_auth(DESKTOP_TOKEN))
        body = resp.json()
        assert len(body) == 1
        assert body[0]["id"] == claim["run_id"]

    def test_get_run_by_id(self, client):
        ps.create_item("Get run test", "", resource_route="local")
        claim = client.post("/programming-schedule/claim",
                            json={"worker": "desktop", "route": "local"},
                            headers=_auth(DESKTOP_TOKEN)).json()
        resp = client.get(f"/programming-schedule/runs/{claim['run_id']}",
                          headers=_auth(DESKTOP_TOKEN))
        body = resp.json()
        assert body["id"] == claim["run_id"]
        assert body["worker"] == "desktop"

    def test_get_run_nonexistent(self, client):
        resp = client.get("/programming-schedule/runs/SR-noexist",
                          headers=_auth(DESKTOP_TOKEN))
        body = resp.json()
        assert "error" in body


# ---------------------------------------------------------------------------
# Route shadowing — machine routes before /{item_id}
# ---------------------------------------------------------------------------

class TestRouteShadowing:
    def test_claim_not_shadowed(self, client):
        ps.create_item("Item one", "", resource_route="local")
        resp = client.post("/programming-schedule/claim",
                           json={"worker": "desktop", "route": "local"},
                           headers=_auth(DESKTOP_TOKEN))
        body = resp.json()
        assert "run_id" in body, f"Route shadowed: {body}"

    def test_heartbeat_not_shadowed(self, client):
        ps.create_item("Shadow test", "", resource_route="local")
        claim = client.post("/programming-schedule/claim",
                            json={"worker": "desktop", "route": "local"},
                            headers=_auth(DESKTOP_TOKEN)).json()
        resp = client.post(f"/programming-schedule/runs/{claim['run_id']}/heartbeat",
                           json={"input_tokens": 10},
                           headers=_auth(DESKTOP_TOKEN))
        body = resp.json()
        assert body["input_tokens"] == 10, f"Route shadowed: {body}"

    def test_active_runs_not_shadowed(self, client):
        resp = client.get("/programming-schedule/runs/active",
                          headers=_auth(DESKTOP_TOKEN))
        body = resp.json()
        assert body == []

    def test_get_run_not_shadowed(self, client):
        ps.create_item("Get run", "", resource_route="local")
        claim = client.post("/programming-schedule/claim",
                            json={"worker": "desktop", "route": "local"},
                            headers=_auth(DESKTOP_TOKEN)).json()
        resp = client.get(f"/programming-schedule/runs/{claim['run_id']}",
                          headers=_auth(DESKTOP_TOKEN))
        body = resp.json()
        assert "id" in body


# ---------------------------------------------------------------------------
# Auth separation — admin sessions vs worker tokens
# ---------------------------------------------------------------------------

class TestAuthSeparation:
    def test_machine_endpoint_rejects_admin_token(self, client, admin_headers):
        ps.create_item("Admin test", "", resource_route="local")
        resp = client.post("/programming-schedule/claim",
                           json={"worker": "desktop", "route": "local"},
                           headers=admin_headers)
        body = resp.json()
        assert "error" in body, "Admin token should not work for machine endpoints"

    def test_worker_token_rejected_on_admin_route(self, client):
        ps.create_item("Admin route test", "", resource_route="local")
        resp = client.get("/programming-schedule",
                          headers=_auth(DESKTOP_TOKEN))
        body = resp.json()
        assert "error" in body, "Worker token should not work for admin routes"

    def test_worker_token_rejected_on_dashboard_view(self, client):
        resp = client.get("/programming-schedule/dashboard-view",
                          headers=_auth(DESKTOP_TOKEN))
        body = resp.json()
        assert "error" in body


# ---------------------------------------------------------------------------
# Review #2: Mac model naming — local-mac provider/model must be free
# ---------------------------------------------------------------------------

class TestMacModelNaming:
    def test_mac_model_local_mac_prefix_is_free(self, client):
        """Mac Studio reports model='local-mac/qwen3.6-35b', provider='local-mac'.
        _is_free_model must return True so runs are not flagged as paid."""
        from api.app import _is_free_model
        assert _is_free_model("local-mac/qwen3.6-35b", "local-mac") is True
        assert _is_free_model("local-mac/qwen3.6-35b") is True
        assert _is_free_model("qwen3.6-35b", "local-mac") is True

    def test_mac_model_without_prefix_is_not_free(self):
        """If the Mac doesn't prefix its model, it IS flagged as paid (safety)."""
        from api.app import _is_free_model
        assert _is_free_model("qwen3.6-35b") is False
        assert _is_free_model("gpt-4") is False

    def test_complete_mac_run_no_warning(self, client):
        """Completing a run with Mac's local model should NOT trigger a non-free warning."""
        ps.create_item("Mac item", "", resource_route="local")
        claim = client.post("/programming-schedule/claim",
                            json={"worker": "vps", "route": "local"},
                            headers=_auth(VPS_TOKEN)).json()
        run_id = claim["run_id"]
        resp = client.post(f"/programming-schedule/runs/{run_id}/complete",
                           json={"outcome": "completed", "provider": "local-mac",
                                 "model": "local-mac/qwen3.6-35b"},
                           headers=_auth(VPS_TOKEN))
        body = resp.json()
        assert body["outcome"] == "completed"
        events = ps.get_events(claim["id"])
        warnings = [e for e in events if "non-free" in str(e)]
        assert len(warnings) == 0
