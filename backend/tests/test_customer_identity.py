"""Authorization regressions for companion data, using synthetic proof only."""
from copy import deepcopy
import pytest
from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import CUSTOMER, CUSTOMER_ACCOUNT, VERIFICATION, LEAD
from core import customer_accounts as accounts
from core.customer_identity import resolve_customer
from core import saved_vehicles, saved_searches, customer_appointments
# Initialize API storage loading before any identity fixture seeds its graph.
from api.app import app


@pytest.fixture
def identity():
    ledger.reset()
    customer = Entity(id='C1', entity_type=CUSTOMER, attributes={'email':'owner@example.com','phone':'+15555550123'})
    account = Entity(id='A1', entity_type=CUSTOMER_ACCOUNT, attributes={
        'status':'active','linked_customer_id':'C1','email_verified':True,
        'link_proof':{'provider':'privateemail','channel':'email','customer_id':'C1',
                      'recipient':'owner@example.com','verified_at':'2026-01-01T00:00:00Z'}})
    ledger.add_entity(customer); ledger.add_entity(account)
    token = accounts.issue_customer_token('A1')
    yield customer, account, token
    ledger.reset()


def test_bound_identity_is_read_only(identity):
    customer, account, token = identity
    before = deepcopy(account.attributes)
    assert resolve_customer(token) == ('C1', None)
    assert account.attributes == before


@pytest.mark.parametrize('change', ['no_proof','legacy_provider','wrong_customer','wrong_contact',
    'changed_contact','unverified','lead','deleted_customer','disabled','revoked','missing_time',
    'invalid_time','naive_time','future_time'])
def test_unproven_or_stale_identity_denied(identity, change):
    customer, account, token = identity
    proof = account.attributes['link_proof']
    if change == 'no_proof': account.attributes.pop('link_proof')
    if change == 'legacy_provider': proof['provider'] = 'simulated'
    if change == 'wrong_customer': proof['customer_id'] = 'C2'
    if change == 'wrong_contact': proof['recipient'] = 'attacker@example.com'
    if change == 'changed_contact': customer.attributes['email'] = 'changed@example.com'
    if change == 'unverified': account.attributes['email_verified'] = False
    if change == 'lead': customer.entity_type = LEAD
    if change == 'deleted_customer': account.attributes['linked_customer_id'] = 'missing'
    if change == 'disabled': account.attributes['status'] = 'disabled'
    if change == 'revoked': account.attributes['session_version'] = 1
    if change == 'missing_time': proof.pop('verified_at')
    if change == 'invalid_time': proof['verified_at'] = 'invalid'
    if change == 'naive_time': proof['verified_at'] = '2026-01-01T00:00:00'
    if change == 'future_time': proof['verified_at'] = '9999-01-01T00:00:00Z'
    assert resolve_customer(token)[0] is None
    assert 'error' in saved_vehicles.get_saved_vehicles(token)
    assert 'error' in saved_searches.get_saved_searches(token)
    assert 'error' in customer_appointments.get_my_appointments(token)
    summary = accounts.me(account.id)['account']
    if change != 'revoked':
        assert 'customer' not in summary
        assert summary['linked_customer_id'] is None
        assert summary['linked'] is False


def test_promoted_legacy_verification_token_never_grants_companion_access(identity):
    ledger.add_entity(Entity(id='V1',entity_type=VERIFICATION,attributes={
        'session_token':'legacy','tier':'verified_human','linked_entity_id':'C1'}))
    assert resolve_customer('legacy')[0] is None
    assert 'error' in saved_vehicles.set_saved_vehicle('legacy','vehicle',True)
    assert 'error' in saved_searches.save_search('legacy',{'make':'Example'})
    assert 'error' in customer_appointments.get_my_appointments('legacy')


def test_sms_proof_requires_original_crm_phone(identity):
    customer, account, token = identity
    account.attributes['phone_verified'] = True
    account.attributes['link_proof'].update(provider='twilio_verify',channel='sms',recipient='+15555550123')
    assert resolve_customer(token) == ('C1',None)
    customer.attributes['phone'] = '+15555550999'
    assert resolve_customer(token)[0] is None


def test_http_account_summary_hides_crm_after_contact_change(identity):
    from fastapi.testclient import TestClient
    customer, account, token = identity
    client = TestClient(app)
    headers = {'Authorization': 'Bearer ' + token}
    before = client.get('/customer/me', headers=headers).json()['account']
    assert before['customer']['email'] == 'owner@example.com'
    customer.attributes['email'] = 'new-owner@example.com'
    after = client.get('/customer/me', headers=headers).json()['account']
    assert 'customer' not in after
    assert after['linked'] is False
    assert after['linked_customer_id'] is None
