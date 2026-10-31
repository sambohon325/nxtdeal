"""Synthetic credential provider through real Bridge staging/health boundaries."""
from datetime import datetime, timedelta, timezone

import pytest
from core import bridge_credentials as credentials, bridge_runtime as runtime, bridge_sync as sync, bridge_health as health
from core import dealer_bridge as bridge
from core.bridge_contracts import SourceRecord, SyncPage
from core.dealeros import ledger
from tests.test_bridge_sync import A, B, API, isolated, configured, state_of  # noqa: F401
from tests.test_bridge_credentials import Provider


class CredentialReadConnector:
    capabilities = frozenset({"sync", "health"})
    def __init__(self, broker, system, config):
        self.broker, self.system, self.config = broker, system, config
        self.accepted_tokens = {"synthetic-secret-one", "synthetic-secret-two"}
        self.read_count = 0
    def _credential(self):
        material = self.broker.resolve(self.system, **self.config)
        if material.require("access_token") not in self.accepted_tokens:
            raise credentials.CredentialUnavailable()
    def sync(self, object_type, cursor):
        self._credential()
        self.read_count += 1
        return SyncPage((SourceRecord(object_type, "credential-fixture", "2026-10-04T12:00:00Z",
                         {"name": "Synthetic credential fixture", "email": "fixture@example.invalid"}),), "fixture-page", True)
    def health(self):
        self._credential()
        return {"status": "ready"}


def source():
    system, mapping, state, _ = configured()
    broker, provider = credentials.CredentialBroker(), Provider()
    config = dict(reference="vault/synthetic-read", account_ref="synthetic-account", environment="synthetic", objects=["customers"])
    broker.grant(system, provider=provider, **config, expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
    adapter = CredentialReadConnector(broker, system, config)
    runtime.bind(system, adapter, revision="credential-fixture-1", objects=["customers"], environment="synthetic")
    sync.configure(A, mapping, True, 60, reviewed_binding_revision="credential-fixture-1", reviewed_binding_environment="synthetic")
    return system, state, broker, provider, adapter, config


def test_credential_backed_page_requires_human_activation_and_never_stores_token():
    system, state, broker, provider, adapter, _ = source()
    assert health.check(A, system)["status"] == "ready"
    provider.value["access_token"] = "synthetic-secret-two"
    result = sync.run_once(A, state)
    assert result["status"] == "awaiting_review" and adapter.read_count == 1
    job = result["job_id"]
    assert not any(entity.entity_type == "Customer" for entity in ledger.entities.values())
    bridge.validate(API, job)
    with pytest.raises(PermissionError): bridge.activate(API, job)
    bridge.activate(B, job)
    assert sync.run_once(A, state)["status"] == "checkpointed"
    assert state_of(state)["cursor"] == "fixture-page"
    assert "synthetic-secret" not in str({key: value.attributes for key, value in ledger.entities.items()})
    assert "vault/synthetic-read" not in str(bridge.system_map(A))


@pytest.mark.parametrize("during_read", [False, True])
def test_revocation_blocks_collection_without_advancing_or_staging(during_read):
    system, state, broker, provider, adapter, _ = source()
    if during_read: provider.during_read = lambda: broker.revoke(system)
    else: broker.revoke(system)
    assert sync.run_once(A, state)["status"] == "blocked"
    record = state_of(state)
    assert record["last_error_code"] == "authentication_required"
    item = next(item for item in bridge.system_map(A)["systems"] if item["id"] == system)
    assert item["readiness"]["next_step"] == "renew_connector_access"
    assert record["cursor"] is None and record.get("pending_job_id") is None
    assert adapter.read_count == 0
    assert not any(entity.entity_type == "BridgeJob" for entity in ledger.entities.values())
    assert health.check(A, system)["status"] == "authentication_required"
    assert not provider.calls if not during_read else len(provider.calls) == 1


def test_restored_credentials_require_explicit_retry_and_do_not_autoactivate():
    system, state, broker, provider, adapter, config = source()
    broker.revoke(system)
    assert sync.run_once(A, state)["status"] == "blocked"
    broker.grant(system, provider=provider, **config, expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
    assert sync.run_once(A, state)["status"] == "blocked"
    with pytest.raises(PermissionError): sync.retry(API, state, "Retry after synthetic credential restoration")
    sync.retry(B, state, "Retry after synthetic credential restoration")
    assert sync.run_once(B, state)["status"] == "awaiting_review"
    assert state_of(state)["cursor"] is None
