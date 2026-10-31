from copy import deepcopy
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from core import bridge_chrono as outbox, bridge_chrono_review as review
from core.dealeros import ledger
from core.entities import Entity
from api.routers.dealer_bridge import router, admin
from tests.test_bridge_chrono import A, B, API, FakeSink, enabled, isolated  # noqa: F401


def failed():
    events, sink = enabled()
    sink.failure = ValueError("private provider payload")
    outbox.deliver_once(A)
    return events, sink


def test_read_is_metadata_only_without_delivery_or_mutations():
    events,sink = failed()
    before = deepcopy(ledger.entities)
    result = review.read(API)
    assert len(result["receipts"]) == 2 and result["matching_receipts"] == 2
    assert result["status_counts"] == {"blocked":2}
    assert all(item["retry_available"] for item in result["receipts"])
    assert all(word not in str(result) for word in ("Ada","Grace","lease_token","private provider payload"))
    assert ledger.entities == before and len(sink.calls) == 1


def test_cursor_survives_retry_and_acknowledgement():
    events,sink = failed()
    first = review.read(A,limit=1)
    row = first["receipts"][0]
    outbox.retry(B,row["event_id"],"Reviewed synthetic delivery failure",row["id"])
    sink.failure = None
    outbox.deliver_once(B)
    second = review.read(A,before_id=first["next_before_id"],limit=1)
    assert second["matching_receipts"] == 1
    assert second["receipts"][0]["event_id"] != row["event_id"]
    assert second["next_before_id"] is None


def test_policy_revision_change_rejects_stale_cursor_and_retry():
    events,sink = failed()
    row = review.read(A,limit=1)["receipts"][0]
    other = FakeSink(); other.failure = ValueError("synthetic")
    outbox.bind_sink("test-sink","v2",other)
    outbox.configure(B,True,"test-sink","v2")
    outbox.deliver_once(B)
    before = deepcopy(ledger.entities)
    with pytest.raises(ValueError,match="destination"): review.read(A,before_id=row["id"])
    with pytest.raises(ValueError,match="destination changed"):
        outbox.retry(B,row["event_id"],"Reviewed old destination receipt",row["id"])
    assert ledger.entities == before


def test_unattempted_events_have_no_receipts_and_disabled_policy_cannot_retry():
    events,sink = enabled()
    assert review.read(A)["receipts"] == []
    sink.failure = TimeoutError()
    outbox.deliver_once(A)
    outbox.configure(B,False)
    result = review.read(A)
    assert result["effective_status"] == "disabled"
    assert not any(row["retry_available"] for row in result["receipts"])


def test_lease_is_not_retryable_and_unknown_records_are_excluded():
    events,sink = failed()
    from datetime import timedelta
    row = review.read(A)["receipts"][0]
    ledger.get_entity(row["id"]).attributes.update(status="in_flight",lease_until=(outbox.utcnow()+timedelta(minutes=2)).isoformat())
    assert not next(item for item in review.read(A)["receipts"] if item["id"] == row["id"])["retry_available"]
    copied = deepcopy(ledger.get_entity(row["id"]).attributes)
    ledger.entities["forged"] = Entity("forged","BridgeChronoDelivery",copied)
    ledger.get_entity(events[1]).attributes["workspace_id"] = "foreign"
    result = review.read(A,status="all")
    assert len(result["receipts"]) == 1 and result["excluded_receipts"] == 2
    with pytest.raises(PermissionError): review.read({**A,"workspace_id":"foreign"})


@pytest.mark.parametrize("options", [{"limit":0},{"limit":101},{"limit":True},{"status":"pending"},{"before_id":""}])
def test_invalid_filters(options):
    with pytest.raises(ValueError): review.read(A,**options)


def test_http_scopes_and_receipt_fenced_retry():
    failed()
    app=FastAPI();app.include_router(router);app.dependency_overrides[admin]=lambda:B
    api=TestClient(app)
    row=api.get("/dealer-bridge/chrono/receipt-queue?limit=1").json()["receipts"][0]
    assert api.get("/dealer-bridge/chrono/receipt-queue?limit=101").status_code == 422
    response=api.post(f"/dealer-bridge/chrono/observations/{row['event_id']}/retry",json={"reason":"Reviewed synthetic receipt","receipt_id":row["id"]})
    assert response.status_code == 200
    app.dependency_overrides[admin]=lambda:API
    assert api.post(f"/dealer-bridge/chrono/observations/{row['event_id']}/retry",json={"reason":"API must not authorize retry","receipt_id":row["id"]}).status_code == 403


def test_more_than_legacy_receipt_window_remains_reviewable():
    from core import dealer_bridge as bridge
    events,sink = enabled()
    mapping=next(e.id for e in ledger.entities.values() if e.entity_type=="BridgeMapping")
    csv="external_id,modified_at,name\n"+"".join(f"extra-{i},2026-01-01T00:00:00Z,Synthetic {i}\n" for i in range(203))
    job=bridge.stage(A,mapping,csv)["id"]
    bridge.validate(A,job);bridge.activate(B,job)
    sink.failure=ValueError("synthetic failure")
    for _ in range(3):outbox.deliver_once(A,limit=100)
    assert len(outbox.receipts(A))==200
    seen=[];cursor=None;sizes=[]
    while True:
        result=review.read(A,limit=25,before_id=cursor)
        sizes.append(len(result["receipts"]))
        seen.extend(row["event_id"] for row in result["receipts"])
        cursor=result["next_before_id"]
        if cursor is None:break
        assert len(sizes)<=9
    assert sizes==[25]*8+[5]
    assert len(seen)==len(set(seen))==205 and set(events)<=set(seen)
