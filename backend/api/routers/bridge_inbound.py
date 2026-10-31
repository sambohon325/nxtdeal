"""Bounded signed delivery endpoint. No session token substitutes for signature."""
import asyncio
import re
from threading import BoundedSemaphore

from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool
from starlette.requests import ClientDisconnect
from core import bridge_inbound as inbound
from core.bridge_adapters.adf_gateway import InvalidDelivery
from core.bridge_credentials import CredentialUnavailable

router = APIRouter()
_SLOTS = BoundedSemaphore(4)
_BODY_TIMEOUT_SECONDS = 15


def one_header(request, name, *, required=True):
    values = request.headers.getlist(name)
    if len(values) > 1 or required and len(values) != 1:
        raise HTTPException(400, "Invalid delivery envelope")
    return values[0] if values else None


@router.post("/inbound/adf/{endpoint_id}", status_code=202)
async def receive_adf(endpoint_id: str, request: Request):
    delivery_id = one_header(request, "x-nxtdeal-delivery-id")
    signed_at = one_header(request, "x-nxtdeal-signed-at")
    signature = one_header(request, "x-nxtdeal-signature")
    if (not re.fullmatch(r"[A-Za-z0-9_-]{24,96}", endpoint_id) or
            not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}", delivery_id) or
            not re.fullmatch(r"[0-9]{10}", signed_at) or not re.fullmatch(r"[0-9a-f]{64}", signature)):
        raise HTTPException(403, "Delivery not accepted")
    content_type = one_header(request, "content-type").lower()
    encoding = one_header(request, "content-encoding", required=False)
    if (not re.fullmatch(r'(?:application|text)/xml\s*(?:;\s*charset\s*=\s*(?:utf-8|"utf-8"))?\s*', content_type) or
            encoding is not None and encoding.lower() != "identity"):
        raise HTTPException(415, "UTF-8 ADF XML required")
    length = one_header(request, "content-length", required=False)
    transfer = one_header(request, "transfer-encoding", required=False)
    if transfer is not None and (length is not None or transfer.lower() != "chunked"):
        raise HTTPException(400, "Invalid delivery envelope")
    if length is not None and (not re.fullmatch(r"[0-9]{1,7}", length) or not 1 <= int(length) <= 1_000_000):
        raise HTTPException(413, "Delivery body exceeds limits")
    if not _SLOTS.acquire(blocking=False):
        raise HTTPException(503, "Delivery temporarily unavailable", headers={"Retry-After":"30"})
    try:
        try: await run_in_threadpool(inbound.accepting, endpoint_id)
        except (ValueError, PermissionError, KeyError): raise HTTPException(403, "Delivery not accepted") from None
        except Exception:
            raise HTTPException(503, "Delivery temporarily unavailable", headers={"Retry-After":"30"}) from None
        data = bytearray()
        try:
            async with asyncio.timeout(_BODY_TIMEOUT_SECONDS):
                async for chunk in request.stream():
                    if len(data) + len(chunk) > 1_000_000:
                        raise HTTPException(413, "Delivery body exceeds limits")
                    data.extend(chunk)
        except (TimeoutError, ClientDisconnect):
            raise HTTPException(408, "Delivery body was not received") from None
        if not data or length is not None and len(data) != int(length):
            raise HTTPException(400, "Invalid delivery envelope")
        try:
            return await run_in_threadpool(inbound.receive, endpoint_id, delivery_id, signed_at, signature, bytes(data))
        except inbound.InboundBackpressure:
            raise HTTPException(503, "Delivery review queue is full", headers={"Retry-After":"60"}) from None
        except (InvalidDelivery, CredentialUnavailable, PermissionError):
            raise HTTPException(403, "Delivery not accepted") from None
        except (ValueError, KeyError):
            raise HTTPException(400, "Delivery could not be staged") from None
        except Exception:
            raise HTTPException(503, "Delivery temporarily unavailable", headers={"Retry-After":"30"}) from None
    finally:
        _SLOTS.release()
