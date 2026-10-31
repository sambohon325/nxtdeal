from imports.inventory_import import import_inventory
from imports.customer_import import import_customers
from imports.service_import import import_service

from core.dealeros import ledger

import_inventory(
    "data/inventory/inventory.csv"
)

import_customers(
    "data/customers/customers.csv"
)

count = import_service(
    "data/service/service.csv"
)

print(
    f"Service Records Imported: {count}"
)

for relationship in ledger.get_relationships():
    print(relationship)