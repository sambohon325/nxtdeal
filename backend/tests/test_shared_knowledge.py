"""
Tests for the fleet's SHARED AI KNOWLEDGE (core/shared_knowledge.py +
core/shared_knowledge_api.py) — Pillar 5, 2026-07-23. Run from backend/ with `pytest`.

Covers: the pool starts empty and reads cleanly; contributing an insight persists a real
graph entity and re-contributing the same title UPSERTS rather than duplicating; publishing
promotes each team's genuinely-recognized workflows into the one pool and is idempotent;
reading for a section splits own vs. other-team knowledge (the point of the pillar); the
LIVE cross-team analysis flags a sequence 2+ teams independently recognized and ignores a
single-team one; admin gates on publish/delete; and everything lands as SharedKnowledgeEntry
in the single ledger (no side store).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entity_types import SHARED_KNOWLEDGE_ENTRY
from core.permissions import ADMIN, SALES

from core import bot_fleet
from core import shared_knowledge
from core import shared_knowledge_api


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield
    ledger.reset()


def _record_recognized_workflow(section, steps, actor="EMP-1", runs=2):
    """Record `steps` as a repeated workflow for `section` enough times that bot_fleet
    recognizes it (>= MIN_WORKFLOW_OCCURRENCES). Each run gets its own workflow_key so the
    steps chain into one sequence per run."""
    for r in range(runs):
        for action in steps:
            bot_fleet.record_workflow_step(
                section, actor, action, workflow_key=f"{section}-run{r}"
            )


# ---- empty pool ---------------------------------------------------------------------

def test_empty_pool_reads_cleanly():
    knowledge = shared_knowledge.read_shared_knowledge()
    assert knowledge["entry_count"] == 0
    assert knowledge["entries"] == []
    assert knowledge["cross_team_workflows"] == []

    summary = shared_knowledge.knowledge_summary()
    assert summary["total_entries"] == 0
    assert summary["cross_team_pattern_count"] == 0


# ---- contributing insights ----------------------------------------------------------

def test_contribute_insight_persists_graph_entity():
    result = shared_knowledge.contribute_insight(
        "sales", "EMP-7", "Always confirm trade payoff", "Call the lienholder same day."
    )
    assert result["created"] is True
    entry = result["entry"]
    assert entry["kind"] == "insight"
    assert entry["source_section"] == "sales"
    assert entry["title"] == "Always confirm trade payoff"

    # It's an ordinary entity in the ONE ledger — not a side store.
    entities = [e for e in ledger.get_all().values() if e.entity_type == SHARED_KNOWLEDGE_ENTRY]
    assert len(entities) == 1
    assert entities[0].id.startswith("SKE")


def test_reContributing_same_title_updates_not_duplicates():
    shared_knowledge.contribute_insight("sales", "EMP-7", "Trade tip", "First version.")
    second = shared_knowledge.contribute_insight("sales", "EMP-9", "Trade tip", "Better version.")
    assert second["created"] is False

    pool = shared_knowledge.read_shared_knowledge()
    assert pool["entry_count"] == 1
    assert pool["entries"][0]["body"] == "Better version."
    assert pool["entries"][0]["contributor"] == "EMP-9"


def test_contribute_insight_validates_input():
    assert "error" in shared_knowledge.contribute_insight("not-a-team", "EMP-1", "t", "b")
    assert "error" in shared_knowledge.contribute_insight("sales", "EMP-1", "", "b")
    assert "error" in shared_knowledge.contribute_insight("sales", "EMP-1", "t", "")


# ---- publishing recognized workflows ------------------------------------------------

def test_publish_promotes_recognized_workflows_into_pool():
    _record_recognized_workflow("sales", ["create_deal", "add_scenario", "select_scenario"])
    _record_recognized_workflow("finance", ["choose_financing", "fund"])

    result = shared_knowledge.publish_recognized_workflows("ADMIN-1")
    assert result["published"] >= 2
    assert set(result["sections"]) >= {"sales", "finance"}

    pool = shared_knowledge.read_shared_knowledge()
    kinds = {e["kind"] for e in pool["entries"]}
    assert kinds == {"workflow"}
    sales_wf = [e for e in pool["entries"] if e["source_section"] == "sales"]
    assert sales_wf and sales_wf[0]["steps"][0] == "create_deal"
    assert sales_wf[0]["occurrences"] >= 2


def test_publish_is_idempotent():
    _record_recognized_workflow("sales", ["create_deal", "add_scenario"])
    first = shared_knowledge.publish_recognized_workflows("ADMIN-1")
    before = shared_knowledge.read_shared_knowledge()["entry_count"]

    second = shared_knowledge.publish_recognized_workflows("ADMIN-1")
    after = shared_knowledge.read_shared_knowledge()["entry_count"]

    assert after == before  # no duplication
    assert second["published"] == 0
    assert second["updated"] >= first["published"]


# ---- the point of the pillar: cross-pollination -------------------------------------

def test_read_for_section_splits_own_vs_other_teams():
    shared_knowledge.contribute_insight("sales", "EMP-1", "Sales tip", "body")
    shared_knowledge.contribute_insight("finance", "EMP-2", "Finance tip", "body")

    view = shared_knowledge.read_shared_knowledge(for_section="sales")
    assert view["for_section"] == "sales"
    assert {e["title"] for e in view["own"]} == {"Sales tip"}
    assert {e["title"] for e in view["from_other_teams"]} == {"Finance tip"}


def test_cross_team_workflow_detected_when_two_teams_recognize_it():
    shared = ["intake", "review", "close"]
    _record_recognized_workflow("sales", shared)
    _record_recognized_workflow("finance", shared)
    _record_recognized_workflow("service", ["ro_open", "ro_close"])  # single-team only

    cross = shared_knowledge.cross_team_workflows()
    matched = [c for c in cross if c["steps"] == shared]
    assert len(matched) == 1
    assert matched[0]["team_count"] == 2
    assert set(matched[0]["teams"]) == {"sales", "finance"}

    # The service-only sequence is NOT cross-team.
    assert all(c["steps"] != ["ro_open", "ro_close"] for c in cross)


# ---- summary + delete ---------------------------------------------------------------

def test_summary_counts_by_kind_and_section():
    shared_knowledge.contribute_insight("sales", "EMP-1", "Tip A", "body")
    _record_recognized_workflow("finance", ["a", "b"])
    shared_knowledge.publish_recognized_workflows("ADMIN-1")

    summary = shared_knowledge.knowledge_summary()
    assert summary["insight_entries"] == 1
    assert summary["workflow_entries"] >= 1
    assert set(summary["contributing_sections"]) >= {"sales", "finance"}


def test_delete_entry_removes_from_graph():
    entry = shared_knowledge.contribute_insight("sales", "EMP-1", "Tip", "body")["entry"]
    assert shared_knowledge.delete_entry(entry["id"], "ADMIN-1")["deleted"] == entry["id"]
    assert shared_knowledge.read_shared_knowledge()["entry_count"] == 0
    assert shared_knowledge.delete_entry("SKE-nope", "ADMIN-1").get("error")


# ---- API gates ----------------------------------------------------------------------

def test_api_publish_and_delete_are_admin_only():
    _record_recognized_workflow("sales", ["a", "b"])

    assert "error" in shared_knowledge_api.publish_recognized_workflows_api(SALES, "EMP-1")
    ok = shared_knowledge_api.publish_recognized_workflows_api(ADMIN, "ADMIN-1")
    assert "error" not in ok

    entry = shared_knowledge.contribute_insight("sales", "EMP-1", "T", "b")["entry"]
    assert "error" in shared_knowledge_api.delete_shared_entry_api(SALES, "EMP-1", entry["id"])
    assert "error" not in shared_knowledge_api.delete_shared_entry_api(ADMIN, "ADMIN-1", entry["id"])


def test_api_read_and_contribute_open_to_any_role():
    contributed = shared_knowledge_api.contribute_insight_api("EMP-3", "sales", "Tip", "body")
    assert contributed["created"] is True

    read = shared_knowledge_api.get_shared_knowledge_api(SALES, section="sales")
    assert read["knowledge"]["entry_count"] == 1
    assert read["summary"]["total_entries"] == 1
