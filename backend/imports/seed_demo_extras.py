"""
Seeds demo data for the "wire it all up" gaps (2026-07-14, session 59) -- Sam: "lets go
ahead and populate that data with demo data" for the workflow-catalog entries
core/workflow_tab_data.py's REAL_SOURCES map had nothing real to show for, because
nothing in the graph modeled reviews, auction/transport tracking, or OEM recalls at
all (as opposed to the ~13 gaps that just needed a new query over data that already
existed -- see that module's REAL_SOURCES for those).

Three new entity types (core/entity_types.py's REVIEW/AUCTION_TRANSACTION/RECALL),
each an ordinary graph Entity tied to real existing Vehicle/Customer entities rather
than floating free -- same graph-native rule as everything else. Clearly-synthetic
demo content, same bar as imports/generate_seed_data.py's fake names/VINs -- not a
claim of a live review-platform/DMV-recall/auction-house integration.

Unlike imports/*.py's flat CSV importers, this reads directly off the already-loaded
graph (core.dealeros.ledger) to pick real Vehicle/Customer ids rather than a CSV
business-key lookup, since it's meant to run against an already-populated graph (either
right after run_seed_import.py's flat imports, or standalone against today's live
storage/graph.json without disturbing anything already in it).
"""

import random
from datetime import datetime, timedelta, timezone

from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.relationships import Relationship
from core.entity_types import (
    VEHICLE,
    CUSTOMER,
    DEAL,
    EMPLOYEE,
    REVIEW,
    AUCTION_TRANSACTION,
    RECALL,
    DOCUMENT,
)
from core.relationship_types import HAS_DOCUMENT

random.seed(5959)

REVIEW_PLATFORMS = ["Google", "Cars.com", "Facebook"]

POSITIVE_QUOTES = [
    "Great experience from start to finish, would buy here again.",
    "The sales team was low-pressure and genuinely helpful.",
    "Fast, easy financing process and a fair trade-in offer.",
    "Service department got me in and out quickly.",
    "Found exactly the truck I wanted at a fair price.",
    "Everyone was friendly and the paperwork was painless.",
]

NEGATIVE_QUOTES = [
    "Waited over two hours for a scheduled oil change.",
    "Felt pressured into add-ons I didn't ask for.",
    "Financing terms changed at signing from what was quoted.",
    "Called three times about a recall and never got a callback.",
]

AUCTION_HOUSES = ["Manheim", "ADESA", "Copart Dealer Auction", "ACV Auctions"]
CARRIERS = ["Reliable Auto Transport", "Metro Carhaul Logistics", "Interstate Vehicle Shippers"]
TRANSPORT_STATUSES = ["at_auction_yard", "in_transit", "delivered"]

RECALL_CATALOG = [
    ("Airbag inflator may deploy with excessive force", "Safety"),
    ("Fuel pump may fail, increasing stall risk", "Safety"),
    ("Software update needed for backup camera display", "Emissions/Software"),
    ("Brake light switch may not illuminate brake lights", "Safety"),
    ("Powertrain control module software update", "Emissions/Software"),
]

# Document categories (session 60, Operations menu bar's "Documents" item -- Sam's
# operations.pdf spec: "Centralized document vault. Includes: Deal Jackets, Titles,
# Recon Forms, Inspection Reports, Buyer Orders, Compliance Files, Internal Requests").
# core/documents.py's DOCUMENT entity type already exists (chat-attachment uploads,
# session 47) but nothing had ever populated it with the kind of categorized deal/
# recon/compliance paperwork a real document vault holds -- imports/document_import.py
# expects a CSV that was never generated. Rather than inventing a parallel document
# concept, this creates ordinary DOCUMENT entities (same shape document_import.py
# already establishes: EntityType/EntityID/FileName) with a `DocumentType` attribute
# for the vault's category grouping, tied to real funded Deals / real Used unsold
# Vehicles mid-recon / real Customers, with a real HAS_DOCUMENT relationship from the
# entity to the document (same relationship document_import.py creates).
DOCUMENT_TYPES_BY_ENTITY = {
    DEAL: ["Deal Jacket", "Buyer Order"],
    VEHICLE: ["Title", "Recon Form", "Inspection Report"],
    CUSTOMER: ["Compliance File"],
}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _unsold_vehicles():
    return [
        v for v in ledger.get_all().values()
        if v.entity_type == VEHICLE and not v.attributes.get("DateSold")
    ]


def _all_customers():
    return [c for c in ledger.get_all().values() if c.entity_type == CUSTOMER]


def seed_reviews(count=40):
    """marketing.reputation's real source: platform reviews, mostly positive but a real
    mix of unresponded negative ones so the 'escalate negative reviews' workflow has
    something genuine to act on."""

    customers = _all_customers()

    if not customers:
        return 0

    created = 0

    for _ in range(count):

        is_positive = random.random() < 0.8
        rating = random.choice([4, 5]) if is_positive else random.choice([1, 2, 3])
        quote = random.choice(POSITIVE_QUOTES) if is_positive else random.choice(NEGATIVE_QUOTES)
        customer = random.choice(customers)
        days_ago = random.randint(0, 180)
        responded = is_positive or random.random() < 0.4  # most negatives start unresponded

        review_id = id_generator.generate("REV")

        entity = Entity(
            id=review_id,
            entity_type=REVIEW,
            attributes={
                "platform": random.choice(REVIEW_PLATFORMS),
                "rating": rating,
                "author_name": f"{customer.attributes.get('FirstName', 'A')} {customer.attributes.get('LastName', 'Customer')[:1]}.",
                "text": quote,
                "review_date": (datetime.now(timezone.utc) - timedelta(days=days_ago)).date().isoformat(),
                "responded": responded,
                "response_text": "Thank you for the feedback -- we're glad we could help!" if responded and is_positive else None,
                "customer_id": customer.id,
            },
        )

        ledger.add_entity(entity)
        created += 1

    return created


def seed_auction_transactions(count=25):
    """inventory.auction_acquisition's real source: a subset of real unsold vehicles
    marked as auction-acquired, in varying stages of transport -- Vehicle entities have
    no acquisition-channel field at all today, so this is the one gap in this batch that
    genuinely needed new data rather than a new query over existing fields."""

    vehicles = _unsold_vehicles()

    if not vehicles:
        return 0

    sample = random.sample(vehicles, k=min(count, len(vehicles)))
    created = 0

    for vehicle in sample:

        try:
            cost = float(vehicle.attributes.get("Cost") or 10000)
        except (TypeError, ValueError):
            cost = 10000

        status = random.choice(TRANSPORT_STATUSES)
        purchase_days_ago = random.randint(1, 21)

        auction_id = id_generator.generate("AUCT")

        entity = Entity(
            id=auction_id,
            entity_type=AUCTION_TRANSACTION,
            attributes={
                "vehicle_id": vehicle.id,
                "vin": vehicle.attributes.get("VIN"),
                "auction_house": random.choice(AUCTION_HOUSES),
                "bid_amount": round(cost * random.uniform(0.85, 0.98), 2),
                "purchase_date": (datetime.now(timezone.utc) - timedelta(days=purchase_days_ago)).date().isoformat(),
                "transport_status": status,
                "carrier": random.choice(CARRIERS) if status != "at_auction_yard" else None,
                "expected_arrival": (
                    (datetime.now(timezone.utc) + timedelta(days=random.randint(1, 5))).date().isoformat()
                    if status == "in_transit" else None
                ),
            },
        )

        ledger.add_entity(entity)
        created += 1

    return created


def seed_recalls(count=15):
    """service.intake/service.mpi's real source: open OEM recall campaigns tied to real
    Make/Model combinations actually present in inventory, so 'active recalls for this
    VIN' is a genuine (if synthetic) lookup rather than a live NHTSA API call this
    environment doesn't have."""

    vehicles = _unsold_vehicles() + [
        v for v in ledger.get_all().values() if v.entity_type == VEHICLE
    ]

    make_models = sorted({
        (v.attributes.get("Make"), v.attributes.get("Model"))
        for v in vehicles
        if v.attributes.get("Make") and v.attributes.get("Model")
    })

    if not make_models:
        return 0

    sample = random.sample(make_models, k=min(count, len(make_models)))
    created = 0

    for make, model in sample:

        description, campaign_type = random.choice(RECALL_CATALOG)
        days_ago = random.randint(10, 400)

        recall_id = id_generator.generate("RECALL")

        entity = Entity(
            id=recall_id,
            entity_type=RECALL,
            attributes={
                "recall_number": f"{random.randint(20, 26)}V{random.randint(100, 999)}",
                "make": make,
                "model": model,
                "description": description,
                "campaign_type": campaign_type,
                "open": random.random() < 0.7,
                "issued_date": (datetime.now(timezone.utc) - timedelta(days=days_ago)).date().isoformat(),
            },
        )

        ledger.add_entity(entity)
        created += 1

    return created


def _funded_deals():
    return [d for d in ledger.get_all().values() if d.entity_type == DEAL and d.attributes.get("status") == "funded"]


def _used_unsold_vehicles():
    return [
        v for v in _unsold_vehicles()
        if v.attributes.get("Condition") == "Used"
    ]


def _employees():
    return [e for e in ledger.get_all().values() if e.entity_type == EMPLOYEE]


def _create_document(document_type, entity_type, entity_id, filename, uploaded_by, days_ago):
    document_id = id_generator.generate("DOC")

    entity = Entity(
        id=document_id,
        entity_type=DOCUMENT,
        attributes={
            "DocumentNumber": document_id,
            "DocumentType": document_type,
            "EntityType": entity_type,
            "EntityID": entity_id,
            "FileName": filename,
            "UploadedBy": uploaded_by,
            "CreatedAt": (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat(),
        },
    )

    ledger.add_entity(entity)

    ledger.add_relationship(
        Relationship(source_id=entity_id, target_id=document_id, relationship_type=HAS_DOCUMENT)
    )

    return entity


def seed_documents(deal_sample=60, vehicle_sample=30, customer_sample=15):
    """operations.pdf's "Documents" menu item real source: a categorized document vault
    -- Deal Jackets/Buyer Orders on real funded Deals, Titles/Recon Forms/Inspection
    Reports on real Used unsold Vehicles mid-recon, Compliance Files on real Customers.
    Every document carries a real HAS_DOCUMENT relationship back to the entity it's
    about, so "search documents by VIN/Customer/Stock Number" (per the PDF) is a
    genuine one-hop graph traversal, not a fabricated search index."""

    employees = _employees()
    uploaded_by = lambda: random.choice(employees).id if employees else "EMP-00001"

    created = 0

    deals = _funded_deals()
    for deal in random.sample(deals, k=min(deal_sample, len(deals))):
        for doc_type in DOCUMENT_TYPES_BY_ENTITY[DEAL]:
            _create_document(
                doc_type, DEAL, deal.id,
                f"{doc_type.replace(' ', '_')}_{deal.id}.pdf",
                uploaded_by(), random.randint(1, 120),
            )
            created += 1

    vehicles = _used_unsold_vehicles()
    for vehicle in random.sample(vehicles, k=min(vehicle_sample, len(vehicles))):
        # Title is universal; Recon Form / Inspection Report only for units genuinely
        # mid-recon (matches operations_recon_queue's real population, not every used
        # unit).
        _create_document(
            "Title", VEHICLE, vehicle.id,
            f"Title_{vehicle.attributes.get('VIN', vehicle.id)}.pdf",
            uploaded_by(), random.randint(1, 60),
        )
        created += 1
        if random.random() < 0.7:
            _create_document(
                "Recon Form", VEHICLE, vehicle.id,
                f"ReconForm_{vehicle.attributes.get('VIN', vehicle.id)}.pdf",
                uploaded_by(), random.randint(1, 30),
            )
            created += 1
        if random.random() < 0.5:
            _create_document(
                "Inspection Report", VEHICLE, vehicle.id,
                f"InspectionReport_{vehicle.attributes.get('VIN', vehicle.id)}.pdf",
                uploaded_by(), random.randint(1, 30),
            )
            created += 1

    customers = _all_customers()
    for customer in random.sample(customers, k=min(customer_sample, len(customers))):
        _create_document(
            "Compliance File", CUSTOMER, customer.id,
            f"ComplianceFile_{customer.id}.pdf",
            uploaded_by(), random.randint(1, 200),
        )
        created += 1

    return created


def run():
    """Called from run_seed_import.py (which prints its own summary lines) or directly
    via this file's __main__ block against an already-populated storage/graph.json."""

    reviews_created = seed_reviews()
    auctions_created = seed_auction_transactions()
    recalls_created = seed_recalls()
    documents_created = seed_documents()

    return reviews_created, auctions_created, recalls_created, documents_created


if __name__ == "__main__":

    from core.storage import load_graph, save_graph
    from core.storage_paths import GRAPH_PATH

    load_graph(GRAPH_PATH)

    reviews, auctions, recalls, documents = run()

    print(f"Reviews:              {reviews} created")
    print(f"Auction transactions: {auctions} created")
    print(f"Recalls:              {recalls} created")
    print(f"Documents:            {documents} created")

    save_graph(GRAPH_PATH)

    print()
    print(f"Saved to {GRAPH_PATH}.")
