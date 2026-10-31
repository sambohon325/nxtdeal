"""
AI Marketing Studio (2026-07-19, continuing Sam's six-pillar spec, autonomous "keep
going" continuation right after Workforce Management). Closes the "AI Marketing
Studio" half of Sam's still-open "AI Marketing Studio + Website Personalization" item.

Deliberately NOT a new generation engine -- this codebase already has 7 real,
isolated, kill-switched OpenAI wizard functions scattered across 4 modules
(core/email_wizard.py, core/website_wizard.py, core/social_caption_wizard.py,
core/advertising.py), each called ad hoc from its own screen with no shared
history and no cross-channel content library. The Studio is a real, thin
DISPATCH TABLE over all 7 -- one place to generate any kind of marketing content,
plus a real log of every generation made through it.

Why a new entity (MarketingContentDraft) rather than composing what's already
there: checked first whether the content-holding entities themselves already
track "was this AI-generated" consistently -- they don't. core/email_templates.py's
create_template() stores a real ai_generated attribute; core/social_posts.py's
SocialPost never persists one at all (only returned transiently in the API
response). Composing two inconsistent conventions would be more fragile than one
real, deliberate log -- same "own lifecycle" reasoning OperationsTask/DamageReport/
Payment/AutomationExecution/StrategicInitiative/EmployeeShift already established.
A draft's own lifecycle (drafted -> applied/discarded) is honest about what
actually happened to a piece of generated content: applied means a marketer used
it somewhere (an EmailTemplate, a SocialPost, a Website section, an AdCampaign),
discarded means they didn't. This module does NOT itself create the downstream
EmailTemplate/SocialPost/etc. -- applying a draft is a marketer copying/using the
generated text into that channel's own existing creation flow, tracked here only
as a real "did this draft get used" marker, not a second content-creation path.

The 7 real content types dispatched to, and the reasoning for what's deliberately
EXCLUDED from this dispatch table:

  - email_copy / sms_copy   -> core.email_wizard (shares one AI kill switch,
    "email_sms_wizard")
  - website_section          -> core.website_wizard.regenerate_section_copy()
    ("website_wizard" kill switch)
  - website_seo               -> core.website_wizard.generate_page_seo_copy()
    (same kill switch)
  - vehicle_description        -> core.website_wizard.generate_vehicle_description()
    (same kill switch)
  - social_caption             -> core.social_caption_wizard.generate_caption()
    ("social_caption_wizard" kill switch)
  - ad_recommendation           -> core.advertising.generate_ad_recommendation()
    ("advertising_ai" kill switch)

Deliberately excluded: core/website_wizard.py's generate_wizard_copy() (the
whole-SITE bootstrap wizard -- a different shape entirely, a multi-field site
scaffold rather than a single piece of content, with its own dedicated Setup
Wizard screen) and core/event_campaign_generator.py's compound campaign-drafting
action (creates a real linked Campaign + EmailTemplate pair in one call, a bigger
action than a single content draft, with its own dedicated UI inside
EventsBoard.tsx). Neither is a content "draft" in the sense this module logs.

Each wizard function already has its own AI Management kill switch and its own
honest fallback function for when OpenAI is unreachable -- this module doesn't
duplicate either; it calls the real function, and if it returns an error/disabled
result, falls back to that same function's own fallback_* counterpart, exactly
like every existing caller already does. The draft itself always records whether
the content that was actually stored came from a real AI call or a fallback
(`used_fallback`), never blurring the two.
"""

from datetime import datetime, timezone

from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.entity_types import MARKETING_CONTENT_DRAFT
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH

DRAFT_STATUSES = ("drafted", "applied", "discarded")

CONTENT_TYPES = (
    "email_copy",
    "sms_copy",
    "website_section",
    "website_seo",
    "vehicle_description",
    "social_caption",
    "ad_recommendation",
)

CONTENT_TYPE_CATALOG = [
    {
        "key": "email_copy",
        "label": "Email Copy",
        "channel": "email_sms",
        "params": ["goal", "audience_description", "tone"],
        "kill_switch_feature": "email_sms_wizard",
    },
    {
        "key": "sms_copy",
        "label": "SMS Copy",
        "channel": "email_sms",
        "params": ["goal", "audience_description", "tone"],
        "kill_switch_feature": "email_sms_wizard",
    },
    {
        "key": "website_section",
        "label": "Website Section Rewrite",
        "channel": "website",
        "params": ["section_name", "text_fields", "dealership_name", "tone", "instructions"],
        "kill_switch_feature": "website_wizard",
    },
    {
        "key": "website_seo",
        "label": "Website SEO Meta Copy",
        "channel": "website",
        "params": ["dealership_name", "page_key", "page_summary"],
        "kill_switch_feature": "website_wizard",
    },
    {
        "key": "vehicle_description",
        "label": "Vehicle Description",
        "channel": "website",
        "params": ["dealership_name", "vehicle_attrs"],
        "kill_switch_feature": "website_wizard",
    },
    {
        "key": "social_caption",
        "label": "Social Media Caption",
        "channel": "social",
        "params": ["platform", "goal", "tone", "vehicle"],
        "kill_switch_feature": "social_caption_wizard",
    },
    {
        "key": "ad_recommendation",
        "label": "Ad Campaign Recommendation",
        "channel": "advertising",
        "params": ["platform", "objective", "audience_description", "vehicle_description"],
        "kill_switch_feature": "advertising_ai",
    },
]


def _now():
    return datetime.now(timezone.utc).isoformat()


def _generate_raw(content_type, params):
    """Dispatches to the real wizard function for content_type, falling back to
    that same wizard's own fallback_* function on any error/disabled result.
    Returns (content_dict, used_fallback: bool, error_note: str | None)."""

    params = params or {}

    if content_type in ("email_copy", "sms_copy"):
        from core.email_wizard import generate_email_copy, generate_sms_copy, fallback_copy

        brief = {
            "goal": params.get("goal"),
            "audience_description": params.get("audience_description"),
            "tone": params.get("tone"),
        }
        channel = "email" if content_type == "email_copy" else "sms"
        result = generate_email_copy(brief) if content_type == "email_copy" else generate_sms_copy(brief)

        if isinstance(result, dict) and "error" in result:
            return fallback_copy(brief, channel), True, result.get("error")
        return result, False, None

    if content_type == "website_section":
        from core.website_wizard import regenerate_section_copy

        result = regenerate_section_copy(
            params.get("section_name"),
            params.get("text_fields") or [],
            dealership_name=params.get("dealership_name"),
            tone=params.get("tone"),
            instructions=params.get("instructions"),
        )
        if isinstance(result, dict) and "error" in result:
            # No dedicated fallback exists for a per-section rewrite (the caller is
            # meant to keep the section's existing values on failure) -- record the
            # attempt honestly rather than fabricate replacement copy.
            return {}, True, result.get("error")
        return result, False, None

    if content_type == "website_seo":
        from core.website_wizard import generate_page_seo_copy, fallback_seo_copy

        result = generate_page_seo_copy(
            params.get("dealership_name"), params.get("page_key"), page_summary=params.get("page_summary")
        )
        if isinstance(result, dict) and "error" in result:
            return fallback_seo_copy(params.get("dealership_name"), params.get("page_key")), True, result.get("error")
        return result, False, None

    if content_type == "vehicle_description":
        from core.website_wizard import generate_vehicle_description, fallback_vehicle_description

        vehicle_attrs = params.get("vehicle_attrs") or {}
        result = generate_vehicle_description(params.get("dealership_name"), vehicle_attrs)
        if isinstance(result, dict) and "error" in result:
            return {"description": fallback_vehicle_description(vehicle_attrs)}, True, result.get("error")
        return result, False, None

    if content_type == "social_caption":
        from core.social_caption_wizard import generate_caption, fallback_caption

        platform = params.get("platform")
        goal = params.get("goal")
        tone = params.get("tone")
        vehicle = params.get("vehicle")
        result = generate_caption(platform, goal=goal, tone=tone, vehicle=vehicle)
        if isinstance(result, dict) and "error" in result:
            return fallback_caption(platform, goal=goal, vehicle=vehicle), True, result.get("error")
        return result, False, None

    if content_type == "ad_recommendation":
        from core.advertising import generate_ad_recommendation, fallback_recommendation

        brief = {
            "platform": params.get("platform"),
            "objective": params.get("objective"),
            "audience_description": params.get("audience_description"),
            "vehicle_description": params.get("vehicle_description"),
        }
        result = generate_ad_recommendation(brief)
        if isinstance(result, dict) and "error" in result:
            return fallback_recommendation(brief), True, result.get("error")
        return result, False, None

    return None, None, None


def generate_content(content_type, params, created_by):

    if content_type not in CONTENT_TYPES:
        return {"error": f"content_type must be one of {CONTENT_TYPES}"}

    content, used_fallback, error_note = _generate_raw(content_type, params)

    if content is None:
        return {"error": f"No dispatcher registered for content_type '{content_type}'"}

    draft_id = id_generator.generate("MCD")

    entity = Entity(
        id=draft_id,
        entity_type=MARKETING_CONTENT_DRAFT,
        attributes={
            "content_type": content_type,
            "params": params or {},
            "content": content,
            "used_fallback": used_fallback,
            "fallback_reason": error_note if used_fallback else None,
            "status": "drafted",
            "created_by": created_by,
            "created_at": _now(),
            "decided_by": None,
            "decided_at": None,
        },
    )

    ledger.add_entity(entity)
    save_graph(GRAPH_PATH)

    return entity


def _get_draft(draft_id):
    e = ledger.get_entity(draft_id)
    return e if e and e.entity_type == MARKETING_CONTENT_DRAFT else None


def _decide_draft(draft_id, new_status, by):

    draft = _get_draft(draft_id)
    if not draft:
        return {"error": "Content draft not found"}

    if draft.attributes.get("status") != "drafted":
        return {"error": f"Cannot change a draft that is already '{draft.attributes.get('status')}'."}

    draft.attributes["status"] = new_status
    draft.attributes["decided_by"] = by
    draft.attributes["decided_at"] = _now()

    save_graph(GRAPH_PATH)

    return draft


def mark_applied(draft_id, by):
    return _decide_draft(draft_id, "applied", by)


def mark_discarded(draft_id, by):
    return _decide_draft(draft_id, "discarded", by)


def list_content_drafts(content_type=None, status=None, created_by=None):

    drafts = [e for e in ledger.get_all().values() if e.entity_type == MARKETING_CONTENT_DRAFT]

    if content_type:
        drafts = [d for d in drafts if d.attributes.get("content_type") == content_type]
    if status:
        drafts = [d for d in drafts if d.attributes.get("status") == status]
    if created_by:
        drafts = [d for d in drafts if d.attributes.get("created_by") == created_by]

    drafts.sort(key=lambda d: d.attributes.get("created_at") or "", reverse=True)

    return drafts


def _draft_brief(draft):
    return {
        "id": draft.id,
        "content_type": draft.attributes.get("content_type"),
        "params": draft.attributes.get("params"),
        "content": draft.attributes.get("content"),
        "used_fallback": draft.attributes.get("used_fallback"),
        "fallback_reason": draft.attributes.get("fallback_reason"),
        "status": draft.attributes.get("status"),
        "created_by": draft.attributes.get("created_by"),
        "created_at": draft.attributes.get("created_at"),
        "decided_by": draft.attributes.get("decided_by"),
        "decided_at": draft.attributes.get("decided_at"),
    }


def get_studio_overview():

    drafts = list_content_drafts()

    by_type = {}
    by_status = {}
    fallback_count = 0

    for d in drafts:
        ct = d.attributes.get("content_type")
        st = d.attributes.get("status")
        by_type[ct] = by_type.get(ct, 0) + 1
        by_status[st] = by_status.get(st, 0) + 1
        if d.attributes.get("used_fallback"):
            fallback_count += 1

    return {
        "content_type_catalog": CONTENT_TYPE_CATALOG,
        "total_drafts": len(drafts),
        "by_content_type": by_type,
        "by_status": by_status,
        "fallback_count": fallback_count,
        "recent_drafts": [_draft_brief(d) for d in drafts[:25]],
    }
