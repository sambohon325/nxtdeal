"""Review queue for explicit creation events, separate from snapshot imports."""
from copy import deepcopy
import re

from core import dealer_bridge as bridge, bridge_event_profiles as profiles
from core.dealeros import ledger
from core.entities import Entity
from core.bridge_contracts import graph_values
from core.bridge_projection import snapshot
from core.bridge_inbound_evidence import checked as delivery_evidence


def source_key(system_id, row):
    return bridge.digest([ledger.tenant.workspace_id, system_id, "adf_prospects", row["source_namespace"], row["external_id"]])


def _check(job, job_id):
    delivery_evidence(job_id, job)
    profile = profiles.checked(job["profile_id"])
    if profile["hash"] != job["profile_hash"]:
        raise ValueError("Event profile changed; stage a new batch")
    if bridge.digest(job["source_evidence"]) != job["source_evidence_hash"]:
        raise ValueError("Staged source evidence changed; stage a new batch")
    if bridge.digest(job["rows"]) != job["rows_hash"]:
        raise ValueError("Staged event rows changed; stage a new batch")
    if bridge.get(job["system_id"], "BridgeSystem").get("paused"):
        raise ValueError("System is paused")
    return profile


def stage(actor, profile_id, content):
    # Simulation is bounded and does not persist unselected source data.
    report = profiles.simulate(actor, profile_id, content)
    with bridge.mutation(actor):
        profile = profiles.checked(profile_id)
        if profile["hash"] != report["profile_hash"]:
            raise ValueError("Event profile changed; simulate again")
        if bridge.get(profile["system_id"], "BridgeSystem").get("paused"):
            raise ValueError("System is paused")
        rows = report["rows"]
        evidence = {"export_sha256": report["content_hash"], "byte_count": len(content.encode("utf-8")),
                    "file_format": "adf", "adapter_version": profile["adapter_version"], "storage_policy": "mapped_event_values_only"}
        job_id = bridge.add("BridgeEventJob", {"profile_id": profile_id, "profile_hash": profile["hash"],
            "system_id": profile["system_id"], "rows": rows, "rows_hash": bridge.digest(rows),
            "source_evidence": evidence, "source_evidence_hash": bridge.digest(evidence),
            "status": "staged", "created_by": actor["employee_id"], "created_at": bridge.now(),
            "created_principal": actor.get("bridge_principal"), "preview": []})
        bridge.get(profile["system_id"], "BridgeSystem")["phase"] = "discovery_import"
        bridge.audit(actor, "event_import.stage", job_id)
    return {"id": job_id, "rows": len(rows), "status": "staged"}


def contact_key(field, value):
    text = str(value or "").strip().casefold()
    return re.sub(r"[^0-9]", "", text) if field == "phone" else text


def candidate_record(candidate):
    values, conflicts = snapshot("Lead", ledger.get_entity(candidate).attributes, ("first_name", "last_name", "email", "phone"))
    return {"id": candidate, "values": values, "legacy_conflicts": conflicts}


def preview(job, job_id=None, *, apply_decisions=True):
    """Recompute collisions and candidates from current workspace state."""
    result, batch_keys, batch_contacts = [], {}, {}
    entities = list(ledger.get_all().values())
    contacts = {}
    for entity in entities:
        if entity.entity_type != "Lead" or entity.attributes.get("workspace_id", ledger.tenant.workspace_id) != ledger.tenant.workspace_id:
            continue
        for field, alias in (("email", "Email"), ("phone", "Phone")):
            for value in (entity.attributes.get(field), entity.attributes.get(alias)):
                normalized = contact_key(field, value)
                if normalized:
                    contacts.setdefault((field, normalized), set()).add(entity.id)
    for row in job["rows"]:
        item = deepcopy(row)
        if row["status"] == "quarantined":
            result.append(item)
            continue
        key = source_key(job["system_id"], row)
        item["source_key"] = key
        fingerprint = bridge.digest([row["occurred_at"], row["time_semantics"], row["values"]])
        item["fingerprint"] = fingerprint
        link = ledger.get_entity("BEX-" + key)
        if key in batch_keys:
            item.update(status="duplicate" if batch_keys[key] == fingerprint else "quarantined")
            if item["status"] == "quarantined": item["error_code"] = "conflicting_creation_event"
        elif link:
            attrs = link.attributes
            target = ledger.get_entity(attrs.get("target_id"))
            event = ledger.get_entity(attrs.get("event_id"))
            if (link.entity_type != "BridgeEventExternalID" or attrs.get("workspace_id") != ledger.tenant.workspace_id or
                    attrs.get("system_id") != job["system_id"] or attrs.get("source_namespace") != row["source_namespace"] or attrs.get("external_id") != row["external_id"] or
                    not target or target.entity_type != "Lead" or target.attributes.get("workspace_id", ledger.tenant.workspace_id) != ledger.tenant.workspace_id or
                    not event or event.entity_type != "SourceObservation" or event.attributes.get("workspace_id") != ledger.tenant.workspace_id or
                    event.attributes.get("entity_id") != target.id or event.attributes.get("external_key") != key or
                    event.attributes.get("source_time_semantics") != "created" or
                    bridge.digest([event.attributes.get("source_timestamp"), "created", event.attributes.get("values")]) != attrs.get("fingerprint")):
                item.update(status="quarantined", error_code="source_identity_unavailable")
            elif attrs.get("fingerprint") == fingerprint:
                item.update(status="duplicate", target_id=target.id)
            else:
                item.update(status="quarantined", error_code="conflicting_creation_event")
        else:
            candidates = set()
            sibling = False
            for field in ("email", "phone"):
                value = contact_key(field, row["values"].get(field))
                if value:
                    candidates.update(contacts.get((field, value), ()))
                    sibling = sibling or (field, value) in batch_contacts
                    batch_contacts[(field, value)] = key
            if candidates or sibling:
                item.update(status="quarantined", error_code="identity_review_required", candidates=sorted(candidates))
                item["candidate_records"] = [candidate_record(candidate) for candidate in sorted(candidates)]
                item["candidate_signature"] = bridge.digest([sibling, [(candidate, ledger.get_entity(candidate).attributes) for candidate in sorted(candidates)]])
                decision_id = job.get("identity_reviews", {}).get(str(row["row_number"])) if apply_decisions else None
                if decision_id:
                    decision = bridge.get(decision_id, "BridgeEventIdentityReview")
                    if (decision.get("status") != "active" or decision.get("job_id") != job_id or decision.get("row_number") != row["row_number"] or
                            decision.get("row_hash") != bridge.digest(row) or decision.get("profile_hash") != job["profile_hash"] or
                            decision.get("candidate_signature") != item["candidate_signature"]):
                        item["error_code"] = "identity_review_stale"
                    elif decision["action"] == "keep_separate":
                        item.update(status="ready", effect="create", identity_resolution="human_keep_separate", identity_review_id=decision_id)
                        item.pop("error_code", None)
                    elif decision["action"] == "link" and decision.get("target_id") in candidates:
                        item.update(status="ready", effect="history_only", target_id=decision["target_id"], identity_resolution="human_link", identity_review_id=decision_id)
                        item.pop("error_code", None)
            else:
                item.update(status="ready", effect="create")
        if apply_decisions and job.get("identity_reviews", {}).get(str(row["row_number"])) and item.get("effect") == "create" and not item.get("identity_review_id"):
            item.update(status="quarantined", error_code="identity_review_stale")
            item.pop("effect", None)
        batch_keys[key] = fingerprint
        result.append(item)
    return result



def validation_hash(job, checked, job_id):
    values = [job["rows_hash"], job["profile_hash"], job["source_evidence_hash"], checked]
    evidence = delivery_evidence(job_id, job)
    if evidence is not None: values.append(evidence)
    return bridge.digest(values)


def validate(actor, job_id):
    with bridge.mutation(actor):
        job = bridge.get(job_id, "BridgeEventJob")
        if job["status"] in {"activated", "cancelled"}:
            raise ValueError("Finished event import cannot be validated")
        _check(job, job_id)
        checked = preview(job, job_id)
        job.update(preview=checked, status="blocked" if any(row["status"] == "quarantined" for row in checked) else "validated",
                   validated_at=bridge.now(), validated_by=actor["employee_id"], validation_hash=validation_hash(job, checked, job_id))
        bridge.audit(actor, "event_import.validate", job_id)
    return {"status": job["status"], "rows": deepcopy(checked)}


def cancel(actor, job_id, reason):
    reason = bridge.review_reason(reason)
    with bridge.mutation(actor, True):
        job = bridge.get(job_id, "BridgeEventJob")
        if job["status"] == "activated":
            raise ValueError("Activated event imports cannot be cancelled")
        if job["status"] != "cancelled":
            job.update(status="cancelled", cancelled_by=actor["employee_id"], cancelled_at=bridge.now(), cancel_reason=reason)
            bridge.audit(actor, "event_import.cancel", job_id)
    return {"status": "cancelled"}


def report(actor, job_id):
    bridge.authorize(actor)
    with bridge.LOCK:
        job = bridge.get(job_id, "BridgeEventJob")
        profile = bridge.get(job["profile_id"], "BridgeEventProfile")
        try: ingestion = delivery_evidence(job_id, job)
        except (ValueError, TypeError, KeyError): ingestion = {"status":"changed", "notice":"Signed delivery evidence is missing or changed; investigate before activation."}
        available = job["status"] == "validated" and profile["status"] == "approved" and (ingestion is None or ingestion["status"] == "consistent")
        return {"id": job_id, **deepcopy(job), "activation_available": available, "receipt_integrity": receipt_integrity(job, job_id), "ingestion_evidence": ingestion,
                "notice": "Availability is indicative; activation rechecks authorization, profile integrity, pause state and current graph."}


def activate(actor, job_id):
    with bridge.mutation(actor, True):
        job = bridge.get(job_id, "BridgeEventJob")
        if job["status"] == "activated":
            return {"status": "activated", "idempotent": True}
        profile = _check(job, job_id)
        if profile["status"] != "approved":
            raise PermissionError("Approved event profile required")
        if job["status"] != "validated":
            raise ValueError("Validate the event batch first")
        checked = preview(job, job_id)
        signature = validation_hash(job, checked, job_id)
        if checked != job["preview"] or signature != job.get("validation_hash") or any(row["status"] == "quarantined" for row in checked):
            raise ValueError("Event review changed; validate again")
        system = bridge.get(job["system_id"], "BridgeSystem")
        activated_at, created = bridge.now(), []
        for item in checked:
            if item["status"] == "duplicate":
                continue
            # No unresolved identity or existing-record update is permitted.
            if item.get("effect") not in {"create", "history_only"}:
                raise ValueError("Unsupported event projection; review required")
            target_id = item["target_id"] if item["effect"] == "history_only" else bridge.add("Lead", graph_values("Lead", item["values"]))
            key = item["source_key"]
            event_id = "BRE-" + bridge.digest(["creation", key, item["occurred_at"], item["fingerprint"]])
            if ledger.get_entity(event_id):
                raise ValueError("Event identity already exists without its reviewed source link")
            bridge.put(Entity(event_id, "SourceObservation", {"workspace_id": ledger.tenant.workspace_id,
                "origin": "dealer_bridge", "entity_id": target_id, "timestamp": item["occurred_at"], "evidence_kind": "observed",
                "source_system": system["vendor"], "source_id": item["external_id"], "source_timestamp": item["occurred_at"],
                "source_time_semantics": "created", "source_namespace": item["source_namespace"], "import_timestamp": activated_at,
                "confidence": 1.0, "identity_resolution": item.get("identity_resolution", "new"), "identity_review_id": item.get("identity_review_id"), "raw_reference": job_id,
                "system_id": job["system_id"], "external_key": key, "object_type": "adf_prospects",
                "mapping_id": job["profile_id"], "source_transport": job.get("transport", "manual_adf"), "ingestion_receipt_id": job.get("inbound_receipt_id"), "canonical_kind": "Lead", "values": deepcopy(item["values"]), "delivery_status": "pending"}))
            bridge.put(Entity("BEX-" + key, "BridgeEventExternalID", {"workspace_id": ledger.tenant.workspace_id,
                "system_id": job["system_id"], "source_namespace": item["source_namespace"], "external_id": item["external_id"],
                "target_id": target_id, "event_id": event_id, "occurred_at": item["occurred_at"], "time_semantics": "created",
                "fingerprint": item["fingerprint"]}))
            created.append({"event_id": event_id, "canonical_id": target_id, "projection": item["effect"]})
        receipt = {"version": 1, "job_id": job_id, "profile_id": job["profile_id"], "profile_hash": job["profile_hash"],
                   "profile_proposed_by": profile["proposed_by"], "profile_approved_by": profile["approved_by"],
                   "profile_approved_at": profile["approved_at"], "source_evidence": deepcopy(job["source_evidence"]),
                   "rows_hash": job["rows_hash"], "validation_hash": signature, "time_semantics": "created",
                   "staged_by": job["created_by"], "validated_by": job["validated_by"],
                   "activated_by": actor["employee_id"], "activated_at": activated_at, "created": created,
                   "identity_review_ids": sorted({row["identity_review_id"] for row in checked if row.get("identity_review_id")}),
                   "duplicate_rows": sum(row["status"] == "duplicate" for row in checked)}
        receipt.update(staged_principal=job.get("created_principal"), transport=job.get("transport", "manual_adf"))
        ingestion = delivery_evidence(job_id, job)
        if ingestion is not None: receipt["ingestion_evidence"] = ingestion
        receipt["checksum"] = bridge.digest(receipt)
        job.update(status="activated", activated_at=activated_at, activated_by=actor["employee_id"], activation_receipt=receipt)
        system.update(phase="active", last_success_at=activated_at, import_health={"status": "ready", "transport": job.get("transport", "manual_adf")})
        bridge.audit(actor, "event_import.activate", job_id)
    return {"status": "activated", "created": sum(item["projection"] == "create" for item in created), "observations": len(created)}


def review_identity(actor, job_id, row_number, action, target_id, reason, candidate_signature):
    reason = bridge.review_reason(reason)
    if not isinstance(action, str) or action not in {"link", "keep_separate"} or type(row_number) is not int:
        raise ValueError("Explicit identity action and row required")
    with bridge.mutation(actor, True):
        job = bridge.get(job_id, "BridgeEventJob")
        if job["status"] in {"activated", "cancelled"}:
            raise ValueError("Finished event import cannot change identity decisions")
        _check(job, job_id)
        if not 1 <= row_number <= len(job["rows"]):
            raise ValueError("Event row is unavailable")
        item = preview(job, job_id, apply_decisions=False)[row_number - 1]
        if item.get("error_code") != "identity_review_required" or item.get("candidate_signature") != candidate_signature:
            raise ValueError("Identity candidates changed; validate and review again")
        if action == "link" and target_id not in item["candidates"] or action == "keep_separate" and target_id is not None:
            raise ValueError("Choose an existing candidate for linking, or no target for keeping separate")
        decisions = job.setdefault("identity_reviews", {})
        previous = decisions.get(str(row_number))
        if previous:
            prior = bridge.get(previous, "BridgeEventIdentityReview")
            if prior.get("job_id") != job_id or prior.get("row_number") != row_number:
                raise ValueError("Identity decision does not belong to this row")
            prior["status"] = "superseded"
        decision_id = bridge.add("BridgeEventIdentityReview", {"job_id": job_id, "row_number": row_number,
            "row_hash": bridge.digest(job["rows"][row_number - 1]), "profile_hash": job["profile_hash"],
            "candidate_signature": candidate_signature, "action": action, "target_id": target_id, "reason": reason,
            "reviewed_by": actor["employee_id"], "reviewed_at": bridge.now(), "status": "active"})
        decisions[str(row_number)] = decision_id
        job.update(status="staged", preview=[])
        job.pop("validation_hash", None)
        bridge.audit(actor, "event_import.identity.review", decision_id)
    return {"id": decision_id, "next_step": "validate"}


def withdraw_identity(actor, job_id, row_number, reason):
    reason = bridge.review_reason(reason)
    with bridge.mutation(actor, True):
        job = bridge.get(job_id, "BridgeEventJob")
        if job["status"] in {"activated", "cancelled"}:
            raise ValueError("Finished event import cannot change identity decisions")
        decision_id = job.get("identity_reviews", {}).get(str(row_number))
        if not decision_id:
            raise ValueError("Identity decision unavailable")
        decision = bridge.get(decision_id, "BridgeEventIdentityReview")
        if decision.get("job_id") != job_id or decision.get("row_number") != row_number:
            raise ValueError("Identity decision does not belong to this import")
        decision.update(status="withdrawn", withdrawn_by=actor["employee_id"], withdrawn_at=bridge.now(), withdraw_reason=reason)
        del job["identity_reviews"][str(row_number)]
        job.update(status="staged", preview=[])
        job.pop("validation_hash", None)
        bridge.audit(actor, "event_import.identity.withdraw", decision_id)
    return {"status": "withdrawn", "next_step": "validate"}


def list_jobs(actor, system_id, limit=25, before_id=None):
    bridge.authorize(actor)
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("Event import page size must be between 1 and 100")
    if before_id is not None and (not isinstance(before_id, str) or not before_id or len(before_id) > 120):
        raise ValueError("Use an event import cursor from this system")
    with bridge.LOCK:
        bridge.get(system_id, "BridgeSystem")
        jobs = [e for e in list(ledger.get_all().values()) if e.entity_type == "BridgeEventJob" and
                e.attributes.get("workspace_id") == ledger.tenant.workspace_id and e.attributes.get("system_id") == system_id]
        jobs.sort(key=lambda e: (e.attributes["created_at"], e.id), reverse=True)
        start = 0
        if before_id is not None:
            positions = [i for i, e in enumerate(jobs) if e.id == before_id]
            if not positions:
                raise ValueError("Event import cursor does not belong to this system")
            start = positions[0] + 1
        page = jobs[start:start + limit]
        return {"jobs": [{"id": e.id, **{field: e.attributes[field] for field in ("profile_id", "status", "created_at", "created_by")},
                           "row_count": e.attributes.get("payload_cleanup", {}).get("row_count", len(e.attributes["rows"])),
                           "payload_removed": bool(e.attributes.get("payload_cleanup"))} for e in page],
                "next_before_id": page[-1].id if start + len(page) < len(jobs) else None, "total_jobs": len(jobs)}


def receipt_integrity(job, job_id):
    receipt = job.get("activation_receipt")
    if not isinstance(receipt, dict):
        return "not_recorded"
    try:
        consistent = (job.get("status") == "activated" and receipt.get("job_id") == job_id and
                      receipt.get("activated_by") == job.get("activated_by") and receipt.get("activated_at") == job.get("activated_at") and
                      bridge.digest(job.get("source_evidence")) == job.get("source_evidence_hash") and
                      receipt.get("checksum") == bridge.digest({key: value for key, value in receipt.items() if key != "checksum"}) and
                      all(receipt.get(field) == job.get(field) for field in ("profile_id", "profile_hash", "rows_hash", "source_evidence", "validation_hash")))
        consistent = (consistent and receipt.get("staged_by") == job.get("created_by") and
                      receipt.get("validated_by") == job.get("validated_by"))
        ingestion = delivery_evidence(job_id, job)
        consistent = consistent and receipt.get("ingestion_evidence") == ingestion
        if "staged_principal" in receipt:
            consistent = consistent and receipt["staged_principal"] == job.get("created_principal") and receipt.get("transport") == job.get("transport", "manual_adf")
        if job.get("payload_cleanup"):
            consistent = consistent and job.get("rows") == [] and job.get("preview") == []
        else:
            consistent = (consistent and bridge.digest(job.get("rows")) == job.get("rows_hash") and
                          validation_hash(job, job.get("preview"), job_id) == job.get("validation_hash"))
    except (TypeError, ValueError, KeyError):
        consistent = False
    return "consistent" if consistent else "changed"


def lineage(actor, system_id, source_namespace, external_id):
    bridge.authorize(actor)
    for value, bound in ((source_namespace, 120), (external_id, 500)):
        if not isinstance(value, str) or not value.strip() or value != value.strip() or len(value) > bound:
            raise ValueError("Exact bounded provider namespace and source ID required")
    with bridge.LOCK:
        system = bridge.get(system_id, "BridgeSystem")
        key = source_key(system_id, {"source_namespace": source_namespace, "external_id": external_id})
        link = bridge.get("BEX-" + key, "BridgeEventExternalID")
        target = ledger.get_entity(link.get("target_id"))
        event = bridge.get(link.get("event_id"), "SourceObservation")
        if (link.get("system_id") != system_id or link.get("source_namespace") != source_namespace or link.get("external_id") != external_id or
                not target or target.entity_type != "Lead" or target.attributes.get("workspace_id", ledger.tenant.workspace_id) != ledger.tenant.workspace_id or
                event.get("entity_id") != target.id or event.get("external_key") != key or event.get("origin") != "dealer_bridge" or
                event.get("source_time_semantics") != "created" or event.get("source_namespace") != source_namespace or
                bridge.digest([event.get("source_timestamp"), "created", event.get("values")]) != link.get("fingerprint")):
            raise ValueError("Event source identity is inconsistent; operator review required")
        job = bridge.get(event["raw_reference"], "BridgeEventJob")
        if job["system_id"] != system_id or job["profile_id"] != event["mapping_id"]:
            raise ValueError("Event import evidence is inconsistent; operator review required")
        current, conflicts = snapshot("Lead", target.attributes)
        return {"canonical_id": target.id, "kind": "Lead", "current_values": current, "legacy_conflicts": conflicts,
                "source": {"system_id": system_id, "system_name": system["name"], "source_namespace": source_namespace, "external_id": external_id},
                "observation": {"event_id": link["event_id"], "occurred_at": event["source_timestamp"], "time_semantics": "created",
                                "imported_at": event["import_timestamp"], "values": deepcopy(event["values"]),
                                "identity_resolution": event.get("identity_resolution"), "identity_review_id": event.get("identity_review_id"),
                                "profile_id": event["mapping_id"], "job_id": event["raw_reference"]},
                "receipt_integrity": receipt_integrity(job, event["raw_reference"]),
                "notice": "Creation facts preserve the imported source event. Current lead values may include later dealership edits; this is not a complete as-of reconstruction."}



def observation_lineage(actor, event_id):
    """Resolve retained creation history without requiring a staging-row copy."""
    bridge.authorize(actor)
    with bridge.LOCK:
        event = bridge.get(event_id, "SourceObservation")
        if event.get("origin") != "dealer_bridge" or event.get("source_time_semantics") != "created":
            raise ValueError("Observation is not a Bridge creation event")
        result = lineage(actor, event.get("system_id"), event.get("source_namespace"), event.get("source_id"))
        if result["observation"]["event_id"] != event_id:
            raise ValueError("Observation source identity is inconsistent; operator review required")
        return result
