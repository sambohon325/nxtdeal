from imports.inventory_import import import_inventory
from imports.lead_import import import_leads

from core.dealeros import ledger

import_inventory(
    "data/inventory/inventory.csv"
)

count = import_leads(
    "data/leads/leads.csv"
)

print(f"Leads Imported: {count}")

print("\nRelationships\n")

for relationship in ledger.get_relationships():
    print(relationship)