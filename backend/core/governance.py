"""
core/governance.py -- Administration's "Compliance & Governance" item
(Administration Control Center rebuild, continuing 2026-07-18). admin.pdf's
own 15-item proposal names "Compliance & Governance" as its own item; this
codebase already had a thin "Governance" Top Menu item
(core/administration_menu.py's governance()) surfacing a real cross-
department CONTENT approval queue (campaigns/assets/websites/financing,
via `_approval_queue()`), a real escalation dashboard, and a flat 50-event
audit-trail dump. That item's own docstring already stated the honest gap:
"Policy Management, Workflow Templates, and Department Standards have no
backing data model." This module does NOT invent those -- there is still no
policy-document/charter entity anywhere in this codebase, and inventing one
here would be exactly the kind of fabrication this whole rebuild has
avoided. What it DOES add is real: this dealership now has TWO other real
governance-shaped engines that were never tied into this screen --
core/compliance.py's cited-federal-rules alert engine (session 38) and
core/permissions_registry.py's real, tier-gated cross-department
ApprovalRequest hierarchy (Roles & Permissions, this same session) -- plus
a genuinely new governance-scoped slice of the audit log
(core/audit_center.py's real EVENT_CATEGORIES already has "Permissions"/
"Approvals"/"Compliance" buckets sitting unused by any Administration
screen). This module composes those three into one real governance
workspace rather than building a fourth, parallel engine.

No role gating happens inside this module (matching core/audit_center.py's
own established convention) -- core/governance_api.py and
core/administration_menu.py's governance() are both ADMIN/OPERATIONS-gated
already, and every function here calls the ROLE-FREE core function on the
other module directly (core.compliance.list_alerts, not
core.compliance_api.list_alerts_api; core.permissions_registry.
list_approval_requests, not the _api wrapper) -- the same "core module
reuses another core module directly, not its own _api layer" convention
core/event_campaign_generator.py already established.
"""

from datetime import datetime

from core.compliance import list_alerts
from core.compliance_rules import all_rules, NOT_LEGAL_ADVICE_NOTICE
from core.permissions_registry import list_approval_requests, list_approval_chains
from core.audit_api import list_audit_events
from core.audit_center import EVENT_CATEGORIES, DEFAULT_CATEGORY, _serialize as _serialize_event


GOVERNANCE_CATEGORIES = ("Permissions", "Approvals", "Compliance")


def _hours_between(iso_a, iso_b):
    """Real elapsed hours between two ISO timestamps -- an unparseable pair
    (e.g. a legacy record missing a field) degrades to None rather than a
    crash or a fabricated duration."""

    try:
        a = datetime.fromisoformat(iso_a)
        b = datetime.fromisoformat(iso_b)
        return abs((b - a).total_seconds()) / 3600.0
    except (TypeError, ValueError):
        return None


def get_compliance_governance_summary():
    """Real open/resolved/overridden compliance-alert breakdown, a real
    resolution rate, a real average resolution time (hours between
    created_at and resolved_at across every alert actually closed), and a
    real per-law violation breakdown -- each alert's own stored
    `violations` list already carries the rule_id that fired, cross-
    referenced against compliance_rules.all_rules() for a human-readable
    law name rather than a second rules catalog."""

    alerts = list_alerts()
    rules_by_id = {r["id"]: r for r in all_rules()}

    by_status = {}
    resolution_hours = []
    by_law = {}

    for a in alerts:
        attrs = a.attributes
        status = attrs.get("status", "open")
        by_status[status] = by_status.get(status, 0) + 1

        if status in ("resolved", "overridden") and attrs.get("created_at") and attrs.get("resolved_at"):
            hrs = _hours_between(attrs["created_at"], attrs["resolved_at"])
            if hrs is not None:
                resolution_hours.append(hrs)

        for v in (attrs.get("violations") or []):
            rule_id = v.get("rule_id")
            rule = rules_by_id.get(rule_id)
            law = rule["law"] if rule else (rule_id or "Unknown rule")
            by_law[law] = by_law.get(law, 0) + 1

    total = len(alerts)
    closed = by_status.get("resolved", 0) + by_status.get("overridden", 0)
    resolution_rate = round(closed / total, 3) if total else None
    avg_resolution_hours = round(sum(resolution_hours) / len(resolution_hours), 1) if resolution_hours else None

    return {
        "total_alerts": total,
        "by_status": by_status,
        "resolution_rate": resolution_rate,
        "avg_resolution_hours": avg_resolution_hours,
        "by_law": by_law,
        "notice": NOT_LEGAL_ADVICE_NOTICE,
    }


def get_approval_hierarchy_summary():
    """Real cross-department ApprovalRequest data -- every real request
    ever created via core/permissions_registry.py's approval chains
    (permission-change/role-change/policy-exception/expense), grouped by
    status and by chain, plus a real average turnaround time (hours from
    created_at to updated_at across every request that's actually left
    'pending')."""

    requests = list_approval_requests()

    by_status = {}
    by_chain = {}
    turnaround_hours = []

    for attrs in requests:
        status = attrs.get("status", "pending")
        by_status[status] = by_status.get(status, 0) + 1

        chain_key = attrs.get("chain_key", "unknown")
        by_chain[chain_key] = by_chain.get(chain_key, 0) + 1

        if status != "pending" and attrs.get("created_at") and attrs.get("updated_at"):
            hrs = _hours_between(attrs["created_at"], attrs["updated_at"])
            if hrs is not None:
                turnaround_hours.append(hrs)

    total = len(requests)
    decided = total - by_status.get("pending", 0)
    throughput_rate = round(decided / total, 3) if total else None
    avg_turnaround_hours = round(sum(turnaround_hours) / len(turnaround_hours), 1) if turnaround_hours else None

    return {
        "total_requests": total,
        "by_status": by_status,
        "by_chain": by_chain,
        "chains": list_approval_chains(),
        "throughput_rate": throughput_rate,
        "avg_turnaround_hours": avg_turnaround_hours,
        "pending_requests": [r for r in requests if r.get("status") == "pending"][:50],
    }


def get_governance_action_log(category=None, limit=100):
    """A genuinely governance-scoped slice of the platform-wide audit log --
    every real event whose category (core/audit_center.py's own
    EVENT_CATEGORIES map) is Permissions/Approvals/Compliance, i.e. every
    permission override granted/revoked, every approval-chain step taken,
    and every compliance alert created/resolved/overridden -- reusing that
    module's own category catalog rather than a second one. `category`
    narrows to one of the three when given; otherwise all three are
    merged and re-sorted most-recent-first."""

    categories = (category,) if category else GOVERNANCE_CATEGORIES

    events = list_audit_events()
    matched = [
        e for e in events
        if EVENT_CATEGORIES.get(e.get("event_type"), DEFAULT_CATEGORY) in categories
    ]

    matched.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
    total = len(matched)
    matched = [_serialize_event(e) for e in matched[:limit]]

    return {"total_matches": total, "returned": len(matched), "events": matched}


def get_governance_health(compliance_summary=None, approval_summary=None):
    """A real, transparent blend of two already-real rates -- compliance
    resolution_rate and approval throughput_rate -- into one governance
    health percentage, explicitly labeled as a blend of those two real
    inputs rather than a fabricated single "governance score." Either
    input missing (e.g. zero alerts or zero requests ever created) drops
    out of the average honestly rather than being treated as 0% or 100%."""

    compliance_summary = compliance_summary or get_compliance_governance_summary()
    approval_summary = approval_summary or get_approval_hierarchy_summary()

    rates = [
        r for r in (compliance_summary.get("resolution_rate"), approval_summary.get("throughput_rate"))
        if r is not None
    ]
    blended = round(sum(rates) / len(rates), 3) if rates else None

    return {
        "blended_health_score": blended,
        "basis": "real_blend_of_compliance_resolution_rate_and_approval_throughput_rate",
        "compliance_resolution_rate": compliance_summary.get("resolution_rate"),
        "approval_throughput_rate": approval_summary.get("throughput_rate"),
        "open_compliance_alerts": compliance_summary.get("by_status", {}).get("open", 0),
        "pending_approval_requests": approval_summary.get("by_status", {}).get("pending", 0),
    }


def get_governance_overview():
    """The composed Compliance & Governance workspace -- compliance summary,
    approval hierarchy summary, a real governance action log (most recent
    30), and a real blended governance-health figure. Deliberately does NOT
    include the pre-existing content approval queue (campaigns/assets/
    websites/financing) or escalation dashboard -- core/administration_
    menu.py's governance() keeps composing those itself, unchanged, since
    they were already real and already working; this function is additive."""

    compliance_summary = get_compliance_governance_summary()
    approval_summary = get_approval_hierarchy_summary()
    health = get_governance_health(compliance_summary, approval_summary)
    action_log = get_governance_action_log(limit=30)

    return {
        "compliance_summary": compliance_summary,
        "approval_hierarchy": approval_summary,
        "governance_health": health,
        "governance_action_log": action_log,
        "not_yet_tracked": {
            "policy_management": "No policy-document/charter entity exists anywhere in this codebase.",
            "workflow_templates": "core/workflow_catalog.py's WORKFLOW_CATALOG is a fixed, code-defined catalog -- not a dealer-editable template-management feature.",
            "department_standards": "No department-standards entity exists yet.",
        },
    }
