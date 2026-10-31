"""
Thin API-layer functions for the marketing asset design/approval workflow (session
30), imported directly into api/app.py's route handlers -- same "no service layer
indirection" convention every other `*_api.py` module in this codebase follows. ACL
checks live here (not in core/assets.py), mirroring core/messaging_api.py.

Role rule (Sam's explicit scoping answer, session 30): any authenticated role can
request/create and submit an asset; only MARKETING or ADMIN can approve or reject one
or list the pending-approval queue. No new role was added -- reuses MARKETING/ADMIN
exactly as they already work everywhere else in core/permissions.py.
"""

from core.assets import (
    list_templates,
    get_template,
    create_asset,
    get_asset,
    submit_for_approval,
    approve_asset,
    reject_asset,
    list_assets,
    list_pending_approvals,
)
from core.permissions import ADMIN, MARKETING
from core.audit import audit_log
from core.audit_storage import save_audit_log
from core.storage_paths import AUDIT_PATH
from core.compliance import enforce_gate


def _serialize_asset(entity):

    return {
        "id": entity.id,
        **entity.attributes,
    }


def _can_review(role):
    return role == ADMIN or role == MARKETING


def list_templates_api():

    return list_templates()


def create_asset_api(employee_id, template_key, fields, vehicle_id=None, campaign_id=None):

    template = get_template(template_key)

    if not template:
        return {"error": f"Unknown asset template '{template_key}'"}

    missing = [
        f["key"]
        for f in template["fields"]
        if f.get("required") and not (fields or {}).get(f["key"])
    ]

    if missing:
        return {"error": f"Missing required field(s): {', '.join(missing)}"}

    entity = create_asset(template_key, employee_id, fields or {}, vehicle_id, campaign_id)

    return _serialize_asset(entity)


def submit_asset_api(role, employee_id, asset_id):

    asset = get_asset(asset_id)

    if not asset:
        return {"error": "Asset not found"}

    if asset.attributes.get("requested_by") != employee_id and role != ADMIN:
        return {"error": "Only the requester (or an admin) can submit this asset"}

    if asset.attributes.get("status") != "draft":
        return {"error": f"Asset is already '{asset.attributes.get('status')}', not a draft"}

    updated = submit_for_approval(asset_id)

    return _serialize_asset(updated)


def get_asset_api(role, employee_id, asset_id):

    asset = get_asset(asset_id)

    if not asset:
        return {"error": "Asset not found"}

    if asset.attributes.get("requested_by") != employee_id and not _can_review(role):
        return {"error": "You don't have access to this asset"}

    return _serialize_asset(asset)


def list_my_assets_api(employee_id):

    return [_serialize_asset(a) for a in list_assets(requested_by=employee_id)]


def list_pending_approvals_api(role):

    if not _can_review(role):
        return {"error": "You don't have access to the asset approval queue"}

    return [_serialize_asset(a) for a in list_pending_approvals()]


def approve_asset_api(role, reviewer_id, asset_id, notes=None):

    if not _can_review(role):
        return {"error": "You don't have access to approve assets"}

    asset = get_asset(asset_id)

    if not asset:
        return {"error": "Asset not found"}

    if asset.attributes.get("status") != "pending_approval":
        return {"error": f"Asset is '{asset.attributes.get('status')}', not pending approval"}

    # Compliance agent (session 38) -- advertising disclosure check runs on every
    # public-facing creative before it's approved.
    gate = enforce_gate("asset_approve", asset)

    if gate["blocked"]:
        return {
            "error": "Compliance check failed -- this asset can't be approved until the issue(s) below are corrected.",
            "compliance_alert_id": gate["alert_id"],
            "compliance_violations": gate["violations"],
            "notice": gate["notice"],
        }

    updated = approve_asset(asset_id, reviewer_id, notes)

    audit_log.record(
        event_type="asset_approved",
        summary=f"Asset {asset_id} approved by {reviewer_id}",
        entity_id=asset_id,
        actor=reviewer_id,
        details={"template_key": updated.attributes.get("template_key")},
    )
    save_audit_log(AUDIT_PATH)

    return _serialize_asset(updated)


def reject_asset_api(role, reviewer_id, asset_id, notes=None):

    if not _can_review(role):
        return {"error": "You don't have access to reject assets"}

    asset = get_asset(asset_id)

    if not asset:
        return {"error": "Asset not found"}

    if asset.attributes.get("status") != "pending_approval":
        return {"error": f"Asset is '{asset.attributes.get('status')}', not pending approval"}

    updated = reject_asset(asset_id, reviewer_id, notes)

    audit_log.record(
        event_type="asset_rejected",
        summary=f"Asset {asset_id} rejected by {reviewer_id}",
        entity_id=asset_id,
        actor=reviewer_id,
        details={"template_key": updated.attributes.get("template_key"), "notes": notes},
    )
    save_audit_log(AUDIT_PATH)

    return _serialize_asset(updated)
