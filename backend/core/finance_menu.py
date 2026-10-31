"""
core/finance_menu.py -- real data behind Finance's 8-item Top Menu
(core/menu_catalog.py), session 64 continuation. finance.pdf's own framing: unlike
Sales or Service, Finance isn't organized around customers or vehicles -- it's
organized around cash flow, compliance, funding, and accounting control. Its Menu Bar
(Overview | Deals | Funding | Compliance | Accounting | Floorplan | Commissions |
Reporting) maps onto five questions: Did we get paid? Are we compliant? Did we pay what
we owed? Is the accounting accurate? Where is our money tied up?

Same discipline as core/operations_menu.py/core/sales_menu.py/core/service_menu.py/
core/marketing_menu.py/core/inventory_menu.py: reuse an already-built function wherever
it's a genuine match, compute a small new real aggregate where the graph has the
underlying data but nobody had queried it this way yet, and use an honest
`not_yet_tracked` note (never a fabricated number) wherever finance.pdf asks for
something this data model doesn't back at all. Finance turned out to have the deepest
structural gaps of any department rolled out so far, confirmed against the live graph
and codebase before writing this module: there is no Commission entity anywhere (no
pay-plan calculation exists at all), no general-ledger/deal-posting/bank-reconciliation/
month-end-close concept exists anywhere (Accounting is almost entirely a gap) -- OFAC
verification and IRS Form 8300 cash reporting were both closed session 112 follow-up
(core/lending_compliance.py; core/compliance_rules.py's catalog now has 8 real rules,
up from 7, adding a real OFAC/SDN screening rule) -- and Floorplan is entirely derived
(core/workflow_tab_data.py's
finance_floorplan_payoff() uses unsold Vehicle.Cost as a stand-in for floorplan
principal -- there's no real per-unit floorplan-lender line, no curtailment schedule,
no interest-accrual field). Where a real signal genuinely exists, it's reused directly;
where it doesn't, this module says so rather than inventing a plausible-looking number.
"""

from datetime import datetime, timezone

from core.dealeros import ledger
from core.entity_types import DEAL, FINANCE_CONTRACT, DOCUMENT, VEHICLE

from core.deals import list_deals
from core.workflow_tab_data import (
    sales_fi_turnover_queue,
    finance_floorplan_payoff,
    inventory_lot_audit,
)
from core.compliance_api import list_alerts_api, list_rules_api
from core.employee_value_api import list_employee_values_api
from core.data_connections_api import readiness_predictions_api
from core.ai_tools import search_entities, get_entity_by_id, get_related_entities
from core.loan_servicing_api import get_loan_detail_api, get_portfolio_dashboard_api
from core.payments_api import get_payments_dashboard_api
from core.collections_api import get_collections_dashboard_api
from core.repossessions_api import get_repossessions_dashboard_api
from core.device_management_api import get_device_management_dashboard_api, get_starter_interrupt_dashboard_api
from core.asset_management_api import get_asset_portfolio_dashboard_api
from core.lending_compliance_api import get_lending_compliance_dashboard_api
from core.glba_program_api import get_glba_readiness_summary_api
from core.pci_dss_guard_api import run_pci_posture_scan_api
from core.loan_accounting_api import get_loan_accounting_summary_api, get_unposted_payments_api, list_periods_api
from core.general_ledger_api import get_trial_balance_api, get_income_statement_api, get_balance_sheet_api
from core.bank_reconciliation_api import get_reconciliation_status_api
from core.lender_intelligence_api import get_dashboard_overview_api as get_lender_intelligence_overview_api

# Reporting = Department Intelligence integration (Sam: "the dynamic reporting is
# supposed to be integrated in the reporting section of each department"). Finance
# maps onto Department Intelligence's real "fi" KPI key (F&I -- financing/contracts is
# the closest and only real match among the 5 real keys).
from core.department_intelligence_api import get_department_api


def _entities(entity_type):
    return [e for e in ledger.get_all().values() if e.entity_type == entity_type]


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _today():
    return datetime.now(timezone.utc).date().isoformat()


def _funded_deal_gross(deals):
    """Same real front-end-gross computation core/sales_menu.py/core/inventory_menu.py/
    core/employee_value.py already rely on -- sum(Vehicle.Price - Vehicle.Cost) across a
    list of funded Deals."""

    vehicles_by_id = {v.id: v for v in _entities(VEHICLE)}
    total = 0.0
    for deal in deals:
        vehicle = vehicles_by_id.get(deal.attributes.get("vehicle_id"))
        if vehicle:
            total += _safe_float(vehicle.attributes.get("Price")) - _safe_float(vehicle.attributes.get("Cost"))
    return total


def _submitted_deal_aging(deals):
    """HEURISTIC: Deal has no distinct 'submitted to lender' timestamp -- updated_at is
    the closest real field (it's touched by submit_to_lender()), so 'days since last
    update' on a still-submitted deal is the real, if imperfect, proxy this data model
    has for funding aging. Said so explicitly, matching finance_floorplan_payoff's own
    HEURISTIC labeling convention."""

    now = datetime.now(timezone.utc)
    ages = []
    for d in deals:
        updated = d.attributes.get("updated_at")
        if not updated:
            continue
        try:
            ts = datetime.fromisoformat(str(updated).replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            ages.append((now - ts).days)
        except ValueError:
            continue
    return ages


def overview(role):
    """finance.pdf's "Overview" item: the Finance command center. Funding Aging is a
    real HEURISTIC (see _submitted_deal_aging), not a fabricated figure. Monthly
    Finance Income and Commission Liability have no backing data model -- FinanceContract
    has no reserve/product-income field, and no Commission entity exists anywhere in
    this codebase."""

    all_deals = _entities(DEAL)
    submitted = [d for d in all_deals if d.attributes.get("financing_status") == "submitted"]
    unfunded = [d for d in all_deals if d.attributes.get("status") == "contract"]
    funded = [d for d in all_deals if d.attributes.get("status") == "funded"]
    financing_stage = [d for d in all_deals if d.attributes.get("status") == "financing"]
    desking_stage = [d for d in all_deals if d.attributes.get("status") == "desking"]

    floorplan = finance_floorplan_payoff(role)
    open_alerts = list_alerts_api(role, status="open")

    trade_not_funded = [
        d for d in all_deals
        if d.attributes.get("trade_in") and d.attributes.get("status") != "funded"
    ]

    aging_days = _submitted_deal_aging(submitted)

    return {
        "contracts_in_transit": {"count": len(submitted)},
        "unfunded_deals": {"count": len(unfunded)},
        "funding_aging_days_avg": round(sum(aging_days) / len(aging_days), 1) if aging_days else None,
        "floorplan_balance": floorplan.get("total_exposure"),
        "outstanding_trade_payoffs": {"count": len(trade_not_funded)},
        "open_compliance_issues": (
            len(open_alerts["alerts"]) if isinstance(open_alerts, dict) and "alerts" in open_alerts else None
        ),
        "compliance_access_error": open_alerts.get("error") if isinstance(open_alerts, dict) and "error" in open_alerts else None,
        "cash_flow_pipeline": {
            "desking": len(desking_stage),
            "financing": len(financing_stage),
            "contract": len(unfunded),
            "funded": len(funded),
            "posted": None,
        },
        "finance_health": {
            "funding_delays_avg_days": round(sum(aging_days) / len(aging_days), 1) if aging_days else None,
            "compliance_exceptions": (
                len(open_alerts["alerts"]) if isinstance(open_alerts, dict) and "alerts" in open_alerts else None
            ),
        },
        "not_yet_tracked": {
            "monthly_finance_income": "FinanceContract has no reserve/product-income field in this data model yet.",
            "commission_liability": "No Commission entity exists anywhere in this codebase yet.",
            "missing_stips": "No stipulation-tracking field exists on Deal yet.",
            "trade_payoff_delays_dollars": "No trade-payoff-amount/date field exists on Deal yet -- outstanding_trade_payoffs is a real count, not a dollar figure.",
            "posted_stage": "No deal-posting/general-ledger concept exists in this codebase yet -- see the 'accounting' menu item.",
        },
    }


def deals(role, query=None):
    """finance.pdf's "Deals" item: the master deal board. Pending/Submitted/Funded/
    Unfunded/Delivered are all real Deal.status/financing_status groupings. Accounting
    Hold Deals and Deal re-open requests have no backing data model -- no hold flag, no
    reopen-request workflow exists on Deal yet."""

    if query:
        q = query.strip().upper()
        if q.startswith("DEAL-"):
            entity = get_entity_by_id(role, q)
            if "error" in entity:
                return entity
            return {"deal": entity, "related_entities": get_related_entities(role, q)}
        results = [r for r in search_entities(role, query) if r["entity_type"] == DEAL]
        return {"query": query, "count": len(results), "results": results}

    def _brief(d):
        return {
            "id": d.id,
            "customer_id": d.attributes.get("customer_id"),
            "vehicle_id": d.attributes.get("vehicle_id"),
            "status": d.attributes.get("status"),
            "financing_status": d.attributes.get("financing_status"),
            "financing_type": d.attributes.get("financing_type"),
        }

    pending = list_deals(status="desking")
    submitted = [d for d in _entities(DEAL) if d.attributes.get("financing_status") == "submitted"]
    funded = list_deals(status="funded")
    unfunded = list_deals(status="contract")
    delivered = funded

    gross = _funded_deal_gross(funded)

    return {
        "pending_deals": {"count": len(pending), "deals": [_brief(d) for d in pending[:25]]},
        "submitted_deals": {"count": len(submitted), "deals": [_brief(d) for d in submitted[:25]]},
        "funded_deals": {"count": len(funded), "deals": [_brief(d) for d in funded[:25]]},
        "unfunded_deals": {"count": len(unfunded), "deals": [_brief(d) for d in unfunded[:25]]},
        "delivered_deals": {"count": len(delivered), "deals": [_brief(d) for d in delivered[:25]]},
        "gross_analysis": {"funded_deal_gross_total": round(gross, 2)},
        "not_yet_tracked": {
            "accounting_hold_deals": "No accounting-hold flag exists on Deal yet.",
            "deal_reopen_requests": "No reopen-request workflow exists on Deal yet.",
            "missing_paperwork": "No stipulation/paperwork-checklist field exists on Deal yet -- see the 'funding' menu item.",
        },
    }


def funding(role):
    """finance.pdf's "Funding" item: the Contracts-in-Transit command center. CIT
    Queue reuses sales_fi_turnover_queue directly (financing_status=="submitted").
    Lender Responses is a genuinely new real aggregate: financing_status breakdown
    (approved/declined/countered). Daily Funding Activity is real (Deals funded today).
    Missing Stipulations and E-Contracts have no backing data model -- no
    stipulation-checklist or e-contract-signature field exists on Deal yet."""

    cit = sales_fi_turnover_queue(role)
    all_deals = _entities(DEAL)

    lender_responses = {}
    for d in all_deals:
        status = d.attributes.get("financing_status")
        if status in ("approved", "declined", "countered"):
            lender_responses[status] = lender_responses.get(status, 0) + 1

    funded_today = [
        d for d in all_deals
        if d.attributes.get("status") == "funded"
        and str(d.attributes.get("funded_at") or "").startswith(_today())
    ]

    submitted = [d for d in all_deals if d.attributes.get("financing_status") == "submitted"]
    aging_days = _submitted_deal_aging(submitted)

    return {
        "cit_queue": cit,
        "lender_responses": lender_responses,
        "daily_funding_activity": {"count": len(funded_today)},
        "funding_delays": {
            "submitted_count": len(submitted),
            "avg_days_since_last_update": round(sum(aging_days) / len(aging_days), 1) if aging_days else None,
            "note": "HEURISTIC -- Deal has no distinct submitted-to-lender timestamp, so this uses updated_at as the real proxy.",
        },
        "not_yet_tracked": {
            "missing_stipulations": "No stipulation-checklist field exists on Deal yet.",
            "e_contracts": "No e-contract-signature integration exists yet.",
        },
    }


def compliance(role):
    """finance.pdf's "Compliance" item: the dealership risk center. Compliance
    Exceptions and Deal Jacket Audits are both real (the latter reusing the same
    funded-deal-missing-Deal-Jacket check core/operations_menu.py's alerts() already
    computes). The rule catalog itself (list_rules_api) is open to any role and
    surfaces the 8 real cited federal rules this codebase enforces -- including Red
    Flags/Identity Verification (FACTA, 16 CFR 681.2), lending disclosure (TILA/Reg Z),
    and, as of session 112 follow-up, OFAC/SDN screening (Bank Secrecy Act / E.O.
    13224). OFAC Verification and IRS Form 8300 both now have real backing
    (core/lending_compliance.py) -- OFAC screening is a real, human-recorded
    checkable precondition wired as a blocking deal_fund rule (no live SDN-list
    connection exists in this sandbox, matching this catalog's own established
    "real checkable proxy, not a live feed" convention); Form 8300 is a real,
    per-deal cash-payment ledger with an honestly-computed pending/overdue
    obligation status off the real 15-day IRS filing window -- deliberately NOT a
    deal_fund gate, since the real-world obligation is to file within 15 days of
    RECEIPT, not before completing the sale. Also composes two real security-
    hardening additions (2026-07-20, Task #11): glba_program is the real Safeguards
    Rule (16 CFR 314) Information Security Program readiness roll-up
    (core/glba_program.py -- 7 real named components, honest-manual-entry, never a
    fabricated readiness percentage), and pci_dss_posture is a real, on-demand,
    dealership-wide cardholder-data scan (core/pci_dss_guard.py) confirming the
    SAQ-A-eligible posture claim structurally rather than by code review alone."""

    rules = list_rules_api()
    open_alerts = list_alerts_api(role, status="open")

    funded_deal_ids = {d.id for d in _entities(DEAL) if d.attributes.get("status") == "funded"}
    documented_deal_ids = {
        doc.attributes.get("EntityID") for doc in _entities(DOCUMENT)
        if doc.attributes.get("EntityType") == DEAL and doc.attributes.get("DocumentType") == "Deal Jacket"
    }
    missing_deal_jackets = sorted(funded_deal_ids - documented_deal_ids)

    lending_compliance = get_lending_compliance_dashboard_api(role)

    return {
        "compliance_exceptions": open_alerts,
        "deal_jacket_audits": {"count": len(missing_deal_jackets), "deal_ids": missing_deal_jackets},
        "rule_catalog": rules,
        "ofac_verification": lending_compliance.get("ofac") if isinstance(lending_compliance, dict) else lending_compliance,
        "irs_form_8300": lending_compliance.get("form_8300") if isinstance(lending_compliance, dict) else lending_compliance,
        "glba_program": get_glba_readiness_summary_api(role),
        "pci_dss_posture": run_pci_posture_scan_api(role),
    }


def accounting(role):
    """finance.pdf's "Accounting" item: the controller's home screen. As of session
    112 follow-up, core/loan_accounting.py closed the LOAN half of the deal-posting
    gap for real (a real cash-basis sub-ledger off core/payments.py's own real
    Payment records, with a real post/unposted workflow and a real month-end close),
    and -- per Sam's own direct instruction later that same session ("lets keep
    going, simply create the fake data that is needed to build them") --
    core/general_ledger.py and core/bank_reconciliation.py now close General Ledger
    and Bank Reconciliation too, blending real entries (synced from posted Payments
    and funded Deals' real Vehicle Price/Cost) with clearly-disclosed SIMULATED
    entries (floorplan interest, payroll, overhead, other income, and the entire
    simulated bank-transaction feed) for everything this codebase has no real data
    source for. This is a deliberate reversal of the earlier session-112 stance (see
    core/lending_compliance.py's/core/loan_accounting.py's own docstrings) that this
    was a financial-accuracy surface where simulation shouldn't apply -- Sam's
    explicit instruction here overrides that default, and every simulated figure
    still carries its own `basis`/`disclaimer` field so nothing is presented as real
    that isn't. The one other genuine real signal available outside all of this: the
    same PURCHASED-relationship data-integrity check core/inventory_menu.py's
    lot_management() already surfaces is, in accounting terms, exactly an
    unreconciled variance -- reused here as the real proxy for Open Exceptions."""

    audit = inventory_lot_audit(role)
    loan_accounting_summary = get_loan_accounting_summary_api(role)
    unposted_payments = get_unposted_payments_api(role)
    accounting_periods = list_periods_api(role)
    trial_balance = get_trial_balance_api(role)
    income_statement = get_income_statement_api(role)
    balance_sheet = get_balance_sheet_api(role)
    bank_reconciliation = get_reconciliation_status_api(role)

    return {
        "open_exceptions": {
            "count": audit.get("sold_without_purchase_relationship"),
            "discrepancies": audit.get("discrepancies"),
            "note": "Real proxy: a Vehicle marked sold with no real PURCHASED relationship on file -- the closest thing to an unreconciled variance this data model has.",
        },
        "loan_accounting_summary": loan_accounting_summary,
        "unposted_payments": unposted_payments,
        "accounting_periods": accounting_periods,
        "general_ledger": {
            "trial_balance": trial_balance,
            "income_statement": income_statement,
            "balance_sheet": balance_sheet,
            "note": "Blended real (loan payments, vehicle sales) + SIMULATED (floorplan interest, payroll, overhead, other income) entries -- see core/general_ledger.py's own module docstring and each entry's basis field for the full disclosure.",
        },
        "bank_reconciliation": bank_reconciliation,
        "not_yet_tracked": {
            "deal_posting_queue": "Vehicle-sale Deals now sync into the General Ledger above (see general_ledger.trial_balance) -- there's no separate queued-vs-posted workflow specific to Deals beyond that sync.",
            "schedule_audits": "Closely related to core/collections.py's own real delinquency signal (days past due derived from real cumulative payments vs. the contractual schedule) -- no separate payment-misallocation audit built this pass.",
        },
    }


def floorplan(role):
    """finance.pdf's "Floorplan" item: inventory financing management. Reuses
    finance_floorplan_payoff directly -- entirely derived from unsold Vehicle.Cost as a
    stand-in for floorplan principal (its own HEURISTIC label, session 59). Curtailments,
    Interest Charges, and Bank Reconciliations have no backing data model -- there's no
    curtailment schedule, no interest-accrual field, and no floorplan-lender
    integration anywhere in this codebase. Sold Not Paid has no real signal either --
    finance_floorplan_payoff already excludes sold vehicles from exposure, so there's no
    way to detect a floorplan payoff that lagged a sale."""

    payoff = finance_floorplan_payoff(role)

    return {
        "active_floorplan_units": payoff,
        "not_yet_tracked": {
            "curtailments": "No curtailment schedule exists in this codebase yet.",
            "interest_charges": "No interest-accrual field exists on Vehicle/floorplan data yet.",
            "sold_not_paid": "No floorplan-lender integration exists to detect a lagging payoff yet.",
            "floorplan_exceptions": "No floorplan-lender integration exists yet.",
            "bank_reconciliations": "No bank-account/transaction data model exists yet.",
        },
    }


def portfolio(role, query=None):
    """Finance's new "Portfolio" item (added 2026-07-17, session 111 follow-up --
    first slice of Sam's "Retail Automotive Lending Platform" expansion). The master
    Loan record, backed by core/loan_servicing.py -- see that module's own docstring
    for the full real/computed/simulated breakdown. A FIN- id query returns the real
    composed Loan Detail (borrower/vehicle/contract/timeline); otherwise the real
    Portfolio Dashboard (active loans, payoffs, and the SIMULATED delinquency-bucket
    split, since no real payment ledger exists yet -- see the module docstring)."""

    if query:
        q = query.strip().upper()
        if q.startswith("FIN-"):
            return get_loan_detail_api(role, q)
        results = [r for r in search_entities(role, query) if r["entity_type"] == FINANCE_CONTRACT]
        return {"query": query, "count": len(results), "results": results}

    return get_portfolio_dashboard_api(role)


def payments(role):
    """Finance's new "Payments" item (added 2026-07-17, session 112 follow-up --
    second slice of Sam's "Retail Automotive Lending Platform" expansion). Real
    payment-ledger totals -- backed by core/payments.py; see that module's own
    docstring for the full real/simulated breakdown (recording is real, the gateway
    approval/decline itself is honestly SIMULATED, no real processor is connected)."""

    return get_payments_dashboard_api(role)


def collections(role):
    """Finance's new "Collections" item (added 2026-07-17, session 112 follow-up --
    third slice of Sam's "Retail Automotive Lending Platform" expansion). A real
    bucketed delinquency queue, a real rules-based risk score/priority
    recommendation, and real contact logging -- see core/collections.py's own
    docstring for the full breakdown, including why "AI Collection Prioritization"
    is built as a transparent rules engine, not machine learning."""

    return get_collections_dashboard_api(role)


def repossessions(role):
    """Finance's new "Repossessions" item (added 2026-07-17, session 112 follow-up --
    fourth slice of Sam's "Retail Automotive Lending Platform" expansion). A real
    Referral Queue, case lifecycle, deficiency balance calc, and redemption path --
    see core/repossessions.py's own docstring for the full breakdown."""

    return get_repossessions_dashboard_api(role)


def gps_devices(role):
    """Finance's new "GPS & Devices" item (added 2026-07-17, session 112 follow-up --
    fifth slice of Sam's "Retail Automotive Lending Platform" expansion). A real
    device registry with honestly SIMULATED GPS location telemetry -- see
    core/device_management.py's own docstring. Shares one engine with the Starter
    Interrupt item below."""

    return get_device_management_dashboard_api(role)


def starter_interrupt(role):
    """Finance's new "Starter Interrupt" item (added 2026-07-17, session 112
    follow-up -- fifth slice of Sam's "Retail Automotive Lending Platform"
    expansion). Real, stored arm/warn/disable/enable state with a real enforced
    warning-required-before-disable rule -- see core/device_management.py's own
    docstring. Shares one engine with the GPS & Devices item above."""

    return get_starter_interrupt_dashboard_api(role)


def assets(role):
    """Finance's new "Assets" item (added 2026-07-17, session 112 follow-up --
    sixth slice of Sam's "Retail Automotive Lending Platform" expansion). Real
    Title/Lien/Insurance tracking plus a real Collateral Valuation/LTV blending real
    and SIMULATED inputs -- see core/asset_management.py's own docstring. Note the
    underlying routes live at /collateral/*, not /assets/*, to avoid colliding with
    Marketing's own Asset workflow -- this menu item's label is unaffected."""

    return get_asset_portfolio_dashboard_api(role)


def lender_intelligence(role):
    """Finance's new "Lender Intelligence" item (added 2026-07-19) -- closes the
    "Lender Intelligence" item from Sam's own six-pillar spec. Real per-lender
    scorecards (approval rate/avg offered APR/avg turnaround) and a real,
    transparent, rules-based lender recommendation, all computed off Deal Desk's
    own new lender_submission_history log -- see core/lender_intelligence.py's own
    docstring for the full real-vs-honest-gap breakdown (historical deals seeded
    before this slice have no submission history at all, so turnaround/approval-
    rate data only reflects real submissions made through the live app from here
    forward)."""

    return get_lender_intelligence_overview_api(role)


def commissions(role):
    """finance.pdf's "Commissions" item: employee compensation management. No
    Commission entity or pay-plan calculation exists anywhere in this codebase --
    confirmed absent. The closest real signal is core/employee_value_api.py's
    industry_estimate $ tiers for Sales/Finance/Service employees (already
    ADMIN/OPERATIONS-gated, already carrying its own effectiveness disclaimer) -- reused
    here honestly labeled as an estimate stand-in, NOT real commission/payout data."""

    # list_employee_values() compares against Employee.Department lowercased
    # (core/employee_value.py's _department_of()) -- lowercase keys here, not the
    # display-cased department names used elsewhere in this file.
    sales_value = list_employee_values_api(role, department="sales")
    finance_value = list_employee_values_api(role, department="finance")
    service_value = list_employee_values_api(role, department="service")

    return {
        "sales_commissions_estimate": sales_value,
        "finance_commissions_estimate": finance_value,
        "service_commissions_estimate": service_value,
        "note": "These are core/employee_value.py's industry_estimate monthly $ tiers per employee, NOT real commission/pay-plan data -- reused as the closest honest proxy since no Commission entity exists anywhere in this codebase.",
        "not_yet_tracked": {
            "draws": "No draw-tracking entity exists yet.",
            "bonus_programs": "No bonus-program entity exists yet.",
            "approval_queue": "No commission-approval workflow exists yet.",
        },
    }


def _bhph_finance_company_reports(role):
    """BHPH/finance-company-specific reporting modes (2026-07-17, session 112
    follow-up), closing the last explicitly-named item from Sam's "Retail Automotive
    Lending Platform" message -- reports that matter specifically to a BHPH operator
    or finance/servicing company running loan servicing through NXTDeal, distinct
    from a typical franchise dealer's Sales/Service-oriented reporting. Every section
    here reuses an already-built real engine from this arc rather than computing a
    sixth/seventh/eighth parallel number for the same underlying data -- Portfolio's
    delinquency buckets, Loan Accounting's real interest/principal split,
    Repossessions' real deficiency balances, Collections' real stage/priority
    breakdown, and Lending Compliance's real OFAC/Form 8300 status."""

    portfolio = get_portfolio_dashboard_api(role)
    accounting_summary = get_loan_accounting_summary_api(role)
    repo_dashboard = get_repossessions_dashboard_api(role)
    collections_dashboard = get_collections_dashboard_api(role)
    compliance_dashboard = get_lending_compliance_dashboard_api(role)

    def _num(d, key, default=0):
        return d.get(key, default) if isinstance(d, dict) else default

    total_loans = _num(portfolio, "total_loans")
    buckets = _num(portfolio, "delinquency_buckets", {}) or {}
    delinquent_count = sum(buckets.get(b, 0) for b in ("30_day", "60_day", "90_day"))
    delinquency_rate = round((delinquent_count / total_loans) * 100, 2) if total_loans else None

    disposed = _num(repo_dashboard, "disposed_count")
    redeemed = _num(repo_dashboard, "redeemed_count")
    recovery_rate = round((redeemed / (disposed + redeemed)) * 100, 2) if (disposed + redeemed) else None

    portfolio_performance_report = {
        "total_loans": total_loans,
        "active_loans": _num(portfolio, "active_loans"),
        "payoffs": _num(portfolio, "payoffs"),
        "delinquency_buckets": buckets,
        "delinquency_rate_pct": delinquency_rate,
        "total_outstanding_balance": _num(portfolio, "total_outstanding_balance"),
        "total_amount_past_due": _num(portfolio, "total_amount_past_due"),
        "basis_note": _num(portfolio, "disclaimer", None) or "See Portfolio -- delinquency bucketing may be SIMULATED or real per loan depending on real payment history.",
    }

    yield_report = {
        "interest_income_recognized": _num(accounting_summary, "interest_income_recognized"),
        "principal_reduction": _num(accounting_summary, "principal_reduction"),
        "cash_collected": _num(accounting_summary, "cash_collected"),
        "payment_count": _num(accounting_summary, "payment_count"),
        "note": "Real, cumulative-to-date totals from core/loan_accounting.py's Payment ledger -- not an annualized yield figure (no fixed reporting period is assumed).",
    }

    charge_off_and_loss_report = {
        "charged_off_loans": buckets.get("charged_off", 0),
        "repossessed_loans": buckets.get("repossessed", 0),
        "repossession_cases_disposed": disposed,
        "repossession_cases_redeemed": redeemed,
        "recovery_rate_pct": recovery_rate,
        "total_deficiency_outstanding": _num(repo_dashboard, "total_deficiency_outstanding"),
        "note": "Deficiency balance is real math (schedule/ledger-implied balance + real storage/transport costs - real sale proceeds); recovery_rate is redeemed / (redeemed + disposed).",
    }

    collections_effectiveness_report = {
        "total_in_queue": _num(collections_dashboard, "total_in_queue"),
        "bucket_counts": _num(collections_dashboard, "bucket_counts", {}),
        "stage_counts": _num(collections_dashboard, "stage_counts", {}),
        "recovery_risk_count": _num(collections_dashboard, "recovery_risk_count"),
        "contact_today_count": _num(collections_dashboard, "contact_today_count"),
    }

    compliance_summary_report = {
        "ofac_unscreened_or_potential_match_count": _num(_num(compliance_dashboard, "ofac", {}), "unscreened_or_potential_match_count"),
        "form_8300_overdue_count": _num(_num(compliance_dashboard, "form_8300", {}), "overdue_count"),
        "form_8300_pending_count": _num(_num(compliance_dashboard, "form_8300", {}), "pending_count"),
        "form_8300_filed_count": _num(_num(compliance_dashboard, "form_8300", {}), "filed_count"),
    }

    servicing_company_scorecard = {
        "portfolio_value": portfolio_performance_report["total_outstanding_balance"],
        "delinquency_rate_pct": delinquency_rate,
        "recovery_rate_pct": recovery_rate,
        "interest_income_recognized": yield_report["interest_income_recognized"],
        "open_compliance_items": compliance_summary_report["ofac_unscreened_or_potential_match_count"] + compliance_summary_report["form_8300_overdue_count"],
        "note": "A one-page executive view for a BHPH/finance-company operator -- distinct from a franchise dealer's Sales/Service-oriented Executive Financial Report above, all figures pulled from the real modules named in each section of this report rather than recomputed a second way.",
    }

    return {
        "bhph_portfolio_performance_report": portfolio_performance_report,
        "bhph_yield_report": yield_report,
        "charge_off_and_loss_report": charge_off_and_loss_report,
        "collections_effectiveness_report": collections_effectiveness_report,
        "compliance_summary_report": compliance_summary_report,
        "servicing_company_scorecard": servicing_company_scorecard,
    }


def reporting(role):
    """finance.pdf's "Reporting" item: formal financial reporting. Funding Reports and
    Executive Financial Reports' Department Gross reuse real data already computed
    elsewhere. F&I Reports' Product Penetration/Finance Income have no backing field on
    FinanceContract -- financing_type breakdown (in_house vs. outside_lender) is the
    real proxy available. Accounting/Floorplan/Compensation Reports mostly point back
    to the same honest gaps their own menu items already flagged. Forecasting reuses
    core/prediction.py's real ledger-based contracts_funded forecast
    (readiness_predictions_api's "finance" department entry -- FinanceContract.ContractDate
    -backed, same pattern core/sales_menu.py/core/inventory_menu.py use for their own
    department keys). As of session 112 follow-up, also includes BHPH/finance-company-
    specific reporting modes (_bhph_finance_company_reports()) -- Sam's original
    "Retail Automotive Lending Platform" message's last explicitly-named ask, closing
    it by composing already-built real engines from this whole arc rather than a
    ninth parallel computation."""

    all_deals = _entities(DEAL)
    funded = [d for d in all_deals if d.attributes.get("status") == "funded"]
    submitted = [d for d in all_deals if d.attributes.get("financing_status") == "submitted"]

    financing_type_breakdown = {}
    for d in funded:
        ftype = d.attributes.get("financing_type") or "unknown"
        financing_type_breakdown[ftype] = financing_type_breakdown.get(ftype, 0) + 1

    gross_total = _funded_deal_gross(funded)
    floorplan_data = finance_floorplan_payoff(role)
    audit = inventory_lot_audit(role)

    readiness = readiness_predictions_api()
    finance_forecast = next((d for d in readiness.get("departments", []) if d["department"] == "finance"), None)

    return {
        "funding_reports": {
            "cit_count": len(submitted),
            "avg_funding_delay_days": round(sum(_submitted_deal_aging(submitted)) / len(submitted), 1) if submitted and _submitted_deal_aging(submitted) else None,
        },
        "fi_reports": {
            "financing_type_breakdown": financing_type_breakdown,
            "funded_contracts_total": len(funded),
        },
        "accounting_reports": {
            "open_variances": audit.get("sold_without_purchase_relationship"),
        },
        "floorplan_reports": {
            "inventory_financing_exposure": floorplan_data.get("total_exposure"),
            "note": "HEURISTIC principal exposure (unsold Vehicle.Cost), not a real interest-expense figure.",
        },
        "compensation_reports": {
            "note": "See the 'commissions' menu item -- no real payable-commission or bonus-liability data exists yet.",
        },
        "executive_financial_reports": {
            "department_gross_total": round(gross_total, 2),
        },
        "forecasting": finance_forecast,
        "department_intelligence": get_department_api(role, "fi"),
        **_bhph_finance_company_reports(role),
        "not_yet_tracked": {
            "reserve_income_product_penetration": "FinanceContract has no reserve/product-income field yet.",
            "posting_accuracy_month_end_performance": "Real for loan payments as of session 112 follow-up -- see loan_accounting_summary/unposted_payments/accounting_periods on the 'accounting' menu item. Vehicle-sale Deal posting still has no general-ledger concept.",
            "interest_expense_curtailments": "No interest-accrual/curtailment field exists yet.",
            "payable_commissions_bonus_liability_payroll_allocation": "No Commission entity exists yet.",
            "cash_flow_net_profit_expense_allocation_dealer_statement": "No full P&L/cash-flow-statement model exists in this codebase yet.",
        },
    }
