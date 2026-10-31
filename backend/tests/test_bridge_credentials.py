from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import pickle

import pytest
from core import bridge_credentials as credentials, dealer_bridge as bridge
from core.dealeros import ledger
from tests.test_dealer_bridge import A, B, isolated, setup  # noqa: F401


class Provider:
    def __init__(self):
        self.calls = []
        self.value = {"access_token": "synthetic-secret-one"}
        self.during_read = None
    def read(self, reference):
        self.calls.append(reference)
        if self.during_read: self.during_read()
        return self.value


def configured():
    system, _ = setup()
    broker, provider = credentials.CredentialBroker(), Provider()
    config = dict(reference="vault/dealer-read", account_ref="dealer-account-a", environment="sandbox", objects=["customers"])
    broker.grant(system, provider=provider, **config, expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
    return system, broker, provider, config


def test_scoped_secret_rotation_is_uncached_and_never_persisted():
    system, broker, provider, config = configured()
    before = {key: deepcopy(value.attributes) for key, value in ledger.entities.items()}
    first = broker.resolve(system, **config)
    assert first.require("access_token") == "synthetic-secret-one"
    assert "synthetic-secret" not in repr(first)
    assert "vault/dealer-read" not in repr(broker._grants)
    provider.value["access_token"] = "synthetic-secret-two"
    assert first.require("access_token") == "synthetic-secret-one"
    assert broker.resolve(system, **config).require("access_token") == "synthetic-secret-two"
    assert len(provider.calls) == 2
    assert before == {key: value.attributes for key, value in ledger.entities.items()}
    with pytest.raises(TypeError): pickle.dumps(first)
    with pytest.raises(TypeError): json.dumps(first)


@pytest.mark.parametrize("field,value", [("reference", "vault/other"), ("account_ref", "other-account"),
    ("environment", "production"), ("objects", ["customers", "payments"]), ("objects", []), ("objects", ["*"])])
def test_wrong_scope_never_calls_provider(field, value):
    system, broker, provider, config = configured()
    config[field] = value
    with pytest.raises(credentials.CredentialUnavailable): broker.resolve(system, **config)
    assert provider.calls == []


def test_other_system_pause_and_foreign_workspace_are_rejected_before_io():
    system, broker, provider, config = configured()
    other = bridge.connect(A, "CSV", "Another system")["id"]
    with pytest.raises(credentials.CredentialUnavailable): broker.resolve(other, **config)
    bridge.set_system_paused(B, system, True, "Suspend credentials in synthetic test")
    with pytest.raises(credentials.CredentialUnavailable): broker.resolve(system, **config)
    bridge.get(system, "BridgeSystem")["workspace_id"] = "other"
    with pytest.raises(credentials.CredentialUnavailable): broker.resolve(system, **config)
    assert not provider.calls


@pytest.mark.parametrize("change", ["revoke", "replace", "pause", "vendor", "workspace"])
def test_scope_changes_during_provider_read_discard_result(change):
    system, broker, provider, config = configured()
    def during():
        if change == "revoke": broker.revoke(system)
        elif change == "replace": broker.grant(system, provider=Provider(), **config, expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
        elif change == "pause": bridge.set_system_paused(B, system, True, "Pause during synthetic secret resolution")
        else: bridge.get(system, "BridgeSystem")["vendor" if change == "vendor" else "workspace_id"] = "other"
    provider.during_read = during
    with pytest.raises(credentials.CredentialUnavailable): broker.resolve(system, **config)


@pytest.mark.parametrize("invalid", [None, {}, {"token": ""}, {"token": 1}, {"token": "x" * 16385}, {"bad key": "secret"}, {"token": "\ud800"}], ids=["none", "empty", "blank", "number", "large", "key", "unicode"])
def test_invalid_provider_values_are_sanitized(invalid):
    system, broker, provider, config = configured()
    provider.value = invalid
    with pytest.raises(credentials.CredentialUnavailable, match="Authorized connector credentials are unavailable"):
        broker.resolve(system, **config)


def test_provider_error_details_do_not_escape():
    system, broker, provider, config = configured()
    def fail(): raise RuntimeError("synthetic-secret-in-raw-provider-error")
    provider.during_read = fail
    with pytest.raises(credentials.CredentialUnavailable) as error: broker.resolve(system, **config)
    assert "synthetic-secret" not in str(error.value)
    assert error.value.__suppress_context__


def test_expired_and_naive_grants_are_not_installed():
    system, broker, provider, config = configured()
    for expiry in (datetime.now(timezone.utc) - timedelta(seconds=1), datetime.now(), "tomorrow"):
        with pytest.raises(credentials.CredentialUnavailable): broker.grant(system, provider=provider, **config, expires_at=expiry)
    assert broker.resolve(system, **config).require("access_token") == "synthetic-secret-one"



def test_grant_expiry_during_provider_read_discards_material(monkeypatch):
    system, broker, provider, config = configured()
    class Later(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.now(tz) + timedelta(hours=2)
    provider.during_read = lambda: monkeypatch.setattr(credentials, "datetime", Later)
    with pytest.raises(credentials.CredentialUnavailable): broker.resolve(system, **config)


@pytest.mark.parametrize("change", ["revoke","replace","pause","vendor","workspace","removed","expired"])
def test_resolved_material_rechecks_grant_before_returning_a_field(change, monkeypatch):
    system,broker,provider,config=configured()
    material=broker.resolve(system,**config)
    assert material.require("access_token")=="synthetic-secret-one"
    if change=="revoke":broker.revoke(system)
    elif change=="replace":broker.grant(system,provider=Provider(),**config,expires_at=datetime.now(timezone.utc)+timedelta(hours=1))
    elif change=="pause":bridge.set_system_paused(B,system,True,"Suspend synthetic source before using resolved material")
    elif change=="removed":ledger.entities.pop(system)
    elif change=="expired":
        class Later(datetime):
            @classmethod
            def now(cls,tz=None):return datetime.now(tz)+timedelta(hours=2)
        monkeypatch.setattr(credentials,"datetime",Later)
    else:bridge.get(system,"BridgeSystem")["vendor" if change=="vendor" else "workspace_id"]="other"
    with pytest.raises(credentials.CredentialUnavailable,match="Authorized connector credentials are unavailable"):
        material.require("access_token")
    assert len(provider.calls)==1
