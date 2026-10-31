"""
Test coverage for core/reputation.py + core/reputation_api.py -- real per-review
response, a bad-review alert queue, an AI auto-respond bot (kill-switched, honest
templated fallback), and a simulated competitor-tracking comparison.

Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity

import core.reputation as rep
import core.reputation_api as rapi
import core.ai_management as am
from core.system_config import set_feature_flag
from core.ai_management import get_call_stats


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    am._CALL_STATS.clear()
    yield
    ledger.reset()
    am._CALL_STATS.clear()


def _review(rid, **attrs):
    ledger.add_entity(Entity(id=rid, entity_type="Review", attributes=attrs))


class TestListReviews:

    def test_sorted_by_review_date_descending(self):
        _review("REV-1", review_date="2026-07-01")
        _review("REV-2", review_date="2026-07-10")
        _review("REV-3", review_date="2026-07-05")
        reviews = rep.list_reviews()
        assert [r.id for r in reviews] == ["REV-2", "REV-3", "REV-1"]

    def test_platform_filter(self):
        _review("REV-1", platform="Google")
        _review("REV-2", platform="Facebook")
        reviews = rep.list_reviews(platform="Google")
        assert [r.id for r in reviews] == ["REV-1"]

    def test_responded_filter_true(self):
        _review("REV-1", responded=True)
        _review("REV-2", responded=False)
        reviews = rep.list_reviews(responded=True)
        assert [r.id for r in reviews] == ["REV-1"]

    def test_responded_filter_false(self):
        _review("REV-1", responded=True)
        _review("REV-2", responded=False)
        reviews = rep.list_reviews(responded=False)
        assert [r.id for r in reviews] == ["REV-2"]

    def test_responded_none_returns_everything(self):
        _review("REV-1", responded=True)
        _review("REV-2", responded=False)
        reviews = rep.list_reviews()
        assert len(reviews) == 2

    def test_max_rating_filter(self):
        _review("REV-1", rating=5)
        _review("REV-2", rating=2)
        _review("REV-3", rating=1)
        reviews = rep.list_reviews(max_rating=2)
        assert {r.id for r in reviews} == {"REV-2", "REV-3"}

    def test_missing_rating_defaults_to_5_for_max_rating_filter(self):
        _review("REV-1")  # no rating attribute at all
        assert rep.list_reviews(max_rating=4) == []
        assert [r.id for r in rep.list_reviews(max_rating=5)] == ["REV-1"]

    def test_empty_ledger_returns_empty_list(self):
        assert rep.list_reviews() == []


class TestListBadReviewAlerts:

    def test_only_unresponded_at_or_below_threshold(self):
        _review("REV-1", rating=1, responded=False, review_date="2026-07-01")  # bad, unresponded
        _review("REV-2", rating=3, responded=False, review_date="2026-07-02")  # bad (threshold), unresponded
        _review("REV-3", rating=4, responded=False, review_date="2026-07-03")  # good, excluded
        _review("REV-4", rating=1, responded=True, review_date="2026-07-04")  # bad but already responded

        alerts = rep.list_bad_review_alerts("ADMIN")
        assert {a["id"] for a in alerts} == {"REV-1", "REV-2"}

    def test_alert_shape(self):
        _review(
            "REV-1", platform="Google", rating=2, author_name="Bob",
            text="Bad experience", review_date="2026-07-05", responded=False,
        )
        alerts = rep.list_bad_review_alerts("ADMIN")
        assert alerts[0] == {
            "id": "REV-1", "platform": "Google", "rating": 2, "author_name": "Bob",
            "text": "Bad experience", "review_date": "2026-07-05",
        }

    def test_no_bad_reviews_returns_empty(self):
        _review("REV-1", rating=5, responded=False)
        assert rep.list_bad_review_alerts("ADMIN") == []


class TestRespondToReview:

    def test_missing_review_is_rejected(self):
        result = rep.respond_to_review("REV-999", "EMP-1", "text")
        assert result == {"error": "Review not found"}

    def test_blank_text_is_rejected(self):
        _review("REV-1")
        result = rep.respond_to_review("REV-1", "EMP-1", "   ")
        assert result == {"error": "A response needs real text."}

    def test_success_sets_all_real_attributes(self):
        _review("REV-1")
        result = rep.respond_to_review("REV-1", "EMP-1", "  Thanks for the feedback!  ")
        assert result.attributes["responded"] is True
        assert result.attributes["response_text"] == "Thanks for the feedback!"
        assert result.attributes["responded_by"] == "EMP-1"
        assert result.attributes["auto_responded"] is False
        assert result.attributes["responded_at"]

    def test_auto_responded_flag_can_be_set_true(self):
        _review("REV-1")
        result = rep.respond_to_review("REV-1", "BOT", "Auto text", auto_responded=True)
        assert result.attributes["auto_responded"] is True


class TestAutoRespondReview:

    def test_missing_review_is_rejected(self):
        result = rep.auto_respond_review("REV-999")
        assert result == {"error": "Review not found"}

    def test_already_responded_is_rejected(self):
        _review("REV-1", responded=True)
        result = rep.auto_respond_review("REV-1")
        assert result == {"error": "This review already has a response."}

    def test_disabled_bad_review_gets_apology_fallback(self):
        set_feature_flag("ai_reputation_autorespond_enabled", False, "EMP-TEST")
        _review("REV-1", rating=2, author_name="Bob", text="Bad")
        result = rep.auto_respond_review("REV-1")
        assert "Bob" in result.attributes["response_text"]
        assert "sorry" in result.attributes["response_text"]
        assert result.attributes["auto_responded"] is True
        assert result.attributes["responded_by"] == "BOT"

    def test_disabled_good_review_gets_thank_you_fallback(self):
        set_feature_flag("ai_reputation_autorespond_enabled", False, "EMP-TEST")
        _review("REV-1", rating=4, author_name="Dave", text="Great")
        result = rep.auto_respond_review("REV-1")
        assert "Dave" in result.attributes["response_text"]
        assert "Thank you" in result.attributes["response_text"]

    def test_disabled_records_blocked_call_attempt(self):
        set_feature_flag("ai_reputation_autorespond_enabled", False, "EMP-TEST")
        _review("REV-1", rating=5)
        rep.auto_respond_review("REV-1")
        stats = get_call_stats("reputation_autorespond")
        assert stats["attempted"] == 1
        assert stats["blocked"] == 1
        assert stats["succeeded"] == 0
        assert stats["fell_back"] == 0

    def test_enabled_but_unreachable_falls_back_and_records_fell_back(self):
        set_feature_flag("ai_reputation_autorespond_enabled", True, "EMP-TEST")
        _review("REV-1", rating=2, author_name="Bob", text="Bad")
        result = rep.auto_respond_review("REV-1")
        # no outbound OpenAI network access in this sandbox -- genuinely falls back
        assert "Bob" in result.attributes["response_text"]
        stats = get_call_stats("reputation_autorespond")
        assert stats["fell_back"] == 1
        assert stats["blocked"] == 0

    def test_missing_rating_treated_as_good_review_for_fallback(self):
        set_feature_flag("ai_reputation_autorespond_enabled", False, "EMP-TEST")
        _review("REV-1", author_name="Eve")  # no rating attribute at all
        result = rep.auto_respond_review("REV-1")
        assert "Thank you" in result.attributes["response_text"]

    def test_missing_author_name_falls_back_to_there(self):
        set_feature_flag("ai_reputation_autorespond_enabled", False, "EMP-TEST")
        _review("REV-1", rating=2)
        result = rep.auto_respond_review("REV-1")
        assert "Hi there" in result.attributes["response_text"]


class TestGetReputationSummary:

    def test_delegates_to_workflow_tab_data(self):
        _review("REV-1", platform="Google", rating=5)
        _review("REV-2", platform="Google", rating=3)
        summary = rep.get_reputation_summary("ADMIN")
        assert summary["total_reviews"] == 2
        assert summary["by_platform"]["Google"]["count"] == 2
        assert summary["by_platform"]["Google"]["avg_rating"] == 4.0

    def test_empty_ledger_returns_honest_zeroes(self):
        summary = rep.get_reputation_summary("ADMIN")
        assert summary["total_reviews"] == 0
        assert summary["by_platform"] == {}
        assert summary["unresponded_negative_count"] == 0


class TestGetCompetitorTracking:

    def test_own_avg_is_simple_average_of_per_platform_averages(self):
        _review("REV-1", platform="Google", rating=5)
        _review("REV-2", platform="Google", rating=3)
        _review("REV-3", platform="Facebook", rating=1)
        result = rep.get_competitor_tracking("ADMIN")
        # Google avg 4.0, Facebook avg 1.0 -- own_avg averages the two platform
        # averages, not a review-count-weighted average across all 3 reviews.
        assert result["you"]["avg_rating"] == 2.5
        assert result["you"]["review_count"] == 3

    def test_empty_ledger_avg_rating_is_none_not_zero(self):
        result = rep.get_competitor_tracking("ADMIN")
        assert result["you"]["avg_rating"] is None
        assert result["you"]["review_count"] == 0

    def test_competitors_are_the_fixed_simulated_baselines(self):
        result = rep.get_competitor_tracking("ADMIN")
        assert len(result["competitors"]) == 3
        labels = {c["label"] for c in result["competitors"]}
        assert labels == {"Competitor A", "Competitor B", "Competitor C"}

    def test_basis_and_notice_are_honestly_labeled_simulated(self):
        result = rep.get_competitor_tracking("ADMIN")
        assert result["basis"] == "simulated_competitor_data"
        assert "SIMULATED" in result["notice"]


class TestReputationApiRoleGating:

    def test_respond_denied_for_sales(self):
        _review("REV-1")
        result = rapi.respond_to_review_api("SALES", "EMP-1", "REV-1", "text")
        assert result == {"error": "Only marketing/admin can respond to a review"}

    def test_respond_allowed_for_marketing(self):
        _review("REV-1")
        result = rapi.respond_to_review_api("MARKETING", "EMP-1", "REV-1", "Thanks!")
        assert result["responded"] is True

    def test_respond_allowed_for_admin(self):
        _review("REV-1")
        result = rapi.respond_to_review_api("ADMIN", "EMP-1", "REV-1", "Thanks!")
        assert result["responded"] is True

    def test_respond_propagates_a_real_error(self):
        result = rapi.respond_to_review_api("ADMIN", "EMP-1", "REV-999", "text")
        assert result == {"error": "Review not found"}

    def test_auto_respond_denied_for_sales(self):
        _review("REV-1", rating=5)
        result = rapi.auto_respond_review_api("SALES", "EMP-1", "REV-1")
        assert result == {"error": "Only marketing/admin can trigger the auto-respond bot"}

    def test_auto_respond_allowed_for_admin(self):
        set_feature_flag("ai_reputation_autorespond_enabled", False, "EMP-TEST")
        _review("REV-1", rating=5, author_name="Dave")
        result = rapi.auto_respond_review_api("ADMIN", "EMP-1", "REV-1")
        assert result["auto_responded"] is True

    def test_summary_and_alerts_and_competitor_tracking_open_to_any_role(self):
        _review("REV-1", platform="Google", rating=5)
        assert rapi.get_reputation_summary_api("SALES")["total_reviews"] == 1
        assert rapi.list_bad_review_alerts_api("SALES") == []
        assert rapi.get_competitor_tracking_api("SALES")["basis"] == "simulated_competitor_data"


class TestListReviewsApiBooleanParsing:

    def test_responded_string_true_is_parsed(self):
        _review("REV-1", responded=True)
        _review("REV-2", responded=False)
        result = rapi.list_reviews_api("ADMIN", responded="true")
        assert [r["id"] for r in result] == ["REV-1"]

    def test_responded_string_1_is_parsed(self):
        _review("REV-1", responded=True)
        result = rapi.list_reviews_api("ADMIN", responded="1")
        assert [r["id"] for r in result] == ["REV-1"]

    def test_responded_string_yes_is_parsed(self):
        _review("REV-1", responded=True)
        result = rapi.list_reviews_api("ADMIN", responded="yes")
        assert [r["id"] for r in result] == ["REV-1"]

    def test_responded_string_false_is_parsed(self):
        _review("REV-1", responded=True)
        _review("REV-2", responded=False)
        result = rapi.list_reviews_api("ADMIN", responded="false")
        assert [r["id"] for r in result] == ["REV-2"]

    def test_responded_string_no_is_treated_as_false(self):
        _review("REV-1", responded=False)
        result = rapi.list_reviews_api("ADMIN", responded="no")
        assert [r["id"] for r in result] == ["REV-1"]

    def test_responded_none_returns_everything(self):
        _review("REV-1", responded=True)
        _review("REV-2", responded=False)
        result = rapi.list_reviews_api("ADMIN")
        assert len(result) == 2

    def test_serialized_shape_includes_id_and_attributes(self):
        _review("REV-1", platform="Google", rating=5)
        result = rapi.list_reviews_api("ADMIN")
        assert result[0]["id"] == "REV-1"
        assert result[0]["platform"] == "Google"
