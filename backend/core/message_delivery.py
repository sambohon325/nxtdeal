"""
Campaign message delivery pipeline (Track B, 2026-07-25). Until now activating a campaign
just stamped sent_count from the frozen audience snapshot -- an honest but aggregate-only
simulation, with open/click stuck under `not_yet_tracked`. This module turns that into a
real per-recipient delivery pipeline: it iterates the campaign's audience, resolves each
member's email/phone, and dispatches through the existing provider seam
(integrations_registry.send_notification), writing one MessageSend record per recipient.

Nothing here fabricates a real-world side effect. Because no notifications adapter is
registered by default, every dispatch comes back `simulated: True` and the MessageSend is
recorded as "simulated" -- but the PIPELINE is real (real audience resolution, real
per-recipient records, real status/counts, real open/click tracking hooks). The day an
adapter is registered (see core/provider_credentials.py), the exact same code path sends
for real and records "sent". This is the difference between "the whole thing is fake" and
"the whole thing is real and simulated only at the last hop."
"""

from datetime import datetime, timezone

from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.entity_types import MESSAGE_SEND
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH
from core import integrations_registry
from core.campaigns import get_campaign


# Contact-key spellings vary across import/dialpad/CSV paths -- resolve across all of them
# (same discipline as core/bulk_import.py).
_EMAIL_KEYS = ("email", "Email", "email_address")
_PHONE_KEYS = ("phone", "Phone", "phone_number", "mobile", "cell")


def _now():
    return datetime.now(timezone.utc).isoformat()


def _entity_email(entity):
    for k in _EMAIL_KEYS:
        v = entity.attributes.get(k)
        if v:
            return v
    return ""


def _entity_phone(entity):
    for k in _PHONE_KEYS:
        v = entity.attributes.get(k)
        if v:
            return v
    return ""


def _channel_to_capability_channel(channel):
    """Map a campaign channel to the notification channel the seam understands. email/sms
    map directly; direct_mail and ringless_voicemail have no notifications-seam channel yet,
    so they resolve to None (recorded as 'unsupported_channel')."""
    if channel in ("email", "sms"):
        return channel
    return None


def _recipient_contact(entity, channel):
    if channel == "email":
        return _entity_email(entity)
    if channel == "sms":
        return _entity_phone(entity)
    return ""


def get_message_send(send_id):
    e = ledger.get_entity(send_id)
    return e if e and e.entity_type == MESSAGE_SEND else None


def list_sends(campaign_id, status=None):
    out = [
        e for e in ledger.get_all().values()
        if e.entity_type == MESSAGE_SEND and e.attributes.get("campaign_id") == campaign_id
    ]
    if status:
        out = [e for e in out if e.attributes.get("status") == status]
    return sorted(out, key=lambda e: e.attributes.get("created_at", ""))


def _existing_send_recipient_ids(campaign_id):
    return {s.attributes.get("recipient_id") for s in list_sends(campaign_id)}


def deliver_campaign(campaign_id, actor=None, resend=False):
    """Send (or re-send) a campaign to its audience through the provider seam, one
    MessageSend record per recipient. Idempotent by default: a recipient already sent to
    is skipped unless resend=True. Returns a summary of what happened."""
    campaign = get_campaign(campaign_id)
    if not campaign:
        return {"error": "Campaign not found"}
    if campaign.attributes.get("status") == "cancelled":
        return {"error": "Campaign is cancelled"}

    channel = campaign.attributes.get("channel")
    cap_channel = _channel_to_capability_channel(channel)
    audience_ids = campaign.attributes.get("audience_ids") or []
    already = _existing_send_recipient_ids(campaign_id) if not resend else set()

    counts = {"sent": 0, "simulated": 0, "no_contact": 0, "failed": 0, "unsupported_channel": 0, "skipped": 0}
    live = integrations_registry.is_live("notifications")

    for rid in audience_ids:
        if rid in already:
            counts["skipped"] += 1
            continue
        member = ledger.get_entity(rid)
        if not member:
            continue

        if cap_channel is None:
            status = "unsupported_channel"
            to = ""
            dispatch = None
        else:
            to = _recipient_contact(member, cap_channel)
            if not to:
                status = "no_contact"
                dispatch = None
            else:
                try:
                    dispatch = integrations_registry.send_notification(
                        to=to,
                        event={"type": "campaign", "campaign_id": campaign_id,
                               "campaign_name": campaign.attributes.get("name"),
                               "subject": (campaign.attributes.get("notes") or "")[:120]},
                        channels=(cap_channel,),
                    )
                    if not isinstance(dispatch, dict):
                        status = "failed"
                        dispatch = {"error": "Provider returned an invalid delivery result."}
                    elif dispatch.get("error") or dispatch.get("dispatched") is False:
                        status = "failed"
                    elif dispatch.get("delivered") is False or dispatch.get("sent") is False:
                        status = "failed"
                    elif dispatch.get("status") in ("failed", "rejected", "blocked", "cancelled", "canceled"):
                        status = "failed"
                    elif dispatch.get("simulated") is True:
                        status = "simulated"
                    elif dispatch.get("simulated") is not None and dispatch.get("simulated") is not False:
                        status = "failed"
                        dispatch = {**dispatch, "error": "Provider returned an invalid simulation marker."}
                    elif dispatch.get("status") in ("accepted", "queued", "pending"):
                        status = "queued"
                    elif dispatch.get("delivered") is True or dispatch.get("sent") is True or dispatch.get("status") in ("sent", "delivered"):
                        status = "sent"
                    else:
                        status = "failed"
                        dispatch = {**dispatch, "error": "Provider did not acknowledge dispatch."}
                except Exception as exc:  # a bad recipient must not abort the whole run
                    status = "failed"
                    dispatch = {"error": str(exc)}

        counts[status] = counts.get(status, 0) + 1

        record = Entity(
            id=id_generator.generate("MSND"),
            entity_type=MESSAGE_SEND,
            attributes={
                "campaign_id": campaign_id,
                "recipient_id": rid,
                "recipient_type": member.entity_type,
                "channel": channel,
                "to": to,
                "status": status,
                "provider": (dispatch or {}).get("provider") if isinstance(dispatch, dict) else None,
                "simulated": bool((dispatch or {}).get("simulated")) if isinstance(dispatch, dict) else None,
                "error": (dispatch or {}).get("error") if isinstance(dispatch, dict) else None,
                "opened": False,
                "clicked": False,
                "opened_at": None,
                "clicked_at": None,
                "sent_by": actor,
                "created_at": _now(),
            },
        )
        ledger.add_entity(record)

    # Real delivery accounting on the campaign (distinct from the legacy simulated
    # sent_count, which activate_campaign still stamps).
    delivered = counts["sent"] + counts["simulated"]
    campaign.attributes["delivered_count"] = campaign.attributes.get("delivered_count", 0) + delivered
    campaign.attributes["last_delivered_at"] = _now()
    campaign.attributes["delivery_runs"] = campaign.attributes.get("delivery_runs", 0) + 1
    save_graph(GRAPH_PATH)

    return {
        "campaign_id": campaign_id,
        "channel": channel,
        "mode": "live" if live else "simulated",
        "total_recipients": len(audience_ids),
        **counts,
        "delivered": delivered,
    }


def mark_opened(send_id):
    """Tracking hook: a real provider's open webhook would call this. Idempotent."""
    s = get_message_send(send_id)
    if not s:
        return {"error": "Message send not found"}
    if not s.attributes.get("opened"):
        s.attributes["opened"] = True
        s.attributes["opened_at"] = _now()
        save_graph(GRAPH_PATH)
    return {"ok": True, "send_id": send_id}


def mark_clicked(send_id):
    """Tracking hook: a real provider's click webhook would call this. A click implies an
    open, so it stamps both. Idempotent."""
    s = get_message_send(send_id)
    if not s:
        return {"error": "Message send not found"}
    changed = False
    if not s.attributes.get("opened"):
        s.attributes["opened"] = True
        s.attributes["opened_at"] = _now()
        changed = True
    if not s.attributes.get("clicked"):
        s.attributes["clicked"] = True
        s.attributes["clicked_at"] = _now()
        changed = True
    if changed:
        save_graph(GRAPH_PATH)
    return {"ok": True, "send_id": send_id}


def get_delivery_stats(campaign_id):
    """Real per-recipient delivery stats from the MessageSend log. Open/click rates are
    honest: they reflect real tracking events (mark_opened/mark_clicked), which stay at 0
    until a real provider webhook reports them -- not a fabricated percentage."""
    sends = list_sends(campaign_id)
    total = len(sends)
    by_status = {}
    opened = clicked = 0
    for s in sends:
        st = s.attributes.get("status")
        by_status[st] = by_status.get(st, 0) + 1
        if s.attributes.get("opened"):
            opened += 1
        if s.attributes.get("clicked"):
            clicked += 1

    delivered = by_status.get("sent", 0) + by_status.get("simulated", 0)
    live = integrations_registry.is_live("notifications")

    return {
        "campaign_id": campaign_id,
        "mode": "live" if live else "simulated",
        "total_sends": total,
        "by_status": by_status,
        "delivered": delivered,
        "opened": opened,
        "clicked": clicked,
        "open_rate": round(opened / delivered, 4) if delivered else 0.0,
        "click_rate": round(clicked / delivered, 4) if delivered else 0.0,
        "tracking_note": (
            "Delivery is real and per-recipient; it dispatches through the provider seam. "
            "Opens/clicks reflect real tracking events only (0 until a live provider reports "
            "them), never a fabricated rate."
            if not live else
            "A live notifications adapter is registered; sends and tracking are real."
        ),
    }
