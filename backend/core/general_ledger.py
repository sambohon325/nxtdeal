"""
core/general_ledger.py -- General Ledger (2026-07-17, session 112 follow-up). Sam's
direct instruction after every explicitly-named item in the Retail Lending Platform
arc closed: "lets keep going, simply create the fake data that is needed to build
them" -- reversing the earlier honest not_yet_tracked stance on General Ledger and
Bank Reconciliation. This module builds a real dealership-wide chart of accounts and
a real double-entry ledger, blending two kinds of entries:

1. REAL entries synced from data this codebase already has for real -- every posted
   Payment (core/loan_accounting.py, principal_portion/interest_portion already real)
   becomes a real Cash/Interest Income/Loan Principal Receivable posting, and every
   funded Deal's real Vehicle.Price/Cost becomes a real Vehicle Sales Revenue/COGS/
   Inventory posting (the same real front-end-gross math core/sales_menu.py/
   core/employee_value.py already rely on, just posted as a proper journal entry here
   instead of just summed).

2. SIMULATED entries for everything this codebase has no real data model for at all
   -- Floorplan Interest Expense (a simulated rate applied to the real HEURISTIC
   floorplan exposure core/workflow_tab_data.py already computes), Payroll Expense,
   Rent & Overhead, and Other Income. Every simulated entry carries
   `basis: "simulated_gl_entry"` plus an explicit disclaimer, same disclosure
   precedent as core/pricing_desk.py/core/acquisitions.py -- deterministically seeded
   per period so repeat generation for the same period produces the same numbers
   rather than fresh noise.

Every GlEntry is a balanced pair (or set) of debit/credit lines against the real
CHART_OF_ACCOUNTS below -- get_trial_balance() confirms total debits == total credits
across the WHOLE ledger (real + simulated combined), the actual test of whether a
general ledger is internally consistent. get_income_statement()/get_balance_sheet()
are real financial statements computed from account balances, closing the
"cash_flow_net_profit_expense_allocation_dealer_statement" not_yet_tracked gap
alongside the general_ledger one.

Entries respect core/loan_accounting.py's AccountingPeriod close the same way Payment
posting does -- once a period is closed, no further entry (real sync or simulated
generation) may be posted into it without reopening.
"""

import hashlib
from datetime import datetime, timezone, date
import calendar

from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.entity_types import GL_ENTRY, DEAL, VEHICLE
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH
from core.payments import _all_payments
from core.loan_accounting import is_period_closed
from core.loan_servicing import _safe_float


SIMULATED_BASIS = "simulated_gl_entry"
_DISCLAIMER = (
    "SIMULATED general-ledger entry -- no real payroll/overhead/floorplan-lender "
    "data feed exists in this system. Deterministically generated per accounting "
    "period from real underlying signals where one exists (e.g. real floorplan "
    "exposure), not fresh random noise on repeat reads."
)

CHART_OF_ACCOUNTS = [
    {"number": "1000", "name": "Cash", "type": "asset"},
    {"number": "1100", "name": "Loan Principal Receivable", "type": "asset"},
    {"number": "1300", "name": "Vehicle Inventory", "type": "asset"},
    {"number": "2000", "name": "Floorplan Payable", "type": "liability"},
    {"number": "3000", "name": "Owner's Equity", "type": "equity"},
    {"number": "4000", "name": "Vehicle Sales Revenue", "type": "revenue"},
    {"number": "4100", "name": "Interest Income", "type": "revenue"},
    {"number": "4200", "name": "Other Income", "type": "revenue"},
    {"number": "5000", "name": "Cost of Goods Sold (Vehicles)", "type": "expense"},
    {"number": "5100", "name": "Floorplan Interest Expense", "type": "expense"},
    {"number": "5200", "name": "Payroll Expense", "type": "expense"},
    {"number": "5300", "name": "Rent & Overhead Expense", "type": "expense"},
]

_ACCOUNTS_BY_NUMBER = {a["number"]: a for a in CHART_OF_ACCOUNTS}

_SIMULATED_FLOORPLAN_RATE_ANNUAL = 0.065  # an assumed 6.5% floorplan rate -- no real
# floorplan-lender rate exists anywhere in this codebase, this is a plausible,
# stated-as-such placeholder, not a claim about this dealer's real financing terms.
_SIMULATED_MONTHLY_RENT_OVERHEAD = 18500.0
_SIMULATED_MONTHLY_OTHER_INCOME_BASE = 1200.0


def _now():
    return datetime.now(timezone.utc).isoformat()


def _today():
    return date.today()


def _parse_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _period_key(d):
    return f"{d.year:04d}-{d.month:02d}"


def _seeded_float(seed_str, low, high):
    digest = hashlib.sha256(seed_str.encode("utf-8")).hexdigest()
    span = high - low
    fraction = (int(digest[:12], 16) % 100000) / 100000
    return round(low + fraction * span, 2)


def get_chart_of_accounts():
    return list(CHART_OF_ACCOUNTS)


def _all_entries():
    return [e for e in ledger.get_all().values() if e.entity_type == GL_ENTRY]


def _existing_source_refs():
    return {e.attributes.get("source_reference") for e in _all_entries() if e.attributes.get("source_reference")}


def _create_entry(entry_date, description, lines, source, source_reference, created_by, basis=None, disclaimer=None):
    """lines is a list of {account, debit, credit} dicts -- must balance (sum debit ==
    sum credit) or this raises a ValueError, the same real internal-consistency check
    get_trial_balance() performs across the whole ledger."""

    total_debit = round(sum(_safe_float(l.get("debit")) for l in lines), 2)
    total_credit = round(sum(_safe_float(l.get("credit")) for l in lines), 2)

    if abs(total_debit - total_credit) > 0.01:
        raise ValueError(f"Unbalanced entry: debits {total_debit} != credits {total_credit}")

    entry = Entity(
        id=id_generator.generate("GLE"),
        entity_type=GL_ENTRY,
        attributes={
            "entry_date": entry_date,
            "description": description,
            "lines": lines,
            "source": source,
            "source_reference": source_reference,
            "created_by": created_by,
            "created_at": _now(),
            "basis": basis or "real",
            "disclaimer": disclaimer,
        },
    )
    ledger.add_entity(entry)
    return entry


# ---------------------------------------------------------------------------
# Real entries synced from already-real data
# ---------------------------------------------------------------------------

def sync_real_entries(synced_by):
    """Pulls every posted Payment and every funded Deal not already synced into a real
    GlEntry -- idempotent, dedupes by source_reference so re-running only picks up new
    activity. Skips anything whose entry_date falls in an already-closed accounting
    period (same real posting-lock precedent core/loan_accounting.py's own
    post_payment_to_ledger() already established)."""
    from core.workflow_readiness import simulation_block
    blocked = simulation_block("accounting_sync")
    if blocked:
        return blocked


    existing = _existing_source_refs()
    created = []
    skipped_closed = []

    for payment in _all_payments():

        if payment.attributes.get("status") != "approved":
            continue

        if payment.attributes.get("posting_status") != "posted":
            continue

        source_reference = f"payment:{payment.id}"

        if source_reference in existing:
            continue

        entry_date = payment.attributes.get("payment_date")

        if is_period_closed(entry_date):
            skipped_closed.append(payment.id)
            continue

        amount = _safe_float(payment.attributes.get("amount"))
        interest = _safe_float(payment.attributes.get("interest_portion"))
        principal = _safe_float(payment.attributes.get("principal_portion"))

        lines = [
            {"account": "1000", "debit": amount, "credit": 0},
            {"account": "4100", "debit": 0, "credit": interest},
            {"account": "1100", "debit": 0, "credit": principal},
        ]

        entry = _create_entry(
            entry_date=entry_date,
            description=f"Loan payment {payment.id} ({payment.attributes.get('loan_id')})",
            lines=lines,
            source="loan_payment",
            source_reference=source_reference,
            created_by=synced_by,
        )
        created.append(entry.id)

    for deal in [e for e in ledger.get_all().values() if e.entity_type == DEAL]:

        if deal.attributes.get("status") != "funded":
            continue

        source_reference = f"deal:{deal.id}"

        if source_reference in existing:
            continue

        vehicle = ledger.get_entity(deal.attributes.get("vehicle_id"))

        if not vehicle or vehicle.entity_type != VEHICLE:
            continue

        price = _safe_float(vehicle.attributes.get("Price"))
        cost = _safe_float(vehicle.attributes.get("Cost"))

        if price <= 0:
            continue

        entry_date = deal.attributes.get("updated_at", "")[:10] or _today().isoformat()

        if is_period_closed(entry_date):
            skipped_closed.append(deal.id)
            continue

        lines = [
            {"account": "1000", "debit": price, "credit": 0},
            {"account": "4000", "debit": 0, "credit": price},
        ]

        if cost > 0:
            lines.extend([
                {"account": "5000", "debit": cost, "credit": 0},
                {"account": "1300", "debit": 0, "credit": cost},
            ])

        entry = _create_entry(
            entry_date=entry_date,
            description=f"Vehicle sale {deal.id} ({vehicle.id})",
            lines=lines,
            source="vehicle_sale",
            source_reference=source_reference,
            created_by=synced_by,
        )
        created.append(entry.id)

    if created:
        save_graph(GRAPH_PATH)

    return {"synced_count": len(created), "synced_entry_ids": created, "skipped_closed_period": skipped_closed}


# ---------------------------------------------------------------------------
# Simulated entries -- Floorplan Interest / Payroll / Rent & Overhead / Other Income
# ---------------------------------------------------------------------------

def generate_simulated_entries(year, month, generated_by, floorplan_exposure=0.0):

    from core.workflow_readiness import simulation_block
    blocked = simulation_block("financial_simulation")
    if blocked:
        return blocked

    period_key = f"{int(year):04d}-{int(month):02d}"

    if is_period_closed(f"{period_key}-15"):
        return {"error": f"Accounting period '{period_key}' is closed."}

    existing = _existing_source_refs()
    prefix = f"simulated:{period_key}"

    if any(ref and ref.startswith(prefix) for ref in existing):
        return {"error": f"Simulated entries for '{period_key}' already exist -- delete/reverse before regenerating."}

    days_in_month = calendar.monthrange(int(year), int(month))[1]
    entry_date = f"{period_key}-{min(days_in_month, 28):02d}"

    created = []

    # Floorplan Interest Expense -- a simulated monthly rate applied to the real
    # HEURISTIC floorplan exposure figure (core/workflow_tab_data.py's own
    # finance_floorplan_payoff), not a fully invented number.
    monthly_interest = round(_safe_float(floorplan_exposure) * (_SIMULATED_FLOORPLAN_RATE_ANNUAL / 12), 2)
    if monthly_interest > 0:
        entry = _create_entry(
            entry_date=entry_date,
            description=f"Floorplan interest expense, {period_key} (SIMULATED rate {_SIMULATED_FLOORPLAN_RATE_ANNUAL*100:.1f}% annual on real exposure)",
            lines=[
                {"account": "5100", "debit": monthly_interest, "credit": 0},
                {"account": "2000", "debit": 0, "credit": monthly_interest},
            ],
            source="simulated_floorplan_interest",
            source_reference=f"{prefix}:floorplan_interest",
            created_by=generated_by,
            basis=SIMULATED_BASIS,
            disclaimer=_DISCLAIMER,
        )
        created.append(entry.id)

    # Payroll Expense -- fully simulated, deterministically seeded per period.
    payroll = _seeded_float(f"payroll|{period_key}", 62000, 78000)
    entry = _create_entry(
        entry_date=entry_date,
        description=f"Payroll expense, {period_key} (SIMULATED -- no real payroll data source exists)",
        lines=[
            {"account": "5200", "debit": payroll, "credit": 0},
            {"account": "1000", "debit": 0, "credit": payroll},
        ],
        source="simulated_payroll",
        source_reference=f"{prefix}:payroll",
        created_by=generated_by,
        basis=SIMULATED_BASIS,
        disclaimer=_DISCLAIMER,
    )
    created.append(entry.id)

    # Rent & Overhead -- fully simulated, a fixed base with a small deterministic
    # monthly variance.
    overhead = round(_SIMULATED_MONTHLY_RENT_OVERHEAD + _seeded_float(f"overhead|{period_key}", -800, 800), 2)
    entry = _create_entry(
        entry_date=entry_date,
        description=f"Rent & overhead expense, {period_key} (SIMULATED)",
        lines=[
            {"account": "5300", "debit": overhead, "credit": 0},
            {"account": "1000", "debit": 0, "credit": overhead},
        ],
        source="simulated_overhead",
        source_reference=f"{prefix}:overhead",
        created_by=generated_by,
        basis=SIMULATED_BASIS,
        disclaimer=_DISCLAIMER,
    )
    created.append(entry.id)

    # Other Income -- fully simulated, small misc income (e.g. warranty reserve,
    # sublet labor, doc fees not otherwise tracked).
    other_income = round(_SIMULATED_MONTHLY_OTHER_INCOME_BASE + _seeded_float(f"other_income|{period_key}", -300, 900), 2)
    if other_income > 0:
        entry = _create_entry(
            entry_date=entry_date,
            description=f"Other income, {period_key} (SIMULATED)",
            lines=[
                {"account": "1000", "debit": other_income, "credit": 0},
                {"account": "4200", "debit": 0, "credit": other_income},
            ],
            source="simulated_other_income",
            source_reference=f"{prefix}:other_income",
            created_by=generated_by,
            basis=SIMULATED_BASIS,
            disclaimer=_DISCLAIMER,
        )
        created.append(entry.id)

    save_graph(GRAPH_PATH)

    return {"period_key": period_key, "generated_count": len(created), "generated_entry_ids": created}


def delete_entry(entry_id, deleted_by):
    """A real reversal mechanism -- deletes a single GlEntry (used for
    regenerating/correcting a simulated batch, or reversing a bad sync). Real entries
    synced from a Payment/Deal can be re-synced afterward via sync_real_entries()
    since dedup is by source_reference, which frees up the moment the old entry is
    gone."""

    entry = ledger.get_entity(entry_id)

    if not entry or entry.entity_type != GL_ENTRY:
        return {"error": f"GL entry '{entry_id}' not found"}

    if is_period_closed(entry.attributes.get("entry_date")):
        return {"error": "This entry's accounting period is closed -- reopen it before deleting."}

    del ledger.entities[entry_id]
    save_graph(GRAPH_PATH)

    return {"deleted": entry_id, "deleted_by": deleted_by}


# ---------------------------------------------------------------------------
# Ledger views + financial statements
# ---------------------------------------------------------------------------

def get_general_ledger(account_number=None, start_date=None, end_date=None, limit=200, offset=0):

    start = _parse_date(start_date)
    end = _parse_date(end_date)

    entries = _all_entries()

    def _in_range(entry):
        d = _parse_date(entry.attributes.get("entry_date"))
        if not d:
            return True
        if start and d < start:
            return False
        if end and d > end:
            return False
        return True

    entries = [e for e in entries if _in_range(e)]

    if account_number:
        entries = [e for e in entries if any(l.get("account") == account_number for l in e.attributes.get("lines", []))]

    entries.sort(key=lambda e: (e.attributes.get("entry_date") or "", e.id))

    return {
        "count": len(entries),
        "entries": [
            {"id": e.id, **e.attributes}
            for e in entries[max(0, int(offset)):max(0, int(offset)) + max(1, min(200, int(limit)))]
        ],
    }


def get_trial_balance(start_date=None, end_date=None):

    start = _parse_date(start_date)
    end = _parse_date(end_date)

    balances = {a["number"]: {"account": a["name"], "type": a["type"], "debit": 0.0, "credit": 0.0} for a in CHART_OF_ACCOUNTS}

    for entry in _all_entries():

        d = _parse_date(entry.attributes.get("entry_date"))
        if start and d and d < start:
            continue
        if end and d and d > end:
            continue

        for line in entry.attributes.get("lines", []):
            account = line.get("account")
            if account not in balances:
                continue
            balances[account]["debit"] += _safe_float(line.get("debit"))
            balances[account]["credit"] += _safe_float(line.get("credit"))

    total_debit = 0.0
    total_credit = 0.0

    rows = []
    for number, b in balances.items():
        b["debit"] = round(b["debit"], 2)
        b["credit"] = round(b["credit"], 2)
        total_debit += b["debit"]
        total_credit += b["credit"]
        rows.append({"account_number": number, **b})

    rows.sort(key=lambda r: r["account_number"])

    return {
        "rows": rows,
        "total_debit": round(total_debit, 2),
        "total_credit": round(total_credit, 2),
        "balanced": abs(round(total_debit - total_credit, 2)) < 0.01,
    }


def get_income_statement(start_date=None, end_date=None):

    trial_balance = get_trial_balance(start_date, end_date)

    revenue_total = 0.0
    expense_total = 0.0
    revenue_lines = []
    expense_lines = []

    for row in trial_balance["rows"]:
        net = round(row["credit"] - row["debit"], 2)
        if row["type"] == "revenue":
            revenue_total += net
            if net:
                revenue_lines.append({"account": row["account"], "amount": net})
        elif row["type"] == "expense":
            amount = round(row["debit"] - row["credit"], 2)
            expense_total += amount
            if amount:
                expense_lines.append({"account": row["account"], "amount": amount})

    return {
        "start_date": start_date,
        "end_date": end_date,
        "revenue": {"lines": revenue_lines, "total": round(revenue_total, 2)},
        "expenses": {"lines": expense_lines, "total": round(expense_total, 2)},
        "net_income": round(revenue_total - expense_total, 2),
        "note": "Blended real (loan payments, vehicle sales) + SIMULATED (floorplan interest, payroll, overhead, other income) general-ledger entries -- see each entry's own basis field.",
    }


def get_balance_sheet(as_of_date=None):

    trial_balance = get_trial_balance(end_date=as_of_date)

    assets = 0.0
    liabilities = 0.0
    equity = 0.0
    asset_lines = []
    liability_lines = []

    for row in trial_balance["rows"]:
        net = round(row["debit"] - row["credit"], 2)
        if row["type"] == "asset":
            assets += net
            asset_lines.append({"account": row["account"], "balance": net})
        elif row["type"] == "liability":
            liabilities += -net
            liability_lines.append({"account": row["account"], "balance": -net})
        elif row["type"] == "equity":
            equity += -net

    income_statement = get_income_statement(end_date=as_of_date)
    retained_earnings = income_statement["net_income"]

    return {
        "as_of_date": as_of_date or _today().isoformat(),
        "assets": {"lines": asset_lines, "total": round(assets, 2)},
        "liabilities": {"lines": liability_lines, "total": round(liabilities, 2)},
        "equity": {"owners_equity": round(equity, 2), "retained_earnings": round(retained_earnings, 2), "total": round(equity + retained_earnings, 2)},
        "balances": abs(round(assets - (liabilities + equity + retained_earnings), 2)) < 0.01,
        "note": "Blended real + SIMULATED entries -- see get_income_statement()/get_trial_balance() for the same disclosure.",
    }
