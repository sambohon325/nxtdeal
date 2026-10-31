"""Local connector declarations never imply authenticated vendor access."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from core import bridge_runtime as runtime
from core.bridge_connectors import CATALOG, REGISTRY, CsvConnector, UnavailableConnector, register_connector
from core.bridge_contracts import validated_capabilities
from core import dealer_bridge as bridge
from tests.test_dealer_bridge import A, CSV, isolated  # noqa: F401


@pytest.fixture(autouse=True)
def isolate_registration():
    catalog, registry, bindings = deepcopy(CATALOG), REGISTRY.copy(), runtime._BINDINGS.copy()
    runtime._BINDINGS.clear()
    yield
    CATALOG.clear(); CATALOG.update(catalog)
    REGISTRY.clear(); REGISTRY.update(registry)
    runtime._BINDINGS.clear(); runtime._BINDINGS.update(bindings)


@pytest.mark.parametrize("declaration", [None, "sync", {"invented"}, ["sync", "sync"], [False], {"sync": True}, ["sync"] * 10])
def test_invalid_declarations_rejected_by_registry_and_runtime(declaration):
    adapter = SimpleNamespace(capabilities=declaration, sync=lambda *_: None)
    system = bridge.connect(A, "Frazer", "Test source")["id"]
    with pytest.raises(ValueError):
        register_connector("Frazer", adapter)
    with pytest.raises(ValueError):
        runtime.bind(system, adapter, revision="test-v1", objects=["customers"])
    assert CATALOG["Frazer"]["status"] == "requires_vendor_access"
    assert runtime.describe(system)["status"] == "unavailable"


def test_inherited_unavailable_method_cannot_be_advertised_as_implemented():
    class IncorrectAdapter(UnavailableConnector):
        capabilities = frozenset({"sync"})
    with pytest.raises(ValueError, match="no implementation"):
        validated_capabilities(IncorrectAdapter())


def test_capability_validation_has_no_network_or_authentication_side_effects():
    def forbidden(*args, **kwargs):
        raise AssertionError("Contract inspection must not invoke adapter operations")
    adapter = SimpleNamespace(capabilities={"sync", "health", "authenticate"}, sync=forbidden,
                              health=forbidden, authenticate=forbidden)
    assert validated_capabilities(adapter) == frozenset({"sync", "health", "authenticate"})
    register_connector("Frazer", adapter)
    system = bridge.connect(A, "Frazer", "Unauthenticated source")["id"]
    assert bridge.get(system, "BridgeSystem")["health"]["status"] == "unavailable"


def test_runtime_pins_verified_capabilities_until_explicit_rebind():
    adapter = CsvConnector(CSV)
    system = bridge.connect(A, "CSV", "Authorized synthetic export")["id"]
    runtime.bind(system, adapter, revision="fixture-v1", objects=["customers"])
    before = runtime.describe(system)
    adapter.capabilities = frozenset({"sync"})
    assert runtime.describe(system) == before
    runtime.bind(system, adapter, revision="fixture-v2", objects=["customers"])
    assert runtime.describe(system)["capabilities"] == ["sync"]


def test_all_shipped_stubs_and_local_csv_have_honest_contracts():
    assert all(not validated_capabilities(adapter) for name, adapter in REGISTRY.items() if name != "CSV")
    assert validated_capabilities(CsvConnector(CSV)) == frozenset({"discover", "schema", "sync", "health"})
    assert "write" not in validated_capabilities(CsvConnector(CSV))


def test_advertised_noncallable_method_fails_before_binding():
    with pytest.raises(ValueError, match="no implementation"):
        validated_capabilities(SimpleNamespace(capabilities={"sync"}, sync=True))


def test_active_connector_replacement_or_scope_change_requires_new_revision():
    adapter = CsvConnector(CSV)
    system = bridge.connect(A, "CSV", "Synthetic export")["id"]
    runtime.bind(system, adapter, revision="v1", objects=["customers"])
    original = runtime.binding(system)
    runtime.bind(system, adapter, revision="v1", objects=["customers"])
    assert runtime.binding(system) is original
    with pytest.raises(ValueError, match="new revision"):
        runtime.bind(system, CsvConnector(CSV), revision="v1", objects=["customers"])
    with pytest.raises(ValueError, match="new revision"):
        runtime.bind(system, adapter, revision="v1", objects=["customers", "accounts"])
    assert runtime.binding(system) is original



def test_csv_snapshot_does_not_claim_historical_feed():
    from core import bridge_sync as sync
    from tests.test_dealer_bridge import setup
    system, mapping = setup()
    adapter = CsvConnector(CSV, object_type="customers")
    runtime.bind(system, adapter, revision="snapshot-v1", objects=["customers"])
    assert "history" not in runtime.describe(system)["capabilities"]
    assert "history" not in CATALOG["CSV"]["capabilities"]
    with pytest.raises(ValueError, match="unavailable"):
        adapter.history("customers", None)
    with pytest.raises(ValueError):
        sync.configure(A, mapping, True, mode="history")
    assert bridge.system_map(A)["sync_states"] == []
    assert adapter.sync("customers").records


@pytest.mark.parametrize("method", ["schema", "sync"])
def test_csv_explicit_object_scope_cannot_be_relabeled(method):
    adapter = CsvConnector(CSV, object_type="customers")
    with pytest.raises(ValueError, match="does not match"):
        getattr(adapter, method)("loan_accounts")


@pytest.mark.parametrize("content,expected", [(None, "unavailable"), ("invalid", "source_changed"), (CSV, "ready")])
def test_csv_health_checks_bound_snapshot_without_returning_values(content, expected):
    result = CsvConnector(content).health()
    assert result == {"status": expected, "transport": "manual_upload"}
