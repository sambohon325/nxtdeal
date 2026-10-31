"""Unified Communications Hub (2026-07-21). Sam's own gap-analysis of a
competitor sales deck flagged "Communications Platform" as NXTDeal's single
biggest missing area: "Calling, Texting, Recording, Notes, Conversation
History with: Recording, Transcription, AI Analysis, Coaching, Automation."

core/unified_communications.py (session 19, backing Operations' existing
"Communications" Top Menu item) already composes a real, read-only feed over
three siloed FieldNote-backed logs (Sales' _unified_inbox, Service's RO
Communication Center, Finance's Collections contact log) -- but FieldNote's
own generic {department, category, body, linked_entity_id} shape has no room
for a real per-call recording/transcription/sentiment/follow-up/AI-summary
record without breaking every existing FieldNote consumer across this
codebase. This module is deliberately a NEW, first-class entity
(entity_types.COMMUNICATION, id prefix "COMM") rather than a FieldNote or a
dict on something else -- many real communications accumulate per Lead/
Customer/Deal/ServiceRecord/FinanceContract over time, each with its own
real channel/direction/duration/transcript/sentiment/follow-up/AI-summary
state, the same "own lifecycle" reasoning OperationsTask/DamageReport/
Payment/AutomationExecution/MarketingContentDraft/PerformanceReview already
established in this codebase.

Honest real-vs-simulated split, matching session 110's disclosure
convention: logging that a call/text/email/chat/social touch happened is
100% real (a genuine employee action, timestamped, persisted). Phone-call
Recording/Transcription/Sentiment are honestly SIMULATED -- no telephony/
call-recording vendor (Twilio, RingCentral, CallRail, etc.) is connected
anywhere in this codebase -- deterministically seeded per communication id
(hashlib.sha256, the same convention core/pricing_desk.py/core/
acquisitions.py already established) so the same call always reads the
same, not fresh noise on every fetch. Every simulated field carries a real
`basis` label plus an explicit disclaimer, never presented as real. Text/
email/chat/social entries have no recording/transcript/sentiment at all --
those channels are never phone calls, so nothing is fabricated for them.

The AI Summary is genuinely real: an isolated, kill-switched OpenAI call
following core/email_wizard.py's own established isolated-wizard-with-
fallback pattern exactly (a dedicated, no-tool-calling client, an
is_feature_enabled()/record_call_attempt() gate, a try/except around the
real API call, and an honest, non-AI fallback_summary() for when the call
can't be reached -- this sandbox has consistently shown no outbound OpenAI
network access across many prior sessions, so the fallback path is what
actually fires here today).

Deliberately COMPOSES WITH, not replaces, core/unified_communications.py:
get_communications_hub_overview() merges this module's own richer
Communication entities with that module's existing Sales/Service/Finance
FieldNote-backed feed into one real view, rather than a second, disconnected
communications screen. Sales' OWN, separate "communications" Top Menu item
(core/sales_menu.py's communications(), components/CommunicationsBoard.tsx)
is untouched -- this module backs Operations' existing "Communications" Top
Menu item alongside (not in place of) core/unified_communications.py's own
feed.

Follows the per-call save_graph() convention core/lead_tasks.py/
core/field_notes.py/core/website_chat.py already established for low/
moderate-frequency, human-driven mutations (not the batched-loop
convention used for high-frequency bulk actions elsewhere in this
codebase) -- logging a communication is a single human action, not a bulk
job, so a direct save on every mutating call is the right, safe choice.
"""

import hashlib
import re
from datetime import datetime, timezone

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import COMMUNICATION
from core.id_generator import IDGenerator
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH

id_generator = IDGenerator()

CHANNELS = ["phone", "text", "email", "chat", "social"]
DIRECTIONS = ["inbound", "outbound"]

SENTIMENT_LABELS = ["positive", "neutral", "negative"]

RECORDING_BASIS = "simulated_call_recording"
RECORDING_DISCLAIMER = (
    "SIMULATED -- no telephony/call-recording vendor (e.g. Twilio, "
    "RingCentral, CallRail) is connected in this environment. This "
    "recording/transcript/sentiment is a deterministic placeholder for "
    "demonstration purposes only, never a real captured call."
)


def _now():

    return datetime.now(timezone.utc).isoformat()


def _seed_int(comm_id, salt, mod):
    """Deterministic per-communication pseudo-random int, same convention
    core/pricing_desk.py/core/acquisitions.py already established -- the
    same communication id always resolves to the same simulated value."""

    digest = hashlib.sha256(f"{comm_id}:{salt}".encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % mod


def _simulate_call_recording(comm_id, duration_seconds):
    """Honest, disclosed simulation of a phone call's recording URL/
    transcript/sentiment -- never a real captured recording. Deterministic
    per comm_id so repeat fetches of the same communication read
    identically."""

    duration = duration_seconds if duration_seconds and duration_seconds > 0 else (
        30 + _seed_int(comm_id, "duration", 600)
    )

    sentiment_score = _seed_int(comm_id, "sentiment", 101) / 100.0
    if sentiment_score >= 0.66:
        sentiment_label = "positive"
    elif sentiment_score >= 0.33:
        sentiment_label = "neutral"
    else:
        sentiment_label = "negative"

    transcript_snippets = [
        "Thanks for calling in -- let me pull up your account.",
        "I can check on that for you right now.",
        "We have a few options that might work for your situation.",
        "Let me get that scheduled and I'll follow up with a confirmation.",
        "Is there anything else I can help you with today?",
    ]
    snippet_count = 2 + _seed_int(comm_id, "snippets", 3)
    transcript_text = " ".join(
        transcript_snippets[i % len(transcript_snippets)]
        for i in range(snippet_count)
    )

    return {
        "basis": RECORDING_BASIS,
        "disclaimer": RECORDING_DISCLAIMER,
        "duration_seconds": duration,
        "recording_url": f"https://simulated-recordings.example/{comm_id}.mp3",
        "transcript": transcript_text,
        "sentiment_score": round(sentiment_score, 2),
        "sentiment_label": sentiment_label,
    }


def _comm_brief(comm):

    attrs = comm.attributes

    brief = {
        "id": comm.id,
        "channel": attrs.get("channel"),
        "direction": attrs.get("direction"),
        "department": attrs.get("department"),
        "body": attrs.get("body"),
        "linked_entity_id": attrs.get("linked_entity_id"),
        "created_by": attrs.get("created_by"),
        "created_at": attrs.get("created_at"),
        "duration_seconds": attrs.get("duration_seconds"),
        "follow_up": attrs.get("follow_up"),
        "ai_summary": attrs.get("ai_summary"),
    }

    if attrs.get("channel") == "phone":
        brief["recording"] = attrs.get("recording")
    else:
        brief["recording"] = None

    return brief


def log_communication(
    department,
    channel,
    direction,
    body,
    created_by,
    linked_entity_id=None,
    duration_seconds=None,
    follow_up_required=False,
    follow_up_due_at=None,
    follow_up_note=None,
    skip_recording_simulation=False,
):
    """Logs a real, first-class Communication. Returns (comm_dict, error).

    channel must be one of CHANNELS; direction must be one of DIRECTIONS.
    Phone-channel entries get an honestly-simulated recording/transcript/
    sentiment block (see _simulate_call_recording's own disclosure) --
    every other channel gets recording=None, nothing fabricated.

    follow_up_required=True creates a real, embedded follow-up dict
    (due_at/completed/completed_at/completed_by/note) on the communication
    itself, modeled on core/lead_tasks.py's own due_at/completed/
    completed_at/completed_by shape but embedded rather than a separate
    entity, since a communication's own follow-up is a property of that
    one touch, not an independent unit of work accumulating its own
    history.

    skip_recording_simulation=True (added for core/call_center.py, Phase 2's
    Voice build) skips the phone-channel recording simulation entirely --
    for a call that was never actually answered (missed) or that only
    produced a one-way voicemail message, fabricating a two-way
    "conversation transcript" via _simulate_call_recording() would
    misrepresent what happened. Default False preserves every existing
    caller's behavior unchanged."""

    if channel not in CHANNELS:
        return None, f"Invalid channel '{channel}'. Must be one of: {', '.join(CHANNELS)}."

    if direction not in DIRECTIONS:
        return None, f"Invalid direction '{direction}'. Must be one of: {', '.join(DIRECTIONS)}."

    if not body or not str(body).strip():
        return None, "A communication must have a non-empty body/summary."

    comm_id = id_generator.generate("COMM")
    now = _now()

    attributes = {
        "department": department,
        "channel": channel,
        "direction": direction,
        "body": body,
        "linked_entity_id": linked_entity_id,
        "created_by": created_by,
        "created_at": now,
        "duration_seconds": duration_seconds,
        "follow_up": None,
        "ai_summary": None,
        "recording": None,
    }

    if channel == "phone" and not skip_recording_simulation:
        attributes["recording"] = _simulate_call_recording(comm_id, duration_seconds)
        if not duration_seconds:
            attributes["duration_seconds"] = attributes["recording"]["duration_seconds"]

    if follow_up_required:
        attributes["follow_up"] = {
            "required": True,
            "due_at": follow_up_due_at,
            "completed": False,
            "completed_at": None,
            "completed_by": None,
            "note": follow_up_note,
        }

    comm = Entity(id=comm_id, entity_type=COMMUNICATION, attributes=attributes)
    ledger.add_entity(comm)
    save_graph(GRAPH_PATH)

    return _comm_brief(comm), None


def get_communication(comm_id):

    comm = ledger.get_entity(comm_id)
    if not comm or comm.entity_type != COMMUNICATION:
        return None, f"No communication found with id {comm_id}."

    return _comm_brief(comm), None


def list_communications(
    department=None,
    channel=None,
    linked_entity_id=None,
    follow_up_pending_only=False,
    limit=200,
):
    """Real, filterable list of every logged Communication, most-recent-
    first. follow_up_pending_only=True restricts to communications with a
    real, still-open follow_up (required=True, completed=False)."""

    results = []
    for entity in ledger.entities.values():
        if entity.entity_type != COMMUNICATION:
            continue

        attrs = entity.attributes

        if department and attrs.get("department") != department:
            continue

        if channel and attrs.get("channel") != channel:
            continue

        if linked_entity_id and attrs.get("linked_entity_id") != linked_entity_id:
            continue

        if follow_up_pending_only:
            follow_up = attrs.get("follow_up") or {}
            if not (follow_up.get("required") and not follow_up.get("completed")):
                continue

        results.append(entity)

    results.sort(key=lambda e: e.attributes.get("created_at") or "", reverse=True)

    return [_comm_brief(c) for c in results[:limit]]


def complete_follow_up(comm_id, completed_by):

    comm = ledger.get_entity(comm_id)
    if not comm or comm.entity_type != COMMUNICATION:
        return None, f"No communication found with id {comm_id}."

    follow_up = comm.attributes.get("follow_up")
    if not follow_up or not follow_up.get("required"):
        return None, "This communication has no follow-up to complete."

    if follow_up.get("completed"):
        return None, "This communication's follow-up is already completed."

    follow_up["completed"] = True
    follow_up["completed_at"] = _now()
    follow_up["completed_by"] = completed_by
    comm.attributes["follow_up"] = follow_up

    save_graph(GRAPH_PATH)

    return _comm_brief(comm), None


def get_communications_stats(department=None):
    """Real, live-computed counts -- total, by channel, by direction, and
    the real count of still-open follow-ups."""

    all_comms = list_communications(department=department, limit=100000)

    by_channel = {c: 0 for c in CHANNELS}
    by_direction = {d: 0 for d in DIRECTIONS}
    open_follow_ups = 0
    phone_with_recording = 0

    for c in all_comms:
        if c["channel"] in by_channel:
            by_channel[c["channel"]] += 1
        if c["direction"] in by_direction:
            by_direction[c["direction"]] += 1

        follow_up = c.get("follow_up") or {}
        if follow_up.get("required") and not follow_up.get("completed"):
            open_follow_ups += 1

        if c["channel"] == "phone" and c.get("recording"):
            phone_with_recording += 1

    return {
        "total_communications": len(all_comms),
        "by_channel": by_channel,
        "by_direction": by_direction,
        "open_follow_ups": open_follow_ups,
        "phone_calls_with_simulated_recording": phone_with_recording,
        "recording_basis_note": RECORDING_DISCLAIMER,
    }


# ---------------------------------------------------------------------------
# AI Summary -- isolated, kill-switched OpenAI call, core/email_wizard.py's
# own established pattern exactly.
# ---------------------------------------------------------------------------

import json
import os

from dotenv import load_dotenv
from core.optional_ai_client import LazyOpenAI

from core.ai_management import is_feature_enabled, record_call_attempt

load_dotenv()

client = LazyOpenAI(
    api_key=os.getenv(
        "OPENAI_API_KEY"
    )
)

SUMMARY_SYSTEM_PROMPT = (
    "You are an assistant summarizing a single customer/prospect communication "
    "(a phone call, text, email, chat, or social message) for a dealership "
    "employee's own records. Given the channel, direction, and body/transcript "
    "of the communication, return ONLY a JSON object with exactly these keys: "
    "summary (2-3 short sentences, plain factual recap of what was discussed, "
    "never inventing a detail not present in the given text), "
    "key_points (a JSON array of up to 4 short strings, each a single concrete "
    "fact or commitment mentioned), "
    "suggested_follow_up (one short sentence describing a reasonable next "
    "action, or an empty string if none is warranted). Do not include any "
    "commentary outside the JSON object."
)


def _summary_user_content(comm):

    channel = comm.get("channel") or "communication"
    direction = comm.get("direction") or "unknown direction"
    body = comm.get("body") or ""
    transcript = ""
    if comm.get("recording"):
        transcript = comm["recording"].get("transcript") or ""

    content = f"Channel: {channel}\nDirection: {direction}\nBody/notes: {body}\n"
    if transcript:
        content += f"Transcript: {transcript}\n"

    return content


def generate_ai_summary(comm_id):
    """Real, isolated OpenAI call summarizing one logged communication.
    Returns (summary_dict, error). On success, the summary is stored back
    onto the communication's own ai_summary field and a real save_graph()
    call persists it -- on failure/disabled, returns an honest fallback
    summary (never stored, since it's not a real AI result) so the caller
    always has something usable.

    AI Management: checks the real 'communications_hub_summary' kill switch
    (core/ai_management.py, communications_hub_summary_enabled flag) before
    attempting."""

    comm, error = get_communication(comm_id)
    if error:
        return None, error

    if not is_feature_enabled("communications_hub_summary"):
        record_call_attempt("communications_hub_summary", "blocked")
        fallback = fallback_summary(comm)
        fallback["ai_generated"] = False
        fallback["disabled"] = True
        return fallback, None

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
                {"role": "user", "content": _summary_user_content(comm)},
            ],
            response_format={"type": "json_object"},
        )

        record_call_attempt("communications_hub_summary", "succeeded")
        parsed = json.loads(response.choices[0].message.content)
        parsed["ai_generated"] = True

        entity = ledger.get_entity(comm_id)
        entity.attributes["ai_summary"] = parsed
        save_graph(GRAPH_PATH)

        return parsed, None

    except Exception as exc:  # noqa: BLE001 -- any OpenAI/network/parse failure falls back, never raises
        record_call_attempt("communications_hub_summary", "fell_back", detail=str(exc))
        fallback = fallback_summary(comm)
        fallback["ai_generated"] = False
        fallback["fallback_reason"] = str(exc)
        return fallback, None


def fallback_summary(comm):
    """Plain, non-AI placeholder summary -- used when the AI call is
    disabled or fails, same pattern as core/email_wizard.py's
    fallback_copy()/core/website_wizard.py's fallback_copy()."""

    channel = comm.get("channel") or "communication"
    body = comm.get("body") or ""

    return {
        "summary": (
            f"A {channel} {comm.get('direction') or ''} was logged: "
            f"{body[:200]}"
        ).strip(),
        "key_points": [],
        "suggested_follow_up": "",
    }


# ---------------------------------------------------------------------------
# Composition with core/unified_communications.py -- extends, never
# replaces, that module's existing Sales/Service/Finance FieldNote feed.
# ---------------------------------------------------------------------------

def get_communications_hub_overview(role, department=None, channel=None):
    """The real, merged Communications Hub view: this module's own richer
    Communication entities (with recording/transcript/sentiment/follow-up/
    AI-summary) PLUS core/unified_communications.py's existing Sales/
    Service/Finance FieldNote-backed feed, composed into one payload --
    never a duplicate computation of that module's own aggregation logic."""

    from core.unified_communications import get_unified_communications_overview

    legacy_feed = get_unified_communications_overview(role, department=department, channel=channel)

    hub_stats = get_communications_stats(department=department)
    hub_recent = list_communications(department=department, channel=channel, limit=25)
    hub_open_follow_ups = list_communications(
        department=department, channel=channel, follow_up_pending_only=True, limit=50
    )

    return {
        "hub_stats": hub_stats,
        "hub_recent_communications": hub_recent,
        "hub_open_follow_ups": hub_open_follow_ups,
        "legacy_unified_feed": legacy_feed,
        "note": (
            "hub_* fields are this module's own first-class Communication "
            "log (real logging, simulated phone recording/transcript/"
            "sentiment, real AI summaries). legacy_unified_feed is "
            "core/unified_communications.py's existing Sales/Service/"
            "Finance FieldNote-backed aggregation, composed alongside "
            "rather than replaced."
        ),
    }
