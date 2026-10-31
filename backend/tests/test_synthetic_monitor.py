"""Failure-path checks for the no-auth synthetic monitor."""
import importlib.util
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError
from email.message import Message
from unittest.mock import MagicMock

import pytest

spec = importlib.util.spec_from_file_location('synthetic_monitor', Path(__file__).resolve().parents[2]/'scripts/monitor_synthetic_stack.py')
monitor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(monitor)


@pytest.fixture(autouse=True)
def healthy_web():
    with patch.object(monitor, 'web_available', return_value=True) as web:
        yield web


def identity(service):
    return {'scope':'synthetic_only', 'service':service, 'delivery_enabled':False}


@pytest.mark.parametrize('field', ['dealer', 'hub', 'delivery'])
def test_numeric_zero_cannot_confirm_delivery_disabled(field):
    values = [identity('dealer'), identity('hub'), {'available':False}]
    index = ['dealer', 'hub', 'delivery'].index(field)
    values[index]['available' if field == 'delivery' else 'delivery_enabled'] = 0
    with patch.object(monitor, 'fetch', side_effect=values):
        report = monitor.probe()
    assert report['status'] == 'attention_needed'
    assert report['checks'][field] == ('unexpected_configuration' if field == 'delivery' else 'identity_mismatch')


@pytest.mark.parametrize('body', [b'{"available":true,"available":false}', b'{"available":NaN}'])
def test_api_health_rejects_ambiguous_json(body):
    response = MagicMock()
    response.status = 200
    response.headers = Message()
    response.headers['Content-Type'] = 'application/json'
    response.read.return_value = body
    response.__enter__.return_value = response
    with patch.object(monitor, 'build_opener') as opener:
        opener.return_value.open.return_value = response
        with pytest.raises(ValueError):
            monitor.fetch(9317, '/mysales/email/status')


@pytest.mark.parametrize('status,media', [(202, 'application/json'), (200, 'text/html'), (200, 'text/plain')])
def test_api_probe_rejects_wrong_status_or_media_before_reading(status, media):
    response = MagicMock()
    response.status = status
    response.headers = Message()
    response.headers['Content-Type'] = media
    response.read.return_value = b'{"available":false}'
    response.__enter__.return_value = response
    with patch.object(monitor, 'build_opener') as opener:
        opener.return_value.open.return_value = response
        with pytest.raises(ValueError):
            monitor.fetch(9317, '/mysales/email/status')
    response.read.assert_not_called()


def test_parser_recursion_failure_reports_unavailable_instead_of_crashing():
    response = MagicMock()
    response.status = 200
    response.headers = Message()
    response.headers['Content-Type'] = 'application/json; charset=utf-8'
    response.read.return_value = b'[' * 2000 + b'0' + b']' * 2000
    response.__enter__.return_value = response
    with patch.object(monitor, 'build_opener') as opener, patch.object(
            monitor.json, 'loads', side_effect=RecursionError('private parser detail')):
        opener.return_value.open.return_value = response
        report = monitor.probe()
    assert report['status'] == 'attention_needed'
    assert report['checks'] == {'dealer':'unavailable', 'hub':'unavailable',
                                'delivery':'not_checked', 'web':'not_checked'}


def test_healthy_monitor_is_read_only_and_reports_no_alert_delivery():
    with patch.object(monitor, 'fetch', side_effect=[identity('dealer'), identity('hub'), {'available':False}]) as fetch:
        report = monitor.probe()
    assert report['status'] == 'healthy'
    assert report['alert_delivery'] == 'not_configured'
    assert fetch.call_args_list == [((8317, '/synthetic/identity'),), ((9317, '/synthetic/identity'),), ((9317, '/mysales/email/status'),)]


def test_outage_and_recovery_do_not_leak_exception_details():
    with patch.object(monitor, 'fetch', side_effect=[identity('dealer'), URLError('private provider detail')]):
        report = monitor.probe()
    assert report['status'] == 'attention_needed'
    assert report['checks']['hub'] == 'unavailable'
    assert report['checks']['delivery'] == 'not_checked'
    assert 'private' not in str(report)
    with patch.object(monitor, 'fetch', side_effect=[identity('dealer'), identity('hub'), {'available':False}]):
        assert monitor.probe()['status'] == 'healthy'


def test_wrong_identity_prevents_followup_and_enabled_delivery_fails():
    with patch.object(monitor, 'fetch', side_effect=[identity('dealer'), {'scope':'production'}]) as fetch:
        assert monitor.probe()['checks']['hub'] == 'identity_mismatch'
        assert fetch.call_count == 2
    with patch.object(monitor, 'fetch', side_effect=[identity('dealer'), identity('hub'), {'available':True}]):
        assert monitor.probe()['checks']['delivery'] == 'unexpected_configuration'


def test_redirects_are_not_followed():
    assert monitor.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://example.test') is None


def test_truncated_http_response_reports_unavailable_and_allows_recovery():
    from http.client import IncompleteRead
    with patch.object(monitor, 'fetch', side_effect=[identity('dealer'), IncompleteRead(b'private-partial-body', 20)]) as fetch:
        report = monitor.probe()
    assert report['status'] == 'attention_needed'
    assert report['checks'] == {'dealer': 'healthy', 'hub': 'unavailable', 'delivery': 'not_checked', 'web': 'not_checked'}
    assert fetch.call_count == 2
    assert 'private' not in str(report)
    with patch.object(monitor, 'fetch', side_effect=[identity('dealer'), identity('hub'), {'available': False}]):
        assert monitor.probe()['status'] == 'healthy'


def test_web_outage_is_not_masked_by_healthy_apis(healthy_web):
    healthy_web.side_effect = URLError('private web detail')
    with patch.object(monitor, 'fetch', side_effect=[identity('dealer'), identity('hub'), {'available':False}]):
        report = monitor.probe()
    assert report['status'] == 'attention_needed'
    assert report['checks']['web'] == 'unavailable'
    assert report['checks']['dealer'] == report['checks']['hub'] == 'healthy'
    assert 'private' not in str(report)
    healthy_web.side_effect = None
    with patch.object(monitor, 'fetch', side_effect=[identity('dealer'), identity('hub'), {'available':False}]):
        assert monitor.probe()['status'] == 'healthy'


def test_web_unexpected_content_and_identity_gate(healthy_web):
    healthy_web.return_value = False
    with patch.object(monitor, 'fetch', side_effect=[identity('dealer'), identity('hub'), {'available':False}]):
        assert monitor.probe()['checks']['web'] == 'unexpected_content'
    healthy_web.reset_mock()
    with patch.object(monitor, 'fetch', side_effect=[{'scope':'production'}, identity('hub'), {'available':False}]):
        assert monitor.probe()['checks']['web'] == 'not_checked'
    healthy_web.assert_not_called()


@pytest.mark.parametrize('status,content_type,body,expected', [
    (200, 'text/html', b'<title>NXTDeal</title>App Suite', True),
    (503, 'text/html', b'NXTDeal App Suite', False),
    (200, 'application/json', b'NXTDeal App Suite', False),
    (200, 'text/html', b'Other application', False),
    (200, 'text/html', b'NXTDeal App Suite' + b'x' * 1048576, False),
], ids=['healthy', 'unavailable-status', 'wrong-content-type', 'wrong-app', 'oversize'])
def test_web_probe_bounds_and_validates_response(status, content_type, body, expected):
    # Load an unpatched copy so the common healthy-web fixture cannot mask this check.
    actual = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(actual)
    response = MagicMock()
    response.status = status
    response.headers = Message()
    response.headers['Content-Type'] = content_type
    response.read.return_value = body
    response.__enter__.return_value = response
    with patch.object(actual, 'build_opener') as opener:
        opener.return_value.open.return_value = response
        assert actual.web_available() is expected
    response.read.assert_called_once_with(1048577)
    opener.return_value.open.assert_called_once_with('http://127.0.0.1:3317/apps', timeout=5)
def test_invalid_http_status_during_delivery_check_is_reported_safely():
    from http.client import BadStatusLine
    with patch.object(monitor, 'fetch', side_effect=[identity('dealer'), identity('hub'), BadStatusLine('private-invalid-status')]):
        report = monitor.probe()
    assert report['status'] == 'attention_needed'
    assert report['checks']['delivery'] == 'unavailable'
    assert 'private' not in str(report)


@pytest.mark.parametrize('missing_bytes', [0, 100])
def test_real_http_response_requires_complete_declared_body(monkeypatch, missing_bytes):
    """A valid JSON prefix is not a complete declared HTTP response."""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            body = b'{"scope":"synthetic_only","service":"dealer","delivery_enabled":false}'
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body) + missing_bytes))
            self.end_headers()
            self.wfile.write(body)
            self.close_connection = True

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=lambda: server.serve_forever(poll_interval=0.02), daemon=True)
    thread.start()
    try:
        monkeypatch.setenv('http_proxy', 'http://127.0.0.1:1')
        monkeypatch.setenv('no_proxy', '')
        if missing_bytes:
            with pytest.raises((ValueError, monitor.HTTPException)):
                monitor.fetch(server.server_port, '/synthetic/identity')
        else:
            assert monitor.fetch(server.server_port, '/synthetic/identity') == identity('dealer')
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        assert not thread.is_alive()


@pytest.mark.parametrize('lengths,transfer', [
    (['5', '5'], None), (['-1'], None), (['garbage'], None),
    (['5'], 'chunked'), (['9'], None),
])
def test_response_framing_rejects_ambiguous_or_incomplete_body(lengths, transfer):
    response = MagicMock()
    response.headers = Message()
    for value in lengths:
        response.headers['Content-Length'] = value
    if transfer:
        response.headers['Transfer-Encoding'] = transfer
    response.read.return_value = b'hello'
    with pytest.raises(ValueError):
        monitor._read_response(response, 64)
