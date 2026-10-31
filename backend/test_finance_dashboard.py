from imports.inventory_import import import_inventory
from imports.customer_import import import_customers
from imports.finance_import import import_finance

from core.queries import get_finance_dashboard

import_inventory(
    "data/inventory/inventory.csv"
)

import_customers(
    "data/customers/customers.csv"
)

import_finance(
    "data/finance/finance.csv"
)

dashboard = get_finance_dashboard()

print("Finance Dashboard")

print()

print(
    f"Finance Contracts: {dashboard['finance_contract_count']}"
)

print(
    f"Customers: {dashboard['customer_count']}"
)

print(
    f"Vehicles: {dashboard['vehicle_count']}"
)

print(
    f"Lenders: {dashboard['lender_count']}"
)