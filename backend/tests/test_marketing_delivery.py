import pytest
from core import marketing_delivery as d


def test_email_acceptance_uses_tls_and_stable_message_id(monkeypatch):
    monkeypatch.setenv("NXTDEAL_PRIVATEEMAIL_USERNAME", "sender@example.test")
    monkeypatch.setenv("NXTDEAL_PRIVATEEMAIL_PASSWORD", "test-only")
    recorded = []
    class SMTP:
        def __init__(self, host, port, **kwargs):
            assert host == "mail.privateemail.com" and port == 465
            assert kwargs["context"].check_hostname
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def login(self, username, password):
            assert username == "sender@example.test"
        def send_message(self, message):
            recorded.append(message)
            return {}
    monkeypatch.setattr(d.smtplib, "SMTP_SSL", SMTP)
    action = {"id": "MKT-test", "channel": "email", "to": "recipient@example.test", "subject": "Draft", "body": "Approved copy"}
    result = d.send(action)
    assert result == {"provider": "privateemail", "provider_reference": "<MKT-test@example.test>"}
    assert recorded[0]["Message-ID"] == result["provider_reference"]
    with pytest.raises(ValueError):
        d.send({**action, "to": "bad\nBcc: other@example.test"})


def test_twilio_validates_acknowledgement_and_never_retries(monkeypatch):
    for key, value in {"TWILIO_ACCOUNT_SID": "AC" + "a" * 32, "TWILIO_API_KEY_SID": "SK" + "b" * 32, "TWILIO_API_KEY_SECRET": "test-only", "TWILIO_MESSAGING_SERVICE_SID": "MG" + "c" * 32}.items():
        monkeypatch.setenv(key, value)
    calls = []
    data = {"account_sid": "AC" + "a" * 32, "to": "+15555550123", "sid": "SM" + "d" * 32}
    class Response:
        def raise_for_status(self): pass
        def json(self): return data
    class Client:
        def __init__(self, **kwargs): assert not kwargs["follow_redirects"]
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, url, **kwargs):
            calls.append(kwargs)
            assert url.startswith("https://api.twilio.com/")
            return Response()
    monkeypatch.setattr(d.httpx, "Client", Client)
    action = {"id": "MKT-test", "channel": "sms", "to": "+15555550123", "body": "Approved copy"}
    assert d.send(action)["provider_reference"] == data["sid"]
    data["account_sid"] = "AC" + "e" * 32
    with pytest.raises(RuntimeError): d.send(action)
    assert len(calls) == 2


def test_unconfigured_transport_fails_before_network(monkeypatch):
    monkeypatch.delenv("NXTDEAL_PRIVATEEMAIL_PASSWORD", raising=False)
    with pytest.raises(ValueError): d.send({"channel": "email"})
