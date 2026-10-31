"""
Tests for core/workflow_tab_data.py -- the "one generic engine" that backs every
workflow-modal window's live-data panel (GET /workflows/tab-data, session 57).

Two things are locked in here:

  * REAL_SOURCES completeness (session 59's invariant): every one of the 36 workflow
    keys in core/workflow_catalog.py has exactly one REAL_SOURCES entry -- no missing
    key, no orphan key -- and every source block is well-formed (id/label/type, a
    dashboard_key on dashboard-type sources, a callable fetch).

  * get_tab_data()'s three role-gating branches (dashboard / admin_only / self_gated).
    The 2026-07-15 interactive session had to RECONSTRUCT this function after a
    FUSE-mount truncation cut the branches, the sources.append(), and the return off
    mid-body -- a SyntaxError that took the whole api/app.py boot down and made it look
    like the entire navigation layer had vanished. That reconstruction shipped with no
    committed regression coverage; this file is that coverage, so the same truncation
    (or any future edit) can't silently re-break the gating without a red test.

This module DOES import the graph-ledger/data-fetch chain, but the assertions here are
about REAL_SOURCES structure and the role-gating control flow, neither of which depends
on the graph being loaded -- the module-level ledger is empty in a fresh import and the
self_gated fetches still return non-error dicts against it. Run from backend/ with
`pytest tests/test_workflow_tab_data.py`.

Session 73 (scheduled builder, autonomous) added this file per the standing incremental
`backend/tests/` coverage directive -- same motivation as sessions 71 (navigation
catalogs) and 72 (entity_update_api): convert ad-hoc live-import verification into a
committed regression test as recently-touched modules get revisited.
"""

import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

import pytest

from core import workflow_tab_data as wtd
from core import workflow_catalog


VALID_SOURCE_TYPES = {"dashboard", "admin_only", "self_gated"}


def _catalog_keys():
    keys = []
    for workflows in workflow_catalog.WORKFLOW_CATALOG.values():
        for wf in workflows:
            keys.append(wf["key"])
    return keys


# ---------------------------------------------------------------------------
# REAL_SOURCES completeness -- session 59's "all 36 keys covered" invariant.
# ---------------------------------------------------------------------------

def test_real_sources_covers_every_catalog_key_exactly():
    catalog_keys = set(_catalog_keys())
    source_keys = set(wtd.REAL_SOURCES.keys())

    # 36 workflows, 36 REAL_SOURCES entries, a perfect 1:1 -- no workflow left
    # without a real data source, no source pointing at a workflow that no longer
    # exists. This is the exact thing a truncation/rename silently breaks.
    assert len(catalog_keys) == 44
    assert source_keys == catalog_keys, {
        "missing_from_real_sources": sorted(catalog_keys - source_keys),
        "orphan_real_sources": sorted(source_keys - catalog_keys),
    }


# Session 68 repurposed marketing.reputation to carry "Events & Activations" and moved
# its review-summary source onto marketing.website_merchandising, deliberately leaving
# marketing.reputation with an empty REAL_SOURCES list (an honest gap -- no Event entity
# exists anywhere in this codebase yet). That is the ONLY intentionally-empty block.
_INTENTIONALLY_EMPTY = {"marketing.reputation"}


def test_every_real_source_block_is_a_list():
    for key, sources in wtd.REAL_SOURCES.items():
        assert isinstance(sources, list), key


def test_only_marketing_reputation_is_empty():
    empty = {k for k, srcs in wtd.REAL_SOURCES.items() if len(srcs) == 0}
    # Locks in session 68's repurpose: exactly one honest-gap block, no others silently
    # emptied by a future truncation/edit.
    assert empty == _INTENTIONALLY_EMPTY


def test_every_source_is_well_formed():
    for key, sources in wtd.REAL_SOURCES.items():
        for source in sources:
            for field in ("id", "label", "type", "fetch"):
                assert field in source, (key, field)
            assert source["type"] in VALID_SOURCE_TYPES, (key, source["type"])
            assert callable(source["fetch"]), (key, source["id"])
            # dashboard-type sources are gated via can_access_dashboard(role, key),
            # so they must carry the dashboard_key that gate reads.
            if source["type"] == "dashboard":
                assert source.get("dashboard_key"), (key, source["id"])


def test_all_three_source_types_are_actually_used():
    types = {s["type"] for sources in wtd.REAL_SOURCES.values() for s in sources}
    # If any of the three branches loses its only caller, get_tab_data()'s
    # corresponding branch is dead code -- assert every branch is exercised by
    # at least one real source.
    assert types == VALID_SOURCE_TYPES


# ---------------------------------------------------------------------------
# get_tab_data() -- shape + the reconstructed role-gating branches.
# ---------------------------------------------------------------------------

def test_get_tab_data_unknown_workflow_returns_error():
    result = wtd.get_tab_data("ADMIN", "nope.does_not_exist")
    assert result == {"error": "Unknown workflow 'nope.does_not_exist'"}


def test_get_tab_data_known_workflow_returns_documented_shape():
    result = wtd.get_tab_data("ADMIN", "operations.recon")
    assert set(result.keys()) == {
        "workflow_key",
        "linked_entity",
        "related_entities",
        "sources",
    }
    assert result["workflow_key"] == "operations.recon"
    assert isinstance(result["sources"], list)
    # every appended entry keeps its source id/label and carries a data payload
    for entry in result["sources"]:
        assert "id" in entry and "label" in entry and "data" in entry


def test_self_gated_source_runs_for_any_role():
    # operations.recon's only source is self_gated (fetch(role)) -- it gates
    # internally, not at the branch, so ADMIN gets real (non-error) data.
    result = wtd.get_tab_data("ADMIN", "operations.recon")
    recon = next(s for s in result["sources"] if s["id"] == "recon_queue")
    assert not (isinstance(recon["data"], dict) and "error" in recon["data"])


def test_admin_only_source_forbidden_for_non_admin_allowed_for_admin():
    # administration.audit_monitoring's sources are admin_only -- SALES is blocked
    # at the branch, ADMIN is let through.
    sales = wtd.get_tab_data("SALES", "administration.audit_monitoring")
    for entry in sales["sources"]:
        assert isinstance(entry["data"], dict) and "error" in entry["data"]

    admin = wtd.get_tab_data("ADMIN", "administration.audit_monitoring")
    for entry in admin["sources"]:
        assert not (isinstance(entry["data"], dict) and "error" in entry["data"])


def test_dashboard_source_gated_by_dashboard_access():
    # finance.deal_accounting's finance_dashboard source is a dashboard-type gated
    # via can_access_dashboard(role, "finance"): SALES cannot, FINANCE can.
    sales = wtd.get_tab_data("SALES", "finance.deal_accounting")
    fin_sales = next(s for s in sales["sources"] if s["id"] == "finance_dashboard")
    assert isinstance(fin_sales["data"], dict) and "error" in fin_sales["data"]

    finance = wtd.get_tab_data("FINANCE", "finance.deal_accounting")
    fin_ok = next(s for s in finance["sources"] if s["id"] == "finance_dashboard")
    assert not (isinstance(fin_ok["data"], dict) and "error" in fin_ok["data"])


# ---------------------------------------------------------------------------
# linked_entity handling.
# ---------------------------------------------------------------------------

def test_no_linked_entity_leaves_entity_fields_none():
    result = wtd.get_tab_data("ADMIN", "operations.recon")
    assert result["linked_entity"] is None
    assert result["related_entities"] is None


def test_nonexistent_linked_entity_reports_error_and_no_related():
    result = wtd.get_tab_data(
        "ADMIN", "operations.recon", linked_entity_id="VEH-999999"
    )
    assert isinstance(result["linked_entity"], dict)
    assert "error" in result["linked_entity"]
    # related_entities is only populated when the linked entity resolved cleanly.
    assert result["related_entities"] is None
