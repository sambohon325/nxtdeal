import pytest
from core import bridge_inbound as inbound, bridge_event_imports as imports, bridge_event_retention as retention, dealer_bridge as b
from core.dealeros import ledger
from tests.test_bridge_inbound import configured, delivery, bindings  # noqa: F401
from tests.test_bridge_sync import A, B, isolated  # noqa: F401


def received():
    system, _, _, _, _ = configured()
    result = inbound.receive(*delivery())
    receipt = b.get(result["receipt_id"],"BridgeInboundDelivery")
    return system, result["receipt_id"], receipt["job_id"]


def test_delivery_provenance_is_visible_and_survives_approval_cleanup_and_source_pause():
    system, receipt, job = received()
    report = imports.report(A,job)
    assert report["ingestion_evidence"]["receipt_id"] == receipt
    assert report["ingestion_evidence"]["environment"] == "synthetic"
    imports.validate(A,job); imports.activate(B,job)
    approved = imports.report(A,job)
    assert approved["activation_receipt"]["staged_principal"] == "inbound_gateway"
    assert approved["activation_receipt"]["ingestion_evidence"] == report["ingestion_evidence"]
    assert b.get(system,"BridgeSystem")["import_health"]["transport"] == "nxtdeal_adf_gateway_v1"
    observation = next(e.attributes for e in ledger.get_all().values() if e.entity_type == "SourceObservation")
    assert observation["ingestion_receipt_id"] == receipt
    from core import bridge_chrono
    entity = next(e for e in ledger.get_all().values() if e.entity_type == "SourceObservation")
    provenance = bridge_chrono.envelope(entity).provenance
    assert provenance["ingestion_receipt_id"] == receipt and provenance["source_transport"] == "nxtdeal_adf_gateway_v1"
    review = retention.preview(A,job)
    retention.cleanup(B,job,review["review_token"],"Reviewed synthetic retained delivery evidence")
    b.get(system,"BridgeSystem")["paused"] = True
    assert imports.report(A,job)["receipt_integrity"] == "consistent"
    assert imports.report(A,job)["ingestion_evidence"] == report["ingestion_evidence"]


@pytest.mark.parametrize("change", ["body", "profile", "owner", "time", "link", "principal", "transport"])
def test_changed_delivery_evidence_blocks_review_and_activation(change):
    _, receipt_id, job_id = received()
    job, receipt = b.get(job_id,"BridgeEventJob"), b.get(receipt_id,"BridgeInboundDelivery")
    imports.validate(A,job_id)
    if change == "body": receipt["body_hash"] = "changed"
    elif change == "profile": receipt["profile_id"] = "another-profile"
    elif change == "owner": receipt["job_id"] = "another-job"
    elif change == "time": receipt["received_at"] = "2026-01-01T00:00:00Z"
    elif change == "link": job.pop("inbound_receipt_id")
    elif change == "principal": job["created_principal"] = "session"
    else: job["transport"] = "manual_adf"
    assert imports.report(A,job_id)["ingestion_evidence"]["status"] == "changed"
    assert not imports.report(A,job_id)["activation_available"]
    with pytest.raises((ValueError,KeyError)): imports.activate(B,job_id)
    assert not any(e.entity_type == "Lead" for e in ledger.get_all().values())


def test_changed_checksum_consistent_delivery_requires_fresh_validation():
    _, receipt_id, job_id = received()
    imports.validate(A,job_id)
    receipt = b.get(receipt_id,"BridgeInboundDelivery")
    receipt["binding_revision"] = "changed-revision"
    receipt["checksum"] = b.digest({key:value for key,value in receipt.items() if key != "checksum"})
    with pytest.raises(ValueError,match="review changed"): imports.activate(B,job_id)


def test_changed_delivery_receipt_invalidates_activation_evidence_and_cleanup():
    _, receipt_id, job_id = received()
    imports.validate(A,job_id); imports.activate(B,job_id)
    b.get(receipt_id,"BridgeInboundDelivery")["received_at"] = "changed"
    assert imports.report(A,job_id)["receipt_integrity"] == "changed"
    assert not retention.preview(A,job_id)["eligible"]


def test_manual_upload_has_no_gateway_attestation_and_retains_legacy_receipt_compatibility():
    from tests.test_bridge_event_imports import staged
    _, profile, job = staged()
    from core import bridge_event_profiles
    bridge_event_profiles.approve(B,profile)
    assert imports.report(A,job)["ingestion_evidence"] is None
    imports.validate(A,job); imports.activate(B,job)
    stored = b.get(job,"BridgeEventJob")
    assert stored["activation_receipt"]["transport"] == "manual_adf"
    receipt = stored["activation_receipt"]
    receipt.pop("staged_principal"); receipt.pop("transport")
    receipt["checksum"] = b.digest({key:value for key,value in receipt.items() if key != "checksum"})
    assert imports.report(A,job)["receipt_integrity"] == "consistent"
