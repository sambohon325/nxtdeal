"""
Tests for the Digital Retail website widgets (core/websites.py catalog + render, DR-5,
2026-07-24). Run from backend/ with `pytest`.

Covers: the five new section templates are in the builder catalog and addable via add_section;
Ask NXTDeal resolves a live inventory sample; Payment Builder resolves live options + parsed
payment config; Buy Online normalizes its level; Delivery Scheduling parses its toggles.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import VEHICLE

from core import websites


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield
    ledger.reset()


_NEW = ("ask_dealeros", "payment_builder", "trade_evaluation", "buy_online", "delivery_scheduling")


def _seed_inventory():
    for i, (mk, md, tr, price) in enumerate([
        ("Ford", "F-150", "XLT", 42000),
        ("Ford", "F-150", "Lariat", 55000),
        ("Toyota", "Camry", "SE", 28000),
    ]):
        ledger.add_entity(Entity(id=f"VEH-{i}", entity_type=VEHICLE,
                                 attributes={"Make": mk, "Model": md, "Trim": tr, "Price": price, "Cost": price - 4000}))


def _site():
    return websites.create_website("Test Motors", "EMP-1", "traditional")


def test_all_five_widgets_in_catalog():
    keys = {t["key"] for t in websites.list_section_templates()}
    for k in _NEW:
        assert k in keys, f"{k} missing from SECTION_TEMPLATES"
        tpl = websites.get_section_template(k)
        assert tpl["name"] and tpl["fields"]


def test_widgets_are_addable():
    site = _site()
    for k in _NEW:
        res = websites.add_section(site.id, "home", k, {})
        assert not (isinstance(res, dict) and res.get("error")), f"{k}: {res}"


def test_ask_dealeros_resolves_inventory_sample():
    _seed_inventory()
    site = _site()
    websites.add_section(site.id, "home", "ask_dealeros", {"heading": "Ask us"})
    rendered = websites.render_page(websites.get_website(site.id), "home")
    sec = next(s for s in rendered["sections"] if s["section_key"] == "ask_dealeros")
    assert isinstance(sec["live_vehicles"], list) and len(sec["live_vehicles"]) >= 1


def test_payment_builder_resolves_options_and_config():
    _seed_inventory()
    site = _site()
    websites.add_section(site.id, "home", "payment_builder",
                         {"default_down": "5000", "default_term_months": "72", "assumed_apr": "5.5"})
    rendered = websites.render_page(websites.get_website(site.id), "home")
    sec = next(s for s in rendered["sections"] if s["section_key"] == "payment_builder")
    assert isinstance(sec["live_options"], list) and sec["live_options"]
    cfg = sec["payment_config"]
    assert cfg["default_down"] == 5000 and cfg["default_term_months"] == 72 and cfg["assumed_apr"] == 5.5


def test_payment_config_falls_back_on_bad_input():
    site = _site()
    websites.add_section(site.id, "home", "payment_builder", {"assumed_apr": "not-a-number"})
    rendered = websites.render_page(websites.get_website(site.id), "home")
    sec = next(s for s in rendered["sections"] if s["section_key"] == "payment_builder")
    assert sec["payment_config"]["assumed_apr"] == 6.9  # default
    assert sec["payment_config"]["default_down"] == 3000


def test_buy_online_normalizes_level():
    site = _site()
    websites.add_section(site.id, "home", "buy_online", {"level": "PURCHASE"})
    websites.add_section(site.id, "home", "buy_online", {"level": "bogus"})
    rendered = websites.render_page(websites.get_website(site.id), "home")
    levels = [s["buy_online_level"] for s in rendered["sections"] if s["section_key"] == "buy_online"]
    assert levels == ["purchase", "build"]  # normalized + fallback


def test_delivery_scheduling_parses_toggles():
    site = _site()
    websites.add_section(site.id, "home", "delivery_scheduling",
                         {"offer_home_delivery": "false", "offer_try_before_you_buy": "true",
                          "delivery_radius_miles": "100"})
    rendered = websites.render_page(websites.get_website(site.id), "home")
    sec = next(s for s in rendered["sections"] if s["section_key"] == "delivery_scheduling")
    opts = sec["delivery_options"]
    assert opts["store_pickup"] is True          # default
    assert opts["home_delivery"] is False
    assert opts["try_before_you_buy"] is True
    assert opts["radius_miles"] == 100
