from imports.inventory_import import import_inventory
from imports.customer_import import import_customers
from imports.deal_import import import_deals

from core.dealeros import ledger

import_inventory(
    "data/inventory/inventory.csv"
)

import_customers(
    "data/customers/customers.csv"
)

count = import_deals(
    "data/deals/deals.csv"
)

print(f"Relationships Created: {count}")

for relationship in ledger.get_relationships():
    print(relationship)