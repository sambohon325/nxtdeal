"""
NXTDeal Hub -- thin functions between hub/app.py's route handlers and
hub_core/feature_flags.py, matching backend/core/*_api.py's "validate + call the
real function + shape the response" convention.
"""

from hub_core.feature_flags import (
    SCOPES,
    create_or_update_override,
    delete_override,
    list_overrides,
    list_known_flag_keys,
    resolve_flag,
    registry as flag_registry,
)
from hub_core.feature_flags_storage import save_feature_flags
from hub_core.hub_audit_api import record_and_save

FEATURE_FLAGS_PATH = "storage/feature_flags.json"


def list_feature_flag_scopes_api():
    return {"scopes": SCOPES, "known_flag_keys": list_known_flag_keys()}


def list_feature_flag_overrides_api(flag_key=None):
    return {"overrides": list_overrides(flag_key)}


def create_feature_flag_override_api(
    flag_key,
    scope,
    enabled,
    scope_target=None,
    note=None,
    created_by="nxtdeal_staff"
):

    result, error = create_or_update_override(
        flag_key,
        scope,
        enabled,
        scope_target=scope_target,
        note=note,
        created_by=created_by,
    )

    if error:
        return {"error": error}

    save_feature_flags(FEATURE_FLAGS_PATH)

    record_and_save(
        event_type="feature_flag_override_created",
        summary=f"Feature flag '{flag_key}' override set (scope={scope}, enabled={enabled}) by {created_by}",
        dealer_id=scope_target if scope == "dealer" else None,
        actor=created_by,
        details={"flag_key": flag_key, "scope": scope, "scope_target": scope_target, "enabled": enabled},
    )

    return result


def delete_feature_flag_override_api(override_id, deleted_by="nxtdeal_staff"):

    existing = flag_registry.get(override_id)

    ok, error = delete_override(override_id)

    if error:
        return {"error": error}

    save_feature_flags(FEATURE_FLAGS_PATH)

    record_and_save(
        event_type="feature_flag_override_deleted",
        summary=f"Feature flag override '{override_id}' deleted by {deleted_by}",
        dealer_id=(existing.scope_target if existing and existing.scope == "dealer" else None),
        actor=deleted_by,
        details={"override_id": override_id},
    )

    return {"deleted": True, "override_id": override_id}


def resolve_feature_flag_api(flag_key, dealer_id):

    result, error = resolve_flag(flag_key, dealer_id)

    if error:
        return {"error": error}

    return result
