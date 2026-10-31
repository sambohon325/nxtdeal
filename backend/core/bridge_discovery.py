"""Data-minimal CSV and bound-connector discovery. Suggestions remain drafts."""
import re
from core import dealer_bridge as bridge
from core.bridge_connectors import inspect_file
from core.bridge_contracts import FIELDS, REQUIRED, REFERENCE_TYPES, DECIMAL_FIELDS


def normalized(value):
    return re.sub(r"[^a-z0-9]", "", value.lower())


def discover_file(actor, system_id, kind, content, file_format="csv"):
    bridge.authorize(actor)
    with bridge.LOCK:
        bridge.get(system_id, "BridgeSystem")
    if kind not in FIELDS:
        raise ValueError("Known canonical type required")
    headers, rows = inspect_file(content, file_format)
    return {**header_suggestions(kind, headers), "row_count": len(rows),
        "columns": [{"name": header, "populated_rows": sum(bool(row[header].strip()) for row in rows)} for header in headers],
        "transport": "manual_upload", "file_format": file_format}


def header_suggestions(kind, headers):
    """Only neutral field-name matches; no values or vendor synonyms are inferred."""
    if kind not in FIELDS:
        raise ValueError("Known canonical type required")
    suggestions, ambiguous = {}, []
    for field in FIELDS[kind]:
        matching = [header for header in headers if normalized(header) == normalized(field)]
        if len(matching) == 1:
            suggestions[field] = {"source": matching[0], "transform": "decimal" if field in DECIMAL_FIELDS else "text"}
        elif matching:
            ambiguous.append(field)
    # Source identity roles are suggested only for exact neutral role names.
    # Vendor-specific synonyms, relationship namespaces and semantics need review.
    source_columns = {}
    for role in ("external_id", "modified_at"):
        matching = [header for header in headers if normalized(header) == normalized(role)]
        if len(matching) == 1:
            source_columns[role] = matching[0]
    return {"headers": headers, "schema_hash": bridge.digest(sorted(headers)),
        "suggestions": suggestions, "ambiguous_fields": ambiguous, "source_columns": source_columns,
        "required_fields": sorted(REQUIRED.get(kind, set())),
        "reference_fields": {field: REFERENCE_TYPES[field] for field in FIELDS[kind] if field in REFERENCE_TYPES},
        "status": "review_required", "stored": False,
        "notice": "Suggestions match header names only. Confirm source identity, timestamps and relationship meanings before proposing."}


def discover_bound_schema(actor, system_id, kind, object_type):
    """Inspect only an operator-allowlisted object; never run sync/auth/write.

    Adapters return a flattened list of column names, not a vendor response or
    sample record. IO is outside the graph lock and results are fenced against
    unbinding, replacement, pause or workspace changes while the call ran.
    """
    from core import bridge_runtime as runtime
    bridge.authorize(actor)
    if kind not in FIELDS:
        raise ValueError("Known canonical type required")
    with bridge.LOCK:
        bridge.require_durable_state()
        system = bridge.get(system_id, "BridgeSystem")
        bound = runtime.binding(system_id)
        if system.get("paused"):
            raise ValueError("System is paused")
        if object_type not in bound.objects or "schema" not in bound.capabilities:
            raise ValueError("Source object or schema inspection is not authorized for this connector")
    try:
        headers = bound.adapter.schema(object_type)
    except Exception:
        # Vendor messages may contain credentials, URLs or sample customer data.
        raise ValueError("Connector schema inspection failed; check the authorized adapter configuration") from None
    if (not isinstance(headers, (list, tuple)) or not headers or len(headers) > 100 or
            any(not isinstance(header, str) or not header.strip() or len(header) > 120 or
                any(ord(char) < 32 for char in header) for header in headers) or len(set(headers)) != len(headers)):
        raise ValueError("Connector must return up to 100 unique bounded column names without row values")
    headers = list(headers)
    with bridge.LOCK:
        bridge.authorize(actor)
        bridge.require_durable_state()
        system = bridge.get(system_id, "BridgeSystem")
        if system.get("paused") or runtime.binding(system_id) is not bound:
            raise ValueError("Connector configuration changed during discovery; inspect again")
    return {**header_suggestions(kind, headers), "row_count": None,
        "columns": [{"name": header} for header in headers], "transport": "bound_connector",
        "object_type": object_type, "binding_revision": bound.revision, "environment": bound.environment}


def discover_adf(actor, system_id, content):
    """Inspect authorized ADF structure without persisting lead values."""
    from core.bridge_adapters.adf import inspect
    bridge.authorize(actor)
    with bridge.LOCK:
        bridge.get(system_id, "BridgeSystem")
    return inspect(content)



def discover_bound_objects(actor, system_id):
    """Return only discovered object names already in the operator's allowlist."""
    from core import bridge_runtime as runtime
    bridge.authorize(actor)
    with bridge.LOCK:
        bridge.require_durable_state()
        system = bridge.get(system_id, "BridgeSystem")
        bound = runtime.binding(system_id)
        if system.get("paused"):
            raise ValueError("System is paused")
        if "discover" not in bound.capabilities:
            raise ValueError("Object discovery is not implemented by this connector")
    try:
        objects = bound.adapter.discover()
    except Exception:
        raise ValueError("Connector object discovery failed; check the authorized adapter configuration") from None
    if (not isinstance(objects, (list, tuple)) or len(objects) > 100 or
            any(not isinstance(item, str) or not item.strip() or item != item.strip() or len(item) > 120 or
                any(ord(char) < 32 for char in item) for item in objects) or len(set(objects)) != len(objects)):
        raise ValueError("Connector must return at most 100 unique bounded object names without values")
    reported = frozenset(objects)
    with bridge.LOCK:
        bridge.authorize(actor)
        bridge.require_durable_state()
        system = bridge.get(system_id, "BridgeSystem")
        if system.get("paused") or runtime.binding(system_id) is not bound:
            raise ValueError("Connector configuration changed during discovery; inspect again")
    available = sorted(reported & bound.objects)
    missing = sorted(bound.objects - reported)
    return {"system_id": system_id, "objects": available, "authorized_not_reported": missing,
            "binding_revision": bound.revision, "environment": bound.environment,
            "schema_inspection_available": "schema" in bound.capabilities,
            "discovery_hash": bridge.digest([available, missing]), "stored": False,
            "notice": "Only operator-authorized object names are shown. Discovery does not approve mappings, enable collection, prove historical completeness or permit writes."}
