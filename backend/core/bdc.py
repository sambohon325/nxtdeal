"""
core/bdc.py -- the BDC (Business Development Center) queue, the second of Sam's ~10
"completely missing" dealership workflows (Sam's own roster spec, BUILD_QUEUE.md
session 39, names "2 BDC/internet reps" as a distinct Sales seat). A BDC rep's job is
speed-to-lead on internet-sourced leads specifically -- distinct from the Up System's
floor traffic (core/up_system.py) and from core/lead_routing.py's general least-busy
assignment. No new entity type: this is a live filter + a real timing computation over
the existing Lead entities already in the graph (Source in {"Website","Autotrader"}),
same "compute live, don't duplicate" convention as core/trigger_alerts.py.
"""

from datetime import datetime, timezone

from core.dealeros import ledger
from core.entity_types import LEAD
from core.field_notes import list_field_notes
from core.lead_record import COMMUNICATION_CATEGORIES

INTERNET_SOURCES = ("Website", "Autotrader")

# A common real BDC SLA convention -- not a graph fact. Most dealership BDC
# scorecards target first contact within roughly 5-15 minutes; this codebase has no
# configured SLA setting, so these are hand-picked, honestly-labeled thresholds, not
# something read off the graph.
URGENT_MINUTES = 15
WARNING_MINUTES = 45


def _now():
    return datetime.now(timezone.utc)


def _parse(ts):

    if not ts:
        return None

    try:
        dt = datetime.fromisoformat(ts)
    except ValueError:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt


def _minutes_since(ts):

    dt = _parse(ts)

    if not dt:
        return None

    return round((_now() - dt).total_seconds() / 60, 1)


def _urgency(minutes):

    if minutes is None:
        return "unknown"

    if minutes >= WARNING_MINUTES:
        return "critical"

    if minutes >= URGENT_MINUTES:
        return "warning"

    return "ok"


def _internet_leads():

    return [
        e for e in ledger.get_all().values()
        if e.entity_type == LEAD and e.attributes.get("Source") in INTERNET_SOURCES
    ]


def _first_contact_at(lead_id):
    """The real timestamp of the first logged call/text/email/video against this
    lead -- the actual "time to first contact" signal, not a guess."""

    notes = list_field_notes(linked_entity_id=lead_id, limit=200)
    comms = [n for n in notes if n.attributes.get("category") in COMMUNICATION_CATEGORIES]

    if not comms:
        return None

    comms.sort(key=lambda n: n.attributes.get("created_at") or "")

    return comms[0].attributes.get("created_at")


def _lead_brief(lead):
    """CreatedAt (full ISO precision, session 100 follow-up) is only real for leads
    created since this session -- historical CSV-imported leads only ever had
    CreatedDate (date-only). Falls back honestly rather than fabricating precision
    that was never real, and says so via `precise_timestamp`."""

    precise = lead.attributes.get("CreatedAt")
    minutes = _minutes_since(precise) if precise else None

    return {
        "id": lead.id,
        "first_name": lead.attributes.get("FirstName"),
        "last_name": lead.attributes.get("LastName"),
        "source": lead.attributes.get("Source"),
        "pipeline_state": lead.attributes.get("PipelineState"),
        "created_date": lead.attributes.get("CreatedDate"),
        "minutes_since_created": minutes,
        "precise_timestamp": bool(precise),
        "urgency": _urgency(minutes) if precise else "unknown",
    }


def get_untouched_queue():
    """Internet leads still in PipelineState "NEW" -- nobody has advanced them past
    intake yet. Leads with a precise timestamp sort oldest-first (most overdue is
    most urgent); leads without one (historical imports) sort after, since there's no
    honest way to rank their urgency by minutes."""

    leads = [l for l in _internet_leads() if l.attributes.get("PipelineState") == "NEW"]
    briefs = [_lead_brief(l) for l in leads]

    briefs.sort(key=lambda b: (b["minutes_since_created"] is None, -(b["minutes_since_created"] or 0)))

    return briefs


def get_response_time_stats():
    """Real speed-to-lead: for internet leads with a precise CreatedAt that HAVE
    been contacted, the actual minutes between creation and the first logged
    communication -- a direct measurement off real timestamps, not an estimate."""

    leads = [l for l in _internet_leads() if l.attributes.get("CreatedAt")]
    response_minutes = []

    for lead in leads:
        first_contact = _first_contact_at(lead.id)

        if not first_contact:
            continue

        created = _parse(lead.attributes.get("CreatedAt"))
        contacted = _parse(first_contact)

        if not created or not contacted:
            continue

        delta = (contacted - created).total_seconds() / 60

        if delta >= 0:
            response_minutes.append(delta)

    if not response_minutes:
        return {"sample_size": 0, "average_minutes": None, "under_target_pct": None}

    avg = sum(response_minutes) / len(response_minutes)
    under_target = sum(1 for m in response_minutes if m <= URGENT_MINUTES)

    return {
        "sample_size": len(response_minutes),
        "average_minutes": round(avg, 1),
        "under_target_pct": round(100 * under_target / len(response_minutes), 1),
    }


def get_qualification_queue():
    """Session 102 follow-up (Sam: "the workflows... need to be a working process, not
    just a list") -- internet leads that have been contacted at least once (past NEW)
    but haven't reached an appointment yet. This is the BDC rep's actual middle step:
    qualifying interest/budget/timeline before handing off to the floor, distinct from
    the untouched queue (nobody's tried yet) and the handoff candidates (already
    qualified, waiting on a floor rep)."""

    leads = [l for l in _internet_leads() if l.attributes.get("PipelineState") == "CONTACTED"]

    return [_lead_brief(l) for l in leads]


def get_handoff_candidates():
    """Internet leads qualified enough to hand to a floor closer -- an appointment is
    set or they've already visited, but ownership hasn't moved from BDC to a floor
    salesperson yet. The actual transfer reuses core/lead_assignment.py's real
    transfer_lead() (session 94) -- no parallel handoff mechanism."""

    leads = [
        l for l in _internet_leads()
        if l.attributes.get("PipelineState") in ("APPOINTMENT_SET", "VISITED")
    ]

    return [_lead_brief(l) for l in leads]


def get_bdc_dashboard():

    queue = get_untouched_queue()
    stats = get_response_time_stats()

    return {
        "untouched_queue": {"count": len(queue), "leads": queue},
        "response_time": stats,
        "sla_thresholds": {"urgent_minutes": URGENT_MINUTES, "warning_minutes": WARNING_MINUTES},
        "internet_sources": list(INTERNET_SOURCES),
        "not_yet_tracked": {
            "chat_transcripts": "No live-chat-to-BDC handoff model exists beyond core/website_chat.py's dealer-facing session view.",
            "outbound_dialer_integration": "No telephony/dialer integration exists in this codebase.",
        },
    }
