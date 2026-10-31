"""New source versions must not be silently collapsed by datetime precision."""
import csv
import io
import json

import pytest
from core.bridge_contracts import SourceEvent, SourceRecord, SyncPage, source_timestamp, timestamp
from core.bridge_connectors import parse_export
from core.bridge_sync import page_csv
from core.bridge_adapters.adf import creation_events, inspect
from tests.test_bridge_adf_discovery import ADF


@pytest.mark.parametrize("file_format", ["csv", "tsv", "json"])
@pytest.mark.parametrize("fraction", ["1234561", "000000001"])
def test_export_intake_rejects_nonrepresentable_source_versions(file_format, fraction):
    row = {"external_id": "private-source", "modified_at": f"2026-10-04T12:00:00.{fraction}Z", "name": "Private value"}
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(row), delimiter="\t" if file_format == "tsv" else ",")
    writer.writeheader(); writer.writerow(row)
    content = json.dumps([row]) if file_format == "json" else output.getvalue()
    with pytest.raises(ValueError, match="microsecond") as error:
        parse_export("CSV", content, file_format=file_format)
    assert "private" not in str(error.value).lower()


@pytest.mark.parametrize("fraction", ["123456", "1234560", "123456000"])
def test_exact_microseconds_and_additional_zero_digits_are_preserved(fraction):
    value = f"2026-10-04T12:00:00.{fraction}Z"
    assert source_timestamp(value).microsecond == 123456
    _, rows = parse_export("CSV", f"external_id,modified_at,name\nsource,{value},Synthetic\n")
    assert rows[0]["modified_at"] == value


def test_retained_timestamp_parser_remains_compatible():
    assert timestamp("2026-10-04T12:00:00.1234567Z").microsecond == 123456
    with pytest.raises(ValueError, match="microsecond"):
        source_timestamp("2026-10-04T12:00:00,1234567Z")


def test_adf_and_event_contract_reject_submicrosecond_creation_time():
    created = "2026-10-04T10:00:00.1234567-05:00"
    content = ADF.replace("2026-10-04T10:00:00-05:00", created)
    assert inspect(content)["rows"][0]["issues"] == ["source_time_precision_requires_adapter"]
    with pytest.raises(ValueError, match="microsecond"):
        creation_events(content, id_source="Provider")
    with pytest.raises(ValueError, match="microsecond"):
        SourceEvent("leads", "id", created, "provider", "created", {"name": "Synthetic"})


def test_captured_sdk_page_rejects_lossy_version_before_csv_conversion():
    page = SyncPage((SourceRecord("customers", "id", "2026-10-04T12:00:00.1234567Z", {"name": "Synthetic"}),), None, True)
    mapping = {"object_type": "customers", "fields": {"first_name": {"source": "name", "transform": "text"}}}
    with pytest.raises(ValueError, match="microsecond"):
        page_csv(page, mapping)


@pytest.mark.parametrize("sign", ["+", "-"])
@pytest.mark.parametrize("fraction", ["5", "000001", "5000000"])
def test_fractional_timezone_offset_cannot_silently_become_utc(sign, fraction):
    value = f"2026-10-04T12:00:00{sign}00:00:00.{fraction}"
    assert timestamp(value).utcoffset().total_seconds() == 0  # Existing parser limitation.
    with pytest.raises(ValueError, match="offset loses precision"):
        source_timestamp(value)


def test_exact_fractional_offset_with_nonzero_seconds_is_not_reinterpreted():
    assert source_timestamp("2026-10-04T12:00:00+00:00:01.5").utcoffset().total_seconds() == 1.5
