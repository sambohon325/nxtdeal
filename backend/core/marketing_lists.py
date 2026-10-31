"""
Marketing Lists (session 82) -- Sam: "under lists we need to be able to click on the
list names and have them show as a list of names lets say in a list of 25
individuals, with a page up and down also adjustable by 25, 50, 100... its really
there you'd be able to start to curate marketing lists for campaigns." And later,
about the same feature: "this is actually a functionality that is going to appear on
the sales side as well."

A MarketingList is an ordinary graph entity: a named, curated collection of real
Customer/Lead ids. Membership is stored as a plain `member_ids` array (whole-object
persistence for the list's own fields, same pattern as core/email_templates.py's
`blocks`) rather than a MEMBER_OF relationship per member -- a list's membership is
edited as a bounded set (add/remove), not incrementally streamed, so there's no real
graph-traversal benefit to a relationship here, and a plain array keeps pagination
trivial (slice the array, resolve each id).

A list can be built two ways:
  1. build_list_from_pool() -- seeded from one of the real live audience pools
     core/campaigns.py's build_audience() already computes (finance_renewal/
     inventory_ads/retention/accessory_accelerator/general). Re-runs the builder
     server-side against the full graph, not just whatever sample happened to be on
     screen, so the list's membership is the complete matching set at save time.
  2. create_list() + add_members() -- manual, or seeded from an explicit id list the
     caller already has in hand (e.g. the Equity Mining pool, which has no
     campaign_type/build_audience() builder behind it -- see
     core/opportunities_actions.py).

Once seeded, membership is a real, editable snapshot -- a marketer can remove an
obviously-wrong entry before a campaign ever targets the list -- not a live query that
silently changes underneath them.
"""

from datetime import datetime, timezone

from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.entity_types import MARKETING_LIST, CUSTOMER, LEAD
from core.campaigns import build_audience
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH


def _now():
    return datetime.now(timezone.utc).isoformat()


def _all_lists():
    return [e for e in ledger.get_all().values() if e.entity_type == MARKETING_LIST]


def create_list(name, created_by, description=""):

    entity = Entity(
        id=id_generator.generate("LIST"),
        entity_type=MARKETING_LIST,
        attributes={
            "name": name,
            "description": description or "",
            "member_ids": [],
            "source": "manual",
            "created_by": created_by,
            "created_at": _now(),
            "updated_at": _now(),
        },
    )

    ledger.add_entity(entity)
    save_graph(GRAPH_PATH)

    return entity


def build_list_from_pool(name, created_by, campaign_type_key, params, description=""):
    """Seeds a new list's full membership from one of the real live audience pools --
    the exact same builder the CRM's Campaigns/Lists tabs already preview against, so
    "Save as List" always matches what the pool actually contains, not just the 5-10
    on-screen sample rows."""

    members = build_audience(campaign_type_key, params or {})

    entity = Entity(
        id=id_generator.generate("LIST"),
        entity_type=MARKETING_LIST,
        attributes={
            "name": name,
            "description": description or "",
            "member_ids": [m.id for m in members],
            "source": f"pool:{campaign_type_key}",
            "created_by": created_by,
            "created_at": _now(),
            "updated_at": _now(),
        },
    )

    ledger.add_entity(entity)
    save_graph(GRAPH_PATH)

    return entity


def get_list(list_id):

    entity = ledger.get_entity(list_id)

    if entity and entity.entity_type == MARKETING_LIST:
        return entity

    return None


_EDITABLE_FIELDS = {"name", "description"}


def update_list(list_id, patch):

    entity = get_list(list_id)

    if not entity:
        return None

    for key, value in (patch or {}).items():
        if key in _EDITABLE_FIELDS:
            entity.attributes[key] = value

    entity.attributes["updated_at"] = _now()
    save_graph(GRAPH_PATH)

    return entity


def add_members(list_id, entity_ids):

    entity = get_list(list_id)

    if not entity:
        return None

    existing = list(entity.attributes.get("member_ids") or [])
    existing_set = set(existing)
    added = []

    for eid in entity_ids or []:

        if eid in existing_set:
            continue

        target = ledger.get_entity(eid)

        if target and target.entity_type in (CUSTOMER, LEAD):
            existing.append(eid)
            existing_set.add(eid)
            added.append(eid)

    entity.attributes["member_ids"] = existing
    entity.attributes["updated_at"] = _now()
    save_graph(GRAPH_PATH)

    return {"list": entity, "added": added}


def remove_members(list_id, entity_ids):

    entity = get_list(list_id)

    if not entity:
        return None

    remove_set = set(entity_ids or [])

    entity.attributes["member_ids"] = [
        m for m in (entity.attributes.get("member_ids") or []) if m not in remove_set
    ]
    entity.attributes["updated_at"] = _now()
    save_graph(GRAPH_PATH)

    return entity


def delete_list(list_id):
    """No ledger.remove_entity exists anywhere in this codebase (append-only graph,
    same rule core/lead_assignment.py's relationships already follow) -- "deleting" a
    list marks it archived instead, matching the honest-append-only convention rather
    than pretending a hard delete happened."""

    entity = get_list(list_id)

    if not entity:
        return None

    entity.attributes["archived"] = True
    entity.attributes["updated_at"] = _now()
    save_graph(GRAPH_PATH)

    return entity


def list_lists(created_by=None, include_archived=False):

    lists = _all_lists()

    if not include_archived:
        lists = [l for l in lists if not l.attributes.get("archived")]

    if created_by:
        lists = [l for l in lists if l.attributes.get("created_by") == created_by]

    lists.sort(key=lambda l: (l.attributes.get("updated_at", ""), l.id), reverse=True)

    return lists


def _serialize_member(entity):

    if entity.entity_type == CUSTOMER:

        name = f"{entity.attributes.get('FirstName', '')} {entity.attributes.get('LastName', '')}".strip()

        return {
            "id": entity.id,
            "entity_type": CUSTOMER,
            "name": name or entity.id,
            "phone": entity.attributes.get("Phone"),
            "email": entity.attributes.get("Email"),
        }

    if entity.entity_type == LEAD:

        return {
            "id": entity.id,
            "entity_type": LEAD,
            "name": entity.attributes.get("Name") or entity.attributes.get("FullName") or " ".join(str(entity.attributes.get(k) or "") for k in ("FirstName", "LastName")).strip() or entity.attributes.get("LeadID") or entity.id,
            "phone": entity.attributes.get("Phone"),
            "email": entity.attributes.get("Email"),
            "source": entity.attributes.get("Source"),
            "pipeline_state": entity.attributes.get("PipelineState"),
        }

    return {"id": entity.id, "entity_type": entity.entity_type, "name": entity.id}


def get_list_members(list_id, page=1, page_size=25, entity_type_filter=None):
    """Real server-side pagination -- Sam: "click on the list names and have them show
    as a list of names lets say in a list of 25 individuals, with a page up and down
    also adjustable by 25, 50, 100." Defaults to page 1 / 25 per page, page_size capped
    at 200 to keep one response bounded."""

    entity = get_list(list_id)

    if not entity:
        return None

    member_ids = entity.attributes.get("member_ids") or []
    members = [ledger.get_entity(mid) for mid in member_ids]
    members = [m for m in members if m is not None]

    if entity_type_filter:
        members = [m for m in members if m.entity_type == entity_type_filter]

    total = len(members)
    page_size = max(1, min(int(page_size or 25), 200))
    page = max(1, int(page or 1))
    start = (page - 1) * page_size
    page_members = members[start:start + page_size]

    return {
        "list_id": list_id,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, -(-total // page_size)),
        "members": [_serialize_member(m) for m in page_members],
    }
