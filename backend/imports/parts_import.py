"""
Loads backend/seed_data/parts.csv and part_sales.csv into the graph (Department
Intelligence, session 35). Same one-off importer shape as every other imports/*.py
script: dict(row) becomes
the entity's attributes verbatim, one Relationship wired per row where a lookup
succeeds. See imports/generate_seed_data.py for how the CSVs are produced.
"""

import csv

from core.entities import Entity

from core.dealeros import (
    ledger,
    registry,
    id_generator
)

from core.entity_types import (
    PART,
    PART_SALE
)

from core.relationships import Relationship

from core.relationship_types import (
    SOLD_PART,
    SOLD_BY
)


def import_parts(csv_path):

    created = 0

    with open(csv_path, newline="", encoding="utf-8-sig") as file:

        reader = csv.DictReader(file)

        for row in reader:

            part_id = id_generator.generate(
                "PART"
            )

            part_entity = Entity(
                id=part_id,
                entity_type=PART,
                attributes=dict(row)
            )

            ledger.add_entity(
                part_entity
            )

            registry.register_part(
                row["PartNumber"],
                part_id
            )

            created += 1

    return created


def import_part_sales(csv_path):

    created = 0

    with open(csv_path, newline="", encoding="utf-8-sig") as file:

        reader = csv.DictReader(file)

        for row in reader:

            sale_id = id_generator.generate(
                "PSALE"
            )

            sale_entity = Entity(
                id=sale_id,
                entity_type=PART_SALE,
                attributes=dict(row)
            )

            ledger.add_entity(
                sale_entity
            )

            part = registry.find_part(
                row["PartNumber"]
            )

            if part:

                ledger.add_relationship(
                    Relationship(
                        source_id=sale_id,
                        target_id=part,
                        relationship_type=SOLD_PART
                    )
                )

            counterperson = registry.find_employee(
                row.get("Counterperson", "")
            )

            if counterperson:

                ledger.add_relationship(
                    Relationship(
                        source_id=sale_id,
                        target_id=counterperson,
                        relationship_type=SOLD_BY
                    )
                )

            created += 1

    return created