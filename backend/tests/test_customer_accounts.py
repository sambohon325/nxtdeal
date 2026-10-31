"""
Tests for customer accounts (core/customer_accounts.py + _api.py) — 2026-07-24, NXTDeal's
first customer-facing login for the My Garage app. Run from backend/ with `pytest`.

Covers: sign-up creates an account + credential and issues a customer token; password/email
validation; duplicate-email rejection; login (right/wrong password); domain-separated tokens
(a customer token is NOT a valid employee token and vice-versa); "match + verify" — a sign-up
whose email/phone matches an existing Customer stays UNLINKED until a one-time code is
confirmed (wrong code, expiry-of-attempts, correct code attaches the record); and the _api
token-gated wrappers reject a missing/garbage bearer.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import CUSTOMER, CUSTOMER_ACCOUNT
from core import auth as employee_auth
from core import customer_accounts as ca
from core import customer_accounts_api as ca_api


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch):
    monkeypatch.setenv("DEALEROS_DEMO", "1")
    from core import customer_delivery_limits as limits
    monkeypatch.setattr(limits, 'delivery_budget', limits.DeliveryBudget())
    ledger.reset()
    ca.customer_credential_store.reset()
    # The link code now goes ONLY to the matched record's contact and is not returned to the
    # caller by default (security fix). Opt in to surfacing it so these tests can read it — the
    # same escape hatch a local operator uses.
    os.environ["DEALEROS_EXPOSE_LINK_CODE"] = "1"
    yield
    os.environ.pop("DEALEROS_EXPOSE_LINK_CODE", None)
    ledger.reset()
    ca.customer_credential_store.reset()


def _seed_customer(name="Pat Buyer", email="pat@example.com", phone="555-0100"):
    entity = Entity(
        id="CUST-00001",
        entity_type=CUSTOMER,
        attributes={"name": name, "email": email, "phone": phone},
    )
    ledger.add_entity(entity)
    return entity


# --------------------------------------------------------------------------------------
# Sign-up + login
# --------------------------------------------------------------------------------------

def test_signup_creates_account_credential_and_token():
    result = ca.sign_up("new@buyer.com", "hunter2xyz", name="New Buyer", phone="555-0200")
    assert "error" not in result
    assert result["match_found"] is False
    account = result["account"]
    assert account["email"] == "new@buyer.com"
    assert account["linked"] is False
    assert account["token"]
    # account entity exists, credential set
    assert ledger.get_entity(account["account_id"]).entity_type == CUSTOMER_ACCOUNT
    assert ca.customer_credential_store.has_email("new@buyer.com")


def test_signup_rejects_bad_email_weak_password_and_duplicate():
    assert "error" in ca.sign_up("notanemail", "hunter2xyz")
    assert "error" in ca.sign_up("a@b.com", "short")          # too weak
    assert "error" in ca.sign_up("a@b.com", "allletters")     # no digit
    ca.sign_up("dupe@b.com", "hunter2xyz")
    assert "error" in ca.sign_up("DUPE@b.com", "hunter2xyz")  # case-insensitive dupe


def test_login_right_and_wrong_password():
    ca.sign_up("log@in.com", "hunter2xyz")
    ok = ca.log_in("LOG@in.com", "hunter2xyz")               # email case-insensitive
    assert "error" not in ok and ok["account"]["token"]
    assert "error" in ca.log_in("log@in.com", "wrongpass9")
    assert "error" in ca.log_in("nobody@in.com", "hunter2xyz")


# --------------------------------------------------------------------------------------
# Domain-separated tokens
# --------------------------------------------------------------------------------------

def test_customer_and_employee_tokens_do_not_cross_validate():
    result = ca.sign_up("token@test.com", "hunter2xyz")
    customer_token = result["account"]["token"]

    # A customer token must NOT validate as an employee token.
    assert employee_auth.verify_token(customer_token) is None
    # An employee token must NOT validate as a customer token.
    employee_auth.credential_store.set_credential("EMP-00001", "Fictional2026!", "Sales")
    emp_token = employee_auth.issue_token("EMP-00001", "Sales")
    assert ca.verify_customer_token(emp_token) is None
    # The customer token DOES validate on its own path.
    payload = ca.verify_customer_token(customer_token)
    assert payload and payload["kind"] == "customer"


# --------------------------------------------------------------------------------------
# Match + verify
# --------------------------------------------------------------------------------------

def test_signup_matching_customer_stays_unlinked_until_code_confirmed():
    _seed_customer(email="pat@example.com", phone="555-0100")
    result = ca.sign_up("pat@example.com", "hunter2xyz", name="Pat")
    assert result["match_found"] is True
    account = result["account"]
    assert account["linked"] is False           # NOT linked yet
    assert account["pending_link"] is True
    assert result["dev_code"]                    # simulated delivery surfaces the code

    account_id = account["account_id"]
    code = result["dev_code"]

    # Wrong code does not link.
    bad = ca.confirm_link_code(account_id, "email", "000000")
    assert "error" in bad
    assert ca.get_account(account_id).attributes["linked_customer_id"] is None

    # Correct code links to the matched CRM record.
    good = ca.confirm_link_code(account_id, "email", code)
    assert good.get("linked") is True
    # Simulated confirmation cannot disclose CRM details through the summary.
    assert good["account"]["linked_customer_id"] is None
    assert "customer" not in good["account"]


def test_link_code_locks_out_after_max_attempts():
    _seed_customer(email="pat@example.com")
    result = ca.sign_up("pat@example.com", "hunter2xyz")
    account_id = result["account"]["account_id"]
    for _ in range(ca.OTP_MAX_ATTEMPTS):
        ca.confirm_link_code(account_id, "email", "999999")
    # Further attempts (even the right code) are refused until a new code is requested.
    locked = ca.confirm_link_code(account_id, "email", result["dev_code"])
    assert "error" in locked
    assert ca.get_account(account_id).attributes["linked_customer_id"] is None


def test_match_by_phone_when_email_differs():
    _seed_customer(email="pat@example.com", phone="(555) 010-0999")
    # Different email, same phone (differently formatted) -> should still match on phone.
    result = ca.sign_up("different@buyer.com", "hunter2xyz", phone="5550100999")
    assert result["match_found"] is True


def test_phone_match_never_leaks_code_to_caller_or_auto_links(monkeypatch):
    """Regression for the account-takeover fix: someone who knows only a victim's phone must
    NOT be handed the link code (it goes to the record's real contact), and must not be linked."""
    monkeypatch.delenv("DEALEROS_EXPOSE_LINK_CODE", raising=False)  # production default
    _seed_customer(name="Vic Tim", email="victim@example.com", phone="555-0100")
    result = ca.sign_up("attacker@evil.com", "hunter2xyz", phone="5550100")
    assert result["match_found"] is True
    assert result.get("channel") == "sms"          # verified on the channel we matched (phone)
    assert "dev_code" not in result                 # code is NEVER returned to the caller
    assert result["account"]["linked"] is False     # and nothing is auto-linked
    # The attacker can't guess their way in either.
    account_id = result["account"]["account_id"]
    assert "error" in ca.confirm_link_code(account_id, "sms", "000000")
    assert ca.get_account(account_id).attributes["linked_customer_id"] is None


# --------------------------------------------------------------------------------------
# API token gate
# --------------------------------------------------------------------------------------

def test_api_wrappers_reject_missing_or_bad_bearer():
    assert "error" in ca_api.me_api(None)
    assert "error" in ca_api.me_api("Bearer garbage.token")
    assert "error" in ca_api.confirm_link_code_api("", "email", "123456")


def test_api_me_returns_account_for_valid_token():
    result = ca_api.signup_api("api@me.com", "hunter2xyz")
    token = result["account"]["token"]
    me = ca_api.me_api(f"Bearer {token}")
    assert "error" not in me
    assert me["account"]["email"] == "api@me.com"

@pytest.fixture
def twilio_link(monkeypatch):
    monkeypatch.delenv("DEALEROS_DEMO", raising=False)
    from core import twilio_sms_verification as tv
    monkeypatch.setenv('NXTDEAL_CUSTOMER_SMS_PROVIDER','twilio_verify')
    config=tv.VerifyConfig('AC'+'1'*32,'VA'+'2'*32,'SK'+'3'*32,'fixture')
    monkeypatch.setattr(tv.VerifyConfig,'from_environment',classmethod(lambda cls:config))
    calls=[]
    class Provider:
        def __init__(self,config): pass
        def start(self,phone):
            calls.append(('start',phone))
            return {'verification_sid':'VE'+'4'*32,'status':'pending','verified':False}
        def check(self,sid,code):
            calls.append(('check',sid,code))
            return {'verified':code=='123456','status':'approved' if code=='123456' else 'pending'}
    monkeypatch.setattr(tv,'TwilioSmsVerification',Provider)
    record=_seed_customer(phone='+15555550123')
    result=ca.sign_up('different@example.com','hunter2xyz',phone='+15555550123')
    account=ca.get_account(result['account']['account_id'])
    return record,account,result,calls


def test_twilio_link_uses_matched_contact_and_no_local_code(twilio_link):
    record,account,result,calls=twilio_link
    assert result['delivery']=='pending'
    assert 'dev_code' not in result
    assert calls==[('start','+15555550123')]
    assert 'code' not in account.attributes['challenges']['sms']
    assert not account.attributes.get('linked_customer_id')
    assert ca.confirm_link_code(account.id,'sms','123456')['linked'] is True
    assert account.attributes['linked_customer_id']==record.id
    assert 'error' in ca.confirm_link_code(account.id,'sms','123456')
    assert len(calls)==2


@pytest.mark.parametrize('change',['contact','pending','expired','attempts'])
def test_twilio_link_rejects_stale_or_exhausted_challenge(twilio_link,change):
    record,account,result,calls=twilio_link
    challenge=account.attributes['challenges']['sms']
    if change=='contact': record.attributes['phone']='+15555550999'
    if change=='pending': account.attributes['pending_link_customer_id']='CUST-OTHER'
    if change=='expired': challenge['expires_at']=0
    if change=='attempts': challenge['attempts']=5
    assert 'error' in ca.confirm_link_code(account.id,'sms','123456')
    assert not account.attributes.get('linked_customer_id')
    assert calls==[('start','+15555550123')]


def test_twilio_pending_response_never_links_and_resend_is_limited(twilio_link):
    _,account,_,calls=twilio_link
    assert 'error' in ca.confirm_link_code(account.id,'sms','000000')
    assert not account.attributes.get('linked_customer_id')
    assert 'error' in ca.request_link_code(account.id,'sms')
    assert len(calls)==2


def test_twilio_configuration_does_not_promote_legacy_challenge(twilio_link):
    _,account,_,calls=twilio_link
    challenge=account.attributes['challenges']['sms']
    challenge.pop('provider');challenge['code']='123456'
    assert 'error' in ca.confirm_link_code(account.id,'sms','123456')
    assert not account.attributes.get('linked_customer_id')
    assert len(calls)==1


def test_twilio_link_save_failure_does_not_grant_in_memory_access(twilio_link,monkeypatch):
    _,account,_,calls=twilio_link
    saves=[]
    def save(_):
        saves.append(True)
        if len(saves)==2: raise OSError('fixture final save failure')
    monkeypatch.setattr(ca,'save_graph',save)
    with pytest.raises(OSError,match='fixture final save failure'):
        ca.confirm_link_code(account.id,'sms','123456')
    assert not account.attributes.get('linked_customer_id')
    assert not account.attributes['phone_verified']
    assert not account.attributes['challenges']['sms']['consumed']


def test_twilio_missing_configuration_never_falls_back_to_dev_code(twilio_link,monkeypatch):
    from core.twilio_sms_verification import VerifyConfig
    _,account,_,calls=twilio_link
    monkeypatch.setattr(VerifyConfig,'from_environment',classmethod(lambda cls:None))
    account.attributes['challenges']={}
    result=ca.request_link_code(account.id,'sms')
    assert 'error' in result
    assert 'dev_code' not in result
    assert not account.attributes['challenges']
    assert len(calls)==1


def test_customer_session_revocation_and_disabled_account():
    result=ca.sign_up('revoke@example.com','hunter2xyz')
    account_id=result['account']['account_id'];token=result['account']['token']
    assert ca.verify_customer_token(token)
    assert ca.revoke_customer_sessions(account_id)=={'revoked':True}
    assert ca.verify_customer_token(token) is None
    fresh=ca.log_in('revoke@example.com','hunter2xyz')['account']['token']
    assert ca.verify_customer_token(fresh)
    ca.get_account(account_id).attributes['status']='disabled'
    assert ca.verify_customer_token(fresh) is None


def test_failed_session_revocation_save_preserves_prior_state(monkeypatch):
    result=ca.sign_up('revoke-failure@example.com','hunter2xyz')
    def fail(_): raise OSError('fixture revoke failure')
    monkeypatch.setattr(ca,'save_graph',fail)
    with pytest.raises(OSError): ca.revoke_customer_sessions(result['account']['account_id'])
    assert ca.verify_customer_token(result['account']['token'])


def test_logout_api_revokes_only_authenticated_account():
    first=ca.sign_up('first-logout@example.com','hunter2xyz')['account']
    second=ca.sign_up('second-logout@example.com','hunter2xyz')['account']
    assert 'error' in ca_api.logout_api('')
    assert ca_api.logout_api('Bearer '+first['token'])=={'revoked':True}
    assert ca.verify_customer_token(first['token']) is None
    assert ca.verify_customer_token(second['token']) is not None

@pytest.mark.parametrize('token', [None, 123, '', 'a.é', '\ud800.signature', 'x' * 4097, 'a.' + 'g' * 64])
def test_malformed_customer_tokens_fail_closed(token):
    assert ca.verify_customer_token(token) is None


def test_real_http_logout_revokes_customer_access():
    from fastapi.testclient import TestClient
    from api.app import app
    client = TestClient(app)
    signup = client.post('/public/customer/signup', json={
        'email': 'http-logout@example.com', 'password': 'hunter2xyz'})
    assert signup.status_code == 200
    token = signup.json()['account']['token']
    headers = {'Authorization': 'Bearer ' + token}
    assert client.get('/customer/me', headers=headers).json()['account']['email'] == 'http-logout@example.com'
    assert client.post('/customer/logout', headers=headers).json() == {'revoked': True}
    assert 'error' in client.get('/customer/me', headers=headers).json()
    assert 'error' in client.post('/customer/logout', headers=headers).json()
    login = client.post('/public/customer/login', json={
        'email': 'http-logout@example.com', 'password': 'hunter2xyz'})
    fresh = login.json()['account']['token']
    assert client.get('/customer/me', headers={'Authorization': 'Bearer ' + fresh}).json()['account']

@pytest.fixture
def privateemail_link(monkeypatch):
    monkeypatch.delenv("DEALEROS_DEMO", raising=False)
    from core import privateemail_verification as pe
    monkeypatch.setenv('NXTDEAL_CUSTOMER_EMAIL_PROVIDER', 'privateemail')
    monkeypatch.setenv('NXTDEAL_CUSTOMER_SMS_PROVIDER', 'twilio_verify')
    monkeypatch.setattr(pe.PrivateEmailConfig, 'from_environment', classmethod(lambda cls: pe.PrivateEmailConfig('info@example.com','fixture')))
    sent = []
    def send(self, recipient, code):
        sent.append((recipient, code))
        return {'provider':'privateemail','delivery':'accepted','verified':False}
    monkeypatch.setattr(pe.PrivateEmailVerification, 'send_code', send)
    record = _seed_customer()
    result = ca.sign_up('pat@example.com','hunter2xyz')
    account = ca.get_account(result['account']['account_id'])
    return record, account, result, sent


def test_privateemail_links_only_after_code_and_never_exposes_code(privateemail_link):
    record, account, result, sent = privateemail_link
    assert result['delivery'] == 'accepted'
    assert 'dev_code' not in result
    code = sent[0][1]
    assert sent[0][0] == 'pat@example.com'
    assert code not in str(account.attributes['challenges'])
    assert not account.attributes['linked_customer_id']
    assert 'error' in ca.confirm_link_code(account.id,'email','invalid')
    assert ca.confirm_link_code(account.id,'email',code)['linked']
    assert account.attributes['linked_customer_id'] == record.id
    assert 'error' in ca.confirm_link_code(account.id,'email',code)


@pytest.mark.parametrize('change', ['contact','pending','expired','attempts'])
def test_privateemail_stale_challenge_cannot_link(privateemail_link, change):
    record, account, _, sent = privateemail_link
    challenge = account.attributes['challenges']['email']
    if change == 'contact': record.attributes['email'] = 'changed@example.com'
    if change == 'pending': account.attributes['pending_link_customer_id'] = 'CUST-other'
    if change == 'expired': challenge['expires_at'] = 0
    if change == 'attempts': challenge['attempts'] = ca.OTP_MAX_ATTEMPTS
    assert 'error' in ca.confirm_link_code(account.id,'email',sent[0][1])
    assert not account.attributes['linked_customer_id']


def test_privateemail_resend_cooldown(privateemail_link):
    _, account, _, sent = privateemail_link
    assert 'error' in ca.request_link_code(account.id,'email')
    assert len(sent) == 1


def test_privateemail_save_failure_never_sends_or_grants_access(privateemail_link, monkeypatch):
    _, account, _, sent = privateemail_link
    code = sent[0][1]
    def fail(_): raise OSError('fixture failure')
    monkeypatch.setattr(ca,'save_graph',fail)
    with pytest.raises(OSError): ca.confirm_link_code(account.id,'email',code)
    assert not account.attributes['linked_customer_id']
    account.attributes['challenges'] = {}
    with pytest.raises(OSError): ca.request_link_code(account.id,'email')
    assert not account.attributes['challenges']
    assert len(sent) == 1

@pytest.mark.parametrize('operation', ['vehicles','searches','appointments'])
def test_provider_link_unlocks_only_own_companion_data_then_logout_revokes(privateemail_link, operation):
    from core import saved_vehicles, saved_searches, customer_appointments
    _, account, result, sent = privateemail_link
    token = result['account']['token']
    reads = {'vehicles':saved_vehicles.get_saved_vehicles,
             'searches':saved_searches.get_saved_searches,
             'appointments':customer_appointments.get_my_appointments}
    read = reads[operation]
    assert 'error' in read(token)
    assert ca.confirm_link_code(account.id,'email',sent[0][1])['linked']
    assert 'error' not in read(token)
    assert account.attributes['link_proof']['customer_id'] == 'CUST-00001'
    assert ca.revoke_customer_sessions(account.id)['revoked']
    assert 'error' in read(token)

@pytest.mark.parametrize('change', ['contact','pending','disabled','challenge','expiry'])
def test_provider_response_rechecks_state_before_linking(twilio_link, monkeypatch, change):
    from core import twilio_sms_verification as tv
    record, account, _, _ = twilio_link
    def check(self, sid, code):
        if change == 'contact': record.attributes['phone'] = '+15555550999'
        if change == 'pending': account.attributes['pending_link_customer_id'] = 'CUST-other'
        if change == 'disabled': account.attributes['status'] = 'disabled'
        if change == 'challenge': account.attributes['challenges']['sms'] = {}
        if change == 'expiry': account.attributes['challenges']['sms']['expires_at'] = 0
        return {'verified':True}
    monkeypatch.setattr(tv.TwilioSmsVerification,'check',check)
    assert 'error' in ca.confirm_link_code(account.id,'sms','123456')
    assert not account.attributes['linked_customer_id']
    assert 'link_proof' not in account.attributes


@pytest.mark.parametrize('operation', ['request','confirm'])
def test_overlapping_provider_requests_are_serialized(twilio_link, monkeypatch, operation):
    from concurrent.futures import ThreadPoolExecutor, TimeoutError
    from threading import Event
    from core import twilio_sms_verification as tv
    _, account, _, _ = twilio_link
    entered, release, second_started = Event(), Event(), Event()
    calls = []
    def provider(*args):
        calls.append(True)
        entered.set()
        assert release.wait(3), 'test did not release provider'
        return {'verified':True,'verification_sid':'VE'+'4'*32}
    if operation == 'request':
        account.attributes['challenges'] = {}
        monkeypatch.setattr(tv.TwilioSmsVerification,'start',provider)
        invoke = lambda: ca.request_link_code(account.id,'sms')
    else:
        monkeypatch.setattr(tv.TwilioSmsVerification,'check',provider)
        invoke = lambda: ca.confirm_link_code(account.id,'sms','123456')
    def second_call():
        second_started.set()
        return invoke()
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(invoke)
        try:
            assert entered.wait(3)
            second = executor.submit(second_call)
            assert second_started.wait(3)
            with pytest.raises(TimeoutError): second.result(timeout=0.1)
        finally:
            release.set()
        assert 'error' not in first.result(timeout=3)
        assert 'error' in second.result(timeout=3)
    assert len(calls) == 1

@pytest.mark.parametrize('fixture_name,channel', [('twilio_link', 'sms'), ('privateemail_link', 'email')])
def test_send_budget_survives_new_accounts_and_provider_failures(request, monkeypatch, fixture_name, channel):
    record, account, result, initial_calls = request.getfixturevalue(fixture_name)
    failures = []
    def failed_send(*args):
        failures.append(True)
        return {'error': 'Provider acknowledgement unconfirmed.'}
    if channel == 'sms':
        from core.twilio_sms_verification import TwilioSmsVerification
        monkeypatch.setattr(TwilioSmsVerification, 'start', failed_send)
    else:
        from core.privateemail_verification import PrivateEmailVerification
        monkeypatch.setattr(PrivateEmailVerification, 'send_code', failed_send)
    # Initial fixture sent once. Two uncertain attempts from different accounts
    # exhaust this contact's budget; the fourth attempt cannot call the provider.
    for i in range(3):
        other = Entity(id=f'CACC-BUDGET-{i}', entity_type=CUSTOMER_ACCOUNT,
                       attributes={'status': 'active', 'pending_link_customer_id': record.id})
        ledger.add_entity(other)
        outcome = ca._issue_code(other, channel)
        if i < 2:
            assert 'unconfirmed' in outcome['error']
        else:
            assert 'limit reached' in outcome['error']
            assert 'challenges' not in other.attributes
    assert len(failures) == 2

@pytest.mark.parametrize('operation', ['request', 'confirm'])
def test_api_request_revoked_before_account_lock_is_rejected(twilio_link, monkeypatch, operation):
    _, account, result, calls = twilio_link
    token = result['account']['token']
    original = ca.request_link_code if operation == 'request' else ca.confirm_link_code
    def revoke_before_operation(*args, **kwargs):
        ca.revoke_customer_sessions(account.id)
        return original(*args, **kwargs)
    monkeypatch.setattr(ca, 'request_link_code' if operation == 'request' else 'confirm_link_code', revoke_before_operation)
    before = len(calls)
    if operation == 'request':
        response = ca_api.request_link_code_api('Bearer ' + token, 'sms')
    else:
        response = ca_api.confirm_link_code_api('Bearer ' + token, 'sms', '123456')
    assert 'session expired' in response['error']
    assert len(calls) == before
    assert not account.attributes['linked_customer_id']


def test_http_logout_during_provider_check_prevents_link_and_summary(twilio_link, monkeypatch):
    from fastapi.testclient import TestClient
    from api.app import app
    from core.twilio_sms_verification import TwilioSmsVerification
    _, account, result, _ = twilio_link
    headers = {'Authorization': 'Bearer ' + result['account']['token']}
    client = TestClient(app)
    def check(self, sid, code):
        assert client.post('/customer/logout', headers=headers).json() == {'revoked': True}
        return {'verified': True}
    monkeypatch.setattr(TwilioSmsVerification, 'check', check)
    response = client.post('/customer/link/confirm', headers=headers, json={'channel': 'sms', 'code': '123456'})
    assert 'session expired' in response.json()['error']
    assert 'account' not in response.json()
    assert not account.attributes['linked_customer_id']
    assert 'link_proof' not in account.attributes
    assert ca.verify_customer_token(result['account']['token']) is None

@pytest.mark.parametrize('setting', ['', 'disabled', 'other_provider'])
def test_disabled_sms_provider_cannot_confirm_existing_challenge(twilio_link, monkeypatch, setting):
    _, account, _, calls = twilio_link
    monkeypatch.setenv('NXTDEAL_CUSTOMER_SMS_PROVIDER', setting)
    assert 'error' in ca.confirm_link_code(account.id, 'sms', '123456')
    assert calls == [('start', '+15555550123')]
    assert not account.attributes['linked_customer_id']
    assert 'link_proof' not in account.attributes


def test_sms_provider_disabled_during_check_cannot_grant_authority(twilio_link, monkeypatch):
    from core.twilio_sms_verification import TwilioSmsVerification
    _, account, _, _ = twilio_link
    def check(self, sid, code):
        monkeypatch.delenv('NXTDEAL_CUSTOMER_SMS_PROVIDER')
        return {'verified': True}
    monkeypatch.setattr(TwilioSmsVerification, 'check', check)
    assert 'error' in ca.confirm_link_code(account.id, 'sms', '123456')
    assert not account.attributes['linked_customer_id']
    assert 'link_proof' not in account.attributes


def test_email_provider_disabled_during_confirmation_cannot_grant_authority(privateemail_link, monkeypatch):
    _, account, _, sent = privateemail_link
    def disable_during_attempt_save(_):
        monkeypatch.delenv('NXTDEAL_CUSTOMER_EMAIL_PROVIDER', raising=False)
    monkeypatch.setattr(ca, 'save_graph', disable_during_attempt_save)
    assert 'error' in ca.confirm_link_code(account.id, 'email', sent[0][1])
    assert not account.attributes['linked_customer_id']
    assert 'link_proof' not in account.attributes

@pytest.mark.parametrize('value', [{'private': '5550100'}, ['5550100'], 5550100, True])
def test_malformed_crm_contacts_do_not_match_or_crash(value):
    record = _seed_customer(email=value, phone=value)
    assert ca._find_matching_customer('valid@example.com', '5550100') is None
    assert ca._customer_sms_destination(record) == ''
    assert record.attributes['email'] is value and record.attributes['phone'] is value


def test_malformed_crm_summary_values_are_not_exposed():
    record = _seed_customer(name={'private': 'fixture-secret'}, email=['fixture-secret'], phone={'private':'fixture-secret'})
    record.attributes.update(first_name=['fixture-secret'], last_name={'private':'fixture-secret'})
    summary = ca._customer_summary(record.id)
    assert summary == {'customer_id':record.id, 'name':record.id, 'email':None, 'phone':None}
    assert 'fixture-secret' not in str(summary)


def test_contact_normalization_rejects_oversized_or_unicode_digit_values():
    assert ca._normalize_email('x' * 255) == ''
    assert ca._normalize_phone('1' * 33) == ''
    assert ca._normalize_phone('５５５０１００') == ''
    assert ca._normalize_phone('５５５0100') == ''
    assert ca._normalize_phone('+1 (555) 555-0123') == '15555550123'


def test_failed_signup_graph_save_removes_phantom_account_and_allows_retry(monkeypatch):
    existing = ca.sign_up('existing-fixture@example.com', 'hunter2xyz')['account']
    before_ids = set(ledger.get_all())
    attempted = []
    with monkeypatch.context() as patch:
        def fail(_):
            attempted.extend(set(ledger.get_all()) - before_ids)
            raise OSError('fixture graph failure')
        def unexpected_credentials(): raise AssertionError('credentials must not save after graph failure')
        patch.setattr(ca, 'save_graph', fail)
        patch.setattr(ca, '_save_customer_credentials', unexpected_credentials)
        with pytest.raises(OSError): ca.sign_up('failed-fixture@example.com', 'hunter2xyz')
    assert set(ledger.get_all()) == before_ids
    assert not ca.customer_credential_store.has_email('failed-fixture@example.com')
    assert 'error' in ca.log_in('failed-fixture@example.com', 'hunter2xyz')
    assert ca.verify_customer_token(existing['token']) is not None
    retried = ca.sign_up('failed-fixture@example.com', 'hunter2xyz')['account']
    assert retried['account_id'] not in attempted
    assert ca.verify_customer_token(retried['token']) is not None


def test_concurrent_signup_normalized_email_creates_one_account(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor, TimeoutError
    from threading import Event
    entered, release = Event(), Event()
    original = ca.save_graph
    def block_first_save(path):
        entered.set()
        assert release.wait(5)
        original(path)
    monkeypatch.setattr(ca, 'save_graph', block_first_save)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(ca.sign_up, 'Concurrent@example.com', 'hunter2xyz')
        assert entered.wait(5)
        second = pool.submit(ca.sign_up, ' concurrent@EXAMPLE.com ', 'different-password2')
        try:
            with pytest.raises(TimeoutError): second.result(timeout=0.1)
        finally:
            release.set()
        success, duplicate = first.result(), second.result()
    assert 'account' in success and 'already exists' in duplicate['error']
    accounts = [e for e in ledger.get_all().values() if e.entity_type == CUSTOMER_ACCOUNT]
    assert len(accounts) == 1
    assert ca.log_in('concurrent@example.com', 'hunter2xyz')['account']['account_id'] == accounts[0].id
    assert 'error' in ca.log_in('concurrent@example.com', 'different-password2')


def test_provider_delivery_does_not_hold_signup_creation_lock(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    _seed_customer(email='slow-fixture@example.com')
    entered, release = Event(), Event()
    def slow_delivery(entity, channel):
        entered.set()
        assert release.wait(5)
        return {'delivery':'simulated'}
    monkeypatch.setattr(ca, '_issue_code', slow_delivery)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(ca.sign_up, 'slow-fixture@example.com', 'hunter2xyz')
        assert entered.wait(5)
        try:
            other = pool.submit(ca.sign_up, 'unrelated-fixture@example.com', 'hunter2xyz').result(timeout=3)
            assert 'account' in other
        finally:
            release.set()
        assert first.result()['delivery'] == 'simulated'

@pytest.mark.parametrize('failure_stage', [None, 'graph', 'credentials'])
def test_login_waits_for_signup_initial_persistence(monkeypatch, failure_stage):
    from concurrent.futures import ThreadPoolExecutor, TimeoutError
    from threading import Event
    entered, release = Event(), Event()
    target = '_save_customer_credentials' if failure_stage == 'credentials' else 'save_graph'
    original = getattr(ca, target)
    def blocked_save(*args):
        entered.set()
        assert release.wait(5)
        if failure_stage:
            raise OSError('fixture signup save failure')
        original(*args)
    monkeypatch.setattr(ca, target, blocked_save)
    with ThreadPoolExecutor(max_workers=2) as pool:
        signup = pool.submit(ca.sign_up, 'pending-fixture@example.com', 'hunter2xyz')
        assert entered.wait(5)
        login = pool.submit(ca.log_in, 'pending-fixture@example.com', 'hunter2xyz')
        try:
            with pytest.raises(TimeoutError): login.result(timeout=0.1)
        finally:
            release.set()
        if failure_stage:
            with pytest.raises(OSError): signup.result()
            assert 'error' in login.result()
        else:
            created = signup.result()['account']
            authenticated = login.result()['account']
            assert authenticated['account_id'] == created['account_id']
            assert ca.verify_customer_token(authenticated['token']) is not None


def test_failed_signup_credential_save_denies_login_and_retry_preserves_other_accounts(monkeypatch):
    existing = ca.sign_up('existing-credential@example.com', 'hunter2xyz')['account']
    before_ids = set(ledger.get_all())
    attempted = []
    with monkeypatch.context() as patch:
        def fail():
            attempted.extend(set(ledger.get_all()) - before_ids)
            raise OSError('fixture credential save failure')
        patch.setattr(ca, '_save_customer_credentials', fail)
        with pytest.raises(OSError):
            ca.sign_up('failed-credential@example.com', 'hunter2xyz')
    assert set(ledger.get_all()) == before_ids
    assert not ca.customer_credential_store.has_email('failed-credential@example.com')
    assert 'error' in ca.log_in('failed-credential@example.com', 'hunter2xyz')
    assert ca.verify_customer_token(existing['token']) is not None
    retried = ca.sign_up('failed-credential@example.com', 'hunter2xyz')['account']
    assert retried['account_id'] not in attempted
    assert ca.log_in('failed-credential@example.com', 'hunter2xyz')['account']['account_id'] == retried['account_id']


@pytest.mark.parametrize('state', ['active', 'exhausted', 'expired', 'consumed'])
def test_twilio_reused_verification_keeps_original_limits(twilio_link, monkeypatch, state):
    _, account, _, calls = twilio_link
    original = account.attributes['challenges']['sms']
    original['requested_at'] -= 61
    original['attempts'] = 3
    if state == 'exhausted': original['attempts'] = ca.OTP_MAX_ATTEMPTS
    if state == 'expired': original['expires_at'] = 0
    if state == 'consumed': original['consumed'] = True
    expires, attempts, consumed = original['expires_at'], original['attempts'], original['consumed']
    assert ca.request_link_code(account.id, 'sms')['delivery'] == 'pending'
    current = account.attributes['challenges']['sms']
    assert (current['expires_at'], current['attempts'], current['consumed']) == (expires, attempts, consumed)
    before = len(calls)
    result = ca.confirm_link_code(account.id, 'sms', '123456')
    if state == 'active':
        assert result['linked'] is True
    else:
        assert 'error' in result and len(calls) == before
        assert not account.attributes['linked_customer_id']


def test_twilio_distinct_verification_can_start_fresh_challenge(twilio_link, monkeypatch):
    from core.twilio_sms_verification import TwilioSmsVerification
    _, account, _, _ = twilio_link
    old = account.attributes['challenges']['sms']
    old.update(requested_at=0, expires_at=0, attempts=5)
    monkeypatch.setattr(TwilioSmsVerification, 'start', lambda self, phone: {'verification_sid':'VE'+'5'*32})
    assert ca.request_link_code(account.id, 'sms')['delivery'] == 'pending'
    current = account.attributes['challenges']['sms']
    assert current['attempts'] == 0 and current['expires_at'] > 0
    assert current['verification_sid'] != old['verification_sid']


def test_twilio_reused_verification_cannot_rebind_changed_contact(twilio_link):
    from copy import deepcopy
    record, account, _, _ = twilio_link
    account.attributes['challenges']['sms']['requested_at'] = 0
    before = deepcopy(account.attributes['challenges']['sms'])
    record.attributes['phone'] = '+15555550999'
    assert 'error' in ca.request_link_code(account.id, 'sms')
    assert account.attributes['challenges']['sms'] == before


@pytest.mark.parametrize('same_sid', [False, True])
def test_sms_resend_save_failure_restores_original_challenge_limits(twilio_link, monkeypatch, same_sid):
    from copy import deepcopy
    from core.twilio_sms_verification import TwilioSmsVerification
    _, account, _, _ = twilio_link
    original = account.attributes['challenges']['sms']
    original.update(requested_at=0, attempts=3)
    before = deepcopy(account.attributes)
    starts = []
    def start(self, phone):
        starts.append(phone)
        return {'verification_sid': original['verification_sid'] if same_sid else 'VE'+'5'*32}
    def fail(_): raise OSError('fixture resend persistence failure')
    monkeypatch.setattr(TwilioSmsVerification, 'start', start)
    monkeypatch.setattr(ca, 'save_graph', fail)
    with pytest.raises(OSError): ca.request_link_code(account.id, 'sms')
    assert starts == ['+15555550123']
    assert account.attributes == before
    assert not account.attributes['linked_customer_id']


def test_sms_resend_uncertain_provider_acceptance_keeps_existing_challenge(twilio_link, monkeypatch):
    from copy import deepcopy
    from core.twilio_sms_verification import TwilioSmsVerification
    _, account, _, _ = twilio_link
    account.attributes['challenges']['sms'].update(requested_at=0, attempts=3)
    before = deepcopy(account.attributes)
    monkeypatch.setattr(TwilioSmsVerification, 'start', lambda self, phone: {'error':'Verification provider is unavailable.'})
    def unexpected(_): raise AssertionError('unknown provider result must not save a new challenge')
    monkeypatch.setattr(ca, 'save_graph', unexpected)
    assert 'error' in ca.request_link_code(account.id, 'sms')
    assert account.attributes == before


def test_uncertain_email_resend_can_verify_only_the_persisted_new_code(privateemail_link, monkeypatch):
    from core.privateemail_verification import PrivateEmailVerification
    _, account, _, sent = privateemail_link
    old_code = sent[0][1]
    new_code = '000001' if old_code != '000001' else '000002'
    account.attributes['challenges']['email']['requested_at'] = 0
    monkeypatch.setattr(ca.secrets, 'randbelow', lambda _: int(new_code))
    attempts = []
    def uncertain(self, recipient, code):
        attempts.append(code)
        stored = account.attributes['challenges']['email']
        assert stored['code_digest'] == ca._email_code_digest(stored['nonce'], code)
        return {'error':'Email acceptance could not be confirmed.', 'reason':'acceptance_unconfirmed'}
    monkeypatch.setattr(PrivateEmailVerification, 'send_code', uncertain)
    response = ca.request_link_code(account.id, 'email')
    assert response['reason'] == 'acceptance_unconfirmed'
    assert attempts == [new_code] and new_code not in str(response)
    assert 'error' in ca.confirm_link_code(account.id, 'email', old_code)
    assert ca.confirm_link_code(account.id, 'email', new_code)['linked'] is True


@pytest.mark.parametrize('channel', ['email', 'sms'])
def test_failed_link_save_cannot_undo_concurrent_successful_logout(request, monkeypatch, channel):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    _, account, result, evidence = request.getfixturevalue('privateemail_link' if channel == 'email' else 'twilio_link')
    customer_token = result['account']['token']
    code = evidence[0][1] if channel == 'email' else '123456'
    entered, release = Event(), Event()
    saves = []
    def save(_):
        saves.append(True)
        if len(saves) == 2:  # after attempt persistence, final link write
            entered.set()
            assert release.wait(5)
            raise OSError('fixture final link save failed')
    monkeypatch.setattr(ca, 'save_graph', save)
    with ThreadPoolExecutor(max_workers=1) as pool:
        link = pool.submit(ca.confirm_link_code, account.id, channel, code)
        assert entered.wait(5)
        try:
            assert ca.revoke_customer_sessions(account.id) == {'revoked':True}
        finally:
            release.set()
        with pytest.raises(OSError): link.result()
    assert account.attributes['session_version'] == 1
    assert ca.verify_customer_token(customer_token) is None
    assert not account.attributes['linked_customer_id']
    assert 'link_proof' not in account.attributes


def test_failed_logout_rolls_back_only_its_session_field(twilio_link, monkeypatch):
    _, account, result, _ = twilio_link
    def fail(_):
        account.attributes['fixture_concurrent_field'] = {'retained':True}
        raise OSError('fixture logout write failed')
    monkeypatch.setattr(ca, 'save_graph', fail)
    with pytest.raises(OSError): ca.revoke_customer_sessions(account.id)
    assert account.attributes['fixture_concurrent_field'] == {'retained':True}
    assert 'session_version' not in account.attributes
    assert ca.verify_customer_token(result['account']['token']) is not None


@pytest.mark.parametrize('logout_fails', [False, True])
def test_login_token_waits_for_logout_persistence_or_rollback(monkeypatch, logout_fails):
    from concurrent.futures import ThreadPoolExecutor, TimeoutError
    from threading import Event
    created = ca.sign_up('logout-race@example.com', 'hunter2xyz')['account']
    entered, release = Event(), Event()
    def save(_):
        entered.set()
        assert release.wait(5)
        if logout_fails: raise OSError('fixture logout failure')
    with monkeypatch.context() as patch:
        patch.setattr(ca, 'save_graph', save)
        with ThreadPoolExecutor(max_workers=2) as pool:
            logout = pool.submit(ca.revoke_customer_sessions, created['account_id'])
            assert entered.wait(5)
            login = pool.submit(ca.log_in, 'logout-race@example.com', 'hunter2xyz')
            try:
                with pytest.raises(TimeoutError): login.result(timeout=0.1)
            finally:
                release.set()
            if logout_fails:
                with pytest.raises(OSError): logout.result()
            else:
                assert logout.result() == {'revoked':True}
            new_token = login.result()['account']['token']
    payload = ca.verify_customer_token(new_token)
    assert payload is not None
    assert payload['session_version'] == (0 if logout_fails else 1)
    assert (ca.verify_customer_token(created['token']) is not None) == logout_fails
    ca.revoke_customer_sessions(created['account_id'])
    assert ca.verify_customer_token(new_token) is None


def test_http_two_customer_verification_privacy_and_revocation_journey(privateemail_link, monkeypatch):
    """Real application routes, fictional contacts, captured fake email only."""
    from fastapi.testclient import TestClient
    from api.app import app
    first_record, _, _, sent = privateemail_link
    first_code = sent[0][1]
    # Ensure distinct proof codes so this test never depends on a random collision.
    monkeypatch.setattr(ca.secrets, 'randbelow', lambda upper: (int(first_code) + 1) % upper)
    second_record = Entity(id='SYN-CUSTOMER-TWO', entity_type=CUSTOMER,
                           attributes={'name': 'Fictional Second', 'email': 'second@example.com'})
    ledger.add_entity(second_record)
    client = TestClient(app)  # Deliberately no production lifespan/workers.

    first_login = client.post('/public/customer/login', json={
        'email': 'pat@example.com', 'password': 'hunter2xyz'}).json()
    second_signup = client.post('/public/customer/signup', json={
        'email': 'second@example.com', 'password': 'Fictional2026!'}).json()
    first = {'Authorization': 'Bearer ' + first_login['account']['token']}
    second = {'Authorization': 'Bearer ' + second_signup['account']['token']}
    assert len(sent) == 2 and sent[1][0] == 'second@example.com'
    second_code = sent[1][1]
    assert first_code != second_code
    assert 'dev_code' not in second_signup
    for headers in (first, second):
        pending = client.get('/customer/me', headers=headers).json()['account']
        assert pending['linked'] is False and 'customer' not in pending

    for headers, foreign_code in ((first, second_code), (second, first_code)):
        denied = client.post('/customer/link/confirm', headers=headers,
                             json={'channel': 'email', 'code': foreign_code}).json()
        assert 'error' in denied
        assert 'customer' not in client.get('/customer/me', headers=headers).json()['account']

    for headers, own_code, expected_id in (
            (first, first_code, first_record.id), (second, second_code, second_record.id)):
        confirmed = client.post('/customer/link/confirm', headers=headers,
                                json={'channel': 'email', 'code': own_code}).json()
        assert confirmed['linked'] is True
        summary = client.get('/customer/me', headers=headers).json()['account']
        assert summary['customer']['customer_id'] == expected_id
        assert 'error' in client.post('/customer/link/confirm', headers=headers,
                                     json={'channel': 'email', 'code': own_code}).json()

    # Changing the matched contact removes access to its formerly verified summary.
    first_record.attributes['email'] = 'changed@example.com'
    summary = client.get('/customer/me', headers=first).json()['account']
    assert summary['linked'] is False and 'customer' not in summary
    assert client.get('/customer/me', headers=second).json()['account']['linked'] is True

    # Logout revokes every previously issued token for only the second account.
    second_login = client.post('/public/customer/login', json={
        'email': 'second@example.com', 'password': 'Fictional2026!'}).json()
    another = {'Authorization': 'Bearer ' + second_login['account']['token']}
    assert client.post('/customer/logout', headers=second).json() == {'revoked': True}
    for headers in (second, another):
        assert 'error' in client.get('/customer/me', headers=headers).json()
        assert 'error' in client.post('/customer/link/confirm', headers=headers,
                                     json={'channel': 'email', 'code': second_code}).json()
    assert 'account' in client.get('/customer/me', headers=first).json()
    # Verified account journeys must not accidentally activate legacy Garage access.
    assert client.get('/public/garage/vehicles', headers=first).status_code == 503
    assert len(sent) == 2


def test_simulated_link_cannot_issue_or_expose_code_in_production(monkeypatch):
    monkeypatch.delenv("DEALEROS_DEMO", raising=False)
    monkeypatch.delenv("NXTDEAL_CUSTOMER_EMAIL_PROVIDER", raising=False)
    monkeypatch.delenv("NXTDEAL_CUSTOMER_SMS_PROVIDER", raising=False)
    monkeypatch.setattr(ca.integrations_registry, "is_live", lambda _: False)
    _seed_customer()
    account = Entity("ACCT-REVIEW", CUSTOMER_ACCOUNT, {"pending_link_customer_id": "CUST-00001"})
    ledger.add_entity(account)
    result = ca._issue_code(account, "email")
    assert result["blocked"] is True
    assert "dev_code" not in result
    assert "challenges" not in account.attributes
