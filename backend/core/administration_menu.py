from core.administration_access import system_admin_context, reserved_system_admin
"""
core/administration_menu.py -- real data behind Administration's 8-item Top Menu
(core/menu_catalog.py), session 65 continuation. admin.pdf's own framing: Admin is
different from every other department because it isn't a production department -- it's
the control layer above the dealership ("Operations runs the store. Administration runs
the system that runs the store"), closer to a Salesforce Admin Console / Okta Admin
than a department dashboard. Its Menu Bar (Overview | Users | Security | Systems |
Integrations | Vendors | Governance | Reporting) maps onto: Who has access? Is it
secure? Is the platform up? Are integrations healthy? What are we paying for? Who
approves changes? How are we performing?

Same discipline as core/operations_menu.py/core/sales_menu.py/core/service_menu.py/
core/marketing_menu.py/core/inventory_menu.py/core/finance_menu.py: reuse an
already-built function wherever it's a genuine match, compute a small new real
aggregate where the graph has the underlying data but nobody had queried it this way
yet, and use an honest `not_yet_tracked` note (never a fabricated number) wherever
admin.pdf asks for something this data model doesn't back at all. Confirmed structural
gaps before writing this module: no session table exists (core/auth.py's tokens are
stateless HMAC payloads, not stored server-side) so there's no last-login timestamp or
failed-login COUNTER, though individual login_success/login_failed/credential_created/
credential_reset/password_changed EVENTS are real and audit-logged (core/auth_api.py) --
reused directly for Security. No MFA field, no data-export-tracking, and no system
health/uptime/backup/storage-usage monitoring exists anywhere (a full, confirmed gap).
core/entity_types.py defines a VENDOR entity type that has never been instantiated by
any importer or seed script -- zero real Vendor records exist, so Vendors reuses
core/data_connections_api.py's real Connection records (the same "vendor" stand-in
core/workflow_tab_data.py's administration.vendor_management REAL_SOURCES entry
already established, session 59/60) rather than inventing vendor/contract/license data.
No employee has HireDate/TerminationDate fields, so New Hires/Terminated Employees are
an honest gap too. core/workflow_tab_data.py's administration_onboarding_roster()
(session 59) -- Employee roster cross-referenced with real login-credential coverage --
is reused directly across Overview/Users/Reporting rather than reimplemented.

Bug found and fixed during this session's smoke test: list_connections_api(role)
returns {"connections": [...]}, not a plain list (confirmed by reading
core/data_connections_api.py directly) -- the first draft of overview()/integrations()/
vendors()/reporting() iterated the raw dict, which silently iterated its string keys
instead of the connection records. Fixed at all four call sites to unwrap
result["connections"] first.
"""

from core.dealeros import ledger
from core.entity_types import EMPLOYEE

from core.permissions import ADMIN, OPERATIONS
from core.auth import credential_store
from core.audit_api import list_audit_events, get_audit_dashboard
from core.data_connections_api import list_connections_api
from core.compliance_api import list_alerts_api
from core.campaigns_api import list_pending_campaigns_api
from core.assets_api import list_pending_approvals_api
from core.websites_api import list_pending_websites_api
from core.deals_api import list_pending_financing_api
from core.escalation_dashboard_api import get_dashboard as get_escalation_dashboard
from core.governance import get_governance_overview
from core.workflow_tab_data import administration_onboarding_roster
from core.workflow_tracking_api import list_workflow_instances_api
from core.ai_tools import search_entities, get_entity_by_id, get_related_entities

# Reporting = Department Intelligence integration (Sam: "the dynamic reporting is
# supposed to be integrated in the reporting section of each department"). Of
# Department Intelligence's 5 real keys (sales/service/parts/fi/executive),
# "executive" is Administration's closest match -- Administration is NXTDeal's own
# control-layer department, the nearest analog to a cross-department executive view,
# not a stretch mapping onto an unrelated key.
from core.department_intelligence_api import get_department_api

# Roles & Permissions (Administration Control Center rebuild, first slice,
# 2026-07-18) -- reused directly, no service-layer indirection.
from core.permissions_registry import (
    list_permission_catalog,
    get_effective_permissions,
    list_overrides_for_employee,
    list_all_overrides,
    list_approval_chains,
    list_approval_requests,
    get_tier_distribution,
)

# Vendor Management / System Configuration & Organizations / Data Management /
# Identity & Access (Administration Control Center rebuild, continued,
# 2026-07-18/19) -- reused directly, no service-layer indirection.
from core.vendor_management import get_vendor_dashboard, list_vendors
from core.system_config import get_system_config
from core.data_backup import list_exportable_entity_types, list_backups
from core.api_keys import list_all_api_keys, list_api_keys_for_employee
from core.audit_center import get_audit_center_overview, get_actor_timeline
from core.workflow_automation import get_automation_dashboard
from core.ai_management import get_ai_management_overview

# Newly-built NXTDeal-internal module (2026-07-23 integration pass) -- thin
# role-gated pass-through, mirroring operations_menu.customer_journey.
from core.success_center_api import list_dealers_api


_ADMIN_ONLY_ERROR = {"error": "Admin/Operations role required."}


def _entities(entity_type):
    return [e for e in ledger.get_all().values() if e.entity_type == entity_type]


def _pending_count(result):
    """list_pending_*_api functions return either a plain list or a role-forbidden
    {"error": ...} dict -- same normalization core/operations_menu.py's tasks() already
    uses."""
    if isinstance(result, dict) and "error" in result:
        return {"count": None, "error": result["error"]}
    return {"count": len(result), "items": result}


def _approval_queue(role):
    """The real cross-department "who approves changes?" queue -- every pending
    content/financing approval already tracked elsewhere in this codebase, gathered
    into one view rather than reimplemented. Same real queues
    core/operations_menu.py's tasks() already surfaces individually."""

    return {
        "campaigns": _pending_count(list_pending_campaigns_api(role)),
        "assets": _pending_count(list_pending_approvals_api(role)),
        "websites": _pending_count(list_pending_websites_api(role)),
        "financing": _pending_count(list_pending_financing_api(role)),
    }


def _approval_counts(role):
    """A COUNT-ONLY view of the approval queue for the Overview dashboard module. The full
    _approval_queue keeps each queue's `items` list (the pending entities) for the governance
    and reporting boards, but on the Overview's auto-charted module those raw entity lists
    render as an unreadable JSON dump (Sam's feedback, 2026-07-24) -- so Overview shows just the
    per-queue counts."""
    return {
        key: (value.get("count") if isinstance(value, dict) else value)
        for key, value in _approval_queue(role).items()
    }


def overview(role):
    """admin.pdf's "Overview" item: the Admin command center -- the "bird's-eye view"
    of NXTDeal. System Health, API Status, Monthly Software Spend, and Permissions
    Exceptions have no backing data model -- confirmed full gaps, no uptime/health
    monitoring or Vendor/license data exists anywhere in this codebase."""

    is_admin = role in (ADMIN, OPERATIONS)
    roster = administration_onboarding_roster(role) if is_admin else None

    connections_result = list_connections_api(role)
    connection_count = (
        len(connections_result["connections"])
        if isinstance(connections_result, dict) and "connections" in connections_result
        else None
    )

    open_alerts = list_alerts_api(role, status="open")
    security_alert_count = (
        len(open_alerts["alerts"]) if isinstance(open_alerts, dict) and "alerts" in open_alerts else None
    )

    return {
        "active_users": {"count": roster["total_employees"] if roster else None} if is_admin else {"error": _ADMIN_ONLY_ERROR["error"]},
        "connected_platforms": {"count": connection_count},
        "security_alerts": {
            "count": security_alert_count,
            "note": "Reuses the real compliance-alert stream (core/compliance_rules.py) as the closest existing security-adjacent signal -- not a dedicated security-event feed.",
        },
        "executive_approvals_pending": _approval_counts(role),
        "user_activity_by_department": roster["by_department"] if roster else {"error": _ADMIN_ONLY_ERROR["error"]},
        "not_yet_tracked": {
            "permissions_exceptions": "No permission-exception/review data model exists yet.",
            "system_health": "No service-uptime/health-monitoring data model exists anywhere in this codebase yet.",
            "api_status": "No API-status/uptime monitoring exists yet.",
            "monthly_software_spend": "No Vendor/license/contract data has ever been populated -- VENDOR is a defined entity type with zero real records.",
            "cost_center": "Same gap as monthly_software_spend -- no real cost/license data exists to compute unused seats or potential savings.",
        },
    }


def _employee_brief(employee_id):
    emp = ledger.get_entity(employee_id)
    if not emp or emp.entity_type != EMPLOYEE:
        return {"name": None, "title": None, "department": None}
    first = emp.attributes.get("FirstName", "") or ""
    last = emp.attributes.get("LastName", "") or ""
    name = f"{first} {last}".strip() or None
    return {
        "name": name,
        "title": emp.attributes.get("Title"),
        "department": emp.attributes.get("Department"),
    }


def _user_administration_row(rec):
    """A genuine identity + access + security composite per credentialed
    employee -- Users Enrichment (Administration Control Center rebuild,
    closing slice, 2026-07-19): reuses core/permissions_registry.py's real
    overrides, core/api_keys.py's real API keys, and core/auth.py's real
    computed lockout state, rather than a fourth parallel roster. This is
    the actual "who has access, at what level, and is anything currently
    restricted" answer admin.pdf's Users item asks for."""

    employee_id = rec["employee_id"]
    brief = _employee_brief(employee_id)
    lockout = credential_store.get_lockout_status(employee_id)
    active_overrides = [o for o in list_overrides_for_employee(employee_id) if o.get("active")]
    active_keys = [k for k in list_api_keys_for_employee(employee_id) if k.get("active")]

    return {
        "employee_id": employee_id,
        "name": brief["name"],
        "title": brief["title"],
        "department": brief["department"],
        "role": rec.get("role"),
        "must_change_password": rec.get("must_change_password", False),
        "locked": lockout["locked"],
        "failed_attempts": lockout["failed_attempts"],
        "active_permission_overrides": len(active_overrides),
        "active_api_keys": len(active_keys),
    }


def users(role, query=None):
    """admin.pdf's "Users" item: the central employee directory. Active
    Employees/Department Access reuse administration_onboarding_roster directly (real
    Employee-vs-login-credential coverage, session 59). Role Assignments is a
    genuinely new real aggregate: credential_store's role field grouped by role. New
    Hires and Terminated Employees have no backing data model -- Employee has no
    HireDate/TerminationDate field in this codebase.

    Enriched (Administration Control Center rebuild, closing slice, 2026-07-19):
    `user_administration` is a real per-employee identity+access+security row
    (permission overrides, API keys, lockout state) composed from three modules
    this rebuild already built -- core/permissions_registry.py, core/api_keys.py,
    core/auth.py -- rather than four separate screens an admin would otherwise
    have to cross-reference by hand. `permission_requests` is now real too: the
    Roles & Permissions slice's own real ApprovalRequest chains include
    "permission_change_request"/"role_change_request", closing what used to be
    an honest not_yet_tracked gap here. A single EMP- id query now returns a
    full combined identity/access/security/recent-activity detail view for
    that one employee, not just a raw entity dump."""

    if role not in (ADMIN, OPERATIONS):
        return _ADMIN_ONLY_ERROR

    if query:
        q = query.strip().upper()
        if q.startswith("EMP-"):
            entity = get_entity_by_id(role, q)
            if "error" in entity:
                return entity

            record = credential_store.get_record(q) or {}
            lockout = credential_store.get_lockout_status(q)
            active_overrides = [o for o in list_overrides_for_employee(q) if o.get("active")]

            return {
                "employee": entity,
                "related_entities": get_related_entities(role, q),
                "identity_and_access": {
                    "role": record.get("role"),
                    "must_change_password": record.get("must_change_password", False),
                    "created_at": record.get("created_at"),
                    "email": record.get("email"),
                    "lockout": lockout,
                    "ip_allowlist": record.get("ip_allowlist") or [],
                    "effective_permissions": get_effective_permissions((credential_store.get_record(q) or {}).get("role"), q),
                    "active_permission_overrides": active_overrides,
                    "api_keys": list_api_keys_for_employee(q) if system_admin_context.get() else [],
                },
                "recent_activity": get_actor_timeline(q, limit=25) if system_admin_context.get() else {"notice": "System activity requires NXTDeal system administrator access"},
            }
        results = [r for r in search_entities(role, query) if r["entity_type"] == EMPLOYEE]
        return {"query": query, "count": len(results), "results": results}

    roster = administration_onboarding_roster(role)

    role_assignments = {}
    for rec in credential_store.list_records():
        r = rec.get("role", "Unknown")
        role_assignments[r] = role_assignments.get(r, 0) + 1

    records = [rec for rec in credential_store.list_records() if system_admin_context.get() or not reserved_system_admin(rec["employee_id"])]
    user_admin_rows = [_user_administration_row(rec) for rec in records]

    permission_requests = [
        r for r in list_approval_requests()
        if r.get("chain_key") in ("permission_change_request", "role_change_request")
    ]
    permission_requests_by_status = {}
    for r in permission_requests:
        permission_requests_by_status[r["status"]] = permission_requests_by_status.get(r["status"], 0) + 1

    return {
        "active_employees": {"count": roster["total_employees"]},
        "department_access": roster["by_department"],
        "employees_without_login": {
            "count": len(roster["employees_without_login"]),
            "employees": roster["employees_without_login"],
        },
        "role_assignments": role_assignments,
        "user_administration": {
            "count": len(user_admin_rows),
            "rows": user_admin_rows[:100],
            "locked_count": sum(1 for r in user_admin_rows if r["locked"]),
            "with_active_overrides_count": sum(1 for r in user_admin_rows if r["active_permission_overrides"] > 0),
            "with_active_api_keys_count": sum(1 for r in user_admin_rows if r["active_api_keys"] > 0),
            "note": "A real per-employee identity+access+security composite (core/permissions_registry.py + core/api_keys.py + core/auth.py) -- query a single EMP- id for that employee's full effective-permission set, active overrides, API keys, lockout detail, and recent audit activity.",
        },
        "permission_requests": {
            "count": len(permission_requests),
            "by_status": permission_requests_by_status,
            "requests": permission_requests[:25],
            "note": "Real ApprovalRequest records (core/permissions_registry.py) on the 'permission_change_request'/'role_change_request' chains -- closes what used to be an honest not_yet_tracked gap here. Create one via POST /approval-requests.",
        },
        "not_yet_tracked": {
            "new_hires": "Employee has no HireDate field in this data model yet.",
            "terminated_employees": "Employee has no TerminationDate/active-status field in this data model yet.",
        },
    }


def roles_permissions(role, query=None, employee_id=None):
    """Administration's new "Roles & Permissions" item (Administration Control
    Center rebuild, first slice, 2026-07-18) -- Sam's own "one of the most
    important modules." A query of a real EMP- id returns that specific
    employee's effective permission set + active overrides; the default view is
    the whole matrix -- the real permission catalog (core/permissions_registry.py,
    each permission's role default mirroring an already-real ACL set elsewhere in
    this codebase), a real tier distribution (staff/manager/executive, off
    core/bot_tasks.py's own infer_tier() applied to every real Employee.Title),
    every currently-active permission override, and the approval-request queue
    (real counts by status, not a fabricated pending number)."""

    if role not in (ADMIN, OPERATIONS):
        return _ADMIN_ONLY_ERROR

    if query:
        q = query.strip().upper()
        if q.startswith("EMP-"):
            entity = get_entity_by_id(role, q)
            if "error" in entity:
                return entity
            return {
                "employee": entity,
                "effective_permissions": get_effective_permissions((credential_store.get_record(q) or {}).get("role"), q),
                "overrides": list_overrides_for_employee(q),
            }
        results = [r for r in search_entities(role, query) if r["entity_type"] == EMPLOYEE]
        return {"query": query, "count": len(results), "results": results}

    catalog = list_permission_catalog()
    tiers = get_tier_distribution()
    overrides = list_all_overrides()
    active_overrides = [o for o in overrides if o.get("active")]

    all_requests = list_approval_requests()
    by_status = {}
    for r in all_requests:
        s = r.get("status", "unknown")
        by_status[s] = by_status.get(s, 0) + 1

    return {
        "permission_catalog": catalog,
        "tier_distribution": {tier: data["count"] for tier, data in tiers.items()},
        "tier_breakdown": tiers,
        "active_overrides": {"count": len(active_overrides), "overrides": active_overrides[:25]},
        "approval_chains": list_approval_chains(),
        "approval_requests": {"by_status": by_status, "total": len(all_requests)},
    }


def security(role):
    """admin.pdf's "Security" item: the dealership SOC. Login Activity and Failed
    Logins are REAL -- core/auth_api.py audit-logs every login_success/login_failed
    event (confirmed by reading the source), not a fabricated feed. Security Events
    reuses the broader audit dashboard plus credential-lifecycle events
    (credential_created/credential_reset/password_changed). Real as of the Security
    expansion (Administration Control Center rebuild, continued): account-lockout
    state (core/auth.py's CredentialStore.get_lockout_status(), a real computed
    failed-attempt counter + currently-locked flag) and per-employee IP-allowlist
    coverage (how many credentials have a real, non-empty allowlist set) --
    surfaced as a roster-wide summary here, with the single-employee detail views
    living at GET /auth/admin/lockout/{employee_id} and the mutating unlock/
    set-ip-allowlist actions at their own dedicated routes. MFA Status, Suspicious
    Activity, and Data Exports still have no backing data model -- no MFA field
    exists on any credential record, and no export-tracking exists anywhere."""

    if role not in (ADMIN, OPERATIONS):
        return _ADMIN_ONLY_ERROR

    login_success = list_audit_events(event_type="login_success")
    login_failed = list_audit_events(event_type="login_failed")
    credential_created = list_audit_events(event_type="credential_created")
    credential_reset = list_audit_events(event_type="credential_reset")
    password_changed = list_audit_events(event_type="password_changed")

    def _brief(events):
        return [
            {"id": e.get("id"), "actor": e.get("actor"), "entity_id": e.get("entity_id"), "timestamp": e.get("timestamp")}
            for e in events[:25]
        ]

    records = credential_store.list_records()
    locked_employees = []
    ip_restricted_count = 0
    for rec in records:
        employee_id = rec["employee_id"]
        lockout = credential_store.get_lockout_status(employee_id)
        if lockout["locked"]:
            locked_employees.append({"employee_id": employee_id, **lockout})
        full_record = credential_store.get_record(employee_id) or {}
        if full_record.get("ip_allowlist"):
            ip_restricted_count += 1

    return {
        "login_activity": {"count": len(login_success), "recent": _brief(login_success)},
        "failed_logins": {"count": len(login_failed), "recent": _brief(login_failed)},
        "security_events": {
            "credential_created": len(credential_created),
            "credential_reset": len(credential_reset),
            "password_changed": len(password_changed),
        },
        "account_lockouts": {
            "count": len(locked_employees),
            "locked_employees": locked_employees,
            "note": "Real, computed lockout state (core/auth.py) -- 'locked' is always evaluated against the real clock, not a stale stored flag. Use GET /auth/admin/lockout/{employee_id} for one employee's detail and POST /auth/admin/unlock/{employee_id} to clear a lockout early.",
        },
        "ip_allowlist_coverage": {
            "restricted_employee_count": ip_restricted_count,
            "total_employee_count": len(records),
            "note": "Count of employees with a real, non-empty IP allowlist set (core/auth.py's CredentialStore.set_ip_allowlist()) -- an empty list means unrestricted, the default. Manage via POST /auth/admin/ip-allowlist/{employee_id} (ADMIN-only).",
        },
        "not_yet_tracked": {
            "mfa_status": "No MFA field exists on any credential record yet.",
            "suspicious_activity": "No anomaly-detection/suspicious-activity flagging exists yet.",
            "data_exports": "No data-export-tracking exists anywhere in this codebase yet.",
        },
    }


def systems(role):
    """admin.pdf's "Systems" item: admin control over the actual platform. Audit Logs
    reuses get_audit_dashboard directly. Workflow Engine is a genuinely new real
    aggregate: active WorkflowInstance counts by status (core/workflow_tracking.py,
    session 53). NXTDeal Services, Database Health, Storage Usage, and Backup Status
    have no backing data model -- confirmed full gap, no uptime/health/storage
    monitoring exists anywhere in this codebase."""

    if role not in (ADMIN, OPERATIONS):
        return _ADMIN_ONLY_ERROR

    audit = get_audit_dashboard()

    instances = list_workflow_instances_api()
    by_status = {}
    if isinstance(instances, list):
        for inst in instances:
            status = inst.get("status", "unknown")
            by_status[status] = by_status.get(status, 0) + 1

    return {
        "audit_logs": audit,
        "workflow_engine": {
            "total_instances": len(instances) if isinstance(instances, list) else None,
            "by_status": by_status,
        },
        "not_yet_tracked": {
            "dealeros_services": "No service-uptime monitoring exists yet.",
            "database_health": "No database-health-check data model exists yet.",
            "storage_usage": "No storage-usage tracking exists yet.",
            "backup_status": "No backup-tracking data model exists yet.",
        },
    }


def integrations(role):
    """admin.pdf's "Integrations" item: the dealership technology stack. Reuses
    list_connections_api directly (core/data_connections.py, session 37) -- the exact
    real source core/workflow_tab_data.py's administration.vendor_management already
    established for this class of data. Grouped by connection_type/status/department,
    a genuinely new real aggregate over the same real records.

    Enriched (Administration Control Center rebuild, closing slice, 2026-07-19):
    `software_vendor_contracts` surfaces the software-category slice of
    core/vendor_management.py's real Vendor records alongside the Connection data
    above -- two related but genuinely distinct real things, both honestly
    labeled rather than conflated: a Connection is a live data-integration
    endpoint (a CSV import, an API feed); a software Vendor is the actual
    contract behind an integration (cost, renewal date, contact). See
    vendors() for the full vendor catalog across every category."""

    connections_result = list_connections_api(role)

    if isinstance(connections_result, dict) and "error" in connections_result:
        return connections_result

    connections = connections_result["connections"]

    by_type = {}
    by_status = {}
    by_department = {}

    for c in connections:
        ctype = c.get("connection_type", "unknown")
        status = c.get("status", "unknown")
        dept = c.get("department", "unknown")
        by_type[ctype] = by_type.get(ctype, 0) + 1
        by_status[status] = by_status.get(status, 0) + 1
        by_department[dept] = by_department.get(dept, 0) + 1

    software_vendors = list_vendors(category="software")
    software_monthly_cost = round(
        sum(v.get("monthly_cost") or 0 for v in software_vendors if v.get("status") == "active"), 2
    )

    return {
        "total_connections": len(connections),
        "by_connection_type": by_type,
        "by_status": by_status,
        "by_department": by_department,
        "connections": connections[:50],
        "software_vendor_contracts": {
            "count": len(software_vendors),
            "active_monthly_cost": software_monthly_cost,
            "vendors": software_vendors,
            "note": "Real Vendor entities (core/vendor_management.py) filtered to category=='software' -- the actual contract side of this screen (cost, renewal date, contact), distinct from the live data Connections above. Add one via POST /vendors.",
        },
        "not_yet_tracked": {
            "oem_feed_specific_status": "Connections are typed csv/api, not a dedicated OEM-feed category -- no OEM-feed-specific health check exists yet.",
        },
    }


def vendors(role):
    """admin.pdf's "Vendors" item: software and contract management. VENDOR is a
    defined entity type (core/entity_types.py) that went unpopulated for a long
    stretch of this codebase's history -- Integrations' real Connection records were
    reused as the honest stand-in (core/workflow_tab_data.py's administration.
    vendor_management precedent). As of the Vendor Management slice (Administration
    Control Center rebuild, continued), core/vendor_management.py's real Vendor
    entities now exist alongside that Connection-proxy data -- BOTH are surfaced here
    (not one replacing the other) since they answer genuinely different questions:
    Connections are real data-integration endpoints (a CSV import, an API feed);
    Vendors are real software/service contracts (a subscription, a monthly cost, a
    renewal date) -- a dealership's CRM data connection and its CRM vendor contract
    are related but distinct real things. Use POST /vendors to add a real vendor
    record."""

    if role not in (ADMIN, OPERATIONS):
        return _ADMIN_ONLY_ERROR

    connections_result = list_connections_api(role)
    connections = (
        connections_result["connections"]
        if isinstance(connections_result, dict) and "connections" in connections_result
        else []
    )

    vendor_dashboard = get_vendor_dashboard()

    return {
        "vendors": vendor_dashboard,
        "active_vendors_proxy": {
            "count": len(connections),
            "connections": connections[:50],
            "note": "Kept alongside the real Vendor data above, not replaced by it -- these are real Connection records (core/data_connections.py) reused as a data-integration-endpoint view, a different real thing from a Vendor's own software/service contract record. See this function's own docstring for why both exist.",
        },
        "not_yet_tracked": {
            "usage_analysis": "No per-seat usage-tracking data model exists yet -- Vendor now tracks monthly_cost/contract dates/auto_renew for real, but not per-seat license utilization.",
        },
    }


def organizations(role):
    """Administration's new "Organizations" item (Administration Control Center
    rebuild, continued): this ONE dealer's own profile and locations/rooftops --
    NOT multiple separate dealers, that's the NXTDeal Hub's job (see CLAUDE.md's
    "NXTDeal Hub / Multi-Tenant Architecture" section). Viewing is open to any role
    (every department benefits from knowing the dealership's own business hours/
    timezone); editing is gated inside core/system_config_api.py itself
    (ADMIN/OPERATIONS)."""

    return get_system_config()


def data_management(role):
    """Administration's new "Data Management" item (Administration Control Center
    rebuild, continued): real per-entity-type CSV export (core/data_backup.py) plus
    real graph.json backup/restore. ADMIN/OPERATIONS-only, matching this whole
    department's established convention -- restoring a backup is real (and the
    single most consequential real action in this rebuild), so this view only
    lists what exists, it never performs a restore itself."""

    if role not in (ADMIN, OPERATIONS):
        return _ADMIN_ONLY_ERROR

    return {
        "exportable_entity_types": list_exportable_entity_types(),
        "backups": list_backups(),
        "not_yet_tracked": {
            "scheduled_backups": "No scheduled/automatic backup system exists -- an admin triggers a backup explicitly via POST /data-management/backups, same 'explicit human action, not a background job' precedent as Payments' auto-draft run-now action.",
        },
    }


def identity_access(role):
    """Administration's new "Identity & Access" item (Administration Control Center
    rebuild, continued): real per-employee API keys (core/api_keys.py) for
    programmatic/integration access, distinct from core/auth.py's session tokens --
    already wired into api/app.py's _authenticate() as a real bearer-token fallback,
    not a hollow CRUD screen. ADMIN/OPERATIONS-only for the platform-wide roster
    view here; an individual employee manages their own keys via GET /api-keys/mine
    and POST /api-keys."""

    if role not in (ADMIN, OPERATIONS):
        return _ADMIN_ONLY_ERROR

    keys = list_all_api_keys()
    active_keys = [k for k in keys if k.get("active")]

    return {
        "total_keys": len(keys),
        "active_keys": {"count": len(active_keys), "keys": active_keys[:50]},
        "revoked_keys": {"count": len(keys) - len(active_keys)},
    }


def audit_center(role):
    """admin.pdf's "Audit Center" item -- a real investigative workspace over
    the audit log, distinct from Security/Systems/Governance's own thin
    slices of it. Reuses core/audit_center.py's get_audit_center_overview()
    directly for this menu view; the dedicated real filtering/search,
    actor-activity drill-down, and suspicious-activity flag list all live at
    their own /audit-center/* routes (core/audit_center_api.py), the same
    "bespoke board bypasses /menu/data" precedent every other rich
    Administration slice this rebuild (Roles & Permissions, Vendors,
    Organizations, Data Management, Identity & Access) already established."""

    if role not in (ADMIN, OPERATIONS):
        return _ADMIN_ONLY_ERROR

    return get_audit_center_overview()


def workflow_automation(role):
    """admin.pdf's "Workflow Automation" item -- core/workflow_automation.py's
    real, admin-configurable "if condition, then action" rule engine.
    Evaluated live on every fetch (run_now=True, its own established
    "compute on read, no third background scheduler" scoping decision -- see
    that module's docstring for the full reasoning) rather than a separate
    tick. The dedicated rule CRUD/execution-log/manual-run actions all live
    at their own /automation*/automation-rules/* routes
    (core/workflow_automation_api.py), the same "bespoke board bypasses
    /menu/data" precedent every other rich Administration slice this
    rebuild established."""

    if role not in (ADMIN, OPERATIONS):
        return _ADMIN_ONLY_ERROR

    return get_automation_dashboard(run_now=True)


def ai_management(role):
    """admin.pdf's "AI Management" item -- core/ai_management.py's real catalog of
    every OpenAI-backed feature in this codebase, each with a real, wired kill switch
    (backed by core/system_config.py's FEATURE_FLAGS, actually checked by each
    feature's own consumer function, not just stored) and honest in-memory call-
    attempt counters. See core/ai_management.py's own docstring for why usage/cost
    metrics from a real OpenAI dashboard aren't shown here (this sandbox has no
    outbound network path to the OpenAI API at all) and for a real route-wiring gap
    this module's own research found (core/help_api.py's ask_help_api() has no route
    behind it). The dedicated toggle action lives at its own
    /ai-management/features/{feature_key} route (core/ai_management_api.py), same
    "bespoke board bypasses /menu/data for its own mutations" precedent every other
    rich Administration slice this rebuild established."""

    if role not in (ADMIN, OPERATIONS):
        return _ADMIN_ONLY_ERROR

    return get_ai_management_overview(role)


def modules(role):
    """Freemium Platform roadmap, Phase 5 -- the NXTDeal Foundation + paid Modules entitlement
    state (core/entitlements.py): which Modules are active, at what level, the current profile
    (reference/foundation/custom), and the Foundation usage caps. ADMIN/OPERATIONS. The bespoke
    AddModulesBoard performs its own mutations via the dedicated /entitlements/* routes (same
    'bespoke board bypasses /menu/data for mutations' precedent every rich Administration slice
    follows); this is the menu's at-a-glance snapshot."""

    if role not in (ADMIN, OPERATIONS):
        return _ADMIN_ONLY_ERROR

    from core.entitlements import get_entitlements
    return get_entitlements()


def ai_spend(role):
    """Freemium Platform roadmap, Phase 5 -- the AI Spend Governor overview (core/ai_spend.py):
    the bring-your-own-key AI provider posture and per-user AI-action consumption against the
    admin's limits for the current month. ADMIN/OPERATIONS. The AiSpendBoard mutates via the
    dedicated /ai-spend/* routes; this is the menu's at-a-glance snapshot."""

    if role not in (ADMIN, OPERATIONS):
        return _ADMIN_ONLY_ERROR

    from core.ai_spend import get_spend_overview
    return get_spend_overview()


def fleet(role):
    """The agentic-bot FLEET (Pillar 4, core/bot_fleet.py) -- the nine NXTDeal team
    agents, each recording its team's real observed workflows and admin-activatable in
    draft/auto mode (auto gated by the same default-deny bot.coverage.auto_mode
    capability as Bot Coverage). Viewing the fleet is non-sensitive operational insight
    (how each team works), open to any authenticated role -- the same posture
    core/bot_fleet_api.get_fleet_api() applies; activation/deactivation is ADMIN-only,
    enforced at the dedicated /bot/fleet/{section}/activate|deactivate routes
    (core/bot_fleet_api.py), the same "bespoke board bypasses /menu/data for its own
    mutations" precedent every rich Administration slice follows. The FleetBoard reads
    live fleet state straight from /bot/fleet, so this pass-through is just the menu's
    honest at-a-glance snapshot."""

    from core.bot_fleet import list_fleet, fleet_summary

    return {"fleet": list_fleet(), "summary": fleet_summary()}


def ai_workforce(role):
    """The customer-facing AI WORKFORCE (core/ai_worker.py) -- eight AI workers
    (Receptionist, BDC, Sales, Service, Marketing, Finance, Collections, Operator),
    each handling inbound touches across phone/SMS/email/chat and working an outbound
    queue. Viewing the workforce is non-sensitive operational insight, open to any
    authenticated role -- the same posture core/ai_worker_api.get_workforce_api()
    applies; activation/deactivation and queue runs are ADMIN-only, enforced at the
    dedicated /workforce/{role}/activate|deactivate|run routes (core/ai_worker_api.py),
    the same "bespoke board bypasses /menu/data for its own mutations" precedent every
    rich Administration slice follows. The AiWorkforceBoard reads live state straight
    from /workforce, so this pass-through is just the menu's honest at-a-glance snapshot."""

    from core.ai_worker import list_workforce, workforce_summary

    return {"workforce": list_workforce(), "summary": workforce_summary()}


def connect(role):
    """NXTDeal CONNECT (core/connect.py) -- the unified customer-engagement surface: one
    inbox across every channel, a per-customer timeline, and an analytics rollup (AI-vs-human
    split + rules-based sentiment/score on every channel). It's a pure read/compose layer over
    the Communications already logged (no new storage/entity/capability), so viewing is open to
    any authenticated role -- the same posture core/connect_api.get_connect_analytics_api()
    applies. The ConnectBoard reads live inbox/timeline/analytics straight from /connect/*, so
    this pass-through is just the menu's honest at-a-glance analytics snapshot."""

    from core.connect import get_analytics

    return get_analytics()


def digital_retail(role):
    """The Digital Retail KPI dashboard (core/digital_retail_analytics.py) -- a read-only
    roll-up over everything the Digital Retail initiative (Verify/execution-modes/negotiation/
    self-service deals/delivery/AI-workforce) records: digital deals/closings/gross, AI
    performance, and the journey drop-off funnel. Non-sensitive operational insight, open to any
    authenticated role -- the same posture core/digital_retail_analytics_api applies. The
    DigitalRetailBoard reads live from /digital-retail/dashboard, so this pass-through is the
    menu's honest at-a-glance snapshot."""

    from core.digital_retail_analytics import get_digital_retail_dashboard

    return get_digital_retail_dashboard()


def governance(role):
    """admin.pdf's "Compliance & Governance" item (enriched 2026-07-18,
    Administration Control Center rebuild continuation): the formal business
    governance layer. Approval Queue (content approvals -- campaigns/assets/
    websites/financing) and Escalation Rules are the same real sources this
    item already surfaced. Audit Trail is now the real governance-scoped
    slice of the audit log (core/governance.py's get_governance_action_log(),
    Permissions/Approvals/Compliance categories only) rather than an
    undifferentiated flat dump of every event type. Newly composed in this
    same call: a real cross-department Approval Hierarchy summary (every
    ApprovalRequest ever created via core/permissions_registry.py's tier-
    gated chains -- permission-change/role-change/policy-exception/expense --
    grouped by status/chain with a real average turnaround time), a real
    Compliance Summary (open/resolved/overridden alert counts, a real
    resolution rate, a real average resolution time, and a per-law violation
    breakdown off core/compliance.py's cited-rules engine), and a real
    blended Governance Health figure (compliance resolution_rate averaged
    with approval throughput_rate -- both real, neither fabricated). Policy
    Management, Workflow Templates, and Department Standards still have no
    backing data model -- no policy entity exists anywhere in this codebase;
    core/workflow_catalog.py's WORKFLOW_CATALOG is a fixed, code-defined
    catalog, not a dealer-editable template-management feature -- stated
    honestly rather than invented."""

    if role not in (ADMIN, OPERATIONS):
        return _ADMIN_ONLY_ERROR

    approval_queue = _approval_queue(role)
    escalations = get_escalation_dashboard()
    governance_overview = get_governance_overview()

    return {
        "approval_queue": approval_queue,
        "escalation_rules": escalations,
        "audit_trail": governance_overview["governance_action_log"],
        "compliance_summary": governance_overview["compliance_summary"],
        "approval_hierarchy": governance_overview["approval_hierarchy"],
        "governance_health": governance_overview["governance_health"],
        "not_yet_tracked": governance_overview["not_yet_tracked"],
    }


def reporting(role):
    """admin.pdf's "Reporting" item: administrative reporting. User Reports reuses
    administration_onboarding_roster, including a genuinely real "NXTDeal Adoption"
    figure (with_login / total_employees). Integration Reports reuses the same
    Connection-status breakdown Integrations surfaces. Governance Reports reuses the
    real approval-queue counts. No standalone "administration" forecast entry exists in
    core/prediction.py (confirmed absent) -- said so rather than borrowing an unrelated
    department's forecast.

    Enriched (Administration Control Center rebuild, closing slice, 2026-07-19):
    four new real, backend-only report sections -- vendor_summary (core/
    vendor_management.py's real cost/renewal aggregate, closing the old
    software_reports gap), audit_summary (core/audit_center.py's real event
    totals + suspicious-activity flag counts, closing the old security_reports
    gap), permissions_summary (core/permissions_registry.py's real tier
    distribution + active-override + approval-request counts), and
    ai_adoption_summary (core/ai_management.py's real per-feature enabled/
    call-attempt counts). Each is a new top-level key on this function's own
    return dict -- core/report_modules.py's get_report_modules() already
    reshapes every top-level key of a department's reporting() fetch into a
    draggable module with zero code changes there, the same auto-discovery
    precedent every prior department's Reporting slice (Sales session 97,
    Inventory/Service/Finance sessions 110/111/112) already established, so
    this needed no new route and no frontend change to surface on the
    existing Report Dashboard Builder."""

    if role not in (ADMIN, OPERATIONS):
        return _ADMIN_ONLY_ERROR

    roster = administration_onboarding_roster(role)
    total = roster["total_employees"]
    with_login = sum(d.get("with_login", 0) for d in roster["by_department"].values())
    adoption_rate = round(with_login / total, 3) if total else None

    connections_result = list_connections_api(role)
    by_status = {}
    if isinstance(connections_result, dict) and "connections" in connections_result:
        for c in connections_result["connections"]:
            status = c.get("status", "unknown")
            by_status[status] = by_status.get(status, 0) + 1

    approval_queue = _approval_queue(role)

    vendor_dashboard = get_vendor_dashboard()
    vendor_summary = {
        "total_vendors": vendor_dashboard["total_vendors"],
        "active_vendors": vendor_dashboard["active_vendors"],
        "total_monthly_cost": vendor_dashboard["total_monthly_cost"],
        "upcoming_renewals_count": len(vendor_dashboard["upcoming_renewals"]),
        "by_category": vendor_dashboard["by_category"],
    }

    audit_overview = get_audit_center_overview()
    audit_summary = {
        "total_events": audit_overview["total_events"],
        "by_type": audit_overview["by_type"],
        "suspicious_activity": audit_overview["suspicious_activity_summary"],
    }

    tier_distribution = get_tier_distribution()
    tier_counts = {tier: bucket["count"] for tier, bucket in tier_distribution.items()}
    all_requests = list_approval_requests()
    requests_by_status = {}
    for r in all_requests:
        requests_by_status[r["status"]] = requests_by_status.get(r["status"], 0) + 1
    permissions_summary = {
        "tier_distribution": tier_counts,
        "active_overrides_count": len(list_all_overrides()),
        "approval_requests_by_status": requests_by_status,
        "total_approval_requests": len(all_requests),
    }

    ai_overview = get_ai_management_overview(role)
    ai_adoption_summary = {
        "total_features": ai_overview["summary"]["total_features"],
        "enabled_count": ai_overview["summary"]["enabled_count"],
        "disabled_count": ai_overview["summary"]["disabled_count"],
        "features_with_recorded_activity": ai_overview["summary"]["features_with_recorded_activity"],
    }

    return {
        "user_reports": {
            "total_employees": total,
            "with_login": with_login,
            "dealeros_adoption_rate": adoption_rate,
        },
        "integration_reports": {"by_status": by_status},
        "governance_reports": {"approval_queue": approval_queue},
        "vendor_summary": vendor_summary,
        "audit_summary": audit_summary if system_admin_context.get() else {"notice": "System audit reports require NXTDeal system administrator access"},
        "permissions_summary": permissions_summary,
        "ai_adoption_summary": ai_adoption_summary,
        "forecasting": None,
        "department_intelligence": get_department_api(role, "executive"),
        "not_yet_tracked": {
            "security_reports": "Real login/lockout/audit-event activity is now surfaced via the new audit_summary field above (core/audit_center.py) -- a dedicated access-violation risk SCORE remains out of scope for this backend-only enrichment.",
            "software_reports": "Real vendor cost/renewal data is now surfaced via the new vendor_summary field above (core/vendor_management.py) -- per-seat/per-license usage analysis remains an honest gap, no usage-tracking data model exists anywhere in this codebase.",
            "executive_reports": "No technology-spend-vs-budget, security-risk-score, or single operational-health-score computation exists yet -- vendor_summary/audit_summary/permissions_summary/ai_adoption_summary above are real component signals, not yet blended into one executive score.",
            "forecasting": "No standalone 'administration' department entry exists in core/prediction.py yet.",
        },
    }


def success_center(role):
    """Administration's "Success Center" view (2026-07-23) -- a thin, role-gated
    pass-through to core/success_center_api.py's real portfolio-wide dealer list
    (NXTDeal-internal). Mirrors operations_menu.customer_journey."""

    return {
        "success_center": list_dealers_api(role),
        "note": "NXTDeal-internal dealer success portfolio overview (Administration).",
    }
