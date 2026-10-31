"""The dealer's requested stack is discoverable without claiming live access."""
from copy import deepcopy

import pytest

from core.bridge_catalog import CATALOG, CATEGORY_LABELS, GROUPS
from core.bridge_connectors import REGISTRY, UnavailableConnector
from core.bridge_contracts import FIELDS
from core import dealer_bridge as bridge, bridge_runtime as runtime
from tests.test_dealer_bridge import A, isolated  # noqa: F401


REQUESTED = ["CDK Global", "Reynolds and Reynolds", "ERA-IGNITE", "Tekion", "Dealertrack DMS",
    "DealerCenter", "Frazer", "Auto/Mate", "Desk-It", "Wayne Reaves", "ABCoA Deal Pack", "DealerClick",
    "Auto Master Systems", "AMS", "Finance Express", "VinSolutions", "Elead", "DriveCentric",
    "DealerSocket", "Selly Automotive", "DealerCenter CRM", "cyclCRM", "Impel", "SpinCar", "Matador.ai",
    "Fullpath", "AutoLeadStar", "CarNow Conversational AI", "Car Wars", "CallRail", "Convirza", "Podium",
    "Kenect", "SocketTalk", "Dealer.com", "DealerOn", "Dealer Inspire", "Dealer Spike", "DealerCenter Web",
    "Carbase", "vAuto", "Provision", "Conquest", "Max Digital", "Laser Appraiser", "Carbly", "Manheim MMR",
    "Kelley Blue Book", "Black Book", "CARFAX", "Dealer-FX", "AutoHook", "Megasys", "Nortridge Loan System",
    "NLS", "Spireon", "GoldStar", "PassTime GPS", "Procon Analytics", "PayNearMe", "REPAY", "Speedpay",
    "Datalinx Metro 2", "Equifax", "Experian", "TransUnion", "RouteOne"]


def test_every_requested_product_label_is_discoverable_without_duplicate_ids():
    names = {name.casefold() for entry in CATALOG.values() for name in [entry["id"], *entry["aliases"]]}
    assert not {name for name in REQUESTED if name.casefold() not in names}
    grouped = [name for names in GROUPS.values() for name in names]
    assert len(grouped) == len(set(grouped))
    assert set(grouped) == set(CATALOG) - {"CSV"}


@pytest.mark.parametrize("vendor", ["Desk-It", "DealerClick", "Auto Master Systems", "Finance Express",
    "DealerCenter CRM", "DealerCenter Web", "Selly Automotive", "cyclCRM", "CarNow Conversational AI",
    "Fullpath", "Dealer-FX", "AutoHook", "Megasys", "Nortridge Loan System", "Spireon GoldStar",
    "PassTime GPS", "Procon Analytics", "Datalinx Metro 2", "Speedpay", "RouteOne", "Dealertrack Lender Network"])
def test_added_software_is_a_read_only_access_request_not_a_connection(vendor):
    system_id = bridge.connect(A, vendor, "Synthetic requested system")["id"]
    system = bridge.get(system_id, "BridgeSystem")
    assert system["mode"] == "read_only" and system["health"]["status"] == "unavailable"
    assert runtime.describe(system_id)["status"] == "unavailable"
    assert isinstance(REGISTRY[vendor], UnavailableConnector)
    assert not REGISTRY[vendor].capabilities
    with pytest.raises(ValueError, match="unavailable"):
        REGISTRY[vendor].write({"test": "never dispatched"})


def test_product_scopes_are_separate_and_planning_references_known_types():
    for products in [("DealerCenter", "DealerCenter CRM", "DealerCenter Web"),
                     ("Dealertrack", "Dealertrack Lender Network"), ("Dealer-FX", "AutoHook"),
                     ("Auto Master Systems", "AutoManager DeskManager"), ("Laser Appraiser", "Carbly")]:
        assert len({CATALOG[product]["id"] for product in products}) == len(products)
    for entry in CATALOG.values():
        assert entry["category_label"] == CATEGORY_LABELS[entry["category"]]
        assert set(entry["planned_record_types"]) <= set(FIELDS)
        assert entry["writeback"] == "disabled"
        if entry["id"] != "CSV":
            assert entry["planning_only"] and not entry["capabilities"]


def test_system_map_catalog_is_detached_from_runtime_registry_metadata():
    before = deepcopy(CATALOG["Spireon GoldStar"])
    response = bridge.system_map(A)
    entry = next(value for value in response["catalog"] if value["id"] == "Spireon GoldStar")
    entry["aliases"].append("untrusted alias")
    entry["capabilities"].append("write")
    response["category_labels"]["telematics"] = "Changed by caller"
    assert CATALOG["Spireon GoldStar"] == before
    assert CATEGORY_LABELS["telematics"] == "GPS and telematics"


def test_requested_cross_category_discovery_preserves_one_product_identity():
    expected={"Auto/Mate":["dms","independent_bhph"],"Deal Pack":["independent_bhph","loan_servicing"],"Fullpath":["marketing","conversational_ai"]}
    report=bridge.system_map(A)
    for name,categories in expected.items():
        entry=next(item for item in report["catalog"] if item["id"]==name)
        assert entry["discovery_categories"]==categories
        assert entry["category"]==categories[0] and entry["planning_only"]
        assert not entry["capabilities"] and entry["writeback"]=="disabled"
        for category in categories:
            assert len([item for item in report["catalog"] if item["id"]==name and category in item["discovery_categories"]])==1
        entry["discovery_categories"].append("mutated-client-category")
        assert CATALOG[name]["discovery_categories"]==categories
    for entry in CATALOG.values():
        assert entry["category"]==entry["discovery_categories"][0]
        assert len(entry["discovery_categories"])==len(set(entry["discovery_categories"]))
        assert set(entry["discovery_categories"])<=set(CATEGORY_LABELS)
