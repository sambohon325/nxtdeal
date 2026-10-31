"""Current mutable graph and whole-file persistence, bound to one workspace.

Paths still come from legacy callers. This is not shared-hosting isolation.
"""

import json
import os
from copy import deepcopy
from threading import RLock

from core.entities import Entity
from core.relationships import Relationship
from core.tenant_context import TenantContext


def demo_persistence_disabled():
    return os.environ.get("DEALEROS_DEMO", "").strip().lower() in ("1", "true", "yes", "on")


class JsonGraphRepository:
    def __init__(self, tenant: TenantContext):
        if not isinstance(tenant, TenantContext):
            raise TypeError("An explicit TenantContext is required")
        self._tenant = tenant
        self._persistence_lock = RLock()
        self.entities = {}
        self.relationships = []

    @property
    def tenant(self):
        return self._tenant

    def add_entity(self, entity):
        self.entities[entity.id] = entity

    def get_entity(self, entity_id):
        return self.entities.get(entity_id)

    def get_all(self):
        return self.entities

    def add_relationship(self, relationship):
        self.relationships.append(relationship)

    def get_relationships(self):
        return self.relationships

    def get_entity_relationships(self, entity_id):
        return [r for r in self.relationships if r.source_id == entity_id or r.target_id == entity_id]

    def reset(self):
        self.entities = {}
        self.relationships = []

    def persistence_guard(self):
        """Serialize saves and participating mutation/rollback boundaries.

        This is process-local. Legacy callers still receive live objects and
        must opt into this guard for their mutations to share this boundary.
        """
        return self._persistence_lock

    def save(self, filepath):
        if demo_persistence_disabled():
            return
        with self.persistence_guard():
            self._save(filepath)

    def _save(self, filepath):
        data = {
            "entities": [
                {"id": e.id, "entity_type": e.entity_type, "attributes": e.attributes}
                for e in self.entities.values()
            ],
            "relationships": [
                {"source_id": r.source_id, "target_id": r.target_id,
                 "relationship_type": r.relationship_type,
                 "created_by": r.created_by, "created_at": r.created_at}
                for r in self.relationships
            ],
        }
        # JSON encoding must not follow live attribute dictionaries after the
        # snapshot is captured. Legacy writers can still mutate those objects.
        data = deepcopy(data)
        # The guard covers the snapshot and swap, not just the temporary file.
        # Separate processes/repositories targeting one path remain unsupported.
        tmp_path = filepath + ".tmp"
        parent = os.path.dirname(filepath)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(tmp_path, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=4)
            # Fail before replacing the previous snapshot if the OS cannot
            # flush this file. Atomic replacement alone does not flush data.
            # Directory/remote-storage durability remains deployment-specific.
            file.flush()
            os.fsync(file.fileno())
        os.replace(tmp_path, filepath)

    def load(self, filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as file:
                data = json.load(file)
        except FileNotFoundError:
            print(f"No {filepath} yet — starting with an empty graph.")
            return False
        # Legacy loads merge entities and append relationships without reset.
        for row in data["entities"]:
            self.add_entity(Entity(id=row["id"], entity_type=row["entity_type"], attributes=row["attributes"]))
        for row in data["relationships"]:
            self.add_relationship(Relationship(
                source_id=row["source_id"], target_id=row["target_id"],
                relationship_type=row["relationship_type"],
                created_by=row.get("created_by"), created_at=row.get("created_at"),
            ))
        return True
