from imports.inventory_import import import_inventory
from imports.customer_import import import_customers
from imports.lead_import import import_leads
from imports.conversion_import import import_conversions

from core.dealeros import ledger

import_inventory(
    "data/inventory/inventory.csv"
)

import_customers(
    "data/customers/customers.csv"
)

import_leads(
    "data/leads/leads.csv"
)

count = import_conversions(
    "data/conversions/conversions.csv"
)

print(f"Conversions Created: {count}")

for relationship in ledger.get_relationships():
    print(relationship)