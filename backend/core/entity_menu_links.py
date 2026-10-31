"""
core/entity_menu_links.py -- chat "deep link to the right dashboard" suggestions
(session 76). Sam: "when it's clearly leading to showing in dashboard format, lets lead
them to their [dashboard] versus giving a non answer or saying sorry can't do that... can
you pull up the info for John Smith - it should say in the chat would you like to look at
his lead status? (click here) and it pulls up marketing / crm data. would you like to see
his current car contract (pull up in financing / etc."

A static entity_type -> real Top Menu (department, item_key) mapping, same
one-catalog/no-new-engine pattern as every other *_menu.py module in this codebase --
reuses core/menu_catalog.py's ALREADY-CATALOGUED 9-department Top Menu verbatim rather
than inventing new navigation. Scoped (per Sam's answer to a clarifying question) to the
core entity types with an obvious single department home: Lead, Customer, Vehicle,
Deal/FinanceContract, ServiceRecord -- not every one of the ~20 entity types in the graph.

Honest limitation, called out per Sam's answer to a second clarifying question: most Top
Menu items aren't filterable to one specific entity today -- GET /menu/data's
QUERY_CAPABLE_ITEMS (frontend/components/MenuDashPanel.tsx) is just {"vehicles",
"documents"}. So a suggestion either carries `query_capable=True` (today: only
Operations' "vehicles" item, matched against the vehicle's VIN/stock number) and the
frontend pre-fills the search box, or it's `query_capable=False` and the label says so
plainly ("...search for the name there") rather than pretending every department
dashboard can be filtered to one record when it can't yet.
"""

from core.entity_types import (
    LEAD,
    CUSTOMER,
    VEHICLE,
    DEAL,
    FINANCE_CONTRACT,
    SERVICE_RECORD,
)

# entity_type -> list of {department, item_key, label, query_capable, query_field}.
# `query_field` names which attribute on the resolved entity to use as the search query
# when query_capable is True (e.g. a Vehicle's VIN) -- resolved at suggestion-build time,
# not stored here.
ENTITY_MENU_LINKS = {

    LEAD: [
        {
            "department": "Sales",
            "item_key": "prospects",
            "label": "View lead status in Sales",
            "query_capable": False,
        },
    ],

    CUSTOMER: [
        {
            "department": "Sales",
            "item_key": "customers",
            "label": "View customer record in Sales",
            "query_capable": False,
        },
    ],

    VEHICLE: [
        {
            "department": "Operations",
            "item_key": "vehicles",
            "label": "View vehicle record",
            "query_capable": True,
            "query_field": "VIN",
        },
        {
            "department": "Inventory",
            "item_key": "inventory",
            "label": "View in Inventory",
            "query_capable": False,
        },
    ],

    DEAL: [
        {
            "department": "Finance",
            "item_key": "deals",
            "label": "View deal / financing in Finance",
            "query_capable": False,
        },
    ],

    FINANCE_CONTRACT: [
        {
            "department": "Finance",
            "item_key": "funding",
            "label": "View contract funding in Finance",
            "query_capable": False,
        },
    ],

    SERVICE_RECORD: [
        {
            "department": "Service",
            "item_key": "repair_orders",
            "label": "View repair order in Service",
            "query_capable": False,
        },
    ],
}

# Caps how many suggestions ride along on one chat answer -- a handful of entities each
# offering 1-2 links could otherwise produce a wall of buttons under a single message.
MAX_SUGGESTED_ACTIONS = 4


def build_suggested_actions(resolved_entities):
    """resolved_entities: a list of {"id": str, "entity_type": str, "attributes": dict}
    (the exact shape core/ai_tools.py's _serialize_entity already returns). Returns a
    flat, de-duplicated, capped list of real suggestion dicts ready to attach to the
    chat response as `suggested_actions`. Silently skips entity types with no mapping
    (e.g. Document, Campaign) -- same "no match, no suggestion" convention every other
    matcher in core/ai_api.py already follows, not an error."""

    seen = set()
    actions = []

    for entity in resolved_entities:

        entity_type = entity.get("entity_type")
        entity_id = entity.get("id")
        attributes = entity.get("attributes") or {}

        links = ENTITY_MENU_LINKS.get(entity_type)

        if not links:
            continue

        for link in links:

            dedupe_key = (entity_id, link["department"], link["item_key"])

            if dedupe_key in seen:
                continue

            seen.add(dedupe_key)

            action = {
                "entity_id": entity_id,
                "entity_type": entity_type,
                "department": link["department"],
                "item_key": link["item_key"],
                "label": link["label"],
                "query_capable": link["query_capable"],
            }

            if link["query_capable"]:
                query_value = attributes.get(link.get("query_field", ""))
                action["query"] = str(query_value) if query_value else None

            actions.append(action)

            if len(actions) >= MAX_SUGGESTED_ACTIONS:
                return actions

    return actions
