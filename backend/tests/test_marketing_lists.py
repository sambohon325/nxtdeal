"""
Tests for core/marketing_lists.py -- the Marketing Lists engine added in session 82
(Sam: "under lists we need to be able to click on the list names and have them show as
a list of names ... 25 individuals, with a page up and down also adjustable by 25, 50,
100"). This is the first committed regression coverage for that module, added per
BUILD_QUEUE.md's standing "convert the loose test_*.py scripts to a real backend/tests/
pytest suite as each module gets touched" rule.

The module is load-bearing marketing infrastructure: a MarketingList is a curated,
editable snapshot of real Customer/Lead ids that campaigns target, and both
core/smart_audiences.py ("Save as List") and core/dealership_events.py (an event's
invite audience) build directly on it. It had zero committed coverage through this run
despite carrying real logic worth locking: create-time defaults, build_list_from_pool's
[m.id for m in members] materialization + "pool:<key>" source tag, update_list's
_EDITABLE_FIELDS allowlist, add_members' CUSTOMER/LEAD-only + dedupe filtering,
remove_members, delete_list's archive-not-hard-delete convention, list_lists filtering +
updated_at/id reverse sort, the real server-side pagination math in get_list_members
(page/page_size clamping, total_pages ceil, entity_type_filter, missing-id skip), and the
per-entity-type _serialize_member shapes.

Everything seeds directly into the ledger and stubs save_graph, so it's deterministic,
seed-independent, and never touches the real graph.json -- same precautions
tests/test_email_templates.py / tests/test_appointments.py document. It also imports only
the ledger chain (not the FUSE-truncated *_menu/api.app modules), so it runs green in the
sandbox. Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

import pytest

from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.entity_types import CUSTOMER, LEAD, MARKETING_LIST, VEHICLE

from core import marketing_lists


# --------------------------------------------------------------------------
# fixtures / helpers
# --------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def fresh_singletons():
    """Reset the ledger + the id counters before/after every test. ledger.reset()
    clears entities but does NOT reset id_generator counters, so ids would otherwise
    leak across tests (same rule tests/test_email_templates.py documents)."""

    def _reset():
        ledger.reset()
        for prefix in id_generator.counters:
            id_generator.counters[prefix] = 0

    _reset()
    yield
    _reset()


@pytest.fixture(autouse=True)
def no_real_disk_writes(monkeypatch):
    """marketing_lists.py does `from core.storage import save_graph`, so patch the
    imported reference in its namespace -- otherwise every create/update would clobber
    the real graph.json (the conftest temp-dir isolation is belt-and-suspenders on top
    of this)."""

    monkeypatch.setattr(marketing_lists, "save_graph", lambda *a, **k: None)


def _seed_customer(first="Jane", last="Doe", phone="555-0100", email="jane@x.com"):
    cid = id_generator.generate("CUST")
    e = Entity(
        id=cid,
        entity_type=CUSTOMER,
        attributes={"FirstName": first, "LastName": last, "Phone": phone, "Email": email},
    )
    ledger.add_entity(e)
    return e


def _seed_lead(lead_id="L-99", source="Web", state="new"):
    lid = id_generator.generate("LEAD")
    e = Entity(
        id=lid,
        entity_type=LEAD,
        attributes={"LeadID": lead_id, "Source": source, "PipelineState": state},
    )
    ledger.add_entity(e)
    return e


def _seed_vehicle():
    vid = id_generator.generate("VEH")
    e = Entity(id=vid, entity_type=VEHICLE, attributes={"Make": "Ford"})
    ledger.add_entity(e)
    return e


# --------------------------------------------------------------------------
# create_list
# --------------------------------------------------------------------------


def test_create_list_defaults():
    lst = marketing_lists.create_list("Spring Blast", "EMP-1")

    assert lst.entity_type == MARKETING_LIST
    assert lst.id.startswith("LIST-")
    assert lst.attributes["name"] == "Spring Blast"
    assert lst.attributes["description"] == ""
    assert lst.attributes["member_ids"] == []
    assert lst.attributes["source"] == "manual"
    assert lst.attributes["created_by"] == "EMP-1"
    assert lst.attributes["created_at"]
    assert lst.attributes["updated_at"]


def test_create_list_keeps_description_and_persists_to_ledger():
    lst = marketing_lists.create_list("VIPs", "EMP-2", description="High spenders")

    assert lst.attributes["description"] == "High spenders"
    # actually landed in the ledger, retrievable by id
    assert ledger.get_entity(lst.id) is lst


def test_create_list_none_description_coerced_to_empty():
    lst = marketing_lists.create_list("NoDesc", "EMP-1", description=None)
    assert lst.attributes["description"] == ""


# --------------------------------------------------------------------------
# build_list_from_pool
# --------------------------------------------------------------------------


def test_build_list_from_pool_materializes_member_ids(monkeypatch):
    c1 = _seed_customer()
    c2 = _seed_customer(first="Sam", last="Smith")
    monkeypatch.setattr(marketing_lists, "build_audience", lambda key, params: [c1, c2])

    lst = marketing_lists.build_list_from_pool("Retention", "EMP-1", "retention", {})

    assert lst.attributes["member_ids"] == [c1.id, c2.id]
    assert lst.attributes["source"] == "pool:retention"
    assert lst.attributes["name"] == "Retention"


def test_build_list_from_pool_unknown_key_is_empty():
    # real build_audience returns [] for an unrecognized campaign_type_key
    lst = marketing_lists.build_list_from_pool("Empty", "EMP-1", "no_such_pool", {})

    assert lst.attributes["member_ids"] == []
    assert lst.attributes["source"] == "pool:no_such_pool"


def test_build_list_from_pool_none_params_ok(monkeypatch):
    monkeypatch.setattr(marketing_lists, "build_audience", lambda key, params: [])
    lst = marketing_lists.build_list_from_pool("P", "EMP-1", "retention", None)
    assert lst.attributes["member_ids"] == []


# --------------------------------------------------------------------------
# get_list
# --------------------------------------------------------------------------


def test_get_list_returns_marketing_list():
    lst = marketing_lists.create_list("A", "EMP-1")
    assert marketing_lists.get_list(lst.id) is lst


def test_get_list_missing_returns_none():
    assert marketing_lists.get_list("LIST-99999") is None


def test_get_list_wrong_type_returns_none():
    cust = _seed_customer()
    assert marketing_lists.get_list(cust.id) is None


# --------------------------------------------------------------------------
# update_list
# --------------------------------------------------------------------------


def test_update_list_edits_name_and_description():
    lst = marketing_lists.create_list("Old", "EMP-1")
    out = marketing_lists.update_list(lst.id, {"name": "New", "description": "d"})

    assert out.attributes["name"] == "New"
    assert out.attributes["description"] == "d"


def test_update_list_ignores_non_editable_fields():
    lst = marketing_lists.create_list("Keep", "EMP-1")
    original_source = lst.attributes["source"]
    original_creator = lst.attributes["created_by"]

    marketing_lists.update_list(
        lst.id,
        {"source": "hacked", "created_by": "EMP-9", "member_ids": ["X"], "id": "LIST-0"},
    )

    assert lst.attributes["source"] == original_source
    assert lst.attributes["created_by"] == original_creator
    assert lst.attributes["member_ids"] == []
    assert lst.id != "LIST-0"


def test_update_list_missing_returns_none():
    assert marketing_lists.update_list("LIST-404", {"name": "x"}) is None


def test_update_list_none_patch_ok():
    lst = marketing_lists.create_list("Same", "EMP-1")
    out = marketing_lists.update_list(lst.id, None)
    assert out.attributes["name"] == "Same"


# --------------------------------------------------------------------------
# add_members
# --------------------------------------------------------------------------


def test_add_members_adds_customers_and_leads():
    lst = marketing_lists.create_list("L", "EMP-1")
    c = _seed_customer()
    ld = _seed_lead()

    res = marketing_lists.add_members(lst.id, [c.id, ld.id])

    assert res["added"] == [c.id, ld.id]
    assert res["list"].attributes["member_ids"] == [c.id, ld.id]


def test_add_members_dedupes():
    lst = marketing_lists.create_list("L", "EMP-1")
    c = _seed_customer()
    marketing_lists.add_members(lst.id, [c.id])

    res = marketing_lists.add_members(lst.id, [c.id])

    assert res["added"] == []
    assert res["list"].attributes["member_ids"] == [c.id]


def test_add_members_skips_non_customer_lead_and_unknown_ids():
    lst = marketing_lists.create_list("L", "EMP-1")
    veh = _seed_vehicle()
    c = _seed_customer()

    res = marketing_lists.add_members(lst.id, [veh.id, "CUST-99999", c.id])

    assert res["added"] == [c.id]
    assert res["list"].attributes["member_ids"] == [c.id]


def test_add_members_missing_list_returns_none():
    assert marketing_lists.add_members("LIST-404", ["CUST-1"]) is None


def test_add_members_none_ids_ok():
    lst = marketing_lists.create_list("L", "EMP-1")
    res = marketing_lists.add_members(lst.id, None)
    assert res["added"] == []
    assert res["list"].attributes["member_ids"] == []


# --------------------------------------------------------------------------
# remove_members
# --------------------------------------------------------------------------


def test_remove_members_removes_given_keeps_rest():
    lst = marketing_lists.create_list("L", "EMP-1")
    c1 = _seed_customer()
    c2 = _seed_customer(first="Two")
    marketing_lists.add_members(lst.id, [c1.id, c2.id])

    out = marketing_lists.remove_members(lst.id, [c1.id])

    assert out.attributes["member_ids"] == [c2.id]


def test_remove_members_unknown_id_is_noop():
    lst = marketing_lists.create_list("L", "EMP-1")
    c = _seed_customer()
    marketing_lists.add_members(lst.id, [c.id])

    out = marketing_lists.remove_members(lst.id, ["CUST-99999"])

    assert out.attributes["member_ids"] == [c.id]


def test_remove_members_missing_list_returns_none():
    assert marketing_lists.remove_members("LIST-404", ["CUST-1"]) is None


def test_remove_members_none_ids_ok():
    lst = marketing_lists.create_list("L", "EMP-1")
    c = _seed_customer()
    marketing_lists.add_members(lst.id, [c.id])
    out = marketing_lists.remove_members(lst.id, None)
    assert out.attributes["member_ids"] == [c.id]


# --------------------------------------------------------------------------
# delete_list (archive, not hard delete)
# --------------------------------------------------------------------------


def test_delete_list_archives():
    lst = marketing_lists.create_list("Gone", "EMP-1")
    out = marketing_lists.delete_list(lst.id)

    assert out.attributes["archived"] is True
    # still present in the ledger -- append-only convention
    assert ledger.get_entity(lst.id) is lst


def test_delete_list_missing_returns_none():
    assert marketing_lists.delete_list("LIST-404") is None


# --------------------------------------------------------------------------
# list_lists
# --------------------------------------------------------------------------


def test_list_lists_excludes_archived_by_default():
    a = marketing_lists.create_list("A", "EMP-1")
    marketing_lists.create_list("B", "EMP-1")
    marketing_lists.delete_list(a.id)

    names = [l.attributes["name"] for l in marketing_lists.list_lists()]

    assert "A" not in names
    assert "B" in names


def test_list_lists_include_archived():
    a = marketing_lists.create_list("A", "EMP-1")
    marketing_lists.delete_list(a.id)

    names = [l.attributes["name"] for l in marketing_lists.list_lists(include_archived=True)]

    assert "A" in names


def test_list_lists_filters_by_creator():
    marketing_lists.create_list("Mine", "EMP-1")
    marketing_lists.create_list("Theirs", "EMP-2")

    names = [l.attributes["name"] for l in marketing_lists.list_lists(created_by="EMP-1")]

    assert names == ["Mine"]


def test_list_lists_sorted_by_updated_at_desc():
    a = marketing_lists.create_list("A", "EMP-1")
    b = marketing_lists.create_list("B", "EMP-1")
    c = marketing_lists.create_list("C", "EMP-1")
    # force a deterministic recency order (create_at timestamps can tie in the same tick)
    a.attributes["updated_at"] = "2026-01-01T00:00:00+00:00"
    b.attributes["updated_at"] = "2026-03-01T00:00:00+00:00"
    c.attributes["updated_at"] = "2026-02-01T00:00:00+00:00"

    names = [l.attributes["name"] for l in marketing_lists.list_lists()]

    assert names == ["B", "C", "A"]


# --------------------------------------------------------------------------
# get_list_members (pagination + serialization)
# --------------------------------------------------------------------------


def _list_with_n_customers(n):
    lst = marketing_lists.create_list("Big", "EMP-1")
    ids = []
    for i in range(n):
        c = _seed_customer(first=f"C{i}")
        ids.append(c.id)
    marketing_lists.add_members(lst.id, ids)
    return lst, ids


def test_get_list_members_default_page_and_size():
    lst, ids = _list_with_n_customers(60)

    out = marketing_lists.get_list_members(lst.id)

    assert out["total"] == 60
    assert out["page"] == 1
    assert out["page_size"] == 25
    assert out["total_pages"] == 3
    assert len(out["members"]) == 25
    assert out["members"][0]["id"] == ids[0]


def test_get_list_members_second_page():
    lst, ids = _list_with_n_customers(60)

    out = marketing_lists.get_list_members(lst.id, page=2, page_size=25)

    assert out["page"] == 2
    assert len(out["members"]) == 25
    assert out["members"][0]["id"] == ids[25]


def test_get_list_members_last_partial_page():
    lst, ids = _list_with_n_customers(60)

    out = marketing_lists.get_list_members(lst.id, page=3, page_size=25)

    assert len(out["members"]) == 10
    assert out["members"][-1]["id"] == ids[-1]


def test_get_list_members_page_size_options():
    lst, _ = _list_with_n_customers(120)

    for size, expected_pages in ((25, 5), (50, 3), (100, 2)):
        out = marketing_lists.get_list_members(lst.id, page=1, page_size=size)
        assert out["page_size"] == size
        assert out["total_pages"] == expected_pages


def test_get_list_members_page_size_capped_at_200():
    lst, _ = _list_with_n_customers(3)
    out = marketing_lists.get_list_members(lst.id, page_size=9999)
    assert out["page_size"] == 200


def test_get_list_members_page_size_floor_and_page_floor():
    lst, _ = _list_with_n_customers(3)

    out = marketing_lists.get_list_members(lst.id, page=0, page_size=0)

    assert out["page"] == 1
    assert out["page_size"] == 25


def test_get_list_members_skips_missing_member_ids():
    lst = marketing_lists.create_list("L", "EMP-1")
    c = _seed_customer()
    # inject a dangling id directly onto the membership array
    lst.attributes["member_ids"] = [c.id, "CUST-DELETED"]

    out = marketing_lists.get_list_members(lst.id)

    assert out["total"] == 1
    assert [m["id"] for m in out["members"]] == [c.id]


def test_get_list_members_entity_type_filter():
    lst = marketing_lists.create_list("L", "EMP-1")
    c = _seed_customer()
    ld = _seed_lead()
    marketing_lists.add_members(lst.id, [c.id, ld.id])

    out = marketing_lists.get_list_members(lst.id, entity_type_filter=LEAD)

    assert out["total"] == 1
    assert out["members"][0]["entity_type"] == LEAD


def test_get_list_members_missing_list_returns_none():
    assert marketing_lists.get_list_members("LIST-404") is None


def test_serialize_customer_shape():
    lst = marketing_lists.create_list("L", "EMP-1")
    c = _seed_customer(first="Ann", last="Lee", phone="555-1", email="ann@x.com")
    marketing_lists.add_members(lst.id, [c.id])

    m = marketing_lists.get_list_members(lst.id)["members"][0]

    assert m == {
        "id": c.id,
        "entity_type": CUSTOMER,
        "name": "Ann Lee",
        "phone": "555-1",
        "email": "ann@x.com",
    }


def test_serialize_customer_blank_name_falls_back_to_id():
    lst = marketing_lists.create_list("L", "EMP-1")
    c = _seed_customer(first="", last="")
    marketing_lists.add_members(lst.id, [c.id])

    m = marketing_lists.get_list_members(lst.id)["members"][0]

    assert m["name"] == c.id


def test_serialize_lead_shape():
    lst = marketing_lists.create_list("L", "EMP-1")
    ld = _seed_lead(lead_id="LD-7", source="Event", state="working")
    marketing_lists.add_members(lst.id, [ld.id])

    m = marketing_lists.get_list_members(lst.id)["members"][0]

    assert m == {
        "id": ld.id,
        "entity_type": LEAD,
        "name": "LD-7",
        "phone": None,
        "email": None,
        "source": "Event",
        "pipeline_state": "working",
    }


def test_lead_member_shows_canonical_contact_details_without_private_fields():
    from core.marketing_lists import _serialize_member
    from core.entities import Entity
    row = _serialize_member(Entity("L-QA", "Lead", {"FirstName":"QA", "LastName":"Recipient", "Email":"qa@example.test", "Phone":"5550100", "SSN":"private"}))
    assert row['name']=='QA Recipient'
    assert row['email']=='qa@example.test' and row['phone']=='5550100'
    assert 'SSN' not in row
