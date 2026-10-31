from imports.employee_import import import_employees
from imports.customer_import import import_customers
from imports.lead_import import import_leads
from imports.assignment_import import import_assignments
from imports.management_import import import_management

from core.queries import get_team_360

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

import_management(
    "data/management/management.csv"
)

profile = get_team_360(
    "EMP-00001"
)

print("Manager")
print(profile["manager"])

print()

print("Direct Reports")

for employee in profile["direct_reports"]:
    print(employee)

print()

print("Customers")

for customer in profile["customers"]:
    print(customer)

print()

print("Leads")

for lead in profile["leads"]:
    print(lead)

print()

print(
    f"Employee Count: {profile['employee_count']}"
)

print(
    f"Customer Count: {profile['customer_count']}"
)

print(
    f"Lead Count: {profile['lead_count']}"
)