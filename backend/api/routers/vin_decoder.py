"""NXTDeal VIN Intelligence router -- Phase 1 (core offline/live VIN decode)
and Phase 2 (read-only department cross-checks) of the VIN Intelligence
rollout (core/vin_decoder.py / core/vin_decoder_api.py).

Real offline structural decode (FMVSS 115 / ISO 3779 check digit + model-year
decode + a curated WMI table) merged with a best-effort live NHTSA vPIC
fetch -- never fabricated when the live half can't be reached (this sandbox
has no outbound network access, confirmed at build time; every unresolved
field is reported honestly via a `gaps`/`gap_note`, not guessed).

Extracted verbatim out of api/app.py (CAF-00120, god_file_app_py -- splitting
the 13,000+-line monolith into domain-scoped FastAPI routers). Behavior is
unchanged from the original inline routes -- same paths, same request/
response shapes, same auth flow. Static "/vin-decoder/decode" and
"/vin-decoder/bulk-apply" registered before the dynamic
"/vin-decoder/vehicle/{vehicle_id}" (and its own "/match-check" sibling),
matching the original file's own route-shadowing-avoidance ordering.

The sibling "/deals/{deal_id}/trade-in/decode-vin" route (Phase 2's Sales
trade-in integration) is NOT part of this router -- it belongs to the much
larger, higher-risk "deals" domain and is deliberately left inline in
api/app.py for a later, more cautious pass.
"""

from fastapi import APIRouter, Header
from pydantic import BaseModel

from api.deps import _authenticate

from core.vin_decoder_api import (
    decode_vin_api,
    get_vehicle_vin_decode_api,
    check_vehicle_vin_match_api,
    apply_decode_to_vehicle_api,
    bulk_apply_decode_api,
)


router = APIRouter()


class DecodeVinRequest(BaseModel):

    vin: str
    attempt_live: bool = True


class ApplyVinDecodeRequest(BaseModel):

    attempt_live: bool = True


class BulkApplyVinDecodeRequest(BaseModel):

    vehicle_ids: list = None
    attempt_live: bool = True
    limit: int = 100


@router.post("/vin-decoder/decode")
def vin_decoder_decode(request: DecodeVinRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return decode_vin_api(payload["role"], request.vin, attempt_live=request.attempt_live)


@router.get("/vin-decoder/vehicle/{vehicle_id}")
def vin_decoder_get_vehicle(vehicle_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_vehicle_vin_decode_api(payload["role"], vehicle_id)


@router.post("/vin-decoder/vehicle/{vehicle_id}/apply")
def vin_decoder_apply(vehicle_id: str, request: ApplyVinDecodeRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return apply_decode_to_vehicle_api(payload["role"], payload["employee_id"], vehicle_id, attempt_live=request.attempt_live)


@router.post("/vin-decoder/bulk-apply")
def vin_decoder_bulk_apply(request: BulkApplyVinDecodeRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return bulk_apply_decode_api(
        payload["role"],
        payload["employee_id"],
        vehicle_ids=request.vehicle_ids,
        attempt_live=request.attempt_live,
        limit=request.limit,
    )


@router.get("/vin-decoder/vehicle/{vehicle_id}/match-check")
def vin_decoder_match_check(vehicle_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return check_vehicle_vin_match_api(payload["role"], vehicle_id)
