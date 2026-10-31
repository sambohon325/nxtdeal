import csv

from core.dealeros import ledger
from core.relationships import Relationship
from core.relationship_types import ASSIGNED_TO


def import_assignments(csv_path):

    created = 0

    with open(csv_path, newline="", encoding="utf-8-sig") as file:

        reader = csv.DictReader(file)

        for row in reader:

            ledger.add_relationship(
                Relationship(
                    source_id=row["EmployeeID"],
                    target_id=row["TargetID"],
                    relationship_type=ASSIGNED_TO
                )
            )

            created += 1

    return created
    