"""
core/knowledge_pins.py -- Shared Knowledge (2026-07-15, session 72). Sam: "id like
there to be a regular knowledge and a shared knowledge. when you pin something from
the workplace, it should have an option (simular to google docs) for only you to
access, or if you want to share, you can select a department, multiple departments, or
all, and it goes into 'Shared Knowledge'."

"My Knowledge" (the existing plain pin -- frontend/lib/pins.ts) stays exactly what it
was: a private, browser-local bookmark, never touching the backend. This module is
purely additive -- it only ever exists for pins the owner explicitly chose to share.
A KnowledgePin is an ordinary graph entity (owner, visibility, the role list it's
shared with, kind/ref_id/label/tag mirroring frontend/lib/pins.ts's own Pin shape) --
same no-separate-store rule as every other feature in this codebase.

"Select a department... or all" maps onto the same 6 roles core/messaging.py's
CHANNEL_DEFS and core/permissions.py's DASHBOARD_ACCESS already use to gate everything
else in the app -- that's the one real access-control unit that exists here, so
sharing rides on it rather than inventing a second, parallel "department" concept with
no actual enforcement behind it.

No hard delete anywhere in this codebase's graph ledger (core/ledger.py has no
remove_entity) -- "deleting" a shared pin is a soft `active: False` flag, same
resolved/cancelled-flag convention as ComplianceAlert/WorkflowInstance.
"""

from datetime import datetime, timezone

from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.entity_types import KNOWLEDGE_PIN
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE
from core.entity_mentions import link_entity_reference
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH

# Real data-loss bug found and fixed (2026-07-18, codebase-wide save_graph() audit --
# see core/lead_conversion.py's docstring for the running list of confirmed instances).
# This module had ZERO save_graph() calls anywhere since it shipped (session 72) --
# every real shared knowledge pin ever created, retagged, re-shared, or removed had
# been silently discarded on server restart. Fixed below: every mutating function now
# saves directly.

SHARE_ROLES = [ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE]

VISIBILITY_ALL = "all"
VISIBILITY_ROLES = "roles"


def _now():
    return datetime.now(timezone.utc).isoformat()


def _display_name(employee_id):

    entity = ledger.get_entity(employee_id)

    if not entity:
        return None

    attrs = entity.attributes or {}

    if attrs.get("Name"):
        return attrs["Name"]

    if attrs.get("FirstName") and attrs.get("LastName"):
        return f"{attrs['FirstName']} {attrs['LastName']}"

    return None


def _all_pins():
    return [
        entity
        for entity in ledger.get_all().values()
        if entity.entity_type == KNOWLEDGE_PIN
    ]


def _serialize(entity):
    attrs = entity.attributes
    return {
        "id": entity.id,
        "owner_employee_id": attrs.get("owner_employee_id"),
        "owner_name": attrs.get("owner_name"),
        "kind": attrs.get("kind"),
        "ref_id": attrs.get("ref_id"),
        "label": attrs.get("label"),
        "tag": attrs.get("tag"),
        "visibility": attrs.get("visibility"),
        "roles": attrs.get("roles") or [],
        "shared_at": attrs.get("shared_at"),
    }


def create_pin(owner_employee_id, kind, ref_id, label, tag, visibility, roles=None):
    """visibility is "all" or "roles" (roles must be a non-empty subset of
    SHARE_ROLES when "roles"). Returns an error dict on bad input, matching this
    codebase's convention of {"error": ...} rather than raising for caller-facing
    validation failures."""

    if visibility not in (VISIBILITY_ALL, VISIBILITY_ROLES):
        return {"error": f"Unknown visibility '{visibility}' -- expected 'all' or 'roles'."}

    clean_roles = []

    if visibility == VISIBILITY_ROLES:
        clean_roles = [r for r in (roles or []) if r in SHARE_ROLES]

        if not clean_roles:
            return {"error": "Pick at least one department to share with, or choose 'Everyone'."}

    pin_id = id_generator.generate("PIN")

    entity = Entity(
        id=pin_id,
        entity_type=KNOWLEDGE_PIN,
        attributes={
            "owner_employee_id": owner_employee_id,
            "owner_name": _display_name(owner_employee_id),
            "kind": kind,
            "ref_id": ref_id,
            "label": label,
            "tag": tag,
            "visibility": visibility,
            "roles": clean_roles,
            "shared_at": _now(),
            "active": True,
        },
    )

    ledger.add_entity(entity)

    # Session 76 fourth follow-up -- if ref_id actually resolves to a real graph
    # entity (a "profile"/"asset"/"campaign"/"website"/"deal"/"workspace_board" pin's
    # ref_id genuinely is one; a "dashboard"/"visualization"/"workspace_note" pin's
    # ref_id is a query descriptor or a WITEM id, not a graph entity, so this is a
    # no-op for those -- see link_entity_reference's own real-entity check), create a
    # real REFERENCES relationship so "what's been pinned about this" becomes
    # explorable from the entity's own side, not just from the Knowledge sidebar.
    link_entity_reference(pin_id, ref_id, created_by=owner_employee_id)

    save_graph(GRAPH_PATH)

    return _serialize(entity)


def list_pins_for_role(role, employee_id=None):
    """Every active shared pin a role can see -- ADMIN sees everything (matching
    can_access_entity/DASHBOARD_ACCESS's ADMIN-always-passes rule elsewhere), everyone
    else sees "all"-visibility pins plus anything explicitly shared with their role.
    `employee_id`, if given, also always includes the caller's own shared pins even if
    their current role somehow isn't in the share list (e.g. a role change after
    sharing) -- an owner should never lose sight of something they shared."""

    results = []

    for entity in _all_pins():

        attrs = entity.attributes

        if not attrs.get("active", True):
            continue

        visible = (
            role == ADMIN
            or attrs.get("visibility") == VISIBILITY_ALL
            or role in (attrs.get("roles") or [])
            or (employee_id and attrs.get("owner_employee_id") == employee_id)
        )

        if visible:
            results.append(_serialize(entity))

    results.sort(key=lambda p: p["shared_at"] or "", reverse=True)

    return results


def _can_modify(entity, employee_id, role):
    return role == ADMIN or entity.attributes.get("owner_employee_id") == employee_id


def retag_pin(pin_id, employee_id, role, tag):

    entity = ledger.get_entity(pin_id)

    if not entity or entity.entity_type != KNOWLEDGE_PIN:
        return {"error": "Shared knowledge pin not found."}

    if not _can_modify(entity, employee_id, role):
        return {"error": "Only the person who shared this (or an Admin) can retag it."}

    entity.attributes["tag"] = tag.strip() or "General"

    save_graph(GRAPH_PATH)

    return _serialize(entity)


def update_sharing(pin_id, employee_id, role, add_roles=None, set_all=False):
    """Widens an existing pin's sharing -- backs the drag-into-a-channel/DM confirm
    flow ("it will ask if you want to change the access so that you know that its
    going to be accessible"). Only ever widens, never narrows (narrowing is
    delete_pin + re-share, an explicit separate action) -- accidental narrowing while
    dragging something into a chat would be a much worse surprise than accidental
    widening."""

    entity = ledger.get_entity(pin_id)

    if not entity or entity.entity_type != KNOWLEDGE_PIN:
        return {"error": "Shared knowledge pin not found."}

    if not _can_modify(entity, employee_id, role):
        return {"error": "Only the person who shared this (or an Admin) can change who it's shared with."}

    if set_all:
        entity.attributes["visibility"] = VISIBILITY_ALL
        entity.attributes["roles"] = []
    elif add_roles:
        existing = set(entity.attributes.get("roles") or [])
        existing.update(r for r in add_roles if r in SHARE_ROLES)
        entity.attributes["roles"] = sorted(existing)
        if entity.attributes.get("visibility") != VISIBILITY_ALL:
            entity.attributes["visibility"] = VISIBILITY_ROLES

    save_graph(GRAPH_PATH)

    return _serialize(entity)


def delete_pin(pin_id, employee_id, role):

    entity = ledger.get_entity(pin_id)

    if not entity or entity.entity_type != KNOWLEDGE_PIN:
        return {"error": "Shared knowledge pin not found."}

    if not _can_modify(entity, employee_id, role):
        return {"error": "Only the person who shared this (or an Admin) can remove it from Shared Knowledge."}

    entity.attributes["active"] = False

    save_graph(GRAPH_PATH)

    return {"ok": True}
