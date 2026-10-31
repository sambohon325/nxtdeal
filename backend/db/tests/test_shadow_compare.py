import json
from dataclasses import replace
from uuid import uuid4

import pytest

from db.shadow_compare import GraphObservation, ShadowRejected, compare_committed_graphs

WORKSPACE = '11111111-1111-1111-1111-111111111111'
GRAPH = b'{"entities":[{"id":"PRIVATE-A","entity_type":"Customer","attributes":{"private":"PRIVATE-PAYLOAD","value":1.2300}}],"relationships":[]}'


def observation(generation=1, graph=GRAPH):
    return GraphObservation(WORKSPACE, generation, graph)


def compare(a,b):
    return compare_committed_graphs(a,b,workspace_id=WORKSPACE)


def test_semantic_match_and_redacted_evidence():
    original = observation()
    report = compare(original, observation(graph=GRAPH.replace(b'1.2300',b'1.23') + b'\n'))
    assert report['status'] == 'matched'
    assert report['scope'] == 'graph_only'
    assert 'PRIVATE' not in json.dumps(report)
    assert 'PRIVATE' not in repr(original)
    report['authority']['counts'].clear()
    assert compare(original, original)['authority']['counts']


@pytest.mark.parametrize('generation,status',[(1,'lagging'),(2,'matched'),(3,'ahead')])
def test_generation_is_required_even_when_data_is_identical(generation,status):
    assert compare(observation(2),observation(generation))['status'] == status


def test_missing_is_not_parity():
    assert compare(observation(),None)['status'] == 'missing'


def test_exact_decimal_change_is_divergence():
    a = observation(graph=GRAPH.replace(b'1.2300',b'0.123456789012345678901'))
    b = observation(graph=GRAPH.replace(b'1.2300',b'0.123456789012345678902'))
    assert compare(a,b)['status'] == 'divergent'


def test_relationship_multiplicity_and_optional_field_presence():
    link = b'{"source_id":"PRIVATE-A","target_id":"PRIVATE-A","relationship_type":"owns"}'
    a = observation(graph=GRAPH.replace(b'"relationships":[]',b'"relationships":[' + link + b']'))
    duplicate = replace(a,graph_bytes=a.graph_bytes.replace(link,link+b','+link))
    provenance = replace(a,graph_bytes=a.graph_bytes.replace(link,link[:-1]+b',"created_by":null}'))
    assert compare(a,duplicate)['status'] == 'divergent'
    assert compare(a,provenance)['status'] == 'divergent'


@pytest.mark.parametrize('generation',[0,-1,True,1.0,'1',2**63])
def test_invalid_generation_is_rejected(generation):
    with pytest.raises(ShadowRejected,match='^invalid_generation$'):
        compare(observation(),observation(generation))


@pytest.mark.parametrize('graph',[b'{',b'{"entities":[],"entities":[],"relationships":[]}',bytearray(GRAPH)])
def test_invalid_observation_is_not_reported_as_divergence(graph):
    with pytest.raises(ShadowRejected,match='^invalid_graph_observation$'):
        compare(observation(),observation(graph=graph))


@pytest.mark.parametrize('side',['authority','shadow'])
def test_cross_workspace_is_rejected(side):
    a,b = observation(),observation()
    if side == 'authority':
        a = replace(a,workspace_id=str(uuid4()))
    else:
        b = replace(b,workspace_id=str(uuid4()))
    with pytest.raises(ShadowRejected,match='^workspace_mismatch$'):
        compare(a,b)


def test_observation_contract_and_explicit_workspace():
    with pytest.raises(ShadowRejected,match='^observation_required$'):
        compare({},None)
    with pytest.raises(ShadowRejected,match='^invalid_workspace$'):
        compare_committed_graphs(observation(),None,workspace_id='PRIVATE-invalid')


def test_entity_and_relationship_order_are_part_of_parity():
    entities = [{'id': name, 'entity_type': 'Customer', 'attributes': {}} for name in ('A','B')]
    links = [{'source_id': 'A', 'target_id': 'B', 'relationship_type': name} for name in ('owns','knows')]
    def captured(items, relationships):
        return observation(graph=json.dumps({'entities': items,'relationships': relationships}).encode())
    original = captured(entities,links)
    assert compare(original,captured(list(reversed(entities)),links))['status'] == 'divergent'
    assert compare(original,captured(entities,list(reversed(links))))['status'] == 'divergent'
