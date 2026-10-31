"""
Tests for core/secrets.py + core/secrets_api.py (security-hardening pass,
2026-07-20, Task #13).

Uses a real, in-memory FakeBackend (implements the SecretsBackend Protocol) rather
than mutating os.environ directly -- exercising the module's own real swap point
(set_backend()) is both the more direct test of the abstraction itself and avoids any
risk of test-order-dependent os.environ pollution leaking into other test files that
import core.secrets transitively (e.g. core/auth.py, core/network_snapshot_api.py).
Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

import pytest

from core import secrets as secrets_module
from core.secrets import (
    get_secret,
    is_configured,
    is_using_dev_fallback,
    get_secrets_posture,
    warn_on_dev_fallbacks,
    set_backend,
    EnvVarBackend,
    KNOWN_SECRETS,
)
from core.secrets_api import get_secrets_posture_api


class FakeBackend:
    """A real, in-memory SecretsBackend implementation -- lets a test deterministically
    control exactly what each secret name "resolves to" without touching the real
    process environment at all."""

    def __init__(self, values=None):
        self.values = dict(values or {})

    def read(self, name):
        return self.values.get(name)


@pytest.fixture(autouse=True)
def restore_real_backend():
    """Every test starts and ends on the real EnvVarBackend -- set_backend() mutates
    module-level global state, so a test that swaps in a FakeBackend and doesn't clean
    up would silently break every other test file that imports core.secrets (directly,
    or transitively via core.auth/core.network_snapshot_api) later in the same pytest
    process."""

    set_backend(EnvVarBackend())
    yield
    set_backend(EnvVarBackend())


def test_known_secrets_catalog_has_exactly_the_three_real_backend_secrets():
    names = {spec.name for spec in KNOWN_SECRETS}

    assert names == {"DEALEROS_AUTH_SECRET", "DEALEROS_NETWORK_KEY", "OPENAI_API_KEY"}


def test_get_secret_falls_back_to_registered_dev_fallback_when_unset():
    set_backend(FakeBackend({}))

    assert get_secret("DEALEROS_AUTH_SECRET") == "dev-only-insecure-secret-change-me"
    assert get_secret("DEALEROS_NETWORK_KEY") == "dev-only-insecure-network-key-change-me"


def test_get_secret_returns_real_value_when_configured():
    set_backend(FakeBackend({"DEALEROS_AUTH_SECRET": "a-real-production-secret"}))

    assert get_secret("DEALEROS_AUTH_SECRET") == "a-real-production-secret"


def test_get_secret_treats_blank_string_as_unset():
    set_backend(FakeBackend({"DEALEROS_AUTH_SECRET": ""}))

    assert get_secret("DEALEROS_AUTH_SECRET") == "dev-only-insecure-secret-change-me"


def test_get_secret_with_no_registered_fallback_returns_none_when_unset():
    set_backend(FakeBackend({}))

    # OPENAI_API_KEY deliberately has no dev_fallback -- an unset key must resolve to
    # None, not a fabricated fake key.
    assert get_secret("OPENAI_API_KEY") is None


def test_get_secret_caller_supplied_fallback_overrides_registered_one():
    set_backend(FakeBackend({}))

    assert get_secret("DEALEROS_AUTH_SECRET", "caller-supplied-fallback") == "caller-supplied-fallback"


def test_get_secret_unknown_name_with_no_fallback_returns_none():
    set_backend(FakeBackend({}))

    assert get_secret("SOME_UNKNOWN_SECRET_NAME") is None


def test_get_secret_unknown_name_with_explicit_fallback_returns_it():
    set_backend(FakeBackend({}))

    assert get_secret("SOME_UNKNOWN_SECRET_NAME", "explicit-default") == "explicit-default"


def test_is_using_dev_fallback_true_when_unset():
    set_backend(FakeBackend({}))

    assert is_using_dev_fallback("DEALEROS_AUTH_SECRET") is True
    assert is_using_dev_fallback("DEALEROS_NETWORK_KEY") is True


def test_is_using_dev_fallback_false_when_configured():
    set_backend(FakeBackend({"DEALEROS_AUTH_SECRET": "a-real-value"}))

    assert is_using_dev_fallback("DEALEROS_AUTH_SECRET") is False


def test_is_using_dev_fallback_always_false_for_secret_with_no_fallback():
    set_backend(FakeBackend({}))

    # OPENAI_API_KEY has no dev_fallback -- can never be "on its fallback" by definition.
    assert is_using_dev_fallback("OPENAI_API_KEY") is False


def test_is_using_dev_fallback_false_for_unknown_secret():
    set_backend(FakeBackend({}))

    assert is_using_dev_fallback("SOME_UNKNOWN_SECRET_NAME") is False


def test_is_configured_does_not_apply_fallback_substitution():
    set_backend(FakeBackend({}))

    # is_configured() must report the RAW backend state -- unlike get_secret(), it
    # must not be fooled into "true" just because a dev fallback exists.
    assert is_configured("DEALEROS_AUTH_SECRET") is False


def test_is_configured_true_when_real_value_present():
    set_backend(FakeBackend({"DEALEROS_AUTH_SECRET": "a-real-value"}))

    assert is_configured("DEALEROS_AUTH_SECRET") is True


def test_is_configured_treats_blank_string_as_unset():
    set_backend(FakeBackend({"DEALEROS_AUTH_SECRET": ""}))

    assert is_configured("DEALEROS_AUTH_SECRET") is False


def test_is_configured_works_for_names_outside_known_secrets_catalog():
    set_backend(FakeBackend({"SOME_UNKNOWN_SECRET_NAME": "x"}))

    assert is_configured("SOME_UNKNOWN_SECRET_NAME") is True
    assert is_configured("SOME_OTHER_UNKNOWN_NAME") is False


def test_get_secrets_posture_all_on_fallback():
    set_backend(FakeBackend({}))

    posture = get_secrets_posture()

    assert posture["any_dev_fallback_in_use"] is True
    assert "insecure" in posture["posture"]

    by_name = {entry["name"]: entry for entry in posture["secrets"]}

    assert by_name["DEALEROS_AUTH_SECRET"]["configured"] is False
    assert by_name["DEALEROS_AUTH_SECRET"]["using_dev_fallback"] is True
    assert by_name["DEALEROS_AUTH_SECRET"]["has_dev_fallback_available"] is True

    assert by_name["DEALEROS_NETWORK_KEY"]["configured"] is False
    assert by_name["DEALEROS_NETWORK_KEY"]["using_dev_fallback"] is True

    # OPENAI_API_KEY has no fallback at all -- unset there must never count toward
    # any_dev_fallback_in_use.
    assert by_name["OPENAI_API_KEY"]["configured"] is False
    assert by_name["OPENAI_API_KEY"]["using_dev_fallback"] is False
    assert by_name["OPENAI_API_KEY"]["has_dev_fallback_available"] is False


def test_get_secrets_posture_all_configured():
    set_backend(FakeBackend({
        "DEALEROS_AUTH_SECRET": "real-1",
        "DEALEROS_NETWORK_KEY": "real-2",
        "OPENAI_API_KEY": "sk-real-3",
    }))

    posture = get_secrets_posture()

    assert posture["any_dev_fallback_in_use"] is False
    assert "Every known secret" in posture["posture"]

    for entry in posture["secrets"]:
        assert entry["configured"] is True
        assert entry["using_dev_fallback"] is False


def test_get_secrets_posture_never_leaks_the_actual_secret_value():
    set_backend(FakeBackend({
        "DEALEROS_AUTH_SECRET": "super-secret-value-must-not-leak",
    }))

    posture = get_secrets_posture()

    assert "super-secret-value-must-not-leak" not in str(posture)


def test_get_secrets_posture_partial_configuration():
    set_backend(FakeBackend({"DEALEROS_AUTH_SECRET": "real-value"}))

    posture = get_secrets_posture()
    by_name = {entry["name"]: entry for entry in posture["secrets"]}

    assert by_name["DEALEROS_AUTH_SECRET"]["using_dev_fallback"] is False
    assert by_name["DEALEROS_NETWORK_KEY"]["using_dev_fallback"] is True
    assert posture["any_dev_fallback_in_use"] is True


def test_warn_on_dev_fallbacks_prints_and_returns_names_when_unset():
    import io

    set_backend(FakeBackend({}))
    buf = io.StringIO()

    names = warn_on_dev_fallbacks(stream=buf)

    assert set(names) == {"DEALEROS_AUTH_SECRET", "DEALEROS_NETWORK_KEY"}

    output = buf.getvalue()
    assert "DEALEROS_AUTH_SECRET" in output
    assert "DEALEROS_NETWORK_KEY" in output
    assert "SECURITY WARNING" in output
    # OPENAI_API_KEY has no fallback -- must never appear in this warning, being unset
    # is its normal, honest, already-handled state, not a security misconfiguration.
    assert "OPENAI_API_KEY" not in output


def test_warn_on_dev_fallbacks_prints_nothing_when_fully_configured():
    import io

    set_backend(FakeBackend({
        "DEALEROS_AUTH_SECRET": "real-1",
        "DEALEROS_NETWORK_KEY": "real-2",
    }))
    buf = io.StringIO()

    names = warn_on_dev_fallbacks(stream=buf)

    assert names == []
    assert buf.getvalue() == ""


def test_warn_on_dev_fallbacks_defaults_to_stderr():
    set_backend(FakeBackend({
        "DEALEROS_AUTH_SECRET": "real-1",
        "DEALEROS_NETWORK_KEY": "real-2",
    }))

    # Doesn't raise, doesn't require a stream argument -- confirms the real
    # api/app.py / hub/app.py lifespan() call sites (which call this with zero
    # arguments) work correctly.
    names = warn_on_dev_fallbacks()

    assert names == []


def test_set_backend_actually_swaps_behavior():
    set_backend(FakeBackend({"DEALEROS_AUTH_SECRET": "fake-backend-value"}))
    assert get_secret("DEALEROS_AUTH_SECRET") == "fake-backend-value"

    set_backend(EnvVarBackend())
    # The real EnvVarBackend reads the real os.environ -- this sandbox process has no
    # DEALEROS_AUTH_SECRET set for real, so this must fall back, not still return the
    # fake backend's value (proving the swap genuinely took effect, not just cached).
    assert get_secret("DEALEROS_AUTH_SECRET") != "fake-backend-value"


def test_env_var_backend_reads_real_os_environ(monkeypatch):
    monkeypatch.setenv("DEALEROS_AUTH_SECRET", "a-real-env-value")
    set_backend(EnvVarBackend())

    assert get_secret("DEALEROS_AUTH_SECRET") == "a-real-env-value"


class TestSecretsPostureApi:
    """core/secrets_api.py's ACL layer -- ADMIN/OPERATIONS only, matching every other
    security self-check surface in this codebase (crypto_agility_api.py, etc.)."""

    def test_admin_can_view(self):
        set_backend(FakeBackend({}))

        result = get_secrets_posture_api("ADMIN")

        assert "error" not in result
        assert "secrets" in result

    def test_operations_can_view(self):
        set_backend(FakeBackend({}))

        result = get_secrets_posture_api("OPERATIONS")

        assert "error" not in result
        assert "secrets" in result

    def test_sales_denied(self):
        result = get_secrets_posture_api("SALES")

        assert "error" in result
        assert result["error"]

    def test_marketing_denied(self):
        result = get_secrets_posture_api("MARKETING")

        assert "error" in result

    def test_unknown_role_denied(self):
        result = get_secrets_posture_api("NOT_A_REAL_ROLE")

        assert "error" in result

@pytest.mark.parametrize("spec", [spec for spec in KNOWN_SECRETS if spec.dev_fallback is not None])
def test_explicit_development_value_is_still_reported_as_insecure(spec):
    set_backend(FakeBackend({spec.name: spec.dev_fallback}))
    assert is_using_dev_fallback(spec.name) is True
    posture = get_secrets_posture()
    assert posture["any_dev_fallback_in_use"] is True
    # Presence and safety are distinct: explicitly setting a public default
    # must not clear the insecure-fallback warning or reveal the value.
    assert spec.dev_fallback not in str(posture)
