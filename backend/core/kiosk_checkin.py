"""Unwired single-process lobby write adapter. No public route or activation."""
from collections import deque
import hashlib
import hmac
import json
import secrets
import threading
import time
import uuid


class CheckinUnconfirmed(RuntimeError):
    pass


class CheckinThrottled(RuntimeError):
    pass


class CheckinConflict(ValueError):
    pass


def _write_walk_in(identity, fields):
    from core.up_system import log_up
    result = log_up('walk_in', 'KIOSK:' + identity.device_id,
                    fields['name'], '', phone=fields['phone'] or None,
                    notes=fields['reason'])
    if isinstance(result, dict) and 'error' in result:
        raise CheckinUnconfirmed('Check-in could not be confirmed. Ask the front desk.')


class KioskCheckin:
    MAX_RECEIPTS = 1024
    MAX_PER_MINUTE = 5

    def __init__(self, sessions, writer=None, journal=None):
        self.sessions = sessions
        self._writer = writer or _write_walk_in
        self._journal = journal
        self._receipts = {}
        self._attempts = {}
        self._fingerprint_key = secrets.token_bytes(32)
        self._lock = threading.RLock()

    @staticmethod
    def _fields(body):
        if not isinstance(body, dict) or set(body) - {'name', 'phone', 'reason'}:
            raise ValueError('Only name, phone and reason are accepted')
        result = {}
        for field, limit in (('name', 120), ('phone', 40), ('reason', 500)):
            value = body.get(field, '')
            if (not isinstance(value, str) or len(value) > limit
                    or any(ord(char) < 32 or ord(char) == 127 for char in value)):
                raise ValueError('Invalid check-in field')
            result[field] = value.strip()
        if not result['name']:
            raise ValueError('Visitor name is required')
        return result

    def submit(self, token, *, device_id, request_id, body):
        fields = self._fields(body)
        if not isinstance(request_id, str) or len(request_id) != 36:
            raise ValueError('A canonical UUID request ID is required')
        try:
            if str(uuid.UUID(request_id)) != request_id:
                raise ValueError()
        except ValueError:
            raise ValueError('A canonical UUID request ID is required') from None
        fingerprint = hmac.new(self._fingerprint_key,
                               json.dumps(fields, sort_keys=True).encode(), hashlib.sha256).digest()

        def write(identity):
            if self._journal is not None:
                return self._journal.run(identity, request_id, fields,
                                         lambda: self._writer(identity, fields))
            now = time.time()
            self._receipts = {key: item for key, item in self._receipts.items()
                              if item['expires'] > now}
            self._attempts = {key: times for key, times in self._attempts.items()
                              if times and times[-1] > now - 60}
            key = (self.sessions._digest(token), request_id)
            previous = self._receipts.get(key)
            if previous:
                if not hmac.compare_digest(previous['fingerprint'], fingerprint):
                    raise CheckinConflict('Request ID was already used for different input')
                if not previous['confirmed']:
                    raise CheckinUnconfirmed('Check-in could not be confirmed. Ask the front desk.')
                return dict(previous['receipt'])
            if len(self._receipts) >= self.MAX_RECEIPTS:
                raise CheckinThrottled('Check-in is busy. Ask the front desk.')
            times = self._attempts.setdefault(identity.device_id, deque())
            while times and times[0] <= now - 60:
                times.popleft()
            if len(times) >= self.MAX_PER_MINUTE:
                raise CheckinThrottled('Too many check-ins. Ask the front desk.')
            times.append(now)
            record = {'expires': identity.expires_at, 'fingerprint': fingerprint,
                      'confirmed': False, 'receipt': {'status': 'checked_in', 'receipt': request_id}}
            self._receipts[key] = record
            try:
                self._writer(identity, fields)
            except Exception:
                # Writes may have partly succeeded. Keep an uncertain tombstone:
                # replaying this key must not create another visitor silently.
                raise CheckinUnconfirmed('Check-in could not be confirmed. Ask the front desk.') from None
            record['confirmed'] = True
            return dict(record['receipt'])

        with self._lock:
            return self.sessions.run_authorized(token, device_id=device_id,
                                                action=self.sessions.ACTION, operation=write)
