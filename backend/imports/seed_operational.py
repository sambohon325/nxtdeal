"""
Seeds real, in-flight operational activity that doesn't fit the flat CSV-import shape
every other imports/*.py script uses -- Deal Desk deals spanning every real lifecycle
stage, marketing Campaigns spanning every real status, and a handful of marketing
Assets -- per Sam's session 39 ask for "contracts in various states of close, finance in
various stages, marketing, operations, etc."

Unlike imports/*.py, this module calls the real core.deals / core.campaigns / core.assets
functions directly (not a flat Entity(attributes=dict(row)) import) so every invariant
those modules enforce (state machine transitions, audience building, id generation) runs
for real -- exactly as if a person had clicked through the Deal Desk / campaign / asset
workflows in the UI. Called from run_seed_import.py, after the flat CSV entities
(employees/vehicles/customers/leads/finance/service/parts) are already loaded, since it
depends on those existing in the graph (it looks vehicles/customers/lenders up by their
business keys via core.dealeros.registry).

Reads backend/seed_data/deal_desk_pairs.csv (written by
imports/generate_seed_data.py's write_deal_desk_pairs()) to know which VIN/CustomerID
pairs are reserved for Deal Desk activity -- those vehicles/customers deliberately have
no funded FinanceContract from the flat finance.csv import (see that module's docstring).
"""

import csv
import os
import random

from core.dealeros import registry

from core.deals import (
    create_deal,
    add_scenario,
    select_scenario,
    choose_in_house_financing,
    submit_to_lender,
    record_lender_decision,
    accept_countered_terms,
    generate_contract,
    fund_deal,
    cancel_deal,
    list_lenders,
)

from core.campaigns import (
    create_campaign,
    activate_campaign,
    complete_campaign,
    cancel_campaign,
    get_campaign_type,
)
from core.assets import create_asset, submit_for_approval, approve_asset, reject_asset


random.seed(4242)

SEED_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "seed_data")

FRANCHISE_SALES_IDS = ["E3008", "E3009", "E3010", "E3011", "E3012", "E3013", "E3014"]
BHPH_SALES_IDS = ["E3015", "E3016"]
ALL_SALES_IDS = FRANCHISE_SALES_IDS + BHPH_SALES_IDS + ["E3017", "E3018"]

MARKETING_STAFF_IDS = ["E3040", "E3041", "E3042", "E3043"]
MARKETING_REVIEWER_ID_KEY = "E3040"  # Marketing Manager (business key) -- resolved to
# the real graph Employee id at call time below, same reason as the created_by/
# requested_by resolution above.

FINANCE_STAFF_IDS = ["E3020", "E3021", "E3022", "E3023"]


# ---------------------------------------------------------------------------
# Deal Desk -- 50 reserved vehicle/customer pairs spread across every real stage of the
# desking -> financing -> contract -> funded lifecycle (plus cancelled), per Sam:
# "contracts in various states of close, finance in various stages."
# ---------------------------------------------------------------------------

DEAL_STAGE_PLAN = (
    ["desking_multi"] * 8
    + ["financing_not_started"] * 4
    + ["in_house_approved"] * 6
    + ["submitted_pending"] * 8
    + ["outside_approved"] * 4
    + ["declined"] * 5
    + ["countered"] * 3
    + ["contract_generated"] * 4
    + ["funded"] * 5
    + ["cancelled"] * 3
)


def _read_pairs(filename):

    path = os.path.join(SEED_DIR, filename)

    if not os.path.isfile(path):
        return []

    with open(path, newline="", encoding="utf-8-sig") as file:
        return list(csv.DictReader(file))


def _build_scenarios(deal_id, base_price, count):

    labels = ["Standard Term", "Lower Payment", "Shorter Term"]

    for idx in range(count):

        term = random.choice([48, 60, 72]) if idx != 2 else 36
        down = round(base_price * random.uniform(0.0, 0.12), 2)

        add_scenario(
            deal_id,
            labels[idx % len(labels)],
            sale_price=base_price + random.randint(-500, 500),
            down_payment=down,
            term_months=term,
        )


def seed_deal_desk():

    pairs = _read_pairs("deal_desk_pairs.csv")

    if not pairs:
        print("No deal_desk_pairs.csv found -- skipping Deal Desk seeding.")
        return 0

    plan = list(DEAL_STAGE_PLAN)

    while len(plan) < len(pairs):
        plan.append("desking_multi")

    random.shuffle(plan)

    lenders = list_lenders()
    created = 0

    for row, stage in zip(pairs, plan):

        customer_key = row.get("CustomerID")
        vin = row.get("VIN")

        customer_id = registry.find_customer(customer_key)
        vehicle_id = registry.find_vehicle(vin)

        if not customer_id or not vehicle_id:
            continue

        created_by_key = random.choice(ALL_SALES_IDS)
        created_by = registry.find_employee(created_by_key) or created_by_key

        deal = create_deal(customer_id, vehicle_id, created_by)

        if isinstance(deal, dict) and deal.get("error"):
            continue

        deal_id = deal.id

        from core.dealeros import ledger
        vehicle = ledger.get_entity(vehicle_id)
        base_price = float(vehicle.attributes.get("Price") or 25000)

        scenario_count = 3 if stage in ("desking_multi",) else random.choice([1, 2])
        _build_scenarios(deal_id, base_price, scenario_count)

        created += 1

        if stage == "desking_multi":
            continue

        deal = select_scenario(deal_id, f"scn-1")

        if stage == "financing_not_started":
            continue

        if stage == "cancelled":
            cancel_deal(deal_id)
            continue

        if stage == "in_house_approved":
            choose_in_house_financing(deal_id)
            continue

        # Everything past this point goes through an outside lender submission.
        lender = random.choice(lenders) if lenders else None

        if not lender:
            choose_in_house_financing(deal_id)
            continue

        submit_to_lender(deal_id, lender.id)

        if stage == "submitted_pending":
            continue

        if stage == "outside_approved":
            record_lender_decision(deal_id, "approved")
            continue

        if stage == "declined":
            record_lender_decision(
                deal_id, "declined",
                notes="Debt-to-income ratio outside lender guidelines.",
            )
            continue

        if stage == "countered":
            record_lender_decision(
                deal_id, "countered",
                countered_terms={
                    "apr": 11.9, "term_months": 60,
                    "amount_financed": base_price * 0.9,
                    "down_payment": base_price * 0.1,
                    "monthly_payment": round(base_price * 0.9 / 60, 2),
                },
                notes="Approved at a higher rate than requested.",
            )
            continue

        if stage == "contract_generated":
            record_lender_decision(deal_id, "approved")
            generate_contract(deal_id)
            continue

        if stage == "funded":
            record_lender_decision(deal_id, "approved")
            generate_contract(deal_id)
            fund_deal(deal_id)
            continue

    return created


# ---------------------------------------------------------------------------
# Campaigns -- one or more per campaign type, spread across draft/active/completed/
# cancelled so the marketing department has real, varied history to show.
# ---------------------------------------------------------------------------

CAMPAIGN_PLAN = [
    ("retention", "Spring Service Win-Back", {"months_since_service": 6}, "draft"),
    ("retention", "Summer Maintenance Reminder", {"months_since_service": 4}, "active"),
    ("retention", "Q1 Retention Push", {"months_since_service": 8}, "completed"),
    ("retention", "Loyalty Recall Follow-Up", {"months_since_service": 12}, "cancelled"),
    ("inventory_ads", "Truck Inventory Conquest", {"make": "Ford", "model": ""}, "active"),
    ("inventory_ads", "SUV Ad Refresh", {"make": "Toyota", "model": ""}, "draft"),
    ("inventory_ads", "Sedan Clearance Push", {"make": "", "model": ""}, "completed"),
    ("inventory_ads", "Jeep Conquest Retarget", {"make": "Jeep", "model": ""}, "cancelled"),
    ("finance_renewal", "End-of-Term Renewal Offers", {"months_to_maturity": 3}, "active"),
    ("finance_renewal", "Payoff Refinance Outreach", {"months_to_maturity": 6}, "completed"),
    ("accessory_accelerator", "New Owner Accessory Upsell", {"days_since_sale": 30}, "active"),
    ("accessory_accelerator", "Protection Plan Push", {"days_since_sale": 60}, "draft"),
    ("general", "Fall Customer Appreciation Event", {}, "active"),
    ("general", "Holiday Hours Announcement", {}, "completed"),
]


def seed_campaigns():

    created = 0

    for campaign_type, name, params, target_status in CAMPAIGN_PLAN:

        created_by_key = random.choice(MARKETING_STAFF_IDS)
        created_by = registry.find_employee(created_by_key) or created_by_key
        type_info = get_campaign_type(campaign_type) or {}

        campaign = create_campaign(
            campaign_type, name,
            channel=type_info.get("default_channel", "email"),
            created_by=created_by,
            params=params,
        )

        if target_status == "draft":
            pass
        elif target_status == "active":
            activate_campaign(campaign.id)
        elif target_status == "completed":
            activate_campaign(campaign.id)
            complete_campaign(campaign.id)
        elif target_status == "cancelled":
            cancel_campaign(campaign.id)

        created += 1

    return created


# ---------------------------------------------------------------------------
# Marketing assets -- a handful across templates/statuses so the design/approval queue
# has real, varied content.
# ---------------------------------------------------------------------------

ASSET_PLAN = [
    ("inventory_flyer", {"headline": "2025 F-150 -- Now Arriving", "highlight_1": "0% APR available", "highlight_2": "Factory warranty", "cta_text": "Schedule a test drive"}, "approved"),
    ("inventory_flyer", {"headline": "Certified Pre-Owned RAV4 Sale", "highlight_1": "Multi-point inspected", "cta_text": "See the lot"}, "pending_approval"),
    ("social_post", {"headline": "Weekend Sales Event", "body": "Stop by this weekend for our biggest incentives of the season.", "hashtags": "#NXTDeal #WeekendSale"}, "approved"),
    ("social_post", {"headline": "Meet Our Service Team", "body": "Get to know the technicians keeping your vehicle running right."}, "draft"),
    ("sold_announcement", {"customer_name": "The Martinez Family", "vehicle_description": "2025 Toyota Highlander", "message": "Congratulations on your new Highlander!"}, "approved"),
    ("service_special", {"offer_title": "Fall Oil Change Special", "offer_details": "$29.99 synthetic blend oil change, now through October.", "expiration_date": "2026-10-31"}, "pending_approval"),
    ("finance_offer", {"offer_title": "In-House Financing Available", "apr_rate": "As low as 14.9%", "term_months": "60", "disclaimer": "APR based on approved credit. See dealer for details."}, "rejected"),
    ("finance_offer", {"offer_title": "0.9% APR for Qualified Buyers", "apr_rate": "0.9%", "term_months": "36"}, "approved"),
]


def seed_assets():

    created = 0

    for template_key, fields, target_status in ASSET_PLAN:

        requested_by_key = random.choice(MARKETING_STAFF_IDS + ["E3008", "E3009"])
        requested_by = registry.find_employee(requested_by_key) or requested_by_key

        asset = create_asset(template_key, requested_by, fields)

        reviewer_id = registry.find_employee(MARKETING_REVIEWER_ID_KEY) or MARKETING_REVIEWER_ID_KEY

        if target_status == "draft":
            pass
        elif target_status == "pending_approval":
            submit_for_approval(asset.id)
        elif target_status == "approved":
            submit_for_approval(asset.id)
            approve_asset(asset.id, reviewer_id, notes="Looks good, approved.")
        elif target_status == "rejected":
            submit_for_approval(asset.id)
            reject_asset(asset.id, reviewer_id, notes="Add required APR disclaimer before resubmitting.")

        created += 1

    return created


def run():
    """Called from run_seed_import.py, which prints its own summary lines for these
    counts -- no printing here to avoid double output."""

    deals_created = seed_deal_desk()
    campaigns_created = seed_campaigns()
    assets_created = seed_assets()

    return deals_created, campaigns_created, assets_created
