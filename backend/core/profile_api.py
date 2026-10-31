"""
Entity 360 profile — backs GET /profile/{entity_id}. core/queries.py already had
get_customer_360()/get_employee_360()/get_vehicle_360() (Phase 1-7 work) but nothing ever
called them: no route, no frontend page. This wires them up behind a single role-filtered
entry point that dispatches on the entity's type, instead of three separate routes the
frontend would have to know to pick between.

Every entity bundled into a profile (not just the top-level one) is filtered through
core/security.py's can_access_entity(role, entity_type) — the same rule Phase 9 wired into
GET /search, GET /entity/{id}, and core/ai_tools.py. A role that can't see finance
contracts directly (e.g. SALES) shouldn't see them smuggled into a customer's profile
either — a naive "just return get_customer_360()'s dict" would have leaked exactly that.
"""

from core.repository import repository
from core.security import can_access_entity
from core.entity_types import CUSTOMER, EMPLOYEE, VEHICLE

from core.queries import (
    get_customer_360,
    get_employee_360,
    get_vehicle_360,
    get_graph_view,
)


def _serialize(entity):

    if not entity:
        return None

    return {
        "id": entity.id,
        "entity_type": entity.entity_type,
        "attributes": entity.attributes,
    }


def _filter_one(role, entity):

    if not entity:
        return None

    if not can_access_entity(role, entity.entity_type):
        return None

    return _serialize(entity)


def _filter_many(role, entities):

    return [
        _serialize(entity)
        for entity in entities
        if entity and can_access_entity(role, entity.entity_type)
    ]


def get_profile(role, entity_id):

    entity = repository.get_entity(entity_id)

    if not entity:

        return {"error": "Entity not found"}

    if not can_access_entity(role, entity.entity_type):

        return {"error": "Forbidden: your role cannot access this entity type"}

    if entity.entity_type == CUSTOMER:

        profile = get_customer_360(entity_id)

        return {
            "entity_type": CUSTOMER,
            "customer": _filter_one(role, profile["customer"]),
            "finances": _filter_many(role, profile["finances"]),
            "vehicles": _filter_many(role, profile["vehicles"]),
            "service_records": _filter_many(role, profile["service_records"]),
            "lead_sources": _filter_many(role, profile["lead_sources"]),
            "documents": _filter_many(role, profile["documents"]),
        }

    if entity.entity_type == EMPLOYEE:

        profile = get_employee_360(entity_id)

        return {
            "entity_type": EMPLOYEE,
            "employee": _filter_one(role, profile["employee"]),
            "customers": _filter_many(role, profile["customers"]),
            "leads": _filter_many(role, profile["leads"]),
        }

    if entity.entity_type == VEHICLE:

        profile = get_vehicle_360(entity_id)

        return {
            "entity_type": VEHICLE,
            "vehicle": _filter_one(role, profile["vehicle"]),
            "owners": _filter_many(role, profile["owners"]),
            "finance_contracts": _filter_many(role, profile["finance_contracts"]),
            "service_records": _filter_many(role, profile["service_records"]),
            "documents": _filter_many(role, profile["documents"]),
            "images": _filter_many(role, profile["images"]),
        }

    # No dedicated 360 view for this entity type (Lead, FinanceContract, ServiceRecord,
    # Lender, Document, Image, ...) — fall back to the entity plus its direct
    # relationships, same shape get_graph_view() already returns, filtered the same way.
    graph = get_graph_view(entity_id)

    return {
        "entity_type": entity.entity_type,
        "entity": _filter_one(role, graph["entity"]),
        "relationships": [
            {
                "direction": item["direction"],
                "relationship": item["relationship"],
                "entity": _serialize(item["entity"]),
            }
            for item in graph["relationships"]
            if item["entity"] and can_access_entity(role, item["entity"].entity_type)
        ],
    }
