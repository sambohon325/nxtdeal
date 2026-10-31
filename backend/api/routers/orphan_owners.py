"""Orphan Owner Mining router -- the ninth of Sales' ~10 originally-missing
dealership workflows (core/orphan_owner_mining.py / core/orphan_owner_mining_api.py).

Real dealership definition: a customer who owns a vehicle but has no
salesperson currently working that relationship. Viewing is open to
ADMIN/OPERATIONS/SALES/MARKETING; claiming (creating a real assigned Lead
via GENERATED_LEAD) is ADMIN/OPERATIONS/SALES only.

Extracted verbatim out of api/app.py (CAF-00120, god_file_app_py -- splitting
the 13,000+-line monolith into domain-scoped FastAPI routers). Behavior is
unchanged from the original inline routes -- same paths, same request/
response shapes, same auth flow. Static "/orphan-owners/dashboard",
"/orphan-owners/queue", and "/orphan-owners/stats" registered before the
dynamic "/orphan-owners/{customer_id}" (and its own "/claim" sibling),
matching the original file's own route-shadowing-avoidance ordering.
"""

from fastapi import APIRouter, Header
from pydantic import BaseModel

from api.deps import _authenticate

from core.orphan_owner_mining_api import (
    get_orphan_owners_api,
    get_orphan_owner_detail_api,
    claim_orphan_owner_api,
    get_orphan_owner_stats_api,
    get_orphan_owner_dashboard_api,
)


router = APIRouter()


class ClaimOrphanOwnerRequest(BaseModel):

    note: str | None = None


@router.get("/orphan-owners/dashboard")
def orphan_owners_dashboard(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_orphan_owner_dashboard_api(payload["role"])


@router.get("/orphan-owners/queue")
def orphan_owners_queue(limit: int = 50, include_claimed: bool = False, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_orphan_owners_api(payload["role"], limit=limit, include_claimed=include_claimed)


@router.get("/orphan-owners/stats")
def orphan_owners_stats(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_orphan_owner_stats_api(payload["role"])


@router.get("/orphan-owners/{customer_id}")
def orphan_owners_detail(customer_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_orphan_owner_detail_api(payload["role"], customer_id)


@router.post("/orphan-owners/{customer_id}/claim")
def orphan_owners_claim(customer_id: str, request: ClaimOrphanOwnerRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return claim_orphan_owner_api(payload["role"], payload["employee_id"], customer_id, note=request.note)
