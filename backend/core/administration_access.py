"""NXTDeal control-plane access, provisioned by the deployment operator.

ADMIN remains a dealership role. The environment allowlist is deliberately not
stored in the editable graph, role overrides, request bodies or browser session.
Each backend has its own credential store and allowlist; it grants no cross-tenant
routing. Reserved identities cannot be created/reset by dealership administrators.
"""
import os
from contextvars import ContextVar

system_admin_context = ContextVar("nxtdeal_system_admin", default=False)
SYSTEM_MENU_KEYS = frozenset({"systems", "integrations", "connections", "security",
    "identity_access", "data_management", "audit_center", "ai_management", "fleet",
    "modules", "success_center"})
DEALERSHIP_MENU_KEYS = frozenset({"overview", "organizations", "users", "team_management",
    "roles_permissions", "vendors", "governance", "lead_routing", "workflow_automation",
    "ai_workforce", "ai_spend", "reporting", "connect", "digital_retail"})
SYSTEM_ENTITY_TYPES = frozenset({"SsoConfig", "Entitlement", "Connection", "ApiKey",
    "BotCapabilityGrant", "ProviderCredential", "TeamAgent", "TeamAgentRun", "TeamWorkflowEvent", "ExecutionPolicy"})
PUBLIC_BRIDGE_PREFIXES = ("/dealer-bridge/inbound/adf", "/dealer-bridge/system-map")
SYSTEM_PREFIXES = (
    "/audit", "/dashboard/audit", "/audit-center", "/security", "/api-keys",
    "/data-management", "/integrations", "/connections", "/ai-management",
    "/ai-settings", "/bot/fleet", "/bot-permissions", "/execution-modes",
    "/ai-audit", "/ai-kill-switch", "/success-center", "/dealer-bridge", "/crypto-agility", "/secrets",
    "/auth/admin/lockout", "/auth/admin/unlock", "/auth/admin/ip-allowlist",
)
SYSTEM_MUTATION_PREFIXES = ("/entitlements", "/system-config/feature-flags", "/security")


def reserved_system_admin(employee_id):
    return bool(employee_id) and employee_id in {
        value.strip() for value in os.environ.get("NXTDEAL_SYSTEM_ADMIN_IDS", "").split(",") if value.strip()
    }


def is_system_admin(payload):
    # Only a verified interactive session may enter the control plane. Existing
    # API keys do not inherit it, including keys issued to a system administrator.
    if not payload or payload.get("role") != "ADMIN" or not payload.get("credential_binding"):
        return False
    if payload.get("purpose") or not reserved_system_admin(payload.get("employee_id")):
        return False
    from core.auth import credential_store
    record = credential_store.get_record(payload["employee_id"])
    return bool(record and record.get("role") == "ADMIN" and not record.get("must_change_password") and not record.get("disabled"))


def can_manage_account(payload, target):
    # Let the caller reject invalid/challenge credentials without revealing which IDs are reserved.
    if not payload or payload.get("purpose"):
        return True
    return not reserved_system_admin(target) or is_system_admin(payload)


def can_open_admin_item(payload, key):
    return bool(payload and payload.get("role") == "ADMIN" and
        (key in DEALERSHIP_MENU_KEYS or (key in SYSTEM_MENU_KEYS and is_system_admin(payload))))


def requires_system_admin(path, method):
    path = path.rstrip("/") or "/"
    within = lambda prefix: path == prefix or path.startswith(prefix + "/")
    if any(within(prefix) for prefix in PUBLIC_BRIDGE_PREFIXES):
        return False
    return (any(within(prefix) for prefix in SYSTEM_PREFIXES)
        or (method not in ("GET", "HEAD", "OPTIONS") and any(within(prefix) for prefix in SYSTEM_MUTATION_PREFIXES))
        or (path.startswith("/marketplace/listings/") and path.endswith(("/install", "/uninstall")))
        or path in ("/network/ai-kill-switch-status", "/network/ai-kill-switch-push"))
