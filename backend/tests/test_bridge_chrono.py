from copy import deepcopy
from datetime import timedelta
import pytest

from chrono.delivery import DeliveryReceipt
from core import dealer_bridge as b, bridge_chrono as outbox
from core.dealeros import ledger

A = {"employee_id": "admin-a", "role": "ADMIN", "bridge_principal": "session"}
B = {"employee_id": "admin-b", "role": "ADMIN", "bridge_principal": "session"}
API = {**A, "bridge_principal": "api"}


class FakeSink:
    supports_idempotency = True
    def __init__(self):
        self.accepted = set()
        self.calls = []
        self.failure = None
        self.receipt = None
        self.during_send = None
    def deliver(self, *, workspace_id, events):
        self.calls.append((workspace_id, events))
        if self.during_send:
            self.during_send()
        if self.failure:
            raise self.failure
        self.accepted.update(event.event_id for event in events)
        return self.receipt or DeliveryReceipt(tuple(event.event_id for event in events))


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    previous = ledger.entities, ledger.relationships, outbox._BINDING
    ledger.entities, ledger.relationships = {}, []
    outbox.unbind_sink()
    monkeypatch.setattr(b, "save_graph", lambda path: None)
    monkeypatch.setattr(outbox.credential_store, "get_record", lambda employee: {"role": "ADMIN"})
    yield
    ledger.entities, ledger.relationships, outbox._BINDING = previous


def observations():
    system = b.connect(A, "CSV", "Source")["id"]
    mapping = b.propose_mapping(A, system, "Customer", "customers", {"first_name": {"source": "name", "transform": "text"}})["id"]
    b.approve_mapping(B, mapping)
    job = b.stage(A, mapping, "external_id,modified_at,name\n1,2026-01-01T00:00:00Z,Ada\n2,2026-01-01T00:00:00Z,Grace\n")["id"]
    b.validate(A, job); b.activate(B, job)
    return [value["event_id"] for value in b.chrono_observations(A)]


def enabled():
    events = observations()
    sink = FakeSink()
    outbox.bind_sink("test-sink", "v1", sink)
    outbox.configure(A, True, "test-sink", "v1")
    return events, sink


def test_no_binding_or_policy_means_no_delivery():
    observations()
    assert outbox.deliver_once(A)["status"] == "disabled"
    with pytest.raises(ValueError): outbox.configure(A, True, "imaginary", "v1")
    assert not outbox.receipts(A)


def test_active_sink_cannot_be_silently_replaced_under_same_approval():
    _, sink = enabled()
    binding = outbox._BINDING
    outbox.bind_sink("test-sink", "v1", sink)
    assert outbox._BINDING is binding
    replacement = FakeSink()
    with pytest.raises(ValueError, match="new revision"):
        outbox.bind_sink("test-sink", "v1", replacement)
    assert outbox._BINDING is binding and replacement.calls == []
    outbox.bind_sink("test-sink", "v2", replacement)
    with pytest.raises(ValueError):
        outbox.deliver_once(A)
    assert replacement.calls == []


def test_receipts_are_separate_from_immutable_observations():
    events, sink = enabled()
    snapshots = {event: deepcopy(ledger.get_entity(event).attributes) for event in events}
    assert outbox.deliver_once(A)["delivered"] == 2
    assert outbox.deliver_once(A)["status"] == "idle" and len(sink.calls) == 1
    assert all(ledger.get_entity(event).attributes == snapshots[event] for event in events)
    assert all(item["delivery_status"] == "delivered" for item in b.chrono_observations(A))
    assert outbox.status(A)["counts"] == {"delivered": 2}
    payload = sink.calls[0][1][0]
    source = ledger.get_entity(payload.event_id).attributes
    assert payload.provenance == {"connector_instance_id": source["system_id"], "source_object": "customers",
        "mapping_revision_id": source["mapping_id"], "external_identity_key": source["external_key"],
        "canonical_kind": "Customer", "origin": "dealer_bridge"}


def test_partial_acknowledgement_only_completes_named_events():
    events, sink = enabled()
    sink.receipt = DeliveryReceipt((events[0],), retryable=True)
    assert outbox.deliver_once(A)["delivered"] == 1
    states = {record["event_id"]: record["status"] for record in outbox.receipts(A)}
    assert states == {events[0]: "delivered", events[1]: "retrying"}


def test_invalid_acknowledgement_blocks_without_trusting_foreign_ids():
    events, sink = enabled()
    sink.receipt = DeliveryReceipt(("foreign-event",))
    assert outbox.deliver_once(A)["delivered"] == 0
    assert all(record["status"] == "blocked" for record in outbox.receipts(A))


@pytest.mark.parametrize("invalid", ["too_many", "oversized_id", "duplicate", "not_tuple", "invalid_retry"])
def test_invalid_receipt_shapes_never_acknowledge_or_retain_payloads(invalid):
    events, sink = enabled()
    ids = {"too_many": tuple(events) + ("private-response",),
           "oversized_id": ("private-response" * 100,),
           "duplicate": (events[0], events[0]),
           "not_tuple": list(events), "invalid_retry": tuple(events)}[invalid]
    sink.receipt = DeliveryReceipt(ids, retryable="true" if invalid == "invalid_retry" else True)
    assert outbox.deliver_once(A)["delivered"] == 0
    records = outbox.receipts(A)
    assert len(records) == 2 and all(record["status"] == "blocked" for record in records)
    assert "private-response" not in str(records)


def test_oversized_receipt_is_rejected_before_iterating_adapter_values():
    traversed = []
    class OversizedReceipt(tuple):
        def __iter__(self):
            traversed.append(True)
            raise AssertionError("Oversized receipts must not be traversed")
    _, sink = enabled()
    sink.receipt = DeliveryReceipt(OversizedReceipt(("a", "b", "c")))
    assert outbox.deliver_once(A)["delivered"] == 0
    assert traversed == []
    assert all(record["status"] == "blocked" for record in outbox.receipts(A))


def test_timeout_retries_stable_event_ids_with_backoff(monkeypatch):
    events, sink = enabled()
    sink.failure = TimeoutError("secret credential and raw customer response")
    assert outbox.deliver_once(A)["delivered"] == 0
    assert outbox.deliver_once(A)["status"] == "idle"
    assert "secret" not in str(outbox.receipts(A))
    later = outbox.utcnow() + timedelta(minutes=10)
    monkeypatch.setattr(outbox, "utcnow", lambda: later)
    sink.failure = None
    assert outbox.deliver_once(A)["delivered"] == 2
    assert {event.event_id for event in sink.calls[0][1]} == {event.event_id for event in sink.calls[1][1]} == set(events)


def test_ack_save_failure_recovers_by_idempotent_redelivery(monkeypatch):
    events, sink = enabled()
    count = []
    def save(path):
        count.append(path)
        if len(count) == 2:
            raise OSError("failed acknowledgement persistence")
    monkeypatch.setattr(b, "save_graph", save)
    with pytest.raises(OSError): outbox.deliver_once(A)
    assert all(record["status"] == "in_flight" for record in outbox.receipts(A))
    later = outbox.utcnow() + timedelta(minutes=10)
    monkeypatch.setattr(outbox, "utcnow", lambda: later)
    assert outbox.deliver_once(A)["delivered"] == 2
    assert sink.accepted == set(events)


def test_policy_change_during_send_records_factual_receipt_but_stops_next_send():
    events, sink = enabled()
    sink.during_send = lambda: outbox.configure(B, False)
    assert outbox.deliver_once(A)["delivered"] == 2
    assert outbox.deliver_once(A)["status"] == "disabled"
    assert outbox.status(A)["counts"] == {"delivered": 2}


def test_rebinding_requires_human_policy_review_and_cannot_share_receipts():
    events, sink = enabled()
    outbox.deliver_once(A)
    replacement = FakeSink()
    outbox.bind_sink("test-sink", "v2", replacement)
    with pytest.raises(ValueError): outbox.deliver_once(A)
    with pytest.raises(PermissionError): outbox.configure(API, True, "test-sink", "v2")
    outbox.configure(B, True, "test-sink", "v2")
    assert outbox.deliver_once(B)["delivered"] == 2
    assert replacement.accepted == set(events)


def test_disabled_authorizer_and_api_call_cannot_dispatch(monkeypatch):
    events, sink = enabled()
    with pytest.raises(PermissionError): outbox.deliver_once(API)
    monkeypatch.setattr(outbox.credential_store, "get_record", lambda employee: {"role": "SALES"})
    assert outbox.tick()["status"] == "authorization_or_binding_unavailable"
    assert sink.calls == []


def test_sink_must_declare_durable_deduplication():
    sink = FakeSink(); sink.supports_idempotency = False
    with pytest.raises(ValueError): outbox.bind_sink("unsafe", "v1", sink)


def test_concurrent_drainers_cannot_send_same_leased_batch():
    events, sink = enabled()
    other = []
    sink.during_send = lambda: other.append(outbox.deliver_once(B))
    assert outbox.deliver_once(A)["delivered"] == 2
    assert other == [{"status": "idle", "delivered": 0}]


def test_demo_without_durable_storage_never_delivers(monkeypatch):
    _, sink = enabled()
    monkeypatch.setenv("DEALEROS_DEMO", "true")
    with pytest.raises(ValueError, match="Durable storage"): outbox.deliver_once(A)
    assert outbox.status(A)["effective_status"] == "review_required"
    assert sink.calls == []
    assert outbox.configure(A, False)["enabled"] is False
