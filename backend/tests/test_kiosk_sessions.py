"""Restricted kiosk enrollment policy, without activating any application route."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import threading
import pytest

from core import auth
from core.kiosk_sessions import KioskSessions


@pytest.fixture
def staff():
    previous = deepcopy(auth.credential_store.credentials)
    auth.credential_store.reset()
    auth.credential_store.set_credential('SYN-ADMIN', 'Fictional2026!', 'ADMIN', must_change_password=False)
    auth.credential_store.set_credential('SYN-SALES', 'Fictional2026!', 'SALES')
    yield auth.issue_token('SYN-ADMIN', 'ADMIN', fresh_auth=True)
    auth.credential_store.load_credentials(previous)


def check(registry, token, device='lobby-one', action=KioskSessions.ACTION):
    return registry.verify(token, device_id=device, action=action)


def test_grant_cannot_authenticate_as_staff_or_read_business_data(staff):
    from api.deps import _authenticate
    registry = KioskSessions('synthetic-a')
    grant = registry.issue(staff, 'lobby-one')
    identity = check(registry, grant['token'])
    assert identity.tenant_id == 'synthetic-a'
    assert identity.device_id == 'lobby-one'
    assert not hasattr(identity, 'role')
    assert auth.verify_token(grant['token']) is None
    payload, error = _authenticate('Bearer ' + grant['token'])
    assert payload is None and error
    for action in ('lobby:checkin:list', 'staff:directory', 'messages:read', '*', None):
        assert check(registry, grant['token'], action=action) is None
    assert check(registry, staff) is None
    assert grant['token'] not in repr(registry._grants)
    assert staff not in repr(registry._grants)


@pytest.mark.parametrize('kind', ['anonymous', 'sales', 'mfa', 'revoked'])
def test_enrollment_and_revocation_require_current_admin(staff, kind):
    registry = KioskSessions('synthetic-a')
    token = {'anonymous': None, 'sales': auth.issue_token('SYN-SALES', 'SALES', fresh_auth=True),
             'mfa': auth.issue_mfa_challenge_token('SYN-ADMIN', 'ADMIN'), 'revoked': staff}[kind]
    if kind == 'revoked':
        auth.credential_store.set_role('SYN-ADMIN', 'SALES')
    with pytest.raises(PermissionError):
        registry.issue(token, 'lobby-one')
    with pytest.raises(PermissionError):
        registry.revoke(token, 'lobby-one')


def test_tenant_device_restart_and_rotation_isolation(staff):
    registry = KioskSessions('synthetic-a')
    old = registry.issue(staff, 'lobby-one')['token']
    other = registry.issue(staff, 'lobby-two')['token']
    assert check(registry, old, device='lobby-two') is None
    assert check(KioskSessions('synthetic-b'), old) is None
    assert check(KioskSessions('synthetic-a'), old) is None
    fresh = registry.issue(staff, 'lobby-one')['token']
    assert check(registry, old) is None
    assert check(registry, fresh)
    registry.revoke(staff, 'lobby-one')
    assert check(registry, fresh) is None
    assert check(registry, other, device='lobby-two')


@pytest.mark.parametrize('mutation', ['password', 'role_roundtrip', 'remove', 'expiry'])
def test_grant_tracks_issuer_revocation_and_expiry(staff, mutation, monkeypatch):
    registry = KioskSessions('synthetic-a')
    grant = registry.issue(staff, 'lobby-one')
    if mutation == 'password':
        auth.credential_store.set_credential('SYN-ADMIN', 'DifferentFictional2026!', 'ADMIN')
    elif mutation == 'role_roundtrip':
        auth.credential_store.set_role('SYN-ADMIN', 'SALES')
        auth.credential_store.set_role('SYN-ADMIN', 'ADMIN')
    elif mutation == 'remove':
        auth.credential_store.reset()
    else:
        monkeypatch.setattr('core.kiosk_sessions.time.time', lambda: grant['expires_at'])
    assert check(registry, grant['token']) is None
    assert not registry._grants


def test_short_parent_expiry_bounds_grant(staff, monkeypatch):
    monkeypatch.setattr(auth, 'TOKEN_TTL_SECONDS', 10)
    staff = auth.issue_token('SYN-ADMIN', 'ADMIN', fresh_auth=True)
    parent = auth.verify_token(staff)
    grant = KioskSessions('synthetic-a').issue(staff, 'lobby-one')
    assert grant['expires_at'] == parent['expires_at']


def test_management_requires_fresh_auth_but_existing_grant_survives_freshness_window(staff, monkeypatch):
    registry = KioskSessions('synthetic-a')
    grant = registry.issue(staff, 'lobby-one')
    ordinary = auth.issue_token('SYN-ADMIN', 'ADMIN')
    for operation in (registry.issue, registry.revoke):
        with pytest.raises(PermissionError, match='Fresh'):
            operation(ordinary, 'lobby-one')
    authenticated = auth.verify_token(staff)['authenticated_at']
    monkeypatch.setattr('core.kiosk_sessions.time.time', lambda: authenticated + 301)
    assert check(registry, grant['token']) is not None
    for operation in (registry.issue, registry.revoke):
        with pytest.raises(PermissionError, match='Fresh'):
            operation(staff, 'lobby-one')
    new_login = auth.issue_token('SYN-ADMIN', 'ADMIN', fresh_auth=True)
    registry.revoke(new_login, 'lobby-one')
    assert check(registry, grant['token']) is None


def test_password_and_completed_mfa_login_stamp_freshness(staff, monkeypatch):
    from core import auth_api
    result = auth_api.login('SYN-ADMIN', 'Fictional2026!')
    assert 'authenticated_at' in auth.verify_token(result['token'])
    monkeypatch.setattr(auth.credential_store, 'is_mfa_enabled', lambda employee: True)
    challenge = auth_api.login('SYN-ADMIN', 'Fictional2026!')
    assert challenge['mfa_required'] is True
    assert 'authenticated_at' not in auth.verify_token(challenge['mfa_challenge_token'])
    monkeypatch.setattr(auth.credential_store, 'verify_mfa_code', lambda employee, code: (code == 'fixture', 'totp'))
    assert 'error' in auth_api.verify_mfa_login(challenge['mfa_challenge_token'], 'wrong')
    result = auth_api.verify_mfa_login(challenge['mfa_challenge_token'], 'fixture')
    assert 'authenticated_at' in auth.verify_token(result['token'])


def test_capacity_and_malformed_input_fail_closed(staff):
    registry = KioskSessions('synthetic-a')
    registry.MAX_DEVICES = 1
    registry.issue(staff, 'lobby-one')
    with pytest.raises(RuntimeError):
        registry.issue(staff, 'lobby-two')
    assert registry.issue(staff, 'lobby-one')
    for value in (None, 1, {}, '', 'kiosk_é', 'x' * 10000):
        assert check(registry, value) is None
    for device in ('', ' ', None, 'x' * 129):
        with pytest.raises(ValueError):
            registry.issue(staff, device)


@pytest.mark.parametrize('operation', ['issue', 'revoke'])
def test_queued_management_rechecks_staff_before_mutating_grants(staff, operation):
    registry = KioskSessions('synthetic-a')
    registry.issue(staff, 'lobby-one')
    original = dict(registry._grants)
    inner = registry._lock
    waiting = threading.Event()
    owner = threading.get_ident()

    class ObservedLock:
        def __enter__(self):
            if threading.get_ident() != owner:
                waiting.set()
            return inner.__enter__()

        def __exit__(self, *args):
            return inner.__exit__(*args)

    registry._lock = ObservedLock()
    with ThreadPoolExecutor(max_workers=1) as pool:
        with registry._lock:
            work = pool.submit(getattr(registry, operation), staff, 'lobby-one')
            assert waiting.wait(2)
            auth.credential_store.set_role('SYN-ADMIN', 'SALES')
        with pytest.raises(PermissionError):
            work.result(timeout=2)
    # A stale manager cannot rotate, prune or remove any grant after waiting.
    assert registry._grants == original

def test_pending_password_change_blocks_management_until_password_changed(staff):
    from core import auth_api
    registry = KioskSessions('synthetic-a')
    auth.credential_store.set_credential('SYN-ADMIN', 'Temporary2026!', 'ADMIN')
    pending = auth_api.login('SYN-ADMIN', 'Temporary2026!')
    assert pending['must_change_password'] is True
    for operation in (registry.issue, registry.revoke):
        with pytest.raises(PermissionError, match='password'):
            operation(pending['token'], 'lobby-one')
    assert not registry._grants
    assert auth.credential_store.change_password('SYN-ADMIN', 'Temporary2026!', 'Permanent2026!')
    completed = auth_api.login('SYN-ADMIN', 'Permanent2026!')
    assert completed['must_change_password'] is False
    grant = registry.issue(completed['token'], 'lobby-one')
    assert check(registry, grant['token'])
    registry.revoke(completed['token'], 'lobby-one')
    assert check(registry, grant['token']) is None


def test_pending_password_flag_invalidates_existing_kiosk_authority(staff):
    registry = KioskSessions('synthetic-a')
    grant = registry.issue(staff, 'lobby-one')
    auth.credential_store.get_record('SYN-ADMIN')['must_change_password'] = True
    assert check(registry, grant['token']) is None
    assert not registry._grants
