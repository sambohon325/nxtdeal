import copy
import hashlib
import json
from uuid import uuid4

import pytest

from db.import_audit import GENESIS, verify_audit
from db.import_preflight import preflight


def chain():
    events = []
    for index in range(3):
        event = {'id':f'PRIVATE-ID-{index}', 'event_type':'changed','entity_id':None,
                 'actor':'PRIVATE-ACTOR', 'summary':'PRIVATE-SUMMARY',
                 'details':{'float':1.0,'unicode':'é','big':9007199254740993},
                 'timestamp':'2026-10-01T12:00:00+00:00',
                 'prev_hash':events[-1]['hash'] if events else GENESIS}
        # Independent reproduction of the existing writer's encoding contract.
        event['hash'] = hashlib.sha256(json.dumps(event, sort_keys=True, default=str).encode()).hexdigest()
        events.append(event)
    return events


def checkpoint(events):
    return {'event_count':len(events),'last_event_id':events[-1]['id'] if events else None,
            'last_hash':events[-1]['hash'] if events else GENESIS,'checkpointed_at':'2026-10-01T12:01:00Z'}


def test_valid_chain_checkpoint_and_native_number_serialization(tmp_path):
    events = chain()
    graph, audit, anchor = [tmp_path/name for name in ('graph.json','audit.json','checkpoint.json')]
    graph.write_text('{"entities":[],"relationships":[]}',encoding='utf-8')
    audit.write_text(json.dumps(events),encoding='utf-8')
    anchor.write_text(json.dumps(checkpoint(events)),encoding='utf-8')
    before = {path:path.read_bytes() for path in (graph,audit,anchor)}
    report = preflight(graph,str(uuid4()),audit,anchor)
    assert report['valid'] and report['audit_integrity'] == 'chain_and_checkpoint_match'
    assert report['audit_verification']['verified_events'] == 3
    assert 'PRIVATE' not in json.dumps(report)
    assert all(path.read_bytes() == value for path,value in before.items())


@pytest.mark.parametrize('change,code', [
    ('content','content_hash_mismatch'), ('remove','broken_link'), ('reorder','broken_genesis'),
    ('unhashed','unhashed_event_inside_chain'), ('encoding','invalid_hash_encoding'),
])
def test_altered_history_is_detected_and_not_repaired(change,code):
    events = chain()
    if change == 'content': events[1]['summary'] = 'altered'
    if change == 'remove': events.pop(1)
    if change == 'reorder': events.reverse()
    if change == 'unhashed': events[1]['hash'] = ''
    if change == 'encoding': events[1]['hash'] = 'not-a-hash'
    before = copy.deepcopy(events)
    result = verify_audit(events)
    assert result['status'] == 'invalid'
    assert code in {issue['code'] for issue in result['issues']}
    assert events == before and 'PRIVATE' not in json.dumps(result)


def test_checkpoint_detects_truncation_but_missing_anchor_is_not_full_verification():
    events = chain()
    assert verify_audit(events)['status'] == 'chain_only'
    assert verify_audit(events[:-1],checkpoint(events))['checkpoint'] == 'mismatched'
    assert verify_audit([],checkpoint([]))['status'] == 'empty'


@pytest.mark.parametrize('bad', [None,[],{}, {'event_count':True,'last_event_id':None,'last_hash':GENESIS,'checkpointed_at':'2026-10-01T12:00:00Z'}])
def test_explicit_malformed_checkpoint_is_invalid(bad):
    assert verify_audit([],bad,checkpoint_provided=True)['status'] == 'invalid'


def test_legacy_prefix_remains_unverifiable():
    events = chain()
    legacy = {**events[0], 'id':'older', 'hash':'', 'prev_hash':''}
    result = verify_audit([legacy]+events)
    assert result['status'] == 'legacy_unverifiable'
    assert result['legacy_events'] == 1 and result['verified_events'] == 3


def test_checkpoint_requires_audit_and_null_checkpoint_is_not_missing(tmp_path):
    graph, audit, anchor = [tmp_path/name for name in ('graph.json','audit.json','checkpoint.json')]
    graph.write_text('{"entities":[],"relationships":[]}',encoding='utf-8')
    audit.write_text('[]',encoding='utf-8')
    anchor.write_text('null',encoding='utf-8')
    assert not preflight(graph,str(uuid4()),checkpoint_path=anchor)['valid']
    assert not preflight(graph,str(uuid4()),audit,anchor)['valid']
