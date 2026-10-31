"""Reject oversized customer inputs before credential or provider operations."""
import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def bounded_client(monkeypatch):
    api = importlib.import_module('api.app')
    calls = []
    def called(*args, **kwargs):
        calls.append((args, kwargs))
        return {'accepted_by_fixture': True}
    for name in ('customer_signup_api', 'customer_login_api',
                 'customer_request_link_code_api', 'customer_confirm_link_code_api'):
        monkeypatch.setattr(api, name, called)
    return TestClient(api.app), calls


@pytest.mark.parametrize('route,payload', [
    ('/public/customer/signup', {'email': 'x'*255, 'password': 'valid-password'}),
    ('/public/customer/signup', {'email': 'a@example.com', 'password': 'x'*1025}),
    ('/public/customer/signup', {'email': 'a@example.com', 'password': 'valid-password', 'name': 'x'*201}),
    ('/public/customer/signup', {'email': 'a@example.com', 'password': 'valid-password', 'phone': '1'*33}),
    ('/public/customer/login', {'email': 'x'*255, 'password': 'valid-password'}),
    ('/public/customer/login', {'email': 'a@example.com', 'password': 'x'*1025}),
    ('/customer/link/request-code', {'channel': 'other'}),
    ('/customer/link/confirm', {'channel': 'sms', 'code': '1'*11}),
    ('/customer/link/confirm', {'channel': 'sms', 'code': '123'}),
    ('/customer/link/confirm', {'channel': 'sms', 'code': '１２３４５６'}),
    ('/customer/link/confirm', {'channel': 'sms', 'code': '123456\n'}),
    ('/customer/link/confirm', {'channel': 'other', 'code': '123456'}),
])
def test_invalid_input_never_reaches_customer_operation(bounded_client, route, payload):
    client, calls = bounded_client
    response = client.post(route, json=payload)
    assert response.status_code == 422
    assert response.headers['cache-control'] == 'no-store'
    assert all(set(error) == {'loc', 'type', 'msg'} for error in response.json()['detail'])
    assert calls == []


@pytest.mark.parametrize('route,payload', [
    ('/public/customer/signup', {'email': 'a@example.com', 'password': 'x'*1024, 'name': 'x'*200, 'phone': '1'*32}),
    ('/public/customer/login', {'email': 'a@example.com', 'password': 'x'*1024}),
    ('/customer/link/request-code', {}),
    ('/customer/link/confirm', {'channel': 'sms', 'code': '1234'}),
    ('/customer/link/confirm', {'channel': 'sms', 'code': '1234567890'}),
])
def test_valid_bounded_input_reaches_existing_operation(bounded_client, route, payload):
    client, calls = bounded_client
    response = client.post(route, json=payload)
    assert response.json() == {'accepted_by_fixture': True}
    assert response.headers['cache-control'] == 'no-store'
    assert response.headers['pragma'] == 'no-cache'
    assert response.headers['referrer-policy'] == 'no-referrer'
    assert len(calls) == 1


def test_password_and_malformed_json_are_not_echoed(bounded_client):
    client, calls = bounded_client
    secret = 'fixture-sensitive-password-' * 60
    response = client.post('/public/customer/login', json={'email': 'a@example.com', 'password': secret})
    assert 'fixture-sensitive-password' not in response.text
    malformed = client.post('/public/customer/login', content='{"password":"fixture-sensitive-password",',
                            headers={'Content-Type': 'application/json'})
    assert malformed.status_code == 422
    assert 'fixture-sensitive-password' not in malformed.text
    assert malformed.headers['cache-control'] == 'no-store'
    assert calls == []


@pytest.mark.parametrize('route,method', [('/customer/me', 'get'), ('/customer/logout', 'post')])
def test_unauthorized_customer_response_is_not_cacheable(bounded_client, route, method):
    client, _ = bounded_client
    response = getattr(client, method)(route)
    assert 'error' in response.json()
    assert response.headers['cache-control'] == 'no-store'


def test_noncustomer_validation_keeps_default_handler(bounded_client):
    client, _ = bounded_client
    response = client.post('/auth/login', json={})
    assert response.status_code == 422
    assert all(error['msg'] == 'Field required' for error in response.json()['detail'])
