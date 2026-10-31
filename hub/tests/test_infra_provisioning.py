"""
Tests for dealer infrastructure auto-provisioning (hub_core/coolify.py +
hub_core/infra_provisioning.py) — 2026-07-24. Run from hub/ with `pytest`.

The Coolify HTTP layer (coolify._request) is mocked, so these verify the ORCHESTRATION: that
provisioning creates a dealer-api + dealer-frontend app, sets the right env (NEXT_PUBLIC_API_URL
build-time), deploys both, records api_base_url on the dealer, tracks status, and refuses cleanly
when Coolify isn't configured.
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_HUB_DIR = os.path.dirname(_HERE)
if _HUB_DIR not in sys.path:
    sys.path.insert(0, _HUB_DIR)

import pytest

from hub_core.dealer import Dealer
from hub_core.dealer_registry import registry
from hub_core import coolify
from hub_core import infra_provisioning as prov
from hub_core import infra_provisioning_storage as store


def _dealer(dealer_id="DLR-00007", slug="dealer7"):
    return Dealer.from_dict({
        "dealer_id": dealer_id, "slug": slug, "name": f"Dealer {dealer_id}",
        "contact_name": None, "contact_email": "a@b.com", "contact_phone": None,
        "address": None, "city": None, "state": None, "plan_tier": "Standard",
        "status": "active", "storage_dir": f"storage/tenants/{dealer_id}",
        "network_opt_in": True, "api_base_url": None, "created_by": "test",
        "created_at": "2026-01-01T00:00:00+00:00",
    })


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    registry.reset()
    store.reset()
    monkeypatch.delenv("COOLIFY_DOMAIN_BASE", raising=False)
    # Point every write at a throwaway dir.
    monkeypatch.setattr(prov, "DEALERS_PATH", str(tmp_path / "dealers.json"))
    monkeypatch.setattr(prov, "PROVISIONING_PATH", str(tmp_path / "provisioning.json"))
    # Configure Coolify + the shared network key.
    for k, v in {
        "COOLIFY_API_URL": "https://coolify.test",
        "COOLIFY_API_TOKEN": "tok",
        "COOLIFY_PROJECT_UUID": "proj",
        "COOLIFY_SERVER_UUID": "srv",
        "COOLIFY_GITHUB_APP_UUID": "gh",
        "DEALEROS_NETWORK_KEY": "netkey",
    }.items():
        monkeypatch.setenv(k, v)
    yield
    registry.reset()
    store.reset()


def _mock_coolify(monkeypatch):
    """Replace coolify._request with a recorder that returns success for every call."""
    calls = []

    def fake_request(method, path, body=None):
        calls.append({"method": method, "path": path, "body": body})
        if path == "/applications/private-github-app":
            return {"uuid": f"uuid-{body['name']}"}, None
        if path.startswith("/deploy"):
            return {"deployments": [{"uuid": "dep-1"}]}, None
        if method == "GET" and path.startswith("/applications/"):
            return {"status": "running:healthy"}, None
        return {}, None

    monkeypatch.setattr(coolify, "_request", fake_request)
    return calls


def test_provision_creates_both_apps_sets_build_env_deploys_and_records_url(monkeypatch):
    calls = _mock_coolify(monkeypatch)
    registry.add(_dealer())

    result = prov.provision_dealer("DLR-00007")
    assert "error" not in result
    assert result["status"] == "deploying"
    assert result["api"]["url"] == "https://dealer7-api.nxtdeal.app"
    assert result["frontend"]["url"] == "https://dealer7.nxtdeal.app"

    # Two apps created.
    creates = [c for c in calls if c["path"] == "/applications/private-github-app"]
    assert {c["body"]["name"] for c in creates} == {"dealer7-api", "dealer7-frontend"}
    api_create = next(c for c in creates if c["body"]["name"] == "dealer7-api")
    assert api_create["body"]["base_directory"] == "/backend"
    assert api_create["body"]["ports_exposes"] == "8000"
    assert "uvicorn" in api_create["body"]["custom_start_command"]

    # NEXT_PUBLIC_API_URL set as a BUILD-TIME var on the frontend.
    env_calls = [c for c in calls if c["path"].endswith("/envs")]
    npub = [c for c in env_calls if c["body"]["key"] == "NEXT_PUBLIC_API_URL"]
    assert npub and npub[0]["body"]["is_build_time"] is True
    assert npub[0]["body"]["value"] == "https://dealer7-api.nxtdeal.app"
    # Shared network key handed to the dealer-api.
    assert any(c["body"]["key"] == "DEALEROS_NETWORK_KEY" and c["body"]["value"] == "netkey" for c in env_calls)

    # Both apps deployed.
    assert len([c for c in calls if c["path"].startswith("/deploy")]) == 2

    # api_base_url recorded on the dealer (what apps.nxtdeal.app resolves).
    assert registry.get("DLR-00007").api_base_url == "https://dealer7-api.nxtdeal.app"

    # Status persisted.
    assert store.get("DLR-00007")["status"] == "deploying"


def test_provision_refuses_when_coolify_not_configured(monkeypatch):
    monkeypatch.delenv("COOLIFY_API_TOKEN", raising=False)
    calls = _mock_coolify(monkeypatch)
    registry.add(_dealer())
    result = prov.provision_dealer("DLR-00007")
    assert "error" in result
    assert "Missing env: token" in result["error"]
    assert calls == []
    assert store.get("DLR-00007") is None


def test_provision_unknown_dealer(monkeypatch):
    _mock_coolify(monkeypatch)
    assert "error" in prov.provision_dealer("DLR-99999")


def test_failure_midway_is_recorded_and_stops(monkeypatch):
    calls = []

    def fake_request(method, path, body=None):
        calls.append(path)
        if path == "/applications/private-github-app" and body["name"].endswith("-frontend"):
            return None, "Coolify 422: name taken"
        if path == "/applications/private-github-app":
            return {"uuid": f"uuid-{body['name']}"}, None
        return {}, None

    monkeypatch.setattr(coolify, "_request", fake_request)
    registry.add(_dealer())
    result = prov.provision_dealer("DLR-00007")
    assert result["status"] == "failed"
    assert "frontend" in result["error"]
    assert store.get("DLR-00007")["status"] == "failed"
    # api_base_url NOT recorded on a failed run.
    assert registry.get("DLR-00007").api_base_url is None


def test_get_status_and_config(monkeypatch):
    _mock_coolify(monkeypatch)
    registry.add(_dealer())
    prov.provision_dealer("DLR-00007")
    status = prov.get_status("DLR-00007", live=True)
    assert status["status"] == "deploying"
    assert status["live"]["api"] == "running:healthy"
    assert prov.provisioning_config()["configured"] is True
    assert prov.get_status("DLR-99999")["status"] == "none"
