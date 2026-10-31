"""
Tests for core/menu_data.py (the generic dispatcher behind the Top Menu) and
core/menu_api.py (its thin ACL/route layer) -- the engine that turns GET /menu/data into
one route serving every department's every menu item rather than one endpoint per
department. Built across sessions 60-67 (the Top Menu rollout: Operations -> Sales ->
Service -> Marketing -> Inventory -> Finance -> Administration -> Readiness -> Network),
this layer shipped with only its static *catalog* covered (tests/test_navigation_catalogs.py,
session 71) -- the dispatcher/routing itself had no committed regression coverage until now.
Per BUILD_QUEUE.md's standing "convert to a real backend/tests/ suite as each module gets
touched" rule (sessions 46/48/49/71/72/73). Run from backend/ with `pytest`.

The invariants locked in here are the ones the module's own docstring promises and that the
whole 72-screen Top Menu relies on:
  * MENU_SOURCES is a perfect 1:1 against MENU_CATALOG -- exactly the 9 catalogued
    departments, each with exactly its 8 catalogued item keys wired to a callable fetch
    (no missing item silently unroutable, no orphan source pointing at a non-catalog key);
  * every (department, item) pair in QUERY_CAPABLE is a real, wired source (a search box on
    the frontend that dispatched to a non-existent fetch would 500);
  * get_menu_data() routes correctly: an unknown department or unknown item returns an
    {"error": ...} shape *before* any fetch runs; a catalogued-but-unwired item returns the
    distinct "not wired yet" error; a QUERY_CAPABLE item is called as fetch(role, query=...)
    while every other item is called as fetch(role) with no query kwarg;
  * the core/menu_api.py wrappers return the documented {"department", "items"} /
    passthrough shapes.

These tests deliberately do NOT assert the deep output of the 72 real menu functions (those
are covered department-by-department by their own smoke checks in the Session Log and change
per seed); they lock the *routing contract* the frontend depends on, using sentinel fetches
monkeypatched into MENU_SOURCES so the dispatch paths are exercised without needing a
populated graph. That keeps this file deterministic and seed-independent.
"""

import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

import pytest

from core import menu_data
from core.menu_data import MENU_SOURCES, QUERY_CAPABLE, get_menu_data
from core.menu_catalog import MENU_CATALOG, get_department_menu
from core import menu_api


# The 9 departments the Top Menu rollout (sessions 60-67) covers, in rollout order.
EXPECTED_DEPARTMENTS = {
    "Operations",
    "Sales",
    "Service",
    "Marketing",
    "Inventory",
    "Finance",
    "Administration",
    "Network",
    "Readiness",
}

# The exact QUERY_CAPABLE set as of session 67 -- the menu items whose fetch takes an
# optional `query` kwarg (a frontend search box). Locking the exact set, not just validity,
# so adding/removing a search box is a deliberate, test-visible change.
EXPECTED_QUERY_CAPABLE = {
    ("Operations", "vehicles"),
    ("Operations", "documents"),
    ("Sales", "prospects"),
    ("Sales", "customers"),
    ("Sales", "inventory"),
    ("Service", "repair_orders"),
    ("Service", "customers"),
    ("Service", "parts"),
    ("Marketing", "campaigns"),
    ("Marketing", "crm"),
    ("Marketing", "website"),
    ("Marketing", "social_reputation"),
    ("Marketing", "email_sms"), ("Marketing", "events"), ("Marketing", "purls"),
    ("Marketing", "advertising"), ("Finance", "portfolio"), ("Administration", "roles_permissions"),
    ("Inventory", "inventory"),
    ("Inventory", "lot_management"),
    ("Inventory", "pricing"),
    ("Inventory", "wholesale"),
    ("Finance", "deals"),
    ("Administration", "users"),
}


# --------------------------------------------------------------------------------------
# Structural completeness: MENU_SOURCES <-> MENU_CATALOG
# --------------------------------------------------------------------------------------

def test_all_nine_departments_wired():
    assert set(MENU_SOURCES.keys()) == EXPECTED_DEPARTMENTS


def test_sources_departments_match_catalogued_departments():
    """Every department with a wired source set must be catalogued, and vice versa -- a
    source dict for an uncatalogued department would be dead (get_menu_data rejects it on
    the catalog check first), and a catalogued department with no source dict would render
    a menu bar whose every item 500s."""

    # Marketplace (2026-07-24) is a bespoke Platform surface whose every menu item is a
    # frontend-dispatched board (core/marketplace.py via /marketplace), so it intentionally has
    # no MENU_SOURCES entry -- exclude it from the 1:1 sources<->catalog invariant.
    catalogued = {d for d, items in MENU_CATALOG.items() if items} - {"Marketplace"}
    assert set(MENU_SOURCES.keys()) == catalogued


def test_each_department_has_expected_sources():
    for department, sources in MENU_SOURCES.items():
        assert len(sources) == {'Operations': 11, 'Sales': 10, 'Service': 8, 'Marketing': 13, 'Inventory': 9, 'Finance': 16, 'Administration': 22, 'Readiness': 10, 'Network': 11}[department], department


BESPOKE_ITEMS = {'Operations': {'payroll', 'workflows'}, 'Sales': {'workflows', 'propensity'}, 'Marketing': {'lead_import', 'file_manager', 'campaign_library', 'campaign_scheduler'}, 'Administration': {'connections', 'team_management', 'lead_routing'}}


def test_source_keys_cover_catalog_except_explicit_bespoke_boards():
    for department, sources in MENU_SOURCES.items():
        catalog_keys = {item["key"] for item in get_department_menu(department)} - BESPOKE_ITEMS.get(department, set())
        assert sorted(sources.keys()) == sorted(catalog_keys), (
            f"{department}: source keys {sorted(sources.keys())} != "
            f"catalog keys {sorted(catalog_keys)}"
        )


def test_total_wired_items_is_one_hundred_ten():
    total = sum(len(sources) for sources in MENU_SOURCES.values())
    assert total == 110


def test_every_fetch_is_callable():
    for department, sources in MENU_SOURCES.items():
        for key, fetch in sources.items():
            assert callable(fetch), f"{department}.{key} fetch is not callable"


# --------------------------------------------------------------------------------------
# QUERY_CAPABLE integrity
# --------------------------------------------------------------------------------------

def test_query_capable_matches_expected_set():
    assert set(QUERY_CAPABLE) == EXPECTED_QUERY_CAPABLE


def test_every_query_capable_pair_is_a_real_source():
    for department, item_key in QUERY_CAPABLE:
        assert department in MENU_SOURCES, f"{department} not in MENU_SOURCES"
        assert item_key in MENU_SOURCES[department], (
            f"query-capable ({department}, {item_key}) has no wired source"
        )


# --------------------------------------------------------------------------------------
# get_menu_data() dispatch routing -- error paths run before any fetch, so no graph needed
# --------------------------------------------------------------------------------------

def test_unknown_department_returns_error_without_calling_a_fetch():
    result = get_menu_data("ADMIN", "Nonexistent", "overview")
    assert "error" in result
    assert "Nonexistent" in result["error"]


def test_unknown_item_for_known_department_returns_error():
    result = get_menu_data("ADMIN", "Operations", "not_a_real_item")
    assert "error" in result
    assert "not_a_real_item" in result["error"]


def test_catalogued_but_unwired_item_returns_not_wired_error(monkeypatch):
    """If a catalog item has no MENU_SOURCES entry, get_menu_data returns the distinct
    'not wired yet' error rather than crashing -- simulate by removing a live source."""

    monkeypatch.delitem(MENU_SOURCES["Operations"], "overview")
    result = get_menu_data("ADMIN", "Operations", "overview")
    assert "error" in result
    assert "wired" in result["error"].lower()


def test_non_query_item_is_called_with_role_only(monkeypatch):
    calls = {}

    def sentinel(role, **kwargs):
        calls["role"] = role
        calls["kwargs"] = kwargs
        return {"ok": True}

    # "overview" is NOT query-capable for any department.
    monkeypatch.setitem(MENU_SOURCES["Operations"], "overview", sentinel)
    result = get_menu_data("SALES", "Operations", "overview", query="ignored")

    assert result == {"ok": True}
    assert calls["role"] == "SALES"
    assert calls["kwargs"] == {}  # query must NOT be forwarded to a non-query item


def test_query_capable_item_is_called_with_query_kwarg(monkeypatch):
    calls = {}

    def sentinel(role, query=None):
        calls["role"] = role
        calls["query"] = query
        return {"ok": True}

    # ("Operations", "vehicles") is in QUERY_CAPABLE.
    monkeypatch.setitem(MENU_SOURCES["Operations"], "vehicles", sentinel)
    result = get_menu_data("ADMIN", "Operations", "vehicles", query="F-150")

    assert result == {"ok": True}
    assert calls["role"] == "ADMIN"
    assert calls["query"] == "F-150"


# --------------------------------------------------------------------------------------
# core/menu_api.py thin wrappers
# --------------------------------------------------------------------------------------

def test_get_department_menu_api_shape():
    result = menu_api.get_department_menu_api("Operations")
    assert result["department"] == "Operations"
    assert isinstance(result["items"], list)
    assert result["items"] == get_department_menu("Operations")
    assert all("key" in item for item in result["items"])


def test_get_department_menu_api_unknown_department_returns_empty_items():
    result = menu_api.get_department_menu_api("Nonexistent")
    assert result["department"] == "Nonexistent"
    assert result["items"] == []


def test_get_menu_data_api_delegates_to_get_menu_data(monkeypatch):
    marker = {"delegated": True}
    monkeypatch.setattr(
        menu_api,
        "get_menu_data",
        lambda role, department, item_key, query=None: {
            "role": role,
            "department": department,
            "item_key": item_key,
            "query": query,
            **marker,
        },
    )
    result = menu_api.get_menu_data_api("ADMIN", "Sales", "prospects", query="hot")
    assert result["delegated"] is True
    assert result["role"] == "ADMIN"
    assert result["department"] == "Sales"
    assert result["item_key"] == "prospects"
    assert result["query"] == "hot"


def test_get_menu_data_api_error_passthrough():
    # Real path (no monkeypatch): an unknown department flows through the wrapper as an error.
    result = menu_api.get_menu_data_api("ADMIN", "Nonexistent", "overview")
    assert "error" in result
