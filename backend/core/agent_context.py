"""Observed, permission-filtered views over canonical graph relationships."""
from datetime import datetime, timezone

from core.dealeros import ledger
from core.security import can_access_entity


ALIASES = {
    "first_name": ("first_name", "FirstName"), "last_name": ("last_name", "LastName"),
    "year": ("year", "Year"), "make": ("make", "Make"), "model": ("model", "Model"),
    "status": ("status", "PipelineState", "Status"), "name": ("name", "Name"),
    "created_at": ("created_at", "PipelineCreatedAt", "CreatedDate"),
    "last_activity_at": ("last_activity_at", "LastActivityAt", "LastContactDate"),
    "assigned_to": ("assigned_to", "AssignedTo", "AssignedSalesperson"), "department": ("department", "Department"),
    "days_in_stock": ("days_in_stock", "DaysInStock", "DaysOnLot"),
}


def attributes(entity, fields):
    result = {}
    for field in fields:
        for key in ALIASES.get(field, (field,)):
            if key in entity.attributes:
                result[field] = entity.attributes[key]
                break
    if entity.entity_type == 'Lead':
        relations = ledger.get_entity_relationships(entity.id)
        if 'assigned_to' in fields and not result.get('assigned_to'):
            owners = {r.source_id for r in relations if r.relationship_type == 'ASSIGNED_TO'
                      and r.target_id == entity.id and ledger.get_entity(r.source_id)
                      and ledger.get_entity(r.source_id).entity_type == 'Employee'}
            if len(owners) == 1:
                result['assigned_to'] = next(iter(owners))
        if 'customer_ids' in fields:
            candidates = {entity.attributes.get('customer_id'), entity.attributes.get('ConvertedCustomerID')}
            candidates.update(r.target_id for r in relations if r.relationship_type == 'BECAME' and r.source_id == entity.id)
            candidates.update(r.source_id for r in relations if r.relationship_type == 'HAS_LEAD' and r.target_id == entity.id)
            result['customer_ids'] = sorted(k for k in candidates if isinstance(k, str)
                                           and ledger.get_entity(k) and ledger.get_entity(k).entity_type == 'Customer')
        if 'last_activity_at' in fields:
            candidates = [result.get('last_activity_at')]
            candidates.extend(e.attributes.get('created_at') for e in ledger.get_all().values()
                              if e.entity_type == 'FieldNote' and e.attributes.get('linked_entity_id') == entity.id
                              and e.attributes.get('category') in {'call', 'text', 'email', 'video'})
            valid = [(parse_observed_time(v), v) for v in candidates]
            valid = [(t, v) for t, v in valid if t and t <= datetime.now(timezone.utc)]
            if valid:
                result['last_activity_at'] = max(valid, key=lambda item: item[0])[1]
    return result


def parse_observed_time(value):
    try:
        result = datetime.fromisoformat(value)
        return result if result.tzinfo else None
    except (TypeError, ValueError):
        return None


def timeline(actor, record_id, allowed_types, project):
    root = ledger.get_entity(record_id)
    if not root or root.entity_type != "Customer" or not can_access_entity(actor["role"], "Customer"):
        raise ValueError("An accessible customer record is required")
    related = {record_id}
    # Only explicit customer relationships; never traverse a vehicle to all its owners.
    for relation in ledger.get_entity_relationships(record_id):
        other_id = relation.target_id if relation.source_id == record_id else relation.source_id
        other = ledger.get_entity(other_id)
        if other and other.entity_type in allowed_types and can_access_entity(actor["role"], other.entity_type):
            related.add(other_id)
    for entity in ledger.get_all().values():
        if entity.attributes.get("customer_id") == record_id and entity.entity_type in allowed_types and can_access_entity(actor["role"], entity.entity_type):
            related.add(entity.id)
    events = []
    for entity in ledger.get_all().values():
        a = entity.attributes
        if entity.id in related:
            event = project(entity)
            event["timestamp"] = event["attributes"].get("created_at")
            events.append(event)
        elif entity.entity_type == "AgentFabricEvent" and related.intersection(a.get("source_records", [])):
            # Audit details are employee-private; expose only this user's events or admin's view.
            if a.get("user_id") == actor["employee_id"] or actor["role"] == "ADMIN":
                events.append({"id": entity.id, "timestamp": a["timestamp"], "evidence_kind": "observed",
                               "capability": a["capability"], "decision": a["decision"]})
        elif entity.entity_type == "SourceObservation" and a.get("entity_id") in related:
            events.append({"id": entity.id, **{key: a.get(key) for key in (
                "timestamp", "entity_id", "evidence_kind", "source_system", "source_id", "confidence")}})
        elif entity.entity_type in {"Communication", "Appointment", "LeadTask"} and can_access_entity(actor["role"], entity.entity_type):
            if any(a.get(key) in related for key in ("linked_entity_id", "lead_id", "customer_id")):
                # Bodies/transcripts/notes are intentionally not part of department timeline projection.
                events.append({"id": entity.id, "entity_type": entity.entity_type,
                               "timestamp": a.get("created_at"), "evidence_kind": "observed",
                               "status": a.get("status"), "channel": a.get("channel")})
    events.sort(key=lambda e: e.get("timestamp") or "", reverse=True)
    return {"record_id": record_id, "events": events[:200], "total": len(events),
            "source_records": sorted(related), "identity_resolution": "explicit_graph_links"}


def stale_lead(lead):
    status = attributes(lead, ("status",)).get("status", "")
    timestamp = attributes(lead, ("last_activity_at",)).get("last_activity_at")
    observed = parse_observed_time(timestamp)
    if not observed:
        return False, "No timezone-aware last activity observation", timestamp
    if str(status).lower() in {"sold", "lost", "closed", "converted"}:
        return False, "Lead is closed", timestamp
    if str(status).lower() not in {"open", "new", "contacted", "appointment_set", "visited", "proposal", "negotiation", "qualified", "nurturing"}:
        return False, "Lead status is unknown", timestamp
    return (datetime.now(timezone.utc) - observed).total_seconds() >= 48 * 3600, "Lead is not yet stale", timestamp
