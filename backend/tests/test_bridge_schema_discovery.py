"""Connected discovery exposes bounded column names, never sample rows or secrets."""
from copy import deepcopy
from threading import Thread

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core import dealer_bridge as bridge, bridge_runtime as runtime
from core.bridge_discovery import discover_bound_schema
from core.dealeros import ledger
from api.routers.dealer_bridge import router, admin
from tests.test_bridge_sync import A, B, API, configured, isolated  # noqa: F401


def schema_source():
    system, mapping, state, adapter = configured(False)
    adapter.capabilities = frozenset({"sync", "schema"})
    adapter.schema = lambda object_type: ["External ID", "Modified At", "First Name", "email"]
    runtime.bind(system, adapter, revision="schema-v1", objects=["customers"])
    return system, adapter


def test_header_only_suggestions_leave_graph_and_mapping_unchanged():
    system, adapter = schema_source()
    before = deepcopy({key: (value.entity_type, value.attributes) for key, value in ledger.get_all().items()})
    result = discover_bound_schema(API, system, "Customer", "customers")
    assert result["suggestions"]["first_name"] == {"source": "First Name", "transform": "text"}
    assert result["source_columns"] == {"external_id": "External ID", "modified_at": "Modified At"}
    assert result["row_count"] is None and not result["stored"]
    assert result["binding_revision"] == "schema-v1"
    assert result["environment"] == "unspecified"
    assert adapter.calls == []
    assert {key: (value.entity_type, value.attributes) for key, value in ledger.get_all().items()} == before


def test_no_io_without_workspace_object_capability_and_pause_authorization():
    system, adapter = schema_source()
    def forbidden(*args):
        raise AssertionError("Unauthorized inspection must not call the adapter")
    adapter.schema = forbidden
    for actor, kind, source in [({**A, "role": "SALES"}, "Customer", "customers"),
                                ({**A, "workspace_id": "foreign"}, "Customer", "customers"),
                                (A, "Customer", "accounting"), (A, "Unknown", "customers")]:
        with pytest.raises((PermissionError, ValueError)):
            discover_bound_schema(actor, system, kind, source)
    bridge.set_system_paused(B, system, True, "Paused pending source investigation")
    with pytest.raises(ValueError, match="paused"):
        discover_bound_schema(A, system, "Customer", "customers")


def test_sync_only_binding_does_not_gain_schema_access():
    system, _, _, adapter = configured(False)
    adapter.schema = lambda *_: ["email"]
    with pytest.raises(ValueError, match="not authorized"):
        discover_bound_schema(A, system, "Customer", "customers")


@pytest.mark.parametrize("headers", [None, "email", [], ["email", "email"], ["email", {"sample": "secret"}],
                                     [""], ["x" * 121], ["line\nbreak"], [str(i) for i in range(101)]])
def test_invalid_adapter_metadata_is_rejected_without_echoing_payload(headers):
    system, adapter = schema_source()
    adapter.schema = lambda *_: headers
    with pytest.raises(ValueError, match="unique bounded column names") as error:
        discover_bound_schema(A, system, "Customer", "customers")
    assert "secret" not in str(error.value)


def test_vendor_exception_is_sanitized():
    system, adapter = schema_source()
    def fail(*args):
        raise TimeoutError("Authorization: secret-access-token, customer private@example.invalid")
    adapter.schema = fail
    with pytest.raises(ValueError, match="schema inspection failed") as error:
        discover_bound_schema(A, system, "Customer", "customers")
    assert "secret" not in str(error.value) and "private" not in str(error.value)


def test_schema_io_does_not_hold_graph_lock():
    system, adapter = schema_source()
    acquired = []
    def inspect(*args):
        def independent_reader():
            if bridge.LOCK.acquire(timeout=1):
                acquired.append(True)
                bridge.LOCK.release()
        reader = Thread(target=independent_reader, daemon=True)
        reader.start(); reader.join(timeout=2)
        return ["email"]
    adapter.schema = inspect
    assert discover_bound_schema(A, system, "Customer", "customers")["headers"] == ["email"]
    assert acquired == [True]


@pytest.mark.parametrize("change", ["pause", "unbind", "rebind"])
def test_changed_configuration_discards_inflight_result(change):
    system, adapter = schema_source()
    def change_during_read(*args):
        if change == "pause":
            bridge.set_system_paused(B, system, True, "Pause while discovery is in flight")
        elif change == "unbind":
            runtime.unbind(system)
        else:
            runtime.bind(system, adapter, revision="schema-v2", objects=["customers"])
        return ["email"]
    adapter.schema = change_during_read
    with pytest.raises(ValueError):
        discover_bound_schema(A, system, "Customer", "customers")


def test_demo_mode_never_calls_bound_schema(monkeypatch):
    system, adapter = schema_source()
    calls = []
    adapter.schema = lambda *_: calls.append(True)
    monkeypatch.setenv("DEALEROS_DEMO", "1")
    with pytest.raises(ValueError, match="demo mode"):
        discover_bound_schema(A, system, "Customer", "customers")
    assert calls == []


def test_schema_discovery_api_rejects_credentials_urls_and_foreign_objects():
    system, _ = schema_source()
    app = FastAPI(); app.include_router(router)
    app.dependency_overrides[admin] = lambda: API
    client = TestClient(app)
    path = f"/dealer-bridge/systems/{system}/discover-schema"
    body = {"kind": "Customer", "object_type": "customers"}
    assert client.post(path, json=body).status_code == 200
    assert client.post(path, json={**body, "secret_reference": "injected"}).status_code == 422
    assert client.post(path, json={**body, "url": "https://example.invalid"}).status_code == 422
    assert client.post(path, json={**body, "object_type": "accounting"}).status_code == 400



def test_schema_report_identifies_declared_environment_without_approving_it():
    system, adapter = schema_source()
    runtime.bind(system, adapter, revision="schema-sandbox-v1", objects=["customers"], environment="sandbox")
    before = deepcopy(bridge.system_map(A)["sync_states"])
    result = discover_bound_schema(A, system, "Customer", "customers")
    assert result["binding_revision"] == "schema-sandbox-v1" and result["environment"] == "sandbox"
    assert result["status"] == "review_required" and not result["stored"]
    assert bridge.system_map(A)["sync_states"] == before
