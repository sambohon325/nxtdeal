import smtplib
import ssl
import pytest
from core.privateemail_verification import PrivateEmailConfig, PrivateEmailVerification


class SMTP:
    def __init__(self, host, port, **kwargs):
        assert (host, port) == ('mail.privateemail.com', 465)
        assert kwargs['timeout'] == 10
        assert kwargs['context'].verify_mode == ssl.CERT_REQUIRED
        assert kwargs['context'].check_hostname
        self.closed = False
        self.messages = []
    def login(self, username, password):
        assert (username, password) == ('info@example.com', 'fixture-secret')
    def send_message(self, message, **kwargs):
        self.messages.append((message, kwargs))
        return {}
    def close(self):
        self.closed = True


def test_tls_authenticated_acceptance_is_not_delivery():
    clients = []
    def factory(*args, **kwargs):
        client = SMTP(*args, **kwargs); clients.append(client); return client
    adapter = PrivateEmailVerification(PrivateEmailConfig('info@example.com', 'fixture-secret'), smtp_factory=factory)
    result = adapter.send_code('buyer@example.com', '123456')
    assert result == {'provider': 'privateemail', 'delivery': 'accepted', 'verified': False}
    client = clients[0]
    assert client.closed
    message, envelope = client.messages[0]
    assert envelope == {'from_addr': 'info@example.com', 'to_addrs': ['buyer@example.com']}
    assert message['To'] == 'buyer@example.com'
    assert '123456' in message.get_content()
    assert 'fixture-secret' not in str(message)


@pytest.mark.parametrize('recipient,code', [('a@example.com\r\nBcc: victim@example.com','123456'),
    ('a@example.com,b@example.com','123456'), ('bad','123456'), ('a@example.com','12x456'),
    ('a@example.com','１２３４５６'), ('a@example.com',None)])
def test_invalid_input_never_connects(recipient, code):
    def forbidden(*a, **kw): pytest.fail('SMTP must not be reached')
    result = PrivateEmailVerification(PrivateEmailConfig('info@example.com','fixture'), smtp_factory=forbidden).send_code(recipient,code)
    assert result['reason'] == 'invalid_input'


@pytest.mark.parametrize('stage', ['login','send_message','close'])
def test_provider_errors_redacted_and_close_failure_does_not_erase_acceptance(stage):
    class Failure(SMTP):
        pass
    def fail(*args, **kwargs): raise smtplib.SMTPException('fixture-secret 123456')
    setattr(Failure, stage, fail)
    result = PrivateEmailVerification(PrivateEmailConfig('info@example.com','fixture-secret'), smtp_factory=Failure).send_code('buyer@example.com','123456')
    assert 'fixture-secret' not in str(result) and '123456' not in str(result)
    assert result.get('delivery') == ('accepted' if stage == 'close' else None)


def test_rejected_recipient_is_not_accepted():
    class Rejected(SMTP):
        def send_message(self, *a, **kw): return {'buyer@example.com': (550,b'rejected')}
    result = PrivateEmailVerification(PrivateEmailConfig('info@example.com','fixture-secret'), smtp_factory=Rejected).send_code('buyer@example.com','123456')
    assert result['reason'] == 'recipient_rejected'


def test_config_requires_credentials_and_masks_password(monkeypatch):
    monkeypatch.delenv('NXTDEAL_PRIVATEEMAIL_PASSWORD', raising=False)
    assert PrivateEmailConfig.from_environment() is None
    monkeypatch.setenv('NXTDEAL_PRIVATEEMAIL_USERNAME','info@example.com')
    monkeypatch.setenv('NXTDEAL_PRIVATEEMAIL_PASSWORD','fixture-secret')
    config = PrivateEmailConfig.from_environment()
    assert config.username == 'info@example.com'
    assert 'fixture-secret' not in repr(config)
