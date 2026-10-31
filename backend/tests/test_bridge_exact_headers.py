"""Column names are exact source identifiers even when an export includes spaces."""
from core import dealer_bridge as b
from core.bridge_discovery import discover_file
from tests.test_dealer_bridge import A, B, isolated  # noqa: F401


def test_discovered_spaced_headers_round_trip_through_approved_mapping_and_import():
    system = b.connect(A, "CSV", "Exact header fixture")["id"]
    content = ' external_id , modified_at , first_name , email \nfixture-1,2026-10-01T00:00:00Z,Pilot,pilot@example.invalid\n'
    discovery = discover_file(A, system, "Customer", content)
    assert discovery["source_columns"] == {"external_id": " external_id ", "modified_at": " modified_at "}
    assert discovery["suggestions"]["first_name"]["source"] == " first_name "
    mapping = b.propose_mapping(A, system, "Customer", "customers", discovery["suggestions"], discovery["source_columns"])["id"]
    b.approve_mapping(B, mapping)
    job = b.stage(A, mapping, content)["id"]
    assert b.validate(A, job)[0]["values"] == {"first_name": "Pilot", "email": "pilot@example.invalid"}
    b.activate(B, job)
    assert b.import_report(A, job)["receipt_integrity"] == "consistent"


def test_similar_spaced_headers_remain_ambiguous_in_discovery_and_distinct_in_mapping():
    system = b.connect(A, "CSV", "Ambiguous header fixture")["id"]
    content = 'external_id,modified_at,first_name, first_name \nfixture-1,2026-10-01T00:00:00Z,One,Two\n'
    discovery = discover_file(A, system, "Customer", content)
    assert "first_name" in discovery["ambiguous_fields"] and "first_name" not in discovery["suggestions"]
    mapping = b.propose_mapping(A, system, "Customer", "customers", {"first_name": {"source": " first_name ", "transform": "text"}})["id"]
    assert b.simulate_mapping(A, mapping, content)["rows"][0]["values"]["first_name"] == "Two"
