"""Rewritten 2026-07-13: pipeline state no longer has its own storage module
(core/workflow_storage.py + storage/workflows.json are retired) — it's just attributes on
the Lead entity, persisted/reloaded by core/storage.py's save_graph()/load_graph() like
everything else on the graph. See CLAUDE.md's "one graph" note. This now exercises that
save/load round trip instead."""

import tempfile
import os

from core.entities import Entity
from core.dealeros import ledger
from core.entity_types import LEAD

from core.lead_workflows import (
    create_lead_workflow,
    advance_lead_workflow
)

from core.pipeline_state import (
    get_pipeline_state
)

from core.storage import save_graph, load_graph

ledger.add_entity(
    Entity(id="LEAD-00001", entity_type=LEAD, attributes={})
)

create_lead_workflow(
    "LEAD-00001"
)

advance_lead_workflow(
    "LEAD-00001",
    "CONTACTED"
)

fd, path = tempfile.mkstemp(suffix=".json")
os.close(fd)

save_graph(path)

ledger.reset()

load_graph(path)

os.remove(path)

print(
    "Lead:",
    "LEAD-00001"
)

print(
    "State after reload:",
    get_pipeline_state("LEAD-00001")
)
