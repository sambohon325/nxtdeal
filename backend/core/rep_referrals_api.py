"""
Thin API layer for the MySales rep referral/reward program (2026-07-24). Validate + call +
shape, matching core/*_api.py. The rep-facing views are open to any authenticated employee
(a rep manages their OWN referrals, keyed by the token's employee_id); advancing a referral's
status is an admin/NXTDeal action.
"""

from core import rep_referrals
from core.permissions import ADMIN, OPERATIONS


def get_my_summary_api(employee_id):
    return rep_referrals.get_my_summary(employee_id)


def submit_dealership_referral_api(employee_id, kind, dealership_name,
                                   contact_name=None, contact_email=None, notes=None):
    return rep_referrals.submit_dealership_referral(
        employee_id, kind, dealership_name,
        contact_name=contact_name, contact_email=contact_email, notes=notes,
    )


def apply_code_api(employee_id, code):
    """A newly-joined rep records who referred them (or wired into sign-up, task #85)."""
    return rep_referrals.attribute_signup(employee_id, code)


def list_all_api(role, status=None):
    if role not in (ADMIN, OPERATIONS):
        return {"error": "Only an admin or operations manager can view the referral queue."}
    return {"referrals": rep_referrals.list_all(status=status)}


def advance_referral_api(role, actor, referral_id, status):
    if role not in (ADMIN, OPERATIONS):
        return {"error": "Only an admin or operations manager can advance a referral."}
    return rep_referrals.advance_referral(referral_id, status, actor)
