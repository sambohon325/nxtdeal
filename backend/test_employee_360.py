from imports.employee_import import import_employees
from imports.customer_import import import_customers
from imports.lead_import import import_leads
from imports.assignment_import import import_assignments

from core.queries import get_employee_360

import_employees(
    "data/employees/employees.csv"
)

import_customers(
    "data/customers/customers.csv"
)

import_leads(
    "data/leads/leads.csv"
)

import_assignments(
    "data/assignments/assignments.csv"
)

profile = get_employee_360(
    "EMP-00001"
)

print("Employee")
print(profile["employee"])

print()

print("Customers")

for customer in profile["customers"]:
    print(customer)

print()

print("Leads")

for lead in profile["leads"]:
    print(lead)