"""Batch validation stays bounded and never caches identity decisions across calls."""
import pytest

from core import dealer_bridge as b
from core.bridge_indexes import ValidationIndex
from core.dealeros import ledger
from core.entities import Entity
from tests.test_dealer_bridge import A, B, CSV, setup, imported, isolated  # noqa: F401


def test_large_import_uses_bounded_graph_enumeration(monkeypatch):
    _, mapping_id = setup()
    for number in range(2000):
        ledger.add_entity(Entity(f"existing-{number}", "Customer", {"Email": f"other{number}@example.invalid"}))
    rows = "external_id,modified_at,name,email\n" + "".join(
        f"{number},2026-01-01T00:00:00Z,Customer {number},new{number}@example.invalid\n"
        for number in range(1000))
    job_id = b.stage(A, mapping_id, rows)["id"]
    original = ledger.get_all
    reads = []

    def counted():
        reads.append(True)
        return original()

    monkeypatch.setattr(ledger, "get_all", counted)
    preview = b.validate(A, job_id)
    assert len(preview) == 1000 and all(row["status"] == "ready" for row in preview)
    assert len(reads) <= 3, "Validation must not enumerate the full graph per row"


def test_candidates_include_both_aliases_once_in_repository_order():
    index = ValidationIndex([
        Entity("second", "Customer", {"email": "new@example.invalid", "Email": " OLD@example.invalid "}),
        Entity("first", "Customer", {"email": "old@example.invalid", "Email": "old@example.invalid"}),
        Entity("foreign", "Customer", {"email": "old@example.invalid", "workspace_id": "other"}),
        Entity("lead", "Lead", {"email": "old@example.invalid"}),
    ], "here", "Customer")
    assert index.candidates({"email": "OLD@example.invalid"}) == ["second", "first"]
    assert index.candidates({"email": "new@example.invalid"}) == ["second"]


def test_activation_rebuilds_index_and_detects_new_candidate():
    _, mapping_id = setup()
    job_id = b.stage(A, mapping_id, CSV)["id"]
    assert b.validate(A, job_id)[0]["status"] == "ready"
    ledger.add_entity(Entity("new-candidate", "Customer", {"Email": "ada@example.com"}))
    with pytest.raises(ValueError, match="Graph changed"):
        b.activate(B, job_id)
    assert b.validate(A, job_id)[0]["candidates"] == ["new-candidate"]


def test_history_index_matches_timezone_equivalent_timestamp_and_workspace():
    workspace = ledger.tenant.workspace_id
    def event(record_id, key, source_time, values, tenant=workspace):
        return Entity(record_id, "SourceObservation", {"workspace_id": tenant, "external_key": key,
            "source_timestamp": source_time, "values": values})
    index = ValidationIndex([
        event("one", "key", "2026-01-01T00:00:00Z", {"name": "one"}),
        event("foreign", "key", "2026-01-01T00:00:00Z", {"name": "foreign"}, "other"),
        event("irrelevant", "elsewhere", "not-a-timestamp", {"name": "elsewhere"}),
    ], workspace, "Customer", ["key"])
    assert index.historical_values("key", "2025-12-31T18:00:00-06:00") == [{"name": "one"}]
    assert index.historical_values("key", "2026-01-02T00:00:00Z") == []


def test_historical_conflict_still_blocks_after_newer_projection():
    _, mapping_id = setup()
    imported(CSV, mapping_id)
    imported(CSV.replace("2026-01-01", "2026-02-01").replace("Ada,", "Current,"), mapping_id)
    job_id = b.stage(A, mapping_id, CSV.replace("Ada,", "Conflict,"))["id"]
    row = b.validate(A, job_id)[0]
    assert row["status"] == "quarantined"
    assert "historical payload" in row["errors"][0]



@pytest.mark.parametrize("left,right", [("straße@example.invalid", "STRASSE@example.invalid"), ("σ@example.invalid", "ς@example.invalid")])
def test_batch_and_existing_candidates_share_unicode_normalization(left, right):
    _, mapping = setup()
    content = f"external_id,modified_at,name,email\none,2026-01-01T00:00:00Z,First,{left}\ntwo,2026-01-01T00:00:00Z,Second,{right}\n"
    job = b.stage(A, mapping, content)["id"]
    rows = b.validate(A, job)
    assert rows[1]["status"] == "quarantined"
    assert "duplicate within batch" in rows[1]["errors"][0]
    assert b.get(job, "BridgeJob")["status"] == "blocked"
    with pytest.raises(ValueError):
        b.activate(B, job)
    assert not any(e.entity_type == "Customer" for e in ledger.entities.values())
    index = ValidationIndex([Entity("existing", "Customer", {"Email": left})], ledger.tenant.workspace_id, "Customer")
    assert index.candidates({"email": right}) == ["existing"]


def test_normalization_is_candidate_detection_not_source_value_rewriting():
    _, mapping = setup()
    content = "external_id,modified_at,name,email\none,2026-01-01T00:00:00Z,Example,straße@example.invalid\n"
    job = b.stage(A, mapping, content)["id"]
    row = b.validate(A, job)[0]
    assert row["values"]["email"] == "straße@example.invalid"
    b.activate(B, job)
    customer = next(e for e in ledger.entities.values() if e.entity_type == "Customer")
    assert customer.attributes["email"] == "straße@example.invalid"
