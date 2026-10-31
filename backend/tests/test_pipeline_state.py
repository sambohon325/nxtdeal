"""
Tests for core/pipeline_state.py — the graph-backed replacement for the old
workflow_repository/WorkflowInstance pair (lead pipeline state now lives as attributes
directly on the Lead entity, see CLAUDE.md's "one graph" note, 2026-07-13). Run from
backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import LEAD

from core.pipeline_state import (
    start_pipeline,
    set_pipeline_state,
    get_pipeline_state,
    get_pipeline_state_since,
    get_pipeline_created_at,
    is_in_pipeline,
    get_all_pipeline_entity_ids,
    get_pipeline_summary,
)


@pytest.fixture(autouse=True)
def fresh_ledger():

    ledger.reset()

    yield

    ledger.reset()


def _add_lead(entity_id):

    ledger.add_entity(
        Entity(id=entity_id, entity_type=LEAD, attributes={})
    )


def test_start_pipeline_sets_state_and_timestamps():

    _add_lead("LEAD-1")

    start_pipeline("LEAD-1", initial_state="NEW", timestamp="2026-07-01T00:00:00")

    assert get_pipeline_state("LEAD-1") == "NEW"
    assert get_pipeline_created_at("LEAD-1").isoformat() == "2026-07-01T00:00:00"
    assert get_pipeline_state_since("LEAD-1").isoformat() == "2026-07-01T00:00:00"
    assert is_in_pipeline("LEAD-1") is True


def test_start_pipeline_on_unknown_entity_raises():

    with pytest.raises(ValueError):
        start_pipeline("DOES-NOT-EXIST")


def test_set_pipeline_state_advances_state_but_preserves_created_at():

    _add_lead("LEAD-2")

    start_pipeline("LEAD-2", initial_state="NEW", timestamp="2026-07-01T00:00:00")
    set_pipeline_state("LEAD-2", "CONTACTED", timestamp="2026-07-02T00:00:00")

    assert get_pipeline_state("LEAD-2") == "CONTACTED"
    # PipelineCreatedAt must not move once set — that's what time_to_close.py relies on.
    assert get_pipeline_created_at("LEAD-2").isoformat() == "2026-07-01T00:00:00"
    assert get_pipeline_state_since("LEAD-2").isoformat() == "2026-07-02T00:00:00"


def test_unknown_entity_reads_return_none_not_error():

    assert get_pipeline_state("DOES-NOT-EXIST") is None
    assert get_pipeline_state_since("DOES-NOT-EXIST") is None
    assert get_pipeline_created_at("DOES-NOT-EXIST") is None
    assert is_in_pipeline("DOES-NOT-EXIST") is False


def test_get_all_pipeline_entity_ids_only_includes_entities_with_state():

    _add_lead("LEAD-3")
    _add_lead("LEAD-4")

    start_pipeline("LEAD-3")

    assert get_all_pipeline_entity_ids() == ["LEAD-3"]


def test_get_pipeline_summary_counts_by_state():

    for entity_id, state in [
        ("LEAD-5", "NEW"),
        ("LEAD-6", "CONTACTED"),
        ("LEAD-7", "CONTACTED"),
        ("LEAD-8", "SOLD"),
    ]:
        _add_lead(entity_id)
        start_pipeline(entity_id, initial_state=state)

    assert get_pipeline_summary() == {
        "NEW": 1,
        "CONTACTED": 2,
        "SOLD": 1,
    }
