from imports.inventory_import import import_inventory
from imports.customer_import import import_customers
from imports.finance_import import import_finance

from core.dealeros import ledger

import_inventory(
    "data/inventory/inventory.csv"
)

import_customers(
    "data/customers/customers.csv"
)

count = import_finance(
    "data/finance/finance.csv"
)

print(f"Finance Imported: {count}")

for relationship in ledger.get_relationships():
    print(relationship)