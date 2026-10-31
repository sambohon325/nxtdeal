"""Shared negative suppression check; absence of a flag is not consent evidence."""
from datetime import datetime, timezone

from core.dealeros import ledger
from core.entity_types import CUSTOMER, LEAD


def _destination(value):
    text = str(value or '').strip().casefold()
    if '@' in text:
        return ('email', text)
    digits = ''.join(c for c in text if c.isascii() and c.isdigit())
    if len(digits) == 11 and digits.startswith('1'):
        digits = digits[1:]
    return ('phone', digits) if len(digits) >= 7 else ('literal', text)


def _channel_name(value):
    value = str(value).strip().casefold()
    return "voice" if value in ("phone", "call", "voice") else value


def _recorded_consent_blocks(customer_id, channels):
    """Match existing agent consent ordering; imported claims never grant access."""
    records = [e for e in ledger.get_all().values()
               if e.entity_type in ('Consent', 'ImportedConsent')
               and e.attributes.get('customer_id') == customer_id
               and e.attributes.get('workspace_id', ledger.tenant.workspace_id) == ledger.tenant.workspace_id]
    for channel in channels:
        relevant = [e for e in records if isinstance(e.attributes.get('channel'), str)
                    and _channel_name(e.attributes['channel']) == channel]
        if not relevant:
            continue  # No grant implied; this check only enforces existing evidence.
        dated = []
        for record in relevant:
            try:
                timestamp = datetime.fromisoformat(record.attributes['occurred_at'])
                if timestamp.tzinfo is None or timestamp > datetime.now(timezone.utc):
                    return True
            except (KeyError, TypeError, ValueError):
                return True
            dated.append((timestamp, record))
        latest = max(timestamp for timestamp, _ in dated)
        if any(record.entity_type != 'Consent' or record.attributes.get('status') not in
               ('granted', 'opted_in', 'subscribed')
               for timestamp, record in dated if timestamp == latest):
            return True
    return False


def contact_suppression(to, customer_id=None, channels=()):
    """Any matching CRM record's explicit do-not-contact flag denies dispatch.

    Check duplicate records as well as the linked record so free typing or an
    alternate unsuppressed duplicate cannot bypass an existing suppression.
    Unknown nonempty flag values fail closed; explicit false values do not.
    """
    channels = tuple(_channel_name(channel) for channel in channels)
    # Retained consent evidence still applies when the referenced CRM record was
    # removed or is temporarily absent. Do not require a Customer/Lead join before
    # honoring a withdrawal addressed by its explicit customer identifier.
    for identifier in (customer_id, to):
        if isinstance(identifier, str) and identifier and _recorded_consent_blocks(identifier, channels):
            return {'error': 'Contact is suppressed by recorded channel consent.',
                    'code': 'contact_suppressed', 'dispatched': False}
    target = _destination(to)
    for entity in ledger.get_all().values():
        if entity.entity_type not in (CUSTOMER, LEAD):
            continue
        attrs = entity.attributes
        matches = entity.id == customer_id or to == entity.id or any(
            attrs.get(key) and _destination(attrs[key]) == target for key in ('phone', 'Phone', 'phone_number', 'mobile', 'cell',
                         'email', 'Email', 'email_address')
        )
        if not matches:
            continue
        for key in ('do_not_contact', 'DoNotContact'):
            flag = attrs.get(key)
            if flag is None or flag is False or flag == 0:
                continue
            if isinstance(flag, str) and flag.strip().casefold() in ('', 'false', '0', 'no'):
                continue
            return {'error': 'Contact is suppressed by a do-not-contact preference.',
                    'code': 'contact_suppressed', 'dispatched': False}
        if _recorded_consent_blocks(entity.id, channels):
            return {'error': 'Contact is suppressed by recorded channel consent.',
                    'code': 'contact_suppressed', 'dispatched': False}
    return None
