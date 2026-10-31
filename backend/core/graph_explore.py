"""
core/graph_explore.py -- generic, role-gated multi-hop graph traversal (session 76
fourth follow-up). Sam: "that knowledge needs to be explorable at all points, so i
should be able to click on a text translation of a graph and find lists of the people
that its referencing and explore who they are individually... the same in reverse."

Three one-hop building blocks already existed before this module
(core/queries.py's get_entity_relationships/get_graph_view, core/ai_tools.py's
get_related_entities) plus one unused multi-hop function (core/queries.py's
get_graph_tree, depth=2, no ACL, no serialization, no breadth cap -- never wired to any
route). This module is the real, production version of that idea: a bounded BFS out
from a starting entity, filtered node-by-node through the SAME access rules that
already gate search/profile/dashboards (Sam's explicit scoping answer: reuse today's
role-based access exactly, nothing new to design), with relationship direction and
provenance included so the explorer can show "linked via a message Sam sent on
July 15," not just an unlabeled connection.

Two entity types need a sharper check than the generic can_access_entity(role,
entity_type), because their real visibility rule was never about entity_type at all:
  - Message: channel messages are gated by core/messaging.py's can_access_channel
    (role-based, same as the Communications panel); direct messages are only visible
    to their two participants (or ADMIN) -- core/entity_types.MESSAGE has no
    ENTITY_ACCESS entry, so falling back to can_access_entity would incorrectly deny
    everyone but ADMIN.
  - KnowledgePin: gated by core/knowledge_pins.py's own visibility rule (ADMIN, "all"
    visibility, role in the shared roles list, or the pin's own owner) -- same reason.
Every other entity type uses can_access_entity exactly as-is.
"""

from core.dealeros import ledger
from core.entity_types import MESSAGE, KNOWLEDGE_PIN, API_KEY
from core.permissions import ADMIN
from core.security import can_access_entity
from core.messaging import can_access_channel
from core.knowledge_pins import VISIBILITY_ALL

# Caps, not user-configurable beyond the depth query param -- a real dealership graph
# has high-degree nodes (an Employee could show up in hundreds of messages once
# MENTIONS relationships exist) and an unbounded BFS at depth 3 could return a huge,
# slow payload. Matches this codebase's existing "cap at N, don't pretend it's
# everything" convention (e.g. core/ai_tools.py's search_entities/get_related_entities
# both cap at 20).
MAX_DEPTH = 3
DEFAULT_DEPTH = 2
MAX_CHILDREN_PER_NODE = 12


def _serialize_entity(entity):
    return {
        "id": entity.id,
        "entity_type": entity.entity_type,
        "attributes": entity.attributes,
    }


def _can_view(entity, role, employee_id):

    # Keep the internal-key boundary ahead of the explorer's ADMIN shortcut.
    if entity.entity_type == API_KEY:
        return can_access_entity(role, entity.entity_type)

    if role == ADMIN:
        return True

    if entity.entity_type == MESSAGE:
        attrs = entity.attributes or {}

        if attrs.get("kind") == "direct":
            return employee_id in (attrs.get("sender_id"), attrs.get("recipient_id"))

        return can_access_channel(role, attrs.get("channel_key"))

    if entity.entity_type == KNOWLEDGE_PIN:
        attrs = entity.attributes or {}

        if not attrs.get("active", True):
            return False

        return (
            attrs.get("visibility") == VISIBILITY_ALL
            or role in (attrs.get("roles") or [])
            or attrs.get("owner_employee_id") == employee_id
        )

    return can_access_entity(role, entity.entity_type)


def explore_entity(entity_id, role, employee_id, depth=DEFAULT_DEPTH):
    """Bounded BFS out from entity_id, every node individually access-checked via
    _can_view -- a node the caller can't see is dropped from the tree entirely (not
    shown as a locked placeholder, not traversed through), same "don't reveal that
    something exists at all" posture core/security.py's can_access_entity already
    implies for the one-hop endpoints. Returns {"error": ...} if the root itself isn't
    found or isn't visible to the caller.

    Deliberately LEVEL-BY-LEVEL (a real BFS queue), not depth-first recursion. A first
    draft used depth-first recursion with one shared `visited` set and had a real bug a
    live smoke test caught: a node with a DIRECT edge to the root (e.g. a chat message
    that mentions the root Customer directly) could get claimed first by an unrelated
    deeper branch (e.g. via a Vehicle the customer purchased, if that branch happened
    to be visited first) and end up buried two hops down instead of showing as the
    root's own direct connection. Processing one whole level at a time before starting
    the next guarantees the shortest real path to any node is the one that's shown,
    which is what "explore outward from an entity" should mean."""

    depth = max(1, min(int(depth or DEFAULT_DEPTH), MAX_DEPTH))

    root = ledger.get_entity(entity_id)

    if not root:
        return {"error": "Entity not found"}

    if not _can_view(root, role, employee_id):
        return {"error": "Forbidden: your role cannot access this entity"}

    visited = {entity_id}
    children_of = {}
    truncated_of = {}
    current_level = [entity_id]

    for _ in range(depth):

        next_level = []

        for current_id in current_level:

            candidates = []

            for relationship in ledger.get_relationships():

                if relationship.source_id == current_id:
                    direction, next_id = "OUT", relationship.target_id
                elif relationship.target_id == current_id:
                    direction, next_id = "IN", relationship.source_id
                else:
                    continue

                if next_id in visited:
                    continue

                other = ledger.get_entity(next_id)

                if not other or not _can_view(other, role, employee_id):
                    continue

                candidates.append((direction, relationship, next_id, other))

            kept = candidates[:MAX_CHILDREN_PER_NODE]
            truncated_of[current_id] = max(0, len(candidates) - len(kept))

            level_children = []

            for direction, relationship, next_id, other in kept:

                visited.add(next_id)
                next_level.append(next_id)

                level_children.append({
                    "direction": direction,
                    "relationship_type": relationship.relationship_type,
                    "created_by": relationship.created_by,
                    "created_at": relationship.created_at,
                    "entity": _serialize_entity(other),
                    "children": [],
                    "truncated_children": 0,
                })

            children_of[current_id] = level_children

        current_level = next_level

    def attach(current_id):

        nodes = children_of.get(current_id, [])

        for node in nodes:
            child_id = node["entity"]["id"]
            node["children"] = attach(child_id)
            node["truncated_children"] = truncated_of.get(child_id, 0)

        return nodes

    root_children = attach(entity_id)

    return {
        "entity": _serialize_entity(root),
        "children": root_children,
        "truncated_children": truncated_of.get(entity_id, 0),
        "depth": depth,
    }
