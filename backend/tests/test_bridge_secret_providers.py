from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import pickle
from types import SimpleNamespace

import pytest
from core.bridge_credentials import CredentialBroker, CredentialUnavailable
from core.bridge_secret_providers import EnvironmentSecretProvider
from core import bridge_secret_providers as providers
from core.dealeros import ledger
from tests.test_dealer_bridge import isolated, setup  # noqa: F401

NAME = "NXTDEAL_TEST_ONLY_SECRET_BUNDLE"
REFERENCE = "test-only/export"


def test_provider_is_lazy_allowlisted_uncached_and_does_not_retain_values(monkeypatch):
    monkeypatch.delenv(NAME, raising=False)
    config = {REFERENCE:NAME}
    provider = EnvironmentSecretProvider(config)
    config[REFERENCE] = "NOT_THE_CONFIGURED_VARIABLE"
    with pytest.raises(CredentialUnavailable): provider.read(REFERENCE)
    monkeypatch.setenv(NAME, json.dumps({"access_token":"synthetic-first"}))
    first = provider.read(REFERENCE)
    monkeypatch.setenv(NAME, json.dumps({"access_token":"synthetic-second"}))
    assert provider.read(REFERENCE) == {"access_token":"synthetic-second"}
    assert first == {"access_token":"synthetic-first"}
    assert "synthetic" not in repr(provider) and NAME not in repr(provider) and REFERENCE not in repr(provider)
    with pytest.raises(CredentialUnavailable): provider.read(NAME)
    with pytest.raises(TypeError): pickle.dumps(provider)


@pytest.mark.parametrize("raw", ["", "not-json-private", "null", "[]", "{}", '{"access_token":null}',
    '{"access_token":123}', '{"access_token":true}', '{"access_token":NaN}',
    '{"access_token":{"nested":"private"}}', '{"access_token":"one","access_token":"two"}',
    '{"access_token":""}', '{"bad field":"private"}', json.dumps({"token":"x"*16385}),
    json.dumps({f"field{i}":"x" for i in range(21)}), '{"token":"\\ud800"}', " "*131073,
    json.dumps({f"field{i}":"x"*14000 for i in range(5)})],
    ids=["blank","syntax","null","list","empty","null-field","number","bool","nan","nested","duplicate","empty-field","field-name","value-size","field-count","unicode","body-size","total-size"])
def test_invalid_bundles_fail_closed_without_reflecting_material(monkeypatch, raw):
    # Exercise provider bounds independently of platform environment-size limits.
    monkeypatch.setattr(providers, "os", SimpleNamespace(environ={NAME:raw}))
    provider = EnvironmentSecretProvider({REFERENCE:NAME})
    with pytest.raises(CredentialUnavailable) as error: provider.read(REFERENCE)
    assert str(error.value) == "Authorized connector credentials are unavailable"
    assert error.value.__suppress_context__


@pytest.mark.parametrize("config", [{}, None, {"bad reference":NAME}, {REFERENCE:"lowercase"},
    {REFERENCE:"NAME=VALUE"}, {REFERENCE:"A"*129}, {REFERENCE:42}, {str(i):NAME for i in range(101)}],
    ids=["empty","none","reference","lowercase","assignment","length","type","count"])
def test_invalid_operator_configuration_is_rejected(config):
    with pytest.raises(CredentialUnavailable): EnvironmentSecretProvider(config)


def test_scoped_broker_uses_bundle_without_persisting_or_granting_more_access(monkeypatch):
    system, _ = setup()
    monkeypatch.setenv(NAME, json.dumps({"access_token":"synthetic-broker-secret"}))
    provider, broker = EnvironmentSecretProvider({REFERENCE:NAME}), CredentialBroker()
    config = dict(reference=REFERENCE, account_ref="qa-account", environment="synthetic", objects=["customers"])
    broker.grant(system, provider=provider, **config, expires_at=datetime.now(timezone.utc)+timedelta(minutes=5))
    before = deepcopy(ledger.entities)
    material = broker.resolve(system, **config)
    assert material.require("access_token") == "synthetic-broker-secret"
    assert "synthetic-broker-secret" not in repr(material)
    assert ledger.entities == before
    with pytest.raises(CredentialUnavailable): broker.resolve(system, **{**config,"objects":["payments"]})
    broker.revoke(system)
    with pytest.raises(CredentialUnavailable): material.assert_current()
    with pytest.raises(CredentialUnavailable): broker.resolve(system, **config)


def test_private_key_bundle_preserves_exact_newlines_and_passphrase(monkeypatch):
    bundle = {"private_key":"-----BEGIN TEST KEY-----\nsynthetic\n-----END TEST KEY-----\n", "passphrase":"synthetic passphrase"}
    monkeypatch.setenv(NAME, json.dumps(bundle))
    assert EnvironmentSecretProvider({REFERENCE:NAME}).read(REFERENCE) == bundle


def test_provider_reads_only_one_allowlisted_variable_without_enumerating_environment(monkeypatch):
    class Environment:
        calls = []
        def get(self, key):
            self.calls.append(key)
            return '{"access_token":"synthetic-one-read"}'
        def __iter__(self):
            pytest.fail("Provider must never enumerate process environment")
    environment = Environment()
    monkeypatch.setattr(providers, "os", SimpleNamespace(environ=environment))
    provider = EnvironmentSecretProvider({REFERENCE:NAME})
    with pytest.raises(CredentialUnavailable): provider.read("not/allowlisted")
    assert environment.calls == []
    assert provider.read(REFERENCE) == {"access_token":"synthetic-one-read"}
    assert environment.calls == [NAME]
