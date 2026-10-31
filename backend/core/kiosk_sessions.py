"""Unwired, process-local lobby capability boundary; never a staff session.

No routes or singleton are registered here. Activation requires a dedicated kiosk
surface, enrollment review and server-owned tenant identity. Restart fails closed.
"""
from dataclasses import dataclass
import hashlib
import hmac
import math
import secrets
import threading
import time

from core import auth


@dataclass(frozen=True)
class KioskIdentity:
    tenant_id: str
    device_id: str
    expires_at: float


@dataclass(frozen=True)
class _Grant:
    identity: KioskIdentity
    issuer_id: str
    issuer_binding: str


class KioskSessions:
    ACTION = 'lobby:checkin:create'
    TTL_SECONDS = 30 * 60
    MAX_DEVICES = 128
    FRESH_AUTH_SECONDS = 300

    def __init__(self, tenant_id):
        # Obtain this from server configuration, never the caller's tenant header.
        self.tenant_id = self._identifier(tenant_id)
        self._grants = {}
        self._lock = threading.RLock()

    @staticmethod
    def _identifier(value):
        if not isinstance(value, str) or not value.strip() or len(value) > 128:
            raise ValueError('A non-empty identifier of at most 128 characters is required')
        return value.strip()

    @staticmethod
    def _digest(token):
        if (not isinstance(token, str) or len(token) != 49
                or not token.startswith('kiosk_') or not token.isascii()):
            return None
        return hashlib.sha256(token.encode('ascii')).hexdigest()

    @staticmethod
    def _admin(staff_token):
        payload = auth.verify_token(staff_token)
        if (not payload or auth.is_mfa_challenge_token(payload)
                or payload.get('role') != 'ADMIN'):
            raise PermissionError('A current administrator session is required')
        record = auth.credential_store.get_record(payload['employee_id'])
        if not record or record.get('must_change_password'):
            raise PermissionError('Complete the required password change first')
        authenticated = payload.get('authenticated_at')
        if (type(authenticated) not in (int, float) or not math.isfinite(authenticated)
                or not 0 <= time.time() - authenticated <= KioskSessions.FRESH_AUTH_SECONDS):
            raise PermissionError('Fresh administrator sign-in is required')
        return payload

    @staticmethod
    def _current(grant):
        if grant.identity.expires_at <= time.time():
            return False
        record = auth.credential_store.get_record(grant.issuer_id)
        if not record or record.get('must_change_password'):
            return False
        try:
            # Same credential-version binding used by dealer staff sessions;
            # never retain the parent staff token or its password/hash material.
            binding = auth._credential_binding(grant.issuer_id, 'ADMIN')
        except ValueError:
            return False
        return hmac.compare_digest(binding, grant.issuer_binding)

    def issue(self, staff_token, device_id):
        issuer = self._admin(staff_token)
        device_id = self._identifier(device_id)
        with self._lock:
            # Waiting for an in-flight write must not preserve stale staff authority.
            issuer = self._admin(staff_token)
            self._grants = {key: grant for key, grant in self._grants.items()
                            if self._current(grant) and grant.identity.device_id != device_id}
            if len(self._grants) >= self.MAX_DEVICES:
                raise RuntimeError('Kiosk device limit reached')
            token = 'kiosk_' + secrets.token_urlsafe(32)
            expires = min(time.time() + self.TTL_SECONDS, issuer['expires_at'])
            identity = KioskIdentity(self.tenant_id, device_id, expires)
            self._grants[self._digest(token)] = _Grant(
                identity, issuer['employee_id'], issuer['credential_binding'])
            return {'token': token, 'expires_at': expires, 'action': self.ACTION}

    def verify(self, token, *, device_id, action):
        """Return a restricted identity, never a role-bearing staff payload."""
        digest = self._digest(token)
        with self._lock:
            grant = self._grants.get(digest)
            if not grant:
                return None
            if not self._current(grant):
                self._grants.pop(digest, None)
                return None
            if device_id != grant.identity.device_id or action != self.ACTION:
                return None
            return grant.identity

    def revoke(self, staff_token, device_id):
        self._admin(staff_token)
        device_id = self._identifier(device_id)
        with self._lock:
            self._admin(staff_token)
            self._grants = {key: grant for key, grant in self._grants.items()
                            if grant.identity.device_id != device_id}

    def run_authorized(self, token, *, device_id, action, operation):
        """Serialize a synchronous operation against grant rotation/revocation.

        Credential-store changes use a separate lock domain; authorization is
        checked immediately before invoking the operation, not after its writes.
        """
        with self._lock:
            identity = self.verify(token, device_id=device_id, action=action)
            if identity is None:
                raise PermissionError('Invalid or expired kiosk session')
            return operation(identity)
