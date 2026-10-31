from test_dealership_lab import client, auth, saved_comparison
from core.dealership_lab import service as lab
from core.dealeros import ledger


def test_register_explicit_frozen_and_private(client):
    run = saved_comparison(client)
    url = f"/dealership-lab/runs/{run['id']}/finance-detail"
    ordinary = client.get(url, headers=auth()).json()
    assert 'register' not in ordinary['sides']['baseline']
    response = client.get(url+'?include_register=true', headers=auth())
    assert response.status_code == 200, response.text
    detail = response.json()
    for side in ('baseline', 'proposed'):
        path = detail['sides'][side]
        assert path['monthly'] == ordinary['sides'][side]['monthly']
        assert path['register']['total_deals'] == sum(int(r['sales']) for r in path['monthly'])
        assert len(path['register']['deals']) <= 2000
        assert 'not actual transactions' in path['register']['label']
    assert client.get(url+'?include_register=true', headers=auth('OTHER', 'ADMIN')).status_code == 404
    assert client.get(url+'?include_register=true').status_code == 401
    assert lab.serial(ledger.get_entity(run['id'])) == run
    assert client.get(url+'?include_register=true', headers=auth()).json() == detail
    ledger.get_entity(run['id']).attributes['shared_engine_commit'] = 'unknown'
    assert client.get(url+'?include_register=true', headers=auth()).status_code == 409
