"""
Thin API-layer functions for the campaign & customer-lifecycle engine (session 31),
imported directly into api/app.py's route handlers -- same "no service layer
indirection" convention every other `*_api.py` module in this codebase follows. ACL
checks live here (not in core/campaigns.py), mirroring core/assets_api.py.

Role rule, deliberately matching the asset-workflow precedent Sam already approved
(session 30 -- "reuse MARKETING as approver, ADMIN as override, no new role"): any
authenticated role can create a draft campaign or preview an audience; only MARKETING or
ADMIN can activate one (the moment it actually "sends"), complete it, or cancel someone
else's. A creator can cancel their own draft. If a campaign has a linked_asset_id, that
asset must be 'approved' before the campaign can activate -- the concrete link between
this module and last session's asset design/approval workflow.
"""

from core.campaigns import (
    list_campaign_types,
    get_campaign_type,
    list_channels,
    preview_audience,
    create_campaign,
    get_campaign,
    activate_campaign,
    complete_campaign,
    cancel_campaign,
    list_campaigns,
    list_pending_campaigns,
    update_campaign,
    get_campaign_members,
    get_campaign_stats,
    duplicate_campaign,
    bulk_create_campaigns,
    create_recurring_schedule,
    list_recurring_schedules,
    get_recurring_schedule as _get_recurring_schedule_public,
    set_recurring_schedule_active,
    delete_recurring_schedule,
    run_due_recurring_schedules,
    RECURRING_CADENCES,
)
from core.assets import get_asset
from core.email_templates import get_template
from core.permissions import ADMIN, MARKETING
from core.audit import audit_log
from core.audit_storage import save_audit_log
from core.storage_paths import AUDIT_PATH
from core.compliance import enforce_gate


def _serialize_campaign(entity):

    return {
        "id": entity.id,
        **entity.attributes,
    }


def _can_activate(role):
    return role == ADMIN or role == MARKETING


def list_campaign_types_api():
    return list_campaign_types()


def list_channels_api():
    return list_channels()


def preview_audience_api(campaign_type_key, params):

    template = get_campaign_type(campaign_type_key)

    if not template:
        return {"error": f"Unknown campaign type '{campaign_type_key}'"}

    return preview_audience(campaign_type_key, params or {})


def create_campaign_api(employee_id, campaign_type_key, name, channel, params, linked_asset_id=None, linked_template_id=None):

    template = get_campaign_type(campaign_type_key)

    if not template:
        return {"error": f"Unknown campaign type '{campaign_type_key}'"}

    missing = [
        f["key"]
        for f in template["audience_fields"]
        if f.get("required") and not (params or {}).get(f["key"])
    ]

    if missing:
        return {"error": f"Missing required audience field(s): {', '.join(missing)}"}

    if linked_asset_id and not get_asset(linked_asset_id):
        return {"error": f"Linked asset '{linked_asset_id}' not found"}

    resolved_channel = channel or template["default_channel"]

    if linked_template_id:

        message_template = get_template(linked_template_id)

        if not message_template:
            return {"error": f"Linked template '{linked_template_id}' not found"}

        if message_template.attributes.get("channel") != resolved_channel:
            return {
                "error": (
                    f"Linked template '{linked_template_id}' is a "
                    f"{message_template.attributes.get('channel')} template, but this "
                    f"campaign's channel is '{resolved_channel}'"
                )
            }

    entity = create_campaign(
        campaign_type_key,
        name,
        resolved_channel,
        employee_id,
        params or {},
        linked_asset_id,
        linked_template_id,
    )

    # Scoped to "individual" only, not every campaign type -- a 0-count audience is a
    # real (if unusual) outcome for a segment-based campaign type against sparse data,
    # but for "individual" it almost always means a bad/missing target_id, so it's
    # worth a clear error rather than silently creating a campaign with nobody to send
    # to (session 79).
    if campaign_type_key == "individual" and entity.attributes.get("audience_count", 0) == 0:
        return {"error": f"'{(params or {}).get('target_id')}' is not a valid Customer or Lead id."}

    return _serialize_campaign(entity)


def get_campaign_api(role, employee_id, campaign_id):

    campaign = get_campaign(campaign_id)

    if not campaign:
        return {"error": "Campaign not found"}

    if campaign.attributes.get("created_by") != employee_id and not _can_activate(role):
        return {"error": "You don't have access to this campaign"}

    return _serialize_campaign(campaign)


def list_my_campaigns_api(employee_id):
    return [_serialize_campaign(c) for c in list_campaigns(created_by=employee_id)]


def list_pending_campaigns_api(role):

    if not _can_activate(role):
        return {"error": "You don't have access to the campaign activation queue"}

    return [_serialize_campaign(c) for c in list_pending_campaigns()]


def activate_campaign_api(role, employee_id, campaign_id):

    if not _can_activate(role):
        return {"error": "You don't have access to activate campaigns"}

    campaign = get_campaign(campaign_id)

    if not campaign:
        return {"error": "Campaign not found"}

    if campaign.attributes.get("status") != "draft":
        return {"error": f"Campaign is '{campaign.attributes.get('status')}', not a draft"}

    linked_asset_id = campaign.attributes.get("linked_asset_id")

    if linked_asset_id:

        asset = get_asset(linked_asset_id)

        if not asset:
            return {"error": f"Linked asset '{linked_asset_id}' not found"}

        if asset.attributes.get("status") != "approved":
            return {"error": f"Linked asset '{linked_asset_id}' must be approved before this campaign can activate (currently '{asset.attributes.get('status')}')"}

    # Compliance agent (session 38) -- CAN-SPAM/TCPA consent check runs on every
    # marketing push before it activates (sends). Sam: "it needs to run through every
    # sale, marketing push, etc."
    gate = enforce_gate("campaign_activate", campaign)

    if gate["blocked"]:
        return {
            "error": "Compliance check failed -- this campaign can't send until the issue(s) below are corrected.",
            "compliance_alert_id": gate["alert_id"],
            "compliance_violations": gate["violations"],
            "notice": gate["notice"],
        }

    updated = activate_campaign(campaign_id)

    audit_log.record(
        event_type="campaign_activated",
        summary=f"Campaign {campaign_id} activated by {employee_id}",
        entity_id=campaign_id,
        actor=employee_id,
        details={"campaign_type": updated.attributes.get("campaign_type"), "audience_count": updated.attributes.get("audience_count")},
    )
    save_audit_log(AUDIT_PATH)

    return _serialize_campaign(updated)


def complete_campaign_api(role, employee_id, campaign_id):

    if not _can_activate(role):
        return {"error": "You don't have access to complete campaigns"}

    campaign = get_campaign(campaign_id)

    if not campaign:
        return {"error": "Campaign not found"}

    if campaign.attributes.get("status") != "active":
        return {"error": f"Campaign is '{campaign.attributes.get('status')}', not active"}

    updated = complete_campaign(campaign_id)

    return _serialize_campaign(updated)


def update_campaign_api(role, employee_id, campaign_id, patch):
    """Session 82 -- Sam: "the campaigns should be editable." Same ownership rule as
    cancel_campaign_api below: the creator, or MARKETING/ADMIN, can edit."""

    campaign = get_campaign(campaign_id)

    if not campaign:
        return {"error": "Campaign not found"}

    if campaign.attributes.get("created_by") != employee_id and not _can_activate(role):
        return {"error": "Only the creator (or marketing/admin) can edit this campaign"}

    updated = update_campaign(campaign_id, patch or {})

    return _serialize_campaign(updated)


def get_campaign_detail_api(role, employee_id, campaign_id, page=1, page_size=25, entity_type_filter=None):
    """Session 82 -- Sam: "when you click on [a campaign] they should show the list of
    people, all the information that has been included as well as active measurements /
    analytics." One composed response: the campaign itself, its real stats, its
    paginated real audience, and the linked message template if one is attached. Same
    view-access rule as get_campaign_api (creator, or MARKETING/ADMIN)."""

    campaign = get_campaign(campaign_id)

    if not campaign:
        return {"error": "Campaign not found"}

    if campaign.attributes.get("created_by") != employee_id and not _can_activate(role):
        return {"error": "You don't have access to this campaign"}

    linked_template = None
    template_id = campaign.attributes.get("linked_template_id")

    if template_id:

        message_template = get_template(template_id)

        if message_template:
            linked_template = {
                "id": message_template.id,
                "name": message_template.attributes.get("name"),
                "channel": message_template.attributes.get("channel"),
                "subject": message_template.attributes.get("subject"),
            }

    return {
        "campaign": _serialize_campaign(campaign),
        "stats": get_campaign_stats(campaign_id),
        "members": get_campaign_members(campaign_id, page, page_size, entity_type_filter),
        "linked_template": linked_template,
    }


def cancel_campaign_api(role, employee_id, campaign_id):

    campaign = get_campaign(campaign_id)

    if not campaign:
        return {"error": "Campaign not found"}

    if campaign.attributes.get("created_by") != employee_id and not _can_activate(role):
        return {"error": "Only the creator (or marketing/admin) can cancel this campaign"}

    if campaign.attributes.get("status") not in ("draft", "active"):
        return {"error": f"Campaign is already '{campaign.attributes.get('status')}'"}

    updated = cancel_campaign(campaign_id)

    return _serialize_campaign(updated)


# ---------------------------------------------------------------------------
# Bumper-parity campaign tooling (2026-07-25): Duplication Station, Multi-Planner,
# Recurring Schedule. Same role posture as the rest of this module -- any authed role
# can create a DRAFT (duplicate, bulk-create, set up a schedule), but anything that
# actually SENDS (activating a run) is MARKETING/ADMIN only, mirroring _can_activate.
# ---------------------------------------------------------------------------


def _serialize_schedule(entity):
    return {"id": entity.id, **entity.attributes}


def duplicate_campaign_api(role, employee_id, campaign_id, new_name=None):
    """Duplication Station -- clone a campaign into a fresh draft. The clone is a draft,
    so nothing sends until someone activates it, but you can only copy a campaign you
    were allowed to open -- same view rule as get_campaign_api (creator, or
    MARKETING/ADMIN)."""
    original = get_campaign(campaign_id)

    if not original:
        return {"error": "Campaign not found"}

    if original.attributes.get("created_by") != employee_id and not _can_activate(role):
        return {"error": "You don't have access to this campaign"}

    result = duplicate_campaign(campaign_id, employee_id, new_name=new_name)

    if isinstance(result, dict) and result.get("error"):
        return result

    return _serialize_campaign(result)


def bulk_create_campaigns_api(employee_id, specs):
    """Multi-Planner -- create several draft campaigns at once. Drafts only; nothing
    sends here, so any authed role may plan. Each row is validated independently."""
    if not isinstance(specs, list) or not specs:
        return {"error": "specs must be a non-empty list of campaign rows"}

    return bulk_create_campaigns(specs, employee_id)


def create_recurring_schedule_api(employee_id, base_campaign_id, cadence, start_date, end_date=None, interval=1, name=None):
    """Set up a recurring cadence off a base campaign. Setting up the schedule produces
    no sends by itself (each run is activated only when run_due... fires), so any authed
    role may create one, but only over a campaign they're allowed to see."""
    base = get_campaign(base_campaign_id)

    if not base:
        return {"error": "Base campaign not found"}

    if base.attributes.get("created_by") != employee_id:
        # A schedule that fires the base repeatedly is a send-class setup over someone
        # else's campaign -- keep that to MARKETING/ADMIN, consistent with activation.
        return {"error": "Only the base campaign's creator (or marketing/admin) can schedule it"}

    result = create_recurring_schedule(
        base_campaign_id, cadence, start_date, employee_id, end_date=end_date, interval=interval, name=name
    )

    if isinstance(result, dict) and result.get("error"):
        return result

    return _serialize_schedule(result)


def list_recurring_schedules_api(active_only=False):
    return [_serialize_schedule(s) for s in list_recurring_schedules(active_only=active_only)]


def get_recurring_schedule_api(schedule_id):
    sched = _get_recurring_schedule_public(schedule_id)

    if not sched:
        return {"error": "Recurring schedule not found"}

    return _serialize_schedule(sched)


def set_recurring_schedule_active_api(role, employee_id, schedule_id, active):
    """Pause/resume. Resuming a schedule re-arms real sends, so MARKETING/ADMIN only."""
    if not _can_activate(role):
        return {"error": "You don't have access to pause or resume schedules"}

    result = set_recurring_schedule_active(schedule_id, active)

    if isinstance(result, dict) and result.get("error"):
        return result

    return _serialize_schedule(result)


def delete_recurring_schedule_api(role, employee_id, schedule_id):
    if not _can_activate(role):
        return {"error": "You don't have access to stop schedules"}

    return delete_recurring_schedule(schedule_id)


def send_campaign_api(role, employee_id, campaign_id, resend=False):
    """Track B: run the real per-recipient delivery pipeline for a campaign (through the
    provider seam). Sending is the activation-class action, so MARKETING/ADMIN only."""
    if not _can_activate(role):
        return {"error": "You don't have access to send campaigns"}

    from core.message_delivery import deliver_campaign

    campaign = get_campaign(campaign_id)
    if not campaign:
        return {"error": "Campaign not found"}

    result = deliver_campaign(campaign_id, actor=employee_id, resend=resend)

    if isinstance(result, dict) and result.get("error"):
        return result

    audit_log.record(
        event_type="campaign_sent",
        summary=f"Campaign {campaign_id} delivered by {employee_id} ({result.get('mode')}): {result.get('delivered')} to {result.get('total_recipients')}",
        entity_id=campaign_id,
        actor=employee_id,
        details={"mode": result.get("mode"), "delivered": result.get("delivered")},
    )
    save_audit_log(AUDIT_PATH)
    return result


def get_campaign_delivery_api(role, employee_id, campaign_id):
    """Real per-recipient delivery stats (from the MessageSend log). Same view rule as
    get_campaign_api (creator, or MARKETING/ADMIN)."""
    campaign = get_campaign(campaign_id)
    if not campaign:
        return {"error": "Campaign not found"}
    if campaign.attributes.get("created_by") != employee_id and not _can_activate(role):
        return {"error": "You don't have access to this campaign"}

    from core.message_delivery import get_delivery_stats

    return get_delivery_stats(campaign_id)


def run_due_recurring_schedules_api(role, employee_id, today=None):
    """Fire every due schedule (each due run clones + activates the base campaign). This
    is the send-class action in the trio, so MARKETING/ADMIN only, matching activate."""
    if not _can_activate(role):
        return {"error": "You don't have access to run recurring schedules"}

    result = run_due_recurring_schedules(today=today)

    audit_log.record(
        event_type="recurring_schedules_run",
        summary=f"Recurring schedules run by {employee_id}: {result['launched_count']} launched",
        entity_id=None,
        actor=employee_id,
        details={"launched_count": result["launched_count"], "errors": result["errors"]},
    )
    save_audit_log(AUDIT_PATH)

    return result
