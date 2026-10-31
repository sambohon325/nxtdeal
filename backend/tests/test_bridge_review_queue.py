from copy import deepcopy
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.routers.dealer_bridge import router, admin
from core import dealer_bridge as b, bridge_event_profiles as profiles, bridge_event_imports as events
from core.bridge_review_queue import read
from core.dealeros import ledger
from tests.test_dealer_bridge import A, B, API, CSV, isolated, setup  # noqa: F401
from tests.test_bridge_adf_discovery import ADF


def seed():
    system, mapping = setup()
    profile = profiles.propose(A,system,"Provider",{"first_name":{"source":"name_full","transform":"text"}})["id"]
    snapshot = b.stage(A,mapping,CSV)["id"]
    event = events.stage(API,profile,ADF)["id"]
    # Same timestamp verifies deterministic ID tie-breaking across both types.
    b.get(snapshot,"BridgeJob")["created_at"] = "2026-10-04T12:00:00Z"
    b.get(event,"BridgeEventJob")["created_at"] = "2026-10-04T12:00:00Z"
    return system, snapshot, event


def test_unified_queue_is_read_only_and_has_no_source_values():
    system, snapshot, event = seed()
    before = deepcopy(ledger.entities)
    result = read(API)
    assert {job["id"] for job in result["jobs"]} == {snapshot,event}
    assert {job["kind"] for job in result["jobs"]} == {"snapshot","event"}
    assert result["matching_jobs"] == 2 and result["status_counts"] == {"staged":2}
    assert all(job["system_id"] == system and job["row_count"] == 1 for job in result["jobs"])
    assert "Private Name" not in str(result) and "ada@example.com" not in str(result)
    assert ledger.entities == before


def test_cursor_survives_anchor_status_change_and_excludes_newer_jobs():
    system, _, _ = seed()
    first = read(A,system_id=system,limit=1)
    anchor = first["jobs"][0]
    if anchor["kind"] == "event": events.cancel(B,anchor["id"],"Synthetic queue review completed")
    else: b.cancel_import(B,anchor["id"],"Synthetic queue review completed")
    mapping = next(e.id for e in ledger.entities.values() if e.entity_type == "BridgeMapping")
    newer = b.stage(A,mapping,CSV)["id"]
    second = read(A,system_id=system,limit=1,before_id=first["next_before_id"])
    assert len(second["jobs"]) == 1 and second["jobs"][0]["id"] not in {anchor["id"],newer}
    assert second["next_before_id"] is None
    assert second["status_counts"] == {"staged":2,"cancelled":1}


def test_scope_and_type_filters_do_not_accept_foreign_cursors():
    system, snapshot, event = seed()
    other, _ = setup()
    assert [job["id"] for job in read(A,kind="event")["jobs"]] == [event]
    assert [job["id"] for job in read(A,kind="snapshot")["jobs"]] == [snapshot]
    with pytest.raises(ValueError): read(A,system_id=other,before_id=snapshot)
    with pytest.raises(ValueError): read(A,kind="event",before_id=snapshot)
    with pytest.raises(PermissionError): read({**A,"workspace_id":"foreign"})
    b.get(event,"BridgeEventJob")["workspace_id"] = "foreign"
    assert read(A)["matching_jobs"] == 1
    with pytest.raises(ValueError): read(A,before_id=event)


def test_terminal_and_cleaned_metadata_remain_findable_without_rows():
    system, snapshot, event = seed()
    events.cancel(B,event,"Synthetic cancellation")
    b.cancel_import(B,snapshot,"Synthetic cancellation")
    value = b.get(snapshot,"BridgeJob")
    value["rows"] = []
    value["payload_cleanup"] = {"row_count":1}
    assert read(A)["jobs"] == []
    result = read(A,status="cancelled")
    cleaned = next(job for job in result["jobs"] if job["id"] == snapshot)
    assert cleaned["payload_removed"] and cleaned["row_count"] == 1
    assert read(A,status="all")["matching_jobs"] == 2


@pytest.mark.parametrize("options", [{"limit":0},{"limit":101},{"limit":True},{"status":"unknown"},{"kind":"other"},{"before_id":""}])
def test_service_rejects_unbounded_or_unknown_filters(options):
    with pytest.raises(ValueError): read(A,**options)


def test_http_queue_enforces_filters_and_workspace_scope():
    seed()
    app = FastAPI(); app.include_router(router)
    app.dependency_overrides[admin] = lambda: API
    api = TestClient(app)
    assert api.get("/dealer-bridge/review-queue?kind=event&limit=1").json()["matching_jobs"] == 1
    for query in ["limit=101","status=unknown","kind=other"]:
        assert api.get("/dealer-bridge/review-queue?"+query).status_code == 422
    app.dependency_overrides[admin] = lambda: {**API,"workspace_id":"foreign"}
    assert api.get("/dealer-bridge/review-queue").status_code == 403


def test_default_pages_cover_mixed_batches_without_overlap():
    system, snapshot, event = seed()
    mapping = b.get(snapshot,"BridgeJob")["mapping_id"]
    profile = b.get(event,"BridgeEventJob")["profile_id"]
    expected = {snapshot,event}
    for index in range(51):
        job = b.stage(A,mapping,CSV) if index % 2 else events.stage(API,profile,ADF)
        expected.add(job["id"])
    seen = []
    cursor = None
    sizes = []
    while True:
        page = read(A,system_id=system,before_id=cursor)
        sizes.append(len(page["jobs"]))
        seen.extend(job["id"] for job in page["jobs"])
        cursor = page["next_before_id"]
        if cursor is None: break
        assert len(sizes) <= 3
    assert sizes == [25,25,3]
    assert len(seen) == len(set(seen)) and set(seen) == expected


def test_foreign_source_metadata_and_orphan_batches_are_excluded():
    system, snapshot, event = seed()
    b.get(system,"BridgeSystem")["workspace_id"] = "foreign"
    result = read(A,status="all")
    assert result["jobs"] == [] and result["systems"] == []
    with pytest.raises(ValueError,match="not found in this workspace"): read(A,system_id=system)
    with pytest.raises(ValueError): read(A,before_id=snapshot)
    ledger.entities.pop(system)
    assert read(A,status="all")["jobs"] == []
