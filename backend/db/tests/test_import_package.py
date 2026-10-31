from dataclasses import FrozenInstanceError, replace
from decimal import Decimal
import json
from uuid import uuid4

import pytest

import db.import_package as packages
from db.import_package import ImportPackage, ImportRejected, prepare_import
from db.tests.test_import_audit import chain, checkpoint


def fixtures(tmp_path):
    graph, audit, anchor = [tmp_path/name for name in ('graph.json','audit.json','checkpoint.json')]
    graph.write_text('{"entities":[{"id":"A","entity_type":"Customer","attributes":{"secret":"PRIVATE","amount":0.12345678901234567890123456789}}],"relationships":[]}',encoding='utf-8')
    events = chain()
    audit.write_text(json.dumps(events),encoding='utf-8')
    anchor.write_text(json.dumps(checkpoint(events)),encoding='utf-8')
    return graph, audit, anchor


def test_single_capture_remains_valid_after_files_change(tmp_path, monkeypatch):
    graph,audit,anchor = fixtures(tmp_path)
    actual_read = packages.read_source_bytes
    reads = []
    def tracked(path):
        reads.append(path)
        return actual_read(path)
    monkeypatch.setattr(packages,'read_source_bytes',tracked)
    package = prepare_import(graph,str(uuid4()),audit_path=audit,checkpoint_path=anchor)
    before = package.manifest()
    for path in (graph,audit,anchor):
        path.write_text('changed after capture',encoding='utf-8')
    assert package.manifest() == before
    payload,_ = package.payloads()
    assert payload['entities'][0]['attributes']['amount'] == Decimal('0.12345678901234567890123456789')
    assert reads == [graph,audit,anchor]
    assert 'PRIVATE' not in repr(package) and 'PRIVATE' not in json.dumps(before)


def test_mutating_views_cannot_change_capture_or_manifest(tmp_path):
    graph,audit,anchor = fixtures(tmp_path)
    package = prepare_import(graph,str(uuid4()),audit_path=audit,checkpoint_path=anchor)
    before = package.manifest()
    payload,events = package.payloads()
    payload['entities'].clear()
    events.clear()
    manifest = package.manifest()
    manifest['sources']['graph']['sha256'] = 'changed'
    assert package.manifest() == before
    assert len(package.payloads()[0]['entities']) == 1
    with pytest.raises(FrozenInstanceError):
        package.graph_bytes = b'changed'
    with pytest.raises(ImportRejected,match='immutable_bytes_required'):
        replace(package,graph_bytes=bytearray(package.graph_bytes)).validate()


def test_manifest_is_repeatable_and_workspace_policy_and_source_bound(tmp_path):
    graph,audit,anchor = fixtures(tmp_path)
    workspace = str(uuid4())
    package = prepare_import(graph,workspace,audit_path=audit,checkpoint_path=anchor)
    assert package.manifest() == prepare_import(graph,workspace,audit_path=audit,checkpoint_path=anchor).manifest()
    original = package.manifest()['manifest_sha256']
    assert replace(package,workspace_id=str(uuid4())).manifest()['manifest_sha256'] != original
    assert replace(package,audit_policy='acknowledge_limited').manifest()['manifest_sha256'] != original
    # Whitespace is semantically identical but still a different captured source.
    changed = replace(package,graph_bytes=package.graph_bytes+b' ')
    assert changed.manifest()['manifest_sha256'] != original
    assert changed.manifest()['sources']['graph']['semantic_sha256'] == package.manifest()['sources']['graph']['semantic_sha256']


def test_missing_checkpoint_requires_explicit_policy(tmp_path):
    graph,audit,_ = fixtures(tmp_path)
    with pytest.raises(ImportRejected,match='audit_evidence_incomplete'):
        prepare_import(graph,str(uuid4()),audit_path=audit)
    accepted = prepare_import(graph,str(uuid4()),audit_path=audit,audit_policy='acknowledge_limited')
    assert accepted.manifest()['audit_integrity'] == 'chain_only'


def test_graph_only_must_be_explicit_and_cannot_drop_supplied_audit(tmp_path):
    graph,audit,_ = fixtures(tmp_path)
    with pytest.raises(ImportRejected,match='audit_required'):
        prepare_import(graph,str(uuid4()))
    package = prepare_import(graph,str(uuid4()),audit_policy='graph_only')
    assert package.payloads()[1] is None
    with pytest.raises(ImportRejected,match='graph_only_excludes_audit'):
        prepare_import(graph,str(uuid4()),audit_path=audit,audit_policy='graph_only')


def test_limited_policy_does_not_accept_tampered_evidence(tmp_path):
    graph,audit,anchor = fixtures(tmp_path)
    events = json.loads(audit.read_text())
    events[0]['summary'] = 'tampered'
    audit.write_text(json.dumps(events),encoding='utf-8')
    with pytest.raises(ImportRejected,match='source_discrepancies'):
        prepare_import(graph,str(uuid4()),audit_path=audit,checkpoint_path=anchor,audit_policy='acknowledge_limited')


@pytest.mark.parametrize('change,code', [({'audit_policy':'unknown'},'invalid_audit_policy'),
    ({'workspace_id':'invalid'},'invalid_workspace_uuid'), ({'graph_bytes':None},'graph_required'),
    ({'graph_bytes':b'null'},'source_discrepancies')])
def test_forged_package_is_revalidated(tmp_path, change, code):
    graph,_,_ = fixtures(tmp_path)
    package = prepare_import(graph,str(uuid4()),audit_policy='graph_only')
    with pytest.raises(ImportRejected,match=code):
        replace(package,**change).payloads()
