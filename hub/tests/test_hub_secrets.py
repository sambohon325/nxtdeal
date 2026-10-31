"""
Tests for the NXTDeal Hub's secrets management abstraction
(hub_core/secrets.py) -- security-hardening pass Task #13.

Mirrors backend/tests/test_secrets.py's coverage (same real design, two
near-identical standalone modules -- see hub_core/secrets.py's own module
docstring for why hub/ and backend/ each need their own copy rather than a
shared import). Uses a real, in-memory FakeBackend (implements the
SecretsBackend Protocol) rather than mutating os.environ directly.

Also covers hub_core/infra_security.py's get_hub_security_posture() --
the one real Hub call site that specifically needs is_configured()'s
"raw backend state, no fallback substitution" behavior rather than
get_secret()'s -- exercised here with the same FakeBackend swap, confirming
the two functions actually compose correctly end to end, not just in
isolation.

Run from hub/ with `pytest` (or `pytest tests/test_hub_secrets.py`), same as
every other Hub test file.
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_HUB_DIR = os.path.dirname(_HERE)

if _HUB_DIR not in sys.path:
    sys.path.insert(0, _HUB_DIR)

import pytest

from hub_core.secrets import (
    get_secret,
    is_configured,
    is_using_dev_fallback,
    get_secrets_posture,
    warn_on_dev_fallbacks,
    set_backend,
    EnvVarBackend,
    KNOWN_SECRETS,
)
from hub_core.infra_security import get_hub_security_posture


class FakeBackend:
    """A real, in-memory SecretsBackend implementation -- lets a test
    deterministically control exactly what each secret name "resolves to"
    without touching the real process environment at all."""

    def __init__(self, values=None):
        self.values = dict(values or {})

    def read(self, name):
        return self.values.get(name)


@pytest.fixture(autouse=True)
def restore_real_backend():
    """Every test starts and ends on the real EnvVarBackend -- set_backend()
    mutates module-level global state, so a test that swaps in a FakeBackend
    and doesn't clean up would silently break every other test file that
    imports hub_core.secrets (directly, or transitively via hub_core/auth.py
    and every hub_core module that reads DEALEROS_NETWORK_KEY) later in the
    same pytest process."""

    set_backend(EnvVarBackend())
    yield
    set_backend(EnvVarBackend())


def test_known_secrets_catalog_has_exactly_the_three_real_hub_secrets():
    names = {spec.name for spec in KNOWN_SECRETS}

    # The Hub has no OPENAI_API_KEY of its own -- every AI call in this
    # codebase happens tenant-side. DEALEROS_AUTH_SECRET IS in the Hub's own
    # catalog (unlike NXTDEAL_HUB_KEY/DEALEROS_NETWORK_KEY-only, which was
    # this test's first, wrong assumption) -- hub_core/auth.py reads it
    # during dealer provisioning, when hashing a freshly-created dealer's
    # first ADMIN credential, and it must match the real backend's own
    # value exactly. Confirmed by reading hub_core/secrets.py's own
    # KNOWN_SECRETS definition directly, not assumed.
    assert names == {"NXTDEAL_HUB_KEY", "DEALEROS_NETWORK_KEY", "DEALEROS_AUTH_SECRET"}


def test_get_secret_falls_back_to_registered_dev_fallback_when_unset():
    set_backend(FakeBackend({}))

    hub_key = get_secret("NXTDEAL_HUB_KEY")
    network_key = get_secret("DEALEROS_NETWORK_KEY")

    assert hub_key is not None and "dev" in hub_key
    assert network_key is not None and "dev" in network_key


def test_get_secret_returns_real_value_when_configured():
    set_backend(FakeBackend({"NXTDEAL_HUB_KEY": "a-real-production-key"}))

    assert get_secret("NXTDEAL_HUB_KEY") == "a-real-production-key"


def test_get_secret_treats_blank_string_as_unset():
    set_backend(FakeBackend({"NXTDEAL_HUB_KEY": ""}))

    fallback = get_secret("NXTDEAL_HUB_KEY")

    assert fallback is not None and "dev" in fallback


def test_get_secret_unknown_name_with_no_fallback_returns_none():
    set_backend(FakeBackend({}))

    assert get_secret("SOME_UNKNOWN_SECRET_NAME") is None


def test_is_using_dev_fallback_true_when_unset():
    set_backend(FakeBackend({}))

    assert is_using_dev_fallback("NXTDEAL_HUB_KEY") is True
    assert is_using_dev_fallback("DEALEROS_NETWORK_KEY") is True


def test_is_using_dev_fallback_false_when_configured():
    set_backend(FakeBackend({"DEALEROS_NETWORK_KEY": "a-real-value"}))

    assert is_using_dev_fallback("DEALEROS_NETWORK_KEY") is False


def test_is_configured_does_not_apply_fallback_substitution():
    set_backend(FakeBackend({}))

    # is_configured() must report the RAW backend state -- unlike
    # get_secret(), it must not be fooled into "true" just because a dev
    # fallback exists. This is the exact behavior hub_core/infra_security.py's
    # get_hub_security_posture() depends on to report an honest result.
    assert is_configured("NXTDEAL_HUB_KEY") is False
    assert is_configured("DEALEROS_NETWORK_KEY") is False


def test_is_configured_true_when_real_value_present():
    set_backend(FakeBackend({
        "NXTDEAL_HUB_KEY": "real-hub-key",
        "DEALEROS_NETWORK_KEY": "real-network-key",
    }))

    assert is_configured("NXTDEAL_HUB_KEY") is True
    assert is_configured("DEALEROS_NETWORK_KEY") is True


def test_get_secrets_posture_all_on_fallback():
    set_backend(FakeBackend({}))

    posture = get_secrets_posture()

    assert posture["any_dev_fallback_in_use"] is True

    by_name = {entry["name"]: entry for entry in posture["secrets"]}
    assert by_name["NXTDEAL_HUB_KEY"]["configured"] is False
    assert by_name["NXTDEAL_HUB_KEY"]["using_dev_fallback"] is True
    assert by_name["DEALEROS_NETWORK_KEY"]["configured"] is False
    assert by_name["DEALEROS_NETWORK_KEY"]["using_dev_fallback"] is True


def test_get_secrets_posture_all_configured():
    set_backend(FakeBackend({
        "NXTDEAL_HUB_KEY": "real-1",
        "DEALEROS_NETWORK_KEY": "real-2",
        "DEALEROS_AUTH_SECRET": "real-3",
    }))

    posture = get_secrets_posture()

    assert posture["any_dev_fallback_in_use"] is False
    for entry in posture["secrets"]:
        assert entry["configured"] is True
        assert entry["using_dev_fallback"] is False


def test_get_secrets_posture_never_leaks_the_actual_secret_value():
    set_backend(FakeBackend({
        "NXTDEAL_HUB_KEY": "super-secret-value-must-not-leak",
    }))

    posture = get_secrets_posture()

    assert "super-secret-value-must-not-leak" not in str(posture)


def test_warn_on_dev_fallbacks_prints_and_returns_names_when_unset():
    import io

    set_backend(FakeBackend({}))
    buf = io.StringIO()

    names = warn_on_dev_fallbacks(stream=buf)

    assert set(names) == {"NXTDEAL_HUB_KEY", "DEALEROS_NETWORK_KEY", "DEALEROS_AUTH_SECRET"}
    output = buf.getvalue()
    assert "NXTDEAL_HUB_KEY" in output
    assert "DEALEROS_NETWORK_KEY" in output
    assert "DEALEROS_AUTH_SECRET" in output


def test_warn_on_dev_fallbacks_prints_nothing_when_fully_configured():
    import io

    set_backend(FakeBackend({
        "NXTDEAL_HUB_KEY": "real-1",
        "DEALEROS_NETWORK_KEY": "real-2",
        "DEALEROS_AUTH_SECRET": "real-3",
    }))
    buf = io.StringIO()

    names = warn_on_dev_fallbacks(stream=buf)

    assert names == []
    assert buf.getvalue() == ""


def test_set_backend_actually_swaps_behavior():
    set_backend(FakeBackend({"NXTDEAL_HUB_KEY": "fake-backend-value"}))
    assert get_secret("NXTDEAL_HUB_KEY") == "fake-backend-value"

    set_backend(EnvVarBackend())
    assert get_secret("NXTDEAL_HUB_KEY") != "fake-backend-value"


class TestGetHubSecurityPostureViaSecretsChokepoint:
    """hub_core/infra_security.py's get_hub_security_posture() is the one
    real Hub call site built specifically around is_configured()'s "no
    fallback substitution" behavior -- these tests exercise that real
    composition end to end via the FakeBackend swap, not just the
    lower-level secrets.py functions in isolation."""

    def test_reports_neither_configured_when_both_unset(self):
        set_backend(FakeBackend({}))

        posture = get_hub_security_posture()

        assert posture["hub_shared_key_configured_from_env"] is False
        assert posture["network_shared_key_configured_from_env"] is False
        assert "NEITHER" in posture["summary"]

    def test_reports_both_configured_when_both_set(self):
        set_backend(FakeBackend({
            "NXTDEAL_HUB_KEY": "real-hub-key",
            "DEALEROS_NETWORK_KEY": "real-network-key",
        }))

        posture = get_hub_security_posture()

        assert posture["hub_shared_key_configured_from_env"] is True
        assert posture["network_shared_key_configured_from_env"] is True
        assert "Both" in posture["summary"]

    def test_reports_partial_configuration_and_names_the_missing_one(self):
        set_backend(FakeBackend({"NXTDEAL_HUB_KEY": "real-hub-key"}))

        posture = get_hub_security_posture()

        assert posture["hub_shared_key_configured_from_env"] is True
        assert posture["network_shared_key_configured_from_env"] is False
        assert "DEALEROS_NETWORK_KEY" in posture["summary"]

    def test_never_leaks_the_actual_secret_value(self):
        set_backend(FakeBackend({
            "NXTDEAL_HUB_KEY": "super-secret-hub-key-must-not-leak",
        }))

        posture = get_hub_security_posture()

        assert "super-secret-hub-key-must-not-leak" not in str(posture)

@pytest.mark.parametrize("spec", [spec for spec in KNOWN_SECRETS if spec.dev_fallback is not None])
def test_explicit_development_value_is_still_reported_as_insecure(spec):
    set_backend(FakeBackend({spec.name: spec.dev_fallback}))
    assert is_using_dev_fallback(spec.name) is True
    posture = get_secrets_posture()
    assert posture["any_dev_fallback_in_use"] is True
    # Presence and safety are distinct: explicitly setting a public default
    # must not clear the insecure-fallback warning or reveal the value.
    assert spec.dev_fallback not in str(posture)

@pytest.mark.parametrize("fallback_names", [
    {"NXTDEAL_HUB_KEY"}, {"DEALEROS_NETWORK_KEY"},
    {"NXTDEAL_HUB_KEY", "DEALEROS_NETWORK_KEY"},
])
def test_infrastructure_summary_rejects_explicit_public_defaults(fallback_names):
    values = {"NXTDEAL_HUB_KEY": "private-hub-value", "DEALEROS_NETWORK_KEY": "private-network-value"}
    for spec in KNOWN_SECRETS:
        if spec.name in fallback_names:
            values[spec.name] = spec.dev_fallback
    set_backend(FakeBackend(values))
    posture = get_hub_security_posture()
    assert posture["hub_shared_key_configured_from_env"] is True
    assert posture["network_shared_key_configured_from_env"] is True
    assert posture["hub_shared_key_using_dev_fallback"] == ("NXTDEAL_HUB_KEY" in fallback_names)
    assert posture["network_shared_key_using_dev_fallback"] == ("DEALEROS_NETWORK_KEY" in fallback_names)
    assert "Both" not in posture["summary"]
    for name in fallback_names:
        assert name in posture["summary"]
    for value in values.values():
        assert value not in str(posture)
