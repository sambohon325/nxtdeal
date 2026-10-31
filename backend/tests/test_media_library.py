"""Tests for core/media_library.py -- the dealership-wide shared image asset library.
Mirrors test_accessories.py's conventions (fresh_ledger + no_real_persistence autouse
fixtures). Covers: uploaded library assets by category, name/tag search, the live
inventory-photo merge (IMAGE linked to a Vehicle via HAS_IMAGE), removal rules, the
category summary, and the ACL layer."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import VEHICLE, IMAGE
from core.relationships import Relationship
from core.relationship_types import HAS_IMAGE
from core.permissions import ADMIN, FINANCE, MARKETING, OPERATIONS, SALES, SERVICE

from core import media_library
from core import media_library_api


_VIEW_ROLES = (ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE)
_WRITE_ROLES = (ADMIN, OPERATIONS, MARKETING)
_DENIED_WRITE = (SALES, SERVICE, FINANCE, "BOGUS")


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    monkeypatch.setattr(media_library, "save_graph", lambda filepath: None)


def _add_vehicle_photo(vehicle_id="VEH-1", year="2022", make="Ford", model="F-150",
                       stock="A100", url="https://cdn/veh1.jpg", caption="Front"):
    v = ledger.get_entity(vehicle_id)
    if not v:
        v = Entity(id=vehicle_id, entity_type=VEHICLE,
                   attributes={"Year": year, "Make": make, "Model": model, "StockNumber": stock})
        ledger.add_entity(v)
    img_id = f"IMG-veh-{len([r for r in ledger.get_relationships() if r.relationship_type == HAS_IMAGE]) + 1}"
    img = Entity(id=img_id, entity_type=IMAGE, attributes={"URL": url, "Caption": caption})
    ledger.add_entity(img)
    ledger.add_relationship(Relationship(source_id=vehicle_id, target_id=img_id,
                                         relationship_type=HAS_IMAGE))
    return img_id


# --- add / list ---

def test_add_library_image_returns_brief():
    r = media_library.add_library_image("https://cdn/logo.png", "Main Logo", "logos", "EMP-1")
    assert r["url"] == "https://cdn/logo.png"
    assert r["name"] == "Main Logo"
    assert r["category"] == "logos"
    assert r["scope"] == "library"
    assert r["removable"] is True
    assert r["id"].startswith("IMG")


def test_add_defaults_to_general_and_trims_tags():
    r = media_library.add_library_image("https://cdn/x.png", "X", "general", "EMP-1", tags=["  sale ", "", "spring"])
    assert r["tags"] == ["sale", "spring"]


def test_list_returns_added_images_most_recent_first():
    media_library.add_library_image("https://cdn/a.png", "Alpha", "logos", "EMP-1")
    media_library.add_library_image("https://cdn/b.png", "Beta", "oem_approved", "EMP-1")
    imgs = media_library.list_library_images()
    names = [i["name"] for i in imgs]
    assert "Alpha" in names and "Beta" in names


def test_category_filter():
    media_library.add_library_image("https://cdn/a.png", "Alpha", "logos", "EMP-1")
    media_library.add_library_image("https://cdn/b.png", "Beta", "oem_approved", "EMP-1")
    logos = media_library.list_library_images(category="logos")
    assert [i["name"] for i in logos] == ["Alpha"]


def test_query_matches_name_and_tags():
    media_library.add_library_image("https://cdn/a.png", "Summer Banner", "general", "EMP-1")
    media_library.add_library_image("https://cdn/b.png", "Winter", "general", "EMP-1", tags=["holiday"])
    assert {i["name"] for i in media_library.list_library_images(query="summer")} == {"Summer Banner"}
    assert {i["name"] for i in media_library.list_library_images(query="holiday")} == {"Winter"}


def test_unknown_category_filter_errors():
    r = media_library.list_library_images(category="nope")
    assert isinstance(r, dict) and "error" in r


# --- inventory merge ---

def test_inventory_category_merges_live_vehicle_photos():
    _add_vehicle_photo()
    inv = media_library.list_library_images(category="inventory")
    assert len(inv) == 1
    assert inv[0]["scope"] == "inventory"
    assert inv[0]["category"] == "inventory"
    assert inv[0]["removable"] is False
    assert inv[0]["vehicle"] == "2022 Ford F-150 (#A100)"


def test_unfiltered_list_includes_both_library_and_inventory():
    media_library.add_library_image("https://cdn/logo.png", "Logo", "logos", "EMP-1")
    _add_vehicle_photo()
    imgs = media_library.list_library_images()
    scopes = {i["scope"] for i in imgs}
    assert scopes == {"library", "inventory"}


def test_library_category_excludes_vehicle_photos():
    _add_vehicle_photo()
    assert media_library.list_library_images(category="logos") == []


# --- add validation ---

def test_add_to_inventory_category_is_rejected():
    r = media_library.add_library_image("https://cdn/x.png", "X", "inventory", "EMP-1")
    assert "error" in r and "inventory" in r["error"].lower()


def test_add_requires_url():
    r = media_library.add_library_image("", "X", "logos", "EMP-1")
    assert "error" in r


def test_add_unknown_category_errors():
    r = media_library.add_library_image("https://cdn/x.png", "X", "bogus", "EMP-1")
    assert "error" in r


# --- remove ---

def test_remove_library_image():
    added = media_library.add_library_image("https://cdn/x.png", "X", "logos", "EMP-1")
    r = media_library.remove_library_image(added["id"])
    assert r == {"removed": added["id"]}
    assert media_library.list_library_images(category="logos") == []


def test_remove_vehicle_photo_is_refused():
    img_id = _add_vehicle_photo()
    r = media_library.remove_library_image(img_id)
    assert "error" in r
    # still present in the inventory view
    assert len(media_library.list_library_images(category="inventory")) == 1


def test_remove_nonexistent_errors():
    assert "error" in media_library.remove_library_image("IMG-nope")


# --- categories summary ---

def test_list_categories_has_all_five_with_counts():
    media_library.add_library_image("https://cdn/a.png", "A", "logos", "EMP-1")
    media_library.add_library_image("https://cdn/b.png", "B", "logos", "EMP-1")
    _add_vehicle_photo()
    cats = {c["key"]: c["count"] for c in media_library.list_categories()}
    assert set(cats.keys()) == {"oem_approved", "logos", "dealership_branding", "inventory", "general"}
    assert cats["logos"] == 2
    assert cats["inventory"] == 1


# --- ACL layer ---

def test_view_open_to_all_roles():
    media_library.add_library_image("https://cdn/a.png", "A", "logos", "EMP-1")
    for role in _VIEW_ROLES:
        r = media_library_api.list_media_api(role)
        assert "images" in r, role


def test_view_denied_for_unknown_role():
    assert "error" in media_library_api.list_media_api("BOGUS")


def test_add_allowed_only_for_write_roles():
    for role in _WRITE_ROLES:
        r = media_library_api.add_media_api(role, "https://cdn/x.png", "X", "logos", "EMP-1")
        assert "image" in r, role
    for role in _DENIED_WRITE:
        r = media_library_api.add_media_api(role, "https://cdn/x.png", "X", "logos", "EMP-1")
        assert "error" in r, role


def test_remove_allowed_only_for_write_roles():
    added = media_library.add_library_image("https://cdn/x.png", "X", "logos", "EMP-1")
    assert "error" in media_library_api.remove_media_api(SALES, added["id"])
    assert media_library_api.remove_media_api(ADMIN, added["id"]) == {"removed": added["id"]}


def test_categories_api_gated():
    assert "categories" in media_library_api.list_media_categories_api(MARKETING)
    assert "error" in media_library_api.list_media_categories_api("BOGUS")
