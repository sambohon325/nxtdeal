from imports.inventory_import import import_inventory
from imports.customer_import import import_customers
from imports.lead_import import import_leads
from imports.finance_import import import_finance
from imports.employee_import import import_employees

from core.queries import get_sales_dashboard

import_inventory(
    "data/inventory/inventory.csv"
)

import_customers(
    "data/customers/customers.csv"
)

import_leads(
    "data/leads/leads.csv"
)

import_finance(
    "data/finance/finance.csv"
)

import_employees(
    "data/employees/employees.csv"
)

dashboard = get_sales_dashboard()

print("Sales Dashboard")

print()

print(
    f"Employees: {dashboard['employee_count']}"
)

print(
    f"Customers: {dashboard['customer_count']}"
)

print(
    f"Leads: {dashboard['lead_count']}"
)

print(
    f"Vehicles: {dashboard['vehicle_count']}"
)

print(
    f"Finance Contracts: {dashboard['finance_count']}"
)