from imports.inventory_import import import_inventory
from imports.customer_import import import_customers
from imports.finance_import import import_finance

from core.queries import (
    get_customer_profile
)

import_inventory(
    "data/inventory/inventory.csv"
)

import_customers(
    "data/customers/customers.csv"
)

import_finance(
    "data/finance/finance.csv"
)

profile = get_customer_profile(
    "CUST-00001"
)

print(
    profile["customer"]
)

print()

for relationship in profile[
    "relationships"
]:
    print(relationship)