"""Optional organization references preserve relationships, not access grants."""
import pytest
from core import dealer_bridge as b
from core.bridge_plan import import_order
from core.bridge_discovery import header_suggestions
from tests.test_bridge_pilot_workflow import csv_export
from tests.test_dealer_bridge import A, B, isolated  # noqa: F401


def field(source, kind=None):
    return {"source": source, "transform": "external_id", "object_type": kind} if kind else {"source": source, "transform": "text"}


def mapping(system, kind, source, fields):
    mid = b.propose_mapping(A, system, kind, source, fields)["id"]
    b.approve_mapping(B, mid)
    return mid


def import_rows(mid, columns, rows):
    job = b.stage(A, mid, csv_export(columns, rows))["id"]
    checked = b.validate(A, job)
    assert all(row["status"] != "quarantined" for row in checked), checked
    b.activate(B, job)
    return b.get(job, "BridgeJob")["preview"]


def test_dealer_location_household_dependencies_and_source_references():
    system = b.connect(A, "CSV", "Synthetic multi-rooftop source")["id"]
    dealer = mapping(system, "Dealer", "dealers", {"name": field("name")})
    location = mapping(system, "Location", "locations", {"name": field("name"), "dealer_id": field("dealer", "dealers")})
    household = mapping(system, "Household", "households", {"name": field("name")})
    customer = mapping(system, "Customer", "customers", {"first_name": field("name"),
        "location_id": field("location", "locations"), "household_id": field("household", "households")})
    plan = {item["object_type"]: item for item in import_order(A, system)["objects"]}
    assert plan["dealers"]["step"] < plan["locations"]["step"] < plan["customers"]["step"]
    assert plan["households"]["step"] < plan["customers"]["step"]
    columns, rows = ["name", "location", "household"], [("c1", ["Synthetic", "l1", "h1"])]
    unresolved = b.stage(A, customer, csv_export(columns, rows))["id"]
    assert b.validate(A, unresolved)[0]["status"] == "quarantined"
    import_rows(dealer, ["name"], [("d1", ["Synthetic dealer"])])
    import_rows(location, ["name", "dealer"], [("l1", ["North store", "d1"])])
    import_rows(household, ["name"], [("h1", ["Synthetic household"])])
    checked = b.validate(A, unresolved)
    assert checked[0]["status"] == "ready"
    b.activate(B, unresolved)
    from core.bridge_lineage import lookup
    current = lookup(A, system, "customers", "c1")["current_values"]
    assert current["location_id"] == lookup(A, system, "locations", "l1")["canonical_id"]
    assert current["household_id"] == lookup(A, system, "households", "h1")["canonical_id"]
    assert import_rows(customer, columns, rows)[0]["status"] == "duplicate"


@pytest.mark.parametrize("kind", ["Employee", "Vehicle", "Deal", "ServiceRecord", "Appointment", "Customer"])
def test_location_reference_is_exposed_for_explicit_review(kind):
    result = header_suggestions(kind, ["location_id"])
    assert result["reference_fields"]["location_id"] == "Location"
    assert result["suggestions"]["location_id"]["transform"] == "text"  # Never guess a source namespace.


def test_wrong_type_and_foreign_household_are_quarantined():
    from core.dealeros import ledger
    system = b.connect(A, "CSV", "Synthetic reference guard")["id"]
    household = mapping(system, "Household", "households", {"name": field("name")})
    import_rows(household, ["name"], [("h1", ["Synthetic household"])])
    target = next(e for e in ledger.get_all().values() if e.entity_type == "Household")
    customer = mapping(system, "Customer", "customers", {"first_name": field("name"), "household_id": field("household")})
    target.attributes["workspace_id"] = "foreign"
    job = b.stage(A, customer, csv_export(["name", "household"], [("c1", ["Synthetic", target.id])]))["id"]
    assert b.validate(A, job)[0]["status"] == "quarantined"
    target.attributes["workspace_id"] = ledger.tenant.workspace_id
    target.entity_type = "Location"
    assert b.validate(A, job)[0]["status"] == "quarantined"
