"""Coaching router -- Coaching Intensity Tiers, AI Performance Reviews, and
AI Career Pathing (NXTDeal Workforce AI, "Coaching" pillar).

Extracted verbatim out of api/app.py (CAF-00120, god_file_app_py -- splitting
the 14,800+-line monolith into domain-scoped FastAPI routers). Behavior is
unchanged from the original inline routes -- same paths, same request/response
shapes, same auth flow. api/app.py now just does `app.include_router(router)`
for this module instead of defining these 14 routes inline.

core/coaching_api.py's own module docstring covers the ACL reasoning: a
manager-tier employee (or ADMIN/OPERATIONS) can act on anyone; any employee
can always view their OWN resolved intensity and their OWN SHARED (only)
performance reviews.
"""

from fastapi import APIRouter, Header
from pydantic import BaseModel

from api.deps import _authenticate

from core.coaching_api import (
    get_intensity_catalog_api,
    resolve_intensity_api,
    set_intensity_override_api,
    list_intensity_overrides_api,
    preview_intensity_api,
    create_performance_review_api,
    update_review_notes_api,
    finalize_review_api,
    share_review_api,
    discard_review_api,
    get_review_api,
    list_reviews_api,
    get_career_pathing_signal_api,
    get_career_pathing_board_api,
)


router = APIRouter()


class SetCoachingIntensityRequest(BaseModel):
    scope: str
    scope_target: str
    intensity: str
    reason: str = ""


class PreviewCoachingIntensityRequest(BaseModel):
    target_employee_id: str
    items: list
    department: str = None


class CreatePerformanceReviewRequest(BaseModel):
    target_employee_id: str
    period_label: str = ""


class UpdateReviewNotesRequest(BaseModel):
    manager_notes: str


@router.get("/coaching/intensity/catalog")
def coaching_intensity_catalog():
    return get_intensity_catalog_api()


@router.get("/coaching/intensity/resolve")
def coaching_intensity_resolve(
    target_employee_id: str = None,
    department: str = None,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return resolve_intensity_api(
        payload["role"], payload["employee_id"], target_employee_id, department
    )


@router.post("/coaching/intensity/override")
def coaching_intensity_set(
    request: SetCoachingIntensityRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return set_intensity_override_api(
        payload["role"],
        payload["employee_id"],
        request.scope,
        request.scope_target,
        request.intensity,
        request.reason
    )


@router.get("/coaching/intensity/overrides")
def coaching_intensity_overrides(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_intensity_overrides_api(payload["role"], payload["employee_id"])


@router.post("/coaching/intensity/preview")
def coaching_intensity_preview(
    request: PreviewCoachingIntensityRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return preview_intensity_api(
        payload["role"],
        payload["employee_id"],
        request.target_employee_id,
        request.items,
        request.department
    )


@router.post("/coaching/reviews")
def coaching_create_review(
    request: CreatePerformanceReviewRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return create_performance_review_api(
        payload["role"],
        payload["employee_id"],
        request.target_employee_id,
        request.period_label
    )


@router.get("/coaching/reviews")
def coaching_list_reviews(
    employee_id: str = None,
    status: str = None,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_reviews_api(payload["role"], payload["employee_id"], employee_id, status)


@router.get("/coaching/reviews/{review_id}")
def coaching_get_review(
    review_id: str,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_review_api(payload["role"], payload["employee_id"], review_id)


@router.post("/coaching/reviews/{review_id}/notes")
def coaching_update_review_notes(
    review_id: str,
    request: UpdateReviewNotesRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return update_review_notes_api(
        payload["role"], payload["employee_id"], review_id, request.manager_notes
    )


@router.post("/coaching/reviews/{review_id}/finalize")
def coaching_finalize_review(
    review_id: str,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return finalize_review_api(payload["role"], payload["employee_id"], review_id)


@router.post("/coaching/reviews/{review_id}/share")
def coaching_share_review(
    review_id: str,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return share_review_api(payload["role"], payload["employee_id"], review_id)


@router.post("/coaching/reviews/{review_id}/discard")
def coaching_discard_review(
    review_id: str,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return discard_review_api(payload["role"], payload["employee_id"], review_id)


@router.get("/coaching/career-pathing")
def coaching_career_pathing_signal(
    target_employee_id: str = None,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_career_pathing_signal_api(
        payload["role"], payload["employee_id"], target_employee_id
    )


@router.get("/coaching/career-pathing/board")
def coaching_career_pathing_board(
    department: str = None,
    signal: str = None,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_career_pathing_board_api(
        payload["role"], payload["employee_id"], department, signal
    )
