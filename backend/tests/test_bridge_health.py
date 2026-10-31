"""Health probes cannot grant access, leak vendor diagnostics or outrun leases."""
from copy import deepcopy
from datetime import timedelta
from threading import Thread

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers.dealer_bridge import router, admin
from core import dealer_bridge as bridge, bridge_health as health, bridge_runtime as runtime
from core.bridge_sync import ConnectorFailure
from core.dealeros import ledger
from tests.test_bridge_sync import A, B, API, configured, isolated  # noqa: F401


def source():
    system, mapping, state, adapter = configured(False)
    adapter.capabilities = frozenset({"sync", "health"})
    adapter.health = lambda: {"status": "ready", "secret": "must-not-be-stored"}
    runtime.bind(system, adapter, revision="health-v1", objects=["customers"])
    return system, adapter


def test_health_is_sanitized_diagnostic_evidence_only():
    system, adapter = source()
    before = deepcopy(bridge.system_map(A))
    result = health.check(API, system)
    assert result["status"] == "ready" and result["stored"]
    after = bridge.system_map(A)
    assert before["sync_states"] == after["sync_states"]
    assert before["mappings"] == after["mappings"] and before["jobs"] == after["jobs"]
    assert after["writeback"] == "disabled" and adapter.calls == []
    assert after["systems"][0]["connector_health"]["current_binding"]
    assert "must-not-be-stored" not in str(ledger.entities)
    assert "health_probe" not in str(after)


@pytest.mark.parametrize("payload", [None, [], "ready", {"status": []}, {"status": "secret-private-value"}])
def test_malformed_health_payload_becomes_safe_unavailable(payload):
    system, adapter = source()
    adapter.health = lambda: payload
    result = health.check(A, system)
    assert result["status"] == "unavailable" and result["code"] == "invalid_health_response"
    assert "private" not in str(result)


@pytest.mark.parametrize("error, expected", [(TimeoutError("private-secret"), "unavailable"),
                                             (ConnectorFailure(code="authentication_required"), "authentication_required")])
def test_adapter_errors_have_no_raw_text(error, expected):
    system, adapter = source()
    def fail():
        raise error
    adapter.health = fail
    assert health.check(A, system)["status"] == expected
    assert "private-secret" not in str(ledger.entities)


@pytest.mark.parametrize("action", ["pause", "unbind", "rebind"])
def test_inflight_result_discarded_after_configuration_changes(action):
    system, adapter = source()
    def probe():
        if action == "pause":
            bridge.set_system_paused(B, system, True, "Investigate source configuration")
        elif action == "unbind":
            runtime.unbind(system)
        else:
            runtime.bind(system, adapter, revision="health-v2", objects=["customers"])
        return {"status": "ready"}
    adapter.health = probe
    assert health.check(A, system) == {"status": "discarded", "stored": False}
    assert "connector_health" not in ledger.get_entity(system).attributes
    assert "health_probe" not in ledger.get_entity(system).attributes


def test_no_probe_for_missing_authority_pause_demo_or_capability(monkeypatch):
    system, adapter = source()
    calls = []
    adapter.health = lambda: calls.append(True)
    for actor in [{**A, "role": "SALES"}, {**A, "workspace_id": "foreign"}]:
        with pytest.raises(PermissionError): health.check(actor, system)
    monkeypatch.setenv("DEALEROS_DEMO", "true")
    with pytest.raises(ValueError, match="demo mode"): health.check(A, system)
    monkeypatch.delenv("DEALEROS_DEMO")
    bridge.set_system_paused(B, system, True, "Pause source pending investigation")
    with pytest.raises(ValueError, match="paused"): health.check(A, system)
    assert calls == []
    bridge.set_system_paused(B, system, False, "Resume source after investigation")
    adapter.capabilities = frozenset({"sync"})
    runtime.bind(system, adapter, revision="health-v2", objects=["customers"])
    with pytest.raises(ValueError, match="not available"): health.check(A, system)
    assert calls == []


def test_probe_does_not_hold_graph_or_persistence_lock():
    system, adapter = source()
    acquired = []
    def probe():
        def reader():
            with bridge.LOCK, ledger.persistence_guard():
                acquired.append(True)
        thread = Thread(target=reader, daemon=True)
        thread.start(); thread.join(timeout=2)
        assert acquired == [True]
        # A duplicate call sees the lease and never calls the adapter recursively.
        assert health.check(B, system) == {"status": "checking", "stored": False}
        return {"status": "ready"}
    adapter.health = probe
    assert health.check(A, system)["status"] == "ready"


def test_expired_lease_discards_late_result_and_next_probe_can_recover(monkeypatch):
    system, adapter = source()
    current = health.utcnow()
    monkeypatch.setattr(health, "utcnow", lambda: current)
    def slow():
        nonlocal current
        current += timedelta(seconds=health.LEASE_SECONDS + 1)
        return {"status": "ready"}
    adapter.health = slow
    assert health.check(A, system)["status"] == "discarded"
    adapter.health = lambda: {"status": "degraded"}
    assert health.check(A, system)["status"] == "degraded"


def test_binding_change_marks_prior_result_as_previous_configuration():
    system, adapter = source()
    health.check(A, system)
    runtime.bind(system, adapter, revision="health-v2", objects=["customers"])
    assert not bridge.system_map(A)["systems"][0]["connector_health"]["current_binding"]
    runtime.unbind(system)
    assert not bridge.system_map(A)["systems"][0]["connector_health"]["current_binding"]


def test_health_route_rejects_credentials_or_urls():
    system, _ = source()
    app = FastAPI(); app.include_router(router)
    app.dependency_overrides[admin] = lambda: API
    client = TestClient(app)
    path = f"/dealer-bridge/systems/{system}/health-check"
    assert client.post(path, json={}).status_code == 200
    assert client.post(path, json={"credentials": "secret"}).status_code == 422
    assert client.post(path, json={"url": "https://example.invalid"}).status_code == 422


def test_failed_claim_save_never_calls_adapter(monkeypatch):
    system, adapter = source()
    calls = []
    adapter.health = lambda: calls.append(True)
    def fail(_):
        raise OSError("Synthetic disk failure")
    monkeypatch.setattr(bridge, "save_graph", fail)
    with pytest.raises(OSError): health.check(A, system)
    assert calls == []
    assert "health_probe" not in ledger.get_entity(system).attributes


def test_newer_probe_wins_over_expired_response(monkeypatch):
    system, adapter = source()
    current = health.utcnow()
    monkeypatch.setattr(health, "utcnow", lambda: current)
    def first_probe():
        nonlocal current
        current += timedelta(seconds=health.LEASE_SECONDS + 1)
        adapter.health = lambda: {"status": "degraded"}
        assert health.check(B, system)["status"] == "degraded"
        return {"status": "ready"}
    adapter.health = first_probe
    assert health.check(A, system)["status"] == "discarded"
    assert ledger.get_entity(system).attributes["connector_health"]["status"] == "degraded"


@pytest.mark.parametrize("status", ["authentication_required", "permission_denied", "source_changed", "rate_limited", "unavailable", "degraded"])
def test_current_health_failure_guides_operator_without_mutation_or_io(status):
    from core import bridge_sync as sync
    system, adapter = source()
    mapping = next(row for row in bridge.system_map(A)["mappings"] if row["system_id"] == system)
    sync.configure(A, mapping["id"], False, reviewed_binding_revision="health-v1", reviewed_binding_environment="unspecified")
    adapter.health = lambda: {"status": status, "diagnostic": "private-vendor-response"}
    health.check(A, system)
    before = deepcopy(ledger.entities)
    def forbidden():
        raise AssertionError("System Map must not probe connectors")
    adapter.health = forbidden
    item = next(row for row in bridge.system_map(A)["systems"] if row["id"] == system)
    assert item["readiness"]["next_step"] == "review_connector_health"
    assert "last check" in item["readiness"]["guidance"].lower()
    assert "private-vendor-response" not in str(item)
    assert ledger.entities == before and not adapter.calls
    assert not bridge.system_map(A)["sync_states"][0]["enabled"]


def test_previous_health_failure_does_not_override_current_binding_guidance():
    from core import bridge_sync as sync
    system, adapter = source()
    adapter.health = lambda: {"status": "authentication_required"}
    health.check(A, system)
    runtime.bind(system, adapter, revision="health-v2", objects=["customers"])
    mapping = bridge.system_map(A)["mappings"][0]
    sync.configure(A, mapping["id"], False, reviewed_binding_revision="health-v2", reviewed_binding_environment="unspecified")
    item = bridge.system_map(A)["systems"][0]
    assert not item["connector_health"]["current_binding"]
    assert item["readiness"]["next_step"] == "review_collection"



def test_successful_recheck_clears_health_guidance_without_enabling_collection():
    from core import bridge_sync as sync
    system, adapter = source()
    mapping = bridge.system_map(A)["mappings"][0]
    sync.configure(A, mapping["id"], False, reviewed_binding_revision="health-v1", reviewed_binding_environment="unspecified")
    adapter.health = lambda: {"status": "permission_denied"}
    health.check(A, system)
    assert bridge.system_map(A)["systems"][0]["readiness"]["next_step"] == "review_connector_health"
    adapter.health = lambda: {"status": "ready"}
    health.check(A, system)
    report = bridge.system_map(A)
    assert report["systems"][0]["readiness"]["next_step"] == "review_collection"
    assert not report["sync_states"][0]["enabled"] and adapter.calls == []



@pytest.mark.parametrize("source_kind,expected", [("malformed", "source_changed"), ("directory", "permission_denied"), ("missing", "unavailable")])
def test_local_export_probe_preserves_safe_failure_classification(tmp_path, source_kind, expected):
    from core.bridge_adapters.export_file import ExportFileConnector
    from core import bridge_sync as sync
    system, mapping, state, _ = configured(False)
    path = tmp_path if source_kind == "directory" else tmp_path / "private-source-name.csv"
    if source_kind == "malformed":
        path.write_text("private-source-payload", encoding="utf-8")
    adapter = ExportFileConnector(path, object_type="customers")
    runtime.bind(system, adapter, revision="file-health-v1", objects=["customers"], environment="local_file")
    sync.configure(A, mapping, False, reviewed_binding_revision="file-health-v1", reviewed_binding_environment="local_file")
    result = health.check(A, system)
    assert result["stored"] and result["status"] == expected
    report = bridge.system_map(A)
    assert report["systems"][0]["connector_health"]["status"] == expected
    assert report["systems"][0]["readiness"]["next_step"] == "review_connector_health"
    assert "private-source" not in str(report) and str(tmp_path) not in str(report)
    assert not report["sync_states"][0]["enabled"]
