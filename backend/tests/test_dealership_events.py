"""
Tests for core/dealership_events.py -- the NXTDeal-Bumper half of the Events dash
(session 84; Sam: "build out the event dash ... has to tightly integrate into the
CRM."). This is the first committed regression coverage for that module, added per
BUILD_QUEUE.md's standing "convert the loose test_*.py scripts to a real
backend/tests/ pytest suite as each module gets touched" rule, and it continues the
Marketing-engine test arc (email_templates -> marketing_lists -> this).

A DealershipEvent is a real scheduled event whose invite audience is optionally a real
core/marketing_lists.py MarketingList: publish_event() snapshots that list's current
membership into real EventRSVP(status="invited") records at publish time (the same
"snapshot at save time, not a live query" rule marketing_lists.build_list_from_pool()
established). The CRM tie-in that matters is promote_rsvp_to_lead(), which turns a
post-event attendee into a real new Lead (source="Event"), tied back to the originating
Customer via a real GENERATED_LEAD relationship when one exists.

The module carried real, untested logic worth locking: the event lifecycle state
machine (draft -> scheduled -> live -> completed, plus cancel from draft/scheduled and
every illegal-transition guard), create_event's event_type/linked_list validation +
defaults, update_event's _EVENT_EDITABLE_FIELDS allowlist + edit-only-while-draft/
scheduled gate, publish_event's list-membership snapshot into invited RSVPs (incl.
skipping members that aren't a live Customer/Lead), create_rsvp's customer_id/lead_id
existence-and-type coercion + invited-vs-confirmed status rule, update_rsvp_status's
allowlist, list_events/list_event_rsvps filtering + sort, get_event_detail's status
rollup, and promote_rsvp_to_lead's Lead creation + GENERATED_LEAD wiring + already-
promoted guard.

Everything seeds directly into the ledger and stubs save_graph in every mutating
module's namespace (dealership_events + lead_intake), so it's deterministic,
seed-independent, and never touches the real graph.json -- same precautions
tests/test_marketing_lists.py / tests/test_email_templates.py document. It imports only
the ledger chain (not the FUSE-truncated *_menu/api.app modules), so it runs green in
the sandbox. Run from backend/ with `pytest`.
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
from core.entity_types import CUSTOMER, LEAD, MARKETING_LIST, VEHICLE, EVENT, EVENT_RSVP
from core.relationship_types import GENERATED_LEAD

from core import dealership_events
from core import lead_intake


# --------------------------------------------------------------------------
# fixtures / helpers
# --------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def fresh_singletons():
    """Reset the ledger + id counters before/after every test. ledger.reset() clears
    entities but does NOT reset id_generator counters, so ids would otherwise leak
    across tests (same rule tests/test_marketing_lists.py documents)."""

    def _reset():
        ledger.reset()
        for prefix in id_generator.counters:
            id_generator.counters[prefix] = 0

    _reset()
    yield
    _reset()


@pytest.fixture(autouse=True)
def no_real_disk_writes(monkeypatch):
    """Both dealership_events.py and lead_intake.py (reached via promote_rsvp_to_lead's
    create_lead) do `from core.storage import save_graph`, so patch the imported
    reference in each namespace -- otherwise a mutating call would clobber the real
    graph.json (the conftest temp-dir isolation is belt-and-suspenders on top of this)."""

    monkeypatch.setattr(dealership_events, "save_graph", lambda *a, **k: None)
    monkeypatch.setattr(lead_intake, "save_graph", lambda *a, **k: None)


def _seed_customer(first="Jane", last="Doe", phone="555-0100", email="jane@x.com"):
    cid = id_generator.generate("CUST")
    e = Entity(
        id=cid,
        entity_type=CUSTOMER,
        attributes={"FirstName": first, "LastName": last, "Phone": phone, "Email": email},
    )
    ledger.add_entity(e)
    return e


def _seed_lead(first="Lee", last="Prospect", phone="555-0200", email="lee@x.com"):
    lid = id_generator.generate("LEAD")
    e = Entity(
        id=lid,
        entity_type=LEAD,
        attributes={"LeadID": lid, "FirstName": first, "LastName": last, "Phone": phone, "Email": email},
    )
    ledger.add_entity(e)
    return e


def _seed_vehicle():
    vid = id_generator.generate("VEH")
    e = Entity(id=vid, entity_type=VEHICLE, attributes={"VIN": "1HG"})
    ledger.add_entity(e)
    return e


def _seed_list(member_ids, name="Invite List"):
    lid = id_generator.generate("LIST")
    e = Entity(
        id=lid,
        entity_type=MARKETING_LIST,
        attributes={"name": name, "member_ids": list(member_ids), "source": "manual"},
    )
    ledger.add_entity(e)
    return e


def _make_event(created_by="EMP-1", name="Spring Test Drive", event_type="test_drive",
                start_time="2026-08-01T10:00:00+00:00", **kw):
    return dealership_events.create_event(created_by, name, event_type, start_time, **kw)


# --------------------------------------------------------------------------
# list_event_types
# --------------------------------------------------------------------------


def test_list_event_types_returns_six_and_is_a_copy():
    types = dealership_events.list_event_types()
    assert len(types) == 6
    keys = {t["key"] for t in types}
    assert {"test_drive", "vip_sale", "service_clinic", "community", "product_launch", "other"} == keys
    # mutating the returned list must not corrupt the module-level catalog
    types.append({"key": "bogus"})
    assert len(dealership_events.list_event_types()) == 6


# --------------------------------------------------------------------------
# create_event
# --------------------------------------------------------------------------


def test_create_event_happy_path_defaults():
    ev = _make_event()
    assert isinstance(ev, Entity)
    assert ev.entity_type == EVENT
    assert ev.attributes["status"] == "draft"
    assert ev.attributes["event_type"] == "test_drive"
    assert ev.attributes["created_by"] == "EMP-1"
    assert ev.attributes["published_at"] is None
    assert ev.attributes["completed_at"] is None
    assert ev.attributes["cancelled_at"] is None
    assert ev.attributes["created_at"] and ev.attributes["updated_at"]


def test_create_event_blank_name_and_optional_defaults():
    ev = dealership_events.create_event("EMP-1", "", "vip_sale", "2026-08-01T10:00:00+00:00")
    assert ev.attributes["name"] == "New Event"
    assert ev.attributes["description"] == ""
    assert ev.attributes["location"] == ""
    assert ev.attributes["capacity"] is None
    assert ev.attributes["linked_list_id"] is None


def test_create_event_unknown_type_rejected():
    out = dealership_events.create_event("EMP-1", "X", "not_a_type", "2026-08-01T10:00:00+00:00")
    assert isinstance(out, dict) and "error" in out
    # nothing persisted
    assert dealership_events.list_events() == []


def test_create_event_missing_linked_list_rejected():
    out = _make_event(linked_list_id="LIST-99999")
    assert isinstance(out, dict) and "error" in out


def test_create_event_valid_linked_list_accepted():
    lst = _seed_list([])
    ev = _make_event(linked_list_id=lst.id)
    assert isinstance(ev, Entity)
    assert ev.attributes["linked_list_id"] == lst.id


# --------------------------------------------------------------------------
# get_event
# --------------------------------------------------------------------------


def test_get_event_hit_miss_and_wrong_type():
    ev = _make_event()
    assert dealership_events.get_event(ev.id) is ev
    assert dealership_events.get_event("EVT-99999") is None
    cust = _seed_customer()
    assert dealership_events.get_event(cust.id) is None


# --------------------------------------------------------------------------
# update_event
# --------------------------------------------------------------------------


def test_update_event_editable_fields_and_allowlist():
    ev = _make_event()
    before_updated = ev.attributes["updated_at"]
    out = dealership_events.update_event(ev.id, {
        "name": "Renamed",
        "location": "Main Lot",
        "capacity": 50,
        "status": "completed",       # not editable -- must be ignored
        "created_by": "HACKER",      # not editable -- must be ignored
    })
    assert out.attributes["name"] == "Renamed"
    assert out.attributes["location"] == "Main Lot"
    assert out.attributes["capacity"] == 50
    assert out.attributes["status"] == "draft"
    assert out.attributes["created_by"] == "EMP-1"
    assert out.attributes["updated_at"] >= before_updated


def test_update_event_missing_returns_none():
    assert dealership_events.update_event("EVT-99999", {"name": "x"}) is None


def test_update_event_none_patch_is_safe():
    ev = _make_event()
    out = dealership_events.update_event(ev.id, None)
    assert out.attributes["name"] == "Spring Test Drive"


def test_update_event_blocked_once_past_scheduled():
    ev = _make_event()
    dealership_events.publish_event(ev.id)   # -> scheduled (still editable)
    dealership_events.start_event(ev.id)     # -> live (locked)
    out = dealership_events.update_event(ev.id, {"name": "Nope"})
    assert isinstance(out, dict) and "error" in out
    assert dealership_events.get_event(ev.id).attributes["name"] == "Spring Test Drive"


def test_update_event_allowed_while_scheduled():
    ev = _make_event()
    dealership_events.publish_event(ev.id)
    out = dealership_events.update_event(ev.id, {"location": "New Venue"})
    assert out.attributes["location"] == "New Venue"


# --------------------------------------------------------------------------
# publish_event
# --------------------------------------------------------------------------


def test_publish_event_no_list_zero_invites():
    ev = _make_event()
    out = dealership_events.publish_event(ev.id)
    assert out["invited_count"] == 0
    assert out["event"].attributes["status"] == "scheduled"
    assert out["event"].attributes["published_at"] is not None


def test_publish_event_snapshots_list_membership_into_invited_rsvps():
    cust = _seed_customer(first="Ann", last="Buyer")
    lead = _seed_lead(first="Bob", last="Maybe")
    lst = _seed_list([cust.id, lead.id])
    ev = _make_event(linked_list_id=lst.id)
    out = dealership_events.publish_event(ev.id)
    assert out["invited_count"] == 2
    rsvps = dealership_events.list_event_rsvps(ev.id)
    assert len(rsvps) == 2
    assert all(r.attributes["status"] == "invited" for r in rsvps)
    assert all(r.attributes["source"] == "invited" for r in rsvps)
    # customer- and lead-linked RSVPs both present
    linked_customers = {r.attributes["customer_id"] for r in rsvps if r.attributes["customer_id"]}
    linked_leads = {r.attributes["lead_id"] for r in rsvps if r.attributes["lead_id"]}
    assert linked_customers == {cust.id}
    assert linked_leads == {lead.id}


def test_publish_event_skips_non_customer_lead_and_missing_members():
    cust = _seed_customer()
    veh = _seed_vehicle()
    lst = _seed_list([cust.id, veh.id, "GONE-123"])
    ev = _make_event(linked_list_id=lst.id)
    out = dealership_events.publish_event(ev.id)
    # only the real Customer becomes an invite; vehicle + dangling id skipped
    assert out["invited_count"] == 1


def test_publish_event_wrong_status_and_missing():
    ev = _make_event()
    dealership_events.publish_event(ev.id)
    again = dealership_events.publish_event(ev.id)
    assert isinstance(again, dict) and "error" in again
    assert "error" in dealership_events.publish_event("EVT-99999")


# --------------------------------------------------------------------------
# start / complete / cancel lifecycle
# --------------------------------------------------------------------------


def test_start_event_transitions_and_guards():
    ev = _make_event()
    assert "error" in dealership_events.start_event(ev.id)        # still draft
    dealership_events.publish_event(ev.id)
    started = dealership_events.start_event(ev.id)
    assert started.attributes["status"] == "live"
    assert "error" in dealership_events.start_event("EVT-99999")


def test_complete_event_from_scheduled_and_live():
    ev1 = _make_event()
    dealership_events.publish_event(ev1.id)
    done1 = dealership_events.complete_event(ev1.id)
    assert done1.attributes["status"] == "completed"
    assert done1.attributes["completed_at"] is not None

    ev2 = _make_event()
    dealership_events.publish_event(ev2.id)
    dealership_events.start_event(ev2.id)
    done2 = dealership_events.complete_event(ev2.id)
    assert done2.attributes["status"] == "completed"


def test_complete_event_rejected_from_draft():
    ev = _make_event()
    assert "error" in dealership_events.complete_event(ev.id)
    assert "error" in dealership_events.complete_event("EVT-99999")


def test_cancel_event_from_draft_and_scheduled():
    ev1 = _make_event()
    c1 = dealership_events.cancel_event(ev1.id)
    assert c1.attributes["status"] == "cancelled"
    assert c1.attributes["cancelled_at"] is not None

    ev2 = _make_event()
    dealership_events.publish_event(ev2.id)
    c2 = dealership_events.cancel_event(ev2.id)
    assert c2.attributes["status"] == "cancelled"


def test_cancel_event_rejected_once_live_or_completed():
    ev = _make_event()
    dealership_events.publish_event(ev.id)
    dealership_events.start_event(ev.id)
    assert "error" in dealership_events.cancel_event(ev.id)
    assert "error" in dealership_events.cancel_event("EVT-99999")


# --------------------------------------------------------------------------
# list_events
# --------------------------------------------------------------------------


def test_list_events_filters_and_sort():
    a = _make_event(name="A", event_type="test_drive", start_time="2026-08-01T10:00:00+00:00", created_by="EMP-1")
    b = _make_event(name="B", event_type="vip_sale", start_time="2026-09-01T10:00:00+00:00", created_by="EMP-2")
    c = _make_event(name="C", event_type="vip_sale", start_time="2026-07-01T10:00:00+00:00", created_by="EMP-1")

    # default: newest start_time first
    ordered = [e.attributes["name"] for e in dealership_events.list_events()]
    assert ordered == ["B", "A", "C"]

    assert {e.id for e in dealership_events.list_events(event_type="vip_sale")} == {b.id, c.id}
    assert {e.id for e in dealership_events.list_events(created_by="EMP-1")} == {a.id, c.id}

    dealership_events.publish_event(a.id)
    assert {e.id for e in dealership_events.list_events(status="scheduled")} == {a.id}


# --------------------------------------------------------------------------
# create_rsvp
# --------------------------------------------------------------------------


def test_create_rsvp_walk_in_defaults_confirmed():
    ev = _make_event()
    r = dealership_events.create_rsvp(ev.id, "Walk In Guy")
    assert r.entity_type == EVENT_RSVP
    assert r.attributes["status"] == "confirmed"
    assert r.attributes["source"] == "walk_in"
    assert r.attributes["promoted_to_lead_id"] is None


def test_create_rsvp_invited_source_sets_invited_status():
    ev = _make_event()
    r = dealership_events.create_rsvp(ev.id, "Invitee", source="invited")
    assert r.attributes["status"] == "invited"


def test_create_rsvp_blank_name_defaults_to_guest():
    ev = _make_event()
    r = dealership_events.create_rsvp(ev.id, "")
    assert r.attributes["name"] == "Guest"


def test_create_rsvp_coerces_bad_customer_and_lead_ids():
    ev = _make_event()
    veh = _seed_vehicle()
    r = dealership_events.create_rsvp(ev.id, "Bad Refs", customer_id="NOPE", lead_id=veh.id)
    assert r.attributes["customer_id"] is None
    assert r.attributes["lead_id"] is None


def test_create_rsvp_keeps_valid_customer_and_lead_ids():
    ev = _make_event()
    cust = _seed_customer()
    lead = _seed_lead()
    r1 = dealership_events.create_rsvp(ev.id, "C", customer_id=cust.id)
    r2 = dealership_events.create_rsvp(ev.id, "L", lead_id=lead.id)
    assert r1.attributes["customer_id"] == cust.id
    assert r2.attributes["lead_id"] == lead.id


def test_create_rsvp_missing_event_errors():
    out = dealership_events.create_rsvp("EVT-99999", "Nobody")
    assert isinstance(out, dict) and "error" in out


# --------------------------------------------------------------------------
# get_rsvp / update_rsvp_status
# --------------------------------------------------------------------------


def test_get_rsvp_hit_miss_wrong_type():
    ev = _make_event()
    r = dealership_events.create_rsvp(ev.id, "G")
    assert dealership_events.get_rsvp(r.id) is r
    assert dealership_events.get_rsvp("RSVP-99999") is None
    assert dealership_events.get_rsvp(ev.id) is None


def test_update_rsvp_status_valid_and_invalid():
    ev = _make_event()
    r = dealership_events.create_rsvp(ev.id, "G")
    updated = dealership_events.update_rsvp_status(r.id, "attended")
    assert updated.attributes["status"] == "attended"
    assert "error" in dealership_events.update_rsvp_status(r.id, "bogus")
    assert "error" in dealership_events.update_rsvp_status("RSVP-99999", "attended")


# --------------------------------------------------------------------------
# list_event_rsvps / get_event_detail
# --------------------------------------------------------------------------


def test_list_event_rsvps_scoped_and_filtered():
    ev1 = _make_event(name="E1")
    ev2 = _make_event(name="E2")
    dealership_events.create_rsvp(ev1.id, "A")
    b = dealership_events.create_rsvp(ev1.id, "B")
    dealership_events.create_rsvp(ev2.id, "C")
    dealership_events.update_rsvp_status(b.id, "attended")

    assert len(dealership_events.list_event_rsvps(ev1.id)) == 2
    assert len(dealership_events.list_event_rsvps(ev2.id)) == 1
    attended = dealership_events.list_event_rsvps(ev1.id, status="attended")
    assert [r.id for r in attended] == [b.id]


def test_get_event_detail_rolls_up_status_counts():
    ev = _make_event()
    r1 = dealership_events.create_rsvp(ev.id, "A")   # confirmed
    dealership_events.create_rsvp(ev.id, "B")        # confirmed
    dealership_events.update_rsvp_status(r1.id, "attended")

    detail = dealership_events.get_event_detail(ev.id)
    assert detail["event"]["id"] == ev.id
    assert detail["rsvp_summary"] == {"confirmed": 1, "attended": 1}
    assert len(detail["rsvps"]) == 2


def test_get_event_detail_missing_errors():
    assert "error" in dealership_events.get_event_detail("EVT-99999")


# --------------------------------------------------------------------------
# promote_rsvp_to_lead -- the CRM tie-in
# --------------------------------------------------------------------------


def test_promote_rsvp_creates_event_sourced_lead():
    ev = _make_event()
    r = dealership_events.create_rsvp(ev.id, "Chris Walker", phone="555-9", email="c@x.com")
    out = dealership_events.promote_rsvp_to_lead(r.id, "EMP-1")
    lead = out["lead"]
    assert lead.entity_type == LEAD
    assert lead.attributes["Source"] == "Event"
    assert lead.attributes["FirstName"] == "Chris"
    assert lead.attributes["LastName"] == "Walker"
    # the RSVP is stamped so it can't be double-promoted
    assert out["rsvp"].attributes["promoted_to_lead_id"] == lead.id


def test_promote_rsvp_from_customer_wires_generated_lead_relationship():
    ev = _make_event()
    cust = _seed_customer(first="Dana", last="Owner")
    r = dealership_events.create_rsvp(ev.id, "ignored name", customer_id=cust.id)
    out = dealership_events.promote_rsvp_to_lead(r.id, "EMP-1")
    lead = out["lead"]
    # customer's own name wins over the RSVP freeform name
    assert lead.attributes["FirstName"] == "Dana"
    assert lead.attributes["LastName"] == "Owner"
    rels = [
        rel for rel in ledger.get_relationships()
        if rel.relationship_type == GENERATED_LEAD
        and rel.source_id == cust.id
        and rel.target_id == lead.id
    ]
    assert len(rels) == 1


def test_promote_rsvp_already_promoted_rejected():
    ev = _make_event()
    r = dealership_events.create_rsvp(ev.id, "Once Only")
    dealership_events.promote_rsvp_to_lead(r.id, "EMP-1")
    again = dealership_events.promote_rsvp_to_lead(r.id, "EMP-1")
    assert isinstance(again, dict) and "error" in again


def test_promote_rsvp_missing_errors():
    assert "error" in dealership_events.promote_rsvp_to_lead("RSVP-99999", "EMP-1")


def test_promote_rsvp_single_word_name_splits_cleanly():
    ev = _make_event()
    r = dealership_events.create_rsvp(ev.id, "Cher")
    out = dealership_events.promote_rsvp_to_lead(r.id, "EMP-1")
    assert out["lead"].attributes["FirstName"] == "Cher"
    assert out["lead"].attributes["LastName"] == ""
