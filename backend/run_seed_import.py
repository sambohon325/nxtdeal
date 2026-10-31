"""
Loads the generated demo dataset (backend/seed_data/*.csv — see
imports/generate_seed_data.py) into storage/graph.json. Expanded 2026-07-13 (session 39,
per Sam's "add more data" ask): 500 vehicles (franchise new/CPO + an independent BHPH
used lot) in various sale states, 500 customers, 1000 leads, ~300+ service records, 300
parts / 1800 part sales, and a realistic ~45-person employee roster across every
department. Also runs imports/seed_operational.py, which seeds real, in-flight Deal Desk
deals (every lifecycle stage), marketing campaigns (every status), and a handful of
marketing assets -- entities that don't fit the flat CSV-import shape below, built via
the same core.deals/core.campaigns/core.assets functions the UI itself calls.

Usage:
    python imports/generate_seed_data.py   # writes the CSVs to backend/seed_data/
    python run_seed_import.py              # loads them into storage/graph.json

IMPORTANT: this REPLACES storage/graph.json — it does not load the existing file first
and append. Whatever's currently in there (including anything clicked through the UI in
a prior session) gets overwritten. If the backend is running, restart it afterward —
graph data is loaded once at process startup, not hot-reloaded (see CLAUDE.md).

Does not touch storage/credentials.json, storage/audit.json, storage/workflows.json, or
storage/assignments.json — login credentials and the separate Workflow Engine (lead
routing/assignment, which backs the workload/leaderboard/pipeline/escalation/followup
dashboards) are untouched by this. This seed only populates the graph.json entities/
relationships those other systems don't read from. See BUILD_QUEUE.md if you want that
wired up too.
"""

import os

from core.storage import save_graph

from imports.employee_import import import_employees
from imports.inventory_import import import_inventory
from imports.customer_import import import_customers
from imports.deal_import import import_deals
from imports.finance_import import import_finance
from imports.service_import import import_service
from imports.lead_import import import_leads
from imports.parts_import import import_parts, import_part_sales
from imports.seed_operational import run as run_operational_seed
from imports.seed_demo_extras import run as run_demo_extras_seed
from imports.seed_service_operational import run as run_service_operational_seed
from imports.seed_payment_history import run as run_payment_history_seed
from imports.seed_lead_conversions import run as run_lead_conversions_seed


SEED_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "seed_data"
)


def main():

    if not os.path.isdir(SEED_DIR):
        print(f"No {SEED_DIR} directory found.")
        print("Run `python imports/generate_seed_data.py` first.")
        return

    employees = import_employees(os.path.join(SEED_DIR, "employees.csv"))
    print(f"Employees:        {employees} created")

    vehicles, skipped = import_inventory(os.path.join(SEED_DIR, "vehicles.csv"))
    print(f"Vehicles:         {vehicles} created, {skipped} skipped (duplicate VIN)")

    customers, skipped = import_customers(os.path.join(SEED_DIR, "customers.csv"))
    print(f"Customers:        {customers} created, {skipped} skipped (duplicate CustomerID)")

    deals = import_deals(os.path.join(SEED_DIR, "deals.csv"))
    print(f"Deals (PURCHASED): {deals} relationships created")

    finance = import_finance(os.path.join(SEED_DIR, "finance.csv"))
    print(f"Finance contracts: {finance} created")

    service = import_service(os.path.join(SEED_DIR, "service.csv"))
    print(f"Service records:  {service} created")

    leads = import_leads(os.path.join(SEED_DIR, "leads.csv"))
    print(f"Leads:            {leads} created")

    parts = import_parts(os.path.join(SEED_DIR, "parts.csv"))
    print(f"Parts:            {parts} created")

    part_sales = import_part_sales(os.path.join(SEED_DIR, "part_sales.csv"))
    print(f"Part sales:       {part_sales} created")

    deals_created, campaigns_created, assets_created = run_operational_seed()
    print(f"Deal Desk deals:  {deals_created} created (various stages)")
    print(f"Campaigns:        {campaigns_created} created (various statuses)")
    print(f"Marketing assets: {assets_created} created (various statuses)")

    reviews_created, auctions_created, recalls_created, documents_created = run_demo_extras_seed()
    print(f"Reviews:              {reviews_created} created")
    print(f"Auction transactions: {auctions_created} created")
    print(f"Recalls:              {recalls_created} created")
    print(f"Documents:            {documents_created} created")

    service_ros_created = run_service_operational_seed()
    print(f"Live repair orders:   {service_ros_created} created (various RO Workflow stages)")

    payments_created, loans_sampled = run_payment_history_seed()
    print(f"Loan payments:        {payments_created} created across {loans_sampled} sampled loans")

    leads_converted, deals_funded, leads_sampled = run_lead_conversions_seed()
    print(f"Lead conversions:     {leads_converted} converted (of {leads_sampled} sampled), {deals_funded} funded into real Deals")

    save_graph("storage/graph.json")

    print()
    print("Saved to storage/graph.json. Restart the backend to pick up the new data.")


if __name__ == "__main__":
    main()
