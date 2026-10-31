from dataclasses import asdict

import pytest
from core.bridge_adapters.adf import creation_events
from core.bridge_contracts import SourceEvent
from tests.test_bridge_adf_discovery import ADF


def test_selected_provider_and_creation_time_are_preserved_without_modified_time():
    content = ADF.replace('<id source="Provider">', '<id source="Another">ignore-this-id</id><id source="Provider">')
    events = creation_events(content, id_source="Provider")
    assert len(events) == 1
    event = events[0]
    assert event.external_id == "private-id" and event.source_namespace == "Provider"
    assert event.time_semantics == "created" and event.occurred_at == "2026-10-04T10:00:00-05:00"
    assert "modified_at" not in asdict(event)
    assert event.values == {"name_full": "Private Name", "email": "private@example.com"}
    assert "consent" not in event.values and "status" not in event.values


def test_resends_do_not_fabricate_modification_time():
    assert creation_events(ADF, id_source="Provider") == creation_events(ADF.replace('<prospect>', '<prospect status="resend">'), id_source="Provider")


@pytest.mark.parametrize("content", [
    ADF.replace('<id source="Provider">private-id</id>', ''),
    ADF.replace('</prospect>', '<id source="Provider">other-id</id></prospect>'),
    ADF.replace('</customer>', '<contact/></customer>'),
    ADF.replace('</contact>', '<email>another@example.com</email></contact>'),
    ADF.replace('2026-10-04T10:00:00-05:00', '2026-10-04T10:00:00'),
    ADF.replace('<name part="full">Private Name</name>', '<name part="full"><nested/></name>'),
], ids=['missing-id', 'duplicate-id', 'contacts', 'emails', 'naive-time', 'nested-name'])
def test_ambiguous_drafts_fail_as_a_whole_without_echoing_source_values(content):
    with pytest.raises(ValueError) as error:
        creation_events(content, id_source="Provider")
    assert "private-id" not in str(error.value) and "example.com" not in str(error.value)


@pytest.mark.parametrize("provider", ['', ' Provider', None, 'x' * 121])
def test_provider_namespace_is_explicit(provider):
    with pytest.raises(ValueError):
        creation_events(ADF, id_source=provider)


@pytest.mark.parametrize("change", [
    {"time_semantics": "modified"}, {"time_semantics": []}, {"source_namespace": ""},
    {"external_id": "bad\nidentity"}, {"occurred_at": "2026-01-01"},
    {"values": {"nested": {"a": "b"}}}, {"values": {}},
])
def test_event_contract_rejects_ambiguous_or_unbounded_inputs(change):
    fields = dict(object_type="leads", external_id="1", occurred_at="2026-01-01T00:00:00Z", source_namespace="provider", time_semantics="created", values={"name": "Synthetic"})
    with pytest.raises(ValueError):
        SourceEvent(**{**fields, **change})


def test_creation_events_cannot_enter_snapshot_collector():
    from core.bridge_contracts import SyncPage
    from core.bridge_sync import page_csv
    events = creation_events(ADF, id_source="Provider")
    mapping = {"object_type": "adf_prospects", "fields": {"email": {"source": "email", "transform": "text"}}}
    with pytest.raises(ValueError, match="source record"):
        page_csv(SyncPage(events, None, True), mapping)


@pytest.mark.parametrize("values", [{"name": chr(0xd800)}, {"field" + str(i): "x" * 100000 for i in range(11)}], ids=["unicode", "aggregate-size"])
def test_event_drafts_enforce_aggregate_utf8_limits(values):
    with pytest.raises(ValueError):
        SourceEvent("leads", "1", "2026-01-01T00:00:00Z", "provider", "created", values)
