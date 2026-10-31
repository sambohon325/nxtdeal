"""Trusted-startup credential references for read-only adapter implementations.

No provider, grant, reference or secret is accepted by a Bridge HTTP endpoint.
Providers and adapters are trusted code, not sandboxed plugins. This broker does
not provision vendor access, verify account ownership or securely erase Python
strings. Deployment code must supply an authorized secret-store implementation.
"""
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
from threading import RLock
from typing import Protocol

from core.dealeros import ledger


class SecretProvider(Protocol):
    def read(self, reference: str) -> Mapping[str, str]: ...


class CredentialUnavailable(ValueError):
    def __init__(self):
        super().__init__("Authorized connector credentials are unavailable")


class SecretValues:
    """Explicit access for trusted adapters; repr and serialization omit values."""
    __slots__ = ("__values", "__validate")

    def __init__(self, values, validate):
        self.__values = dict(values)
        self.__validate = validate

    def __repr__(self):
        return "<SecretValues redacted>"

    def __reduce_ex__(self, protocol):
        raise TypeError("Connector secrets cannot be serialized")

    def assert_current(self):
        """Recheck the original grant after adapter IO, without rereading secrets."""
        self.__validate()

    def require(self, field):
        # A retained bundle must not outlive its original grant. This does not
        # revoke strings an adapter already copied or reread the provider.
        self.__validate()
        if field not in self.__values:
            raise CredentialUnavailable()
        return self.__values[field]


@dataclass(frozen=True)
class Grant:
    workspace_id: str
    system_id: str
    vendor: str
    account_ref: str
    environment: str
    objects: frozenset[str]
    expires_at: datetime
    reference: str = field(repr=False)
    provider: SecretProvider = field(repr=False)


def _identifier(value):
    return isinstance(value, str) and bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,119}", value))


def _objects(values):
    if not isinstance(values, (list, tuple, set, frozenset)) or not 1 <= len(values) <= 100:
        raise CredentialUnavailable()
    if any(not _identifier(value) for value in values):
        raise CredentialUnavailable()
    return frozenset(values)


def _system(system_id):
    entity = ledger.get_entity(system_id)
    if not entity or entity.entity_type != "BridgeSystem" or entity.attributes.get("workspace_id") != ledger.tenant.workspace_id:
        raise CredentialUnavailable()
    return entity.attributes


def validate_secret_values(values):
    """Copy bounded secret fields; callers must never include failures in diagnostics."""
    if not isinstance(values, Mapping) or not 1 <= len(values) <= 20:
        raise CredentialUnavailable()
    copied = dict(values)
    if (not 1 <= len(copied) <= 20 or
            any(not isinstance(key, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", key) or
                not isinstance(value, str) or not value or len(value) > 16384
                for key, value in copied.items())):
        raise CredentialUnavailable()
    if sum(len(value.encode("utf-8")) for value in copied.values()) > 65536:
        raise CredentialUnavailable()
    return copied


class CredentialBroker:
    """Operator-owned, in-memory grants; never persisted in the dealership graph."""
    def __init__(self):
        self._grants = {}
        self._lock = RLock()

    def grant(self, system_id, *, provider, reference, account_ref, environment, objects, expires_at):
        """Trusted configuration only. Replacing a grant invalidates in-flight reads."""
        system = _system(system_id)
        if (not _identifier(reference) or not _identifier(account_ref) or
                environment not in ("synthetic", "sandbox", "production") or
                not callable(getattr(provider, "read", None)) or
                not isinstance(expires_at, datetime) or expires_at.tzinfo is None or
                expires_at.utcoffset() is None or expires_at <= datetime.now(timezone.utc)):
            raise CredentialUnavailable()
        grant = Grant(ledger.tenant.workspace_id, system_id, system["vendor"], account_ref,
                      environment, _objects(objects), expires_at, reference, provider)
        with self._lock:
            self._grants[(grant.workspace_id, system_id)] = grant

    def revoke(self, system_id):
        with self._lock:
            self._grants.pop((ledger.tenant.workspace_id, system_id), None)

    def resolve(self, system_id, *, reference, account_ref, environment, objects):
        """Read current secret material for the exact configured scope, never cache it."""
        requested = _objects(objects)
        with self._lock:
            system = _system(system_id)
            grant = self._grants.get((ledger.tenant.workspace_id, system_id))
            self._check(grant, system, reference, account_ref, environment, requested)
        try:
            # Providers must enforce bounded transport timeouts and avoid logging values.
            copied = validate_secret_values(grant.provider.read(grant.reference))
        except Exception:
            raise CredentialUnavailable() from None
        with self._lock:
            current = self._grants.get((ledger.tenant.workspace_id, system_id))
            if current is not grant:
                raise CredentialUnavailable()
            self._check(grant, _system(system_id), reference, account_ref, environment, requested)
        return SecretValues(copied, lambda: self._assert_current(grant))

    def _assert_current(self, grant):
        with self._lock:
            if self._grants.get((ledger.tenant.workspace_id, grant.system_id)) is not grant:
                raise CredentialUnavailable()
            self._check(grant, _system(grant.system_id), grant.reference, grant.account_ref,
                        grant.environment, grant.objects)

    @staticmethod
    def _check(grant, system, reference, account_ref, environment, objects):
        if (grant is None or grant.workspace_id != ledger.tenant.workspace_id or
                grant.vendor != system["vendor"] or system.get("paused") or
                grant.reference != reference or grant.account_ref != account_ref or
                grant.environment != environment or grant.objects != objects or
                grant.expires_at <= datetime.now(timezone.utc)):
            raise CredentialUnavailable()
