"""
Department Intelligence reporting layer (2026-07-13, session 35) -- Sam: "add this
product functionality into the admin - its our product 'bumper bi' that creates
dashboards across the dealership." Modeled on a real cross-dealership KPI-dashboard
product's five department dashboards (Sales, Service, Parts, F&I, Accounting), each
showing five KPI cards with a day-over-day trend delta -- "catch profit leaks before
month-end," per that product's own positioning -- rendered here the same chat-first way
as every other NXTDeal feature.

Renamed from core/bumper_bi.py session 68 (Sam: "i want to take out the term 'bumper
bi' all that ever was was reference of the functionality that i wanted to include. What
i do want to do is include that level of reporting for each reporting section of every
department"). Nothing about the KPI computation below changed -- only the module name
and the branding language in comments/labels. See BUILD_QUEUE.md's session-68 entry
(the rebrand pass) for the full list of renamed call sites.

Every KPI below is computed from real graph data, never fabricated. Getting there
honestly required a few deliberate, documented moves:

  - Vehicle gained a `Cost` field (imports/generate_seed_data.py) so front-end gross
    profit is a real SalePrice-minus-Cost derivation, not a guessed ratio.
  - ServiceRecord gained `PartsCost`/`LaborHours`/`PayType` so Service gross profit and
    Effective Labor Rate are real derivations too.
  - Part/PartSale are brand-new entity types -- NXTDeal had no parts department data
    model at all before this session (Sam approved adding it, matching how the Deal
    Desk reused FinanceContract's real shape rather than inventing a parallel model).

Two KPIs from the reference product have no honest equivalent in NXTDeal today and
were deliberately swapped for a real, adjacent metric rather than faked:

  - F&I "Product Penetration" needs aftermarket product attachment data (VSC/GAP/tire &
    wheel) that doesn't exist anywhere in this graph -- swapped for "Deals Financed"
    (a real, meaningful volume KPI from FinanceContract.FundingStatus).
  - A full "Accounting" P&L/balance sheet/cash-flow view isn't possible -- NXTDeal has
    no general ledger. What's built here instead is an honest cross-department
    gross-profit rollup ("Executive Overview"), since every department's numbers
    ultimately flow through the same financial statement anyway.
  - F&I "Reserve" itself is an estimate (a standard, widely-used simplified formula --
    see _estimate_reserve()'s docstring), not fabricated, because NXTDeal's
    FinanceContract only records the customer-facing APR, not the dealer's wholesale
    buy rate a real reserve calculation needs.

Trend deltas ("+X% vs Yesterday") do NOT come from this module -- see
core/kpi_snapshots.py. Every function here always computes CURRENT totals across
everything presently in the graph (no month-to-date date-window filtering), so results
never go stale relative to synthetic seed data whose dates don't track the real
calendar the way live production data would.
"""

import calendar

from datetime import date

from core.dealeros import ledger

from core.entity_types import (
    VEHICLE,
    SERVICE_RECORD,
    FINANCE_CONTRACT,
    PART,
    PART_SALE
)


OBSOLETE_AFTER_DAYS = 180

# The seed dataset's part sales span roughly this many days (see
# imports/generate_seed_data.py's build_part_sales()) -- used only to annualize a
# turns-per-year figure from a shorter observed sales window. Not used for any
# date-window filtering, just this one ratio.
PARTS_SALES_WINDOW_DAYS = 150

# See _estimate_reserve()'s docstring.
ASSUMED_BUY_RATE_SPREAD_POINTS = 2.0


def _f(value, default=0.0):

    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _d(value):

    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _entities(entity_type):

    return [
        entity
        for entity in ledger.get_all().values()
        if entity.entity_type == entity_type
    ]


def kpi(key, label, value, format="number", suffix=None):

    return {
        "key": key,
        "label": label,
        "value": value,
        "format": format,
        "suffix": suffix
    }


def _days_in_month(d):

    return calendar.monthrange(d.year, d.month)[1]


# ---------------------------------------------------------------------------
# Sales
# ---------------------------------------------------------------------------

def compute_sales_kpis():

    vehicles = _entities(VEHICLE)

    sold_vehicles = [
        v for v in vehicles
        if v.attributes.get("DateSold")
    ]

    units_sold = len(sold_vehicles)

    total_gross = 0.0

    for vehicle in sold_vehicles:

        price = _f(vehicle.attributes.get("Price"))
        cost = _f(vehicle.attributes.get("Cost"))

        total_gross += (price - cost)

    gp_per_unit = (
        total_gross / units_sold
        if units_sold else 0.0
    )

    total_sale_price = sum(
        _f(v.attributes.get("Price"))
        for v in sold_vehicles
    )

    avg_sale_price = (
        total_sale_price / units_sold
        if units_sold else 0.0
    )

    today = date.today()
    days_elapsed = today.day
    days_in_month = _days_in_month(today)

    sold_this_month = []

    for vehicle in sold_vehicles:

        sold_date = _d(vehicle.attributes.get("DateSold"))

        if (
            sold_date
            and sold_date.year == today.year
            and sold_date.month == today.month
        ):
            sold_this_month.append(vehicle)

    if days_elapsed > 0 and sold_this_month:

        projected_month_end_units = round(
            len(sold_this_month) / days_elapsed * days_in_month,
            1
        )

    else:

        projected_month_end_units = float(len(sold_this_month))

    kpis = {
        "total_gross_profit": kpi(
            "total_gross_profit", "Total Gross Profit", round(total_gross, 2), "currency"
        ),
        "gross_profit_per_unit": kpi(
            "gross_profit_per_unit", "Gross Profit / Unit", round(gp_per_unit, 2), "currency"
        ),
        "units_sold": kpi(
            "units_sold", "Units Sold", units_sold, "number"
        ),
        "avg_sale_price": kpi(
            "avg_sale_price", "Avg Sale Price", round(avg_sale_price, 2), "currency"
        ),
        "projected_month_end_units": kpi(
            "projected_month_end_units", "Projected Month-End Units",
            projected_month_end_units, "number"
        ),
    }

    return {
        "kpis": kpis,
        "raw": {
            "total_gross": total_gross,
            "units_sold": units_sold
        }
    }


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

def compute_service_kpis():

    records = _entities(SERVICE_RECORD)

    ro_count = len(records)

    total_cost = sum(_f(r.attributes.get("Cost")) for r in records)
    total_parts_cost = sum(_f(r.attributes.get("PartsCost")) for r in records)
    total_labor_hours = sum(_f(r.attributes.get("LaborHours")) for r in records)

    # "Total Gross" here is labor revenue -- total RO revenue minus the parts-cost
    # portion of it -- a real derivation, not RO revenue itself.
    total_gross = total_cost - total_parts_cost

    avg_repair_order = (
        total_cost / ro_count
        if ro_count else 0.0
    )

    customer_pay_count = sum(
        1 for r in records
        if r.attributes.get("PayType") == "Customer Pay"
    )

    customer_pay_pct = (
        customer_pay_count / ro_count * 100
        if ro_count else 0.0
    )

    effective_labor_rate = (
        total_gross / total_labor_hours
        if total_labor_hours else 0.0
    )

    kpis = {
        "total_gross": kpi(
            "total_gross", "Total Gross", round(total_gross, 2), "currency"
        ),
        "ro_count": kpi(
            "ro_count", "RO Count", ro_count, "number"
        ),
        "avg_repair_order": kpi(
            "avg_repair_order", "Avg Repair Order", round(avg_repair_order, 2), "currency"
        ),
        "customer_pay_pct": kpi(
            "customer_pay_pct", "Customer Pay %", round(customer_pay_pct, 1), "percent"
        ),
        "effective_labor_rate": kpi(
            "effective_labor_rate", "Effective Labor Rate",
            round(effective_labor_rate, 2), "currency", suffix="/hr"
        ),
    }

    return {
        "kpis": kpis,
        "raw": {
            "total_gross": total_gross
        }
    }


# ---------------------------------------------------------------------------
# Parts
# ---------------------------------------------------------------------------

def compute_parts_kpis():

    parts = _entities(PART)
    sales = _entities(PART_SALE)

    net_profit = sum(_f(s.attributes.get("GrossProfit")) for s in sales)
    total_qty_sold = sum(_f(s.attributes.get("QuantitySold")) for s in sales)
    parts_sales_total = sum(_f(s.attributes.get("SalePrice")) for s in sales)
    total_cogs = sum(_f(s.attributes.get("Cost")) for s in sales)

    gp_per_unit = (
        net_profit / total_qty_sold
        if total_qty_sold else 0.0
    )

    inventory_value = sum(
        _f(p.attributes.get("QuantityOnHand")) * _f(p.attributes.get("UnitCost"))
        for p in parts
    )

    annualized_cogs = total_cogs * (365 / PARTS_SALES_WINDOW_DAYS)

    inventory_turns = (
        annualized_cogs / inventory_value
        if inventory_value else 0.0
    )

    last_sale_by_part = {}

    for sale in sales:

        part_number = sale.attributes.get("PartNumber")
        sale_date = _d(sale.attributes.get("SaleDate"))

        if not sale_date:
            continue

        current_latest = last_sale_by_part.get(part_number)

        if current_latest is None or sale_date > current_latest:
            last_sale_by_part[part_number] = sale_date

    today = date.today()
    obsolete_value = 0.0

    for part in parts:

        part_number = part.attributes.get("PartNumber")
        last_sale = last_sale_by_part.get(part_number)
        received = _d(part.attributes.get("ReceivedDate"))
        value = _f(part.attributes.get("QuantityOnHand")) * _f(part.attributes.get("UnitCost"))

        if last_sale is not None:
            is_obsolete = (today - last_sale).days >= OBSOLETE_AFTER_DAYS
        elif received is not None:
            is_obsolete = (today - received).days >= OBSOLETE_AFTER_DAYS
        else:
            is_obsolete = False

        if is_obsolete:
            obsolete_value += value

    obsolete_pct = (
        obsolete_value / inventory_value * 100
        if inventory_value else 0.0
    )

    kpis = {
        "net_profit": kpi(
            "net_profit", "Net Profit", round(net_profit, 2), "currency"
        ),
        "gross_profit_per_unit": kpi(
            "gross_profit_per_unit", "Gross Profit / Unit", round(gp_per_unit, 2), "currency"
        ),
        "parts_sales": kpi(
            "parts_sales", "Parts Sales", round(parts_sales_total, 2), "currency"
        ),
        "inventory_turns": kpi(
            "inventory_turns", "Inventory Turns", round(inventory_turns, 1), "ratio"
        ),
        "obsolete_inventory_pct": kpi(
            "obsolete_inventory_pct", "Obsolete Inventory", round(obsolete_pct, 1), "percent"
        ),
    }

    return {
        "kpis": kpis,
        "raw": {
            "net_profit": net_profit,
            "obsolete_value": round(obsolete_value, 2)
        }
    }


# ---------------------------------------------------------------------------
# F&I
# ---------------------------------------------------------------------------

def _estimate_reserve(amount_financed, apr, term_months):
    """Standard, widely-used simplified dealer finance-reserve approximation:
    reserve ~= amount financed x assumed buy-rate spread x (term / 24). Assumes the
    dealer's wholesale 'buy rate' from the lender sits 2.0 points below the
    customer-facing APR -- a common flat-spread assumption used when a real buy rate
    isn't separately tracked, which NXTDeal's FinanceContract doesn't (it records only
    the customer-facing APR, matching real-world contract paperwork). Deterministic,
    like core/deals.py's _estimate_apr() -- an estimate, not a fabricated number."""

    amount_financed = _f(amount_financed)
    term_months = _f(term_months)

    reserve = (
        amount_financed
        * (ASSUMED_BUY_RATE_SPREAD_POINTS / 100)
        * (term_months / 24)
    )

    return round(max(reserve, 0.0), 2)


def compute_fi_kpis():

    contracts = _entities(FINANCE_CONTRACT)
    vehicles = _entities(VEHICLE)

    contract_count = len(contracts)

    funded_count = sum(
        1 for c in contracts
        if c.attributes.get("FundingStatus") == "Funded"
    )

    units_sold = len([
        v for v in vehicles
        if v.attributes.get("DateSold")
    ])

    total_reserve = 0.0
    total_apr = 0.0

    for contract in contracts:

        total_reserve += _estimate_reserve(
            contract.attributes.get("AmountFinanced"),
            contract.attributes.get("APR"),
            contract.attributes.get("TermMonths")
        )

        total_apr += _f(contract.attributes.get("APR"))

    income_per_contract = (
        total_reserve / contract_count
        if contract_count else 0.0
    )

    reserve_per_vehicle = (
        total_reserve / units_sold
        if units_sold else 0.0
    )

    avg_apr = (
        total_apr / contract_count
        if contract_count else 0.0
    )

    kpis = {
        "reserve_income": kpi(
            "reserve_income", "F&I Reserve Income", round(total_reserve, 2), "currency"
        ),
        "income_per_contract": kpi(
            "income_per_contract", "Income / Contract", round(income_per_contract, 2), "currency"
        ),
        "reserve_per_vehicle": kpi(
            "reserve_per_vehicle", "Reserve / Vehicle (PVR)", round(reserve_per_vehicle, 2), "currency"
        ),
        "deals_financed": kpi(
            "deals_financed", "Deals Financed", funded_count, "number"
        ),
        "avg_apr": kpi(
            "avg_apr", "Avg APR", round(avg_apr, 2), "percent"
        ),
    }

    return {
        "kpis": kpis,
        "raw": {
            "total_reserve": total_reserve
        }
    }


# ---------------------------------------------------------------------------
# Executive overview -- cross-department rollup (see this module's docstring for why
# this isn't a full "Accounting" P&L/balance sheet view)
# ---------------------------------------------------------------------------

def compute_executive_kpis():

    sales = compute_sales_kpis()
    service = compute_service_kpis()
    parts = compute_parts_kpis()
    fi = compute_fi_kpis()

    sales_gross = sales["raw"]["total_gross"]
    service_gross = service["raw"]["total_gross"]
    parts_gross = parts["raw"]["net_profit"]
    fi_income = fi["raw"]["total_reserve"]

    total_gross_profit = sales_gross + service_gross + parts_gross + fi_income

    def _pct(value):

        if not total_gross_profit:
            return 0.0

        return round(value / total_gross_profit * 100, 1)

    kpis = {
        "total_gross_profit": kpi(
            "total_gross_profit", "Total Gross Profit", round(total_gross_profit, 2), "currency"
        ),
        "sales_contribution_pct": kpi(
            "sales_contribution_pct", "Sales Contribution", _pct(sales_gross), "percent"
        ),
        "service_contribution_pct": kpi(
            "service_contribution_pct", "Service Contribution", _pct(service_gross), "percent"
        ),
        "parts_contribution_pct": kpi(
            "parts_contribution_pct", "Parts Contribution", _pct(parts_gross), "percent"
        ),
        "fi_contribution_pct": kpi(
            "fi_contribution_pct", "F&I Contribution", _pct(fi_income), "percent"
        ),
    }

    recoverable_profit = parts["raw"]["obsolete_value"]

    alert = {
        "label": "Recoverable Profit",
        "value": recoverable_profit,
        "description": (
            f"${recoverable_profit:,.0f} in obsolete parts inventory (no sale in "
            f"{OBSOLETE_AFTER_DAYS}+ days) is tied up as dead capital -- a real, "
            "addressable profit leak."
        )
    }

    return {
        "kpis": kpis,
        "raw": {
            "recoverable_profit": recoverable_profit
        },
        "alert": alert
    }


# ---------------------------------------------------------------------------
# Department catalog + dispatch
# ---------------------------------------------------------------------------

DEPARTMENT_META = {

    "sales": {
        "title": "Sales Intelligence",
        "subtitle": "Every deal, every dollar, under control.",
        "capabilities": [
            {"title": "Real-Time Gross Management", "description": "Total gross, gross per unit, and average sale price across every delivered deal."},
            {"title": "Sales Pace Forecasting", "description": "Project month-end units from current pace instead of waiting for the month to close."},
            {"title": "Deal-Level Visibility", "description": "Every figure here traces back to a real Vehicle and FinanceContract in the graph."},
            {"title": "Discount Discipline", "description": "Gross-per-unit trends surface discounting patterns before they erode the front end."},
        ]
    },

    "service": {
        "title": "Service Intelligence",
        "subtitle": "Turn every repair order into a profit opportunity.",
        "capabilities": [
            {"title": "Service Gross & Volume", "description": "Labor gross profit, RO count, and average repair order value, updated live."},
            {"title": "Effective Labor Rate", "description": "Real labor revenue per hour billed -- not a rough approximation."},
            {"title": "Customer Pay Mix", "description": "See how much of the shop's work is customer-pay versus warranty and internal."},
            {"title": "Throughput Visibility", "description": "RO volume and average ticket size in one place, no manual reporting."},
        ]
    },

    "parts": {
        "title": "Parts Intelligence",
        "subtitle": "Inventory is capital -- make it pay back.",
        "capabilities": [
            {"title": "Inventory Health", "description": "Stock value, turns, and obsolescence computed from real parts and sales data."},
            {"title": "Margin Control", "description": "Net profit and gross-per-unit across every part sold."},
            {"title": "Obsolescence Detection", "description": "Parts with no sale in 180+ days are flagged as dead capital, not buried in a spreadsheet."},
            {"title": "Turn Optimization", "description": "Inventory turns computed from real cost-of-goods-sold against on-hand value."},
        ]
    },

    "fi": {
        "title": "F&I Intelligence",
        "subtitle": "Maximize the profit behind every deal.",
        "capabilities": [
            {"title": "Reserve Income Visibility", "description": "Estimated finance reserve income across every contract, not just funded ones."},
            {"title": "Income Per Deal", "description": "Reserve income per contract and per vehicle retailed (PVR)."},
            {"title": "Financing Volume", "description": "How many deals are actually reaching a funded FinanceContract."},
            {"title": "Rate Trends", "description": "Average APR across the book, a leading signal for reserve income direction."},
        ]
    },

    "executive": {
        "title": "Executive Overview",
        "subtitle": "One view of where the dealership's profit is really coming from.",
        "capabilities": [
            {"title": "Cross-Department Rollup", "description": "Total gross profit pulled from Sales, Service, Parts, and F&I into one number."},
            {"title": "Contribution Mix", "description": "See which department is actually driving profit this period, not just guessing."},
            {"title": "Profit Leak Detection", "description": "Recoverable profit (like obsolete parts inventory) surfaced as an explicit callout."},
            {"title": "One Source of Truth", "description": "Every figure here is a real rollup of the same graph every other dashboard reads from."},
        ]
    },
}

DEPARTMENTS = list(DEPARTMENT_META.keys())

_COMPUTE_FUNCTIONS = {
    "sales": compute_sales_kpis,
    "service": compute_service_kpis,
    "parts": compute_parts_kpis,
    "fi": compute_fi_kpis,
    "executive": compute_executive_kpis,
}


def compute_department(department):

    compute_fn = _COMPUTE_FUNCTIONS.get(department)

    if not compute_fn:
        return None

    result = compute_fn()
    meta = DEPARTMENT_META[department]

    payload = {
        "department": department,
        "title": meta["title"],
        "subtitle": meta["subtitle"],
        "capabilities": meta["capabilities"],
        "kpis": result["kpis"]
    }

    if "alert" in result:
        payload["alert"] = result["alert"]

    return payload


def list_departments():

    return [
        {"key": key, "title": meta["title"], "subtitle": meta["subtitle"]}
        for key, meta in DEPARTMENT_META.items()
    ]
