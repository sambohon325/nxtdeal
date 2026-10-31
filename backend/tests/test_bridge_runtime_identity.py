"""A retained runtime instance cannot outlive changes to its source identity."""
import pytest
from core import dealer_bridge as b, bridge_runtime as runtime, bridge_health as health, bridge_sync as sync
from core.bridge_discovery import discover_bound_schema
from core.dealeros import ledger
from tests.test_bridge_sync import A, configured, isolated  # noqa: F401


@pytest.mark.parametrize("change", ["vendor","workspace","type","missing"])
def test_binding_rejects_changed_source_identity_before_adapter_io(change):
    system, _, state, adapter = configured(False)
    entity = ledger.get_entity(system)
    if change == "vendor": entity.attributes["vendor"] = "CSV"
    elif change == "workspace": entity.attributes["workspace_id"] = "other"
    elif change == "type": entity.entity_type = "Customer"
    else: ledger.entities.pop(system)
    with pytest.raises(ValueError, match="Source identity changed"):
        runtime.binding(system)
    assert runtime.describe(system) == {"status":"unavailable","capabilities":[]}
    assert adapter.calls == []


def source():
    system, mapping, state, adapter = configured(False)
    adapter.capabilities = frozenset({"sync","schema","health"})
    adapter.schema = lambda object_type: ["external_id","modified_at","name","email"]
    adapter.health = lambda: {"status":"ready"}
    runtime.bind(system, adapter, revision="identity-v2", objects=["customers"])
    sync.configure(A, mapping, False, 60, reviewed_binding_revision="identity-v2", reviewed_binding_environment="unspecified")
    return system, state, adapter


def test_vendor_change_prevents_health_schema_and_collection_calls():
    system, state, adapter = source()
    def forbidden(*args): pytest.fail("Changed source identity must prevent adapter IO")
    adapter.health = adapter.schema = adapter.sync = forbidden
    b.get(system,"BridgeSystem")["vendor"] = "CSV"
    with pytest.raises(ValueError): health.check(A, system)
    with pytest.raises(ValueError): discover_bound_schema(A, system,"Customer","customers")
    with pytest.raises(ValueError): sync.run_once(A, state)


def test_vendor_change_during_health_discards_result():
    system, _, adapter = source()
    def changed():
        b.get(system,"BridgeSystem")["vendor"] = "CSV"
        return {"status":"ready"}
    adapter.health = changed
    assert health.check(A, system) == {"status":"discarded","stored":False}
    assert "connector_health" not in b.get(system,"BridgeSystem")


def test_vendor_change_during_schema_discards_result():
    system, _, adapter = source()
    def changed(object_type):
        b.get(system,"BridgeSystem")["vendor"] = "CSV"
        return ["external_id","modified_at","name"]
    adapter.schema = changed
    with pytest.raises(ValueError, match="Source identity changed"):
        discover_bound_schema(A, system,"Customer","customers")


def test_vendor_change_during_collection_drops_page_without_checkpoint():
    system, state, adapter = source()
    adapter.during_read = lambda: b.get(system,"BridgeSystem").update(vendor="CSV")
    assert sync.run_once(A, state)["status"] == "blocked"
    saved = b.get(state,"BridgeSyncState")
    assert saved["cursor"] is None and saved["pending_job_id"] is None and saved["pages_accepted"] == 0
    assert not any(e.entity_type == "BridgeJob" for e in ledger.get_all().values())


def test_replacing_changed_source_binding_requires_new_revision_and_collection_review():
    system, state, adapter = source()
    b.get(system,"BridgeSystem")["vendor"] = "CSV"
    with pytest.raises(ValueError, match="new revision"):
        runtime.bind(system, adapter, revision="identity-v2", objects=["customers"])
    runtime.bind(system, adapter, revision="identity-v3", objects=["customers"])
    with pytest.raises(ValueError, match="reviewed"):
        sync.run_once(A, state)
    assert adapter.calls == []
    sync.configure(A, b.get(state,"BridgeSyncState")["mapping_id"], False, 60, reviewed_binding_revision="identity-v3", reviewed_binding_environment="unspecified")
    assert sync.run_once(A, state)["status"] == "awaiting_review"
