import csv

from core.entities import Entity
from core.dealeros import (
    ledger,
    registry,
    id_generator
)

from core.entity_types import VEHICLE


def import_inventory(csv_path):

    imported = 0
    skipped = 0

    with open(csv_path, newline="", encoding="utf-8-sig") as file:

        reader = csv.DictReader(file)

        for row in reader:

            vin = row.get("VIN")

            existing = registry.find_vehicle(vin, require_unique=True)

            if existing:
                skipped += 1
                continue

            entity_id = id_generator.generate(
                "VEH"
            )

            vehicle = Entity(
                id=entity_id,
                entity_type=VEHICLE,
                attributes=dict(row)
            )

            ledger.add_entity(vehicle)

            registry.register_vehicle(
                vin,
                entity_id
            )

            imported += 1

    return imported, skipped
