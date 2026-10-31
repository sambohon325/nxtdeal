"""Synthetic fixtures only; preflight must never modify or disclose source payloads."""
import json
from uuid import uuid4

import pytest

from db.import_preflight import preflight, read_source

WORKSPACE = str(uuid4())


def graph():
    return {'entities':[{'id':'A','entity_type':'Customer','attributes':{'secret':'DO_NOT_DISCLOSE','nested':[1,None,True]}}],
            'relationships':[{'source_id':'A','target_id':'A','relationship_type':'owns','created_by':None,'created_at':'legacy time'}]*2}


def write(tmp_path, value, name='graph.json'):
    path = tmp_path / name
    path.write_text(json.dumps(value), encoding='utf-8')
    return path


def test_valid_preflight_preserves_sources_and_duplicate_relationships(tmp_path):
    path = write(tmp_path, graph())
    before, stat = path.read_bytes(), path.stat().st_mtime_ns
    report = preflight(path, WORKSPACE)
    assert report['valid'] and not report['database_written']
    assert report['counts'] == {'entities':1,'relationships':2}
    assert report['audit_integrity'] == 'not_verified'
    assert 'DO_NOT_DISCLOSE' not in json.dumps(report)
    assert 'legacy time' not in json.dumps(report)
    assert path.read_bytes() == before and path.stat().st_mtime_ns == stat


@pytest.mark.parametrize('raw,code', [
    ('null','unexpected_fields_or_shape'),
    ('[]','unexpected_fields_or_shape'),
    ('{"entities":[],"relationships":null}','expected_arrays'),
    ('{"entities":[],"entities":[],"relationships":[]}','duplicate_object_key'),
    ('{"entities":[],"relationships":[],"customer-secret":true}','unexpected_fields_or_shape'),
    ('{"entities":[','invalid_json'),
    ('{"x":NaN}','nonfinite_number'),
    ('{"x":1e131072}','numeric_out_of_range'),
    ('{"x":1e-16384}','numeric_out_of_range'),
    ('{"x":"\\u0000"}','invalid_jsonb_text'),
    ('{"x":"\\ud800"}','invalid_jsonb_text'),
])
def test_invalid_source_is_reported_without_payload(tmp_path, raw, code):
    path = tmp_path / 'input.json'
    path.write_text(raw, encoding='utf-8')
    report = preflight(path, WORKSPACE)
    assert not report['valid']
    assert report['discrepancies'][0]['code'] == code
    assert 'customer-secret' not in json.dumps(report)
    assert path.read_text(encoding='utf-8') == raw


def test_duplicates_dangling_and_unknown_fields_are_not_silently_fixed(tmp_path):
    value = graph()
    value['entities'].append(value['entities'][0])
    value['relationships'][0] = {**value['relationships'][0], 'target_id':'missing'}
    value['relationships'].append({'unknown':'DO_NOT_DISCLOSE'})
    report = preflight(write(tmp_path,value), WORKSPACE)
    assert {v['code'] for v in report['discrepancies']} == {'duplicate_entity_id','dangling_endpoint','unexpected_fields_or_shape'}
    assert 'DO_NOT_DISCLOSE' not in json.dumps(report)


def test_semantic_digest_ignores_format_and_number_spelling_not_array_order(tmp_path):
    first = tmp_path/'first.json'
    second = tmp_path/'second.json'
    first.write_text('{"a":[1.0,2],"b":-0}', encoding='utf-8')
    second.write_text(' { "b":0.0,"a":[1,2.00]} ', encoding='utf-8')
    _, a = read_source(first)
    _, b = read_source(second)
    assert a['sha256'] != b['sha256']
    assert a['semantic_sha256'] == b['semantic_sha256']
    second.write_text('{"a":[2,1],"b":0}', encoding='utf-8')
    assert read_source(second)[1]['semantic_sha256'] != a['semantic_sha256']


@pytest.mark.parametrize('timestamp,valid', [('2026-10-01T10:00:00Z',True),('2026-10-01T05:00:00-05:00',True),('2026-10-01',False),('not-a-time',False)])
def test_audit_timestamp_requires_explicit_offset_and_payload_is_retained(tmp_path, timestamp, valid):
    path = write(tmp_path, graph())
    event = {'id':'AUDIT-1','event_type':'changed','entity_id':'A','actor':'EMP-1','summary':'DO_NOT_DISCLOSE','details':{},'timestamp':timestamp,'hash':'','prev_hash':''}
    audit = write(tmp_path, [event], 'audit.json')
    report = preflight(path,WORKSPACE,audit)
    assert report['valid'] is valid
    assert report['counts']['audit_events'] == 1
    assert report['audit_integrity'] == ('legacy_unverifiable' if valid else 'not_verified')
    assert 'DO_NOT_DISCLOSE' not in json.dumps(report)
    assert read_source(audit)[0] == [event]


def test_null_audit_unreadable_file_and_invalid_workspace_fail_closed(tmp_path):
    path = write(tmp_path, graph())
    audit = write(tmp_path, None, 'audit.json')
    assert not preflight(path,WORKSPACE,audit)['valid']
    assert preflight(tmp_path/'missing',WORKSPACE)['discrepancies'][0]['code'] == 'unreadable_source'
    with pytest.raises(ValueError):
        preflight(path,'not-a-uuid')
