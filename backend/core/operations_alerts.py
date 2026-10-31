"""
core/operations_alerts.py -- Operations' "Alerts" item, upgraded from a read-only
exception report (core/operations_menu.py's alerts(), session 60) into a real
nervous system (session 106 follow-up #7, "keep going" autonomous continuation,
seventh slice of Operations' rebuild). Sam's own framing for this item: red/
yellow/green severity, and real actions, not just a list.

The unified feed pulls together every real exception signal this codebase
already computes across five different modules -- compliance alerts, lot-audit
ownership mismatches, stalled unfunded deals, missing deal jackets, overdue
OperationsTasks, at-risk deliveries, and critical-band aging inventory -- into
one severity-ranked list. Nothing here invents a new signal; this module's job
is aggregation, ranking, and action-wiring, not detection.

Severity is a real, if simple, two-tier scheme (red = needs action now, yellow =
needs attention soon) computed from each source's own real fields (compliance's
own `severity`, days-based thresholds for deals/deliveries, task SLA overdueness,
negative margin for aging). No fabricated "green" tier is returned -- an
all-clear item isn't an alert, so it isn't in this feed at all, matching Sam's
"nervous system" framing (a triage list, not a status board).

Every alert type is wired to a real action. Five of seven reuse an
already-built mutation directly (the frontend calls it, this module just tells
it which one applies):
  - compliance          -> core.compliance_api.resolve_alert_api / override_alert_api
  - missing_deal_jacket -> core.document_workflows.request_document (Deal Jacket)
  - overdue_task        -> core.operations_tasks.escalate_task
  - at_risk_delivery    -> core.operations_scheduling.schedule_delivery
  - critical_aging      -> core.inventory_aging.reduce_price / request_manager_review

The two signal types that had NO existing action anywhere in this codebase
(ownership_mismatch, stalled_deal) get this module's one genuinely new
capability: acknowledge_alert() creates a real OperationsTask for them, deduped
by source_entity_id exactly like core/operations_tasks.py's own
sync_derived_tasks() -- acknowledging one of these alerts is what actually
creates the trackable ticket, rather than being a no-op click.
"""

from datetime import datetime, timezone

from core.dealeros import ledger
from core.entity_types import DEAL, DOCUMENT

from core.workflow_tab_data import inventory_lot_audit
from core.operations_tasks import create_task, list_tasks, _existing_source_ids
from core.inventory_aging import get_aging_board
from core.operations_scheduling import get_delivery_risk_board


def _now():
    return datetime.now(timezone.utc)


def _parse(ts):
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _days_since(ts):
    dt = _parse(ts)
    if not dt:
        return None
    return round((_now() - dt).total_seconds() / 86400, 1)


def _entities(entity_type):
    return [e for e in ledger.get_all().values() if e.entity_type == entity_type]


def get_alert_feed(role):

    from core.compliance_api import list_alerts_api

    alerts = []

    # 1. Compliance -- real severity already computed by core/compliance_rules.py.
    compliance = list_alerts_api(role, status="open")
    if isinstance(compliance, dict) and "alerts" in compliance:
        for a in compliance["alerts"]:
            alerts.append({
                "alert_type": "compliance",
                "severity": "red" if a.get("severity") == "high" else "yellow",
                "title": a.get("law", a.get("category", "Compliance exception")),
                "detail": a.get("description", ""),
                "source_id": a.get("id"),
                "linked_entity_id": a.get("entity_id"),
                "suggested_action": "resolve_compliance",
            })

    # 2. Inventory ownership mismatches -- a real Vehicle marked sold with no
    # PURCHASED relationship on file. Data-integrity issue, always red.
    lot_audit = inventory_lot_audit(role)
    if isinstance(lot_audit, dict):
        for d in lot_audit.get("discrepancies", []):
            alerts.append({
                "alert_type": "ownership_mismatch",
                "severity": "red",
                "title": "Ownership mismatch",
                "detail": f"VIN {d.get('vin')} marked sold with no PURCHASED relationship on file",
                "source_id": d.get("vehicle_id"),
                "linked_entity_id": d.get("vehicle_id"),
                "suggested_action": "acknowledge",
            })

    # 3. Stalled deals -- financing/contract-stage deals with no update in a
    # while. HEURISTIC: Deal has no submitted-to-lender timestamp, so
    # updated_at is the real proxy, same convention core/finance_menu.py's
    # funding_aging already established.
    for d in _entities(DEAL):
        if d.attributes.get("status") not in ("financing", "contract"):
            continue
        days = _days_since(d.attributes.get("updated_at"))
        if days is None or days < 3:
            continue
        alerts.append({
            "alert_type": "stalled_deal",
            "severity": "red" if days >= 7 else "yellow",
            "title": f"Deal stalled {days} days",
            "detail": f"Status '{d.attributes.get('status')}' with no update in {days} days (HEURISTIC, off updated_at)",
            "source_id": d.id,
            "linked_entity_id": d.id,
            "suggested_action": "acknowledge",
        })

    # 4. Missing deal jackets -- funded deals with no Deal Jacket document.
    funded_deal_ids = {d.id for d in _entities(DEAL) if d.attributes.get("status") == "funded"}
    documented_deal_ids = {
        doc.attributes.get("EntityID") for doc in _entities(DOCUMENT)
        if doc.attributes.get("EntityType") == DEAL and doc.attributes.get("DocumentType") == "Deal Jacket"
    }
    for deal_id in sorted(funded_deal_ids - documented_deal_ids):
        alerts.append({
            "alert_type": "missing_deal_jacket",
            "severity": "yellow",
            "title": "Missing Deal Jacket",
            "detail": f"{deal_id} is funded with no Deal Jacket on file",
            "source_id": deal_id,
            "linked_entity_id": deal_id,
            "suggested_action": "request_deal_jacket",
        })

    # 5. Overdue OperationsTasks -- reuses the SLA clock already computed by
    # core/operations_tasks.py, so this feed doesn't recompute overdueness a
    # second way.
    for t in list_tasks(overdue_only=True):
        alerts.append({
            "alert_type": "overdue_task",
            "severity": "red",
            "title": f"Overdue task: {t.attributes.get('task_type')}",
            "detail": t.attributes.get("detail", ""),
            "source_id": t.id,
            "linked_entity_id": t.attributes.get("linked_entity_id"),
            "suggested_action": "escalate_task",
        })

    # 6. At-risk deliveries -- reuses core/operations_scheduling.py's real
    # cross-reference of contract/funded Deals against open delivery
    # Appointments.
    delivery_risk = get_delivery_risk_board(role)
    if isinstance(delivery_risk, dict):
        for d in delivery_risk.get("overdue", {}).get("deals", []):
            alerts.append({
                "alert_type": "at_risk_delivery",
                "severity": "red",
                "title": "Delivery overdue",
                "detail": f"{d.get('deal_id')} had a delivery appointment scheduled that's now past",
                "source_id": d.get("deal_id"),
                "linked_entity_id": d.get("deal_id"),
                "suggested_action": "schedule_delivery",
            })
        for d in delivery_risk.get("no_delivery_scheduled", {}).get("deals", []):
            alerts.append({
                "alert_type": "at_risk_delivery",
                "severity": "yellow",
                "title": "No delivery scheduled",
                "detail": f"{d.get('deal_id')} is in status '{d.get('status')}' with no delivery appointment on file",
                "source_id": d.get("deal_id"),
                "linked_entity_id": d.get("deal_id"),
                "suggested_action": "schedule_delivery",
            })

    # 7. Critical-band aging inventory -- negative-margin units in the top
    # price band, reusing core/inventory_aging.py's real per-band listing.
    aging = get_aging_board()
    if isinstance(aging, dict):
        for v in aging.get("by_price_band", {}).get("40k_plus", []):
            if v.get("margin_pct") is not None and v["margin_pct"] < 0:
                alerts.append({
                    "alert_type": "critical_aging",
                    "severity": "yellow",
                    "title": "Negative-margin aging unit",
                    "detail": f"{v.get('year')} {v.get('make')} {v.get('model')} -- {v.get('margin_pct')}% margin at ${v.get('price')}",
                    "source_id": v.get("vehicle_id"),
                    "linked_entity_id": v.get("vehicle_id"),
                    "suggested_action": "reduce_price",
                })

    alerts.sort(key=lambda a: {"red": 0, "yellow": 1}.get(a["severity"], 2))

    return {
        "count": len(alerts),
        "red_count": sum(1 for a in alerts if a["severity"] == "red"),
        "yellow_count": sum(1 for a in alerts if a["severity"] == "yellow"),
        "alerts": alerts,
    }


def get_alert_stats(role):

    feed = get_alert_feed(role)
    by_type = {}
    for a in feed["alerts"]:
        by_type[a["alert_type"]] = by_type.get(a["alert_type"], 0) + 1

    return {
        "total": feed["count"],
        "red": feed["red_count"],
        "yellow": feed["yellow_count"],
        "by_type": by_type,
    }


# Alert types with no existing dedicated action get routed here -- creates a
# real, deduped OperationsTask, the same acknowledgment-becomes-a-ticket
# mechanism as sync_derived_tasks(), just triggered per-alert instead of in
# bulk.
_ACKNOWLEDGE_TASK_TYPE = {
    "ownership_mismatch": ("confirm_lot_audit", "Lot Manager", "high"),
    "stalled_deal": ("manager_review", "Accounting", "high"),
}


def acknowledge_alert(alert_type, source_id, actor, notes=""):

    mapping = _ACKNOWLEDGE_TASK_TYPE.get(alert_type)
    if not mapping:
        return {"error": f"'{alert_type}' has a dedicated action -- use it directly rather than acknowledging."}

    task_type, owner_bucket, priority = mapping

    if source_id in _existing_source_ids(task_type):
        return {"error": "A task for this alert already exists -- see the Tasks queue."}

    return create_task(
        task_type=task_type,
        detail=notes or f"Acknowledged from Alerts nervous system ({alert_type})",
        created_by=actor,
        priority=priority,
        owner_bucket=owner_bucket,
        linked_entity_id=source_id,
        source_entity_id=source_id,
    )
