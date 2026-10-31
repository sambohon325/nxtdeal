from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import hmac

import pytest
from core import bridge_inbound as inbound, bridge_event_profiles as profiles, bridge_event_imports as imports, dealer_bridge as b
from core.bridge_adapters.adf_gateway import ADFGatewayVerifier, InvalidDelivery, signing_bytes
from core.bridge_credentials import CredentialBroker, CredentialUnavailable
from core.dealeros import ledger
from tests.test_bridge_sync import A, B, API, isolated  # noqa: F401
from tests.test_bridge_adf_discovery import ADF

ENDPOINT = "synthetic_endpoint_0123456789"
KEY = "synthetic-gateway-key-not-for-production-123456"


@pytest.fixture(autouse=True)
def bindings():
    prior = dict(inbound._BINDINGS)
    inbound._BINDINGS.clear()
    yield
    inbound._BINDINGS.clear(); inbound._BINDINGS.update(prior)


def configured(enabled=True, approved=True, limit=100):
    system = b.connect(A, "CSV", "Synthetic gateway")["id"]
    profile = profiles.propose(A, system, "Provider", {"first_name":{"source":"name_full","transform":"text"}})["id"]
    if approved: profiles.approve(B, profile)
    class Provider:
        during_read = None
        def read(self, reference):
            if self.during_read: self.during_read()
            return {"hmac_key":KEY}
    provider, broker = Provider(), CredentialBroker()
    broker.grant(system, provider=provider, reference="vault/gateway", account_ref="qa-gateway", environment="synthetic",
        objects=["adf_prospects"], expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
    verifier = ADFGatewayVerifier(broker=broker, system_id=system, secret_reference="vault/gateway", account_ref="qa-gateway", environment="synthetic")
    inbound.bind(ENDPOINT, profile_id=profile, revision="gateway-v1", environment="synthetic", verifier=verifier, max_pending_batches=limit)
    if enabled: inbound.configure(B, ENDPOINT, True, "gateway-v1")
    return system, profile, broker, provider, verifier


def delivery(identity="delivery-1", body=None, signed_at=None, endpoint=ENDPOINT):
    body = ADF.encode() if body is None else body
    signed_at = str(int(datetime.now(timezone.utc).timestamp())) if signed_at is None else signed_at
    signature = hmac.new(KEY.encode(), signing_bytes(endpoint, identity, signed_at, body), hashlib.sha256).hexdigest()
    return (endpoint, identity, signed_at, signature, body)


def test_signed_delivery_stages_only_and_duplicate_delivery_reuses_receipt():
    system, profile, _, _, _ = configured()
    first = inbound.receive(*delivery())
    assert first["status"] == "received_for_review"
    receipt = b.get(first["receipt_id"], "BridgeInboundDelivery")
    job = b.get(receipt["job_id"], "BridgeEventJob")
    assert job["status"] == "staged" and job["created_principal"] == "inbound_gateway"
    assert not any(e.entity_type in {"Lead", "SourceObservation"} for e in ledger.get_all().values())
    before = {key: deepcopy(value.attributes) for key,value in ledger.entities.items()}
    duplicate = inbound.receive(*delivery())
    assert duplicate == {"status":"already_received", "receipt_id":first["receipt_id"]}
    assert before == {key:value.attributes for key,value in ledger.entities.items()}
    assert KEY not in str(before) and delivery()[3] not in str(before)
    imports.validate(A, receipt["job_id"])
    with pytest.raises(PermissionError): imports.activate(API, receipt["job_id"])
    imports.activate(B, receipt["job_id"])
    assert inbound.receive(*delivery())["status"] == "already_received"


@pytest.mark.parametrize("change", ["signature","body","identity","endpoint","expired","future"])
def test_signed_fields_and_replay_window_cannot_be_changed(change):
    configured()
    values = list(delivery())
    if change == "signature": values[3] = "0" * 64
    elif change == "body": values[4] += b" "
    elif change == "identity": values[1] = "another-delivery"
    elif change == "endpoint": values[0] = "another_endpoint_0123456789"
    else: values = list(delivery(signed_at=str(int(datetime.now(timezone.utc).timestamp()) + (-301 if change == "expired" else 31))))
    with pytest.raises((InvalidDelivery, ValueError)): inbound.receive(*values)
    assert not any(e.entity_type == "BridgeEventJob" for e in ledger.get_all().values())


def test_same_delivery_id_with_different_validly_signed_content_is_rejected():
    configured()
    inbound.receive(*delivery())
    with pytest.raises(InvalidDelivery): inbound.receive(*delivery(body=ADF.encode()+b" "))
    assert len([e for e in ledger.get_all().values() if e.entity_type == "BridgeEventJob"]) == 1


@pytest.mark.parametrize("condition", ["disabled","profile_revoked","source_paused","admin_disabled","rebound","credential_revoked"])
def test_runtime_authorization_must_remain_current(condition, monkeypatch):
    system, profile, broker, _, verifier = configured()
    if condition == "disabled": inbound.configure(B, ENDPOINT, False)
    elif condition == "profile_revoked": profiles.revoke(B, profile, "Synthetic source revoked")
    elif condition == "source_paused": b.get(system,"BridgeSystem")["paused"] = True
    elif condition == "admin_disabled": monkeypatch.setattr(inbound.credential_store,"get_record",lambda _: {"role":"ADMIN","disabled":True})
    elif condition == "rebound": inbound.bind(ENDPOINT, profile_id=profile, revision="gateway-v2", environment="synthetic", verifier=verifier)
    else: broker.revoke(system)
    with pytest.raises((ValueError, PermissionError)): inbound.receive(*delivery())
    assert not any(e.entity_type == "BridgeEventJob" for e in ledger.get_all().values())


def test_policy_change_during_secret_read_discards_delivery():
    _, _, _, provider, _ = configured()
    provider.during_read = lambda: inbound.configure(B, ENDPOINT, False)
    with pytest.raises(InvalidDelivery): inbound.receive(*delivery())
    assert not any(e.entity_type == "BridgeEventJob" for e in ledger.get_all().values())


def test_explicit_environment_bundle_can_supply_gateway_key_without_changing_policy(monkeypatch):
    import json
    from core.bridge_secret_providers import EnvironmentSecretProvider
    system, _, broker, _, _ = configured()
    name = "NXTDEAL_TEST_ONLY_GATEWAY_BUNDLE"
    monkeypatch.setenv(name, json.dumps({"hmac_key":KEY}))
    provider = EnvironmentSecretProvider({"vault/gateway":name})
    broker.grant(system, provider=provider, reference="vault/gateway", account_ref="qa-gateway", environment="synthetic",
        objects=["adf_prospects"], expires_at=datetime.now(timezone.utc)+timedelta(minutes=5))
    assert inbound.receive(*delivery())["status"] == "received_for_review"
    monkeypatch.delenv(name)
    with pytest.raises(CredentialUnavailable): inbound.receive(*delivery(identity="delivery-2"))
    assert len([e for e in ledger.get_all().values() if e.entity_type == "BridgeEventJob"]) == 1


def test_explicit_human_policy_requires_approved_profile_and_exact_revision():
    configured(enabled=False, approved=False)
    with pytest.raises(ValueError): inbound.configure(B, ENDPOINT, True, "gateway-v1")
    with pytest.raises(PermissionError): inbound.configure(API, ENDPOINT, True, "gateway-v1")
    with pytest.raises(ValueError): inbound.receive(*delivery())


def test_pending_queue_limit_allows_duplicate_ack_but_no_extra_job():
    configured(limit=1)
    inbound.receive(*delivery())
    assert inbound.receive(*delivery())["status"] == "already_received"
    with pytest.raises(ValueError, match="queue is full"): inbound.receive(*delivery(identity="delivery-2"))
    assert len([e for e in ledger.get_all().values() if e.entity_type == "BridgeEventJob"]) == 1


def test_receipt_and_staged_job_roll_back_together_on_save_failure(monkeypatch):
    configured()
    before = {key:deepcopy(value.attributes) for key,value in ledger.entities.items()}
    def fail(path): raise OSError("Synthetic durable save failure")
    monkeypatch.setattr(b,"save_graph",fail)
    with pytest.raises(OSError): inbound.receive(*delivery())
    assert before == {key:value.attributes for key,value in ledger.entities.items()}


def test_foreign_workspace_cannot_receive_into_bound_source(monkeypatch):
    configured()
    bound = inbound._BINDINGS[ENDPOINT]
    from dataclasses import replace
    inbound._BINDINGS[ENDPOINT] = replace(bound,workspace_id="another-workspace")
    with pytest.raises(InvalidDelivery): inbound.receive(*delivery())


@pytest.mark.parametrize("first", ["snapshot", "inbound"])
def test_declared_environments_cannot_mix_between_snapshot_and_gateway(first):
    from core import bridge_runtime as runtime, bridge_sync as sync
    from tests.test_bridge_sync import FakeConnector
    system, profile, _, _, verifier = configured()
    mapping = b.propose_mapping(A,system,"Customer","customers",{"first_name":{"source":"name","transform":"text"}})["id"]
    b.approve_mapping(B,mapping)
    if first == "inbound":
        inbound.receive(*delivery())
        runtime.bind(system,FakeConnector(),revision="production-reader",objects=["customers"],environment="production")
        with pytest.raises(ValueError,match="another source environment"):
            sync.configure(B,mapping,True,60)
    else:
        runtime.bind(system,FakeConnector(),revision="synthetic-reader",objects=["customers"],environment="synthetic")
        state = sync.configure(B,mapping,True,60)["id"]
        sync.run_once(B,state)
        production = ADFGatewayVerifier(broker=CredentialBroker(),system_id=system,secret_reference="vault/production",account_ref="production",environment="production")
        inbound.bind(ENDPOINT,profile_id=profile,revision="production-gateway",environment="production",verifier=production)
        with pytest.raises(ValueError,match="another source environment"):
            inbound.configure(B,ENDPOINT,True,"production-gateway")
