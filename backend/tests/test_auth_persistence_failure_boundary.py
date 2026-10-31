"""Authentication cannot issue a session when its credential save fails."""
import json

import pytest

from core import auth, auth_api, auth_storage, mfa


@pytest.mark.parametrize("method", ["password", "totp", "recovery"])
@pytest.mark.parametrize("failure_stage", ["replace", "directory_sync"])
def test_no_session_on_credential_commit_failure(monkeypatch, tmp_path, method, failure_stage):
    monkeypatch.delenv("DEALEROS_DEMO", raising=False)
    store = auth.CredentialStore()
    employee = "SYNTHETIC-FAILURE-TEST"
    password = "SyntheticPassword!42"
    store.set_credential(employee, password, "ADMIN", must_change_password=False)
    for module in (auth, auth_api, auth_storage):
        monkeypatch.setattr(module, "credential_store", store)
    monkeypatch.setattr(auth_api, "save_audit_log", lambda *args: None)
    target = tmp_path / "credentials.json"
    monkeypatch.setattr(auth_api, "CREDENTIALS_PATH", target)
    if method != "password":
        secret = store.begin_mfa_enrollment(employee)["secret"]
        enrollment = store.confirm_mfa_enrollment(employee, mfa.totp_now(secret))
        code = enrollment["recovery_codes"][0] if method == "recovery" else mfa.totp_now(secret)
        challenge = auth.issue_mfa_challenge_token(employee, "ADMIN")
    store.record_failed_login(employee)
    auth_storage.save_credentials(target)
    before = json.loads(target.read_text(encoding="utf-8"))

    def fail(*args):
        raise OSError("synthetic credential commit failure")

    if failure_stage == "replace":
        monkeypatch.setattr(auth_storage.os, "replace", fail)
    else:
        monkeypatch.setattr(auth_storage, "_sync_parent_directory", fail)

    issued = []
    monkeypatch.setattr(auth_api, "issue_token", lambda *args, **kwargs: issued.append(args))
    with pytest.raises(OSError, match="synthetic credential commit failure"):
        if method == "password":
            auth_api.login(employee, password)
        else:
            auth_api.verify_mfa_login(challenge, code)
    assert issued == []
    persisted = json.loads(target.read_text(encoding="utf-8"))
    if failure_stage == "replace":
        assert persisted == before
    else:
        # Replacement succeeded, durability acknowledgement failed: never claim rollback.
        assert persisted == store.credentials
        assert persisted[employee]["failed_attempts"] == 0
    assert list(tmp_path.iterdir()) == [target]
