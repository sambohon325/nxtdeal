"""Pure committed-graph comparison; no storage, runtime activation or repair.

Generation/workspace bindings must come from a trusted commit journal, not clients.
This is graph parity only: it does not certify audit history or authority.
"""
from dataclasses import dataclass, field
from uuid import UUID

from db.import_package import ImportPackage, ImportRejected


class ShadowRejected(ValueError):
    """Fixed redacted codes only."""


@dataclass(frozen=True)
class GraphObservation:
    workspace_id: str
    generation: int
    graph_bytes: bytes = field(repr=False)

    def evidence(self):
        if type(self.generation) is not int or not 1 <= self.generation <= 2**63 - 1:
            raise ShadowRejected('invalid_generation')
        try:
            manifest = ImportPackage(self.workspace_id, 'graph_only', self.graph_bytes).manifest()
        except ImportRejected:
            raise ShadowRejected('invalid_graph_observation') from None
        return {'workspace_id': manifest['workspace_id'], 'generation': self.generation,
                'semantic_sha256': manifest['sources']['graph']['semantic_sha256'],
                'counts': manifest['counts']}


def compare_committed_graphs(authority, shadow, *, workspace_id):
    """Compare a captured JSON commit with its PostgreSQL snapshot observation.

    A lag/ahead result must never count as a successful parity comparison. Arrays
    retain order and duplicates. Reports contain no payloads, IDs or source paths.
    """
    try:
        workspace = str(UUID(workspace_id))
    except (ValueError, TypeError, AttributeError):
        raise ShadowRejected('invalid_workspace') from None
    if type(authority) is not GraphObservation or (shadow is not None and type(shadow) is not GraphObservation):
        raise ShadowRejected('observation_required')
    primary = authority.evidence()
    secondary = shadow.evidence() if shadow is not None else None
    if primary['workspace_id'] != workspace or (secondary and secondary['workspace_id'] != workspace):
        raise ShadowRejected('workspace_mismatch')
    if secondary is None:
        status = 'missing'
    elif secondary['generation'] < primary['generation']:
        status = 'lagging'
    elif secondary['generation'] > primary['generation']:
        status = 'ahead'
    elif secondary['semantic_sha256'] != primary['semantic_sha256']:
        status = 'divergent'
    else:
        status = 'matched'
    return {'format_version': 1, 'scope': 'graph_only', 'workspace_id': workspace,
            'status': status, 'authority': primary, 'shadow': secondary}
