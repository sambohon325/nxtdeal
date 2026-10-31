"""Thin ACL layer for core/marketing_studio.py's AI Marketing Studio.

Viewing (the studio overview + content-draft list) is scoped to ADMIN/MARKETING --
matching core/email_templates_api.py's/core/social_posts_api.py's own content-
creation precedent, since a generated draft can carry unreleased/undecided
marketing copy, not broad department-visible reporting data. Generating/applying/
discarding a draft is that same ADMIN/MARKETING set -- no separate mutate tier,
since drafting marketing content and deciding what to do with it are the same
real job, unlike Workforce's scheduling-vs-approving split.
"""

from core.marketing_studio import (
    generate_content,
    mark_applied,
    mark_discarded,
    list_content_drafts,
    get_studio_overview,
    _draft_brief,
)

VIEW_ROLES = ("ADMIN", "MARKETING")
MUTATE_ROLES = ("ADMIN", "MARKETING")

_VIEW_DENIED = {"error": "You don't have access to the AI Marketing Studio with your current role."}
_MUTATE_DENIED = {"error": "Generating or deciding on marketing content requires Admin or Marketing."}


def _is_error(result):
    return isinstance(result, dict) and "error" in result


def _serialize(result):
    if _is_error(result):
        return result
    return _draft_brief(result)


def get_studio_overview_api(role):
    if role not in VIEW_ROLES:
        return _VIEW_DENIED
    return get_studio_overview()


def list_content_drafts_api(role, content_type=None, status=None, created_by=None):
    if role not in VIEW_ROLES:
        return _VIEW_DENIED
    drafts = list_content_drafts(content_type=content_type, status=status, created_by=created_by)
    return {"drafts": [_draft_brief(d) for d in drafts]}


def generate_content_api(role, content_type, params, created_by):
    if role not in MUTATE_ROLES:
        return _MUTATE_DENIED
    return _serialize(generate_content(content_type, params, created_by))


def mark_applied_api(role, draft_id, by):
    if role not in MUTATE_ROLES:
        return _MUTATE_DENIED
    return _serialize(mark_applied(draft_id, by))


def mark_discarded_api(role, draft_id, by):
    if role not in MUTATE_ROLES:
        return _MUTATE_DENIED
    return _serialize(mark_discarded(draft_id, by))
