"""
Tests for core/queries.py — the Phase-4 graph Query Engine (entity/relationship lookups,
the *_360 profile builders, the count dashboards, free-text search, graph views/trees, and
the keyword `ask_question` router). This module reads the singleton ledger directly
(`from core.dealeros import ledger`), so every test seeds Entity/Relationship objects into
that ledger by hand and resets it around each test — fully deterministic and
seed-independent (nothing here depends on storage/graph.json). No disk is touched:
queries.py is read-only, it never calls save_graph. Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.relationships import Relationship

from core import queries


# ---------------------------------------------------------------------------
# helpers / fixture
# ---------------------------------------------------------------------------

def _entity(entity_id, entity_type, **attributes):
    ledger.add_entity(Entity(entity_id, entity_type, attributes))
    return entity_id


def _rel(source_id, target_id, relationship_type):
    ledger.add_relationship(
        Relationship(source_id, target_id, relationship_type)
    )


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield
    ledger.reset()


# ---------------------------------------------------------------------------
# primitive lookups
# ---------------------------------------------------------------------------

def test_get_entity_returns_the_seeded_entity_and_none_for_unknown():
    _entity("CUST-1", "Customer", Name="Jane Doe")

    got = queries.get_entity("CUST-1")
    assert got is not None
    assert got.entity_type == "Customer"
    assert got.attributes["Name"] == "Jane Doe"

    assert queries.get_entity("CUST-NOPE") is None


def test_get_entity_relationships_returns_edges_touching_the_entity_either_direction():
    _entity("CUST-1", "Customer")
    _entity("FIN-1", "FinanceContract")
    _entity("EMP-1", "Employee")
    _entity("OTHER-1", "Customer")

    _rel("CUST-1", "FIN-1", "FINANCED_BY")   # CUST-1 as source
    _rel("EMP-1", "CUST-1", "ASSIGNED_TO")   # CUST-1 as target
    _rel("OTHER-1", "FIN-1", "FINANCED_BY")  # does not touch CUST-1

    rels = queries.get_entity_relationships("CUST-1")

    assert len(rels) == 2
    types = sorted(r.relationship_type for r in rels)
    assert types == ["ASSIGNED_TO", "FINANCED_BY"]


def test_get_connected_entities_returns_the_other_end_of_every_touching_edge():
    _entity("CUST-1", "Customer")
    _entity("FIN-1", "FinanceContract")
    _entity("EMP-1", "Employee")

    _rel("CUST-1", "FIN-1", "FINANCED_BY")
    _rel("EMP-1", "CUST-1", "ASSIGNED_TO")

    connected = queries.get_connected_entities("CUST-1")

    assert sorted(connected) == ["EMP-1", "FIN-1"]


def test_get_connected_entities_empty_for_isolated_entity():
    _entity("CUST-1", "Customer")

    assert queries.get_connected_entities("CUST-1") == []


def test_find_entities_by_type_filters_on_entity_type():
    _entity("VEH-1", "Vehicle")
    _entity("VEH-2", "Vehicle")
    _entity("CUST-1", "Customer")

    vehicles = queries.find_entities_by_type("Vehicle")

    assert {v.id for v in vehicles} == {"VEH-1", "VEH-2"}
    assert queries.find_entities_by_type("Lender") == []


# ---------------------------------------------------------------------------
# customer profile / 360
# ---------------------------------------------------------------------------

def test_get_customer_profile_bundles_customer_plus_its_relationships():
    _entity("CUST-1", "Customer", Name="Jane")
    _entity("FIN-1", "FinanceContract")
    _rel("CUST-1", "FIN-1", "FINANCED_BY")

    profile = queries.get_customer_profile("CUST-1")

    assert profile["customer"].id == "CUST-1"
    assert len(profile["relationships"]) == 1
    assert profile["relationships"][0].relationship_type == "FINANCED_BY"


def test_get_customer_360_walks_finance_vehicle_service_lead_and_documents():
    _entity("CUST-1", "Customer", Name="Jane")
    _entity("FIN-1", "FinanceContract")
    _entity("VEH-1", "Vehicle")
    _entity("SRV-1", "ServiceRecord")
    _entity("LEAD-1", "Lead")
    _entity("DOC-1", "Document")

    # customer -> finance -> (COVERS) vehicle
    _rel("CUST-1", "FIN-1", "FINANCED_BY")
    _rel("FIN-1", "VEH-1", "COVERS")
    # customer -> service record
    _rel("CUST-1", "SRV-1", "AUTHORIZED")
    # lead -> customer (lead is the SOURCE of BECAME)
    _rel("LEAD-1", "CUST-1", "BECAME")
    # customer -> document
    _rel("CUST-1", "DOC-1", "HAS_DOCUMENT")

    profile = queries.get_customer_360("CUST-1")

    assert [f.id for f in profile["finances"]] == ["FIN-1"]
    assert [v.id for v in profile["vehicles"]] == ["VEH-1"]
    assert [s.id for s in profile["service_records"]] == ["SRV-1"]
    assert [l.id for l in profile["lead_sources"]] == ["LEAD-1"]
    assert [d.id for d in profile["documents"]] == ["DOC-1"]


# ---------------------------------------------------------------------------
# vehicle 360
# ---------------------------------------------------------------------------

def test_get_vehicle_360_walks_owner_finance_service_document_and_image():
    _entity("VEH-1", "Vehicle", VIN="ABC")
    _entity("CUST-1", "Customer")
    _entity("FIN-1", "FinanceContract")
    _entity("SRV-1", "ServiceRecord")
    _entity("DOC-1", "Document")
    _entity("IMG-1", "Image")

    _rel("CUST-1", "VEH-1", "OWNS")            # owner is the SOURCE
    _rel("FIN-1", "VEH-1", "COVERS")           # finance is the SOURCE
    _rel("VEH-1", "SRV-1", "HAS_SERVICE_RECORD")
    _rel("VEH-1", "DOC-1", "HAS_DOCUMENT")
    _rel("VEH-1", "IMG-1", "HAS_IMAGE")

    profile = queries.get_vehicle_360("VEH-1")

    assert [o.id for o in profile["owners"]] == ["CUST-1"]
    assert [f.id for f in profile["finance_contracts"]] == ["FIN-1"]
    assert [s.id for s in profile["service_records"]] == ["SRV-1"]
    assert [d.id for d in profile["documents"]] == ["DOC-1"]
    assert [i.id for i in profile["images"]] == ["IMG-1"]


# ---------------------------------------------------------------------------
# employee / manager / team 360
# ---------------------------------------------------------------------------

def test_get_employee_360_splits_assigned_customers_and_leads():
    _entity("EMP-1", "Employee", Name="Rep")
    _entity("CUST-1", "Customer")
    _entity("LEAD-1", "Lead")
    _entity("LEAD-2", "Lead")

    _rel("EMP-1", "CUST-1", "ASSIGNED_TO")
    _rel("EMP-1", "LEAD-1", "ASSIGNED_TO")
    _rel("EMP-1", "LEAD-2", "ASSIGNED_TO")

    profile = queries.get_employee_360("EMP-1")

    assert [c.id for c in profile["customers"]] == ["CUST-1"]
    assert sorted(l.id for l in profile["leads"]) == ["LEAD-1", "LEAD-2"]


def test_get_employee_360_ignores_assigned_to_targets_missing_from_the_ledger():
    _entity("EMP-1", "Employee")
    _rel("EMP-1", "GONE-1", "ASSIGNED_TO")  # target never added

    profile = queries.get_employee_360("EMP-1")

    assert profile["customers"] == []
    assert profile["leads"] == []


def test_get_manager_360_lists_direct_reports_via_managed_by():
    _entity("MGR-1", "Employee", Name="Boss")
    _entity("EMP-1", "Employee")
    _entity("EMP-2", "Employee")
    _entity("EMP-3", "Employee")

    _rel("EMP-1", "MGR-1", "MANAGED_BY")
    _rel("EMP-2", "MGR-1", "MANAGED_BY")
    _rel("EMP-3", "OTHER-MGR", "MANAGED_BY")  # reports to someone else

    profile = queries.get_manager_360("MGR-1")

    assert sorted(e.id for e in profile["direct_reports"]) == ["EMP-1", "EMP-2"]


def test_get_team_360_aggregates_reports_and_their_assignments_with_counts():
    _entity("MGR-1", "Employee")
    _entity("EMP-1", "Employee")
    _entity("EMP-2", "Employee")
    _entity("CUST-1", "Customer")
    _entity("CUST-2", "Customer")
    _entity("LEAD-1", "Lead")

    _rel("EMP-1", "MGR-1", "MANAGED_BY")
    _rel("EMP-2", "MGR-1", "MANAGED_BY")
    _rel("EMP-1", "CUST-1", "ASSIGNED_TO")
    _rel("EMP-1", "LEAD-1", "ASSIGNED_TO")
    _rel("EMP-2", "CUST-2", "ASSIGNED_TO")

    profile = queries.get_team_360("MGR-1")

    assert profile["employee_count"] == 2
    assert profile["customer_count"] == 2
    assert profile["lead_count"] == 1
    assert sorted(c.id for c in profile["customers"]) == ["CUST-1", "CUST-2"]
    assert [l.id for l in profile["leads"]] == ["LEAD-1"]


# ---------------------------------------------------------------------------
# count dashboards
# ---------------------------------------------------------------------------

def _seed_mixed_graph():
    _entity("EMP-1", "Employee")
    _entity("EMP-2", "Employee")
    _entity("CUST-1", "Customer")
    _entity("LEAD-1", "Lead")
    _entity("VEH-1", "Vehicle")
    _entity("VEH-2", "Vehicle")
    _entity("FIN-1", "FinanceContract")
    _entity("SRV-1", "ServiceRecord")
    _entity("DOC-1", "Document")
    _entity("IMG-1", "Image")
    _entity("LENDER-1", "Lender")


def test_get_sales_dashboard_counts_by_type():
    _seed_mixed_graph()

    d = queries.get_sales_dashboard()

    assert d["employee_count"] == 2
    assert d["customer_count"] == 1
    assert d["lead_count"] == 1
    assert d["vehicle_count"] == 2
    assert d["finance_count"] == 1


def test_get_service_dashboard_counts_by_type():
    _seed_mixed_graph()

    d = queries.get_service_dashboard()

    assert d["service_record_count"] == 1
    assert d["vehicle_count"] == 2
    assert d["document_count"] == 1
    assert d["image_count"] == 1


def test_get_finance_dashboard_counts_by_type():
    _seed_mixed_graph()

    d = queries.get_finance_dashboard()

    assert d["finance_contract_count"] == 1
    assert d["customer_count"] == 1
    assert d["vehicle_count"] == 2
    assert d["lender_count"] == 1


def test_get_executive_dashboard_counts_every_tracked_type():
    _seed_mixed_graph()

    d = queries.get_executive_dashboard()

    assert d["employees"] == 2
    assert d["customers"] == 1
    assert d["leads"] == 1
    assert d["vehicles"] == 2
    assert d["finance_contracts"] == 1
    assert d["service_records"] == 1
    assert d["documents"] == 1
    assert d["images"] == 1
    assert d["lenders"] == 1


def test_dashboards_are_all_zero_on_an_empty_graph():
    assert queries.get_sales_dashboard()["customer_count"] == 0
    assert queries.get_executive_dashboard()["employees"] == 0


# ---------------------------------------------------------------------------
# graph view / tree
# ---------------------------------------------------------------------------

def test_get_graph_view_tags_out_and_in_edges():
    _entity("CUST-1", "Customer")
    _entity("FIN-1", "FinanceContract")
    _entity("EMP-1", "Employee")

    _rel("CUST-1", "FIN-1", "FINANCED_BY")   # OUT of CUST-1
    _rel("EMP-1", "CUST-1", "ASSIGNED_TO")   # IN to CUST-1

    view = queries.get_graph_view("CUST-1")

    assert view["entity"].id == "CUST-1"

    by_dir = {r["direction"]: r for r in view["relationships"]}
    assert by_dir["OUT"]["relationship"] == "FINANCED_BY"
    assert by_dir["OUT"]["entity"].id == "FIN-1"
    assert by_dir["IN"]["relationship"] == "ASSIGNED_TO"
    assert by_dir["IN"]["entity"].id == "EMP-1"


def test_get_graph_tree_respects_depth_and_avoids_cycles():
    # chain: A - B - C - D ; plus a back-edge A-B to make a cycle
    _entity("A", "Customer")
    _entity("B", "FinanceContract")
    _entity("C", "Vehicle")
    _entity("D", "ServiceRecord")

    _rel("A", "B", "FINANCED_BY")
    _rel("B", "C", "COVERS")
    _rel("C", "D", "HAS_SERVICE_RECORD")

    # depth 1 from A reaches B but not C
    shallow = queries.get_graph_tree("A", depth=1)
    assert shallow["entity"].id == "A"
    child_ids = {c["node"]["entity"].id for c in shallow["children"]}
    assert child_ids == {"B"}
    assert shallow["children"][0]["node"]["children"] == []

    # depth 3 reaches all of B, C, D along the chain; visited-set prevents infinite loop
    deep = queries.get_graph_tree("A", depth=3)
    b_node = deep["children"][0]["node"]
    assert b_node["entity"].id == "B"
    c_node = b_node["children"][0]["node"]
    assert c_node["entity"].id == "C"


def test_get_graph_tree_none_for_unknown_root():
    assert queries.get_graph_tree("NOPE") is None


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------

def test_search_graph_is_case_insensitive_substring_over_attribute_values():
    _entity("CUST-1", "Customer", Name="Jane Doe", City="Springfield")
    _entity("CUST-2", "Customer", Name="John Smith")

    hits = queries.search_graph("jane")
    assert [h.id for h in hits] == ["CUST-1"]

    # substring across any attribute, case-insensitive
    assert [h.id for h in queries.search_graph("SPRING")] == ["CUST-1"]


def test_search_graph_returns_each_matching_entity_at_most_once():
    # two attributes both contain the term — the `break` must dedupe to a single hit
    _entity("CUST-1", "Customer", First="match", Last="match")

    hits = queries.search_graph("match")
    assert [h.id for h in hits] == ["CUST-1"]


def test_search_graph_empty_when_nothing_matches():
    _entity("CUST-1", "Customer", Name="Jane")
    assert queries.search_graph("zzzz") == []


# ---------------------------------------------------------------------------
# ask_graph / ask_question
# ---------------------------------------------------------------------------

def test_ask_graph_pairs_each_matched_entity_with_its_graph_view():
    _entity("CUST-1", "Customer", Name="Zorptastic")
    _entity("FIN-1", "FinanceContract")
    _rel("CUST-1", "FIN-1", "FINANCED_BY")

    results = queries.ask_graph("zorptastic")

    assert len(results) == 1
    assert results[0]["entity"].id == "CUST-1"
    assert results[0]["graph"]["relationships"][0]["entity"].id == "FIN-1"


def test_ask_question_finance_branch_returns_financed_contracts():
    _entity("CUST-1", "Customer", Name="Zorptastic")
    _entity("FIN-1", "FinanceContract", Amount=10000)
    _rel("CUST-1", "FIN-1", "FINANCED_BY")

    out = queries.ask_question("show finance for zorptastic")

    assert out["type"] == "finance"
    assert [f.id for f in out["results"]] == ["FIN-1"]


def test_ask_question_lender_branch_follows_finance_to_lender():
    _entity("CUST-1", "Customer", Name="Zorptastic")
    _entity("FIN-1", "FinanceContract")
    _entity("LENDER-1", "Lender", Name="BigBank")
    _rel("CUST-1", "FIN-1", "FINANCED_BY")
    _rel("FIN-1", "LENDER-1", "FUNDED_BY")

    out = queries.ask_question("show lender for zorptastic")

    assert out["type"] == "lender"
    assert [l.id for l in out["results"]] == ["LENDER-1"]


def test_ask_question_vehicle_branch_returns_owned_vehicles():
    _entity("CUST-1", "Customer", Name="Zorptastic")
    _entity("VEH-1", "Vehicle", VIN="ABC123")
    _rel("CUST-1", "VEH-1", "OWNS")

    out = queries.ask_question("show vehicles for zorptastic")

    assert out["type"] == "vehicle"
    assert [v.id for v in out["results"]] == ["VEH-1"]


def test_ask_question_service_branch_returns_authorized_service_records():
    _entity("CUST-1", "Customer", Name="Zorptastic")
    _entity("SRV-1", "ServiceRecord")
    _rel("CUST-1", "SRV-1", "AUTHORIZED")

    out = queries.ask_question("show service records for zorptastic")

    assert out["type"] == "service"
    assert [s.id for s in out["results"]] == ["SRV-1"]


def test_ask_question_falls_back_to_plain_search():
    _entity("CUST-1", "Customer", Name="Zorptastic")

    out = queries.ask_question("zorptastic")

    assert out["type"] == "search"
    assert [e.id for e in out["results"]] == ["CUST-1"]
