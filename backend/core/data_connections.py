"""
core/data_connections.py — the integration platform behind the readiness page
(2026-07-13, session 37). Sam: "the readiness page acts as the integration platform for
dealerOS to pull data via api, csv, etc from various dealer platforms / crms / DMS's and
fill the knowledge ledger to a set point of prediction certainty... so that no dealer
has to go full deploy across the dealership at one time and it can be slowly integrated
as it learns and is fed more data."

A Connection is an ordinary graph entity (ADMIN/OPERATIONS-only, core/permissions.py)
describing one configured data source tied to a department -- not a separate
integrations database, same "one graph" rule as everything else in this codebase.

Two real connection types, honestly scoped for an environment with no live third-party
credentials:
  - "csv"  -- fully real. Uploading a file actually parses and populates the graph,
    reusing the exact same imports/*_import.py functions the seed pipeline uses (no
    second CSV-parsing implementation to drift out of sync with the real one).
  - "api"  -- real connection-config storage plus a real HTTP GET attempt
    (test_connection()) against whatever endpoint_url is configured. There is no live
    DealerSocket/CDK/PBS partnership behind this today, so testing a connection with no
    real endpoint configured will honestly fail/timeout rather than fabricate a
    successful pull -- the framework is real, the live data source isn't, and the
    status field always reflects which is true.

Once real data lands (via either path), core/prediction.py's confidence scoring reads
it directly from the underlying entities (Vehicle/ServiceRecord/FinanceContract/
PartSale/Lead) -- a Connection doesn't gate what prediction.py can see, it's just the
UI-facing record of "how did this data get here."
"""

import os
import tempfile
import urllib.request
import urllib.error
from datetime import datetime, timezone

from core.entities import Entity
from core.dealeros import ledger, id_generator
from core.entity_types import CONNECTION
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH

from imports.inventory_import import import_inventory
from imports.service_import import import_service
from imports.finance_import import import_finance
from imports.lead_import import import_leads
from imports.parts_import import import_parts, import_part_sales


VALID_CONNECTION_TYPES = ("csv", "api")

VALID_DEPARTMENTS = ("sales", "service", "finance", "parts", "marketing")

# department -> (importer function, accepts a csv_kind hint or None). Parts is the one
# department with two distinct CSV shapes (a parts catalog vs. a sales log), so its
# entry is a dict keyed by csv_kind instead of a single function.
_IMPORTERS = {
    "sales": import_inventory,
    "service": import_service,
    "finance": import_finance,
    "marketing": import_leads,
    "parts": {
        "parts": import_parts,
        "sales": import_part_sales,
    },
}


def _now():
    return datetime.now(timezone.utc).isoformat()


def create_connection(name, connection_type, department, created_by, endpoint_url=None):

    if connection_type not in VALID_CONNECTION_TYPES:
        return {"error": f"Unknown connection_type '{connection_type}' -- must be one of {VALID_CONNECTION_TYPES}"}

    if department not in VALID_DEPARTMENTS:
        return {"error": f"Unknown department '{department}' -- must be one of {VALID_DEPARTMENTS}"}

    if connection_type == "api" and not endpoint_url:
        return {"error": "endpoint_url is required for an 'api' connection"}

    connection_id = id_generator.generate("CONN")

    connection = Entity(
        id=connection_id,
        entity_type=CONNECTION,
        attributes={
            "name": name,
            "connection_type": connection_type,
            "department": department,
            "endpoint_url": endpoint_url,
            "status": "pending",
            "records_ingested": 0,
            "created_by": created_by,
            "created_at": _now(),
            "last_synced_at": None,
            "last_test_at": None,
            "last_test_result": None,
            "error_message": None,
        },
    )

    ledger.add_entity(connection)

    return {"connection": dict(connection.attributes, id=connection_id)}


def list_connections(department=None):

    connections = [
        e for e in ledger.get_all().values() if e.entity_type == CONNECTION
    ]

    if department:
        connections = [c for c in connections if c.attributes.get("department") == department]

    connections.sort(key=lambda c: c.attributes.get("created_at", ""), reverse=True)

    return [dict(c.attributes, id=c.id) for c in connections]


def get_connection(connection_id):

    connection = ledger.get_entity(connection_id)

    if not connection or connection.entity_type != CONNECTION:
        return None

    return connection


def ingest_csv(connection_id, filename, file_bytes, csv_kind=None):
    # The importer updates graph entities and legacy identity indexes together.
    # Keep both consistent if parsing, linking, or persistence fails.
    from copy import deepcopy
    from core.dealeros import registry
    from api.routers.marketing_operations import _lock
    with _lock, ledger.persistence_guard():
        entities, relationships = deepcopy(ledger.entities), deepcopy(ledger.relationships)
        indexes = {k: deepcopy(v) for k, v in vars(registry).items() if isinstance(v, dict)}
        result = _ingest_csv(connection_id, filename, file_bytes, csv_kind)
        if "error" in result:
            ledger.entities, ledger.relationships = entities, relationships
            for key, value in indexes.items():
                setattr(registry, key, value)
        return result


def _ingest_csv(connection_id, filename, file_bytes, csv_kind=None):
    """Writes the uploaded bytes to a temp file and hands it to the real importer for
    this connection's department, then persists the graph exactly once -- same
    save_graph-at-the-end convention run_seed_import.py uses. Returns
    {"records_created": n} or {"error": ...}; never raises past this function so a bad
    upload shows up as a connection status, not a 500."""

    connection = get_connection(connection_id)

    if not connection:
        return {"error": f"Connection '{connection_id}' not found"}

    if connection.attributes.get("connection_type") != "csv":
        return {"error": "This connection is not a CSV connection"}

    department = connection.attributes["department"]
    importer = _IMPORTERS.get(department)

    if isinstance(importer, dict):

        if csv_kind not in importer:
            return {
                "error": f"'{department}' requires csv_kind to be one of {list(importer.keys())}"
            }

        importer = importer[csv_kind]

    tmp_path = None

    try:
        from core.csv_mapping import mapped_csv
        file_bytes = mapped_csv(file_bytes, department, connection.attributes.get("column_mapping", {}))
        with tempfile.NamedTemporaryFile(
            mode="wb", suffix=".csv", delete=False
        ) as tmp_file:
            tmp_file.write(file_bytes)
            tmp_path = tmp_file.name

        previous_ids = set(ledger.get_all())
        result = importer(tmp_path)
        from hashlib import sha256
        from core.agent_data_bridge import record_import
        record_import(connection_id, previous_ids, sha256(file_bytes).hexdigest(), _now())

        # import_inventory returns (created, skipped); everything else returns a bare
        # count -- normalize to a single "records_created" number either way.
        records_created = result[0] if isinstance(result, tuple) else result

        connection.attributes["status"] = "connected"
        connection.attributes["records_ingested"] = (
            connection.attributes.get("records_ingested") or 0
        ) + records_created
        connection.attributes["last_synced_at"] = _now()
        connection.attributes["error_message"] = None

        save_graph(GRAPH_PATH)

        return {"records_created": records_created, "connection": dict(connection.attributes, id=connection_id)}

    except Exception as exc:

        connection.attributes["status"] = "error"
        connection.attributes["error_message"] = str(exc)

        return {"error": f"Import failed: {exc}"}

    finally:

        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_api_connection(connection_id, timeout_seconds=5):
    """A real HTTP GET attempt against connection.endpoint_url -- honestly reports
    success or failure rather than fabricating a pull. There is no live DealerSocket/
    CDK/PBS partnership behind this environment, so most real attempts here will
    legitimately fail (unknown host, refused connection, etc.) until pointed at a real
    endpoint with real credentials in a future session -- that failure is the correct,
    honest behavior, not a bug."""

    connection = get_connection(connection_id)

    if not connection:
        return {"error": f"Connection '{connection_id}' not found"}

    if connection.attributes.get("connection_type") != "api":
        return {"error": "This connection is not an API connection"}

    url = connection.attributes.get("endpoint_url")

    try:
        from core.outbound_http import probe_public_https
        status_code = probe_public_https(url, timeout=timeout_seconds)

        connection.attributes["status"] = "connected"
        connection.attributes["last_test_result"] = f"HTTP {status_code}"
        connection.attributes["error_message"] = None

    except Exception as exc:

        connection.attributes["status"] = "error"
        connection.attributes["last_test_result"] = None
        connection.attributes["error_message"] = str(exc)

    connection.attributes["last_test_at"] = _now()

    return {"connection": dict(connection.attributes, id=connection_id)}
