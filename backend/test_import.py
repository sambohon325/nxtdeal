from imports.inventory_import import import_inventory
from core.dealeros import ledger

imported, skipped = import_inventory(
    "data/inventory/inventory.csv"
)

print(f"Imported: {imported}")
print(f"Skipped: {skipped}")

for entity_id, entity in ledger.get_all().items():
    print(entity_id)
    print(entity.attributes)