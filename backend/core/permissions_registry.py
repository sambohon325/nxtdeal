"""
core/permissions_registry.py -- Administration's "Roles & Permissions" item
(Administration Control Center rebuild, first slice, 2026-07-18). Sam's own
framing: "Administration currently appears to monitor the system. It should run
the platform," and of the 14-item restructure he proposed, Roles & Permissions
was his own "one of the most important modules" -- Role-Based Security, Granular
Security (View/Edit/Approve/Delete/Export/Fund per area), Field-Level Security
("Can View Deal, Cannot See Credit Score"), and Approval Hierarchies
(Employee -> Manager -> Director -> Executive).

**The existing 6-role system (core/permissions.py -- ADMIN/OPERATIONS/SALES/
MARKETING/SERVICE/FINANCE) is NOT replaced.** It's baked into ~100+ existing
`core/*_api.py` modules' own hardcoded ACL checks across this entire codebase --
rewriting it wholesale would be an enormous, high-risk change for one slice. This
module is a genuinely ADDITIVE layer on top of it:

  1. PERMISSION_CATALOG -- a real, granular permission list grouped by area
     (Deals, F&I, Credit Applications, Compliance, Customers, Marketing, Finance/
     Loan Servicing, Inventory, Administration itself), each permission's role
     DEFAULT deliberately mirroring an already-real, already-enforced ACL set
     elsewhere in this codebase (deals_api.py's `_BOARD_VIEW_ROLES`/`_FI_ROLES`,
     fi_products_api.py, credit_app_api.py's `_CREDIT_APP_ROLES`,
     compliance_api.py's `COMPLIANCE_ROLES`, permissions.py's own `ENTITY_ACCESS`,
     etc.) -- not invented from nothing. **Honest scope note, matching this
     codebase's own established precedent for DASHBOARD_ACCESS's docstring**:
     this catalog covers the real, most load-bearing permission areas of the
     platform as a genuine starting point, not a claim to have modeled every
     single one of the ~100+ existing ACL checks in one pass.

  2. PermissionOverride -- a real, first-class, per-employee grant/revoke of one
     specific permission beyond that employee's role default, auditable and
     reversible (a new override for the same employee+key deactivates the prior
     one rather than deleting history).

  3. FIELD_SECURITY + filter_sensitive_fields() -- genuine field-level masking,
     wired into at least one real read path (core/customer_360.py's CreditScore,
     core/credit_app.py's ssn_last4) so this has real teeth, not just a config
     screen nobody's data ever passes through.

  4. Approval Hierarchies -- ApprovalRequest entities routed through a REAL
     3-tier system (staff/manager/executive), reusing core/bot_tasks.py's own
     already-real `infer_tier()` off Employee.Title (session 36) rather than
     fabricating a 4th "Director" tier this codebase has no Title-keyword data
     to honestly distinguish (a director-titled employee already collapses into
     the "manager" tier via `infer_tier()`'s own `_MANAGER_TITLE_PHRASES`).

Every mutation here also logs to core/audit.py's real, already-platform-wide
`audit_log` singleton -- the same audit trail logins/compliance
overrides/credential changes already write to, not a second parallel log.
"""

from datetime import datetime, timezone

from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.entity_types import PERMISSION_OVERRIDE, APPROVAL_REQUEST, EMPLOYEE
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH, AUDIT_PATH
from core.audit_storage import save_audit_log
from core.audit import audit_log

from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE, BDC
from core.bot_tasks import infer_tier, TIER_STAFF, TIER_MANAGER, TIER_EXECUTIVE


def _now():
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# 1. Granular permission catalog (additive on top of the 6 coarse roles)
# ---------------------------------------------------------------------------

PERMISSION_CATALOG = {
    "Deals": [
        {"key": "deals.view_board", "label": "View the whole Deal Desk board",
         "roles": [ADMIN, OPERATIONS, SALES, FINANCE]},
        {"key": "deals.desk", "label": "Desk a deal (scenarios, trade appraisal)",
         "roles": [ADMIN, OPERATIONS, SALES, FINANCE]},
        {"key": "deals.advance_financing", "label": "Submit/decide financing, generate contract",
         "roles": [ADMIN, OPERATIONS, FINANCE]},
        {"key": "deals.fund", "label": "Fund a deal",
         "roles": [ADMIN, OPERATIONS, FINANCE]},
    ],
    "F&I": [
        {"key": "fi.view_menu", "label": "View a deal's F&I product menu",
         "roles": [ADMIN, OPERATIONS, SALES, FINANCE]},
        {"key": "fi.present_products", "label": "Present/price/decide F&I products",
         "roles": [ADMIN, OPERATIONS, FINANCE]},
    ],
    "Credit Applications": [
        {"key": "credit_app.manage", "label": "Create, edit, decision credit applications",
         "roles": [ADMIN, OPERATIONS, SALES, FINANCE]},
    ],
    "Compliance": [
        {"key": "compliance.resolve_alert", "label": "Resolve a compliance alert",
         "roles": [ADMIN, OPERATIONS]},
        {"key": "compliance.override_alert", "label": "Override a compliance gate",
         "roles": [ADMIN]},
    ],
    "Customers": [
        {"key": "customers.view", "label": "View customer records",
         "roles": [ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE]},
        {"key": "customers.view_credit_score", "label": "View a customer's credit score",
         "roles": [ADMIN, FINANCE]},
        {"key": "customers.export", "label": "Export customer data",
         "roles": [ADMIN, OPERATIONS, MARKETING]},
    ],
    "Marketing": [
        {"key": "marketing.create_campaign", "label": "Draft a campaign",
         "roles": [ADMIN, OPERATIONS, SALES, MARKETING]},
        {"key": "marketing.activate_campaign", "label": "Activate/publish a campaign",
         "roles": [ADMIN, MARKETING]},
        {"key": "marketing.publish_website", "label": "Approve/publish a dealer website",
         "roles": [ADMIN, MARKETING]},
    ],
    "Finance / Loan Servicing": [
        {"key": "finance.view_loan_portfolio", "label": "View the loan portfolio",
         "roles": [ADMIN, OPERATIONS, FINANCE]},
        {"key": "finance.modify_loan_status", "label": "Change a loan's status",
         "roles": [ADMIN, OPERATIONS, FINANCE]},
    ],
    "Inventory": [
        {"key": "inventory.view_vehicles", "label": "View vehicle inventory",
         "roles": [ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE]},
        {"key": "inventory.adjust_pricing", "label": "Adjust vehicle pricing",
         "roles": [ADMIN, OPERATIONS]},
        {"key": "inventory.mutate_lifecycle", "label": "Advance a vehicle's recon/lifecycle stage",
         "roles": [ADMIN, OPERATIONS, SERVICE]},
    ],
    "Administration": [
        {"key": "admin.manage_users", "label": "Manage employee/user directory",
         "roles": [ADMIN, OPERATIONS]},
        {"key": "admin.manage_permissions", "label": "Grant/revoke a permission override",
         "roles": [ADMIN]},
        {"key": "admin.view_audit", "label": "View the platform audit log",
         "roles": [ADMIN]},
    ],
}

# Flattened key -> catalog entry index, built once at import time.
_PERMISSION_INDEX = {
    entry["key"]: {**entry, "category": category}
    for category, entries in PERMISSION_CATALOG.items()
    for entry in entries
}

ALL_ROLES = (ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE, BDC)


def list_permission_catalog():
    """The full catalog, category by category, for a Roles & Permissions matrix
    screen -- each entry already carries its own real role defaults."""

    return {
        "categories": [
            {"category": category, "permissions": entries}
            for category, entries in PERMISSION_CATALOG.items()
        ],
        "roles": list(ALL_ROLES),
    }


def _active_override(employee_id, permission_key):
    for e in ledger.get_all().values():
        if (
            e.entity_type == PERMISSION_OVERRIDE
            and e.attributes.get("employee_id") == employee_id
            and e.attributes.get("permission_key") == permission_key
            and e.attributes.get("active")
        ):
            return e
    return None


def has_permission(role, employee_id, permission_key):
    """The real check: an active per-employee override always wins; otherwise
    fall back to the permission's role default. Unknown permission keys
    conservatively deny (fail closed, not open) rather than silently allowing
    everything for a typo'd key."""

    if permission_key == "admin.view_audit":
        from core.administration_access import reserved_system_admin
        return role == ADMIN and reserved_system_admin(employee_id)
    entry = _PERMISSION_INDEX.get(permission_key)
    if not entry:
        return False

    override = _active_override(employee_id, permission_key)
    if override is not None:
        return bool(override.attributes.get("granted"))

    return role in entry["roles"]


def get_effective_permissions(role, employee_id):
    """Every catalog permission plus whether this specific employee currently
    has it (role default, unless overridden) -- the real per-employee view a
    Roles & Permissions screen needs."""

    out = []
    for key, entry in _PERMISSION_INDEX.items():
        override = _active_override(employee_id, key)
        out.append({
            "key": key,
            "label": entry["label"],
            "category": entry["category"],
            "role_default": has_permission(role, employee_id, key) if key == "admin.view_audit" else role in entry["roles"],
            "effective": has_permission(role, employee_id, key),
            "overridden": override is not None,
        })
    return out


def list_overrides_for_employee(employee_id):
    overrides = [
        e for e in ledger.get_all().values()
        if e.entity_type == PERMISSION_OVERRIDE and e.attributes.get("employee_id") == employee_id
    ]
    overrides.sort(key=lambda e: e.attributes.get("created_at") or "", reverse=True)
    return [{"id": e.id, **e.attributes} for e in overrides]


def list_all_overrides():
    overrides = [e for e in ledger.get_all().values() if e.entity_type == PERMISSION_OVERRIDE]
    overrides.sort(key=lambda e: e.attributes.get("created_at") or "", reverse=True)
    return [{"id": e.id, **e.attributes} for e in overrides]


def set_override(target_employee_id, permission_key, granted, granted_by, reason=""):
    """Grants or revokes one permission for one employee, beyond their role
    default. A new override for the same (employee, permission_key) pair
    deactivates any prior one rather than deleting it -- full history stays
    inspectable, only the currently-active grant changes."""

    if permission_key not in _PERMISSION_INDEX and not _is_valid_field_permission_key(permission_key):
        return {"error": f"Unknown permission key '{permission_key}'"}

    target = ledger.get_entity(target_employee_id)
    if not target or target.entity_type != EMPLOYEE:
        return {"error": f"Employee '{target_employee_id}' not found"}

    prior = _active_override(target_employee_id, permission_key)
    if prior is not None:
        prior.attributes["active"] = False
        prior.attributes["superseded_at"] = _now()

    override_id = id_generator.generate("PERM")
    entity = Entity(
        id=override_id,
        entity_type=PERMISSION_OVERRIDE,
        attributes={
            "employee_id": target_employee_id,
            "permission_key": permission_key,
            "granted": bool(granted),
            "reason": reason,
            "active": True,
            "granted_by": granted_by,
            "created_at": _now(),
            "superseded_at": None,
        },
    )
    ledger.add_entity(entity)

    audit_log.record(
        event_type="permission_override_set",
        summary=f"{'Granted' if granted else 'Revoked'} '{permission_key}' for {target_employee_id}",
        entity_id=target_employee_id,
        actor=granted_by,
        details={"permission_key": permission_key, "granted": bool(granted), "reason": reason},
    )

    save_graph(GRAPH_PATH)
    save_audit_log(AUDIT_PATH)
    return {"id": entity.id, **entity.attributes}


def revoke_override(override_id, actor_employee_id):
    """Deactivates a specific override outright (reverting that employee back to
    their plain role default for that one permission), distinct from set_override
    creating a new opposite-direction override."""

    entity = ledger.get_entity(override_id)
    if not entity or entity.entity_type != PERMISSION_OVERRIDE:
        return {"error": f"Override '{override_id}' not found"}

    if not entity.attributes.get("active"):
        return {"error": "This override is already inactive"}

    entity.attributes["active"] = False
    entity.attributes["superseded_at"] = _now()

    audit_log.record(
        event_type="permission_override_revoked",
        summary=f"Deactivated override {override_id} ({entity.attributes.get('permission_key')}) for {entity.attributes.get('employee_id')}",
        entity_id=entity.attributes.get("employee_id"),
        actor=actor_employee_id,
        details={"override_id": override_id},
    )

    save_graph(GRAPH_PATH)
    save_audit_log(AUDIT_PATH)
    return {"id": entity.id, **entity.attributes}


# ---------------------------------------------------------------------------
# 2. Field-level security
# ---------------------------------------------------------------------------

# entity_type -> {field_name: [roles allowed to see the real value by default]}.
# Sam's own literal example -- "Can View Deal, Cannot See Credit Score" -- is the
# Customer.CreditScore entry below; CreditApplication.ssn_last4 (last-4-only,
# this codebase never stores a full SSN anywhere, core/credit_app.py) gets the
# same treatment since it's the other genuinely sensitive field this codebase
# already surfaces broadly today.
FIELD_SECURITY = {
    "Customer": {
        "CreditScore": [ADMIN, FINANCE],
    },
    "CreditApplication": {
        "ssn_last4": [ADMIN, FINANCE],
    },
}

_REDACTED = "•••• (restricted)"


def _field_permission_key(entity_type, field_name):
    return f"field:{entity_type}.{field_name}"


def _is_valid_field_permission_key(permission_key):
    """True if `permission_key` is a well-formed synthetic field-security key
    (`field:{entity_type}.{field_name}`) referencing a real, currently-gated
    FIELD_SECURITY field -- the field-level analog to `_PERMISSION_INDEX`
    membership for the catalog above. set_override() uses this so a field-
    level grant/revoke (Sam's own "Can View Deal, Cannot See Credit Score"
    example) is actually reachable through the one real grant/revoke
    mechanism this module exposes, matching filter_sensitive_fields()'s own
    docstring claim that fields use "the same grant/revoke mechanism above
    ... not a second system" -- previously true only in the docstring, not
    in set_override()'s own validation, which rejected every field: key as
    unknown. Fixed 2026-07-20 as part of the Code Auditor's missing_test_
    coverage closure, which surfaced the gap via a failing test."""

    if not permission_key.startswith("field:"):
        return False
    rest = permission_key[len("field:"):]
    if "." not in rest:
        return False
    entity_type, field_name = rest.split(".", 1)
    return field_name in FIELD_SECURITY.get(entity_type, {})


def can_see_field(role, employee_id, entity_type, field_name):
    allowed_roles = FIELD_SECURITY.get(entity_type, {}).get(field_name)
    if allowed_roles is None:
        return True

    key = _field_permission_key(entity_type, field_name)
    override = _active_override(employee_id, key) if employee_id else None
    if override is not None:
        return bool(override.attributes.get("granted"))

    return role in allowed_roles


def filter_sensitive_fields(role, employee_id, entity_type, attributes):
    """Returns a shallow copy of `attributes` with any FIELD_SECURITY-gated field
    the caller can't see replaced by a plain redaction marker rather than the
    real value -- real enforcement, not just a config screen. Per-employee field
    overrides use a synthetic `field:{entity_type}.{field}` permission key so the
    same grant/revoke mechanism above covers fields too, not a second system."""

    gated = FIELD_SECURITY.get(entity_type)
    if not gated or not attributes:
        return attributes

    out = dict(attributes)
    for field_name in gated:
        if field_name in out and not can_see_field(role, employee_id, entity_type, field_name):
            out[field_name] = _REDACTED
    return out


# ---------------------------------------------------------------------------
# 3. Approval hierarchies (real 3-tier: staff / manager / executive)
# ---------------------------------------------------------------------------

_TIER_RANK = {TIER_STAFF: 0, TIER_MANAGER: 1, TIER_EXECUTIVE: 2}

APPROVAL_CHAINS = {
    "permission_change_request": {
        "label": "Request a permission change",
        "steps": [TIER_MANAGER],
    },
    "role_change_request": {
        "label": "Request a role change",
        "steps": [TIER_MANAGER, TIER_EXECUTIVE],
    },
    "policy_exception": {
        "label": "Policy exception request",
        "steps": [TIER_MANAGER, TIER_EXECUTIVE],
    },
    "expense_request": {
        "label": "Budget / expense request",
        "steps": [TIER_MANAGER],
    },
    "autonomous_ai_rule_activation": {
        "label": "Activate an autonomous AI automation rule",
        "steps": [TIER_MANAGER],
    },
}


def _employee_tier(employee_id):
    emp = ledger.get_entity(employee_id)
    if not emp or emp.entity_type != EMPLOYEE:
        return None
    return infer_tier(emp.attributes.get("Title"))


def list_approval_chains():
    return [{"key": k, **v} for k, v in APPROVAL_CHAINS.items()]


def create_approval_request(chain_key, requested_by, subject, details="", entity_id=None):
    chain = APPROVAL_CHAINS.get(chain_key)
    if not chain:
        return {"error": f"Unknown approval chain '{chain_key}'"}

    requester = ledger.get_entity(requested_by)
    if not requester or requester.entity_type != EMPLOYEE:
        return {"error": f"Employee '{requested_by}' not found"}

    request_id = id_generator.generate("APPR")
    entity = Entity(
        id=request_id,
        entity_type=APPROVAL_REQUEST,
        attributes={
            "chain_key": chain_key,
            "chain_label": chain["label"],
            "steps": list(chain["steps"]),
            "current_step_index": 0,
            "status": "pending",
            "subject": subject,
            "details": details,
            "entity_id": entity_id,
            "requested_by": requested_by,
            "created_at": _now(),
            "updated_at": _now(),
            "history": [
                {"action": "requested", "by": requested_by, "at": _now(), "note": subject}
            ],
        },
    )
    ledger.add_entity(entity)

    audit_log.record(
        event_type="approval_request_created",
        summary=f"{requested_by} requested approval: {subject} ({chain_key})",
        entity_id=request_id,
        actor=requested_by,
        details={"chain_key": chain_key},
    )

    save_graph(GRAPH_PATH)
    save_audit_log(AUDIT_PATH)
    return {"id": entity.id, **entity.attributes}


def _get_request(request_id):
    e = ledger.get_entity(request_id)
    if not e or e.entity_type != APPROVAL_REQUEST:
        return None
    return e


def approve_step(request_id, approver_employee_id, note=""):
    """The real tier-gated approval action: the approver's own Employee.Title is
    resolved to a real tier via core/bot_tasks.py's infer_tier(), and that tier
    must meet or exceed the current step's required tier (a manager can approve
    a manager-tier step; only an executive-tier approver can clear an
    executive-tier step) -- an honest, computed check, not a role checkbox."""

    req = _get_request(request_id)
    if req is None:
        return {"error": f"Approval request '{request_id}' not found"}

    if req.attributes.get("status") != "pending":
        return {"error": f"Request is already '{req.attributes.get('status')}', not pending"}

    approver_tier = _employee_tier(approver_employee_id)
    if approver_tier is None:
        return {"error": f"Employee '{approver_employee_id}' not found"}

    steps = req.attributes.get("steps") or []
    idx = req.attributes.get("current_step_index", 0)
    if idx >= len(steps):
        return {"error": "No pending step on this request"}

    required_tier = steps[idx]
    if _TIER_RANK.get(approver_tier, 0) < _TIER_RANK.get(required_tier, 0):
        return {
            "error": f"This step requires {required_tier}-tier approval or higher; "
                     f"'{approver_employee_id}' is {approver_tier}-tier."
        }

    history = req.attributes.setdefault("history", [])
    history.append({
        "action": "approved_step", "by": approver_employee_id, "at": _now(),
        "tier": approver_tier, "step_index": idx, "note": note,
    })

    next_idx = idx + 1
    req.attributes["current_step_index"] = next_idx
    req.attributes["updated_at"] = _now()

    if next_idx >= len(steps):
        req.attributes["status"] = "approved"
        history.append({"action": "fully_approved", "by": approver_employee_id, "at": _now()})

    audit_log.record(
        event_type="approval_step_approved",
        summary=f"{approver_employee_id} ({approver_tier}) approved step {idx + 1}/{len(steps)} of {request_id}",
        entity_id=request_id,
        actor=approver_employee_id,
        details={"step_index": idx, "final": next_idx >= len(steps)},
    )

    save_graph(GRAPH_PATH)
    save_audit_log(AUDIT_PATH)
    return {"id": req.id, **req.attributes}


def reject_step(request_id, approver_employee_id, reason):
    req = _get_request(request_id)
    if req is None:
        return {"error": f"Approval request '{request_id}' not found"}

    if req.attributes.get("status") != "pending":
        return {"error": f"Request is already '{req.attributes.get('status')}', not pending"}

    if not reason or not reason.strip():
        return {"error": "A rejection reason is required"}

    # Rejecting is a terminal decision, requiring the same current-step
    # authority as approval. A missing employee must never acquire a tier.
    approver_tier = _employee_tier(approver_employee_id)
    if approver_tier is None:
        return {"error": f"Employee '{approver_employee_id}' not found"}
    steps = req.attributes.get("steps") or []
    idx = req.attributes.get("current_step_index", 0)
    if type(idx) is not int or not 0 <= idx < len(steps):
        return {"error": "No pending step on this request"}
    required_tier = steps[idx]
    if _TIER_RANK.get(approver_tier, -1) < _TIER_RANK.get(required_tier, 99):
        return {"error": f"This step requires {required_tier}-tier approval or higher."}

    req.attributes["status"] = "rejected"
    req.attributes["updated_at"] = _now()
    history = req.attributes.setdefault("history", [])
    history.append({
        "action": "rejected", "by": approver_employee_id, "at": _now(),
        "tier": approver_tier, "reason": reason,
    })

    audit_log.record(
        event_type="approval_request_rejected",
        summary=f"{approver_employee_id} rejected {request_id}: {reason}",
        entity_id=request_id,
        actor=approver_employee_id,
        details={"reason": reason},
    )

    save_graph(GRAPH_PATH)
    save_audit_log(AUDIT_PATH)
    return {"id": req.id, **req.attributes}


def cancel_request(request_id, actor_employee_id):
    req = _get_request(request_id)
    if req is None:
        return {"error": f"Approval request '{request_id}' not found"}

    if req.attributes.get("status") != "pending":
        return {"error": f"Request is already '{req.attributes.get('status')}', not pending"}

    if req.attributes.get("requested_by") != actor_employee_id:
        return {"error": "Only the original requester can cancel this request"}

    req.attributes["status"] = "cancelled"
    req.attributes["updated_at"] = _now()
    req.attributes.setdefault("history", []).append(
        {"action": "cancelled", "by": actor_employee_id, "at": _now()}
    )

    save_graph(GRAPH_PATH)
    save_audit_log(AUDIT_PATH)
    return {"id": req.id, **req.attributes}


def get_approval_request(request_id):
    req = _get_request(request_id)
    if req is None:
        return {"error": f"Approval request '{request_id}' not found"}
    return {"id": req.id, **req.attributes}


def list_approval_requests(status=None, requested_by=None, pending_for_employee=None):
    """`pending_for_employee` is the real "my approvals queue" filter -- pending
    requests whose CURRENT step this employee's own tier is high enough to act
    on, the same tier check approve_step() itself enforces."""

    reqs = [e for e in ledger.get_all().values() if e.entity_type == APPROVAL_REQUEST]

    if status:
        reqs = [r for r in reqs if r.attributes.get("status") == status]
    if requested_by:
        reqs = [r for r in reqs if r.attributes.get("requested_by") == requested_by]

    if pending_for_employee:
        tier = _employee_tier(pending_for_employee)
        tier_rank = _TIER_RANK.get(tier, -1)

        def _actionable(r):
            if r.attributes.get("status") != "pending":
                return False
            steps = r.attributes.get("steps") or []
            idx = r.attributes.get("current_step_index", 0)
            if idx >= len(steps):
                return False
            return tier_rank >= _TIER_RANK.get(steps[idx], 99)

        reqs = [r for r in reqs if _actionable(r)]

    reqs.sort(key=lambda r: r.attributes.get("created_at") or "", reverse=True)
    return [{"id": r.id, **r.attributes} for r in reqs]


# ---------------------------------------------------------------------------
# 4. Real tier distribution (used by administration_menu.py's roles_permissions())
# ---------------------------------------------------------------------------

def get_tier_distribution():
    """Every real Employee, bucketed by infer_tier(Title) -- the honest backing
    for a real org-chart-shaped view of who'd approve what."""

    buckets = {TIER_STAFF: [], TIER_MANAGER: [], TIER_EXECUTIVE: []}
    for e in ledger.get_all().values():
        if e.entity_type != EMPLOYEE:
            continue
        tier = infer_tier(e.attributes.get("Title"))
        buckets.setdefault(tier, []).append({
            "id": e.id,
            "name": f"{e.attributes.get('FirstName', '')} {e.attributes.get('LastName', '')}".strip(),
            "title": e.attributes.get("Title"),
            "department": e.attributes.get("Department"),
        })

    return {tier: {"count": len(members), "employees": members} for tier, members in buckets.items()}
