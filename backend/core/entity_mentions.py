"""
core/entity_mentions.py -- turns a free-text entity-ID mention (e.g. "check on
CUS-00042 before you call") into a REAL graph relationship, not just a client-side
link. Session 76 fourth follow-up (Sam: "a customer should link to the inventory, to
the marketing data between the two, and the knowledge note created, a chat between the
sales department and a sales rep, etc... it should all be accessible at every point...
the same in reverse").

Before this module, frontend/components/MessageContent.tsx already regex-matched entity
IDs in message text and rendered them as clickable links -- but that was purely a
client-side rendering trick with nothing behind it in the graph, so there was no way to
go the other direction (from a Customer entity, see which messages mentioned them).
This module is the backend half: the same ID shape, matched server-side at the moment a
Message or KnowledgePin is created, and turned into a real MENTIONS/REFERENCES
relationship (core/relationship_types.py) so ordinary one-hop traversal
(core/queries.py's get_entity_relationships, core/ai_tools.py's get_related_entities,
and the new core/graph_explore.py) surfaces it automatically in both directions.

Deliberately conservative: a candidate substring is only linked if it resolves to a
REAL, currently-existing entity in the ledger (`ledger.get_entity(candidate)`) -- an
ID-shaped string that doesn't match anything real is left alone rather than creating a
dangling relationship, same "never fabricate, only link what's real" convention this
codebase follows everywhere else (see core/workflow_tab_data.py's REAL_SOURCES).
"""

import re
from datetime import datetime, timezone

from core.dealeros import ledger
from core.relationships import Relationship
from core.relationship_types import MENTIONS, REFERENCES

# Same shape frontend/components/MessageContent.tsx's regex already matches
# ([A-Z]{2,10}-\d{4,6}) -- kept in sync deliberately, since both are looking for the
# same core/id_generator.py-produced ID pattern (VEH-00042, CUS-00001, MSG-00317, ...).
_MENTION_PATTERN = re.compile(r"\b[A-Z]{2,10}-\d{4,6}\b")


def _now():
    return datetime.now(timezone.utc).isoformat()


def extract_mentioned_entity_ids(text):
    """Returns the real, currently-existing entity IDs found in `text`. A candidate
    that matches the ID shape but doesn't resolve to any entity in the ledger is
    silently dropped, not linked."""

    if not text:
        return []

    candidates = set(_MENTION_PATTERN.findall(text))

    return [entity_id for entity_id in candidates if ledger.get_entity(entity_id)]


def link_entity_mentions(source_id, text, relationship_type=MENTIONS, created_by=None):
    """Creates a real relationship from source_id (a Message or KnowledgePin entity
    already added to the ledger) to every real entity referenced by ID in `text`.
    Returns the list of entity IDs actually linked. Safe to call with empty/None text
    (returns an empty list, no-op)."""

    linked = []
    created_at = _now()

    for entity_id in extract_mentioned_entity_ids(text):

        if entity_id == source_id:
            continue

        ledger.add_relationship(Relationship(
            source_id=source_id,
            target_id=entity_id,
            relationship_type=relationship_type,
            created_by=created_by,
            created_at=created_at,
        ))

        linked.append(entity_id)

    return linked


def link_entity_reference(source_id, ref_id, created_by=None):
    """Single-target version of link_entity_mentions, for core/knowledge_pins.py's
    create_pin() -- ref_id is already a specific candidate (not free text to scan), so
    this just checks it resolves to a real, different entity before linking. Returns
    True if a relationship was created."""

    if not ref_id or ref_id == source_id:
        return False

    if not ledger.get_entity(ref_id):
        return False

    ledger.add_relationship(Relationship(
        source_id=source_id,
        target_id=ref_id,
        relationship_type=REFERENCES,
        created_by=created_by,
        created_at=_now(),
    ))

    return True
