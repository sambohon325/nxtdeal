from copy import deepcopy
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from core import dealer_bridge as b
from core.dealer_bridge_migrations import migrate
from core.bridge_connectors import REGISTRY, parse_csv
from core.bridge_contracts import transform
from core.dealeros import ledger
from core.entities import Entity
from api.routers.dealer_bridge import router, admin

A = {"employee_id": "admin-a", "role": "ADMIN", "bridge_principal": "session"}
B = {"employee_id": "admin-b", "role": "ADMIN", "bridge_principal": "session"}
API = {**A, "bridge_principal": "api"}
CSV = "external_id,modified_at,name,email\n1,2026-01-01T00:00:00Z,Ada,ada@example.com\n"

@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    previous = ledger.entities, ledger.relationships
    ledger.entities, ledger.relationships = {}, []
    monkeypatch.setattr(b, "save_graph", lambda path: None)
    yield
    ledger.entities, ledger.relationships = previous

def setup(approved=True):
    system = b.connect(A, "Frazer", "Main store")["id"]
    mapping = b.propose_mapping(API, system, "Customer", "customers", {
        "first_name": {"source": "name", "transform": "text"}, "email": {"source": "email", "transform": "lower"}})["id"]
    if approved:
        b.approve_mapping(B, mapping)
    return system, mapping

def imported(content=CSV, mapping=None):
    if mapping is None:
        _, mapping = setup()
    job = b.stage(A, mapping, content)["id"]
    b.validate(A, job)
    b.activate(B, job)
    return job

def test_staging_never_writes_canonical_and_approval_is_separate():
    _, mapping = setup(False)
    job = b.stage(API, mapping, CSV)["id"]
    assert not any(e.entity_type == "Customer" for e in ledger.get_all().values())
    assert b.validate(API, job)[0]["status"] == "ready"
    with pytest.raises(PermissionError): b.activate(B, job)
    with pytest.raises(PermissionError): b.approve_mapping(A, mapping)
    with pytest.raises(PermissionError): b.approve_mapping({**B, "bridge_principal": "api"}, mapping)
    b.approve_mapping(B, mapping)
    with pytest.raises(PermissionError): b.activate(API, job)
    b.activate(B, job)
    assert b.activate(B, job)["idempotent"]


def test_catalog_registration_never_authenticates_a_new_dealer(monkeypatch):
    class Registered:
        def health(self):
            raise AssertionError("A global adapter must never be probed for a new dealer")
    monkeypatch.setitem(REGISTRY, "Frazer", Registered())
    system = b.connect(A, "Frazer", "New independent store")["id"]
    assert b.get(system, "BridgeSystem")["health"]["status"] == "unavailable"


def test_staging_retains_only_mapped_values_and_hashes_original_export():
    from hashlib import sha256
    import json
    _, mapping = setup()
    content = "external_id,modified_at,name,email,unmapped_private_field\n1,2026-01-01T00:00:00Z,Ada,ada@example.com,DO-NOT-RETAIN-THIS-SENTINEL\n"
    job = b.stage(A, mapping, content)["id"]
    attributes = b.get(job, "BridgeJob")
    assert "unmapped_private_field" not in attributes["rows"][0]
    assert "DO-NOT-RETAIN-THIS-SENTINEL" not in json.dumps(attributes)
    assert attributes["source_evidence"]["export_sha256"] == sha256(content.encode()).hexdigest()
    assert attributes["source_evidence"]["omitted_columns"] == ["unmapped_private_field"]
    b.validate(A, job); b.activate(B, job)
    assert b.import_report(A, job)["source_evidence"]["storage_policy"] == "mapped_columns_only"

def test_replay_and_history_preserve_current_state():
    _, mapping = setup()
    imported(mapping=mapping)
    imported(mapping=mapping)
    imported(CSV.replace("2026-01-01", "2025-01-01").replace("Ada,", "Old,"), mapping)
    customers = [e for e in ledger.get_all().values() if e.entity_type == "Customer"]
    assert len(customers) == 1 and customers[0].attributes["first_name"] == "Ada"
    events = b.chrono_observations(A)
    assert len(events) == 2 and all(e["delivery_status"] == "pending" for e in events)
    assert all(ledger.get_entity(e["event_id"]).entity_type == "SourceObservation" for e in events)
    imported(CSV.replace("2026-01-01", "2027-01-01").replace("Ada,", "New,"), mapping)
    assert customers[0].attributes["first_name"] == "New"

def test_timestamp_conflict_and_cross_system_duplicate_are_quarantined():
    _, mapping = setup()
    imported(mapping=mapping)
    job = b.stage(A, mapping, CSV.replace("Ada,", "Conflict,"))["id"]
    assert b.validate(A, job)[0]["status"] == "quarantined"
    with pytest.raises(ValueError): b.activate(B, job)
    _, other = setup()
    job = b.stage(A, other, CSV)["id"]
    assert b.validate(A, job)[0]["candidates"]

def test_duplicate_within_batch_blocks_whole_activation():
    _, mapping = setup()
    job = b.stage(A, mapping, CSV + "2,2026-01-01T00:00:00Z,Ada,ada@example.com\n")["id"]
    assert b.validate(A, job)[1]["status"] == "quarantined"
    with pytest.raises(ValueError): b.activate(B, job)
    assert not any(e.entity_type == "Customer" for e in ledger.get_all().values())

def test_graph_change_requires_new_preview():
    _, mapping = setup()
    job = b.stage(A, mapping, CSV)["id"]
    b.validate(A, job)
    ledger.add_entity(Entity("existing", "Customer", {"email": "ada@example.com"}))
    with pytest.raises(ValueError, match="Graph changed"): b.activate(B, job)

def test_rollback_on_persistence_failure(monkeypatch):
    _, mapping = setup()
    job = b.stage(A, mapping, CSV)["id"]
    b.validate(A, job)
    previous = deepcopy(ledger.entities)
    def fail(path): raise OSError("disk unavailable")
    monkeypatch.setattr(b, "save_graph", fail)
    with pytest.raises(OSError): b.activate(B, job)
    assert ledger.entities == previous

def test_workspace_and_role_boundaries():
    system, _ = setup()
    with pytest.raises(PermissionError): b.system_map({**A, "role": "SALES"})
    with pytest.raises(PermissionError): b.system_map({**A, "workspace_id": "other"})
    ledger.get_entity(system).attributes["workspace_id"] = "other"
    with pytest.raises(ValueError): b.propose_mapping(A, system, "Customer", "customers", {"email": {"source": "email", "transform": "text"}})

def test_migration_additive_idempotent_and_vendor_stubs_honest():
    ledger.add_entity(Entity("old", "Connection", {"name": "Existing"}))
    assert migrate(A)["changed"] and not migrate(A)["changed"]
    assert ledger.get_entity("old").attributes == {"name": "Existing"}
    assert b.system_map(A)["legacy_connections"][0]["status"] == "legacy_unreviewed"
    for name, adapter in REGISTRY.items():
        if name == "CSV": continue
        assert adapter.health()["status"] == "unavailable"
        with pytest.raises(ValueError): adapter.sync("Customer", None)
        with pytest.raises(ValueError): adapter.write({})

def test_bhph_money_and_references():
    fields = {k: {"source": k, "transform": "text"} for k in ("customer_id", "balance", "currency")}
    assert transform("LoanAccount", fields, {"customer_id": "c1", "balance": "100.10", "currency": "usd"})["balance"] == "100.10"
    for bad in ("NaN", "Infinity", "bad"):
        with pytest.raises(ValueError): transform("LoanAccount", fields, {"customer_id": "c1", "balance": bad, "currency": "usd"})
    with pytest.raises(ValueError): transform("LoanAccount", fields, {"balance": "1"})

def test_strict_csv_and_mapping():
    for bad in ("external_id,modified_at\n1,2026-01-01", "a,a\nx,y", "external_id,modified_at\n,2026-01-01T00:00:00Z"):
        with pytest.raises(ValueError): parse_csv(bad)
    system, _ = setup()
    with pytest.raises(ValueError): b.propose_mapping(A, system, "Customer", "customers", {"email": {"source": "email", "transform": "eval"}})

def test_api_contract_and_authorization():
    app = FastAPI(); app.include_router(router)
    client = TestClient(app)
    assert client.get("/dealer-bridge/system-map").status_code == 401
    app.dependency_overrides[admin] = lambda: A
    assert client.get("/dealer-bridge/system-map").status_code == 200
    assert client.post("/dealer-bridge/systems", json={"vendor": "CSV", "name": "Test", "workspace_id": "other"}).status_code == 422
    assert client.post("/dealer-bridge/systems", json={"vendor": "invented", "name": "Test"}).status_code == 400
    app.dependency_overrides[admin] = lambda: {**A, "role": "SALES"}
    assert client.get("/dealer-bridge/system-map").status_code == 403

def test_write_proposals_never_dispatch():
    system, mapping = setup()
    imported(mapping=mapping)
    target = next(e.id for e in ledger.get_all().values() if e.entity_type == "Customer")
    assert b.propose_write(API, system, target, {"first_name": "Changed"})["status"] == "blocked"
    assert ledger.get_entity(target).attributes["first_name"] == "Ada"


def test_blocked_write_proposals_still_enforce_scope_and_bounded_fields():
    system, mapping = setup(); imported(mapping=mapping)
    target = next(e.id for e in ledger.get_all().values() if e.entity_type == "Customer")
    for changes in ({}, {"credentials": "secret"}, {"first_name": {"nested": "data"}}, {"first_name": "x" * 1001}):
        with pytest.raises(ValueError): b.propose_write(API, system, target, changes)
    ledger.get_entity(target).attributes["workspace_id"] = "foreign"
    with pytest.raises(ValueError): b.propose_write(API, system, target, {"first_name": "Changed"})
    with pytest.raises(ValueError): b.propose_write(API, system, mapping, {"status": "approved"})
    assert not any(e.entity_type == "BridgeWriteProposal" for e in ledger.get_all().values())


def test_approved_mapping_pins_transformation_version():
    _, mapping = setup()
    definition = b.get(mapping, "BridgeMapping")
    assert definition["hash_version"] == 3 and definition["transform_version"] == 3
    job = b.stage(A, mapping, CSV)["id"]; b.validate(A, job)
    definition["transform_version"] = 1
    with pytest.raises(PermissionError): b.activate(B, job)
    assert not any(e.entity_type == "Customer" for e in ledger.get_all().values())


def test_repeated_approval_preserves_original_reviewer_evidence():
    _, mapping = setup()
    before = deepcopy(b.get(mapping, "BridgeMapping"))
    assert b.approve_mapping({**B, "employee_id": "admin-c"}, mapping)["idempotent"]
    assert b.get(mapping, "BridgeMapping") == before


def test_legacy_mapping_keeps_original_transform_semantics():
    system = b.connect(A, "CSV", "Legacy source")["id"]
    mapping = b.propose_mapping(A, system, "Vehicle", "vehicles", {
        "vin": {"source": "vin", "transform": "text"}, "year": {"source": "year", "transform": "text"}})["id"]
    definition = b.get(mapping, "BridgeMapping")
    definition["hash_version"] = 2
    definition.pop("transform_version")
    definition["hash"] = b.mapping_digest(definition)
    b.approve_mapping(B, mapping)
    # An unbound extra property cannot change a legacy mapping's algorithm.
    definition["transform_version"] = 2
    job = b.stage(A, mapping, "external_id,modified_at,vin,year\nv1,2026-01-01T00:00:00Z,1HGCM82633A004352,2026\n")["id"]
    assert b.validate(A, job)[0]["values"]["year"] == "2026"
    b.activate(B, job)


def test_legacy_customer_alias_and_vehicle_vin_dedupe():
    _, mapping = setup()
    ledger.add_entity(Entity("CUST-OLD", "Customer", {"Email": "ada@example.com"}))
    job = b.stage(A, mapping, CSV)["id"]
    assert b.validate(A, job)[0]["status"] == "quarantined"
    ledger.entities.pop("CUST-OLD")
    b.validate(A, job); b.activate(B, job)
    customer = next(e for e in ledger.get_all().values() if e.entity_type == "Customer")
    assert customer.id.startswith("CUST-") and customer.attributes["Email"] == "ada@example.com"

def test_real_auth_dependency_rejects_api_activation_and_mfa(monkeypatch):
    import api.routers.dealer_bridge as routes
    app = FastAPI(); app.include_router(router)
    client = TestClient(app)
    _, mapping = setup()
    job = b.stage(A, mapping, CSV)["id"]; b.validate(A, job)
    monkeypatch.setattr(routes, "_authenticate", lambda authorization: (A, None))
    monkeypatch.setattr(routes, "verify_token", lambda token: None)
    assert client.post(f"/dealer-bridge/imports/{job}/activate", headers={"Authorization": "Bearer api-key"}).status_code == 403
    monkeypatch.setattr(routes, "verify_token", lambda token: {**A, "purpose": "mfa_challenge"})
    assert client.post(f"/dealer-bridge/imports/{job}/activate", headers={"Authorization": "Bearer challenge"}).status_code == 403

def test_csv_sdk_uses_shared_sync_page_contract():
    from core.bridge_connectors import CsvConnector
    adapter = CsvConnector(CSV)
    page = adapter.sync("customers", None)
    assert page.complete and page.cursor is None and page.records[0].external_id == "1"
    assert "email" in adapter.schema("customers")

def test_graph_persistence_roundtrip(tmp_path, monkeypatch):
    from core.storage import save_graph
    path = str(tmp_path / "graph.json")
    monkeypatch.setattr(b, "save_graph", save_graph)
    monkeypatch.setattr(b, "GRAPH_PATH", path)
    imported()
    before = deepcopy(ledger.entities)
    ledger.reset(); ledger.load(path)
    assert ledger.entities == before


def test_historical_conflict_and_timezone_replay():
    _, mapping = setup()
    imported(mapping=mapping)
    older = CSV.replace("2026-01-01", "2025-01-01").replace("Ada,", "Old,")
    imported(older, mapping)
    imported(older.replace("2025-01-01T00:00:00Z", "2024-12-31T18:00:00-06:00"), mapping)
    assert len(b.chrono_observations(A)) == 2
    job = b.stage(A, mapping, older.replace("Old,", "Conflict,"))["id"]
    assert b.validate(A, job)[0]["status"] == "quarantined"


def candidate_job():
    _, mapping = setup()
    ledger.add_entity(Entity("CUST-EXISTING", "Customer", {"Email": "ada@example.com", "FirstName": "Original"}))
    job = b.stage(A, mapping, CSV)["id"]
    candidate = b.validate(A, job)[0]["candidate_records"][0]
    return mapping, job, candidate


def test_reviewed_link_preserves_existing_and_future_projection():
    mapping, job, candidate = candidate_job()
    b.resolve_identity(B, job, 1, candidate["id"], candidate["review_token"], "Verified dealer customer identity")
    assert b.validate(A, job)[0]["projection"] == "preserve"
    b.activate(B, job)
    assert len([e for e in ledger.get_all().values() if e.entity_type == "Customer"]) == 1
    assert ledger.get_entity(candidate["id"]).attributes["FirstName"] == "Original"
    assert b.chrono_observations(A)[0]["identity_resolution"] == "human_link_preserve_current"
    imported(CSV.replace("2026-01-01", "2027-01-01").replace("Ada,", "Updated,"), mapping)
    assert ledger.get_entity(candidate["id"]).attributes["FirstName"] == "Original"
    assert len(b.chrono_observations(A)) == 2


def test_identity_review_permissions_and_stale_tokens():
    _, job, candidate = candidate_job()
    args = (job, 1, candidate["id"], candidate["review_token"], "Verified against customer record")
    with pytest.raises(PermissionError): b.resolve_identity(API, *args)
    ledger.get_entity(candidate["id"]).attributes["FirstName"] = "Changed"
    with pytest.raises(ValueError, match="changed"): b.resolve_identity(B, *args)
    candidate = b.validate(A, job)[0]["candidate_records"][0]
    b.resolve_identity(B, job, 1, candidate["id"], candidate["review_token"], "Verified updated customer record")
    ledger.get_entity(candidate["id"]).attributes["FirstName"] = "Changed again"
    row = b.validate(A, job)[0]
    assert row["status"] == "quarantined" and row["candidate_records"]
    with pytest.raises(ValueError): b.activate(B, job)


def test_identity_review_rejects_unoffered_target_and_activated_job():
    _, job, candidate = candidate_job()
    ledger.add_entity(Entity("wrong", "Vehicle", {"Email": "ada@example.com"}))
    with pytest.raises(ValueError): b.resolve_identity(B, job, 1, "wrong", candidate["review_token"], "Verified against source")
    b.resolve_identity(B, job, 1, candidate["id"], candidate["review_token"], "Verified against source")
    b.validate(A, job); b.activate(B, job)
    with pytest.raises(ValueError): b.resolve_identity(B, job, 1, candidate["id"], candidate["review_token"], "Attempt to relink completed job")


def test_frazer_export_profile_has_no_invented_schema():
    from core.bridge_adapters.frazer import FrazerExportAdapter
    adapter = FrazerExportAdapter({"external_id": "dealer_key", "modified_at": "changed_time"})
    content = "dealer_key,changed_time,name,email\nx1,2026-01-01T00:00:00Z,Ada,ada@example.com\n"
    assert adapter.requirements()["schema_status"] == "dealer_supplied_unverified"
    assert not adapter.requirements()["live_api"]
    system = b.connect(A, "Frazer", "Dealer authorized export")["id"]
    mapping = b.propose_mapping(A, system, "Customer", "customers", {
        "first_name": {"source": "name", "transform": "text"}, "email": {"source": "email", "transform": "lower"}},
        adapter.source_columns)["id"]
    b.approve_mapping(B, mapping)
    imported(content, mapping)
    assert b.chrono_observations(A)[0]["source_id"] == "x1"
    assert b.system_map(A)["systems"][0]["health"]["status"] == "unavailable"


def test_profile_tampering_requires_new_approval():
    _, mapping = setup()
    job = b.stage(A, mapping, CSV)["id"]; b.validate(A, job)
    ledger.get_entity(mapping).attributes["source_columns"]["external_id"] = "another_id"
    with pytest.raises(PermissionError): b.activate(B, job)


def test_reserved_identity_columns_and_malformed_csv_fail_closed():
    with pytest.raises(ValueError, match="conflicts"):
        parse_csv("key,external_id,time\na,b,2026-01-01T00:00:00Z", {"external_id": "key", "modified_at": "time"})
    with pytest.raises(ValueError, match="Malformed"):
        parse_csv('external_id,modified_at\n"unclosed')
    with pytest.raises(ValueError):
        parse_csv(CSV, {"external_id": "name", "modified_at": "name"})


def test_other_workspace_candidate_is_not_offered():
    _, mapping = setup()
    ledger.add_entity(Entity("foreign", "Customer", {"email": "ada@example.com", "workspace_id": "another"}))
    job = b.stage(A, mapping, CSV)["id"]
    assert not b.validate(A, job)[0].get("candidate_records")



def test_bhph_external_references_follow_imported_source_identity():
    system, customers = setup()
    imported(mapping=customers)
    fields = {"customer_id": {"source": "customer", "transform": "external_id", "object_type": "customers"},
              "balance": {"source": "balance", "transform": "decimal"}, "currency": {"source": "currency", "transform": "upper"}}
    mapping = b.propose_mapping(A, system, "LoanAccount", "loans", fields)["id"]
    b.approve_mapping(B, mapping)
    csv = "external_id,modified_at,customer,balance,currency\nloan-1,2026-01-01T00:00:00Z,1,100.10,usd\n"
    imported(csv, mapping)
    loan = next(e for e in ledger.get_all().values() if e.entity_type == "LoanAccount")
    customer = next(e for e in ledger.get_all().values() if e.entity_type == "Customer")
    assert loan.attributes["customer_id"] == customer.id and loan.attributes["balance"] == "100.10"
    payment_fields = {"account_id": {"source": "loan", "transform": "external_id", "object_type": "loans"},
                      **{field: {"source": field, "transform": "text"} for field in ("amount", "currency", "paid_at")}}
    payments = b.propose_mapping(A, system, "Payment", "payments", payment_fields)["id"]
    b.approve_mapping(B, payments)
    imported("external_id,modified_at,loan,amount,currency,paid_at\np1,2026-01-02T00:00:00Z,loan-1,10.10,USD,2026-01-02T00:00:00Z\n", payments)
    payment = next(e for e in ledger.get_all().values() if e.entity_type == "ImportedPayment")
    assert payment.attributes["account_id"] == loan.id
    assert loan.attributes["balance"] == "100.10"  # Import is not a payment-posting command.


def test_missing_or_wrong_type_source_reference_quarantined():
    system, customers = setup()
    fields = {"customer_id": {"source": "customer", "transform": "external_id", "object_type": "customers"},
              "balance": {"source": "balance", "transform": "text"}, "currency": {"source": "currency", "transform": "text"}}
    mapping = b.propose_mapping(A, system, "LoanAccount", "loans", fields)["id"]
    csv = "external_id,modified_at,customer,balance,currency\nl1,2026-01-01T00:00:00Z,1,1,USD\n"
    job = b.stage(A, mapping, csv)["id"]
    assert b.validate(A, job)[0]["status"] == "quarantined"
    imported(mapping=customers)
    assert b.validate(A, job)[0]["status"] == "ready"
    link = next(e for e in ledger.get_all().values() if e.entity_type == "BridgeExternalID")
    link.attributes["kind"] = "Vehicle"
    assert b.validate(A, job)[0]["status"] == "quarantined"


def test_reference_lookup_never_crosses_configured_system():
    _, customers = setup(); imported(mapping=customers)
    other, _ = setup()
    fields = {"customer_id": {"source": "customer", "transform": "external_id", "object_type": "customers"},
              "balance": {"source": "balance", "transform": "text"}, "currency": {"source": "currency", "transform": "text"}}
    mapping = b.propose_mapping(A, other, "LoanAccount", "loans", fields)["id"]
    job = b.stage(A, mapping, "external_id,modified_at,customer,balance,currency\nl1,2026-01-01T00:00:00Z,1,1,USD\n")["id"]
    assert b.validate(A, job)[0]["status"] == "quarantined"



def test_edit_to_existing_target_after_preview_requires_revalidation():
    _, mapping = setup(); imported(mapping=mapping)
    job = b.stage(A, mapping, CSV.replace("2026-01-01", "2027-01-01"))["id"]
    b.validate(A, job)
    customer = next(e for e in ledger.get_all().values() if e.entity_type == "Customer")
    customer.attributes["first_name"] = "Manually updated"
    with pytest.raises(ValueError, match="Graph changed"): b.activate(B, job)
    assert ledger.get_entity(customer.id).attributes["first_name"] == "Manually updated"


def test_identity_http_review_rejects_api_and_accepts_session():
    _, job, candidate = candidate_job()
    app = FastAPI(); app.include_router(router)
    client = TestClient(app)
    body = {"row": 1, "target_id": candidate["id"], "review_token": candidate["review_token"], "reason": "Reviewed source and customer"}
    app.dependency_overrides[admin] = lambda: API
    assert client.post(f"/dealer-bridge/imports/{job}/identity-review", json=body).status_code == 403
    app.dependency_overrides[admin] = lambda: B
    assert client.post(f"/dealer-bridge/imports/{job}/identity-review", json={**body, "workspace_id": "forged"}).status_code == 422
    assert client.post(f"/dealer-bridge/imports/{job}/identity-review", json=body).json()["projection"] == "preserve"



def test_reconciliation_mismatch_blocks_activation_and_requires_new_job():
    _, mapping = setup()
    job = b.stage(A, mapping, CSV, {"row_count": 2})["id"]
    b.validate(A, job)
    report = b.import_report(A, job)
    assert report["status"] == "blocked" and report["reconciliation"]["status"] == "mismatch"
    with pytest.raises(ValueError): b.activate(B, job)
    assert not any(e.entity_type == "Customer" for e in ledger.get_all().values())
    corrected = b.stage(A, mapping, CSV, {"row_count": 1})["id"]
    b.validate(A, corrected); b.activate(B, corrected)
    assert b.import_report(A, corrected)["reconciliation"]["status"] == "matched"


def test_pause_blocks_staging_and_activation_until_human_resume():
    system, mapping = setup()
    job = b.stage(A, mapping, CSV)["id"]; b.validate(A, job)
    with pytest.raises(PermissionError): b.set_system_paused(API, system, True, "Investigating source issue")
    b.set_system_paused(B, system, True, "Investigating source issue")
    with pytest.raises(ValueError, match="paused"): b.activate(B, job)
    with pytest.raises(ValueError, match="paused"): b.stage(A, mapping, CSV)
    b.set_system_paused(B, system, False, "Source issue resolved")
    assert b.activate(B, job)["status"] == "activated"


def test_revoke_is_terminal_and_cannot_reapprove_existing_mapping():
    _, mapping = setup()
    job = b.stage(A, mapping, CSV)["id"]; b.validate(A, job)
    b.revoke_mapping(B, mapping, "Vendor changed field semantics")
    with pytest.raises(PermissionError): b.activate(B, job)
    with pytest.raises(ValueError): b.approve_mapping(B, mapping)
    with pytest.raises(ValueError): b.stage(A, mapping, CSV)
    assert b.revoke_mapping(B, mapping, "Already retired mapping")["idempotent"]


def test_cancel_is_terminal_without_deleting_source_evidence():
    _, mapping = setup()
    job = b.stage(A, mapping, CSV)["id"]
    with pytest.raises(PermissionError): b.cancel_import(API, job, "Wrong export uploaded")
    b.cancel_import(B, job, "Wrong export uploaded")
    assert b.get(job, "BridgeJob")["rows"]
    with pytest.raises(ValueError): b.validate(B, job)
    with pytest.raises(ValueError): b.activate(B, job)
    imported_job = imported(mapping=mapping)
    with pytest.raises(ValueError): b.cancel_import(B, imported_job, "Cannot undo through cancellation")


def test_expectations_tamper_after_validation_requires_new_review():
    _, mapping = setup()
    job = b.stage(A, mapping, CSV, {"row_count": 1})["id"]; b.validate(A, job)
    b.get(job, "BridgeJob")["expectations"] = {"row_count": None, "totals": []}
    with pytest.raises(ValueError, match="Staged input changed"): b.activate(B, job)
