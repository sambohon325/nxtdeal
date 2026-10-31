"""
Reputation management -- real per-review response + a bad-review alert/auto-respond
bot (session 83). Sam: "there needs to be a toggle for reputation tracking, which
connects, google, facebook, etc. reviews to show aggregate reviews, the ability to
respond to each review, and have an bot function to respond to reviews / alert for
bad reviews."

Builds directly on the real seeded Review entities (imports/seed_demo_extras.py,
session 59) and core/workflow_tab_data.py's marketing_reputation_summary() (the same
aggregate already backing the Workflow-button reputation tab and the old standalone
Reputation Top Menu item) rather than a parallel review model. respond_to_review() is
a real, permanent update to the Review entity -- there is no fake "connects to
Google/Facebook" integration here (this sandbox has no path to those review APIs), so
the reviews themselves are the same honest, seeded starting dataset every other
reputation view in this codebase already uses; what's new is the ability to act on
them (respond) and be alerted about them (bad-review queue), not a new data source.

auto_respond_review() is the "bot function to respond to reviews" -- an isolated,
no-tool-access OpenAI call (same isolation pattern as core/email_wizard.py/
core/website_wizard.py) that drafts a real, review-specific response; a plain
templated fallback covers the case OpenAI can't be reached, so the bot always
produces something usable rather than failing silently.
"""

import json
import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from core.optional_ai_client import LazyOpenAI

from core.dealeros import ledger
from core.entity_types import REVIEW
from core.workflow_tab_data import marketing_reputation_summary
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH
from core.ai_management import is_feature_enabled, record_call_attempt

# Real data-loss bug found and fixed (2026-07-18, codebase-wide save_graph() audit --
# see core/lead_conversion.py's docstring for the running list of confirmed instances).
# This module had ZERO save_graph() calls anywhere since it shipped (session 83) --
# every real review response (human or bot-drafted) had been silently discarded on
# server restart. Fixed below.

load_dotenv()

client = LazyOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Bad-review alert threshold -- matches marketing_reputation_summary()'s own real
# threshold (rating <= 3) so "alerts" and "unresponded_negative" never disagree about
# what counts as a bad review.
BAD_REVIEW_RATING_THRESHOLD = 3

RESPONSE_SYSTEM_PROMPT = (
    "You are a dealership's customer experience manager responding publicly to an "
    "online review. Given the review's star rating and text, write a short (2-4 "
    "sentence), sincere, non-defensive public response. For a negative review, "
    "acknowledge the specific issue, apologize, and invite them to contact the "
    "dealership directly to make it right -- do not make specific promises (refunds, "
    "free services) you weren't told to make. For a positive review, thank them by "
    "name if given and mention something specific from their review. Return ONLY a "
    "JSON object with one key: response_text."
)


def _now():
    return datetime.now(timezone.utc).isoformat()


def _get_review(review_id):

    entity = ledger.get_entity(review_id)

    if entity and entity.entity_type == REVIEW:
        return entity

    return None


def get_reputation_summary(role):
    return marketing_reputation_summary(role)


def list_reviews(platform=None, responded=None, max_rating=None):

    reviews = [e for e in ledger.get_all().values() if e.entity_type == REVIEW]

    if platform:
        reviews = [r for r in reviews if r.attributes.get("platform") == platform]

    if responded is not None:
        reviews = [r for r in reviews if bool(r.attributes.get("responded")) == responded]

    if max_rating is not None:
        reviews = [r for r in reviews if (r.attributes.get("rating") or 5) <= max_rating]

    reviews.sort(key=lambda r: r.attributes.get("review_date") or "", reverse=True)

    return reviews


def list_bad_review_alerts(role):
    """The real-time alert queue Sam asked for -- every unresponded review at or below
    BAD_REVIEW_RATING_THRESHOLD, newest first. Not a stored alert entity (no polling/
    push mechanism exists for this yet -- see core/reputation_api.py's module docstring
    for the honest gap note) -- computed live off the real graph each time it's asked
    for, same "compute fresh, don't fake a feed" rule as every other menu-item
    aggregate in this codebase."""

    return [
        {
            "id": r.id,
            "platform": r.attributes.get("platform"),
            "rating": r.attributes.get("rating"),
            "author_name": r.attributes.get("author_name"),
            "text": r.attributes.get("text"),
            "review_date": r.attributes.get("review_date"),
        }
        for r in list_reviews(responded=False, max_rating=BAD_REVIEW_RATING_THRESHOLD)
    ]


def respond_to_review(review_id, employee_id, response_text, auto_responded=False):

    review = _get_review(review_id)

    if not review:
        return {"error": "Review not found"}

    if not (response_text or "").strip():
        return {"error": "A response needs real text."}

    review.attributes["responded"] = True
    review.attributes["response_text"] = response_text.strip()
    review.attributes["responded_by"] = employee_id
    review.attributes["responded_at"] = _now()
    review.attributes["auto_responded"] = bool(auto_responded)

    save_graph(GRAPH_PATH)

    return review


def _draft_response(review):
    """AI Management: checks the real 'reputation_autorespond' kill switch
    (core/ai_management.py, ai_reputation_autorespond_enabled flag) before
    attempting the OpenAI call. When disabled, skips straight to the same
    templated fallback an OpenAI/network failure already falls back to --
    disabling this never leaves a review unanswered, it just stops drafting one
    with AI."""

    rating = review.attributes.get("rating")
    text = review.attributes.get("text") or ""
    author = review.attributes.get("author_name") or "there"

    if is_feature_enabled("reputation_autorespond"):
        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": RESPONSE_SYSTEM_PROMPT},
                    {"role": "user", "content": f"Reviewer: {author}\nRating: {rating}/5\nReview: {text}"},
                ],
                response_format={"type": "json_object"},
            )
            parsed = json.loads(response.choices[0].message.content)
            draft = (parsed.get("response_text") or "").strip()
            if draft:
                record_call_attempt("reputation_autorespond", "succeeded")
                return draft
            record_call_attempt("reputation_autorespond", "fell_back", detail="Empty response returned")
        except Exception as exc:  # noqa: BLE001 -- any OpenAI/network/parse failure falls back
            record_call_attempt("reputation_autorespond", "fell_back", detail=str(exc))
    else:
        record_call_attempt("reputation_autorespond", "blocked")

    if (rating or 5) <= BAD_REVIEW_RATING_THRESHOLD:
        return (
            f"Hi {author}, thank you for the honest feedback -- we're sorry your "
            "experience didn't meet the mark. We'd like to make this right; please "
            "reach out to our office directly so we can help."
        )

    return f"Thank you so much for the kind words, {author} -- we really appreciate you taking the time to share this!"


def auto_respond_review(review_id):
    """The 'bot function to respond to reviews' -- real AI-drafted response, applied
    directly (not just proposed) and flagged auto_responded=True so the reputation
    view can distinguish a bot reply from a human one."""

    review = _get_review(review_id)

    if not review:
        return {"error": "Review not found"}

    if review.attributes.get("responded"):
        return {"error": "This review already has a response."}

    draft = _draft_response(review)

    return respond_to_review(review_id, "BOT", draft, auto_responded=True)


# --- Simulated competitor social/review tracking ---
#
# Sam: "competitors social tracking." This sandbox has no real path to competitors'
# social accounts or review pages, so this is an honestly-labeled SIMULATED estimate,
# same precedent core/network_benchmark.py already established for peer-dealer
# benchmarking (blind-labeled Dealer B/C/D, fixed baseline anchors) -- reused here
# rather than inventing a second simulated-data convention.
SIMULATED_BASIS = "simulated_competitor_data"

_COMPETITOR_BASELINES = [
    {"label": "Competitor A", "avg_rating": 4.3, "review_count": 612, "posts_per_week": 5},
    {"label": "Competitor B", "avg_rating": 3.9, "review_count": 340, "posts_per_week": 3},
    {"label": "Competitor C", "avg_rating": 4.6, "review_count": 891, "posts_per_week": 8},
]


def get_competitor_tracking(role):
    """Blind-labeled simulated competitor snapshot, alongside this dealership's own
    real numbers so the comparison is honest about which side is real."""

    summary = marketing_reputation_summary(role)

    all_ratings = [
        v["avg_rating"] for v in summary.get("by_platform", {}).values() if v.get("avg_rating") is not None
    ]
    own_avg = round(sum(all_ratings) / len(all_ratings), 2) if all_ratings else None

    return {
        "you": {
            "avg_rating": own_avg,
            "review_count": summary.get("total_reviews", 0),
            "posts_per_week": None,
        },
        "competitors": _COMPETITOR_BASELINES,
        "basis": SIMULATED_BASIS,
        "notice": (
            "Competitor figures shown here are SIMULATED -- this sandbox has no real "
            "connection to competitors' social accounts or review pages. Your own "
            "figures (avg_rating, review_count) are real."
        ),
    }
