import csv

from core.entities import Entity
from core.dealeros import (
    ledger,
    id_generator
)

from core.entity_types import DOCUMENT

from core.relationships import Relationship

from core.relationship_types import HAS_DOCUMENT


def import_documents(csv_path):

    created = 0

    with open(csv_path, newline="", encoding="utf-8-sig") as file:

        reader = csv.DictReader(file)

        for row in reader:

            document_id = id_generator.generate(
                "DOC"
            )

            document = Entity(
                id=document_id,
                entity_type=DOCUMENT,
                attributes=dict(row)
            )

            ledger.add_entity(
                document
            )

            ledger.add_relationship(
                Relationship(
                    source_id=row["EntityID"],
                    target_id=document_id,
                    relationship_type=HAS_DOCUMENT
                )
            )

            created += 1

    return created