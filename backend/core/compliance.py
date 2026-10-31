"""
Compliance engine (2026-07-13, session 38) -- Sam: "there needs to be a complete
compliance level baked into every part of this, and it needs to run through every
sale, marketing push, etc... If it fails a compliance review it needs to be flagged,
stopped, and not allowed to go through until the corrections are made... scan
records/deals/etc at least twice a day and flag compliance issues and notify
managers/admin."

Three real, wired mechanisms, not a cosmetic "compliance score" label:

1. evaluate() / enforce_gate() -- called from *_api.py BEFORE a mutating action
   (funding a deal, activating a campaign, approving an asset, publishing a website,
   creating a data connection) is allowed to proceed. Every violation blocks -- there is
   no severity threshold below which a failure is silently allowed through, matching
   Sam's explicit "not allowed to go through until the corrections are made."

2. A ComplianceAlert is an ordinary graph entity (same no-separate-store rule as every
   other module here), created on every blocked action, and DMs every ADMIN/OPERATIONS-
   credentialed employee plus every credentialed manager/executive-tier employee
   (real recipients derived from core.auth's credential store + core.bot_tasks'
   real Title-based tier inference, not a fabricated distribution list).

3. run_full_scan() -- the twice-daily sweep (see core/compliance_scheduler.py) that
   re-checks every live Deal/Campaign/Asset/Website/Connection already on the graph,
   catching drift (an entity that was compliant when first gated but no longer is)
   rather than only checking at the moment of the original action.

See core/compliance_rules.py for the actual rule definitions and its explicit "starting
framework, not exhaustive, not legal advice" scoping note -- repeated here since every
alert this module creates carries that same notice.

Real, major data-loss bug found and fixed (2026-07-18, Marketing Growth Platform data-
gap-fill follow-up) -- this entire module had ZERO save_graph() calls anywhere in it
since it shipped (session 38). Every ComplianceAlert ever created (via enforce_gate()
blocking a deal fund/campaign activate/asset approve/website publish/connection create,
or via run_full_scan()'s twice-daily sweep), every resolve, and every override had been
silently discarded on every server restart -- one of the earliest and most heavily-
relied-upon modules in this whole codebase had never actually persisted a single
compliance decision. Found while investigating an unrelated Events-dash persistence bug
and checking whether the same bug class (see core/lead_conversion.py's own docstring)
extended further than expected -- it did. Fixed by adding save_graph(GRAPH_PATH) to
create_alert() (covers both enforce_gate() and run_full_scan(), since both funnel every
new alert through this one function), resolve_alert(), and override_alert(). evaluate()
and run_full_scan() itself are deliberately left unchanged -- run_full_scan() only
mutates the graph via create_alert(), so fixing that one function already covers the
sweep without adding a wasteful extra save call.
"""

from datetime import datetime, timezone

from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.entity_types import COMPLIANCE_ALERT
from core.compliance_rules import rules_for_action, NOT_LEGAL_ADVICE_NOTICE
from core.bot_tasks import infer_tier, get_employee, TIER_MANAGER, TIER_EXECUTIVE
from core.permissions import ADMIN, OPERATIONS
from core.messaging import send_direct_message
from core.audit import audit_log
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH, AUDIT_PATH
from core.audit_storage import save_audit_log


# Virtual sender, same pattern as the (now-removed) bot DM sender used to be -- a
# compliance alert is a genuine one-off, urgent, actionable notification, unlike the
# recurring per-tick bot task suggestions Sam asked to take OUT of direct messages
# (session 37's fix) for being redundant with a button. There's no equivalent button
# for "you're about to fund a non-compliant deal" -- a DM is the right channel here.
COMPLIANCE_SENDER_ID = "COMPLIANCE"

ACTIONS = [
    "deal_fund",
    "deal_decline",
    "campaign_activate",
    "connection_create",
    "asset_approve",
    "website_publish",
]


def _now():
    return datetime.now(timezone.utc).isoformat()


def evaluate(action, entity):
    """Runs every rule registered for `action` against `entity`. Returns a full result
    dict whether or not anything failed -- callers that just want a read-only compliance
    report (e.g. a "check this before I submit" preview) can call this directly without
    triggering an alert/notification, which enforce_gate() below does on top of this."""

    rules = rules_for_action(action)
    violations = []

    for rule in rules:

        description = rule["check"](entity)

        if description:

            violations.append({
                "rule_id": rule["id"],
                "law": rule["law"],
                "citation": rule["citation"],
                "category": rule["category"],
                "severity": rule["severity"],
                "description": description,
            })

    return {
        "action": action,
        "entity_type": entity.entity_type,
        "entity_id": entity.id,
        "passed": len(violations) == 0,
        "violations": violations,
        "checked_rule_ids": [r["id"] for r in rules],
        "checked_at": _now(),
        "notice": NOT_LEGAL_ADVICE_NOTICE,
    }


def _notify_managers_and_admin(alert):
    """Sam: "notify managers/admin." Real recipients: every credentialed ADMIN/
    OPERATIONS employee, plus every credentialed employee whose Employee.Title infers
    to manager/executive tier (core/bot_tasks.infer_tier -- the same real, schema-free
    tier inference the agentic bot layer already uses). Not a fabricated distribution
    list -- if nobody is credentialed as ADMIN/OPERATIONS/manager/executive, nobody
    gets notified, and that's surfaced honestly (empty notified list) rather than
    inventing a recipient."""

    from core.auth import credential_store

    notified = []
    violations = alert.attributes.get("violations", [])
    first = violations[0]["description"] if violations else "a compliance rule"
    extra = f" (+{len(violations) - 1} more)" if len(violations) > 1 else ""

    content = (
        f"Compliance alert on {alert.attributes['entity_type']} "
        f"{alert.attributes['entity_id']}: {first}{extra}"
    )

    for record in credential_store.list_records():

        employee_id = record["employee_id"]
        role = record["role"]

        should_notify = role in (ADMIN, OPERATIONS)

        if not should_notify:

            employee = get_employee(employee_id)

            if employee:
                should_notify = infer_tier(employee.attributes.get("Title")) in (TIER_MANAGER, TIER_EXECUTIVE)

        if should_notify and employee_id not in notified:

            notified.append(employee_id)
            send_direct_message(COMPLIANCE_SENDER_ID, employee_id, content)

    return notified


def create_alert(action, entity, violations):

    alert_id = id_generator.generate("CMPL")

    alert = Entity(
        id=alert_id,
        entity_type=COMPLIANCE_ALERT,
        attributes={
            "action": action,
            "entity_type": entity.entity_type,
            "entity_id": entity.id,
            "violations": violations,
            "status": "open",
            "created_at": _now(),
            "updated_at": _now(),
            "resolved_by": None,
            "resolved_at": None,
            "resolution_notes": None,
            "notified_employee_ids": [],
        },
    )

    ledger.add_entity(alert)

    alert.attributes["notified_employee_ids"] = _notify_managers_and_admin(alert)

    audit_log.record(
        event_type="compliance_alert_created",
        summary=f"Compliance alert {alert_id} on {entity.entity_type} {entity.id}: {len(violations)} violation(s)",
        entity_id=entity.id,
        actor="COMPLIANCE",
        details={"rule_ids": [v["rule_id"] for v in violations], "action": action},
    )

    save_graph(GRAPH_PATH)
    save_audit_log(AUDIT_PATH)

    return alert


def enforce_gate(action, entity):
    """The actual blocking mechanism. Called from *_api.py immediately before a
    mutating action proceeds -- fund_deal_api(), activate_campaign_api(),
    approve_asset_api(), approve_website_api(), create_connection_api(). Returns
    {"blocked": False} to let the caller continue normally, or {"blocked": True,
    "alert_id", "violations", "notice"} -- the caller returns this straight back as
    the API error response rather than proceeding, matching Sam's "flagged, stopped,
    and not allowed to go through until the corrections are made." Every violation
    blocks; there is no severity threshold that lets a failure through silently."""

    result = evaluate(action, entity)

    if result["passed"]:
        return {"blocked": False}

    alert = create_alert(action, entity, result["violations"])

    return {
        "blocked": True,
        "alert_id": alert.id,
        "violations": result["violations"],
        "notice": NOT_LEGAL_ADVICE_NOTICE,
    }


def get_alert(alert_id):

    entity = ledger.get_entity(alert_id)

    if entity and entity.entity_type == COMPLIANCE_ALERT:
        return entity

    return None


def list_alerts(status=None):

    alerts = [e for e in ledger.get_all().values() if e.entity_type == COMPLIANCE_ALERT]

    if status:
        alerts = [a for a in alerts if a.attributes.get("status") == status]

    alerts.sort(key=lambda a: (a.attributes.get("created_at", ""), a.id), reverse=True)

    return alerts


def resolve_alert(alert_id, resolved_by, notes=None):
    """Marks an alert resolved -- for use once the underlying entity has actually been
    corrected (a disclaimer added, missing customer fields filled in, etc.) and a
    manager/admin confirms the fix, distinct from override_alert() below which bypasses
    without fixing anything."""

    alert = get_alert(alert_id)

    if not alert:
        return {"error": "Compliance alert not found"}

    if alert.attributes.get("status") != "open":
        return {"error": f"Alert is already '{alert.attributes.get('status')}'"}

    alert.attributes["status"] = "resolved"
    alert.attributes["resolved_by"] = resolved_by
    alert.attributes["resolution_notes"] = notes
    alert.attributes["resolved_at"] = _now()
    alert.attributes["updated_at"] = _now()

    audit_log.record(
        event_type="compliance_alert_resolved",
        summary=f"Compliance alert {alert_id} resolved by {resolved_by}",
        entity_id=alert.attributes["entity_id"],
        actor=resolved_by,
        details={"notes": notes},
    )

    save_graph(GRAPH_PATH)
    save_audit_log(AUDIT_PATH)

    return alert


def override_alert(alert_id, overridden_by, notes):
    """ADMIN-only escape hatch (the role check lives in core/compliance_api.py, not
    here) -- lets an authorized admin consciously bypass a block with a documented,
    audited reason, distinct from "resolved" (which means the underlying issue was
    actually fixed). Requires real notes -- a silent, unexplained override isn't
    permitted; there is always an audit trail of who bypassed what and why."""

    alert = get_alert(alert_id)

    if not alert:
        return {"error": "Compliance alert not found"}

    if alert.attributes.get("status") != "open":
        return {"error": f"Alert is already '{alert.attributes.get('status')}'"}

    if not (notes or "").strip():
        return {"error": "An override requires a documented reason"}

    alert.attributes["status"] = "overridden"
    alert.attributes["resolved_by"] = overridden_by
    alert.attributes["resolution_notes"] = notes
    alert.attributes["resolved_at"] = _now()
    alert.attributes["updated_at"] = _now()

    audit_log.record(
        event_type="compliance_alert_overridden",
        summary=f"Compliance alert {alert_id} overridden by {overridden_by}",
        entity_id=alert.attributes["entity_id"],
        actor=overridden_by,
        details={"notes": notes},
    )

    save_graph(GRAPH_PATH)
    save_audit_log(AUDIT_PATH)

    return alert


def run_full_scan():
    """The twice-daily sweep (Sam: "scan records/deals/etc at least twice a day and
    flag compliance issues and notify managers/admin"). Re-runs the real rule checks
    against every live Deal/Campaign/Asset/Website/Connection already on the graph, not
    just at the moment each was first gated -- catches an entity that drifts out of
    compliance afterward (e.g. a customer record loses a required field via a later
    edit). Skips any (entity_id, rule_id) combination that already has an OPEN alert so
    re-scanning doesn't spam duplicate alerts for a known, already-flagged issue."""

    from core.deals import list_deals
    from core.campaigns import list_campaigns
    from core.assets import list_assets
    from core.websites import list_websites
    from core.data_connections import list_connections

    scan_targets = []

    for deal in list_deals():

        if deal.attributes.get("status") == "funded":
            scan_targets.append(("deal_fund", deal))

        if deal.attributes.get("financing_status") == "declined":
            scan_targets.append(("deal_decline", deal))

    for campaign in list_campaigns(status="active"):
        scan_targets.append(("campaign_activate", campaign))

    for asset in list_assets(status="approved"):
        scan_targets.append(("asset_approve", asset))

    for website in list_websites(status="published"):
        scan_targets.append(("website_publish", website))

    for connection in list_connections():
        scan_targets.append(("connection_create", connection))

    existing_open = {
        (alert.attributes["entity_id"], violation["rule_id"])
        for alert in list_alerts(status="open")
        for violation in alert.attributes.get("violations", [])
    }

    new_alerts = []

    for action, entity in scan_targets:

        result = evaluate(action, entity)

        if result["passed"]:
            continue

        fresh_violations = [
            v for v in result["violations"]
            if (entity.id, v["rule_id"]) not in existing_open
        ]

        if not fresh_violations:
            continue

        new_alerts.append(create_alert(action, entity, fresh_violations))

    return {
        "scanned_at": _now(),
        "entities_scanned": len(scan_targets),
        "new_alerts": len(new_alerts),
        "alert_ids": [a.id for a in new_alerts],
    }
