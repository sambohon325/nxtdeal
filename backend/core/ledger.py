from core.graph_repository import GraphRepositoryProtocol
from core.json_graph_repository import JsonGraphRepository
from core.tenant_context import LEGACY_PROCESS_CONTEXT, TenantContext


class DealerLedger:
    """Stable domain facade over one workspace's canonical graph repository."""

    def __init__(self, repository: GraphRepositoryProtocol | None = None, *, tenant: TenantContext | None = None):
        if repository is not None and tenant is not None and repository.tenant != tenant:
            raise ValueError("Repository and ledger tenant contexts must match")
        self._repository = repository if repository is not None else JsonGraphRepository(
            tenant if tenant is not None else LEGACY_PROCESS_CONTEXT
        )

    @property
    def tenant(self):
        return self._repository.tenant

    @property
    def entities(self):
        return self._repository.entities

    @entities.setter
    def entities(self, value):
        self._repository.entities = value

    @property
    def relationships(self):
        return self._repository.relationships

    @relationships.setter
    def relationships(self, value):
        self._repository.relationships = value

    def add_entity(self, entity):
        return self._repository.add_entity(entity)

    def get_entity(self, entity_id):
        return self._repository.get_entity(entity_id)

    def get_all(self):
        return self._repository.get_all()

    def add_relationship(self, relationship):
        return self._repository.add_relationship(relationship)

    def get_relationships(self):
        return self._repository.get_relationships()

    def get_entity_relationships(self, entity_id):
        return self._repository.get_entity_relationships(entity_id)

    def reset(self):
        """Clear state while retaining the facade held by domain modules."""
        return self._repository.reset()

    def save(self, filepath):
        return self._repository.save(filepath)

    def persistence_guard(self):
        """Share the repository's process-local save boundary with a caller."""
        return self._repository.persistence_guard()

    def load(self, filepath):
        return self._repository.load(filepath)
