"""
Leads Configuration -- named, configurable lead-distribution rules (Bumper parity,
2026-07-25). Bumper's "Distribution Configurations" screen lets a dealer define named
rules ("Website leads -> Internet team, round-robin"; "Autotrader -> Jane"; "TX walk-ins
-> Sales, least-busy") with optional ADF/HTTP endpoints. NXTDeal's assignment was
hard-coded (create_lead assigns to whoever logged it; the dormant least-busy path only
picks reps who already carry a lead). This module makes distribution a first-class,
admin-configurable rule set.

Design mirrors core/workflow_automation.py: rules are ordinary graph entities (one graph,
no side store), evaluated ON-DEMAND (no background scheduler) via route_lead(). First
active rule (by priority, then creation order) whose match conditions fit a lead wins;
its strategy picks the rep; we then write BOTH the ASSIGNED_TO relationship AND the
lead's AssignedSalesperson attribute (they can drift -- relationship is source of truth,
attribute is the mirror; core/lead_assignment_api.py documents this discipline).

Strategies:
  - round_robin      : rotate across the target department's roster (per-rule pointer)
  - least_busy       : fewest active (non-SOLD/LOST) leads in the target department roster
  - specific_employee: always a named rep

ADF/HTTP endpoints are stored as config and reported on route, but actual outbound
dispatch is left to the Track B delivery-provider seam (core/integrations_registry.py) --
there is no live ADF/HTTP adapter registered, so route_lead reports the dispatch as
simulated rather than pretending a real POST happened.
"""

from datetime import datetime, timezone

from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.entity_types import LEAD_ROUTING_RULE, LEAD, EMPLOYEE
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH
from core.lead_assignment import assign_lead


STRATEGIES = ("round_robin", "least_busy", "specific_employee")


def _now():
    return datetime.now(timezone.utc).isoformat()


def _dept_roster(department):
    """Employee ids in a department, sorted (deterministic rotation / tie-breaking).
    Normalizes Department with strip().lower() to match the dominant convention
    (core/up_system.py:_sales_employee_ids)."""
    dept = (department or "").strip().lower()
    if not dept:
        return []
    return sorted(
        e.id for e in ledger.get_all().values()
        if e.entity_type == EMPLOYEE and (e.attributes.get("Department") or "").strip().lower() == dept
    )


def _active_workload(employee_id):
    """Count this employee's leads whose pipeline isn't terminal (SOLD/LOST). Roster-based,
    unlike core/lead_routing.auto_assign_lead whose pool is only already-assigned reps."""
    from core.lead_assignment import get_employee_leads
    terminal = {"SOLD", "LOST"}
    n = 0
    for lead_id in get_employee_leads(employee_id):
        lead = ledger.get_entity(lead_id)
        if not lead:
            continue
        state = (lead.attributes.get("PipelineState") or "").strip().upper()
        if state not in terminal:
            n += 1
    return n


def get_routing_rule(rule_id):
    e = ledger.get_entity(rule_id)
    return e if e and e.entity_type == LEAD_ROUTING_RULE else None


def _all_rules():
    return [e for e in ledger.get_all().values() if e.entity_type == LEAD_ROUTING_RULE and not e.attributes.get("deleted")]


def list_routing_rules(active_only=False):
    rules = _all_rules()
    if active_only:
        rules = [r for r in rules if r.attributes.get("is_active")]
    # priority ascending (lower fires first), then creation order for stable ties
    return sorted(rules, key=lambda r: (r.attributes.get("priority", 100), r.attributes.get("created_at", "")))


def _validate_rule(strategy, target_department, target_employee_id, match_sources, priority):
    if strategy not in STRATEGIES:
        return f"strategy must be one of {STRATEGIES}"
    if strategy == "specific_employee":
        if not target_employee_id:
            return "target_employee_id is required for the specific_employee strategy"
        emp = ledger.get_entity(target_employee_id)
        if not emp or emp.entity_type != EMPLOYEE:
            return f"target_employee_id '{target_employee_id}' is not an Employee"
    else:
        if not (target_department or "").strip():
            return f"target_department is required for the {strategy} strategy"
    if match_sources is not None and not isinstance(match_sources, list):
        return "match_sources must be a list"
    if priority is not None:
        try:
            int(priority)
        except (TypeError, ValueError):
            return "priority must be an integer"
    return None


def create_routing_rule(
    name,
    created_by,
    strategy,
    target_department="",
    target_employee_id=None,
    match_sources=None,
    match_states=None,
    match_cities=None,
    endpoint=None,
    description="",
    priority=100,
):
    err = _validate_rule(strategy, target_department, target_employee_id, match_sources, priority)
    if err:
        return {"error": err}

    name = (name or "").strip()
    if not name:
        return {"error": "name is required"}

    rule = Entity(
        id=id_generator.generate("LRULE"),
        entity_type=LEAD_ROUTING_RULE,
        attributes={
            "name": name,
            "description": description or "",
            "strategy": strategy,
            "target_department": (target_department or "").strip(),
            "target_employee_id": target_employee_id,
            # match conditions (empty list/None => "matches any" for that dimension)
            "match_sources": list(match_sources) if match_sources else [],
            "match_states": list(match_states) if match_states else [],
            "match_cities": list(match_cities) if match_cities else [],
            "endpoint": dict(endpoint) if endpoint else None,
            "priority": int(priority) if priority is not None else 100,
            "is_active": False,     # created inactive; must be turned on deliberately
            "next_index": 0,        # round-robin pointer
            "times_matched": 0,
            "last_matched_at": None,
            "created_by": created_by,
            "created_at": _now(),
            "updated_at": _now(),
        },
    )
    ledger.add_entity(rule)
    save_graph(GRAPH_PATH)
    return rule


def update_routing_rule(rule_id, patch):
    rule = get_routing_rule(rule_id)
    if not rule:
        return {"error": "Routing rule not found"}
    allowed = {
        "name", "description", "strategy", "target_department", "target_employee_id",
        "match_sources", "match_states", "match_cities", "endpoint", "priority",
    }
    merged = dict(rule.attributes)
    for k, v in (patch or {}).items():
        if k in allowed:
            merged[k] = v
    err = _validate_rule(
        merged.get("strategy"), merged.get("target_department"),
        merged.get("target_employee_id"), merged.get("match_sources"), merged.get("priority"),
    )
    if err:
        return {"error": err}
    for k in allowed:
        if k in (patch or {}):
            rule.attributes[k] = patch[k]
    if "priority" in (patch or {}) and patch["priority"] is not None:
        rule.attributes["priority"] = int(patch["priority"])
    rule.attributes["updated_at"] = _now()
    save_graph(GRAPH_PATH)
    return rule


def set_routing_rule_active(rule_id, active):
    rule = get_routing_rule(rule_id)
    if not rule:
        return {"error": "Routing rule not found"}
    rule.attributes["is_active"] = bool(active)
    rule.attributes["updated_at"] = _now()
    save_graph(GRAPH_PATH)
    return rule


def delete_routing_rule(rule_id):
    rule = get_routing_rule(rule_id)
    if not rule:
        return {"error": "Routing rule not found"}
    rule.attributes["is_active"] = False
    rule.attributes["deleted"] = True
    rule.attributes["updated_at"] = _now()
    save_graph(GRAPH_PATH)
    return {"ok": True, "rule_id": rule_id}


def _matches(rule, lead_attrs):
    a = rule.attributes
    sources = a.get("match_sources") or []
    if sources and (lead_attrs.get("Source") or "") not in sources:
        return False
    states = a.get("match_states") or []
    if states:
        want = {(s or "").strip().upper() for s in states}
        if (lead_attrs.get("State") or "").strip().upper() not in want:
            return False
    cities = a.get("match_cities") or []
    if cities:
        want = {(c or "").strip().lower() for c in cities}
        if (lead_attrs.get("City") or "").strip().lower() not in want:
            return False
    return True


def _pick_employee(rule, advance=True):
    """Return (employee_id, error). advance=False leaves round-robin state untouched (for
    non-destructive preview)."""
    strategy = rule.attributes.get("strategy")
    if strategy == "specific_employee":
        return rule.attributes.get("target_employee_id"), None

    roster = _dept_roster(rule.attributes.get("target_department"))
    if not roster:
        return None, f"no employees in department '{rule.attributes.get('target_department')}'"

    if strategy == "least_busy":
        workloads = {e: _active_workload(e) for e in roster}
        return min(workloads, key=workloads.get), None  # sorted roster => deterministic ties

    # round_robin
    idx = rule.attributes.get("next_index", 0) % len(roster)
    emp = roster[idx]
    if advance:
        rule.attributes["next_index"] = (idx + 1) % len(roster)
    return emp, None


def _endpoint_dispatch(rule):
    """ADF/HTTP dispatch is a Track B (delivery-provider) concern. There's no live adapter,
    so we report the intended dispatch as simulated rather than faking a real POST."""
    endpoint = rule.attributes.get("endpoint")
    if not endpoint:
        return None
    return {
        "delivered": False,
        "simulated": True,
        "reason": "no live ADF/HTTP adapter registered (Track B)",
        "endpoint": endpoint,
    }


def preview_route(lead_attrs):
    """Non-destructive: which active rule would match these lead attributes and who it
    would pick -- WITHOUT assigning or advancing any round-robin pointer. Powers the config
    screen's 'test this configuration' box."""
    for rule in list_routing_rules(active_only=True):
        if _matches(rule, lead_attrs or {}):
            emp, err = _pick_employee(rule, advance=False)
            return {
                "matched": True,
                "rule_id": rule.id,
                "rule_name": rule.attributes.get("name"),
                "strategy": rule.attributes.get("strategy"),
                "would_assign_to": emp,
                "error": err,
                "endpoint_dispatch": _endpoint_dispatch(rule),
            }
    return {"matched": False}


def route_lead(lead_id):
    """Evaluate active rules against a real lead and, on the first match, assign it. Writes
    both the ASSIGNED_TO relationship and the AssignedSalesperson attribute mirror."""
    lead = ledger.get_entity(lead_id)
    if not lead or lead.entity_type != LEAD:
        return {"error": "Lead not found"}

    for rule in list_routing_rules(active_only=True):
        if not _matches(rule, lead.attributes):
            continue
        emp, err = _pick_employee(rule, advance=True)
        if err or not emp:
            # A matching rule that can't resolve a rep (empty roster) is reported, not
            # silently skipped -- otherwise a misconfigured rule looks like "no match".
            return {"routed": False, "matched_rule_id": rule.id, "reason": err or "no employee resolved"}

        assign_lead(lead_id, emp)                      # ASSIGNED_TO relationship + save
        lead.attributes["AssignedSalesperson"] = emp   # mirror attribute
        rule.attributes["times_matched"] = rule.attributes.get("times_matched", 0) + 1
        rule.attributes["last_matched_at"] = _now()
        save_graph(GRAPH_PATH)
        return {
            "routed": True,
            "lead_id": lead_id,
            "assigned_to": emp,
            "rule_id": rule.id,
            "rule_name": rule.attributes.get("name"),
            "strategy": rule.attributes.get("strategy"),
            "endpoint_dispatch": _endpoint_dispatch(rule),
        }

    return {"routed": False, "reason": "no active rule matched"}
