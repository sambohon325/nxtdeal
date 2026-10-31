"""
Thin ACL layer for core/reputation.py (session 83), imported directly into
api/app.py's route handlers.

Role rule: any authenticated role can read reviews/summaries/alerts/competitor
tracking (same broad-visibility rule as ASSET/CAMPAIGN/WEBSITE); responding to a
review (human or bot-triggered) is scoped to MARKETING/ADMIN, since a response is a
real, permanent, publicly-visible action -- same "any role sees, MARKETING/ADMIN acts"
split as core/social_posts_api.py's publish gate.
"""

from core.reputation import (
    get_reputation_summary,
    list_reviews,
    list_bad_review_alerts,
    respond_to_review,
    auto_respond_review,
    get_competitor_tracking,
)
from core.permissions import ADMIN, MARKETING


def _can_respond(role):
    return role == ADMIN or role == MARKETING


def _serialize(entity):
    return {"id": entity.id, **entity.attributes}


def get_reputation_summary_api(role):
    return get_reputation_summary(role)


def list_reviews_api(role, platform=None, responded=None, max_rating=None):

    responded_bool = None
    if responded is not None:
        responded_bool = str(responded).lower() in ("true", "1", "yes")

    reviews = list_reviews(platform=platform, responded=responded_bool, max_rating=max_rating)

    return [_serialize(r) for r in reviews]


def list_bad_review_alerts_api(role):
    return list_bad_review_alerts(role)


def respond_to_review_api(role, employee_id, review_id, response_text):

    if not _can_respond(role):
        return {"error": "Only marketing/admin can respond to a review"}

    result = respond_to_review(review_id, employee_id, response_text)

    if isinstance(result, dict) and "error" in result:
        return result

    return _serialize(result)


def auto_respond_review_api(role, employee_id, review_id):

    if not _can_respond(role):
        return {"error": "Only marketing/admin can trigger the auto-respond bot"}

    result = auto_respond_review(review_id)

    if isinstance(result, dict) and "error" in result:
        return result

    return _serialize(result)


def get_competitor_tracking_api(role):
    return get_competitor_tracking(role)
