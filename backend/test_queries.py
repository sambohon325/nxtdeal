from imports.inventory_import import import_inventory
from imports.customer_import import import_customers
from imports.finance_import import import_finance

from core.queries import (
    get_connected_entities,
    find_entities_by_type
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

print("Connected To CUST-00001")

print(
    get_connected_entities(
        "CUST-00001"
    )
)

print()

print("Finance Contracts")

finance_contracts = find_entities_by_type(
    "FinanceContract"
)

for contract in finance_contracts:

    print(contract.id)