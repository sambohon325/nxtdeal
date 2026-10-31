"""Thin ACL layer for core/ai_assist.py's generic inline text-assist -- same
"no service-layer indirection" convention as every other *_api.py module in
this codebase.

Inline assist is deliberately open to EVERY real employee role (ADMIN,
OPERATIONS, SALES, MARKETING, SERVICE, FINANCE): the whole point is a single
"AI assist" button that appears next to any text field on any department's
screen, so gating it to a subset of roles would make it unavailable exactly
where it's meant to be universal. This mirrors core/customer_journey_api.py's
own broad VIEW_ROLES tuple for a cross-department staff-facing action -- no
new sensitive data is exposed (the caller supplies the text being
transformed), and the per-feature kill switch (core/ai_management.py's
ai_assist flag) is the real on/off control, not this role list.
"""

from core.ai_assist import assist_text

VIEW_ROLES = ("ADMIN", "OPERATIONS", "SALES", "MARKETING", "SERVICE", "FINANCE")


def assist_text_api(role, text, action, tone=None, context=None):

    if role not in VIEW_ROLES:
        return {"error": f"Role '{role}' is not permitted to use AI text-assist."}

    return assist_text(text, action, tone=tone, context=context, role=role)
