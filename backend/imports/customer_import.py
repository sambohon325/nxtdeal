import csv

from core.entities import Entity
from core.dealeros import (
    ledger,
    registry,
    id_generator
)

from core.entity_types import CUSTOMER


def import_customers(csv_path):

    imported = 0
    skipped = 0

    with open(csv_path, newline="", encoding="utf-8-sig") as file:

        reader = csv.DictReader(file)

        for row in reader:

            customer_id = row["CustomerID"]

            existing = registry.find_customer(
                customer_id
            )

            if existing:
                skipped += 1
                continue

            entity_id = id_generator.generate(
                "CUST"
            )

            customer = Entity(
                id=entity_id,
                entity_type=CUSTOMER,
                attributes=dict(row)
            )

            ledger.add_entity(customer)

            registry.register_customer(
                customer_id,
                entity_id
            )

            imported += 1

    return imported, skipped