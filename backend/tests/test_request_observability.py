import json
import logging
from fastapi import FastAPI
from fastapi.testclient import TestClient
from core.request_observability import install


def test_request_evidence_omits_private_inputs_and_unmatched_paths(caplog):
    app = FastAPI()
    install(app)
    @app.post('/customer/{customer_id}')
    def customer(customer_id: str):
        return {'ok': True}
    with caplog.at_level(logging.INFO, logger='nxtdeal.requests'):
        client = TestClient(app)
        response = client.post('/customer/private-person?token=private-token',
                               json={'password':'private-password'},
                               headers={'X-Request-ID':'injected-private-id'})
        client.get('/private-path?email=private-email')
    assert response.status_code == 200
    assert len(response.headers['x-request-id']) == 32
    evidence = [json.loads(r.message) for r in caplog.records if r.name == 'nxtdeal.requests']
    assert evidence[0]['route'] == '/customer/{customer_id}'
    assert evidence[1]['route'] == 'unmatched'
    assert 'private-' not in json.dumps(evidence)
    assert evidence[0]['request_id'] == response.headers['x-request-id']


def test_exception_evidence_never_contains_exception_message(caplog):
    app = FastAPI()
    install(app)
    @app.get('/failure')
    def failure():
        raise RuntimeError('sensitive provider response')
    with caplog.at_level(logging.INFO, logger='nxtdeal.requests'):
        assert TestClient(app, raise_server_exceptions=False).get('/failure').status_code == 500
    messages = [r.message for r in caplog.records if r.name == 'nxtdeal.requests']
    assert json.loads(messages[0])['status'] == 500
    assert 'sensitive' not in ''.join(messages)
