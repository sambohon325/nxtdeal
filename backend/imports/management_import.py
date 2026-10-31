import csv

from core.dealeros import ledger
from core.relationships import Relationship
from core.relationship_types import MANAGED_BY


def import_management(csv_path):

    created = 0

    with open(csv_path, newline="", encoding="utf-8-sig") as file:

        reader = csv.DictReader(file)

        for row in reader:

            ledger.add_relationship(
                Relationship(
                    source_id=row["EmployeeID"],
                    target_id=row["ManagerID"],
                    relationship_type=MANAGED_BY
                )
            )

            created += 1

    return created