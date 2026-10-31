"""
Tests for core/data_connections.py / core/data_connections_api.py -- the integration
platform behind the readiness page (session 37). Run from backend/ with `pytest`.

save_graph is monkeypatched to a no-op everywhere in this file -- ingest_csv() calling
the real importer functions is exactly what's under test, but persisting to the real
backend/storage/graph.json on whatever machine runs these tests is not.
"""

import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

import pytest

from core.dealeros import ledger
from core import data_connections
from core import data_connections_api
from core.permissions import ADMIN, OPERATIONS, SALES


@pytest.fixture(autouse=True)
def fresh_ledger(monkeypatch):

    ledger.reset()
    monkeypatch.setattr(data_connections, "save_graph", lambda path: None)

    yield

    ledger.reset()


LEADS_CSV = (
    "LeadID,VIN,Status,CreatedDate\n"
    "L9001,,New,2026-07-01\n"
    "L9002,,New,2026-07-02\n"
)


def test_create_connection_validates_type():

    result = data_connections.create_connection(
        "Bad Source", "not-a-type", "marketing", "EMP-00001"
    )
    assert "error" in result


def test_create_connection_validates_department():

    result = data_connections.create_connection(
        "Bad Source", "csv", "not-a-department", "EMP-00001"
    )
    assert "error" in result


def test_create_connection_api_requires_endpoint_url():

    result = data_connections.create_connection(
        "My API", "api", "sales", "EMP-00001"
    )
    assert "error" in result


def test_create_and_list_connection():

    created = data_connections.create_connection(
        "Marketing CSV Feed", "csv", "marketing", "EMP-00001"
    )
    assert "connection" in created

    connections = data_connections.list_connections()
    assert any(c["id"] == created["connection"]["id"] for c in connections)


def test_list_connections_filters_by_department():

    data_connections.create_connection("Sales Feed", "csv", "sales", "EMP-00001")
    data_connections.create_connection("Marketing Feed", "csv", "marketing", "EMP-00001")

    sales_only = data_connections.list_connections(department="sales")
    assert all(c["department"] == "sales" for c in sales_only)
    assert len(sales_only) == 1


def test_ingest_csv_real_import_creates_leads():

    created = data_connections.create_connection(
        "Marketing CSV Feed", "csv", "marketing", "EMP-00001"
    )
    connection_id = created["connection"]["id"]

    result = data_connections.ingest_csv(
        connection_id, "leads.csv", LEADS_CSV.encode("utf-8")
    )

    assert result["records_created"] == 2
    assert result["connection"]["status"] == "connected"
    assert result["connection"]["records_ingested"] == 2


def test_ingest_csv_unknown_connection_errors():

    result = data_connections.ingest_csv("CONN-99999", "x.csv", b"a,b\n1,2\n")
    assert "error" in result


def test_ingest_csv_wrong_connection_type_errors():

    created = data_connections.create_connection(
        "API Feed", "api", "sales", "EMP-00001", endpoint_url="https://example.invalid/api"
    )
    connection_id = created["connection"]["id"]

    result = data_connections.ingest_csv(connection_id, "x.csv", b"a,b\n1,2\n")
    assert "error" in result


def test_ingest_csv_parts_requires_csv_kind():

    created = data_connections.create_connection(
        "Parts Feed", "csv", "parts", "EMP-00001"
    )
    connection_id = created["connection"]["id"]

    result = data_connections.ingest_csv(connection_id, "parts.csv", b"a,b\n1,2\n")
    assert "error" in result


def test_test_api_connection_reports_real_failure_for_bad_host():

    created = data_connections.create_connection(
        "Broken API", "api", "sales", "EMP-00001",
        endpoint_url="http://this-host-does-not-exist.invalid/"
    )
    connection_id = created["connection"]["id"]

    result = data_connections.test_api_connection(connection_id, timeout_seconds=2)

    assert result["connection"]["status"] == "error"
    assert result["connection"]["error_message"]


def test_test_api_connection_wrong_type_errors():

    created = data_connections.create_connection(
        "CSV Feed", "csv", "sales", "EMP-00001"
    )
    connection_id = created["connection"]["id"]

    result = data_connections.test_api_connection(connection_id)
    assert "error" in result


# ---------------------------------------------------------------------------
# ACL
# ---------------------------------------------------------------------------

def test_create_connection_api_denied_for_sales_role():

    result = data_connections_api.create_connection_api(
        SALES, "Feed", "csv", "sales", "EMP-00001"
    )
    assert "error" in result


def test_create_connection_api_allowed_for_admin_and_operations():

    for role in (ADMIN, OPERATIONS):
        result = data_connections_api.create_connection_api(
            role, "Feed", "csv", "sales", "EMP-00001"
        )
        assert "connection" in result


def test_readiness_predictions_api_open_to_any_role():

    result = data_connections_api.readiness_predictions_api()
    assert "departments" in result
    assert len(result["departments"]) == len(data_connections_api.DEPARTMENTS)
