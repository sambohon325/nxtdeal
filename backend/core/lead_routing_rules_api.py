"""
Thin ACL layer for core/lead_routing_rules.py (Bumper parity: Leads Configuration).
Managing distribution rules (create/update/activate/delete) is ADMIN/OPERATIONS -- it
decides where every incoming lead lands, an administration-class action. Routing an
actual lead and previewing what a rule would do are open to any authenticated role (the
intake system and any rep working leads need them).
"""

from core.lead_routing_rules import (
    create_routing_rule,
    get_routing_rule,
    list_routing_rules,
    update_routing_rule,
    set_routing_rule_active,
    delete_routing_rule,
    route_lead,
    preview_route,
    STRATEGIES,
)
from core.lead_intake import VALID_SOURCES
from core.permissions import ADMIN, OPERATIONS
from core.audit import audit_log
from core.audit_storage import save_audit_log
from core.storage_paths import AUDIT_PATH

_ADMIN_ROLES = (ADMIN, OPERATIONS)
_ADMIN_ONLY_ERROR = {"error": "Admin/Operations role required to manage lead routing."}


def _serialize(entity):
    if isinstance(entity, dict):
        return entity
    return {"id": entity.id, **entity.attributes}


def get_routing_config_api(role):
    """The catalog the config screen needs: strategies + the lead sources rules match on."""
    if role not in _ADMIN_ROLES:
        return _ADMIN_ONLY_ERROR
    return {"strategies": list(STRATEGIES), "sources": list(VALID_SOURCES)}


def list_routing_rules_api(role, active_only=False):
    if role not in _ADMIN_ROLES:
        return _ADMIN_ONLY_ERROR
    return {"rules": [_serialize(r) for r in list_routing_rules(active_only=active_only)]}


def get_routing_rule_api(role, rule_id):
    if role not in _ADMIN_ROLES:
        return _ADMIN_ONLY_ERROR
    rule = get_routing_rule(rule_id)
    if not rule:
        return {"error": "Routing rule not found"}
    return _serialize(rule)


def create_routing_rule_api(role, employee_id, name, strategy, target_department="", target_employee_id=None,
                            match_sources=None, match_states=None, match_cities=None, endpoint=None,
                            description="", priority=100):
    if role not in _ADMIN_ROLES:
        return _ADMIN_ONLY_ERROR
    result = create_routing_rule(
        name, employee_id, strategy, target_department=target_department,
        target_employee_id=target_employee_id, match_sources=match_sources,
        match_states=match_states, match_cities=match_cities, endpoint=endpoint,
        description=description, priority=priority,
    )
    if isinstance(result, dict) and result.get("error"):
        return result
    audit_log.record(
        event_type="lead_routing_rule_created",
        summary=f"Lead routing rule '{name}' ({strategy}) created by {employee_id}",
        entity_id=result.id, actor=employee_id, details={"strategy": strategy},
    )
    save_audit_log(AUDIT_PATH)
    return _serialize(result)


def update_routing_rule_api(role, employee_id, rule_id, patch):
    if role not in _ADMIN_ROLES:
        return _ADMIN_ONLY_ERROR
    result = update_routing_rule(rule_id, patch or {})
    if isinstance(result, dict) and result.get("error"):
        return result
    return _serialize(result)


def set_routing_rule_active_api(role, employee_id, rule_id, active):
    if role not in _ADMIN_ROLES:
        return _ADMIN_ONLY_ERROR
    result = set_routing_rule_active(rule_id, active)
    if isinstance(result, dict) and result.get("error"):
        return result
    audit_log.record(
        event_type="lead_routing_rule_toggled",
        summary=f"Lead routing rule {rule_id} set active={bool(active)} by {employee_id}",
        entity_id=rule_id, actor=employee_id, details={"active": bool(active)},
    )
    save_audit_log(AUDIT_PATH)
    return _serialize(result)


def delete_routing_rule_api(role, employee_id, rule_id):
    if role not in _ADMIN_ROLES:
        return _ADMIN_ONLY_ERROR
    return delete_routing_rule(rule_id)


def preview_route_api(role, lead_attrs):
    """Non-destructive 'test this configuration' -- any authed role (no ADMIN gate; it
    writes nothing)."""
    return preview_route(lead_attrs or {})


def route_lead_api(role, employee_id, lead_id):
    """Route a real lead through the active rules. Any authed role (the intake system and
    reps both trigger routing); the write it performs is an assignment, not config."""
    result = route_lead(lead_id)
    if isinstance(result, dict) and result.get("routed"):
        audit_log.record(
            event_type="lead_routed",
            summary=f"Lead {lead_id} routed to {result['assigned_to']} by rule {result['rule_id']}",
            entity_id=lead_id, actor=employee_id,
            details={"assigned_to": result["assigned_to"], "rule_id": result["rule_id"]},
        )
        save_audit_log(AUDIT_PATH)
    return result
