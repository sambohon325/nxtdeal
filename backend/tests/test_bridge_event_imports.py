from copy import deepcopy

import pytest
from core import bridge_event_imports as imports, bridge_event_profiles as profiles, dealer_bridge as bridge
from core.dealeros import ledger
from core.entities import Entity
from tests.test_dealer_bridge import A, B, API, isolated  # noqa: F401
from tests.test_bridge_event_profiles import proposed
from tests.test_bridge_adf_discovery import ADF


def staged(content=ADF):
    system, profile = proposed()
    return system, profile, imports.stage(API, profile, content)["id"]


def test_staging_and_validation_never_create_canonical_records():
    _, _, job = staged()
    report = imports.report(A, job)
    assert report["rows"][0]["values"] == {"first_name": "Private Name", "email": "private@example.com"}
    assert report["source_evidence"]["storage_policy"] == "mapped_event_values_only"
    assert "<adf>" not in str(report)
    assert imports.validate(API, job)["status"] == "validated"
    assert not report["activation_available"]
    assert not any(e.entity_type in {"Lead", "SourceObservation", "BridgeExternalID"} for e in ledger.entities.values())


def test_within_batch_replay_is_duplicate_but_conflict_blocks_batch():
    content = ADF.replace('</adf>', '') + ADF.replace('<adf>', '')
    _, _, job = staged(content)
    assert [row["status"] for row in imports.validate(A, job)["rows"]] == ["ready", "duplicate"]
    _, _, conflict = staged(content.replace('Private Name', 'Other', 1))
    assert imports.validate(A, conflict)["status"] == "blocked"


def test_existing_email_candidate_blocks_and_is_workspace_scoped():
    _, _, job = staged()
    ledger.add_entity(Entity('LEAD-foreign', 'Lead', {"workspace_id": "elsewhere", "Email": "private@example.com"}))
    assert imports.validate(A, job)["status"] == "validated"
    ledger.add_entity(Entity('LEAD-local', 'Lead', {"Email": "PRIVATE@example.com"}))
    result = imports.validate(A, job)
    assert result["status"] == "blocked" and result["rows"][0]["candidates"] == ['LEAD-local']


def test_pause_revocation_and_payload_changes_fence_validation():
    system, profile, job = staged()
    bridge.set_system_paused(B, system, True, "Review this source first")
    with pytest.raises(ValueError, match="paused"): imports.validate(A, job)
    bridge.set_system_paused(B, system, False, "Resume reviewed source")
    bridge.get(job, 'BridgeEventJob')["rows"][0]["values"]["first_name"] = "Changed"
    with pytest.raises(ValueError, match="rows changed"): imports.validate(A, job)
    profiles.revoke(B, profile, "Revoke the source profile")
    with pytest.raises(ValueError, match="revoked"): imports.validate(A, job)


def test_cancellation_is_human_only_and_final():
    _, _, job = staged()
    with pytest.raises(PermissionError): imports.cancel(API, job, "Cancel this test batch")
    imports.cancel(B, job, "Cancel this test batch")
    assert imports.cancel(B, job, "Cancel this test batch")["status"] == "cancelled"
    with pytest.raises(ValueError, match="Finished"): imports.validate(A, job)
    with pytest.raises(PermissionError): imports.report({**A, "workspace_id": "elsewhere"}, job)


def test_failed_validation_save_restores_review_state(monkeypatch):
    _, _, job = staged()
    before = deepcopy(bridge.get(job, 'BridgeEventJob'))
    def fail(_): raise OSError('synthetic failure')
    monkeypatch.setattr(bridge, 'save_graph', fail)
    with pytest.raises(OSError): imports.validate(A, job)
    assert bridge.get(job, 'BridgeEventJob') == before


def test_original_source_evidence_is_bound_to_review():
    _, _, job = staged()
    bridge.get(job, 'BridgeEventJob')["source_evidence"]["export_sha256"] = "changed"
    with pytest.raises(ValueError, match="source evidence changed"):
        imports.validate(A, job)


def test_phone_formatting_is_a_candidate_not_an_automatic_merge():
    system, _ = proposed()
    profile = profiles.propose(A, system, "Provider", {"phone": {"source": "phone", "transform": "text"}})["id"]
    content = ADF.replace('</contact>', '<phone>(555) 123-4567</phone></contact>')
    job = imports.stage(API, profile, content)["id"]
    ledger.add_entity(Entity('LEAD-phone', 'Lead', {"Phone": "5551234567"}))
    result = imports.validate(A, job)
    assert result["status"] == "blocked"
    assert result["rows"][0]["candidates"] == ['LEAD-phone']


def test_activation_requires_human_approval_and_replay_preserves_native_edits():
    _, profile, job = staged()
    imports.validate(API, job)
    with pytest.raises(PermissionError): imports.activate(B, job)
    profiles.approve(B, profile)
    with pytest.raises(PermissionError): imports.activate(API, job)
    assert imports.activate(A, job)["created"] == 1
    assert imports.activate(A, job)["idempotent"]
    report = imports.report(A, job)
    receipt = report["activation_receipt"]
    assert receipt["checksum"] == bridge.digest({k: v for k, v in receipt.items() if k != "checksum"})
    target = ledger.get_entity(receipt["created"][0]["canonical_id"])
    target.attributes["first_name"] = "Dealership edit"
    replay = imports.stage(API, profile, ADF)["id"]
    assert imports.validate(A, replay)["rows"][0]["status"] == "duplicate"
    assert imports.activate(B, replay)["created"] == 0
    assert target.attributes["first_name"] == "Dealership edit"
    events = bridge.chrono_observations(A)
    assert len(events) == 1 and events[0]["source_time_semantics"] == "created"
    assert "modified_at" not in events[0]


def test_activation_rechecks_new_identity_candidates():
    _, profile, job = staged()
    profiles.approve(B, profile)
    imports.validate(A, job)
    ledger.add_entity(Entity('LEAD-late', 'Lead', {"Email": "private@example.com"}))
    with pytest.raises(ValueError, match="review changed"):
        imports.activate(A, job)
    assert bridge.get(job, 'BridgeEventJob')["status"] == "validated"
    assert not bridge.chrono_observations(A)


def test_activation_save_failure_rolls_back_created_records_and_receipt(monkeypatch):
    _, profile, job = staged()
    profiles.approve(B, profile)
    imports.validate(A, job)
    before = {key: deepcopy(value.attributes) for key, value in ledger.entities.items()}
    def fail(_): raise OSError('synthetic failure')
    monkeypatch.setattr(bridge, 'save_graph', fail)
    with pytest.raises(OSError): imports.activate(A, job)
    assert {key: value.attributes for key, value in ledger.entities.items()} == before


def test_chrono_envelope_preserves_creation_semantics_and_provider_namespace():
    from core.bridge_chrono import envelope
    _, profile, job = staged()
    profiles.approve(B, profile)
    imports.validate(A, job); imports.activate(B, job)
    event = next(e for e in ledger.entities.values() if e.entity_type == 'SourceObservation')
    payload = envelope(event)
    assert payload.provenance["source_time_semantics"] == "created"
    assert payload.provenance["source_namespace"] == "Provider"
    assert payload.observation.source_timestamp == "2026-10-04T15:00:00+00:00"
    assert payload.observation.import_timestamp != payload.observation.source_timestamp


def test_event_delivery_uses_existing_explicit_destination_authorization(monkeypatch):
    from core import bridge_chrono as outbox
    from tests.test_bridge_chrono import FakeSink
    monkeypatch.setattr(outbox, '_BINDING', None)
    monkeypatch.setattr(outbox.credential_store, 'get_record', lambda _: {"role": "ADMIN"})
    _, profile, job = staged()
    profiles.approve(B, profile)
    imports.validate(A, job); imports.activate(B, job)
    sink = FakeSink()
    outbox.bind_sink('event-test-sink', 'v1', sink)
    assert outbox.deliver_once(A)["status"] == "disabled" and sink.calls == []
    outbox.configure(A, True, 'event-test-sink', 'v1')
    assert outbox.deliver_once(A)["delivered"] == 1
    payload = sink.calls[0][1][0]
    assert payload.provenance["source_time_semantics"] == "created"
    assert outbox.deliver_once(A)["delivered"] == 0


def test_missing_observation_cannot_be_treated_as_valid_replay():
    _, profile, job = staged()
    profiles.approve(B, profile)
    imports.validate(A, job); imports.activate(B, job)
    event_id = imports.report(A, job)["activation_receipt"]["created"][0]["event_id"]
    ledger.entities.pop(event_id)
    replay = imports.stage(API, profile, ADF)["id"]
    result = imports.validate(A, replay)
    assert result["status"] == "blocked"
    assert result["rows"][0]["error_code"] == "source_identity_unavailable"


def test_two_prevalidated_batches_cannot_create_duplicate_leads():
    _, profile, first = staged()
    profiles.approve(B, profile)
    second = imports.stage(A, profile, ADF.replace('private-id', 'second-id'))["id"]
    assert imports.validate(A, first)["status"] == "validated"
    assert imports.validate(A, second)["status"] == "validated"
    imports.activate(B, first)
    with pytest.raises(ValueError, match="review changed"):
        imports.activate(B, second)
    assert len([e for e in ledger.entities.values() if e.entity_type == "Lead"]) == 1
    assert imports.validate(A, second)["status"] == "blocked"
