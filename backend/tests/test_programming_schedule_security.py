"""Security tests for /programming-schedule/* routes (Section 0).

Verifies that every human-facing programming-schedule route requires an
ADMIN session:
  - logged-out (no Authorization header)      → 401
  - authenticated but non-admin (e.g. SALES) → 403
  - authenticated admin                       → 200 (valid JSON, no error)

Machine-only routes (webhooks, agent-channel) are NOT tested here — they use
HMAC / shared-secret tokens, not user sessions.
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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_ledger():
    ledger.reset()
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


# ---------------------------------------------------------------------------
# Route inventory — every human-facing PS route that must be ADMIN-only.
# Each entry: (method, path, min_valid_body_or_None)
# ---------------------------------------------------------------------------

PS_ROUTES = [
    ("GET",   "/programming-schedule",                                         None),
    ("GET",   "/programming-schedule/dashboard",                               None),
    ("GET",   "/programming-schedule/dashboard-view",                          None),
    ("POST",  "/programming-schedule",                                         {"title": "x"}),
    ("GET",   "/programming-schedule/route/local",                             None),
    ("GET",   "/programming-schedule/ci-runs",                                 None),
    ("GET",   "/programming-schedule/deployment-runs",                         None),
    ("GET",   "/programming-schedule/deployment/deploy-1/status",              None),
    ("GET",   "/programming-schedule/PS-seed-item/production-health",          None),
    ("POST",  "/programming-schedule/PS-seed-item/mark-pushed-live",           None),
    ("GET",   "/programming-schedule/PS-seed-item",                            None),
    ("PATCH", "/programming-schedule/PS-seed-item",                            {"title": "x"}),
    ("POST",  "/programming-schedule/PS-seed-item/progress",                   {"progress": 50}),
    ("POST",  "/programming-schedule/PS-seed-item/assign",                     {"assignee": "backend"}),
    ("POST",  "/programming-schedule/PS-seed-item/status",                     {"status": "in_progress"}),
    ("POST",  "/programming-schedule/PS-seed-item/hours",                      {"hours": 1}),
    ("POST",  "/programming-schedule/PS-seed-item/notes",                      {"note": "note"}),
    ("POST",  "/programming-schedule/PS-seed-item/resources",                  {"resource": "file.txt"}),
    ("POST",  "/programming-schedule/PS-seed-item/route",                       {"resource_route": "vps"}),
]


# ---------------------------------------------------------------------------
# Parametrised: every route must deny logged-out and non-admin
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("method,path,body", PS_ROUTES)
def test_ps_route_requires_auth(client, headers, method, path, body):
    """Logged-out → 401."""
    r = client.request(method, path, headers=headers["none"], json=body)
    assert r.status_code == 401
    assert "error" in r.json()


@pytest.mark.parametrize("method,path,body", PS_ROUTES)
def test_ps_route_requires_admin_role(client, headers, method, path, body):
    """Non-admin → 403."""
    r = client.request(method, path, headers=headers["sales"], json=body)
    assert r.status_code == 403
    assert "error" in r.json()


# ---------------------------------------------------------------------------
# Admin can reach the dashboard-view (the original security blocker)
# ---------------------------------------------------------------------------

def test_admin_can_view_dashboard(client, headers):
    """Admin → 200 on dashboard-view, returns HTML."""
    ps.create_item("Seed item", "for route test", phase="Phase 0")
    r = client.get("/programming-schedule/dashboard-view", headers=headers["admin"])
    assert r.status_code == 200
    assert r.headers["content-type"] == "text/html; charset=utf-8"
    body = r.text
    assert "<html" in body.lower()
    assert "programming" in body.lower()


def test_logged_out_dashboard_view_401(client, headers):
    """The original blocker: GET /programming-schedule/dashboard-view with no auth → 401."""
    r = client.get("/programming-schedule/dashboard-view", headers=headers["none"])
    assert r.status_code == 401
    assert "error" in r.json()


def test_non_admin_dashboard_view_403(client, headers):
    """The original blocker: GET /programming-schedule/dashboard-view with SALES → 403."""
    r = client.get("/programming-schedule/dashboard-view", headers=headers["sales"])
    assert r.status_code == 403
    assert "error" in r.json()


# ---------------------------------------------------------------------------
# Admin can use a representative subset of API routes
# ---------------------------------------------------------------------------

def test_admin_list_items(client, headers):
    ps.create_item("Admin list item", "", phase="Phase 0")
    r = client.get("/programming-schedule", headers=headers["admin"])
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)


def test_admin_get_dashboard_json(client, headers):
    ps.create_item("Admin dash item", "", phase="Phase 0", est_hours=5)
    r = client.get("/programming-schedule/dashboard", headers=headers["admin"])
    assert r.status_code == 200
    data = r.json()
    assert data["dashboard"]["total"] >= 1


def test_admin_create_item(client, headers):
    r = client.post("/programming-schedule", headers=headers["admin"],
                    json={"title": "New PS item", "description": "created via API"})
    assert r.status_code == 200
    data = r.json()
    assert "error" not in data
    assert data["id"] == "PS-new-ps-item"


def test_admin_get_single_item(client, headers):
    ps.create_item("Get single", "", phase="Phase 0")
    r = client.get("/programming-schedule/PS-get-single", headers=headers["admin"])
    assert r.status_code == 200
    assert r.json()["title"] == "Get single"


def test_admin_ci_runs(client, headers):
    r = client.get("/programming-schedule/ci-runs", headers=headers["admin"])
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_admin_deployment_runs(client, headers):
    r = client.get("/programming-schedule/deployment-runs", headers=headers["admin"])
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_item_not_found_returns_admin_auth(client, headers):
    """Even for a non-existent item, admin auth is still required (403 before 404)."""
    r = client.get("/programming-schedule/PS-does-not-exist", headers=headers["sales"])
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Invalid / expired token → 401
# ---------------------------------------------------------------------------

def test_invalid_token_401(client):
    r = client.get("/programming-schedule", headers={"Authorization": "Bearer fake-token"})
    assert r.status_code == 401
    assert "error" in r.json()


if __name__ == "__main__":
    import traceback
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    failed = 0
    for test in tests:
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
