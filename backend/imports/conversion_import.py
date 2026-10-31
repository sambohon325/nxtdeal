import csv

from core.dealeros import ledger
from core.dealeros import registry

from core.relationships import Relationship
from core.relationship_types import BECAME


def import_conversions(csv_path):

    created = 0

    with open(csv_path, newline="", encoding="utf-8-sig") as file:

        reader = csv.DictReader(file)

        for row in reader:

            lead = registry.find_lead(
                row["LeadID"]
            )

            customer = registry.find_customer(
                row["CustomerID"]
            )

            if not lead or not customer:
                continue

            ledger.add_relationship(
                Relationship(
                    source_id=lead,
                    target_id=customer,
                    relationship_type=BECAME
                )
            )

            created += 1

    return created