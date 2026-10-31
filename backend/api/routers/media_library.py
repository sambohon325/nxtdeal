"""Shared media library router (2026-07-23) -- core/media_library.py's dealership-wide
image asset library (OEM approved images, logos, dealership branding, and live
inventory photos merged in), reachable from every marketing tool. See that module's
own docstring for the "reuse the IMAGE entity type + merge live vehicle photos, no
parallel media store" reasoning.

Follows api/routers/accessories.py's pattern: a self-contained APIRouter() importing
the shared _authenticate helper from api/deps.py.
"""

from fastapi import APIRouter, Header, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from api.deps import _authenticate

from core.media_library_api import (
    list_media_api,
    list_media_categories_api,
    add_media_api,
    remove_media_api,
)


router = APIRouter()


class AddMediaRequest(BaseModel):

    url: str
    name: str = ""
    category: str = "general"
    tags: list[str] = []


@router.get("/media-library/categories")
def media_categories_route(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_media_categories_api(payload["role"])


@router.get("/media-library")
def media_list_route(category: str = None, q: str = None, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_media_api(payload["role"], category=category, query=q)


@router.post("/media-library")
def media_add_route(request: AddMediaRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return add_media_api(
        payload["role"],
        request.url,
        request.name,
        request.category,
        payload["employee_id"],
        tags=request.tags,
    )


@router.delete("/media-library/{image_id}")
def media_remove_route(image_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return remove_media_api(payload["role"], image_id)


@router.post("/media-library/upload")
async def media_upload_route(file: UploadFile = File(...), name: str = Form(""), category: str = Form("general"), authorization: str = Header(None)):
    from core.media_library_api import WRITE_ROLES
    from core.media_uploads import MAX_UPLOAD_BYTES, upload_artwork
    from starlette.concurrency import run_in_threadpool
    payload, error = _authenticate(authorization)
    if error:
        await file.close()
        return error
    if payload["role"] not in WRITE_ROLES:
        await file.close()
        return {"error": "Your role cannot upload shared marketing images."}
    try:
        data = await file.read(MAX_UPLOAD_BYTES + 1)
        return await run_in_threadpool(upload_artwork, data, name or file.filename, category, payload["employee_id"])
    finally:
        await file.close()


@router.get("/public/media-library/{asset_key}")
def public_media_route(asset_key: str):
    from core.media_uploads import public_artwork_path
    path = public_artwork_path(asset_key)
    if path is None:
        return JSONResponse({"error": "Image not found"}, status_code=404)
    return FileResponse(path, media_type="image/png", headers={
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "public, max-age=300",
        "Content-Security-Policy": "default-src 'none'; sandbox",
    })
