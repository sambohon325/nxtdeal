"""Immutable approved ADF event profiles; simulation cannot activate records."""
from copy import deepcopy
from datetime import timezone
from hashlib import sha256

from core import dealer_bridge as bridge
from core.bridge_adapters.adf import creation_events
from core.bridge_contracts import transform, timestamp, validate_mapping_spec, TRANSFORM_VERSION
from core.dealeros import ledger

DEFINITION = ("system_id", "adapter_version", "kind", "id_source", "fields", "time_semantics", "projection", "transform_version")
SOURCES = frozenset({"name_first", "name_last", "name_full", "email", "phone"})


def definition_hash(profile):
    if profile.get("version") != 1 or profile.get("adapter_version") != "adf-creation-v1":
        raise ValueError("Unsupported event profile version")
    return bridge.digest({key: profile[key] for key in DEFINITION})


def checked(profile_id):
    profile = bridge.get(profile_id, "BridgeEventProfile")
    if profile["status"] == "revoked":
        raise ValueError("Event profile has been revoked")
    if profile["hash"] != definition_hash(profile):
        raise ValueError("Event profile changed; propose a replacement")
    return profile


def propose(actor, system_id, id_source, fields):
    if not isinstance(id_source, str) or not id_source.strip() or id_source != id_source.strip() or len(id_source) > 120 or any(ord(c) < 32 for c in id_source):
        raise ValueError("Exact bounded provider ID source required")
    if not isinstance(fields, dict) or not fields or set(fields) - {"first_name", "last_name", "email", "phone"}:
        raise ValueError("ADF profiles support selected Lead identity fields")
    for target, spec in fields.items():
        validate_mapping_spec(target, spec)
        if spec["source"] not in SOURCES or spec["transform"] not in {"text", "lower", "upper"}:
            raise ValueError("ADF profile requires selected source identity fields and text transformations")
    profile = {"version": 1, "system_id": system_id, "adapter_version": "adf-creation-v1", "kind": "Lead",
               "id_source": id_source, "fields": deepcopy(fields), "time_semantics": "created",
               "projection": "create_or_history_only", "transform_version": TRANSFORM_VERSION}
    profile["hash"] = definition_hash(profile)
    with bridge.mutation(actor):
        bridge.get(system_id, "BridgeSystem")
        profile_id = bridge.add("BridgeEventProfile", {**profile, "status": "proposed", "proposed_by": actor["employee_id"],
            "proposed_principal": actor.get("bridge_principal"), "proposed_at": bridge.now(), "approved_by": None})
        bridge.audit(actor, "event_profile.propose", profile_id)
    return {"id": profile_id, "status": "proposed"}


def approve(actor, profile_id):
    with bridge.mutation(actor, True):
        profile = checked(profile_id)
        if profile["proposed_by"] == actor["employee_id"]:
            raise PermissionError("A different administrator must approve the event profile")
        if profile["status"] == "approved":
            return {"status": "approved", "idempotent": True}
        profile.update(status="approved", approved_by=actor["employee_id"], approved_at=bridge.now())
        bridge.audit(actor, "event_profile.approve", profile_id)
    return {"status": "approved"}


def revoke(actor, profile_id, reason):
    reason = bridge.review_reason(reason)
    with bridge.mutation(actor, True):
        profile = bridge.get(profile_id, "BridgeEventProfile")
        if profile["status"] != "revoked":
            profile.update(status="revoked", revoked_by=actor["employee_id"], revoked_at=bridge.now(), revoke_reason=reason)
            bridge.audit(actor, "event_profile.revoke", profile_id)
    return {"status": "revoked"}


def list_profiles(actor, system_id):
    bridge.authorize(actor)
    with bridge.LOCK:
        bridge.get(system_id, "BridgeSystem")
        return [{"id": e.id, **deepcopy(e.attributes)} for e in list(ledger.get_all().values())
                if e.entity_type == "BridgeEventProfile" and e.attributes.get("workspace_id") == ledger.tenant.workspace_id
                and e.attributes.get("system_id") == system_id]


def simulate(actor, profile_id, content):
    bridge.authorize(actor)
    with bridge.LOCK:
        profile = deepcopy(checked(profile_id))
        bridge.get(profile["system_id"], "BridgeSystem")
    events = creation_events(content, id_source=profile["id_source"])
    rows, seen = [], {}
    for number, event in enumerate(events, 1):
        try:
            values = transform("Lead", profile["fields"], event.values, version=profile["transform_version"])
            instant = timestamp(event.occurred_at).astimezone(timezone.utc).isoformat()
            key = (event.source_namespace, event.external_id, instant)
            if key in seen and seen[key] != values:
                raise ValueError("Conflicting creation event at the same source time")
            seen[key] = values
            rows.append({"row_number": number, "status": "ready", "external_id": event.external_id,
                         "source_namespace": event.source_namespace, "occurred_at": instant, "time_semantics": "created", "values": values})
        except ValueError:
            rows.append({"row_number": number, "status": "quarantined", "error_code": "invalid_or_conflicting_event"})
    with bridge.LOCK:
        current = checked(profile_id)
        if current["hash"] != profile["hash"] or current["status"] != profile["status"]:
            raise ValueError("Event profile changed during simulation; test again")
    return {"profile_id": profile_id, "profile_hash": profile["hash"], "profile_status": profile["status"],
            "stored": False, "activation_available": False, "rows": rows, "content_hash": sha256(content.encode("utf-8")).hexdigest(),
            "notice": "Mapping simulation only. Identity resolution, staging, canonical projection and Chrono delivery require the event ingestion path; this report does not authorize activation."}
