import csv

from core.entities import Entity
from core.dealeros import (
    ledger,
    id_generator
)

from core.entity_types import IMAGE

from core.relationships import Relationship

from core.relationship_types import HAS_IMAGE


def import_images(csv_path):

    created = 0

    with open(csv_path, newline="", encoding="utf-8-sig") as file:

        reader = csv.DictReader(file)

        for row in reader:

            image_id = id_generator.generate(
                "IMG"
            )

            image = Entity(
                id=image_id,
                entity_type=IMAGE,
                attributes=dict(row)
            )

            ledger.add_entity(
                image
            )

            ledger.add_relationship(
                Relationship(
                    source_id=row["EntityID"],
                    target_id=image_id,
                    relationship_type=HAS_IMAGE
                )
            )

            created += 1

    return created