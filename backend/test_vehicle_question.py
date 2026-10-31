from imports.inventory_import import import_inventory
from imports.customer_import import import_customers
from imports.finance_import import import_finance

from core.queries import ask_question

import_inventory(
    "data/inventory/inventory.csv"
)

import_customers(
    "data/customers/customers.csv"
)

import_finance(
    "data/finance/finance.csv"
)

answer = ask_question(
    "show vehicle for john"
)

print(
    "Question Type:",
    answer["type"]
)

print()

print("Results")

print()

for entity in answer["results"]:

    print(entity)