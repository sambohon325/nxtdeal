"""
ACL layer for core/purls.py's staff-side functions -- imported directly into
api/app.py's route handlers, same "no service layer indirection" convention
every other `*_api.py` module in this codebase follows.

Role rule: matches core/lead_scoring_api.py's own set -- ADMIN/OPERATIONS/SALES/
MARKETING -- generating and reviewing a PURL is a Sales-and-Marketing-shared
action, no broader than working a Lead itself already is.

The 5 PUBLIC functions in core/purls.py (get_personalized_offer/
record_purl_visit/submit_purl_lead) have NO wrapper here at all -- they're
called directly from api/app.py's genuinely unauthenticated `/public/purl/*`
routes, same convention core/approval_center.py/core/appointment_scheduling.py
already established.
"""

from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING
from core.purls import (
    generate_purl,
    revoke_purl,
    list_purls,
    create_mail_piece,
    get_purl_analytics,
    get_purl_dashboard,
    bulk_generate_purls,
)

_ROLES = (ADMIN, OPERATIONS, SALES, MARKETING)

_FORBIDDEN = {"error": "You don't have access to the PURL Platform with your current role."}


def generate_purl_api(role, created_by, offer_type="general", customer_id=None, lead_id=None, notes=None):
    if role not in _ROLES:
        return _FORBIDDEN
    return generate_purl(created_by, offer_type=offer_type, customer_id=customer_id, lead_id=lead_id, notes=notes)


def revoke_purl_api(role, purl_id, revoked_by):
    if role not in _ROLES:
        return _FORBIDDEN
    return revoke_purl(purl_id, revoked_by)


def list_purls_api(role, created_by=None, status=None):
    if role not in _ROLES:
        return _FORBIDDEN
    return list_purls(created_by=created_by, status=status)


def create_mail_piece_api(role, purl_id, piece_name, piece_type, mail_date=None, created_by=None):
    if role not in _ROLES:
        return _FORBIDDEN
    return create_mail_piece(purl_id, piece_name, piece_type, mail_date=mail_date, created_by=created_by)


def get_purl_analytics_api(role, purl_id):
    if role not in _ROLES:
        return _FORBIDDEN
    return get_purl_analytics(purl_id)


def get_purl_dashboard_api(role, created_by=None):
    if role not in _ROLES:
        return _FORBIDDEN
    return get_purl_dashboard(role, created_by=created_by)


def bulk_generate_purls_api(role, created_by, source_type, source_id, offer_type="general", notes=None):
    if role not in _ROLES:
        return _FORBIDDEN
    return bulk_generate_purls(created_by, source_type, source_id, offer_type=offer_type, notes=notes)
