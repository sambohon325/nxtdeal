"""Untrusted experiment inputs become private, unreviewed local plans only."""
import json
from copy import deepcopy

import pytest
from chrono.shared.dealership.model import default_experiment, validate
from core.dealership_lab import service as lab, experiment_import as imports
from core.storage import load_graph
from test_dealership_lab import client, auth, make

BASE = '/dealership-lab/experiment-import'


@pytest.mark.parametrize('change', ['password', 'role', 'removed', 'lab-disabled'])
def test_adoption_rechecks_access_after_preview(client, monkeypatch, change):
    from core.auth import credential_store
    from core.dealership_lab import policy
    from fastapi import HTTPException
    headers=auth()
    response=client.post(BASE+'/preview',headers=headers,
                         json={'content':json.dumps(default_experiment())})
    assert response.status_code==200,response.text
    request=dict(preview_id=response.json()['preview_id'],name='Access changed after preview')
    before=deepcopy(lab.ledger.entities)
    if change=='password':
        credential_store.set_credential('LAB-STAFF','Changed-fictional-password2026!',
                                        'SALES',must_change_password=False)
    elif change=='role':
        credential_store.set_role('LAB-STAFF','CUSTOMER')
    elif change=='removed':
        credential_store.credentials.pop('LAB-STAFF')
    else:
        def disabled():
            raise HTTPException(403,'Lab disabled after preview')
        monkeypatch.setattr(policy,'require_enabled',disabled)
    denied=client.post(BASE+'/save',headers=headers,json=request)
    assert denied.status_code==(403 if change=='lab-disabled' else 401),denied.text
    assert lab.ledger.entities==before
    if change=='role':
        # A fresh customer session must not turn a previously valid staff
        # preview into authority to create a plan.
        assert client.post(BASE+'/save',headers=auth(role='CUSTOMER'),json=request).status_code==403
        assert lab.ledger.entities==before


def preview(client, value, employee='LAB-STAFF'):
    return client.post(BASE + '/preview', headers=auth(employee), json={'content': json.dumps(value)})


def test_preview_save_is_private_idempotent_persistent_and_drops_foreign_evidence(client):
    original = make(client)
    model = validate(default_experiment())
    model['workflow'].update(mode='real', selected=True, setup_complete=True,
        setup_steps=['path', 'identity', 'operations', 'data', 'review'],
        review={'baseline': {}, 'note': 'Foreign review is not verified here'})
    wrapper = dict(input=model, owner='OTHER', id='FORGED', result={'profit': 999999999}, runs=['forged'])
    before = deepcopy(wrapper)
    response = preview(client, wrapper)
    assert response.status_code == 200, response.text
    p = response.json()
    assert wrapper == before
    assert len(lab.items(lab.WORKSPACE)) == 1
    assert not p['input']['workflow']['selected']
    assert not p['input']['workflow']['review']
    assert not p['input']['workflow']['setup_complete']
    assert not p['input']['workflow']['setup_steps']
    assert p['provenance']['discarded_baseline_review']
    request = dict(preview_id=p['preview_id'], name='Imported test')
    assert client.post(BASE+'/save', headers=auth('OTHER'), json=request).status_code == 404
    assert client.post(BASE+'/save', json=request).status_code == 401
    saved = client.post(BASE+'/save', headers=auth(), json=request)
    assert saved.status_code == 200, saved.text
    w = saved.json()
    assert w['owner'] == 'LAB-STAFF' and w['parent_id'] is None
    assert 'result' not in w and 'runs' not in w
    assert w['model_definition']['profile'] == model['profile']
    assert w['imported_from']['file_sha256'] == p['provenance']['file_sha256']
    assert client.post(BASE+'/save', headers=auth(), json=request).json()['id'] == w['id']
    assert client.post(BASE+'/save', headers=auth(), json={**request, 'name':'Other'}).status_code == 409
    assert len(lab.items(lab.WORKSPACE)) == 2
    assert lab.serial(lab.workspace(original['id'], 'LAB-STAFF')) == original
    assert len([v for v in lab.items(lab.VERSION) if v.attributes['workspace_id']==w['id']]) == 1
    lab.ledger.reset()
    load_graph(lab.GRAPH_PATH)
    assert lab.workspace(w['id'], 'LAB-STAFF').attributes['imported_from'] == w['imported_from']


def test_raw_wrapper_normalization_and_preview_expiry(client):
    model = default_experiment()
    raw = preview(client, model).json()
    wrapped = preview(client, {'input': model}).json()
    assert raw['input'] == wrapped['input']
    assert raw['provenance']['file_sha256'] != wrapped['provenance']['file_sha256']
    record = lab.ledger.get_entity(raw['preview_id'])
    record.attributes['expires_at'] = '2000-01-01T00:00:00+00:00'
    body = dict(preview_id=raw['preview_id'], name='Expired')
    assert client.post(BASE+'/save', headers=auth(), json=body).status_code == 409
    record.attributes['expires_at'] = '2099-01-01T00:00:00+00:00'
    record.attributes['shared_engine_commit'] = 'foreign-engine'
    assert client.post(BASE+'/save', headers=auth(), json=body).status_code == 409
    assert not lab.items(lab.WORKSPACE)


@pytest.mark.parametrize('content', ['{', '[]', '{"input":null}', '{"a":1,"a":2}',
    '{"a":NaN}', '{"a":1e999}', '['*45+'0'+']'*45, '{"a":"'+'é'*500000+'"}'],
    ids=['syntax', 'array', 'null-input', 'duplicate', 'nan', 'overflow', 'depth', 'utf8-limit'])
def test_bad_files_rejected_without_persisting(client, content):
    response = client.post(BASE+'/preview', headers=auth(), json={'content': content})
    assert response.status_code == 422, response.text
    assert not lab.items(imports.PREVIEW)
    assert not lab.items(lab.WORKSPACE)


@pytest.mark.parametrize('field,value', [('currency','EUR'), ('country','Elsewhere')])
def test_unsupported_model_rejected(client, field, value):
    model = default_experiment()
    model['profile'][field] = value
    assert preview(client, model).status_code == 422


def test_import_requires_staff_and_enabled_lab(client, monkeypatch):
    body = {'content': json.dumps(default_experiment())}
    assert client.post(BASE+'/preview', json=body).status_code == 401
    assert client.post(BASE+'/preview', headers=auth(role='CUSTOMER'), json=body).status_code == 403
    from core.dealership_lab import policy
    monkeypatch.setattr(policy, 'read', lambda: {'enabled':False})
    assert client.post(BASE+'/preview', headers=auth(), json=body).status_code == 403
    assert client.post(BASE+'/save', headers=auth(), json={'preview_id':'x', 'name':'x'}).status_code == 403


@pytest.mark.parametrize('field', ['profile', 'finance', 'baseline', 'scenario', 'segments', 'mix', 'workflow', 'dealership'])
def test_wrong_nested_types_fail_cleanly(client, field):
    model = default_experiment()
    model[field] = 'invalid object'
    assert preview(client, model).status_code == 422


def test_import_lineage_survives_copy_recovery_and_decision_without_retry_identity(client):
    model=default_experiment()
    model['operating_enabled']=True
    p=preview(client,model).json()
    original=client.post(BASE+'/save',headers=auth(),json=dict(preview_id=p['preview_id'],name='Imported source')).json()
    cloned=make(client,name='Copied inputs',source=original['id'])
    version=next(v for v in lab.items(lab.VERSION) if v.attributes['workspace_id']==original['id'])
    recovered=lab.copy_version(original['id'],'LAB-STAFF',version.id,1,'Recovered inputs','import-recovery-00001')
    response=client.post('/dealership-lab/workspaces/'+original['id']+'/decisions',headers=auth(),
        json=dict(revision=1,name='Cost option',decision='cost',values={'monthly_cost':100}))
    assert response.status_code==200,response.text
    for copy in (cloned,recovered,response.json()):
        assert copy['imported_from']==original['imported_from']
        assert 'import_preview_id' not in copy and 'import_name' not in copy
        saved=next(v for v in lab.items(lab.VERSION) if v.attributes['workspace_id']==copy['id'])
        assert saved.attributes['imported_from']==original['imported_from']
    # A subsequent retry must still resolve to the original import, not an option.
    assert client.post(BASE+'/save',headers=auth(),json=dict(preview_id=p['preview_id'],name='Imported source')).json()['id']==original['id']
