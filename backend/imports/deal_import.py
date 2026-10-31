import csv

from core.relationships import Relationship
from core.dealeros import ledger
from core.dealeros import registry


def import_deals(csv_path):

    relationships_created = 0

    with open(csv_path, newline="", encoding="utf-8-sig") as file:

        reader = csv.DictReader(file)

        for row in reader:

            customer = registry.find_customer(
                row["CustomerID"]
            )

            vehicle = registry.find_vehicle(
                row["VIN"]
            )

            if not customer or not vehicle:
                continue

            ledger.add_relationship(
                Relationship(
                    source_id=customer,
                    target_id=vehicle,
                    relationship_type="PURCHASED"
                )
            )

            relationships_created += 1

    return relationships_created