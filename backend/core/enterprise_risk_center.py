"""
core/enterprise_risk_center.py -- Readiness's reimagined "Exceptions" Top Menu
item (core/menu_catalog.py's Readiness list, key unchanged: "exceptions"), which
is ALSO Sam's separately-named "Enterprise Risk Center" capstone feature
("Monitor Compliance, Funding, Collections, Inventory, Security, Data from one
dashboard"). Sam's own message described the old Exceptions item as something
that "could become an active risk center" and separately named the capstone --
confirmed to be the same real feature before writing anything, so this is built
ONCE, not twice. core/readiness_menu.py's `exceptions(role)` now composes this
module directly in place of its old thin stub.

Sam's spec for this item:
  - Critical Issues: Vehicles Missing Titles, Contracts Missing Documents,
    Inventory Not Located, Data Sync Failures
  - Financial Exceptions: Unfunded Contracts, Funding Delays, Negative Gross Deals
  - Operational Exceptions: Recon Delays, Service Delays, Open Compliance Issues
  - Risk Scoring: every exception gets Low/Medium/High/Critical

This is a COMPOSITION engine, not a new signal-detection pass -- same discipline
core/business_health.py just established for Readiness. 9 of the 10 exception
types reuse an already-real, already-computed signal elsewhere in this
~110-prior-session codebase:

  vehicles_missing_titles      -> core/operations_overview.py's Action Center
                                   (real, broad unsold-inventory Title check)
  contracts_missing_documents  -> core/operations_alerts.py's "missing_deal_jacket"
                                   alert type (funded Deals with no Deal Jacket/
                                   Buyer Order on file)
  inventory_not_located        -> core/lot_control.py's Key Management "missing"
                                   board -- HONEST SCOPE: no GPS/geofence tracking
                                   exists anywhere in this codebase, so this is
                                   scoped to vehicles whose KEY has been reported
                                   missing (a real, defensible "can't currently
                                   move/show this unit" proxy), not a claim the
                                   vehicle itself is physically lost
  data_sync_failures            -> core/data_connections.py's Connection records
                                   with status == "error" (the same real signal
                                   core/readiness_menu.py's old exceptions() stub
                                   already used for this exact field)
  unfunded_contracts            -> core/deals.py's real Deal.status == "contract"
                                   population
  funding_delays                -> core/operations_alerts.py's "stalled_deal"
                                   alert type (financing/contract-stage Deals
                                   stalled 3+ days, HEURISTIC off updated_at --
                                   Deal has no distinct submitted-to-lender
                                   timestamp)
  recon_delays                  -> core/operations_scheduling.py's real recon
                                   backlog (HEURISTIC -- no recon-stage field
                                   exists on Vehicle, so this is the real
                                   population recon work applies to)
  service_delays                -> core/shop_control.py's real Shop Bottlenecks
                                   (Parts Delays, Approval Delays, Technician
                                   Delays / stalled ROs)
  open_compliance_issues        -> core/compliance_api.py's real cited-federal-
                                   rule alert stream

The ONE genuinely new real signal this module introduces is negative_gross_deals
-- nothing anywhere in this codebase had ever computed PER-DEAL gross profit and
flagged a loss before (confirmed via grep: core/sales_menu.py/core/
employee_value.py only ever sum Vehicle.Price - Vehicle.Cost in AGGREGATE across
funded Deals). This module applies that exact same real formula per-deal for the
first time, real data (Vehicle.Price/Vehicle.Cost, both already-established real
fields), just never composed this way before.

Risk Scoring: Sam explicitly asked for Low/Medium/High/Critical (4 tiers),
distinct from core/operations_alerts.py's own simpler 2-tier red/yellow scheme.
Rather than reinvent per-item judgment calls, every exception type's severity is
computed via one of three small, transparent, REAL-magnitude-based rules (see
_count_severity/_dollar_severity below) -- a count-based bucket for
population-size exceptions and a dollar-magnitude bucket for the one
dollar-denominated exception (negative gross). Where a source already carries
its own real 2-tier severity (operations_alerts' red/yellow, compliance's
high/medium), that's mapped onto the 4-tier scale (red/high -> "critical",
yellow/medium -> "high") rather than silently discarded. An exception type with
a real, current count of zero is NOT included in the response's non-null-severity
items -- an all-clear type isn't a risk, matching core/operations_alerts.py's own
"no fabricated green tier" convention -- but it's still reported with
severity=None and count=0 so the UI can show "0 -- clear" rather than silently
omitting the category.

No blended overall risk score is computed, same reasoning core/business_health.py
already gave for its own overall_score: these 10 exception types span
incompatible units (headcounts, dollars, day-counts) with no real methodology to
weight them into one number. The KPI strip is a real count-by-severity roll-up
instead (how many Critical/High/Medium/Low exceptions exist right now), which is
the real, honest analog to a single risk score.
"""

from core.dealeros import ledger
from core.entity_types import DEAL, VEHICLE

from core.compliance_api import list_alerts_api
from core.data_connections_api import list_connections_api
from core.operations_alerts_api import get_alert_feed_api
from core.operations_overview_api import get_operations_overview_api
from core.lot_control_api import get_key_board_api
from core.operations_scheduling_api import get_recon_schedule_api
from core.shop_control_api import get_bottlenecks_api
from core.deals import list_deals


SEVERITY_LEVELS = ("low", "medium", "high", "critical")
_SEVERITY_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def _entities(entity_type):
    return [e for e in ledger.get_all().values() if e.entity_type == entity_type]


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _count_severity(count):
    """Generic real-magnitude bucket for population-size exceptions (missing
    titles/documents, key-missing vehicles, sync failures, unfunded contracts,
    recon backlog). 0 -> None (not a risk). 1-2 -> low. 3-9 -> medium.
    10-24 -> high. 25+ -> critical."""

    if not count or count <= 0:
        return None
    if count <= 2:
        return "low"
    if count <= 9:
        return "medium"
    if count <= 24:
        return "high"
    return "critical"


def _dollar_severity(amount):
    """Real dollar-magnitude bucket, used only for negative_gross_deals'
    aggregate loss total. 0 -> None. <$1,000 -> low. <$5,000 -> medium.
    <$15,000 -> high. $15,000+ -> critical."""

    if not amount or amount <= 0:
        return None
    if amount < 1000:
        return "low"
    if amount < 5000:
        return "medium"
    if amount < 15000:
        return "high"
    return "critical"


def _twotier_to_fourtier(twotier):
    """Maps core/operations_alerts.py's real 2-tier red/yellow scheme (or
    core/compliance_rules.py's real high/medium scheme) onto the 4-tier scale
    this module reports -- red/high -> critical, yellow/medium -> high. Never
    silently discarded, always an explicit mapping."""

    return "critical" if twotier in ("red", "high") else "high"


def _worst_severity(severities):
    present = [s for s in severities if s]
    if not present:
        return None
    return max(present, key=lambda s: _SEVERITY_RANK.get(s, -1))


def _denied_item(key, title, category, resolve, result):
    return {
        "key": key,
        "title": title,
        "category": category,
        "severity": None,
        "count": None,
        "basis": "real",
        "items": [],
        "access_error": result.get("error") if isinstance(result, dict) else "Access denied.",
        "resolve": resolve,
    }


# ---------------------------------------------------------------------------
# Critical Issues
# ---------------------------------------------------------------------------

def _vehicles_missing_titles(role):
    resolve = {"department": "Operations", "item_key": "documents", "hint": "Request the missing Title document."}

    overview = get_operations_overview_api(role)
    action_center = overview.get("action_center") if isinstance(overview, dict) else None
    block = (action_center or {}).get("vehicles_missing_titles") or {}
    count = block.get("count") or 0

    items = [
        {"id": v.get("vehicle_id"), "label": f"VIN {v.get('vin')} (Stock {v.get('stock_number')})"}
        for v in (block.get("vehicles") or [])[:25]
    ]

    return {
        "key": "vehicles_missing_titles",
        "title": "Vehicles Missing Titles",
        "category": "critical",
        "severity": _count_severity(count),
        "count": count,
        "basis": "real",
        "items": items,
        "note": "Real unsold Vehicles with no Title document on file (core/operations_overview.py's Action Center).",
        "resolve": resolve,
    }


def _contracts_missing_documents(role):
    resolve = {"department": "Operations", "item_key": "documents", "hint": "Request the missing Deal Jacket / Buyer Order."}

    feed = get_alert_feed_api(role)
    if isinstance(feed, dict) and "error" in feed:
        return _denied_item("contracts_missing_documents", "Contracts Missing Documents", "critical", resolve, feed)

    matches = [a for a in feed.get("alerts", []) if a.get("alert_type") == "missing_deal_jacket"]
    items = [{"id": a.get("source_id"), "label": a.get("detail")} for a in matches[:25]]

    return {
        "key": "contracts_missing_documents",
        "title": "Contracts Missing Documents",
        "category": "critical",
        "severity": _count_severity(len(matches)),
        "count": len(matches),
        "basis": "real",
        "items": items,
        "note": "Real funded Deals with no Deal Jacket/Buyer Order document on file (core/operations_alerts.py / core/document_workflows.py).",
        "resolve": resolve,
    }


def _inventory_not_located(role):
    resolve = {"department": "Inventory", "item_key": "lot_management", "hint": "Open the Key Management tab and resolve the missing key."}

    board = get_key_board_api(role)
    if isinstance(board, dict) and "error" in board:
        return _denied_item("inventory_not_located", "Inventory Not Located", "critical", resolve, board)

    missing = board.get("missing", [])
    items = [{"id": v.get("vehicle_id"), "label": f"VIN {v.get('vin')} -- key reported missing"} for v in missing[:25]]

    return {
        "key": "inventory_not_located",
        "title": "Inventory Not Located",
        "category": "critical",
        "severity": _count_severity(len(missing)),
        "count": len(missing),
        "basis": "real",
        "items": items,
        "note": (
            "HONEST SCOPE: no vehicle GPS/geofence tracking exists anywhere in this codebase -- "
            "'not located' is scoped to vehicles whose KEY has been reported missing "
            "(core/lot_control.py), a real, defensible 'can't currently move/show this unit' "
            "proxy, not a claim the vehicle itself is physically lost."
        ),
        "resolve": resolve,
    }


def _data_sync_failures(role):
    resolve = {"department": "Readiness", "item_key": "data_health", "hint": "Review the failing Data Connection and re-test it."}

    result = list_connections_api(role)
    if isinstance(result, dict) and "error" in result:
        return _denied_item("data_sync_failures", "Data Sync Failures", "critical", resolve, result)

    connections = result.get("connections", [])
    failures = [c for c in connections if c.get("status") == "error"]
    items = [
        {"id": c.get("id"), "label": f"{c.get('name', c.get('id'))} ({c.get('department', '—')})"}
        for c in failures[:25]
    ]

    return {
        "key": "data_sync_failures",
        "title": "Data Sync Failures",
        "category": "critical",
        "severity": _count_severity(len(failures)),
        "count": len(failures),
        "basis": "real",
        "items": items,
        "note": "Real Data Connection records (core/data_connections.py) with status == 'error'.",
        "resolve": resolve,
    }


# ---------------------------------------------------------------------------
# Financial Exceptions
# ---------------------------------------------------------------------------

def _unfunded_contracts(role):
    resolve = {"department": "Finance", "item_key": "deals", "hint": "Open the Deal Desk and move the deal toward funding."}

    unfunded = list_deals(status="contract")
    items = [
        {"id": d.id, "label": f"{d.id} -- {d.attributes.get('financing_type') or 'unknown financing'}"}
        for d in unfunded[:25]
    ]

    return {
        "key": "unfunded_contracts",
        "title": "Unfunded Contracts",
        "category": "financial",
        "severity": _count_severity(len(unfunded)),
        "count": len(unfunded),
        "basis": "real",
        "items": items,
        "note": "Real Deals in 'contract' status -- financing approved/contract generated but not yet funded (core/deals.py).",
        "resolve": resolve,
    }


def _funding_delays(role):
    resolve = {"department": "Finance", "item_key": "deals", "hint": "Follow up with the lender / move the stalled deal forward."}

    feed = get_alert_feed_api(role)
    if isinstance(feed, dict) and "error" in feed:
        return _denied_item("funding_delays", "Funding Delays", "financial", resolve, feed)

    matches = [a for a in feed.get("alerts", []) if a.get("alert_type") == "stalled_deal"]
    items = [
        {"id": a.get("source_id"), "label": a.get("title"), "severity": _twotier_to_fourtier(a.get("severity"))}
        for a in matches[:25]
    ]
    severity = _worst_severity(item["severity"] for item in items)

    return {
        "key": "funding_delays",
        "title": "Funding Delays",
        "category": "financial",
        "severity": severity,
        "count": len(matches),
        "basis": "heuristic",
        "items": items,
        "note": (
            "HEURISTIC: real financing/contract-stage Deals with no update in 3+ days -- "
            "Deal has no distinct submitted-to-lender timestamp, so updated_at is the real "
            "proxy this data model has (core/operations_alerts.py's stalled_deal check, the "
            "same signal core/finance_menu.py's funding_aging_days_avg is built on)."
        ),
        "resolve": resolve,
    }


def _negative_gross_deals(role):
    resolve = {"department": "Finance", "item_key": "deals", "hint": "Review the deal's pricing/cost basis in the Deal Desk."}

    vehicles_by_id = {v.id: v for v in _entities(VEHICLE)}
    funded = list_deals(status="funded")

    negatives = []
    total_loss = 0.0
    for d in funded:
        vehicle = vehicles_by_id.get(d.attributes.get("vehicle_id"))
        if not vehicle:
            continue
        gross = _safe_float(vehicle.attributes.get("Price")) - _safe_float(vehicle.attributes.get("Cost"))
        if gross < 0:
            negatives.append({
                "id": d.id,
                "label": f"{d.id} -- {vehicle.attributes.get('Year')} {vehicle.attributes.get('Make')} {vehicle.attributes.get('Model')} at ${gross:,.2f} gross",
                "gross": round(gross, 2),
            })
            total_loss += -gross

    negatives.sort(key=lambda x: x["gross"])

    return {
        "key": "negative_gross_deals",
        "title": "Negative Gross Deals",
        "category": "financial",
        "severity": _dollar_severity(total_loss),
        "count": len(negatives),
        "basis": "real",
        "items": negatives[:25],
        "total_loss": round(total_loss, 2),
        "note": (
            "NEW real per-deal check (the first time this codebase computes this) -- real "
            "funded Deals where the linked Vehicle's Price is below its Cost, i.e. "
            "Vehicle.Price - Vehicle.Cost < 0 for that one unit. Same real gross-profit "
            "formula core/sales_menu.py/core/employee_value.py already use in AGGREGATE, "
            "applied per-deal here for the first time."
        ),
        "resolve": resolve,
    }


# ---------------------------------------------------------------------------
# Operational Exceptions
# ---------------------------------------------------------------------------

def _recon_delays(role):
    resolve = {"department": "Operations", "item_key": "scheduling", "hint": "Open Recon Scheduling and assign a target date."}

    result = get_recon_schedule_api(role)
    if isinstance(result, dict) and "error" in result:
        return _denied_item("recon_delays", "Recon Delays", "operational", resolve, result)

    count = result.get("used_unsold_count") or 0
    items = [
        {"id": v.get("vehicle_id"), "label": f"VIN {v.get('vin')} -- {v.get('year')} {v.get('make')} {v.get('model')} ({v.get('lot')})"}
        for v in (result.get("vehicles") or [])[:25]
    ]

    return {
        "key": "recon_delays",
        "title": "Recon Delays",
        "category": "operational",
        "severity": _count_severity(count),
        "count": count,
        "basis": "heuristic",
        "items": items,
        "note": result.get("note") or (
            "HEURISTIC: no recon-stage/recon-complete field exists on Vehicle -- this is the "
            "real backlog of unsold Used-condition units recon work applies to, not a true "
            "per-unit delay duration (core/operations_scheduling.py)."
        ),
        "resolve": resolve,
    }


def _service_delays(role):
    resolve = {"department": "Service", "item_key": "shop_control", "hint": "Open Shop Control and dispatch/expedite the stalled repair order."}

    result = get_bottlenecks_api(role)
    if isinstance(result, dict) and "error" in result:
        return _denied_item("service_delays", "Service Delays", "operational", resolve, result)

    parts = result.get("parts_delays", {}) or {}
    approval = result.get("approval_delays", {}) or {}
    tech = result.get("technician_delays", {}) or {}
    count = (parts.get("count") or 0) + (approval.get("count") or 0) + (tech.get("count") or 0)

    items = []
    for r in (parts.get("repair_orders") or [])[:10]:
        items.append({"id": r.get("id"), "label": f"{r.get('id')} -- parts backordered"})
    for r in (approval.get("repair_orders") or [])[:10]:
        items.append({"id": r.get("id"), "label": f"{r.get('id')} -- awaiting customer approval {r.get('hours_open')}h"})
    for r in (tech.get("repair_orders") or [])[:10]:
        items.append({"id": r.get("id"), "label": f"{r.get('id')} -- stalled, no labor posted {r.get('hours_open')}h"})

    return {
        "key": "service_delays",
        "title": "Service Delays",
        "category": "operational",
        "severity": _count_severity(count),
        "count": count,
        "basis": "real",
        "items": items[:25],
        "note": (
            "Real composed Shop Bottlenecks -- Parts Delays (backordered), Approval Delays "
            "(Customer-Approval-stage ROs open 24+ hours), and Technician Delays (stalled "
            "ROs, 9+ hours open with zero labor posted) (core/shop_control.py)."
        ),
        "resolve": resolve,
    }


def _open_compliance_issues(role):
    resolve = {"department": "Finance", "item_key": "compliance", "hint": "Resolve or override the compliance alert."}

    result = list_alerts_api(role, status="open")
    if isinstance(result, dict) and "error" in result:
        return _denied_item("open_compliance_issues", "Open Compliance Issues", "operational", resolve, result)

    alerts = result.get("alerts", [])
    items = [{"id": a.get("id"), "label": a.get("law") or a.get("category") or "Compliance exception"} for a in alerts[:25]]
    severity = None
    if alerts:
        severity = "critical" if any(a.get("severity") == "high" for a in alerts) else "high"

    return {
        "key": "open_compliance_issues",
        "title": "Open Compliance Issues",
        "category": "operational",
        "severity": severity,
        "count": len(alerts),
        "basis": "real",
        "items": items,
        "note": (
            "Real cited-federal-rule compliance alerts (core/compliance_rules.py's 8-rule "
            "catalog) still open. Every one already BLOCKS a real downstream action (deal "
            "funding, campaign activation, asset/website publish, connection creation) per "
            "core/compliance.py's enforce_gate()."
        ),
        "resolve": resolve,
    }


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------

_EXCEPTION_FUNCTIONS = {
    "vehicles_missing_titles": _vehicles_missing_titles,
    "contracts_missing_documents": _contracts_missing_documents,
    "inventory_not_located": _inventory_not_located,
    "data_sync_failures": _data_sync_failures,
    "unfunded_contracts": _unfunded_contracts,
    "funding_delays": _funding_delays,
    "negative_gross_deals": _negative_gross_deals,
    "recon_delays": _recon_delays,
    "service_delays": _service_delays,
    "open_compliance_issues": _open_compliance_issues,
}

_CATEGORY_ORDER = ("critical", "financial", "operational")


def get_risk_center_overview(role):
    """Composes all 10 exception types, grouped into Sam's 3 categories, plus a
    real count-by-severity KPI roll-up. No blended overall risk score -- see
    this module's own docstring for why (same reasoning core/business_health.py
    already gave for its own overall_score)."""

    items = [fn(role) for fn in _EXCEPTION_FUNCTIONS.values()]

    by_category = {c: [] for c in _CATEGORY_ORDER}
    for item in items:
        by_category.setdefault(item["category"], []).append(item)

    severity_counts = {level: 0 for level in SEVERITY_LEVELS}
    total_exceptions = 0
    for item in items:
        if item.get("severity"):
            severity_counts[item["severity"]] += 1
        if item.get("count"):
            total_exceptions += item["count"]

    return {
        "categories": {
            "critical_issues": by_category["critical"],
            "financial_exceptions": by_category["financial"],
            "operational_exceptions": by_category["operational"],
        },
        "kpi": {
            "total_exception_types_active": sum(1 for i in items if i.get("severity")),
            "total_exception_types": len(items),
            "total_affected_entities": total_exceptions,
            "by_severity": severity_counts,
        },
        "overall_risk_score": None,
        "overall_risk_score_note": (
            "No single blended risk score is computed -- these 10 exception types span "
            "incompatible units (headcounts, dollars, day-counts) with no real methodology "
            "to weight them into one number, same reasoning core/business_health.py's own "
            "overall_score gives. The by_severity KPI roll-up above (how many Critical/High/"
            "Medium/Low exceptions exist right now) is the real, honest analog."
        ),
    }


def get_risk_center_category(role, category):
    """Sam's per-category drill-down -- one of critical/financial/operational."""

    key = (category or "").strip().lower()
    if key not in _CATEGORY_ORDER:
        return {"error": f"Unknown category '{category}' -- expected one of {list(_CATEGORY_ORDER)}."}

    fn_names = {
        "critical": ["vehicles_missing_titles", "contracts_missing_documents", "inventory_not_located", "data_sync_failures"],
        "financial": ["unfunded_contracts", "funding_delays", "negative_gross_deals"],
        "operational": ["recon_delays", "service_delays", "open_compliance_issues"],
    }[key]

    return {
        "category": key,
        "items": [_EXCEPTION_FUNCTIONS[name](role) for name in fn_names],
    }
