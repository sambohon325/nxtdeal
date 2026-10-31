import ssl
import pytest
from core import customer_provider_transport as transport


class Connection:
    def __enter__(self): return self
    def __exit__(self, *args): self.closed = True
    def version(self): return 'TLSv1.3'


def test_transport_uses_fixed_hosts_validating_tls_and_no_authentication(monkeypatch):
    opened, wrapped = [], []
    class Context:
        def wrap_socket(self, connection, server_hostname):
            wrapped.append(server_hostname)
            return Connection()
    def connect(address, timeout):
        assert timeout == 10
        opened.append(address)
        return Connection()
    monkeypatch.setattr(transport.socket, 'create_connection', connect)
    monkeypatch.setattr(transport.ssl, 'create_default_context', lambda: Context())
    result = transport.check_transport()
    assert opened == [('mail.privateemail.com',465), ('verify.twilio.com',443)]
    assert wrapped == [host for host, _ in opened]
    assert result['scope'] == 'executing_host_only'
    for row in result['endpoints']:
        assert row['tls_verified'] is True and row['tls_version'] == 'TLSv1.3'
        assert row['authentication_tested'] is False and row['delivery_tested'] is False
        assert row['observed_at'].endswith('+00:00')


@pytest.mark.parametrize('error,reason', [(OSError('fixture-private'), 'connection_unconfirmed'),
    (ssl.SSLCertVerificationError('fixture-private'), 'certificate_verification_failed')])
def test_transport_failure_is_redacted_and_checks_both_endpoints(monkeypatch, error, reason):
    calls = []
    def fail(*args, **kwargs):
        calls.append(True)
        raise error
    monkeypatch.setattr(transport.socket, 'create_connection', fail)
    result = transport.check_transport()
    assert len(calls) == 2 and 'fixture-private' not in str(result)
    assert all(row['reason'] == reason and row['tls_verified'] is False for row in result['endpoints'])
