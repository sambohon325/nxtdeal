"""
Bumper-parity Content Library (2026-07-25): the Campaign-Template Library
(browse/seed/instantiate) and the File Manager / DAM (multi-type catalog). Run from
backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import CAMPAIGN_TEMPLATE, FILE_ASSET, CUSTOMER, CAMPAIGN
from core import campaign_template_library as lib
from core import campaign_template_library_api as lib_api
from core import file_manager as fm
from core import file_manager_api as fm_api


@pytest.fixture(autouse=True)
def fresh():
    ledger.reset()
    yield
    ledger.reset()


# --- Campaign-Template Library ---

def test_starter_library_seeds_idempotently():
    n1 = lib.seed_starter_templates()
    assert n1 == len(lib.STARTER_TEMPLATES)
    n2 = lib.seed_starter_templates()          # second call adds nothing
    assert n2 == 0
    assert len(lib.list_templates()) == len(lib.STARTER_TEMPLATES)


def test_list_auto_seeds_when_empty():
    assert len(ledger.get_all()) == 0
    templates = lib.list_templates()           # triggers ensure_seeded
    assert len(templates) == len(lib.STARTER_TEMPLATES)


def test_list_filters_by_category_and_type():
    lib.ensure_seeded()
    retention = lib.list_templates(campaign_type="retention")
    assert len(retention) == 2
    finance = lib.list_templates(category="Finance")
    assert all(t.attributes["category"] == "Finance" for t in finance)
    assert len(finance) == 2
    cats = {c["category"] for c in lib.list_categories()}
    assert {"Retention", "Sales", "Finance", "Accessories", "Announcements"} <= cats


def test_instantiate_creates_a_draft_campaign():
    lib.ensure_seeded()
    tmpl = lib.list_templates(campaign_type="retention")[0]
    campaign = lib.instantiate_template(tmpl.id, "EMP-1")
    assert campaign.entity_type == CAMPAIGN
    assert campaign.attributes["status"] == "draft"
    assert campaign.attributes["campaign_type"] == "retention"
    assert campaign.attributes["from_template_id"] == tmpl.id
    # usage counter advanced
    assert lib.get_template(tmpl.id).attributes["times_used"] == 1


def test_instantiate_applies_overrides():
    lib.ensure_seeded()
    tmpl = lib.list_templates(campaign_type="retention")[0]
    campaign = lib.instantiate_template(tmpl.id, "EMP-1", name_override="My Spring Push",
                                        params_override={"months_since_service": 9})
    assert campaign.attributes["name"] == "My Spring Push"
    assert campaign.attributes["params"]["months_since_service"] == 9


def test_create_and_delete_user_template():
    t = lib.create_template("My Template", "general", "email", "EMP-1", category="Custom")
    assert t.entity_type == CAMPAIGN_TEMPLATE and t.attributes["is_starter"] is False
    assert lib.delete_template(t.id)["ok"] is True
    assert lib.get_template(t.id).attributes["deleted"] is True


def test_starter_template_cannot_be_deleted():
    lib.ensure_seeded()
    starter = lib.list_templates()[0]
    assert "error" in lib.delete_template(starter.id)


def test_create_template_validates_type_and_channel():
    assert "error" in lib.create_template("X", "bogus", "email", "EMP-1")
    assert "error" in lib.create_template("X", "general", "carrier_pigeon", "EMP-1")


# --- Campaign library API role gating ---

def test_api_authoring_requires_marketing_admin():
    from core.permissions import ADMIN, SALES
    assert "error" in lib_api.create_template_api(SALES, "EMP-1", "T", "general", "email")
    ok = lib_api.create_template_api(ADMIN, "EMP-1", "T", "general", "email")
    assert "id" in ok
    # But any role can browse and instantiate (draft only).
    lib.ensure_seeded()
    tmpl = lib.list_templates(campaign_type="retention")[0]
    inst = lib_api.instantiate_template_api(SALES, "EMP-2", tmpl.id)
    assert inst["status"] == "draft"


# --- File Manager / DAM ---

def test_add_and_list_multi_type_files():
    fm.add_file("promo.mp4", "video", "https://cdn.example.com/promo.mp4", "EMP-1", category="ads", size_bytes=1000)
    fm.add_file("logo.png", "image", "https://cdn.example.com/logo.png", "EMP-1", category="branding")
    fm.add_file("radio.mp3", "audio", "https://cdn.example.com/radio.mp3", "EMP-1", category="ads")
    assert len(fm.list_files()) == 3
    assert len(fm.list_files(media_type="video")) == 1
    assert len(fm.list_files(category="ads")) == 2
    summary = fm.storage_summary()
    assert summary["total"] == 3
    assert summary["by_media_type"]["video"]["count"] == 1
    assert summary["by_media_type"]["video"]["bytes"] == 1000


def test_add_file_validates():
    assert "error" in fm.add_file("", "video", "http://x", "EMP-1")           # no name
    assert "error" in fm.add_file("x", "hologram", "http://x", "EMP-1")       # bad media_type
    assert "error" in fm.add_file("x", "video", "", "EMP-1")                  # no url


def test_update_and_remove_file():
    f = fm.add_file("draft.pdf", "document", "http://x/d.pdf", "EMP-1")
    fid = f["id"]
    updated = fm.update_file(fid, {"category": "contracts", "tags": ["signed"]})
    assert updated["category"] == "contracts" and updated["tags"] == ["signed"]
    assert fm.remove_file(fid)["removed"] == fid
    assert fm.list_files() == []


def test_search_matches_name_tags_description():
    fm.add_file("Spring Sale Banner", "image", "http://x/1.png", "EMP-1", tags=["seasonal"], description="April promo")
    fm.add_file("Winter Radio Spot", "audio", "http://x/2.mp3", "EMP-1")
    assert len(fm.list_files(query="spring")) == 1
    assert len(fm.list_files(query="seasonal")) == 1
    assert len(fm.list_files(query="april")) == 1


def test_dam_api_write_requires_write_role():
    from core.permissions import ADMIN, SALES, MARKETING
    assert "error" in fm_api.add_file_api(SALES, "EMP-1", "x", "image", "http://x")
    ok = fm_api.add_file_api(MARKETING, "EMP-1", "x", "image", "http://x")
    assert "id" in ok
    # Any role can browse.
    assert "files" in fm_api.list_files_api(SALES)
