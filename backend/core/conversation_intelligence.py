"""
core/conversation_intelligence.py — rules-based conversation intelligence for EVERY channel
(2026-07-24). Sam's NXTDeal Connect spec: "AI Conversation Intelligence... Applies to every
channel... Transcripts, AI Summaries, Sentiment Tracking, Conversation Scoring."

core/call_coaching.py already does real, transparent RULES-BASED scoring -- but only for
CALLS (Call entities, over a transcript). This module extends the same honesty bar to text /
email / chat / social communications: a transparent keyword/heuristic rubric over the message
text, never an LLM, nothing fabricated. It composes the Communications already logged by
core/communications_hub.py (which is where every channel -- and every AI-worker touch -- lands)
and adds a sentiment label, a 0-100 conversation score with explainable dimensions, and a
suggested next action. No new storage or entity type.
"""

BASIS = "rules_based"
DISCLAIMER = (
    "Sentiment and score are computed by a transparent keyword/heuristic rubric over the "
    "message text -- not an LLM, and nothing is fabricated. A short or empty message scores low."
)

# Sentiment cues. Escalation is checked first (it dominates), then negative vs. positive.
_ESCALATION_CUES = ("lawyer", "attorney", "sue", "unacceptable", "ridiculous",
                    "never again", "worst", "speak to a manager", "corporate")
_NEGATIVE_CUES = ("cancel", "refund", "unhappy", "disappointed", "not happy",
                  "frustrat", "delay", "complaint", "still waiting", "no one")
_POSITIVE_CUES = ("thank", "thanks", "great", "perfect", "appreciate", "awesome", "love it",
                  "so happy", "excited", "sounds good", "yes please", "will do")

SENTIMENT_LABELS = ("positive", "neutral", "at_risk", "escalation")

# Score rubric cues.
_ENGAGEMENT_CUES = ("when", "what", "how", "which", "can you", "could you", "do you", "?")
_NEXT_STEP_CUES = ("appointment", "schedule", "come in", "stop by", "visit", "tomorrow",
                   "today", "this week", "time", "call you", "text you", "follow up", "book")
_COURTESY_CUES = ("hi ", "hello", "thank", "thanks", "please", "appreciate", "good morning",
                  "good afternoon")


def _analyze_sentiment(text):
    # Priority: escalation dominates, then a negative cue (a problem outranks courtesy),
    # then positive, else neutral. Keeps "unhappy" from being read as "happy".
    t = (text or "").lower()
    if any(c in t for c in _ESCALATION_CUES):
        return "escalation"
    if any(c in t for c in _NEGATIVE_CUES):
        return "at_risk"
    if any(c in t for c in _POSITIVE_CUES):
        return "positive"
    return "neutral"


def _score_conversation(text):
    """A small, transparent 0-100 rubric: substantive (there's real content), engagement
    (asks/answers something), next_step (moves toward an appointment/follow-up), courtesy
    (greeting/thanks). Each worth up to 25."""
    t = (text or "").lower()
    dims = {
        "substantive": 25 if len(t) >= 20 else (12 if t.strip() else 0),
        "engagement": 25 if any(c in t for c in _ENGAGEMENT_CUES) else 8,
        "next_step": 25 if any(c in t for c in _NEXT_STEP_CUES) else 5,
        "courtesy": 25 if any(c in t for c in _COURTESY_CUES) else 10,
    }
    return sum(dims.values()), dims


def _suggested_action(sentiment, dims):
    if sentiment == "escalation":
        return "Escalate to a manager now — the customer is signalling a serious problem."
    if sentiment == "at_risk":
        return "Reach out personally and quickly to recover the relationship."
    if dims["next_step"] < 25:
        return "No next step was set — propose an appointment or a concrete follow-up time."
    return None


def analyze_text(text, channel=None, direction=None):
    """The core: intelligence for a piece of conversation text, any channel."""
    sentiment = _analyze_sentiment(text)
    score, dims = _score_conversation(text)
    return {
        "sentiment": sentiment,
        "score": score,
        "dimensions": dims,
        "suggested_action": _suggested_action(sentiment, dims),
        "basis": BASIS,
    }


def _text_of(brief):
    """Prefer a phone call's transcript when present, else the message body."""
    rec = brief.get("recording")
    if isinstance(rec, dict) and rec.get("transcript"):
        return rec["transcript"]
    return brief.get("body")


def analyze_brief(brief):
    """Intelligence for a communication brief (a dict from communications_hub)."""
    return analyze_text(_text_of(brief), brief.get("channel"), brief.get("direction"))


def analyze_communication(comm_id):
    from core.communications_hub import get_communication
    brief, error = get_communication(comm_id)
    if error or not brief:
        return {"error": error or f"No communication found with id {comm_id}."}
    return {
        "communication_id": comm_id,
        "channel": brief.get("channel"),
        "direction": brief.get("direction"),
        **analyze_brief(brief),
        "disclaimer": DISCLAIMER,
    }


def get_channel_intelligence(limit=100000):
    """Aggregate conversation intelligence across EVERY channel -- the sentiment mix and the
    average conversation score overall and per channel. This is the 'sentiment tracking +
    conversation scoring on every channel' the calls-only rubric couldn't give."""
    from core.communications_hub import list_communications, CHANNELS

    comms = list_communications(limit=limit)
    by_channel = {c: {"count": 0, "sentiment": {l: 0 for l in SENTIMENT_LABELS}, "_score_total": 0}
                  for c in CHANNELS}
    overall_sentiment = {l: 0 for l in SENTIMENT_LABELS}
    score_total = 0

    for brief in comms:
        intel = analyze_brief(brief)
        overall_sentiment[intel["sentiment"]] += 1
        score_total += intel["score"]
        ch = brief.get("channel")
        if ch in by_channel:
            by_channel[ch]["count"] += 1
            by_channel[ch]["sentiment"][intel["sentiment"]] += 1
            by_channel[ch]["_score_total"] += intel["score"]

    for ch, d in by_channel.items():
        d["avg_score"] = round(d["_score_total"] / d["count"], 1) if d["count"] else None
        d.pop("_score_total")

    n = len(comms)
    return {
        "total_analyzed": n,
        "sentiment": overall_sentiment,
        "avg_score": round(score_total / n, 1) if n else None,
        "by_channel": by_channel,
        "basis": BASIS,
        "disclaimer": DISCLAIMER,
    }
