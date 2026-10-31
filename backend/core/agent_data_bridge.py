"""Additive normalization seam for existing Data Connections.

Called by trusted import/provider adapters after their field mapping and identity
resolution. Does not resolve identities or copy credentials into the graph.
"""
from dataclasses import asdict
from datetime import datetime
from hashlib import sha256

from chrono.contracts import Observation
from core.dealeros import ledger
from core.entities import Entity
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH


def retain_provenance(connection_id: str, observation: Observation, *, persist=True):
    connection = ledger.get_entity(connection_id)
    target = ledger.get_entity(observation.entity_id)
    if not connection or connection.entity_type != "Connection" or not target:
        raise ValueError("Existing connection and normalized target entity required")
    if observation.evidence_kind not in {"observed", "derived", "ai_inferred", "predicted"}:
        raise ValueError("Invalid evidence kind")
    if observation.confidence is not None and not 0 <= observation.confidence <= 1:
        raise ValueError("Confidence must be between zero and one")
    for field in ("timestamp", "source_timestamp", "import_timestamp"):
        if field == "source_timestamp" and observation.source_timestamp is None:
            continue
        if datetime.fromisoformat(getattr(observation, field)).tzinfo is None:
            raise ValueError("Provenance timestamps must include a timezone")
    if not observation.source_id or not observation.source_system:
        raise ValueError("Source identity is required")
    payload = asdict(observation)
    # Append observations; never replace the customer's source history.
    identity = "|".join([connection_id, observation.entity_id, observation.source_system,
                         observation.source_id, observation.source_timestamp or observation.import_timestamp, observation.evidence_kind])
    event_id = "AFSRC-" + sha256(identity.encode()).hexdigest()
    existing = ledger.get_entity(event_id)
    if existing:
        return existing.id
    ledger.add_entity(Entity(event_id, "SourceObservation", {
        **payload, "connection_id": connection_id, "workspace_id": ledger.tenant.workspace_id,
    }))
    if persist:
        save_graph(GRAPH_PATH)
    return event_id


def record_import(connection_id, previous_ids, content_digest, imported_at):
    """Attach provenance to the exact new entities produced by existing CSV importers."""
    from core.agent_events import emit
    for entity in list(ledger.get_all().values()):
        if entity.id in previous_ids or entity.entity_type in {"SourceObservation", "AgentEvent"}:
            continue
        source_id = next((str(entity.attributes[k]) for k in (
            "LeadID", "CustomerID", "ServiceID", "ContractID", "PartID", "VIN") if entity.attributes.get(k)), entity.id)
        retain_provenance(connection_id, Observation(
            entity.id, imported_at, "observed", connection_id, source_id,
            None, imported_at, identity_resolution="existing_importer_mapping",
            raw_reference=f"sha256:{content_digest}",
        ), persist=False)
        if entity.entity_type == "Lead":
            emit("lead.created", entity.id, content_digest)
