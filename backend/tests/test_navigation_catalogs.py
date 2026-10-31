"""
Tests for the two department navigation catalogs -- the sessions 60-68 arc:

  * core/menu_catalog.py     -- the "Top Menu" navigation layer (sessions 60-67,
                                one interactive/scheduled session per department
                                until all 9 were rolled out).
  * core/workflow_catalog.py -- the 4-per-department job-workflow "modal" catalog
                                (session 53), restructured session 68 to a uniform
                                5-stage/5-tab shape with no core_functionality field.

Session 71 (scheduled builder, autonomous) added this file per the standing
"Backlog Hygiene" directive to convert coverage to a real pytest suite as modules
get touched -- this whole 9-department rollout + 36-modal rework had shipped across
sessions 60-68 with zero committed regression coverage. Prior scheduled sessions
(69/70) verified these same invariants ad-hoc via a live `python3` import but never
committed a test, so a future edit to either catalog (or the FUSE-mount truncation
bug those sessions kept hitting) could silently break the 9x8 menu grid or the
36x(5,5) workflow grid without anything failing.

These two catalogs are pure static dicts plus a couple of lookup helpers -- they do
NOT import the graph ledger / data-fetch chain (core/menu_data.py's *_menu functions
do, but the catalogs themselves don't), so this file imports and runs cleanly even
when the rest of the backend can't boot. Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

import pytest

from core import menu_catalog
from core import workflow_catalog


# The 9 departments, as the whole platform names them. app/workspace/page.tsx passes
# these exact strings; both catalogs must agree on them.
EXPECTED_DEPARTMENTS = {
    "Operations",
    "Sales",
    "Service",
    "Marketing",
    "Inventory",
    "Finance",
    "Administration",
    "Readiness",
    "Network",
}

# The Marketplace (2026-07-24) is a bespoke top-level Platform surface (opened from the gear
# menu, after Network), not one of the nine PDF-spec operational departments. It's catalogued
# in MENU_CATALOG so its nav renders, but it has no WORKFLOW_CATALOG entry, no MENU_SOURCES
# (every item is a frontend-dispatched bespoke board), and does not follow the
# Overview..Reporting menu convention -- so it's excluded from those department-shape guards.
MENU_ONLY_DEPARTMENTS = {"Marketplace"}


# ---------------------------------------------------------------------------
# menu_catalog.py -- the Top Menu (9 departments x 8 items)
# ---------------------------------------------------------------------------

def test_menu_catalog_has_all_nine_departments():
    # The nine operational departments plus the bespoke Marketplace Platform surface.
    assert set(menu_catalog.MENU_CATALOG.keys()) == EXPECTED_DEPARTMENTS | MENU_ONLY_DEPARTMENTS


def test_every_department_has_expected_menu_items():
    for department, items in menu_catalog.MENU_CATALOG.items():
        assert len(items) == {'Operations': 13, 'Sales': 12, 'Service': 8, 'Marketing': 17, 'Inventory': 9, 'Finance': 16, 'Administration': 25, 'Readiness': 10, 'Network': 11, 'Marketplace': 5}[department], department


def test_menu_items_have_required_string_fields():
    for department, items in menu_catalog.MENU_CATALOG.items():
        for item in items:
            assert set(item.keys()) == {"key", "label", "description"}, (
                f"{department} item {item.get('key')!r} has unexpected keys "
                f"{set(item.keys())}"
            )
            for field in ("key", "label", "description"):
                assert isinstance(item[field], str) and item[field].strip(), (
                    f"{department} item {item.get('key')!r} has empty {field}"
                )


def test_menu_starts_with_overview_and_ends_with_reporting():
    # Every department's PDF spec (sessions 60-67) defines the Menu Bar as
    # "Overview | ... | Reporting" -- always first Overview, always last Reporting.
    for department, items in menu_catalog.MENU_CATALOG.items():
        if department in MENU_ONLY_DEPARTMENTS:
            continue  # Marketplace is a bespoke Platform surface, not an Overview..Reporting dept
        assert items[0]["key"] == "overview", f"{department} does not start with Overview"
        assert items[0]["label"] == "Overview"
        assert items[-1]["key"] == "reporting", f"{department} does not end with Reporting"
        assert items[-1]["label"] == "Reporting"


def test_menu_item_keys_unique_within_department():
    for department, items in menu_catalog.MENU_CATALOG.items():
        keys = [item["key"] for item in items]
        assert len(keys) == len(set(keys)), f"{department} has duplicate menu item keys"


def test_get_department_menu_returns_the_catalogued_list():
    for department, items in menu_catalog.MENU_CATALOG.items():
        assert menu_catalog.get_department_menu(department) == items


def test_get_department_menu_unknown_department_returns_empty_list():
    # Documented contract: a not-yet-catalogued department returns [] (the frontend
    # hides the menu bar), never raises.
    assert menu_catalog.get_department_menu("Nonexistent") == []


# ---------------------------------------------------------------------------
# workflow_catalog.py -- the 4-per-department job-workflow modals
# ---------------------------------------------------------------------------

def test_workflow_departments_match_menu_departments():
    assert set(workflow_catalog.WORKFLOW_CATALOG.keys()) == EXPECTED_DEPARTMENTS
    assert set(workflow_catalog.DEPARTMENTS) == EXPECTED_DEPARTMENTS


def test_each_department_has_expected_workflows():
    for department, workflows in workflow_catalog.WORKFLOW_CATALOG.items():
        assert len(workflows) == (12 if department == "Sales" else 4), (
            f"{department} has {len(workflows)} workflows, expected 4"
        )


def test_exactly_forty_four_workflows_total():
    total = sum(len(v) for v in workflow_catalog.WORKFLOW_CATALOG.values())
    assert total == 44


def test_workflows_have_all_required_fields():
    required = {
        "key",
        "title",
        "entity_type",
        "entity_label",
        "description",
        "why_it_matters",
        "stages",
        "tabs",
    }
    for department, workflows in workflow_catalog.WORKFLOW_CATALOG.items():
        for workflow in workflows:
            assert required.issubset(workflow.keys()), (
                f"{workflow.get('key')} missing "
                f"{required - set(workflow.keys())}"
            )


def test_session_68_dropped_core_functionality():
    # Session 68's rework removed the old core_functionality field entirely.
    for workflows in workflow_catalog.WORKFLOW_CATALOG.values():
        for workflow in workflows:
            assert "core_functionality" not in workflow, (
                f"{workflow['key']} still carries core_functionality"
            )


def test_every_workflow_has_exactly_five_stages_and_five_tabs():
    # Session 68's uniform shape: exactly 5 stages and 5 tabs, positionally paired.
    for workflows in workflow_catalog.WORKFLOW_CATALOG.values():
        for workflow in workflows:
            assert len(workflow["stages"]) == 5, (
                f"{workflow['key']} has {len(workflow['stages'])} stages, expected 5"
            )
            assert len(workflow["tabs"]) == 5, (
                f"{workflow['key']} has {len(workflow['tabs'])} tabs, expected 5"
            )


def test_stages_and_tabs_are_nonempty_strings():
    for workflows in workflow_catalog.WORKFLOW_CATALOG.values():
        for workflow in workflows:
            for label in workflow["stages"] + workflow["tabs"]:
                assert isinstance(label, str) and label.strip(), (
                    f"{workflow['key']} has an empty stage/tab label"
                )


def test_workflow_keys_globally_unique():
    keys = [
        workflow["key"]
        for workflows in workflow_catalog.WORKFLOW_CATALOG.values()
        for workflow in workflows
    ]
    assert len(keys) == len(set(keys)) == 44


def test_workflow_key_prefix_matches_department():
    # Keys are dotted "<department-lower>.<slug>" -- REAL_SOURCES / workflow_tracking
    # both rely on this stable convention.
    for department, workflows in workflow_catalog.WORKFLOW_CATALOG.items():
        for workflow in workflows:
            prefix = workflow["key"].split(".")[0]
            assert prefix == department.lower(), (
                f"{workflow['key']} prefix does not match department {department}"
            )


def test_get_workflow_def_resolves_known_and_unknown_keys():
    recon = workflow_catalog.get_workflow_def("operations.recon")
    assert recon is not None
    assert recon["title"] == "Vehicle Intake & Recon"
    assert workflow_catalog.get_workflow_def("does.not.exist") is None


def test_get_catalog_returns_the_full_catalog():
    assert workflow_catalog.get_catalog() == workflow_catalog.WORKFLOW_CATALOG


def test_marketing_reputation_key_repurposed_to_events():
    # Session 68 merged Website Merchandising + Reputation into
    # marketing.website_merchandising, and REPURPOSED marketing.reputation to carry
    # the new "Events & Activations" workflow (entity_type dropped to None, since no
    # Event entity exists in this codebase yet).
    marketing_keys = {
        workflow["key"]
        for workflow in workflow_catalog.WORKFLOW_CATALOG["Marketing"]
    }
    assert "marketing.website_merchandising" in marketing_keys
    assert "marketing.reputation" in marketing_keys

    events = workflow_catalog.get_workflow_def("marketing.reputation")
    assert events["title"] == "Events & Activations"
    assert events["entity_type"] is None
