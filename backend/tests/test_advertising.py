"""
Tests for core/advertising.py + core/advertising_api.py -- the Advertising dash added
in session 83 (Meta/Google ad campaigns with inventory integration, 2026-07-16). This
is the first committed regression coverage for that module, added per BUILD_QUEUE.md's
standing "convert the loose test_*.py scripts to a real backend/tests/ pytest suite as
each module gets touched" rule, continuing the Marketing-engine test arc (email_templates
-> marketing_lists -> dealership_events -> smart_audiences -> this).

The module is load-bearing marketing infrastructure and had ZERO coverage: an AdCampaign
is an ordinary graph entity (core/entity_types.py's AD_CAMPAIGN, distinct from
core/campaigns.py's email/SMS Campaign) tied to the Employee who built it and, optionally,
real Vehicle entities via `linked_vehicle_ids` (id-only, resolved LIVE at read time -- the
same no-parallel-inventory-copy rule core/social_posts.py follows). "Launching" is an
honestly-labeled SIMULATED action (real status/timestamps on a real graph record, no real
ad spend), matching campaigns.activate_campaign()/social_posts.publish_post(). The module
also carried a real data-loss bug fixed 2026-07-18 (it shipped with zero save_graph()
calls, silently discarding every ad campaign on restart) -- so the persistence side is
worth pinning too.

Worth locking here:

  * the static catalogs (`list_platforms` = meta/google, `list_objectives` = the four
    objective keys) and their returned-copy safety;
  * `generate_ad_recommendation`'s three branches -- feature-flag-disabled short-circuit,
    a successful (fake) OpenAI call returning parsed JSON, and any exception falling back
    to an {"error": ...} dict -- plus the brief-defaults it sends when fields are missing;
  * `fallback_recommendation`'s plain non-AI placeholder shape (all five keys, objective
    echoed into the body);
  * `create_ad_campaign`'s validation (unknown platform/objective), draft defaults, blank
    -name fallback, `ai_generated` bool coercion, `_valid_vehicle_ids` filtering, and
    ledger persistence (save_graph fired exactly once);
  * `get_ad_campaign`'s hit/miss/wrong-type resolution;
  * `update_ad_campaign`'s `_EDITABLE_FIELDS` allowlist (status/created_by/created_at
    immutable), linked-vehicle re-validation, updated_at bump, missing/None-patch guards;
  * the full lifecycle state machine -- `launch` (draft/paused -> active, launched_at set
    once), `pause` (active -> paused), `complete` (active/paused -> completed), `cancel`
    (draft/paused -> cancelled) -- and every illegal-transition + missing-id guard;
  * `list_ad_campaigns` platform/status/creator filtering + created_at reverse sort;
  * `resolve_linked_vehicles`' live vehicle-attr projection incl. missing/non-vehicle skip;
  * the `advertising_api` ACL layer -- `_can_manage` (ADMIN/MARKETING only), the
    manage-gated launch/pause/complete, the creator-or-manager-gated update/cancel, the
    AI-recommendation error->fallback shaping, and every response's `performance_note`.

Everything seeds directly into the ledger and stubs save_graph + record_call_attempt, so
it's deterministic, seed-independent, and never touches the real graph.json or audit.json
(the conftest temp-dir isolation is belt-and-suspenders on top of this). advertising.py
does `from openai import OpenAI` at import time, so the sandbox run installs openai (import
-time only -- no key or network; the AI path is exercised through a fake client). Run from
backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

import json

import pytest

from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.entity_types import CUSTOMER, VEHICLE, AD_CAMPAIGN
from core.permissions import ADMIN, MARKETING, SALES

from core import advertising
from core import advertising_api


# --------------------------------------------------------------------------
# fixtures / helpers
# --------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def fresh_singletons():
    """Reset the ledger + id counters before/after every test. ledger.reset() clears
    entities AND relationships but does NOT reset id_generator counters, so ids would
    otherwise leak across tests (same rule tests/test_smart_audiences.py documents)."""

    def _reset():
        ledger.reset()
        for prefix in id_generator.counters:
            id_generator.counters[prefix] = 0

    _reset()
    yield
    _reset()


@pytest.fixture(autouse=True)
def no_real_side_effects(monkeypatch):
    """advertising.py does `from core.storage import save_graph` and
    `from core.ai_management import ... record_call_attempt` -- patch the imported
    references in its namespace so creating/mutating a campaign never clobbers the real
    graph.json and never writes a real audit event (the conftest temp-dir isolation is
    additional belt-and-suspenders on top of this)."""

    advertising._save_calls = 0

    def _count_save(*a, **k):
        advertising._save_calls += 1

    monkeypatch.setattr(advertising, "save_graph", _count_save)
    monkeypatch.setattr(advertising, "record_call_attempt", lambda *a, **k: None)


def _add_customer(cid=None, first="Jane", last="Doe"):
    cid = cid or id_generator.generate("CUST")
    c = Entity(id=cid, entity_type=CUSTOMER, attributes={"FirstName": first, "LastName": last})
    ledger.add_entity(c)
    return c


def _add_vehicle(vid=None, **attrs):
    vid = vid or id_generator.generate("VEH")
    v = Entity(id=vid, entity_type=VEHICLE, attributes=dict(attrs))
    ledger.add_entity(v)
    return v


def _new_draft(created_by="EMP-1", platform="meta", objective="traffic", name="Spring Sale",
               fields=None, linked_vehicle_ids=None):
    return advertising.create_ad_campaign(
        created_by, platform, objective, name, fields or {}, linked_vehicle_ids
    )


class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content):
        self.message = _FakeMessage(content)


class _FakeCompletion:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


class _FakeCompletions:
    def __init__(self, content=None, exc=None):
        self._content = content
        self._exc = exc
        self.last_kwargs = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        if self._exc is not None:
            raise self._exc
        return _FakeCompletion(self._content)


class _FakeChat:
    def __init__(self, completions):
        self.completions = completions


class _FakeClient:
    def __init__(self, content=None, exc=None):
        self.chat = _FakeChat(_FakeCompletions(content=content, exc=exc))


# --------------------------------------------------------------------------
# static catalogs
# --------------------------------------------------------------------------


def test_list_platforms_is_meta_and_google():
    assert advertising.list_platforms() == ["meta", "google"]


def test_list_platforms_returns_a_copy():
    advertising.list_platforms().append("tiktok")
    assert advertising.list_platforms() == ["meta", "google"]


def test_list_objectives_keys():
    keys = [o["key"] for o in advertising.list_objectives()]
    assert keys == ["traffic", "leads", "awareness", "inventory"]


def test_list_objectives_returns_a_copy():
    advertising.list_objectives().append({"key": "x", "name": "X"})
    assert len(advertising.list_objectives()) == 4


# --------------------------------------------------------------------------
# generate_ad_recommendation
# --------------------------------------------------------------------------


def test_generate_recommendation_disabled_short_circuits(monkeypatch):
    monkeypatch.setattr(advertising, "is_feature_enabled", lambda key: False)
    result = advertising.generate_ad_recommendation({"platform": "meta"})
    assert result["disabled"] is True
    assert "error" in result


def test_generate_recommendation_success_parses_json(monkeypatch):
    monkeypatch.setattr(advertising, "is_feature_enabled", lambda key: True)
    payload = {
        "headline": "Big Truck Event",
        "primary_text": "Come on down.",
        "description": "Trucks galore.",
        "disclaimer": "See dealer.",
        "targeting_suggestion": "25-mile radius, ages 25-64.",
    }
    fake = _FakeClient(content=json.dumps(payload))
    monkeypatch.setattr(advertising, "client", fake)
    result = advertising.generate_ad_recommendation({"platform": "google", "objective": "leads"})
    assert result == payload


def test_generate_recommendation_sends_brief_defaults(monkeypatch):
    monkeypatch.setattr(advertising, "is_feature_enabled", lambda key: True)
    fake = _FakeClient(content=json.dumps({"headline": "x"}))
    monkeypatch.setattr(advertising, "client", fake)
    advertising.generate_ad_recommendation(None)
    user_msg = fake.chat.completions.last_kwargs["messages"][1]["content"]
    # None brief -> the documented defaults are what gets sent to the model
    assert "Platform: meta" in user_msg
    assert "Objective: traffic" in user_msg
    assert "Audience: local car buyers" in user_msg
    assert "not specified" in user_msg


def test_generate_recommendation_exception_falls_back_to_error(monkeypatch):
    monkeypatch.setattr(advertising, "is_feature_enabled", lambda key: True)
    fake = _FakeClient(exc=RuntimeError("network down"))
    monkeypatch.setattr(advertising, "client", fake)
    result = advertising.generate_ad_recommendation({"platform": "meta"})
    assert "error" in result
    assert "network down" in result["error"]
    assert "disabled" not in result


# --------------------------------------------------------------------------
# fallback_recommendation
# --------------------------------------------------------------------------


def test_fallback_recommendation_shape():
    rec = advertising.fallback_recommendation({"objective": "awareness"})
    assert set(rec.keys()) == {
        "headline", "primary_text", "description", "disclaimer", "targeting_suggestion"
    }
    assert "awareness" in rec["primary_text"]


def test_fallback_recommendation_handles_none_brief():
    rec = advertising.fallback_recommendation(None)
    assert "traffic" in rec["primary_text"]  # default objective


# --------------------------------------------------------------------------
# create_ad_campaign
# --------------------------------------------------------------------------


def test_create_rejects_unknown_platform():
    result = advertising.create_ad_campaign("EMP-1", "tiktok", "traffic", "X", {})
    assert "error" in result
    assert advertising._save_calls == 0


def test_create_rejects_unknown_objective():
    result = advertising.create_ad_campaign("EMP-1", "meta", "conversions", "X", {})
    assert "error" in result
    assert advertising._save_calls == 0


def test_create_defaults_and_persists():
    ad = _new_draft(fields={"headline": "Hi", "daily_budget": 50})
    assert ad.entity_type == AD_CAMPAIGN
    assert ad.attributes["status"] == "draft"
    assert ad.attributes["platform"] == "meta"
    assert ad.attributes["headline"] == "Hi"
    assert ad.attributes["daily_budget"] == 50
    assert ad.attributes["targeting"] == {}
    assert ad.attributes["ai_generated"] is False
    assert ad.attributes["created_by"] == "EMP-1"
    assert ad.attributes["created_at"] and ad.attributes["updated_at"]
    assert ad.attributes["launched_at"] is None
    assert ad.attributes["paused_at"] is None
    assert ad.attributes["completed_at"] is None
    assert advertising._save_calls == 1
    # actually persisted into the ledger
    assert ledger.get_entity(ad.id) is ad


def test_create_blank_name_falls_back_to_platform_title():
    ad = _new_draft(name="", platform="google")
    assert ad.attributes["name"] == "New Google Campaign"


def test_create_coerces_ai_generated_to_bool():
    ad = _new_draft(fields={"ai_generated": "yes"})
    assert ad.attributes["ai_generated"] is True


def test_create_filters_linked_vehicles_to_real_vehicles():
    veh = _add_vehicle()
    cust = _add_customer()  # not a vehicle -> must be dropped
    ad = _new_draft(linked_vehicle_ids=[veh.id, cust.id, "VEH-DOESNOTEXIST"])
    assert ad.attributes["linked_vehicle_ids"] == [veh.id]


def test_create_none_linked_vehicles_is_empty_list():
    ad = _new_draft(linked_vehicle_ids=None)
    assert ad.attributes["linked_vehicle_ids"] == []


# --------------------------------------------------------------------------
# get_ad_campaign
# --------------------------------------------------------------------------


def test_get_returns_the_campaign():
    ad = _new_draft()
    assert advertising.get_ad_campaign(ad.id) is ad


def test_get_missing_returns_none():
    assert advertising.get_ad_campaign("AD-99999") is None


def test_get_wrong_type_returns_none():
    veh = _add_vehicle()
    assert advertising.get_ad_campaign(veh.id) is None


# --------------------------------------------------------------------------
# update_ad_campaign
# --------------------------------------------------------------------------


def test_update_missing_returns_none():
    assert advertising.update_ad_campaign("AD-99999", {"name": "x"}) is None


def test_update_editable_fields_apply():
    ad = _new_draft()
    before = ad.attributes["updated_at"]
    advertising.update_ad_campaign(ad.id, {"name": "Renamed", "daily_budget": 99})
    assert ad.attributes["name"] == "Renamed"
    assert ad.attributes["daily_budget"] == 99
    assert ad.attributes["updated_at"] >= before


def test_update_ignores_non_editable_fields():
    ad = _new_draft()
    advertising.update_ad_campaign(ad.id, {
        "status": "active",
        "created_by": "HACKER",
        "created_at": "1999",
        "launched_at": "1999",
    })
    assert ad.attributes["status"] == "draft"
    assert ad.attributes["created_by"] == "EMP-1"
    assert ad.attributes["created_at"] != "1999"
    assert ad.attributes["launched_at"] is None


def test_update_revalidates_linked_vehicles():
    veh = _add_vehicle()
    ad = _new_draft()
    advertising.update_ad_campaign(ad.id, {"linked_vehicle_ids": [veh.id, "VEH-NOPE"]})
    assert ad.attributes["linked_vehicle_ids"] == [veh.id]


def test_update_none_patch_is_safe():
    ad = _new_draft()
    result = advertising.update_ad_campaign(ad.id, None)
    assert result is ad


# --------------------------------------------------------------------------
# lifecycle state machine
# --------------------------------------------------------------------------


def test_launch_missing_returns_none():
    assert advertising.launch_ad_campaign("AD-99999") is None


def test_launch_draft_goes_active_and_stamps_launched_at():
    ad = _new_draft()
    advertising.launch_ad_campaign(ad.id)
    assert ad.attributes["status"] == "active"
    assert ad.attributes["launched_at"] is not None


def test_launch_from_active_is_rejected():
    ad = _new_draft()
    advertising.launch_ad_campaign(ad.id)
    result = advertising.launch_ad_campaign(ad.id)
    assert "error" in result


def test_relaunch_from_paused_preserves_original_launched_at():
    ad = _new_draft()
    advertising.launch_ad_campaign(ad.id)
    first_launch = ad.attributes["launched_at"]
    advertising.pause_ad_campaign(ad.id)
    advertising.launch_ad_campaign(ad.id)
    assert ad.attributes["status"] == "active"
    assert ad.attributes["launched_at"] == first_launch


def test_pause_missing_returns_none():
    assert advertising.pause_ad_campaign("AD-99999") is None


def test_pause_active_goes_paused():
    ad = _new_draft()
    advertising.launch_ad_campaign(ad.id)
    advertising.pause_ad_campaign(ad.id)
    assert ad.attributes["status"] == "paused"
    assert ad.attributes["paused_at"] is not None


def test_pause_draft_is_rejected():
    ad = _new_draft()
    result = advertising.pause_ad_campaign(ad.id)
    assert "error" in result


def test_complete_from_active():
    ad = _new_draft()
    advertising.launch_ad_campaign(ad.id)
    advertising.complete_ad_campaign(ad.id)
    assert ad.attributes["status"] == "completed"
    assert ad.attributes["completed_at"] is not None


def test_complete_from_paused():
    ad = _new_draft()
    advertising.launch_ad_campaign(ad.id)
    advertising.pause_ad_campaign(ad.id)
    advertising.complete_ad_campaign(ad.id)
    assert ad.attributes["status"] == "completed"


def test_complete_from_draft_is_rejected():
    ad = _new_draft()
    result = advertising.complete_ad_campaign(ad.id)
    assert "error" in result


def test_complete_missing_returns_none():
    assert advertising.complete_ad_campaign("AD-99999") is None


def test_cancel_draft():
    ad = _new_draft()
    advertising.cancel_ad_campaign(ad.id)
    assert ad.attributes["status"] == "cancelled"


def test_cancel_paused():
    ad = _new_draft()
    advertising.launch_ad_campaign(ad.id)
    advertising.pause_ad_campaign(ad.id)
    advertising.cancel_ad_campaign(ad.id)
    assert ad.attributes["status"] == "cancelled"


def test_cancel_active_is_rejected():
    ad = _new_draft()
    advertising.launch_ad_campaign(ad.id)
    result = advertising.cancel_ad_campaign(ad.id)
    assert "error" in result


def test_cancel_missing_returns_none():
    assert advertising.cancel_ad_campaign("AD-99999") is None


# --------------------------------------------------------------------------
# list_ad_campaigns
# --------------------------------------------------------------------------


def test_list_filters_by_platform_status_creator():
    a = _new_draft(created_by="EMP-1", platform="meta")
    b = _new_draft(created_by="EMP-2", platform="google")
    advertising.launch_ad_campaign(b.id)
    assert [c.id for c in advertising.list_ad_campaigns(platform="meta")] == [a.id]
    assert [c.id for c in advertising.list_ad_campaigns(status="active")] == [b.id]
    assert [c.id for c in advertising.list_ad_campaigns(created_by="EMP-2")] == [b.id]


def test_list_sorts_by_created_at_reverse():
    a = _new_draft(name="first")
    a.attributes["created_at"] = "2026-01-01T00:00:00+00:00"
    b = _new_draft(name="second")
    b.attributes["created_at"] = "2026-06-01T00:00:00+00:00"
    ids = [c.id for c in advertising.list_ad_campaigns()]
    assert ids == [b.id, a.id]


# --------------------------------------------------------------------------
# resolve_linked_vehicles
# --------------------------------------------------------------------------


def test_resolve_linked_vehicles_missing_ad_returns_empty():
    assert advertising.resolve_linked_vehicles("AD-99999") == []


def test_resolve_linked_vehicles_projects_attrs_and_skips_bad_ids():
    veh = _add_vehicle(Year=2024, Make="Ford", Model="F-150", Trim="XLT", Price=45000)
    ad = _new_draft(linked_vehicle_ids=[veh.id])
    # inject a dangling id after creation (bypasses _valid_vehicle_ids filter)
    ad.attributes["linked_vehicle_ids"].append("VEH-GONE")
    resolved = advertising.resolve_linked_vehicles(ad.id)
    assert len(resolved) == 1
    assert resolved[0] == {
        "id": veh.id, "year": 2024, "make": "Ford", "model": "F-150",
        "trim": "XLT", "price": 45000,
    }


# --------------------------------------------------------------------------
# advertising_api ACL layer
# --------------------------------------------------------------------------


def test_can_manage_admin_and_marketing_only():
    assert advertising_api._can_manage(ADMIN) is True
    assert advertising_api._can_manage(MARKETING) is True
    assert advertising_api._can_manage(SALES) is False


def test_serialize_carries_performance_note():
    ad = _new_draft()
    out = advertising_api._serialize(ad)
    assert out["id"] == ad.id
    assert "performance_note" in out
    assert "not_yet_tracked" in out["performance_note"]


def test_generate_recommendation_api_success_marks_ai_generated(monkeypatch):
    monkeypatch.setattr(advertising, "is_feature_enabled", lambda key: True)
    monkeypatch.setattr(
        advertising, "client", _FakeClient(content=json.dumps({"headline": "Hey"}))
    )
    out = advertising_api.generate_ad_recommendation_api(MARKETING, {"platform": "meta"})
    assert out["ai_generated"] is True
    assert out["headline"] == "Hey"


def test_generate_recommendation_api_error_returns_fallback(monkeypatch):
    monkeypatch.setattr(advertising, "is_feature_enabled", lambda key: True)
    monkeypatch.setattr(advertising, "client", _FakeClient(exc=RuntimeError("boom")))
    out = advertising_api.generate_ad_recommendation_api(MARKETING, {"objective": "leads"})
    assert out["ai_generated"] is False
    assert "boom" in out["ai_error"]
    # falls back to the plain placeholder, so it still has a headline
    assert out["headline"] == "Discover Your Next Vehicle Today"


def test_create_api_error_passthrough():
    out = advertising_api.create_ad_campaign_api(MARKETING, "EMP-1", "tiktok", "traffic", "X", {})
    assert "error" in out


def test_create_api_success_serialized():
    out = advertising_api.create_ad_campaign_api(SALES, "EMP-1", "meta", "traffic", "Promo", {})
    assert out["status"] == "draft"
    assert "performance_note" in out


def test_get_api_not_found():
    out = advertising_api.get_ad_campaign_api(SALES, "EMP-1", "AD-99999")
    assert out["error"] == "Ad campaign not found"


def test_get_api_includes_linked_vehicles():
    veh = _add_vehicle(Make="Ford")
    ad = _new_draft(linked_vehicle_ids=[veh.id])
    out = advertising_api.get_ad_campaign_api(SALES, "EMP-1", ad.id)
    assert out["id"] == ad.id
    assert out["linked_vehicles"][0]["make"] == "Ford"


def test_update_api_not_found():
    out = advertising_api.update_ad_campaign_api(ADMIN, "EMP-1", "AD-99999", {"name": "x"})
    assert out["error"] == "Ad campaign not found"


def test_update_api_non_creator_non_manager_denied():
    ad = _new_draft(created_by="EMP-1")
    out = advertising_api.update_ad_campaign_api(SALES, "EMP-2", ad.id, {"name": "x"})
    assert "error" in out
    assert ad.attributes["name"] == "Spring Sale"


def test_update_api_creator_allowed():
    ad = _new_draft(created_by="EMP-1")
    out = advertising_api.update_ad_campaign_api(SALES, "EMP-1", ad.id, {"name": "Renamed"})
    assert out["name"] == "Renamed"


def test_update_api_manager_allowed_even_if_not_creator():
    ad = _new_draft(created_by="EMP-1")
    out = advertising_api.update_ad_campaign_api(MARKETING, "EMP-2", ad.id, {"name": "Mgr"})
    assert out["name"] == "Mgr"


def test_launch_api_non_manager_denied():
    ad = _new_draft(created_by="EMP-1")
    out = advertising_api.launch_ad_campaign_api(SALES, "EMP-1", ad.id)
    assert "error" in out
    assert ad.attributes["status"] == "draft"


def test_launch_api_not_found():
    out = advertising_api.launch_ad_campaign_api(MARKETING, "EMP-1", "AD-99999")
    assert out["error"] == "Ad campaign not found"


def test_launch_api_manager_success():
    ad = _new_draft()
    out = advertising_api.launch_ad_campaign_api(ADMIN, "EMP-9", ad.id)
    assert out["status"] == "active"
    assert "performance_note" in out


def test_pause_api_non_manager_denied():
    ad = _new_draft()
    advertising.launch_ad_campaign(ad.id)
    out = advertising_api.pause_ad_campaign_api(SALES, "EMP-1", ad.id)
    assert "error" in out


def test_pause_api_not_found():
    out = advertising_api.pause_ad_campaign_api(MARKETING, "EMP-1", "AD-99999")
    assert out["error"] == "Ad campaign not found"


def test_pause_api_error_passthrough_on_wrong_state():
    ad = _new_draft()  # still draft -> pause is illegal
    out = advertising_api.pause_ad_campaign_api(MARKETING, "EMP-1", ad.id)
    assert "error" in out


def test_complete_api_non_manager_denied():
    ad = _new_draft()
    advertising.launch_ad_campaign(ad.id)
    out = advertising_api.complete_ad_campaign_api(SALES, "EMP-1", ad.id)
    assert "error" in out


def test_complete_api_success():
    ad = _new_draft()
    advertising.launch_ad_campaign(ad.id)
    out = advertising_api.complete_ad_campaign_api(MARKETING, "EMP-1", ad.id)
    assert out["status"] == "completed"


def test_cancel_api_not_found():
    out = advertising_api.cancel_ad_campaign_api(MARKETING, "EMP-1", "AD-99999")
    assert out["error"] == "Ad campaign not found"


def test_cancel_api_non_creator_non_manager_denied():
    ad = _new_draft(created_by="EMP-1")
    out = advertising_api.cancel_ad_campaign_api(SALES, "EMP-2", ad.id)
    assert "error" in out
    assert ad.attributes["status"] == "draft"


def test_cancel_api_creator_allowed():
    ad = _new_draft(created_by="EMP-1")
    out = advertising_api.cancel_ad_campaign_api(SALES, "EMP-1", ad.id)
    assert out["status"] == "cancelled"


def test_list_api_mine_only_filters_by_employee():
    _new_draft(created_by="EMP-1")
    _new_draft(created_by="EMP-2")
    out = advertising_api.list_ad_campaigns_api(MARKETING, "EMP-1", mine_only=True)
    assert len(out) == 1
    assert out[0]["created_by"] == "EMP-1"
    assert "performance_note" in out[0]


def test_list_api_not_mine_returns_all():
    _new_draft(created_by="EMP-1")
    _new_draft(created_by="EMP-2")
    out = advertising_api.list_ad_campaigns_api(MARKETING, "EMP-1", mine_only=False)
    assert len(out) == 2
