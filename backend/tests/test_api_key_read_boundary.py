"""Internal key records must never enter generic graph or AI output."""
import pytest
from core.dealeros import ledger
from core.entities import Entity
from core.relationships import Relationship
from core.entity_types import API_KEY, VEHICLE
from core.permissions import ADMIN, OPERATIONS, SALES
from core.security import can_access_entity
from core import ai_tools, graph_explore, api_keys

@pytest.fixture(autouse=True)
def isolated_graph():
    ledger.reset()
    ledger.add_entity(Entity('KEY-SYNTHETIC', API_KEY, {'key_hash':'synthetic-hash', 'credential_binding':'synthetic-binding', 'employee_id':'EMP-1', 'label':'synthetic-label'}))
    ledger.add_entity(Entity('VEH-SYNTHETIC', VEHICLE, {'Name':'synthetic-label'}))
    ledger.add_relationship(Relationship(source_id='VEH-SYNTHETIC', target_id='KEY-SYNTHETIC', relationship_type='RELATED'))
    yield
    ledger.reset()

@pytest.mark.parametrize('role', [ADMIN, OPERATIONS, SALES])
def test_generic_authorization_denies_key_records(role):
    assert not can_access_entity(role, API_KEY)

def test_admin_ai_reads_and_search_exclude_internal_key_records():
    assert 'error' in ai_tools.get_entity_by_id(ADMIN, 'KEY-SYNTHETIC')
    assert all(e['entity_type'] != API_KEY for e in ai_tools.search_entities(ADMIN, 'synthetic-label'))
    assert all(e['entity_type'] != API_KEY for e in ai_tools.get_related_entities(ADMIN, 'VEH-SYNTHETIC'))

def test_admin_exploration_cannot_return_or_traverse_key_records():
    assert 'error' in graph_explore.explore_entity('KEY-SYNTHETIC', ADMIN, 'EMP-1')
    result = graph_explore.explore_entity('VEH-SYNTHETIC', ADMIN, 'EMP-1')
    assert 'KEY-SYNTHETIC' not in str(result)
    assert 'synthetic-binding' not in str(result)

def test_dedicated_key_metadata_remains_available_without_internal_material():
    result = api_keys.list_api_keys_for_employee('EMP-1')
    assert len(result) == 1
    assert 'key_hash' not in result[0]
    assert 'credential_binding' not in result[0]
    assert can_access_entity(ADMIN, VEHICLE)
