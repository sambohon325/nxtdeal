"""Read-only, fixed-loopback synthetic health probe. No credentials or alert delivery."""
from http.client import HTTPException
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate health response field')
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError('Invalid health response constant')


def _read_response(response, limit):
    content = response.read(limit + 1)
    lengths = response.headers.get_all('Content-Length', [])
    if lengths:
        if (len(lengths) != 1 or not lengths[0].isascii()
                or not lengths[0].isdigit() or len(lengths[0]) > 20
                or response.headers.get('Transfer-Encoding') is not None):
            raise ValueError('Ambiguous response framing')
        # HTTPResponse.read(amount) can return a short body without raising
        # IncompleteRead. Do not accept a valid JSON/HTML prefix as full health.
        if len(content) <= limit and len(content) != int(lengths[0]):
            raise ValueError('Incomplete health response')
    return content


def fetch(port, path):
    # Ignore ambient proxies and reject redirects to any other destination.
    opener = build_opener(ProxyHandler({}), NoRedirect())
    with opener.open(f'http://127.0.0.1:{port}{path}', timeout=5) as response:
        if response.status != 200 or response.headers.get_content_type() != 'application/json':
            raise ValueError('Unexpected health response status or media type')
        content = _read_response(response, 65536)
        if len(content) > 65536:
            raise ValueError('Oversize health response')
        try:
            return json.loads(content, object_pairs_hook=_unique_object,
                              parse_constant=_invalid_constant)
        except RecursionError:
            raise ValueError('Health response nesting exceeded parser capacity') from None


def web_available():
    # This is a transport/content check, not proof of authenticated browser UX.
    # The public app index needs no token. Bound reads and disable redirects/proxies
    # just as for the API probes; never include response contents in the report.
    opener = build_opener(ProxyHandler({}), NoRedirect())
    with opener.open('http://127.0.0.1:3317/apps', timeout=5) as response:
        content = _read_response(response, 1048576)
        return (response.status == 200
                and response.headers.get_content_type() == 'text/html'
                and len(content) <= 1048576
                and b'App Suite' in content and b'NXTDeal' in content)


def probe():
    checks = {}
    for port, service in [(8317, 'dealer'), (9317, 'hub')]:
        try:
            value = fetch(port, '/synthetic/identity')
            checks[service] = 'healthy' if isinstance(value, dict) and value == {
                'scope':'synthetic_only', 'service':service, 'delivery_enabled':False
            } and value['delivery_enabled'] is False else 'identity_mismatch'
        except (HTTPError, URLError, OSError, ValueError, HTTPException):
            checks[service] = 'unavailable'
    # Only inspect provider-disable status after this port confirms its identity.
    if checks['hub'] == 'healthy':
        try:
            value = fetch(9317, '/mysales/email/status')
            checks['delivery'] = 'disabled' if isinstance(value, dict) and value == {
                'available':False} and value['available'] is False else 'unexpected_configuration'
        except (HTTPError, URLError, OSError, ValueError, HTTPException):
            checks['delivery'] = 'unavailable'
    else:
        checks['delivery'] = 'not_checked'
    # Do not inspect an unrelated frontend unless both API identities match.
    if all(checks[key] == 'healthy' for key in ('dealer', 'hub')):
        try:
            checks['web'] = 'healthy' if web_available() else 'unexpected_content'
        except (HTTPError, URLError, OSError, ValueError, HTTPException):
            checks['web'] = 'unavailable'
    else:
        checks['web'] = 'not_checked'
    healthy = all(checks[key] == 'healthy' for key in ('dealer', 'hub', 'web')) and checks['delivery'] == 'disabled'
    return {'scope':'synthetic_only', 'status':'healthy' if healthy else 'attention_needed',
            'checks':checks, 'alert_delivery':'not_configured', 'production_readiness':False}


if __name__ == '__main__':
    result = probe()
    print(json.dumps(result))
    sys.exit(0 if result['status'] == 'healthy' else 1)
