"""An existing session must not replace an active authenticator via enrollment."""
from copy import deepcopy

import pytest

from core import auth, auth_api, mfa


@pytest.fixture
def store(monkeypatch):
    store = auth.CredentialStore()
    store.set_credential("EMP-SYNTHETIC", "SyntheticPassword!42", "ADMIN")
    monkeypatch.setattr(auth, "credential_store", store)
    monkeypatch.setattr(auth_api, "credential_store", store)
    monkeypatch.setattr(auth_api, "save_credentials", lambda *a: None)
    monkeypatch.setattr(auth_api, "save_audit_log", lambda *a: None)
    return store


def enroll(store):
    secret = store.begin_mfa_enrollment("EMP-SYNTHETIC")["secret"]
    result = store.confirm_mfa_enrollment("EMP-SYNTHETIC", mfa.totp_now(secret))
    assert result["success"] is True
    return secret, result["recovery_codes"]


def test_session_cannot_restart_active_enrollment(store):
    secret, codes = enroll(store)
    token = auth.issue_token("EMP-SYNTHETIC", "ADMIN")
    before = deepcopy(store.get_record("EMP-SYNTHETIC"))
    assert "error" in auth_api.begin_mfa_enrollment(token)
    assert store.get_record("EMP-SYNTHETIC") == before
    assert store.verify_mfa_code("EMP-SYNTHETIC", mfa.totp_now(secret)) == (True, "totp")
    assert store.verify_mfa_code("EMP-SYNTHETIC", codes[0]) == (True, "recovery")


def test_legacy_pending_secret_cannot_replace_active_factor(store):
    enroll(store)
    replacement = mfa.generate_totp_secret()
    store.get_record("EMP-SYNTHETIC")["mfa_pending_secret"] = replacement
    before = deepcopy(store.get_record("EMP-SYNTHETIC"))
    token = auth.issue_token("EMP-SYNTHETIC", "ADMIN")
    assert "error" in auth_api.confirm_mfa_enrollment(token, mfa.totp_now(replacement))
    assert store.get_record("EMP-SYNTHETIC") == before


def test_initial_enrollment_can_restart_and_recovery_stays_single_use(store):
    first = store.begin_mfa_enrollment("EMP-SYNTHETIC")["secret"]
    second, codes = enroll(store)
    assert first != second
    assert store.get_record("EMP-SYNTHETIC")["mfa_pending_secret"] is None
    assert store.verify_mfa_code("EMP-SYNTHETIC", codes[0]) == (True, "recovery")
    assert store.verify_mfa_code("EMP-SYNTHETIC", codes[0]) == (False, None)


def test_reenrollment_requires_explicit_disable_first(store):
    enroll(store)
    assert store.disable_mfa("EMP-SYNTHETIC") is True
    enroll(store)


def test_enrollment_revokes_previous_sessions_and_challenges(store):
    token = auth.issue_token("EMP-SYNTHETIC", "ADMIN")
    challenge = auth.issue_mfa_challenge_token("EMP-SYNTHETIC", "ADMIN")
    enroll(store)
    assert auth.verify_token(token) is None
    assert auth.verify_token(challenge) is None
    assert auth.verify_token(auth.issue_token("EMP-SYNTHETIC", "ADMIN")) is not None


def test_disable_and_reenrollment_cannot_revive_old_sessions(store):
    enroll(store)
    token = auth.issue_token("EMP-SYNTHETIC", "ADMIN")
    challenge = auth.issue_mfa_challenge_token("EMP-SYNTHETIC", "ADMIN")
    assert store.disable_mfa("EMP-SYNTHETIC")
    assert auth.verify_token(token) is None
    assert auth.verify_token(challenge) is None
    enroll(store)
    assert auth.verify_token(token) is None


def test_recovery_use_does_not_revoke_valid_sessions(store):
    _, codes = enroll(store)
    token = auth.issue_token("EMP-SYNTHETIC", "ADMIN")
    assert store.verify_mfa_code("EMP-SYNTHETIC", codes[0]) == (True, "recovery")
    assert auth.verify_token(token) is not None


def test_legacy_binding_survives_until_mfa_changes(store):
    record = store.get_record("EMP-SYNTHETIC")
    record.pop("mfa_version", None)
    token = auth.issue_token("EMP-SYNTHETIC", "ADMIN")
    record["mfa_version"] = 0
    assert auth.verify_token(token) is not None
    store.begin_mfa_enrollment("EMP-SYNTHETIC")
    assert auth.verify_token(token) is not None


def recovery_target(store):
    store.set_credential("EMP-TARGET", "SyntheticTarget!42", "SALES", must_change_password=False)
    secret = store.begin_mfa_enrollment("EMP-TARGET")["secret"]
    assert store.confirm_mfa_enrollment("EMP-TARGET", mfa.totp_now(secret))["success"]
    return auth.issue_token("EMP-TARGET", "SALES")


@pytest.mark.parametrize("mode", ["password_only", "old", "future", "temporary_password", "not_enrolled"])
def test_admin_recovery_rejects_insufficient_signin_without_mutation(store, monkeypatch, mode):
    import time
    enroll(store)
    actor = store.get_record("EMP-SYNTHETIC")
    actor["must_change_password"] = mode == "temporary_password"
    if mode == "not_enrolled":
        store.disable_mfa("EMP-SYNTHETIC")
    target_token = recovery_target(store)
    before = deepcopy(store.get_record("EMP-TARGET"))
    real_now = time.time()
    with monkeypatch.context() as clock:
        offset = -301 if mode == "old" else 30 if mode == "future" else 0
        clock.setattr(auth.time, "time", lambda: real_now + offset)
        token = auth.issue_token("EMP-SYNTHETIC", "ADMIN", fresh_auth=True,
                                 mfa_authenticated=mode != "password_only")
    result = auth_api.admin_disable_mfa(token, "EMP-TARGET")
    assert result["code"] == "fresh_admin_mfa_required"
    assert store.get_record("EMP-TARGET") == before
    assert auth.verify_token(target_token) is not None


def test_actual_mfa_login_allows_admin_recovery_and_revokes_target(store):
    secret, _ = enroll(store)
    store.get_record("EMP-SYNTHETIC")["must_change_password"] = False
    target_token = recovery_target(store)
    challenge = auth_api.login("EMP-SYNTHETIC", "SyntheticPassword!42")["mfa_challenge_token"]
    login = auth_api.verify_mfa_login(challenge, mfa.totp_now(secret))
    assert auth.verify_token(login["token"])["mfa_authenticated"] is True
    result = auth_api.admin_disable_mfa(login["token"], "EMP-TARGET")
    assert result["mfa_enabled"] is False
    assert auth.verify_token(target_token) is None
    assert auth.verify_token(login["token"]) is not None


def test_password_login_does_not_claim_second_factor(store):
    result = auth_api.login("EMP-SYNTHETIC", "SyntheticPassword!42")
    assert auth.verify_token(result["token"]).get("mfa_authenticated") is not True


def test_mfa_revocation_and_recovery_consumption_survive_restart(store, monkeypatch, tmp_path):
    from core import auth_storage
    monkeypatch.delenv("DEALEROS_DEMO", raising=False)
    monkeypatch.setattr(auth_storage, "credential_store", store)
    stale = auth.issue_token("EMP-SYNTHETIC", "ADMIN")
    secret, codes = enroll(store)
    current = auth.issue_token("EMP-SYNTHETIC", "ADMIN")
    assert store.verify_mfa_code("EMP-SYNTHETIC", codes[0]) == (True, "recovery")
    path = str(tmp_path / "credentials.json")
    auth_storage.save_credentials(path)
    store.reset()
    auth_storage.load_credentials(path)
    assert auth.verify_token(stale) is None
    assert auth.verify_token(current) is not None
    assert store.verify_mfa_code("EMP-SYNTHETIC", codes[0]) == (False, None)
    assert store.verify_mfa_code("EMP-SYNTHETIC", mfa.totp_now(secret)) == (True, "totp")


def test_pending_setup_limits_survive_password_reset_and_restart(store, monkeypatch, tmp_path):
    from core import auth_storage
    monkeypatch.delenv("DEALEROS_DEMO", raising=False)
    monkeypatch.setattr(auth_storage, "credential_store", store)
    store.begin_mfa_enrollment("EMP-SYNTHETIC")
    with monkeypatch.context() as verification:
        verification.setattr(auth, "verify_totp_code", lambda *a: False)
        assert "error" in store.confirm_mfa_enrollment("EMP-SYNTHETIC", "wrong")
    before = deepcopy(store.get_record("EMP-SYNTHETIC"))
    store.set_credential("EMP-SYNTHETIC", "ReplacementPassword!42", "ADMIN")
    path = str(tmp_path / "credentials.json")
    auth_storage.save_credentials(path)
    store.reset()
    auth_storage.load_credentials(path)
    after = store.get_record("EMP-SYNTHETIC")
    for key in ("mfa_pending_secret", "mfa_pending_started_at", "mfa_pending_attempts", "mfa_version"):
        assert after[key] == before[key]
    assert after["mfa_pending_attempts"] == 1


def test_failed_credential_replace_preserves_previous_complete_file(store, monkeypatch, tmp_path):
    from core import auth_storage
    monkeypatch.delenv("DEALEROS_DEMO", raising=False)
    monkeypatch.setattr(auth_storage, "credential_store", store)
    path = tmp_path / "credentials.json"
    auth_storage.save_credentials(str(path))
    prior = path.read_bytes()
    enroll(store)
    def fail_replace(*args):
        raise OSError("Synthetic replace failure")
    monkeypatch.setattr(auth_storage.os, "replace", fail_replace)
    with pytest.raises(OSError, match="Synthetic replace failure"):
        auth_storage.save_credentials(str(path))
    assert path.read_bytes() == prior


@pytest.mark.parametrize("started", [None, 0, float("nan"), float("inf"), True, "invalid"])
def test_legacy_or_invalid_pending_setup_cannot_activate(store, started):
    secret = store.begin_mfa_enrollment("EMP-SYNTHETIC")["secret"]
    record = store.get_record("EMP-SYNTHETIC")
    record["mfa_pending_started_at"] = started
    assert "error" in store.confirm_mfa_enrollment("EMP-SYNTHETIC", mfa.totp_now(secret))
    assert record["mfa_pending_secret"] is None
    assert not record["mfa_enabled"]


def test_setup_expires_at_ten_minutes_without_revoking_session(store, monkeypatch):
    token = auth.issue_token("EMP-SYNTHETIC", "ADMIN")
    store.begin_mfa_enrollment("EMP-SYNTHETIC")
    record = store.get_record("EMP-SYNTHETIC")
    started = record["mfa_pending_started_at"]
    monkeypatch.setattr(auth.time, "time", lambda: started + 600)
    assert "error" in store.confirm_mfa_enrollment("EMP-SYNTHETIC", "123456")
    assert auth.verify_token(token) is not None
    assert record["mfa_pending_secret"] is None


def test_failed_enrollment_attempts_persist_and_exhaust_setup(store, monkeypatch):
    token = auth.issue_token("EMP-SYNTHETIC", "ADMIN")
    store.begin_mfa_enrollment("EMP-SYNTHETIC")
    monkeypatch.setattr(auth, "verify_totp_code", lambda *a: False)
    saved = []
    monkeypatch.setattr(auth_api, "save_credentials", lambda *a: saved.append(deepcopy(store.get_record("EMP-SYNTHETIC"))))
    for attempt in range(1, 6):
        assert "error" in auth_api.confirm_mfa_enrollment(token, "wrong")
        assert saved[-1]["mfa_pending_attempts"] == attempt
    assert saved[-1]["mfa_pending_secret"] is None
    assert not store.is_mfa_enabled("EMP-SYNTHETIC")
    assert store.begin_mfa_enrollment("EMP-SYNTHETIC")["expires_in_seconds"] == 600
    assert store.get_record("EMP-SYNTHETIC")["mfa_pending_attempts"] == 0


@pytest.mark.parametrize("fresh,mfa_proof", [(False, False), (True, False), (False, True)])
def test_self_disable_needs_recent_second_factor_even_with_password(store, fresh, mfa_proof):
    enroll(store)
    store.get_record("EMP-SYNTHETIC")["must_change_password"] = False
    token = auth.issue_token("EMP-SYNTHETIC", "ADMIN", fresh_auth=fresh, mfa_authenticated=mfa_proof)
    before = deepcopy(store.get_record("EMP-SYNTHETIC"))
    assert auth_api.disable_mfa(token, "SyntheticPassword!42")["code"] == "fresh_mfa_required"
    assert store.get_record("EMP-SYNTHETIC") == before


@pytest.mark.parametrize("use_recovery", [False, True])
def test_self_disable_with_completed_mfa_login_requires_password_and_revokes_session(store, use_recovery):
    secret, codes = enroll(store)
    store.get_record("EMP-SYNTHETIC")["must_change_password"] = False
    challenge = auth_api.login("EMP-SYNTHETIC", "SyntheticPassword!42")["mfa_challenge_token"]
    code = codes[0] if use_recovery else mfa.totp_now(secret)
    token = auth_api.verify_mfa_login(challenge, code)["token"]
    before = deepcopy(store.get_record("EMP-SYNTHETIC"))
    assert "error" in auth_api.disable_mfa(token, "wrong-password")
    assert store.get_record("EMP-SYNTHETIC") == before
    result = auth_api.disable_mfa(token, "SyntheticPassword!42")
    assert result["success"] and result["reauthentication_required"]
    assert auth.verify_token(token) is None
    assert store.is_mfa_enabled("EMP-SYNTHETIC") is False


def test_password_reentry_cannot_reset_failed_second_factor_attempts(store):
    enroll(store)
    for attempt in range(1, auth.MAX_FAILED_ATTEMPTS + 1):
        challenge = auth_api.login('EMP-SYNTHETIC', 'SyntheticPassword!42')['mfa_challenge_token']
        assert 'error' in auth_api.verify_mfa_login(challenge, 'not-a-code')
        assert store.get_record('EMP-SYNTHETIC')['failed_attempts'] == attempt
    assert store.is_locked('EMP-SYNTHETIC')
    assert 'mfa_challenge_token' not in auth_api.login('EMP-SYNTHETIC', 'SyntheticPassword!42')


@pytest.mark.parametrize('use_recovery', [False, True])
def test_completed_mfa_login_clears_failures_and_persists_before_token(store, monkeypatch, use_recovery):
    secret, codes = enroll(store)
    store.record_failed_login('EMP-SYNTHETIC')
    saved = []
    monkeypatch.setattr(auth_api, 'save_credentials', lambda *a: saved.append(deepcopy(store.get_record('EMP-SYNTHETIC'))))
    challenge = auth_api.login('EMP-SYNTHETIC', 'SyntheticPassword!42')['mfa_challenge_token']
    assert store.get_record('EMP-SYNTHETIC')['failed_attempts'] == 1
    response = auth_api.verify_mfa_login(challenge, codes[0] if use_recovery else mfa.totp_now(secret))
    assert response['token']
    assert saved[-1]['failed_attempts'] == 0
    assert saved[-1]['locked_until'] is None


def test_failed_mfa_persistence_never_returns_session(store, monkeypatch):
    secret, _ = enroll(store)
    challenge = auth_api.login('EMP-SYNTHETIC', 'SyntheticPassword!42')['mfa_challenge_token']
    def fail_save(*args):
        raise OSError('synthetic persistence failure')
    monkeypatch.setattr(auth_api, 'save_credentials', fail_save)
    with pytest.raises(OSError, match='synthetic persistence failure'):
        auth_api.verify_mfa_login(challenge, mfa.totp_now(secret))


@pytest.mark.parametrize('operation', ['begin', 'confirm', 'disable', 'admin_disable'])
def test_mfa_changes_never_report_success_when_credential_save_fails(store, monkeypatch, operation):
    secret = None
    if operation in ('disable', 'admin_disable'):
        secret, _ = enroll(store)
        store.get_record('EMP-SYNTHETIC')['must_change_password'] = False
        token = auth.issue_token('EMP-SYNTHETIC', 'ADMIN', fresh_auth=True, mfa_authenticated=True)
    else:
        token = auth.issue_token('EMP-SYNTHETIC', 'ADMIN')
        if operation == 'confirm':
            secret = store.begin_mfa_enrollment('EMP-SYNTHETIC')['secret']
    def fail_save(*args):
        raise OSError('synthetic credential storage failure')
    monkeypatch.setattr(auth_api, 'save_credentials', fail_save)
    with pytest.raises(OSError, match='synthetic credential storage failure'):
        if operation == 'begin':
            auth_api.begin_mfa_enrollment(token)
        elif operation == 'confirm':
            auth_api.confirm_mfa_enrollment(token, mfa.totp_now(secret))
        elif operation == 'disable':
            auth_api.disable_mfa(token, 'SyntheticPassword!42')
        else:
            auth_api.admin_disable_mfa(token, 'EMP-SYNTHETIC')


def test_recovery_code_cannot_issue_second_session_from_another_challenge(store):
    _, codes = enroll(store)
    first = auth_api.login('EMP-SYNTHETIC', 'SyntheticPassword!42')['mfa_challenge_token']
    second = auth_api.login('EMP-SYNTHETIC', 'SyntheticPassword!42')['mfa_challenge_token']
    assert auth_api.verify_mfa_login(first, codes[0])['token']
    assert 'token' not in auth_api.verify_mfa_login(second, codes[0])
