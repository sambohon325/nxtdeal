from imports.inventory_import import import_inventory
from imports.service_import import import_service
from imports.image_import import import_images

from core.dealeros import ledger

import_inventory(
    "data/inventory/inventory.csv"
)

import_service(
    "data/service/service.csv"
)

count = import_images(
    "data/images/images.csv"
)

print(
    f"Images Imported: {count}"
)

for relationship in ledger.get_relationships():

    if relationship.relationship_type == "HAS_IMAGE":

        print(relationship)