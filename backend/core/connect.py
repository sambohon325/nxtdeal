"""
core/connect.py — NXTDeal Connect: the unified communications surface (2026-07-24).
Sam's spec: "NXTDeal Connect is the communications and customer engagement layer... manage
every customer interaction... Unified Inbox... Customer Timeline... Communications Analytics."

This is a pure READ / COMPOSE layer over the communications already logged as first-class
Communication entities by core/communications_hub.py (every channel: phone/text/email/chat/
social; calls synthesize a Communication via core/call_center.py; and — new this initiative
— every AI worker touch is logged here too via core/ai_worker.py). It introduces NO new
storage or entity type — same "compose the one graph, don't fork a parallel store"
convention as core/unified_communications.py. Its value-add over the raw list is three
things Connect needs: one filterable inbox across every channel, a per-entity timeline that
merges communications with the appointments booked off them, and an analytics rollup that
distinguishes AI-handled from human-handled touches and ties in the AI Workforce's own
tallies.
"""

from core.dealeros import ledger
from core.entity_types import APPOINTMENT
from core.communications_hub import (
    list_communications,
    get_communications_stats,
    CHANNELS,
)
from core.conversation_intelligence import analyze_brief, get_channel_intelligence

# An AI worker logs its touches as created_by "ai_worker:<role>" (see core/ai_worker.py).
_AI_PREFIX = "ai_worker:"


def _ai_role(created_by):
    cb = created_by or ""
    return cb[len(_AI_PREFIX):] if cb.startswith(_AI_PREFIX) else None


def _enrich(brief):
    """Add AI attribution and conversation intelligence (sentiment/score) to a communication
    brief without mutating the source."""
    role = _ai_role(brief.get("created_by"))
    return {
        **brief,
        "handled_by_ai": role is not None,
        "ai_worker_role": role,
        "intelligence": analyze_brief(brief),
    }


# ------------------------------------------------------------------------------------
# Unified inbox -- one filterable feed across every channel.
# ------------------------------------------------------------------------------------

def get_inbox(channel=None, direction=None, department=None,
              linked_entity_id=None, ai_only=False, limit=100):
    """Every logged communication across every channel, most-recent-first, each flagged
    with whether an AI worker handled it. Filterable by channel / direction / department /
    linked entity, and to AI-handled touches only."""

    comms = list_communications(
        department=department, channel=channel, linked_entity_id=linked_entity_id, limit=100000
    )
    feed = [_enrich(c) for c in comms]

    if direction:
        feed = [c for c in feed if c.get("direction") == direction]
    if ai_only:
        feed = [c for c in feed if c["handled_by_ai"]]

    total_matching = len(feed)
    return {
        "items": feed[:limit],
        "count": min(len(feed), limit),
        "total_matching": total_matching,
        "channels": list(CHANNELS),
        "note": "One inbox across every channel. AI-handled touches carry handled_by_ai "
                "and ai_worker_role; nothing is fabricated — this composes the logged "
                "Communication records.",
    }


# ------------------------------------------------------------------------------------
# Customer timeline -- communications + the appointments linked to the same entity.
# ------------------------------------------------------------------------------------

def _linked_appointments(entity_id):
    events = []
    for e in ledger.entities.values():
        if e.entity_type != APPOINTMENT:
            continue
        a = e.attributes
        if entity_id in (a.get("customer_id"), a.get("lead_id"),
                         a.get("vehicle_id"), a.get("linked_entity_id")):
            events.append({
                "kind": "appointment",
                "at": a.get("scheduled_start"),
                "channel": None,
                "direction": None,
                "handled_by_ai": str(a.get("created_by") or "").startswith(_AI_PREFIX),
                "summary": f"{a.get('appointment_type') or 'appointment'} "
                           f"({a.get('status') or 'scheduled'})",
                "ref_id": e.id,
            })
    return events


def get_customer_timeline(entity_id, limit=200):
    """A single chronological timeline for one customer/lead/vehicle: every communication
    linked to it, merged with the appointments booked for it, newest first."""

    events = []
    for c in list_communications(linked_entity_id=entity_id, limit=100000):
        e = _enrich(c)
        events.append({
            "kind": "communication",
            "at": e.get("created_at"),
            "channel": e.get("channel"),
            "direction": e.get("direction"),
            "handled_by_ai": e["handled_by_ai"],
            "ai_worker_role": e["ai_worker_role"],
            "sentiment": e["intelligence"]["sentiment"],
            "summary": e.get("ai_summary") or e.get("body"),
            "ref_id": e["id"],
        })

    events.extend(_linked_appointments(entity_id))
    events.sort(key=lambda ev: ev.get("at") or "", reverse=True)

    return {
        "entity_id": entity_id,
        "event_count": len(events),
        "events": events[:limit],
    }


# ------------------------------------------------------------------------------------
# Analytics -- channel/direction rollup + AI-vs-human attribution + workforce tallies.
# ------------------------------------------------------------------------------------

def get_analytics():
    stats = get_communications_stats()
    all_comms = list_communications(limit=100000)

    ai_by_role = {}
    ai_handled = 0
    for c in all_comms:
        role = _ai_role(c.get("created_by"))
        if role is not None:
            ai_handled += 1
            ai_by_role[role] = ai_by_role.get(role, 0) + 1

    from core.ai_worker import workforce_summary

    return {
        "communications": stats,
        "ai_handled": ai_handled,
        "human_handled": stats["total_communications"] - ai_handled,
        "ai_by_role": ai_by_role,
        "workforce": workforce_summary(),
        "intelligence": get_channel_intelligence(),
        "note": "ai_handled = communications logged by an AI worker; workforce = the AI "
                "Workforce's own executed/drafted tallies; intelligence = rules-based "
                "sentiment + conversation score across every channel.",
    }
