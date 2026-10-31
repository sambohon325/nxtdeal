from copy import deepcopy
import pytest
from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import CUSTOMER
from core import customer_comms, integrations_registry, call_center
from core.contact_suppression import contact_suppression

@pytest.fixture
def contact():
    ledger.reset()
    entity = Entity(id='CUST-SUPPRESSION-TEST', entity_type=CUSTOMER,
                    attributes={'phone': '+1 (512) 555-0199', 'email': 'Synthetic@Example.test', 'DoNotContact': True})
    ledger.add_entity(entity)
    yield entity
    ledger.reset()

@pytest.mark.parametrize('to', ['5125550199', '+1-512-555-0199', 'synthetic@example.test', 'CUST-SUPPRESSION-TEST'])
def test_direct_dispatch_denied_before_adapter(contact, monkeypatch, to):
    def forbidden(*args):
        pytest.fail('suppressed destination reached provider')
    monkeypatch.setitem(integrations_registry._ADAPTERS, 'notifications', forbidden)
    monkeypatch.setitem(integrations_registry._ADAPTERS, 'telephony', forbidden)
    before = deepcopy(contact.attributes)
    assert integrations_registry.send_notification(to, {}, ('sms',))['code'] == 'contact_suppressed'
    assert integrations_registry.place_call(to)['code'] == 'contact_suppressed'
    assert contact.attributes == before

@pytest.mark.parametrize('flag', [True, 'true', 'TRUE', '1', 1, 'yes', 'unknown'])
def test_both_crm_flag_spellings_suppress(contact, flag):
    contact.attributes.pop('DoNotContact')
    contact.attributes['do_not_contact'] = flag
    assert contact_suppression('5125550199')

@pytest.mark.parametrize('flag', [False, 'false', 'False', '0', 0, '', None])
def test_explicit_false_is_not_suppression_or_consent(contact, flag):
    contact.attributes['DoNotContact'] = flag
    assert contact_suppression('5125550199') is None


def test_text_denial_creates_no_outbound_record_even_with_override(contact):
    before = set(ledger.get_all())
    result = customer_comms.send_text('EMP-SYNTHETIC', 'synthetic text', customer_id=contact.id, number='5125550100')
    assert result['code'] == 'contact_suppressed'
    assert set(ledger.get_all()) == before


def test_duplicate_and_unlinked_number_cannot_bypass(contact):
    duplicate = Entity(id='CUST-DUPLICATE-TEST', entity_type=CUSTOMER,
                       attributes={'phone': '5125550199', 'do_not_contact': False})
    ledger.add_entity(duplicate)
    assert customer_comms.send_text('EMP-SYNTHETIC', 'test', customer_id=duplicate.id)['code'] == 'contact_suppressed'
    assert customer_comms.send_text('EMP-SYNTHETIC', 'test', number='5125550199')['code'] == 'contact_suppressed'


def test_outbound_call_denied_before_record_creation(contact):
    employee = Entity(id='EMP-SUPPRESSION-TEST', entity_type='Employee', attributes={'name': 'Synthetic'})
    ledger.add_entity(employee)
    before = set(ledger.get_all())
    call, error = call_center.place_outbound_call('sales', '5125550199', employee.id)
    assert call is None and 'suppressed' in error
    assert set(ledger.get_all()) == before


def test_late_call_dispatch_denial_never_reports_connected(contact, monkeypatch):
    contact.attributes['DoNotContact'] = False
    employee = Entity(id='EMP-SUPPRESSION-LATE', entity_type='Employee', attributes={'name': 'Synthetic'})
    ledger.add_entity(employee)
    monkeypatch.setattr(integrations_registry, 'place_call', lambda *a: {'error': 'suppressed', 'code': 'contact_suppressed'})
    result = customer_comms.place_call(employee.id, customer_id=contact.id)
    assert result == {'error': 'suppressed'}


def test_late_text_dispatch_denial_propagates(contact, monkeypatch):
    contact.attributes['DoNotContact'] = False
    monkeypatch.setattr(integrations_registry, 'send_notification', lambda **k: {'error': 'suppressed', 'code': 'contact_suppressed'})
    result = customer_comms.send_text('EMP-SYNTHETIC', 'test', customer_id=contact.id)
    assert result['code'] == 'contact_suppressed'
    assert 'intelligence' not in result


@pytest.mark.parametrize('key', ['Phone', 'phone_number', 'mobile', 'cell', 'Email', 'email_address'])
def test_imported_contact_aliases_remain_suppressed(contact, key):
    value = contact.attributes.pop('email' if 'mail' in key else 'phone')
    contact.attributes[key] = value
    assert contact_suppression(value)['code'] == 'contact_suppressed'


def consent(contact, status, at='2026-01-01T00:00:00+00:00', kind='Consent', channel='sms', suffix='1'):
    record = Entity(id='CONSENT-SYNTHETIC-' + suffix, entity_type=kind,
                    attributes={'customer_id': contact.id, 'channel': channel, 'status': status, 'occurred_at': at})
    ledger.add_entity(record)
    return record

@pytest.mark.parametrize('status', ['revoked', 'withdrawn', 'opted_out', 'unsubscribed', 'unknown'])
def test_channel_withdrawal_blocks_direct_dispatch(contact, monkeypatch, status):
    contact.attributes['DoNotContact'] = False
    consent(contact, status)
    monkeypatch.setitem(integrations_registry._ADAPTERS, 'notifications', lambda *a: pytest.fail('dispatch attempted'))
    assert integrations_registry.send_notification('5125550199', {}, ('sms',))['code'] == 'contact_suppressed'
    before = set(ledger.get_all())
    assert customer_comms.send_text('EMP-SYNTHETIC', 'test', customer_id=contact.id)['code'] == 'contact_suppressed'
    assert set(ledger.get_all()) == before


def test_other_channel_not_suppressed_and_later_native_grant_clears_withdrawal(contact):
    contact.attributes['DoNotContact'] = False
    consent(contact, 'revoked')
    assert contact_suppression('5125550199', channels=('email',)) is None
    consent(contact, 'granted', '2026-02-01T00:00:00+00:00', suffix='2')
    assert contact_suppression('5125550199', channels=('sms',)) is None
    # A conflicting same-time withdrawal always wins.
    consent(contact, 'revoked', '2026-02-01T00:00:00+00:00', suffix='3')
    assert contact_suppression('5125550199', channels=('sms',))

@pytest.mark.parametrize('at', [None, 'invalid', '2026-01-01T00:00:00'])
def test_invalid_consent_timestamp_cannot_clear_suppression(contact, at):
    contact.attributes['DoNotContact'] = False
    consent(contact, 'granted', at)
    assert contact_suppression('5125550199', channels=('sms',))


def test_imported_grant_cannot_authorize_dispatch(contact):
    contact.attributes['DoNotContact'] = False
    consent(contact, 'granted', kind='ImportedConsent')
    assert contact_suppression('5125550199', channels=('sms',))


def test_other_workspace_consent_does_not_change_current_customer(contact):
    contact.attributes['DoNotContact'] = False
    record = consent(contact, 'revoked')
    record.attributes['workspace_id'] = 'unrelated-workspace'
    assert contact_suppression('5125550199', channels=('sms',)) is None


@pytest.mark.parametrize('status', ['granted', 'revoked'])
def test_future_consent_cannot_determine_present_dispatch(contact, status):
    from core.agent_actions import channel_consent
    contact.attributes['DoNotContact'] = False
    consent(contact, 'revoked')
    consent(contact, status, '2999-01-01T00:00:00+00:00', suffix='future')
    assert contact_suppression('5125550199', channels=('sms',))
    assert channel_consent(contact, 'sms') is False


@pytest.mark.parametrize('channel', ['phone', 'voice', 'call', ' PHONE '])
def test_voice_withdrawal_denies_before_call_creation_or_provider(contact, monkeypatch, channel):
    contact.attributes['DoNotContact'] = False
    consent(contact, 'revoked', channel=channel)
    monkeypatch.setitem(integrations_registry._ADAPTERS, 'telephony', lambda *a: pytest.fail('voice provider reached'))
    assert integrations_registry.place_call('5125550199')['code'] == 'contact_suppressed'
    employee = Entity(id='EMP-VOICE-SYNTHETIC', entity_type='Employee', attributes={'name': 'Synthetic'})
    ledger.add_entity(employee)
    before = set(ledger.get_all())
    result = customer_comms.place_call(employee.id, customer_id=contact.id)
    assert 'error' in result and 'suppressed' in result['error']
    assert set(ledger.get_all()) == before
    assert contact_suppression('5125550199', channels=('sms',)) is None


def test_voice_aliases_share_one_ordered_timeline(contact):
    contact.attributes['DoNotContact'] = False
    consent(contact, 'revoked', channel='phone')
    consent(contact, 'granted', '2026-02-01T00:00:00+00:00', channel='voice', suffix='later')
    assert contact_suppression('5125550199', channels=('call',)) is None
    consent(contact, 'revoked', '2026-02-01T00:00:00+00:00', channel='call', suffix='conflict')
    assert contact_suppression('5125550199', channels=('voice',))


@pytest.mark.parametrize('channel', ['sms', 'email', 'voice'])
def test_retained_withdrawal_survives_missing_crm_record(contact, monkeypatch, channel):
    missing = Entity(id='MISSING-SYNTHETIC-CUSTOMER', entity_type=CUSTOMER, attributes={})
    record = consent(missing, 'revoked', channel=channel)
    assert missing.id not in ledger.get_all()
    assert contact_suppression('5125550100', customer_id=missing.id, channels=(channel,))['code'] == 'contact_suppressed'
    monkeypatch.setitem(integrations_registry._ADAPTERS, 'notifications', lambda *a: pytest.fail('provider reached'))
    monkeypatch.setitem(integrations_registry._ADAPTERS, 'telephony', lambda *a: pytest.fail('provider reached'))
    if channel == 'voice':
        result = integrations_registry.place_call(missing.id)
    else:
        result = integrations_registry.send_notification(missing.id, {}, (channel,))
    assert result['code'] == 'contact_suppressed'
    # The join-independent check must still respect workspace boundaries.
    record.attributes['workspace_id'] = 'unrelated-workspace'
    assert contact_suppression(missing.id, channels=(channel,)) is None


def test_missing_crm_record_does_not_turn_absent_consent_into_grant(contact):
    # None means only "no suppression found", never affirmative authorization.
    assert contact_suppression('MISSING-SYNTHETIC-CUSTOMER', channels=('sms',)) is None
