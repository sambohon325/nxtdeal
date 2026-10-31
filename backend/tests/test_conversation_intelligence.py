"""
Tests for core/conversation_intelligence.py — rules-based conversation intelligence for every
channel (2026-07-24). Run from backend/ with `pytest`.

Covers: sentiment (escalation > negative/at_risk > positive > neutral); the 0-100 rubric
scores substance/engagement/next-step/courtesy; suggested actions for escalation/at-risk;
analyze_communication over a logged Communication; and the cross-channel aggregate.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.communications_hub import log_communication
from core import conversation_intelligence as ci


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield
    ledger.reset()


def test_sentiment_labels():
    assert ci._analyze_sentiment("I want to speak to a manager, this is unacceptable") == "escalation"
    assert ci._analyze_sentiment("I'm unhappy, please cancel my order") == "at_risk"
    assert ci._analyze_sentiment("Thanks, that sounds perfect!") == "positive"
    assert ci._analyze_sentiment("ok") == "neutral"


def test_score_rewards_substance_engagement_nextstep_courtesy():
    rich = ci.analyze_text("Hi! Thanks — what time can I come in tomorrow to see the truck?")
    thin = ci.analyze_text("k")
    assert rich["score"] > thin["score"]
    assert set(rich["dimensions"]) == {"substantive", "engagement", "next_step", "courtesy"}
    assert rich["dimensions"]["next_step"] == 25  # mentions "come in"/"tomorrow"/"time"


def test_suggested_action_for_escalation_and_at_risk():
    esc = ci.analyze_text("this is unacceptable, I'll call my lawyer")
    assert "manager" in esc["suggested_action"].lower()
    risk = ci.analyze_text("I'm really disappointed with the delay")
    assert risk["suggested_action"]


def test_analyze_communication_over_a_logged_comm():
    comm, _ = log_communication("sales", "text", "inbound", "Thanks! When can I come in?", "EMP-1")
    result = ci.analyze_communication(comm["id"])
    assert result["channel"] == "text"
    assert result["sentiment"] == "positive"
    assert result["score"] > 0
    assert "disclaimer" in result


def test_analyze_communication_unknown_id():
    assert "error" in ci.analyze_communication("COMM-nope")


def test_channel_intelligence_aggregates_across_channels():
    log_communication("sales", "text", "inbound", "Thanks, perfect!", "EMP-1")
    log_communication("service", "email", "inbound", "I'm unhappy about the delay", "EMP-2")
    log_communication("general", "chat", "inbound", "what are your hours?", "ai_worker:receptionist")
    agg = ci.get_channel_intelligence()
    assert agg["total_analyzed"] == 3
    assert agg["sentiment"]["positive"] >= 1
    assert agg["sentiment"]["at_risk"] >= 1
    assert agg["avg_score"] is not None
    assert agg["by_channel"]["text"]["count"] == 1
