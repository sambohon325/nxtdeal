import json
import httpx
import pytest
from core.twilio_sms_verification import VerifyConfig, TwilioSmsVerification

CONFIG = VerifyConfig('AC'+'1'*32, 'VA'+'2'*32, 'SK'+'3'*32, 'fixture-secret')
SID = 'VE'+'4'*32
PHONE = '+15555550123'


def payload(**changes):
    return dict(account_sid=CONFIG.account_sid, service_sid=CONFIG.service_sid,
                sid=SID, to=PHONE, channel='sms', **changes)


def provider(body, status=200):
    calls = []
    def post(url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(status, content=json.dumps(body))
    return TwilioSmsVerification(CONFIG, post=post), calls


def test_pending_acceptance_is_not_delivery_or_verification():
    client, calls = provider(payload(status='pending'), 201)
    result = client.start(PHONE)
    assert result == {'provider':'twilio_verify','verification_sid':SID,'status':'pending','verified':False}
    assert calls[0][1]['data'] == {'To':PHONE,'Channel':'sms'}
    assert calls[0][1]['follow_redirects'] is False
    assert calls[0][1]['timeout'] == 10.0
    assert 'fixture-secret' not in repr(CONFIG)


@pytest.mark.parametrize('status,valid,verified', [('approved',True,True),('pending',True,False),('approved',False,False),('approved','true',False),('expired',True,False)])
def test_only_explicit_bound_approval_verifies(status, valid, verified):
    client, calls = provider(payload(status=status,valid=valid))
    assert client.check(SID,'123456')['verified'] is verified
    assert calls[0][1]['data'] == {'VerificationSid':SID,'Code':'123456'}


@pytest.mark.parametrize('field,value', [('account_sid','AC'+'9'*32),('service_sid','VA'+'9'*32),('sid','VE'+'9'*32),('channel','email')])
def test_provider_proof_cannot_cross_bindings(field,value):
    body=payload(status='approved',valid=True);body[field]=value
    client,_=provider(body)
    assert 'error' in client.check(SID,'123456')


@pytest.mark.parametrize('status,reason', [(302,'provider_unavailable'),(401,'provider_unavailable'),(429,'rate_limited'),(404,'expired'),(500,'provider_unavailable')])
def test_provider_errors_are_redacted(status,reason):
    client,_=provider({'message':'secret phone code token'},status)
    result=client.check(SID,'123456')
    assert result['reason']==reason
    assert 'secret' not in str(result)


@pytest.mark.parametrize('phone', ['5551234',None,'+0123456789','+1555\n5550123'])
def test_invalid_phone_never_contacts_provider(phone):
    client,calls=provider({})
    assert 'error' in client.start(phone)
    assert not calls


def test_timeout_does_not_become_success():
    def timeout(*args,**kwargs): raise httpx.TimeoutException('sensitive request detail')
    result=TwilioSmsVerification(CONFIG,post=timeout).start(PHONE)
    assert result['reason']=='provider_unavailable'
    assert 'sensitive' not in str(result)


def test_missing_secure_configuration_is_unavailable(monkeypatch):
    for key in ('TWILIO_ACCOUNT_SID','TWILIO_VERIFY_SERVICE_SID','TWILIO_API_KEY_SID','TWILIO_API_KEY_SECRET'):
        monkeypatch.delenv(key,raising=False)
    assert VerifyConfig.from_environment() is None

@pytest.mark.parametrize('body', [None, [], {}, {'sid':'VE'+'4'*32}])
def test_malformed_provider_payload_fails_closed(body):
    client,_=provider(body)
    assert client.start(PHONE)['reason']=='invalid_response'


@pytest.mark.parametrize('field,value', [('to','+15555550999'),('channel','email'),('status','approved')])
def test_start_must_match_recipient_channel_and_pending_status(field,value):
    body=payload(status='pending');body[field]=value
    client,_=provider(body)
    assert client.start(PHONE)['reason']=='invalid_response'


@pytest.mark.parametrize('sid,code', [('wrong','123456'),(SID,'not-a-code'),(SID,123456),(SID,'123456\n')])
def test_invalid_check_never_contacts_provider(sid,code):
    client,calls=provider({})
    assert client.check(sid,code)['reason']=='invalid_input'
    assert not calls


def test_environment_configuration_requires_all_valid_bindings(monkeypatch):
    monkeypatch.setenv('TWILIO_ACCOUNT_SID',CONFIG.account_sid)
    monkeypatch.setenv('TWILIO_VERIFY_SERVICE_SID',CONFIG.service_sid)
    monkeypatch.setenv('TWILIO_API_KEY_SID',CONFIG.api_key_sid)
    monkeypatch.setenv('TWILIO_API_KEY_SECRET',CONFIG.api_key_secret)
    assert VerifyConfig.from_environment()==CONFIG
    monkeypatch.setenv('TWILIO_VERIFY_SERVICE_SID','../../other-service')
    assert VerifyConfig.from_environment() is None
