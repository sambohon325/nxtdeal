import pytest
from fastapi.testclient import TestClient
from api.app import app
from core import demo_mode
from core.auth import credential_store
from core.dealeros import ledger


@pytest.fixture
def sessions(monkeypatch):
    ledger.reset()
    credential_store.reset()
    monkeypatch.setenv('DEALEROS_DEMO', '1')
    monkeypatch.delenv('DEMO_ACCESS_CODE', raising=False)
    monkeypatch.setattr(demo_mode, 'save_graph', lambda *_: None)
    first = demo_mode.start_demo('sales_manager')
    second = demo_mode.start_demo('sales_manager')
    yield TestClient(app), first, second
    ledger.reset()
    credential_store.reset()


@pytest.mark.parametrize('route', ['session', 'summary', 'track'])
def test_demo_analytics_require_owner_token(sessions, route):
    client, first, second = sessions
    def request(token):
        headers = {'Authorization': 'Bearer ' + token} if token else {}
        if route == 'track':
            return client.post('/public/demo/track', headers=headers, json={'session_id':first['session_id'], 'kind':'page_view'}).json()
        return client.get('/public/demo/' + route + '/' + first['session_id'], headers=headers).json()
    for token in [None, 'synthetic-invalid', second['token']]:
        assert 'error' in request(token)
    assert demo_mode.get_session(first['session_id'])['pages_viewed'] == 0
    assert 'error' not in request(first['token'])
    assert demo_mode.get_session(first['session_id'])['pages_viewed'] == (1 if route == 'track' else 0)
