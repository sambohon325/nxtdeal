"""
Backfills real Lead -> Customer conversions and a handful of real funded Deals
tied back to real Lead Source values -- closing a real, confirmed-not-a-bug gap
the Attribution Engine's own smoke test surfaced (Marketing Growth Platform,
session 113 follow-up): zero BECAME relationships and zero SOLD-state Leads
existed anywhere in the live seed graph, so core/marketing_attribution.py's
Channel Mix read an honest $0.00 in real revenue despite 5 real historically-
funded Deals existing elsewhere in the graph (those 5 Customers were seeded
directly, never through a Lead conversion).

Same discipline as imports/seed_operational.py/imports/seed_payment_history.py:
calls the REAL core.lead_workflows/core.lead_conversion/core.deals functions
directly (not a flat Entity(attributes=dict(row)) import), so every real
invariant those modules enforce (state-machine transitions, in-house financing
math, contract generation, Vehicle-sold marking) runs for real -- exactly as if
a person had clicked a Lead through NEW -> ... -> SOLD, converted it, and
desked/funded a deal through the UI. A representative sample of real, still-
open Leads (excludes anything already SOLD/LOST/converted) spread across as
many distinct real Source values as this seed's Lead population actually has,
so Channel Mix gets real cross-source variety rather than one dominant bucket.

Bulk-seeding performance technique (same as imports/seed_payment_history.py,
since core.storage.save_graph() costs several real seconds per call on this
graph's size): every module's per-call save_graph is monkeypatched to a no-op
during the loop, then a single real save_graph() runs once at the end.
"""

import random

from core.dealeros import ledger
from core.entity_types import LEAD, VEHICLE

import core.lead_workflows as lead_workflows_module
import core.lead_conversion as lead_conversion_module
import core.deals as deals_module

from core.lead_workflows import advance_lead_workflow
from core.lead_conversion import convert_lead_to_customer
from core.deals import (
    create_deal,
    add_scenario,
    select_scenario,
    choose_in_house_financing,
    generate_contract,
    fund_deal,
)
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH

random.seed(11713)

# The real LEAD_WORKFLOW chain (core/workflows.py) toward SOLD -- a strictly
# linear path with LOST as the only branch, so a plain ordered list is enough
# to walk any lead from wherever it currently is to SOLD via real, individually
# validated advance_lead_workflow() transitions.
CHAIN = ["NEW", "CONTACTED", "APPOINTMENT_SET", "VISITED", "PROPOSAL", "NEGOTIATION", "SOLD"]

# Real, per-source cap so no single dominant historical Source (e.g. "Website"
# at 229 leads) swamps every other bucket -- Channel Mix should show real
# variety across sources, not one inflated column.
PER_SOURCE_CAP = 5

# Roughly this fraction of newly-converted Customers get carried all the way
# through a real funded Deal (not just conversion) -- a real dealership
# converts more leads than it closes deals same-visit.
FUND_FRACTION = 0.55

STAFF_EMPLOYEE = "EMP-00001"


def _real_employee_ids(limit=20):
    from core.entity_types import EMPLOYEE

    ids = [
        e.id for e in ledger.get_all().values()
        if e.entity_type == EMPLOYEE and (e.attributes.get("Department") or "").strip().lower() == "sales"
    ]
    return ids[:limit] if ids else [STAFF_EMPLOYEE]


def _select_leads():
    """A representative, diverse sample: up to PER_SOURCE_CAP real open Leads per
    real Source value, shuffled deterministically."""

    leads = [
        e for e in ledger.get_all().values()
        if e.entity_type == LEAD
        and e.attributes.get("PipelineState") not in ("SOLD", "LOST")
        and not e.attributes.get("ConvertedCustomerID")
    ]

    by_source = {}
    for lead in leads:
        source = lead.attributes.get("Source") or "Unknown"
        by_source.setdefault(source, []).append(lead)

    selected = []
    for source, group in by_source.items():
        random.shuffle(group)
        selected.extend(group[:PER_SOURCE_CAP])

    random.shuffle(selected)
    return selected


def _advance_to_sold(lead_id):
    """Walks a real Lead through the real state machine from wherever it
    currently is to SOLD -- one real advance_lead_workflow() call per hop."""

    lead = ledger.get_entity(lead_id)
    current = lead.attributes.get("PipelineState") or "NEW"

    if current not in CHAIN:
        return False

    start_idx = CHAIN.index(current)

    for next_state in CHAIN[start_idx + 1:]:
        result = advance_lead_workflow(lead_id, next_state)
        if isinstance(result, dict) and result.get("error"):
            return False

    return True


def run():

    sales_ids = _real_employee_ids()
    unsold_vehicles = [
        v for v in ledger.get_all().values()
        if v.entity_type == VEHICLE and not v.attributes.get("DateSold")
    ]
    random.shuffle(unsold_vehicles)

    leads = _select_leads()

    # Disable every touched module's per-call save_graph during the loop -- a
    # real bulk-seeding performance technique, not a change to any of these
    # functions' normal single-call behavior.
    real_saves = {
        "lead_workflows": lead_workflows_module.save_graph,
        "lead_conversion": lead_conversion_module.save_graph,
        "deals": deals_module.save_graph,
    }
    lead_workflows_module.save_graph = lambda *_a, **_kw: None
    lead_conversion_module.save_graph = lambda *_a, **_kw: None
    deals_module.save_graph = lambda *_a, **_kw: None

    converted = 0
    funded = 0
    vehicle_cursor = 0

    try:
        for lead in leads:

            if not _advance_to_sold(lead.id):
                continue

            employee_id = random.choice(sales_ids)

            customer = convert_lead_to_customer(lead.id, employee_id)
            if isinstance(customer, dict) and customer.get("error"):
                continue

            converted += 1

            if random.random() >= FUND_FRACTION:
                continue

            if vehicle_cursor >= len(unsold_vehicles):
                continue

            vehicle = unsold_vehicles[vehicle_cursor]
            vehicle_cursor += 1

            deal = create_deal(customer.id, vehicle.id, employee_id)
            if isinstance(deal, dict) and deal.get("error"):
                continue

            base_price = float(vehicle.attributes.get("Price") or 25000)
            down = round(base_price * random.uniform(0.0, 0.1), 2)
            term = random.choice([48, 60, 72])

            add_scenario(deal.id, "Standard Term", sale_price=base_price, down_payment=down, term_months=term)
            select_scenario(deal.id, "scn-1")
            choose_in_house_financing(deal.id)
            generate_contract(deal.id)
            result = fund_deal(deal.id)

            if isinstance(result, dict) and result.get("error"):
                continue

            funded += 1

    finally:
        lead_workflows_module.save_graph = real_saves["lead_workflows"]
        lead_conversion_module.save_graph = real_saves["lead_conversion"]
        deals_module.save_graph = real_saves["deals"]

    save_graph(GRAPH_PATH)

    return converted, funded, len(leads)


if __name__ == "__main__":
    from core.storage import load_graph

    load_graph(GRAPH_PATH)
    c, f, sampled = run()
    print(f"Leads sampled:     {sampled}")
    print(f"Converted:         {c}")
    print(f"Funded deals:      {f}")
