"""Explicit separation is limited to humans reviewing all customer candidates."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from core import dealer_bridge as b
from core.dealeros import ledger
from core.entities import Entity
from api.routers.dealer_bridge import router, admin
from tests.test_dealer_bridge import candidate_job, A, B, API, CSV, imported, isolated  # noqa: F401


def tokens(candidate):
    return {candidate["id"]: candidate["review_token"]}


def test_shared_email_can_be_reviewed_as_different_customer():
    mapping, job, candidate = candidate_job()
    b.keep_identity_separate(B, job, 1, tokens(candidate), "Different household member sharing this email")
    assert b.validate(A, job)[0]["identity_resolution"] == "human_keep_separate"
    b.activate(B, job)
    customers = [e for e in ledger.get_all().values() if e.entity_type == "Customer"]
    assert len(customers) == 2
    assert ledger.get_entity(candidate["id"]).attributes["FirstName"] == "Original"
    assert b.chrono_observations(A)[0]["identity_resolution"] == "human_keep_separate"
    imported(CSV.replace("2026-01-01", "2027-01-01"), mapping)
    assert len([e for e in ledger.get_all().values() if e.entity_type == "Customer"]) == 2


def test_review_requires_current_complete_candidate_set():
    _, job, candidate = candidate_job()
    with pytest.raises(PermissionError):
        b.keep_identity_separate(API, job, 1, tokens(candidate), "Different customer based on source")
    ledger.add_entity(Entity("another", "Customer", {"Email": "ada@example.com"}))
    with pytest.raises(ValueError, match="every current"):
        b.keep_identity_separate(B, job, 1, tokens(candidate), "Different customer based on source")
    offered = b.validate(A, job)[0]["candidate_records"]
    b.keep_identity_separate(B, job, 1, {c["id"]: c["review_token"] for c in offered}, "Reviewed both household members")
    ledger.get_entity("another").attributes["FirstName"] = "Changed"
    assert b.validate(A, job)[0]["status"] == "quarantined"
    with pytest.raises(ValueError): b.activate(B, job)


def test_no_generic_override_for_rows_without_candidates_or_terminal_jobs():
    _, job, candidate = candidate_job()
    for invalid in ({}, {"invented": "x" * 64}):
        with pytest.raises(ValueError): b.keep_identity_separate(B, job, 1, invalid, "Reviewed source and candidates")
    b.cancel_import(B, job, "No longer need this import")
    with pytest.raises(ValueError): b.keep_identity_separate(B, job, 1, tokens(candidate), "Reviewed source and candidates")


def test_separation_http_permission_and_strict_body():
    _, job, candidate = candidate_job()
    app = FastAPI(); app.include_router(router)
    client = TestClient(app)
    body = {"row": 1, "candidate_tokens": tokens(candidate), "reason": "Different verified customer"}
    app.dependency_overrides[admin] = lambda: API
    assert client.post(f"/dealer-bridge/imports/{job}/identity-separate", json=body).status_code == 403
    app.dependency_overrides[admin] = lambda: B
    assert client.post(f"/dealer-bridge/imports/{job}/identity-separate", json={**body, "row": True}).status_code == 422
    assert client.post(f"/dealer-bridge/imports/{job}/identity-separate", json=body).status_code == 200


def test_withdraw_stale_review_when_no_candidates_remain():
    _, job, candidate = candidate_job()
    review = b.keep_identity_separate(B, job, 1, tokens(candidate), "Different verified household member")["id"]
    ledger.get_entity(candidate["id"]).attributes["Email"] = "changed@example.com"
    row = b.validate(A, job)[0]
    assert row["status"] == "quarantined" and row["review_decision_active"]
    with pytest.raises(PermissionError): b.withdraw_identity_review(API, job, 1, "Changed identity evidence")
    b.withdraw_identity_review(B, job, 1, "Changed identity evidence")
    assert b.validate(A, job)[0]["status"] == "ready"
    assert ledger.get_entity(review) is not None
    assert any(e.entity_type == "BridgeIdentityReviewWithdrawal" for e in ledger.get_all().values())
    b.activate(B, job)
    with pytest.raises(ValueError): b.withdraw_identity_review(B, job, 1, "Cannot undo activated identity")


def test_established_separate_customers_can_share_email_in_later_bulk_import():
    from tests.test_dealer_bridge import setup
    _, mapping = setup(); imported(mapping=mapping)
    second = b.stage(A, mapping, CSV.replace("\n1,", "\n2,"))["id"]
    candidate = b.validate(A, second)[0]["candidate_records"][0]
    b.keep_identity_separate(B, second, 1, tokens(candidate), "Verified different household member")
    b.validate(A, second); b.activate(B, second)
    both = "external_id,modified_at,name,email\n1,2027-01-01T00:00:00Z,Ada,ada@example.com\n2,2027-01-01T00:00:00Z,Grace,ada@example.com\n"
    job = b.stage(A, mapping, both)["id"]
    assert all(row["status"] == "ready" for row in b.validate(A, job))
    b.activate(B, job)
    assert len([e for e in ledger.get_all().values() if e.entity_type == "Customer"]) == 2
    # A third unlinked identity still needs review and cannot inherit this exception.
    unknown = b.stage(A, mapping, both.replace("\n2,", "\n3,"))["id"]
    assert b.validate(A, unknown)[1]["status"] == "quarantined"


def test_candidate_scan_accounts_for_legacy_whitespace_and_divergent_aliases():
    from tests.test_dealer_bridge import setup
    _, mapping = setup()
    ledger.add_entity(Entity("LEGACY-1", "Customer", {"email": "old@example.com", "Email": " ADA@EXAMPLE.COM "}))
    job = b.stage(A, mapping, CSV)["id"]
    row = b.validate(A, job)[0]
    assert row["status"] == "quarantined"
    candidate = row["candidate_records"][0]
    assert candidate["id"] == "LEGACY-1" and candidate["summary"]["alternate_email"] == " ADA@EXAMPLE.COM "
