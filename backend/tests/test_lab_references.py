from test_dealership_lab import client, auth, make
from test_lab_setup import action
from core.dealership_lab import analysis, service as lab
from chrono.shared.dealership.peers import comparison
from core.dealership_lab.replay import unchanged_bundle


def test_reference_snapshot_is_canonical_private_and_read_only(client):
    w = make(client)
    url = f"/dealership-lab/workspaces/{w['id']}/references?revision={w['revision']}"
    response = client.get(url, headers=auth())
    assert response.status_code == 200, response.text
    snapshot = response.json()
    assert snapshot['comparison'] == comparison(analysis.compile_inputs(w))
    assert snapshot['source_hash'] == lab.digest(analysis.compile_inputs(w))
    assert len(snapshot['reference_hash']) == 64
    assert snapshot['provenance']['commit'] == '263e1c77223ab9f70ad1ce4fd055be00ec5fea7a'
    assert lab.serial(lab.workspace(w['id'], 'LAB-STAFF')) == w
    assert client.get(url, headers=auth('OTHER', 'ADMIN')).status_code == 404
    assert client.get(url).status_code == 401
    assert client.get(url.replace('revision=', 'revision=99'), headers=auth()).status_code == 409
    updated = action(client, w, 'path', {'mode': 'hybrid'}).json()
    assert client.get(url, headers=auth()).status_code == 409
    assert client.get(f"/dealership-lab/workspaces/{w['id']}/references?revision={updated['revision']}", headers=auth()).status_code == 200


def test_prior_production_engine_remains_hash_verified_for_finance_replay():
    assert unchanged_bundle('9967b556af6627ab4adc10577e4a08caaea5f579')
    assert unchanged_bundle('9be8c951f177289b4635d11d38327bfab46d1677')
    assert not unchanged_bundle('unrecognized')
