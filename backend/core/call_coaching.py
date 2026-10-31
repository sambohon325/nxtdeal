"""core/call_coaching.py -- Phase 2: Communications Platform, AI Voice Coaching +
BDC Center Call Scoring (2026-07-22). Sam's own kickoff named this feature twice,
under two different menu headings -- "AI Voice * ... Coaching ... Sentiment" and
"BDC Center * ... Coaching * Call Scoring * QA." Both are the same real signal
viewed from two audiences (an individual agent's own "AI Voice: Coaching" tab, a
BDC manager's team-wide "Call Scoring" queue) -- built ONCE here, not duplicated.

A REAL, TRANSPARENT RULES-BASED rubric engine, never an LLM call -- matching this
codebase's own established "real rules, never fake AI" convention
(core/network_audit.py's recommendation engine, core/collections.py's risk
scoring, core/lead_record.py's next_best_action()). Every rubric dimension below
is a real, checkable computation over data core/call_center.py's Voice build
already produces -- this module adds no new simulation of its own, it only
scores what already exists on an ended call's linked Communication (core/
communications_hub.py's _simulate_call_recording()).

Honest scope limit, stated plainly rather than glossed over: the simulated
transcript this rubric scores is a single, agent-perspective string with NO
speaker-level segmentation (core/communications_hub.py's own
_simulate_call_recording() concatenates 2-4 fixed agent-side snippets, never a
real two-party dialogue) -- so a genuine agent-vs-customer TALK-TIME RATIO cannot
be honestly computed from it. This module substitutes a real, computed PACING
metric instead (words-per-minute across the whole transcript against the call's
own real duration_seconds), clearly labeled as a pacing proxy, not a two-party
ratio -- never fabricating a talk-time split the underlying data doesn't have.
Every simulated call's transcript also always starts at snippet index 0 (the
greeting line), so the "greeting present" check will honestly read True for
every simulated call -- an accurate reflection of the underlying deterministic
data, not a defect in this rubric; it will genuinely discriminate once real
(non-simulated) call transcripts exist behind a real telephony integration.

Only "ended" calls (core/call_center.py's end_call(), the one lifecycle path
that produces a real two-way conversation transcript via log_communication())
can be scored -- missed/voicemail calls (skip_recording_simulation=True) have no
transcript to score, and a "ringing"/"connected" call hasn't happened yet.
score_call() enforces this explicitly rather than silently scoring whatever it
finds.

The Coaching Score is written onto the Call entity's own already-reserved
`coaching_score` field (core/call_center.py's _create_call(), always None until
this module populates it) -- not a new entity type, since a score is a real
property OF one specific call, not an independent unit of work accumulating its
own history the way OperationsTask/DamageReport/Payment/AutomationExecution/
MarketingContentDraft/PerformanceReview do.

QA Review (BDC Center's own separate ask, the Call's OTHER reserved field,
`qa_review`) is deliberately NOT touched by this module -- that's a separate,
human-driven review workflow (Task #10, extending core/bdc.py's own Scripts/QA
build), not a rules-based auto-score. This module only ever writes
coaching_score. Re-running score_call() on an already-scored call simply
overwrites the prior coaching_score with a fresh one (e.g. after a rubric
refinement) -- there is no "already scored" guard, since a re-score is always a
safe, idempotent-over-the-same-transcript action.
"""

import re
from datetime import datetime, timezone

from core.dealeros import ledger
from core.entity_types import CALL
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH
from core.call_center import get_call
from core.communications_hub import get_communication

GREETING_SNIPPET = "Thanks for calling in -- let me pull up your account."
CLOSING_SNIPPETS = [
    "Let me get that scheduled and I'll follow up with a confirmation.",
    "Is there anything else I can help you with today?",
]
OBJECTION_HANDLING_SNIPPET = "We have a few options that might work for your situation."

# Real, fixed pacing thresholds (words-per-minute across the whole transcript) --
# a genuine, computed proxy for "talking too fast/too slow," not a two-party
# talk-time ratio (see module docstring for why that can't be honestly computed
# from this simulated transcript).
PACING_TOO_FAST_WPM = 170
PACING_TOO_SLOW_WPM = 80

RUBRIC_BASIS = "rules_based_rubric"
RUBRIC_DISCLAIMER = (
    "REAL rules-based scoring, not an AI/LLM judgment -- every finding below "
    "traces to a specific, checkable pattern in the call's own (simulated) "
    "transcript and real duration. The underlying transcript itself is SIMULATED "
    "(see the linked communication's own recording.disclaimer) -- this rubric "
    "honestly scores whatever transcript exists, real or simulated; it does not "
    "itself fabricate anything further."
)


def _now():

    return datetime.now(timezone.utc).isoformat()


def _word_count(text):

    return len(re.findall(r"\b\w+\b", text or ""))


def _score_transcript(transcript, duration_seconds):
    """Pure, deterministic rubric computation over a real transcript string and
    a real call duration -- no randomness, no I/O. Returns
    (findings: list[str], components: dict, overall_score: int, grade: str)."""

    findings = []
    components = {}

    greeting_present = transcript.strip().startswith(GREETING_SNIPPET)
    components["greeting_present"] = greeting_present
    findings.append(
        "Greeting: present at call open." if greeting_present
        else "Greeting: not detected at call open."
    )

    closing_present = any(s in transcript for s in CLOSING_SNIPPETS)
    components["closing_attempt_present"] = closing_present
    findings.append(
        "Closing/next-steps attempt: present." if closing_present
        else "Closing/next-steps attempt: not detected."
    )

    objection_present = OBJECTION_HANDLING_SNIPPET in transcript
    components["objection_handling_present"] = objection_present
    findings.append(
        "Objection handling / options presented: present." if objection_present
        else "Objection handling / options presented: not detected."
    )

    words = _word_count(transcript)
    minutes = max(duration_seconds, 1) / 60.0
    wpm = round(words / minutes, 1)
    components["pacing_wpm"] = wpm

    if wpm > PACING_TOO_FAST_WPM:
        pacing_label = "too_fast"
    elif wpm < PACING_TOO_SLOW_WPM:
        pacing_label = "too_slow"
    else:
        pacing_label = "appropriate"

    components["pacing_label"] = pacing_label
    findings.append(f"Pacing: {wpm} words/min ({pacing_label.replace('_', ' ')}).")

    score = 0
    score += 25 if greeting_present else 0
    score += 25 if closing_present else 0
    score += 25 if objection_present else 0
    score += 25 if pacing_label == "appropriate" else (10 if pacing_label in ("too_fast", "too_slow") else 0)

    if score >= 85:
        grade = "excellent"
    elif score >= 70:
        grade = "good"
    elif score >= 50:
        grade = "needs_improvement"
    else:
        grade = "poor"

    return findings, components, score, grade


def score_call(call_id, scored_by):
    """Scores an ended call's already-simulated transcript against the real,
    transparent rubric above, writing the result onto the Call's own reserved
    coaching_score field. Returns (call_brief, error)."""

    call = get_call(call_id)

    if not call:
        return None, f"Call '{call_id}' not found."

    if call["status"] != "ended":
        return None, (
            f"Call is '{call['status']}', not 'ended' -- only a connected-and-completed "
            "call has a real two-way transcript to score."
        )

    comm_id = call.get("communication_id")
    if not comm_id:
        return None, "This call has no linked communication record to score."

    comm, comm_error = get_communication(comm_id)
    if comm_error or not comm:
        return None, f"Linked communication '{comm_id}' could not be found."

    recording = comm.get("recording")
    if not recording or not recording.get("transcript"):
        return None, "The linked communication has no recorded transcript to score."

    duration_seconds = call.get("duration_seconds") or recording.get("duration_seconds") or 1

    findings, components, overall_score, grade = _score_transcript(
        recording["transcript"], duration_seconds
    )

    coaching_score = {
        "basis": RUBRIC_BASIS,
        "disclaimer": RUBRIC_DISCLAIMER,
        "overall_score": overall_score,
        "grade": grade,
        "components": components,
        "sentiment_score": recording.get("sentiment_score"),
        "sentiment_label": recording.get("sentiment_label"),
        "findings": findings,
        "scored_at": _now(),
        "scored_by": scored_by,
    }

    call_entity = ledger.get_entity(call_id)
    if not call_entity or call_entity.entity_type != CALL:
        return None, f"Call '{call_id}' not found."

    call_entity.attributes["coaching_score"] = coaching_score
    save_graph(GRAPH_PATH)

    return get_call(call_id), None


def get_call_coaching(call_id):
    """Read-only fetch of a call's coaching_score, if any. Returns
    (result_dict, error)."""

    call = get_call(call_id)

    if not call:
        return None, f"Call '{call_id}' not found."

    return {
        "call_id": call["id"],
        "status": call["status"],
        "coaching_score": call.get("coaching_score"),
    }, None


def _call_coaching_brief(call_entity):

    attrs = call_entity.attributes

    return {
        "id": call_entity.id,
        "department": attrs.get("department"),
        "assigned_to": attrs.get("assigned_to"),
        "direction": attrs.get("direction"),
        "status": attrs.get("status"),
        "ended_at": attrs.get("ended_at"),
        "duration_seconds": attrs.get("duration_seconds"),
        "communication_id": attrs.get("communication_id"),
        "coaching_score": attrs.get("coaching_score"),
    }


def list_scorable_calls(department=None, limit=100):
    """Every ended call with a linked communication and no coaching_score yet --
    the real work queue a coach/BDC manager actually works from."""

    calls = [
        e for e in ledger.get_all().values()
        if e.entity_type == CALL
        and e.attributes.get("status") == "ended"
        and e.attributes.get("communication_id")
        and not e.attributes.get("coaching_score")
    ]

    if department:
        calls = [c for c in calls if c.attributes.get("department") == department]

    calls.sort(key=lambda c: c.attributes.get("ended_at") or "", reverse=True)

    return [_call_coaching_brief(c) for c in calls[:limit]]


def list_scored_calls(department=None, assigned_to=None, limit=100):
    """Every already-scored call, most-recently-scored first -- a real
    coaching/QA review history."""

    calls = [
        e for e in ledger.get_all().values()
        if e.entity_type == CALL and e.attributes.get("coaching_score")
    ]

    if department:
        calls = [c for c in calls if c.attributes.get("department") == department]

    if assigned_to:
        calls = [c for c in calls if c.attributes.get("assigned_to") == assigned_to]

    calls.sort(
        key=lambda c: (c.attributes.get("coaching_score") or {}).get("scored_at") or "",
        reverse=True,
    )

    return [_call_coaching_brief(c) for c in calls[:limit]]


def get_coaching_stats(department=None):
    """A real, aggregated coaching dashboard -- average score, grade
    distribution, rubric-component pass rates, and pacing distribution across
    every already-scored call."""

    calls = [
        e for e in ledger.get_all().values()
        if e.entity_type == CALL and e.attributes.get("coaching_score")
    ]

    if department:
        calls = [c for c in calls if c.attributes.get("department") == department]

    scores = [c.attributes["coaching_score"] for c in calls]

    if not scores:
        return {
            "department": department,
            "scored_call_count": 0,
            "average_score": None,
            "grade_distribution": {},
            "component_pass_rates": {},
            "pacing_distribution": {},
        }

    grade_distribution = {}
    for s in scores:
        grade_distribution[s["grade"]] = grade_distribution.get(s["grade"], 0) + 1

    component_keys = ["greeting_present", "closing_attempt_present", "objection_handling_present"]
    component_pass_rates = {}
    for key in component_keys:
        passed = sum(1 for s in scores if s["components"].get(key))
        component_pass_rates[key] = round(passed / len(scores) * 100, 1)

    pacing_distribution = {}
    for s in scores:
        label = s["components"].get("pacing_label")
        pacing_distribution[label] = pacing_distribution.get(label, 0) + 1

    return {
        "department": department,
        "scored_call_count": len(scores),
        "average_score": round(sum(s["overall_score"] for s in scores) / len(scores), 1),
        "grade_distribution": grade_distribution,
        "component_pass_rates": component_pass_rates,
        "pacing_distribution": pacing_distribution,
    }
