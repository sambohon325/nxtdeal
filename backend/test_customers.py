from imports.customer_import import import_customers
from core.dealeros import ledger

imported, skipped = import_customers(
    "data/customers/customers.csv"
)

print(f"Imported: {imported}")
print(f"Skipped: {skipped}")

for entity_id, entity in ledger.get_all().items():
    print(entity_id)
    print(entity.entity_type)
    print(entity.attributes)