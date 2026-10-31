"""Review-first bridge on the existing isolated-process graph repository.

Bridge mutations are serialized and use record-scoped rollback on save failure.
This is not a database transaction across other legacy graph writers.
"""
from copy import deepcopy
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
import json
from threading import RLock

from chrono.contracts import Observation
from core.bridge_contracts import FIELDS, REFERENCE_TYPES, GRAPH_ALIASES, MONEY, LOOKUP_FIELDS, graph_values, transform, timestamp, validate_mapping_spec, storage_kind, TRANSFORM_VERSION
from core.bridge_reconciliation import mapping_expectations, reconcile
from core.bridge_connectors import CATALOG, parse_export, source_columns_profile
from core.bridge_catalog import CATEGORY_LABELS
from core.bridge_indexes import ValidationIndex, identity_value
from core.bridge_projection import explain as explain_projection
from core.dealeros import ledger, id_generator
from core import bridge_storage
from core.entities import Entity
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH

LOCK = RLock()

def now():
    return datetime.now(timezone.utc).isoformat()

def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

def authorize(actor, human=False):
    if actor.get("role") != "ADMIN" or not actor.get("employee_id"):
        raise PermissionError("Bridge requires a dealership administrator")
    if human and actor.get("bridge_principal") != "session":
        raise PermissionError("Interactive administrator session required; agent/API credentials cannot approve or activate")
    if actor.get("workspace_id", ledger.tenant.workspace_id) != ledger.tenant.workspace_id:
        raise PermissionError("Workspace mismatch")


def require_durable_state():
    from core.json_graph_repository import demo_persistence_disabled
    if demo_persistence_disabled():
        raise ValueError("Durable storage is disabled in demo mode; live collection and delivery are unavailable")

@contextmanager
def mutation(actor, human=False):
    authorize(actor, human)
    with LOCK, ledger.persistence_guard():
        if bridge_storage.current() is not None:
            yield
            return
        journal, token = bridge_storage.begin()
        attempted = None
        try:
            yield
            attempted = journal.changes()
            if attempted:
                save_graph(GRAPH_PATH)
        except Exception as exc:
            conflicts = journal.rollback(attempted if attempted is not None else journal.changes())
            if conflicts:
                raise bridge_storage.PersistenceConflict("Persistence failed with a concurrent record change; review graph state before retrying") from exc
            if attempted is not None and isinstance(exc, OSError):
                # Preserve the OSError contract for core callers, but distinguish
                # filesystem PermissionError from application authorization.
                raise bridge_storage.PersistenceUnavailable(str(exc)) from exc
            raise
        finally:
            bridge_storage.end(token)


def put(entity):
    bridge_storage.put(entity)


def add(kind, attributes):
    record_id = id_generator.generate({"Customer": "CUST", "Vehicle": "VEH", "Lead": "LEAD", "Employee": "EMP", "Deal": "DEAL", "FinanceContract": "FIN", "ServiceRecord": "SRV", "Part": "PART", "Campaign": "CAMP"}.get(kind, "BRG"))
    metadata = {"canonical_kind": kind, "import_semantics": "observation_only"} if storage_kind(kind) != kind else {}
    put(Entity(record_id, storage_kind(kind), {**deepcopy(attributes), **metadata, "workspace_id": ledger.tenant.workspace_id}))
    return record_id

def get(record_id, kind):
    entity = ledger.get_entity(record_id)
    if not entity or entity.entity_type != kind or entity.attributes.get("workspace_id") != ledger.tenant.workspace_id:
        raise ValueError("Bridge record not found in this workspace")
    bridge_storage.touch(record_id)
    return entity.attributes

def audit(actor, action, record_id):
    add("BridgeAudit", {"actor": actor["employee_id"], "principal": actor.get("bridge_principal"), "action": action, "record_id": record_id, "at": now()})

def system_map(actor):
    with LOCK:
        return _system_map(actor)


def _system_map(actor):
    authorize(actor)
    def rows(kind, exclude=()):
        return [{"id": e.id, **deepcopy({key: value for key, value in e.attributes.items() if key not in exclude})} for e in list(ledger.get_all().values())
                if e.entity_type == kind and e.attributes.get("workspace_id") == ledger.tenant.workspace_id]
    from core import bridge_runtime, bridge_sync, bridge_chrono, bridge_health, bridge_inbound
    from core.bridge_readiness import summarize as readiness_summary
    mappings = rows("BridgeMapping")
    jobs = rows("BridgeJob", {"rows", "preview", "activation_receipt"})
    event_profiles = rows("BridgeEventProfile")
    event_jobs = rows("BridgeEventJob", {"rows", "preview", "activation_receipt", "identity_reviews"})
    sync_states = bridge_sync.states(actor)
    systems = []
    for system in rows("BridgeSystem", {"health_probe"}):
        runtime_description = bridge_runtime.describe(system["id"])
        connector_health = bridge_health.public(system, runtime_description)
        systems.append({**system, "runtime": runtime_description,
                        "readiness": readiness_summary(system, runtime_description, mappings, jobs, event_profiles, event_jobs, sync_states, bridge_inbound.status(actor, system["id"]), connector_health),
                        "connector_health": connector_health})
    return {"catalog": deepcopy(list(CATALOG.values())), "category_labels": dict(CATEGORY_LABELS), "schemas": FIELDS, "monetary_fields": sorted(MONEY), "reference_fields": REFERENCE_TYPES, "lookup_fields": sorted(LOOKUP_FIELDS),
            "systems": systems, "sync_states": sync_states,
            "mappings": mappings, "jobs": jobs,
            "legacy_connections": [{"id": e.id, "name": e.attributes.get("name"), "status": "legacy_unreviewed"}
                                   for e in list(ledger.get_all().values()) if e.entity_type == "Connection" and
                                   e.attributes.get("workspace_id", ledger.tenant.workspace_id) == ledger.tenant.workspace_id],
            "chrono": bridge_chrono.status(actor), "writeback": "disabled"}

def connect(actor, vendor, name):
    if vendor not in CATALOG or not name.strip() or len(name) > 120:
        raise ValueError("Known vendor and system name required")
    with mutation(actor):
        # A registered implementation is not an authenticated dealer connection.
        # Never call a global adapter's health method while adding a new system.
        health = {"status": "ready", "transport": "manual_upload"} if vendor == "CSV" else {
            "status": "unavailable", "reason": "A dealer-authorized per-system adapter binding is required"}
        record_id = add("BridgeSystem", {"vendor": vendor, "name": name.strip(), "mode": "read_only", "phase": "discovered",
            "health": health, "cursor": None, "created_by": actor["employee_id"], "created_at": now()})
        audit(actor, "system.discover", record_id)
    return {"id": record_id}

def propose_mapping(actor, system_id, kind, object_type, fields, source_columns=None):
    # Test syntax without requiring a populated source row. The immutable mapping
    # is hashed and any revision is a NEW proposal with a new approval cycle.
    if kind not in FIELDS or not object_type.strip() or object_type != object_type.strip() or len(object_type) > 120:
        raise ValueError("Known canonical type and source object required")
    if not fields or set(fields) - set(FIELDS[kind]):
        raise ValueError("Unknown canonical fields")
    for target, spec in fields.items():
        validate_mapping_spec(target, spec)
    source_columns = source_columns_profile(source_columns)
    definition = {"system_id": system_id, "kind": kind, "object_type": object_type, "fields": fields,
                  "source_columns": source_columns, "transform_version": TRANSFORM_VERSION}
    with mutation(actor):
        get(system_id, "BridgeSystem")
        record_id = add("BridgeMapping", {"system_id": system_id, "kind": kind, "object_type": object_type,
            "fields": fields, "source_columns": source_columns, "transform_version": TRANSFORM_VERSION,
            "hash_version": 3, "version": 1, "hash": digest(definition), "status": "proposed", "proposed_by": actor["employee_id"],
            "proposed_principal": actor.get("bridge_principal"), "approved_by": None})
        audit(actor, "mapping.propose", record_id)
    return {"id": record_id}

def approve_mapping(actor, mapping_id):
    with mutation(actor, True):
        mapping = get(mapping_id, "BridgeMapping")
        if mapping["status"] == "revoked":
            raise ValueError("Revoked mappings require a new proposal")
        if mapping_digest(mapping) != mapping["hash"]:
            raise ValueError("Mapping definition changed; propose a replacement")
        if mapping["proposed_by"] == actor["employee_id"]:
            raise PermissionError("A different administrator must approve the mapping")
        if mapping["status"] == "approved":
            return {"status": "approved", "idempotent": True}
        mapping.update(status="approved", approved_by=actor["employee_id"], approved_at=now())
        audit(actor, "mapping.approve", mapping_id)
    return {"status": "approved"}

def stage(actor, mapping_id, content, expected=None, file_format="csv"):
    with mutation(actor):
        return _stage_import(actor, mapping_id, content, expected, file_format)


def _stage_import(actor, mapping_id, content, expected=None, file_format="csv"):
    """Internal graph mutation; caller must hold mutation() through persistence."""
    mapping = get(mapping_id, "BridgeMapping")
    system = get(mapping["system_id"], "BridgeSystem")
    if system.get("paused"):
        raise ValueError("System is paused")
    prepared = prepare_import(mapping, system, content, expected, file_format)
    rows, headers = prepared["rows"], prepared["headers"]
    record_id = add("BridgeJob", {"mapping_id": mapping_id, "mapping_hash": mapping["hash"], "system_id": mapping["system_id"],
        "status": "staged", **prepared, "created_at": now(), "created_by": actor["employee_id"], "created_principal": actor.get("bridge_principal"),
        "transport": "manual_upload", "preview": [], "content_hash": digest(rows)})
    system["phase"] = "discovery_import"
    audit(actor, "import.stage", record_id)
    return {"id": record_id, "rows": len(rows), "headers": headers}


def prepare_import(mapping, system, content, expected=None, file_format="csv"):
    """Pure bounded parsing shared by simulation and durable staging."""
    if mapping["status"] == "revoked":
        raise ValueError("Mapping has been revoked; propose a replacement")
    if mapping_digest(mapping) != mapping["hash"]:
        raise ValueError("Mapping definition changed; propose a replacement")
    expected = mapping_expectations(mapping, expected)
    headers, rows = parse_export(system["vendor"], content, mapping.get("source_columns"), file_format)
    if any(spec["source"] not in headers for spec in mapping["fields"].values()):
        raise ValueError("Mapped column absent from export")
    retained = {spec["source"] for spec in mapping["fields"].values()} | set(source_columns_profile(mapping.get("source_columns")).values()) | {"external_id", "modified_at"}
    rows = [{key: value for key, value in row.items() if key in retained} for row in rows]
    source_evidence = {"export_sha256": sha256(content.encode("utf-8")).hexdigest(), "schema_hash": digest(sorted(headers)),
        "byte_count": len(content.encode("utf-8")), "file_format": file_format, "storage_policy": "mapped_columns_only",
        "omitted_columns": sorted(set(headers) - retained)}
    return {"rows": rows, "headers": headers, "source_evidence": source_evidence, "expectations": expected}


def simulate_mapping(actor, mapping_id, content, expected=None, file_format="csv"):
    """Agent-safe test: no job, approval, identity decision, observation or save.

    Simulation remains available while collection is paused so an operator can
    investigate a corrected proposal without resuming production imports.
    """
    authorize(actor)
    with LOCK:
        mapping = get(mapping_id, "BridgeMapping")
        system = get(mapping["system_id"], "BridgeSystem")
        prepared = prepare_import(mapping, system, content, expected, file_format)
        checked = preview(prepared, mapping)
        return {"mapping_id": mapping_id, "mapping_hash": mapping["hash"], "mapping_status": mapping["status"],
            "status": "simulated", "stored": False, "rows": deepcopy(checked),
            "reconciliation": reconcile(checked, prepared["expectations"]), "source_evidence": prepared["source_evidence"],
            "notice": "Simulation only: no import job or approval was created. Staged imports still require fresh validation and human activation."}


def external_key(mapping, row):
    return digest([ledger.tenant.workspace_id, mapping["system_id"], mapping["object_type"], row["external_id"]])

def identity_candidates(kind, values):
    return ValidationIndex(list(ledger.get_all().values()), ledger.tenant.workspace_id, kind).candidates(values)


def preview(job, mapping):
    result, seen, batch_identities = [], set(), {}
    index = ValidationIndex(list(ledger.get_all().values()), ledger.tenant.workspace_id, mapping["kind"],
                            (external_key(mapping, row) for row in job["rows"]))
    for number, row in enumerate(job["rows"], 1):
        key = external_key(mapping, row)
        item = {"row": number, "key": key, "status": "ready", "errors": [], "confidence": 1.0}
        try:
            transform_version = mapping["transform_version"] if mapping.get("hash_version") == 3 else 1
            values = transform(mapping["kind"], mapping["fields"], row, version=transform_version)
            reference_issues = []
            for field, spec in mapping["fields"].items():
                if spec["transform"] == "external_id" and field in values:
                    reference_key = digest([ledger.tenant.workspace_id, mapping["system_id"], spec["object_type"], values[field]])
                    reference = ledger.get_entity("BRX-" + reference_key)
                    if (not reference or reference.entity_type != "BridgeExternalID" or
                            reference.attributes.get("workspace_id") != ledger.tenant.workspace_id or
                            reference.attributes.get("kind") != REFERENCE_TYPES[field] or
                            reference.attributes.get("system_id") != mapping["system_id"] or
                            reference.attributes.get("object_type") != spec["object_type"] or
                            reference.attributes.get("external_id") != values[field]):
                        reference_issues.append({"field": field, "source_object": spec["object_type"],
                            "expected_kind": REFERENCE_TYPES[field], "reason": "source_reference_unresolved"})
                    else:
                        values[field] = reference.attributes["target_id"]
            if reference_issues:
                item["reference_issues"] = reference_issues
                raise ValueError("Unresolved source references; import and activate the listed source objects, then validate this batch again")
            # Reference fields require an existing same-process target and explicit review.
            for field, value in values.items():
                if field in REFERENCE_TYPES:
                    target = ledger.get_entity(value)
                    if not target or target.entity_type not in {REFERENCE_TYPES[field], storage_kind(REFERENCE_TYPES[field])} or target.attributes.get("workspace_id", ledger.tenant.workspace_id) != ledger.tenant.workspace_id:
                        reference_issues.append({"field": field, "expected_kind": REFERENCE_TYPES[field],
                            "reason": "canonical_reference_unresolved"})
            if reference_issues:
                item["reference_issues"] = reference_issues
                raise ValueError("Unresolved or invalid canonical references; verify the listed fields, then validate this batch again")
            if mapping["kind"] == "LoanAccount" and values.get("contract_id"):
                contract = ledger.get_entity(values["contract_id"])
                contract_customer = contract.attributes.get("customer_id")
                if contract_customer and contract_customer != values["customer_id"]:
                    item["review_advisories"] = [{
                        "code": "contract_customer_differs",
                        "reference_hash": digest([values["contract_id"], contract_customer]),
                        "message": "The referenced contract currently names a different customer. Review source borrower roles, identity links and historical timing before activation. No borrower relationship is inferred or changed.",
                    }]
            if mapping["kind"] == "Payment" and values.get("reverses_payment_id"):
                original = ledger.get_entity(values["reverses_payment_id"])
                if original.attributes.get("account_id") != values["account_id"]:
                    raise ValueError("Reversal reference must belong to the same loan account")
            if mapping["kind"] == "JournalEntry" and values.get("ledger_account_id"):
                account = ledger.get_entity(values["ledger_account_id"])
                if account.attributes.get("account_code") != values["account_code"]:
                    raise ValueError("Journal account code does not match the referenced accounting account")
                if account.attributes.get("currency") and account.attributes["currency"] != values["currency"]:
                    raise ValueError("Journal currency does not match the referenced accounting account")
            item["values"] = values
            item["fingerprint"] = digest(values)
            link = ledger.get_entity("BRX-" + key)
            if link and (link.entity_type != "BridgeExternalID" or
                         link.attributes.get("workspace_id") != ledger.tenant.workspace_id or
                         link.attributes.get("system_id") != mapping["system_id"] or
                         link.attributes.get("object_type") != mapping["object_type"] or
                         link.attributes.get("external_id") != row["external_id"]):
                raise ValueError("Stored source identity is inconsistent with this workspace or source")
            identities = {(mapping["kind"], f, identity_value(values[f])) for f in ("email", "vin") if values.get(f)}
            for identity in identities:
                previous_links = batch_identities.get(identity, [])
                for previous in previous_links:
                    established_customers = (identity[0] == "Customer" and identity[1] == "email" and
                        link and previous and link.entity_type == previous.entity_type == "BridgeExternalID" and
                        link.attributes.get("kind") == previous.attributes.get("kind") == "Customer" and
                        link.attributes.get("workspace_id") == previous.attributes.get("workspace_id") == ledger.tenant.workspace_id)
                    if not established_customers or (link.attributes["target_id"] == previous.attributes["target_id"] and
                            (link.attributes.get("projection") != "preserve" or previous.attributes.get("projection") != "preserve")):
                        raise ValueError("Potential duplicate within batch requires manual identity resolution")
                batch_identities.setdefault(identity, []).append(link)
            for historical_values in index.historical_values(key, row["modified_at"]):
                if digest(historical_values) != item["fingerprint"]:
                    raise ValueError("Conflicting historical payload at the same source timestamp")
            if key in seen:
                raise ValueError("Repeated external identity in batch; split historical versions into ordered jobs")
            seen.add(key)
            if link:
                if link.attributes["kind"] != mapping["kind"]:
                    raise ValueError("External identity already mapped to a different canonical type")
                item["target_id"] = link.attributes["target_id"]
                if mapping["kind"] == "Payment" and values.get("reverses_payment_id") == item["target_id"]:
                    raise ValueError("A payment cannot reference itself as its reversal")
                target = ledger.get_entity(item["target_id"])
                if not target or target.entity_type != storage_kind(mapping["kind"]) or target.attributes.get("workspace_id", ledger.tenant.workspace_id) != ledger.tenant.workspace_id:
                    raise ValueError("External identity target missing or incompatible")
                item["target_revision"] = digest(target.attributes)
                item["projection"] = link.attributes.get("projection", "update")
                item["identity_review_id"] = link.attributes.get("identity_review_id")
                old = timestamp(link.attributes["modified_at"])
                new = timestamp(row["modified_at"])
                if old == new and link.attributes["fingerprint"] != item["fingerprint"]:
                    raise ValueError("Conflicting payload at the same source timestamp")
                item["status"] = "duplicate" if old == new else "history" if new < old else "ready"
            else:
                candidates = index.candidates(values)
                # Do not silently merge household emails, shared phones or cross-system VINs.
                decision_id = job.get("identity_decisions", {}).get(str(number))
                if decision_id:
                    item["review_decision_active"] = True
                    item["identity_review_id"] = decision_id
                    decision = get(decision_id, "BridgeIdentityReview")
                    if decision.get("mode") == "keep_separate":
                        current_candidates = [candidate_summary(record_id, row, mapping) for record_id in candidates]
                        if (mapping["kind"] != "Customer" or decision["row_hash"] != digest(row) or
                                decision["mapping_hash"] != mapping["hash"] or
                                decision["candidate_tokens"] != {c["id"]: c["review_token"] for c in current_candidates}):
                            item["candidate_records"] = current_candidates
                            raise ValueError("Identity review is stale; review the current candidates again")
                        item.update(identity_review_id=decision_id, identity_resolution="human_keep_separate")
                        result.append(item)
                        continue
                    target = ledger.get_entity(decision["target_id"])
                    if (decision["row_hash"] != digest(row) or decision["mapping_hash"] != mapping["hash"] or
                            decision["target_id"] not in candidates or not target or digest(target.attributes) != decision["target_hash"]):
                        item["candidate_records"] = [candidate_summary(record_id, row, mapping) for record_id in candidates]
                        raise ValueError("Identity review is stale; review the current candidate again")
                    item.update(target_id=target.id, projection="preserve", identity_review_id=decision_id,
                                identity_resolution="human_link_preserve_current")
                elif candidates:
                    item["candidates"] = candidates
                    item["candidate_records"] = [candidate_summary(record_id, row, mapping) for record_id in candidates]
                    item["confidence"] = 0.5
                    raise ValueError("Potential duplicate requires manual identity resolution")
            result.append(item)
        except (ValueError, TypeError, OverflowError) as exc:
            item.update(status="quarantined", errors=[str(exc)], confidence=0.0)
            result.append(item)
    for item in result:
        target = ledger.get_entity(item["target_id"]) if item.get("target_id") else None
        if target and (target.entity_type != storage_kind(mapping["kind"]) or
                       target.attributes.get("workspace_id", ledger.tenant.workspace_id) != ledger.tenant.workspace_id):
            target = None
        item.update(explain_projection(mapping["kind"], item, target))
    return result

def validate(actor, job_id):
    with mutation(actor):
        job = get(job_id, "BridgeJob")
        if job["status"] == "cancelled":
            raise ValueError("Cancelled imports cannot be validated")
        if job["status"] == "activated":
            return deepcopy(job["preview"])
        mapping = get(job["mapping_id"], "BridgeMapping")
        job["preview"] = preview(job, mapping)
        job["reconciliation"] = reconcile(job["preview"], job.get("expectations"))
        job["status"] = "validated" if job["reconciliation"]["status"] not in {"mismatch", "incomplete"} else "blocked"
        job["validation_hash"] = digest([job["rows"], job.get("expectations"), job["mapping_hash"]])
        job["validated_at"] = now()
        job["validated_by"] = actor["employee_id"]
        job["validated_principal"] = actor.get("bridge_principal")
        system = get(job["system_id"], "BridgeSystem")
        system["phase"] = "validate"
        system["import_health"] = {"status": job["status"], "checked_at": now(), "quarantined_rows": sum(r["status"] == "quarantined" for r in job["preview"])}
        audit(actor, "import.validate", job_id)
    return deepcopy(job["preview"])

def activate(actor, job_id):
    with mutation(actor, True):
        job = get(job_id, "BridgeJob")
        if job["status"] == "activated":
            return {"status": "activated", "idempotent": True}
        mapping = get(job["mapping_id"], "BridgeMapping")
        if mapping["status"] != "approved" or mapping["hash"] != job["mapping_hash"] or mapping_digest(mapping) != mapping["hash"]:
            raise PermissionError("Approved immutable mapping required")
        if job["status"] != "validated":
            raise ValueError("Validate the staged job first")
        if get(job["system_id"], "BridgeSystem").get("paused"):
            raise ValueError("System is paused")
        if job.get("validation_hash") != digest([job["rows"], job.get("expectations"), job["mapping_hash"]]):
            raise ValueError("Staged input changed; validate again")
        checked = preview(job, mapping)
        if checked != job["preview"]:
            raise ValueError("Graph changed since validation; validate again")
        report = reconcile(checked, job.get("expectations"))
        if report["status"] in {"mismatch", "incomplete"} or report != job.get("reconciliation"):
            raise ValueError("Reconciliation changed or failed; validate again")
        activated_at = now()
        # Capture the authorization and reviewed-input evidence before later
        # mapping lifecycle changes. This checksum is not a digital signature.
        receipt = {"version": 1, "job_id": job_id, "system_id": job["system_id"],
            "mapping_id": job["mapping_id"], "mapping_hash": job["mapping_hash"],
            "mapping_hash_version": mapping.get("hash_version", 1),
            "transform_version": mapping["transform_version"] if mapping.get("hash_version") == 3 else 1,
            "mapping_proposed_by": mapping["proposed_by"], "mapping_approved_by": mapping["approved_by"],
            "mapping_proposed_principal": mapping.get("proposed_principal"),
            "mapping_approved_at": mapping.get("approved_at"),
            "staged_by": job["created_by"], "staged_at": job["created_at"],
            "staged_principal": job.get("created_principal"),
            "validated_by": job.get("validated_by"), "validated_principal": job.get("validated_principal"),
            "validated_at": job["validated_at"], "validation_hash": job["validation_hash"],
            "preview_hash": digest(checked), "content_hash": job["content_hash"],
            "source_evidence": deepcopy(job.get("source_evidence")),
            "transport": job.get("transport"), "binding_revision": job.get("binding_revision"),
            "collection_mode": job.get("collection_mode"), "sync_state_id": job.get("sync_state_id"),
            "collection_page": deepcopy(job.get("collection_page")),
            "collection_environment": job.get("collection_environment"),
            "expectations": deepcopy(job.get("expectations")), "reconciliation": deepcopy(report),
            "activated_by": actor["employee_id"], "activated_at": activated_at,
            "identity_review_ids": sorted({item["identity_review_id"] for item in checked if item.get("identity_review_id")})}
        receipt["checksum"] = digest(receipt)
        system = get(job["system_id"], "BridgeSystem")
        for row, item in zip(job["rows"], checked):
            if item["status"] == "duplicate":
                continue
            target_id = item.get("target_id")
            if not target_id:
                target_id = add(mapping["kind"], graph_values(mapping["kind"], item["values"]))
            elif item["status"] != "history" and item.get("projection") != "preserve":
                bridge_storage.touch(target_id)
                ledger.get_entity(target_id).attributes.update(graph_values(mapping["kind"], item["values"]))
            observation = Observation(target_id, row["modified_at"], "observed", system["vendor"], row["external_id"],
                row["modified_at"], now(), item["confidence"], item.get("identity_resolution", "external_id" if item.get("target_id") else "new"), job_id)
            event_id = "BRE-" + digest([item["key"], timestamp(row["modified_at"]).astimezone(timezone.utc).isoformat(), item["fingerprint"]])
            if not ledger.get_entity(event_id):
                put(Entity(event_id, "SourceObservation", {"origin": "dealer_bridge", **asdict(observation), "workspace_id": ledger.tenant.workspace_id,
                    "system_id": job["system_id"], "external_key": item["key"], "object_type": mapping["object_type"], "mapping_id": job["mapping_id"], "canonical_kind": mapping["kind"],
                    "values": item["values"], "delivery_status": "pending"}))
            if item["status"] != "history":
                put(Entity("BRX-" + item["key"], "BridgeExternalID", {"workspace_id": ledger.tenant.workspace_id,
                    "kind": mapping["kind"], "target_id": target_id, "system_id": job["system_id"], "external_id": row["external_id"],
                    "object_type": mapping["object_type"], "modified_at": row["modified_at"], "fingerprint": item["fingerprint"],
                    "projection": item.get("projection", "update"), "identity_review_id": item.get("identity_review_id")}))
        job.update(status="activated", activated_by=actor["employee_id"], activated_at=activated_at, activation_receipt=receipt)
        system.update(phase="active", last_success_at=now(), import_health={"status": "ready", "transport": job.get("transport", "manual_upload")})
        audit(actor, "import.activate", job_id)
    return {"status": "activated", "rows": len(checked)}

def chrono_observations(actor):
    authorize(actor)
    # Read a coherent Bridge snapshot while a background outbox may be updating.
    from core import bridge_chrono
    with LOCK:
        return [{"event_id": e.id, **deepcopy(e.attributes), "delivery_status": bridge_chrono.status_for(e.id)} for e in list(ledger.get_all().values())
                if e.entity_type == "SourceObservation" and e.attributes.get("origin") == "dealer_bridge" and e.attributes["workspace_id"] == ledger.tenant.workspace_id]

def propose_write(actor, system_id, target_id, changes):
    with mutation(actor):
        get(system_id, "BridgeSystem")
        target = ledger.get_entity(target_id)
        if not target or target.attributes.get("workspace_id", ledger.tenant.workspace_id) != ledger.tenant.workspace_id:
            raise ValueError("Existing target in this workspace required")
        kind = target.attributes.get("canonical_kind", target.entity_type)
        if kind not in FIELDS or not isinstance(changes, dict) or not changes or len(changes) > 50 or set(changes) - set(FIELDS[kind]):
            raise ValueError("Known canonical field changes required")
        if any(not isinstance(value, (str, int, bool, type(None))) or len(str(value)) > 1000 for value in changes.values()):
            raise ValueError("Write proposals accept bounded scalar values only")
        record_id = add("BridgeWriteProposal", {"system_id": system_id, "target_id": target_id, "changes": changes,
            "status": "blocked", "reason": "Write-back disabled in foundation; requires operation-specific authorization, reconciliation and adapter certification", "proposed_by": actor["employee_id"]})
        audit(actor, "write.propose", record_id)
    return {"id": record_id, "status": "blocked"}


def candidate_summary(record_id, row, mapping):
    target = ledger.get_entity(record_id)
    aliases = GRAPH_ALIASES.get(target.entity_type, {})
    fields = ("first_name", "last_name", "email", "vin", "make", "model")
    summary = {field: target.attributes.get(field, target.attributes.get(aliases.get(field))) for field in fields}
    for field in ("email", "vin"):
        alternate = target.attributes.get(aliases.get(field))
        if alternate is not None and field in target.attributes and alternate != target.attributes[field]:
            summary["alternate_" + field] = alternate
    return {"id": target.id, "summary": {k: v for k, v in summary.items() if v is not None},
            "review_token": digest([digest(row), mapping["hash"], target.id, target.attributes])}


def resolve_identity(actor, job_id, row_number, target_id, review_token, reason):
    """Link one observed source to a reviewed existing record, never merge or overwrite.

The token binds what the administrator saw to the source row and target snapshot.
A later change invalidates the decision until reviewed again.
"""
    if not isinstance(reason, str) or not 8 <= len(reason.strip()) <= 500:
        raise ValueError("A review reason of 8 to 500 characters is required")
    with mutation(actor, True):
        job = get(job_id, "BridgeJob")
        if job["status"] in {"activated", "cancelled"}:
            raise ValueError("Activated or cancelled imports cannot be relinked")
        if type(row_number) is not int or not 1 <= row_number <= len(job["rows"]):
            raise ValueError("Unknown import row")
        mapping = get(job["mapping_id"], "BridgeMapping")
        # Recompute without an earlier decision so stale reviews can be replaced.
        inspection = deepcopy(job)
        inspection.get("identity_decisions", {}).pop(str(row_number), None)
        candidate = next((c for c in preview(inspection, mapping)[row_number - 1].get("candidate_records", [])
                          if c["id"] == target_id), None)
        if not candidate or candidate["review_token"] != review_token:
            raise ValueError("Candidate changed or was not offered; validate again before reviewing")
        target = ledger.get_entity(target_id)
        review_id = add("BridgeIdentityReview", {"job_id": job_id, "row": row_number, "target_id": target_id,
            "target_hash": digest(target.attributes), "row_hash": digest(job["rows"][row_number - 1]),
            "mapping_hash": mapping["hash"], "reviewed_by": actor["employee_id"], "reviewed_at": now(),
            "reason": reason.strip(), "mode": "link_preserve_current"})
        job.setdefault("identity_decisions", {})[str(row_number)] = review_id
        job.update(status="staged", preview=[])
        audit(actor, "identity.review.link", review_id)
    return {"id": review_id, "status": "reviewed", "next_step": "validate", "projection": "preserve"}


def keep_identity_separate(actor, job_id, row_number, candidate_tokens, reason):
    """Human review of every offered customer match, bound to exact snapshots.

    Shared email is evidence for review, not proof that two customers are the same.
    VIN and within-batch conflicts deliberately have no distinct-record override.
    """
    reason = review_reason(reason)
    with mutation(actor, True):
        job = get(job_id, "BridgeJob")
        if job["status"] in {"activated", "cancelled"}:
            raise ValueError("Activated or cancelled imports cannot be reviewed")
        if type(row_number) is not int or not 1 <= row_number <= len(job["rows"]):
            raise ValueError("Unknown import row")
        mapping = get(job["mapping_id"], "BridgeMapping")
        if mapping["kind"] != "Customer":
            raise ValueError("Separate-record review is available only for customers")
        inspection = deepcopy(job)
        inspection.get("identity_decisions", {}).pop(str(row_number), None)
        offered = preview(inspection, mapping)[row_number - 1].get("candidate_records", [])
        tokens = {candidate["id"]: candidate["review_token"] for candidate in offered}
        if not tokens or tokens != candidate_tokens:
            raise ValueError("Review every current candidate; candidates changed or were not offered")
        review_id = add("BridgeIdentityReview", {"job_id": job_id, "row": row_number,
            "row_hash": digest(job["rows"][row_number - 1]), "mapping_hash": mapping["hash"],
            "candidate_tokens": tokens, "mode": "keep_separate", "reason": reason,
            "reviewed_by": actor["employee_id"], "reviewed_at": now()})
        job.setdefault("identity_decisions", {})[str(row_number)] = review_id
        job.update(status="staged", preview=[])
        audit(actor, "identity.review.separate", review_id)
    return {"id": review_id, "status": "reviewed", "next_step": "validate", "mode": "keep_separate"}


def withdraw_identity_review(actor, job_id, row_number, reason):
    """Withdraw an unactivated decision while retaining its original evidence."""
    reason = review_reason(reason)
    with mutation(actor, True):
        job = get(job_id, "BridgeJob")
        if job["status"] in {"activated", "cancelled"}:
            raise ValueError("Activated or cancelled identity decisions cannot be withdrawn")
        decision_id = job.get("identity_decisions", {}).get(str(row_number))
        if not decision_id:
            raise ValueError("No staged identity decision for this row")
        record_id = add("BridgeIdentityReviewWithdrawal", {"job_id": job_id, "row": row_number,
            "review_id": decision_id, "reason": reason, "withdrawn_by": actor["employee_id"], "withdrawn_at": now()})
        job["identity_decisions"].pop(str(row_number))
        job.update(status="staged", preview=[])
        audit(actor, "identity.review.withdraw", record_id)
    return {"id": record_id, "status": "withdrawn", "next_step": "validate"}


def mapping_digest(mapping):
    # Preserve already-stored v1 proposals; new proposals bind the entire profile.
    if mapping.get("hash_version", 1) == 1:
        return digest(mapping["fields"])
    if mapping["hash_version"] not in {2, 3}:
        raise ValueError("Unsupported mapping hash version")
    keys = ("system_id", "kind", "object_type", "fields", "source_columns")
    if mapping["hash_version"] == 3:
        keys += ("transform_version",)
    return digest({key: mapping[key] for key in keys})


def review_reason(reason):
    if not isinstance(reason, str) or not 8 <= len(reason.strip()) <= 500:
        raise ValueError("A reason of 8 to 500 characters is required")
    return reason.strip()


def set_system_paused(actor, system_id, paused, reason):
    reason = review_reason(reason)
    if type(paused) is not bool:
        raise ValueError("Paused must be a boolean")
    with mutation(actor, True):
        system = get(system_id, "BridgeSystem")
        system.update(paused=paused, pause_reason=reason, pause_changed_by=actor["employee_id"], pause_changed_at=now())
        audit(actor, "system.pause" if paused else "system.resume", system_id)
    return {"id": system_id, "paused": paused}


def revoke_mapping(actor, mapping_id, reason):
    reason = review_reason(reason)
    with mutation(actor, True):
        mapping = get(mapping_id, "BridgeMapping")
        if mapping["status"] == "revoked":
            return {"id": mapping_id, "status": "revoked", "idempotent": True}
        mapping.update(status="revoked", revoked_by=actor["employee_id"], revoked_at=now(), revoke_reason=reason)
        audit(actor, "mapping.revoke", mapping_id)
    return {"id": mapping_id, "status": "revoked"}


def cancel_import(actor, job_id, reason):
    reason = review_reason(reason)
    with mutation(actor, True):
        job = get(job_id, "BridgeJob")
        if job["status"] == "activated":
            raise ValueError("Activated imports require a reviewed correction; cancellation cannot undo data")
        if job["status"] == "cancelled":
            return {"id": job_id, "status": "cancelled", "idempotent": True}
        job.update(status="cancelled", cancelled_by=actor["employee_id"], cancelled_at=now(), cancel_reason=reason)
        audit(actor, "import.cancel", job_id)
    return {"id": job_id, "status": "cancelled"}


def import_report(actor, job_id):
    authorize(actor)
    with LOCK:
        job = get(job_id, "BridgeJob")
        receipt = job.get("activation_receipt")
        from core.bridge_receipts import snapshot_integrity
        receipt_integrity = snapshot_integrity(job, job_id)
        return {"id": job_id, "status": job["status"], "system_id": job["system_id"],
                "mapping_id": job["mapping_id"], "mapping_hash": job["mapping_hash"],
                "content_hash": job.get("content_hash"), "expectations": deepcopy(job.get("expectations")),
                "source_evidence": deepcopy(job.get("source_evidence")),
                "collection_page": deepcopy(job.get("collection_page")),
                "collection_environment": job.get("collection_environment"),
                "activation_receipt": deepcopy(receipt), "receipt_integrity": receipt_integrity,
                "payload_cleanup": deepcopy(job.get("payload_cleanup")),
                "reconciliation": deepcopy(job.get("reconciliation")),
                "created_at": job["created_at"], "validated_at": job.get("validated_at"),
                "activated_at": job.get("activated_at"), "cancelled_at": job.get("cancelled_at")}
