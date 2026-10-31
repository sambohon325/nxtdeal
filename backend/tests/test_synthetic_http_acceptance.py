"""Ensure negative HTTP acceptance checks cannot silently pass success responses."""
import importlib.util
import io
from pathlib import Path
from urllib.error import HTTPError
from unittest.mock import patch
import pytest

spec = importlib.util.spec_from_file_location('stack_acceptance', Path(__file__).resolve().parents[2]/'scripts/check_synthetic_stack.py')
acceptance = importlib.util.module_from_spec(spec)
spec.loader.exec_module(acceptance)


class Response(io.BytesIO):
    status = 200


def test_expected_denial_is_accepted_but_unexpected_success_fails():
    error = HTTPError('http://127.0.0.1:9317/mysales/me', 401, 'Unauthorized', {}, io.BytesIO(b'{"detail":"Unauthorized"}'))
    with patch.object(acceptance, 'urlopen', side_effect=error):
        assert acceptance.request(9317, '/mysales/me', expected_status=401)['detail'] == 'Unauthorized'
    with patch.object(acceptance, 'urlopen', return_value=Response(b'{}')):
        with pytest.raises(AssertionError, match='Expected HTTP 401, got 200'):
            acceptance.request(9317, '/mysales/me', expected_status=401)


def test_method_and_body_are_preserved_and_unexpected_failure_fails():
    with patch.object(acceptance, 'urlopen', return_value=Response(b'{"ok":true}')) as opener:
        assert acceptance.request(9317, '/mysales/page', {'headline':'Fictional'}, 'fake', method='PUT')['ok']
        request = opener.call_args.args[0]
        assert request.get_method() == 'PUT'
        assert request.data == b'{"headline": "Fictional"}'
    error = HTTPError('http://127.0.0.1:9317/mysales/page', 500, 'Internal error', {}, io.BytesIO(b'{}'))
    with patch.object(acceptance, 'urlopen', side_effect=error):
        with pytest.raises(AssertionError, match='Expected HTTP 200, got 500'):
            acceptance.request(9317, '/mysales/page')


@pytest.mark.parametrize('url', [
    'https://example.test/login', 'http://127.0.0.1:8000/login',
    'http://user:password@127.0.0.1:9317/login', 'http://localhost:9317/login',
])
def test_acceptance_transport_refuses_unapproved_destinations(url):
    with patch.object(acceptance, 'build_opener') as opener:
        with pytest.raises(ValueError, match='fixed synthetic loopback'):
            acceptance.urlopen(url)
        opener.assert_not_called()


def test_acceptance_transport_disables_proxy_and_redirect_handlers():
    with patch.object(acceptance, 'build_opener') as builder:
        acceptance.urlopen('http://127.0.0.1:9317/mysales/me', timeout=15)
        handlers = builder.call_args.args
        assert isinstance(handlers[0], acceptance.ProxyHandler) and handlers[0].proxies == {}
        assert isinstance(handlers[1], acceptance.NoRedirect)
        assert handlers[1].redirect_request(None, None, 302, '', {}, 'https://example.test') is None
        builder.return_value.open.assert_called_once_with('http://127.0.0.1:9317/mysales/me', timeout=15)
