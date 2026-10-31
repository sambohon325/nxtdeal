"""Experimental live-object compatibility session; no runtime activation/save.

Only explicit snapshot capture is supported. Callers must separately coordinate
JSON-authoritative saves; this class cannot bypass that boundary through save().
"""
from decimal import Decimal
from core.entities import Entity
from core.relationships import Relationship
from core.json_graph_repository import JsonGraphRepository
from db.import_preflight import canonical, InvalidSource, MAX_DEPTH
from db.shadow_compare import GraphObservation, ShadowRejected
from db.shadow_normalized import load_test_normalized


def _capture_numbers(value, depth=0):
    if depth > MAX_DEPTH:
        raise InvalidSource('nesting_limit')
    if type(value) in (int,float):
        # Match native JSON's decimal rendering of Python floats without
        # rounding already-exact Decimal values loaded from PostgreSQL.
        return Decimal(str(value))
    if isinstance(value,list):
        return [_capture_numbers(item,depth+1) for item in value]
    if isinstance(value,dict):
        return {key:_capture_numbers(item,depth+1) for key,item in value.items()}
    return value


class NormalizedTestSession(JsonGraphRepository):
    def load_from_test_database(self, connection):
        generation, graph = load_test_normalized(connection,workspace_id=self.tenant.workspace_id)
        # Match legacy load: overwrite matching entities, retain others, append
        # relationships. Reads thereafter expose the same mutable instances.
        for row in graph['entities']:
            self.add_entity(Entity(**row))
        for row in graph['relationships']:
            self.add_relationship(Relationship(**row))
        return generation

    def capture_snapshot(self):
        graph = dict(entities=[dict(id=e.id,entity_type=e.entity_type,attributes=e.attributes)
                               for e in self.entities.values()],
                     relationships=[dict(source_id=r.source_id,target_id=r.target_id,
                                         relationship_type=r.relationship_type,created_by=r.created_by,
                                         created_at=r.created_at) for r in self.relationships])
        snapshot = canonical(_capture_numbers(graph)).encode('utf-8')
        GraphObservation(self.tenant.workspace_id,1,snapshot).evidence()
        return snapshot

    def save(self, filepath):
        raise ShadowRejected('runtime_save_disabled')

    def load(self, filepath):
        raise ShadowRejected('runtime_load_disabled')
