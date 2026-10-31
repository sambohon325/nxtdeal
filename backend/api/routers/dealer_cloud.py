"""Dealer-scoped storage controls; uses the existing staff authentication boundary."""
import os
from urllib.parse import urlsplit

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from api.deps import _authenticate
from core import dealer_cloud as cloud

router = APIRouter()


def actor(authorization, roles=("ADMIN",)):
    payload, error = _authenticate(authorization)
    if error or not payload:
        raise HTTPException(401, "Staff sign-in required.")
    if payload.get("role") not in roles:
        raise HTTPException(403, "Your role cannot manage dealer storage.")
    return payload["employee_id"]


def call(fn, *args):
    try:
        return fn(*args)
    except cloud.CloudError as error:
        raise HTTPException(409, str(error)) from None


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    photo_connection: str = Field(default="", max_length=64)
    backup_connection: str = Field(default="", max_length=64)
    interval_hours: int = Field(default=24, ge=1, le=168, strict=True)
    retention_days: int = Field(default=30, ge=1, le=3650, strict=True)
    enabled: bool = False
    public_key: str = Field(default="", max_length=8192)


@router.get("/data-management/cloud")
def get_cloud(authorization: str = Header(None)):
    actor(authorization)
    return call(cloud.status)


@router.put("/data-management/cloud")
def put_cloud(value: Settings, authorization: str = Header(None)):
    employee = actor(authorization)
    return call(cloud.configure, value.model_dump(), employee)


@router.post("/data-management/cloud/backups")
def create_cloud_backup(authorization: str = Header(None)):
    employee = actor(authorization)
    return call(cloud.run_backup, employee)


@router.post("/merchandising/vehicles/{vehicle_id}/cloud-photo")
async def upload_cloud_photo(vehicle_id: str, request: Request, publish: bool = False,
                             authorization: str = Header(None)):
    employee = actor(authorization, ("ADMIN", "OPERATIONS", "MARKETING"))
    if not publish:
        raise HTTPException(400, "Confirm this photo may appear in vehicle listings before uploading.")
    origin = os.getenv("NXTDEAL_PUBLIC_API_ORIGIN", "")
    parts = urlsplit(origin)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password or parts.path not in ("", "/") or parts.query or parts.fragment:
        raise HTTPException(503, "A public HTTPS photo origin must be configured first.")
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > cloud.MAX_PHOTO:
            raise HTTPException(413, "Photo exceeds 10 MB.")
    # Raw body avoids multipart spooling photo bytes onto the app filesystem.
    import asyncio
    return await asyncio.to_thread(call, cloud.upload_photo, vehicle_id, bytes(data), employee, origin.rstrip("/"))


@router.get("/public/vehicle-photos/{photo_id}")
def public_photo(photo_id: str):
    import re
    if not re.fullmatch(r"[a-f0-9]{32}", photo_id):
        raise HTTPException(404, "Photo not found.")
    try:
        data, mime = cloud.read_photo(photo_id)
    except cloud.CloudError:
        raise HTTPException(404, "Photo unavailable.") from None
    return Response(data, media_type=mime, headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})
