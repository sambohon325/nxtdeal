"""
Lead -> Customer conversion (Sales sub-menu spec, session 92 follow-up). Sam's
Overview "Action Center" asks for a one-click "Create Deal" from a lead -- but
core/deals.py's create_deal() requires a real Customer entity, and a Lead is not a
Customer (different real-world objects, same "one entity type per real-world object"
discipline this codebase uses everywhere). There was no live conversion mechanism
anywhere in this codebase.

The relationship this uses -- BECAME (Lead -> Customer) -- already existed in
core/relationship_types.py under a "Lead Lifecycle" heading and is exactly what
imports/conversion_import.py has used for historical CSV-imported conversions since
this project's early sessions; this is the first LIVE caller of it. A converted
Lead is indistinguishable from a historically-imported conversion to every existing
dashboard/profile view that already reads BECAME, same "no parallel model" discipline
as core/deals.py's fund_deal() or core/lead_intake.py's create_lead().

Real, pre-existing data-loss bug found and fixed (2026-07-18, Marketing Growth
Platform, Attribution Engine slice) -- the same missing-save_graph bug class
found repeatedly this session (core/deals.py/core/marketing_lists.py, session
105; core/campaigns.py/core/email_templates.py, this same slice sequence):
convert_lead_to_customer() had never once called save_graph() since it shipped
(session 92 follow-up). Every real Lead-to-Customer conversion ever done
through the live app was silently discarded on server restart. Fixed below --
discovered while building a real seed script to backfill BECAME relationships
for the new Attribution Engine's Channel Mix, which found zero BECAME
relationships anywhere in the live seed graph and traced the cause here.
"""

from datetime import datetime, timezone

from core.dealeros import ledger, id_generator, registry
from core.entities import Entity
from core.entity_types import LEAD, CUSTOMER
from core.relationships import Relationship
from core.relationship_types import BECAME
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH


def _now():
    return datetime.now(timezone.utc).isoformat()


def convert_lead_to_customer(lead_id, employee_id):

    lead = ledger.get_entity(lead_id)

    if not lead or lead.entity_type != LEAD:
        return {"error": f"Lead '{lead_id}' not found"}

    if lead.attributes.get("ConvertedCustomerID"):
        existing = ledger.get_entity(lead.attributes["ConvertedCustomerID"])
        if existing:
            return {"error": f"This lead was already converted to customer {existing.id}", "customer_id": existing.id}

    customer_id = id_generator.generate("CUST")

    customer = Entity(
        id=customer_id,
        entity_type=CUSTOMER,
        attributes={
            "FirstName": lead.attributes.get("FirstName", ""),
            "LastName": lead.attributes.get("LastName", ""),
            "Email": lead.attributes.get("Email", ""),
            "Phone": lead.attributes.get("Phone", lead.attributes.get("phone", "")),
            "City": lead.attributes.get("City", ""),
            "State": lead.attributes.get("State", ""),
            # CreditScore is deliberately absent -- Lead carries no credit data
            # anywhere in this codebase, and fabricating one here would contradict
            # every other module's "real data or an honest gap" rule.
            "ConvertedFromLeadID": lead_id,
            "ConvertedAt": _now(),
            "ConvertedBy": employee_id,
        },
    )

    ledger.add_entity(customer)
    registry.register_customer(customer_id, customer_id)

    ledger.add_relationship(Relationship(source_id=lead_id, target_id=customer_id, relationship_type=BECAME))

    lead.attributes["ConvertedCustomerID"] = customer_id
    lead.attributes["ConvertedAt"] = _now()

    save_graph(GRAPH_PATH)

    return customer
